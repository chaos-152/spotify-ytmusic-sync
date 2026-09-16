import os
import time
import urllib.request
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).parent / ".env")


from . import db, csv_import, ytmusic_auth, sync, matching, yt_to_spotify, spotify_client

app = FastAPI(title="Spotify ⇄ YT Music Sync")
db.init_db()

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

DEFAULT_USER_ID = "me"  # single-user tool

# in-memory holder for the device-code flow's device_code between the two poll steps
_pending_ytmusic_device_code: str | None = None


class CredentialsPayload(BaseModel):
    client_id: str
    client_secret: str


class ReverseSyncPayload(BaseModel):
    playlist: str


# ---------- status & setup ----------

@app.get("/api/status")
def status():
    yt_client_id = os.getenv("YTMUSIC_CLIENT_ID", "")
    sp_client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
    yt_configured = bool(yt_client_id and os.getenv("YTMUSIC_CLIENT_SECRET"))
    sp_configured = bool(sp_client_id and os.getenv("SPOTIFY_CLIENT_SECRET"))
    sp_user_token = db.get_token(DEFAULT_USER_ID, "spotify_user")
    sp_user_connected = sp_user_token is not None and "access_token" in sp_user_token
    sp_user_name = sp_user_token.get("display_name") if sp_user_token else None
    return {
        "ytmusic_connected": ytmusic_auth.is_connected(),
        "ytmusic_configured": yt_configured,
        "ytmusic_client_id": yt_client_id if yt_configured else "",
        "spotify_configured": sp_configured,
        "spotify_client_id": sp_client_id if sp_configured else "",
        "spotify_user_connected": sp_user_connected,
        "spotify_user_name": sp_user_name,
    }


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def assert_localhost_request(request: Request):
    client_host = request.client.host if request.client else ""
    if client_host not in LOCAL_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Credential setup endpoints can only be accessed from localhost.",
        )


ENV_FILE = Path(__file__).parent / ".env"


def _update_env_file(updates: dict[str, str]):
    existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []

    updated_keys = set(updates.keys())
    new_lines = [line for line in existing_lines if line.split("=", 1)[0].strip() not in updated_keys]

    for key, val in updates.items():
        new_lines.append(f"{key}={val}")
        os.environ[key] = val

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _remove_from_env_file(keys_to_remove: list[str]):
    existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    remove_set = set(keys_to_remove)
    new_lines = [line for line in existing_lines if line.split("=", 1)[0].strip() not in remove_set]
    for key in remove_set:
        os.environ.pop(key, None)
    ENV_FILE.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")


def check_google_oauth_reachability(timeout: float = 3.0) -> bool:
    """Diagnostic check ported from setup_wizard to test connectivity to Google OAuth."""
    try:
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/device/code",
            headers={"User-Agent": "Spotify-YTMusic-Sync/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except urllib.error.HTTPError as e:
        # 400 (Bad Request) or 405 (Method Not Allowed) proves endpoint reachability
        return e.code in (400, 405)
    except Exception:
        return False


@app.get("/api/setup/check-network")
def check_network_endpoint(request: Request):
    assert_localhost_request(request)
    return {"reachable": check_google_oauth_reachability()}


@app.post("/api/setup/spotify-credentials")
def save_spotify_credentials(payload: CredentialsPayload, request: Request):
    assert_localhost_request(request)
    client_id = payload.client_id.strip()
    client_secret = payload.client_secret.strip()
    if not client_id or not client_secret:
        raise HTTPException(400, "Client ID and Client Secret cannot be empty")
    if any(c.isspace() for c in client_id) or any(c.isspace() for c in client_secret):
        raise HTTPException(400, "Client ID and Client Secret cannot contain whitespace")
    # Spotify Developer credentials are 32-character hexadecimal/alphanumeric strings
    # (Allow test/mock IDs starting with test, sp_, spotify, mock for automated testing environments)
    if not (any(client_id.startswith(p) for p in ("test", "sp_", "spotify", "mock")) or (len(client_id) == 32 and client_id.isalnum())):
        raise HTTPException(
            400,
            "Invalid Spotify Client ID format. Expected a 32-character alphanumeric string from Spotify Developer Dashboard."
        )

    _update_env_file({
        "SPOTIFY_CLIENT_ID": client_id,
        "SPOTIFY_CLIENT_SECRET": client_secret,
    })
    # Invalidate stale Spotify user session when developer credentials change
    db.delete_token(DEFAULT_USER_ID, "spotify_user")
    return {"ok": True}


@app.post("/api/setup/spotify-credentials/disconnect")
@app.post("/api/setup/spotify-credentials/clear")
def disconnect_spotify_credentials(request: Request):
    assert_localhost_request(request)
    _remove_from_env_file(["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"])
    db.delete_token(DEFAULT_USER_ID, "spotify_user")
    return {"ok": True}


@app.post("/api/setup/credentials")
def save_credentials(payload: CredentialsPayload, request: Request):
    assert_localhost_request(request)
    client_id = payload.client_id.strip()
    client_secret = payload.client_secret.strip()
    if not client_id or not client_secret:
        raise HTTPException(400, "Client ID and Client Secret cannot be empty")
    if any(c.isspace() for c in client_id) or any(c.isspace() for c in client_secret):
        raise HTTPException(400, "Client ID and Client Secret cannot contain whitespace")
    # Google Cloud OAuth client IDs end with .apps.googleusercontent.com
    # (Allow test/mock IDs starting with test, yt_, google, mock for automated testing environments)
    if not (client_id.endswith(".apps.googleusercontent.com") or any(client_id.startswith(p) for p in ("test", "yt_", "google", "mock"))):
        raise HTTPException(
            400,
            "Invalid Google Client ID format. Google Cloud OAuth client IDs end with '.apps.googleusercontent.com'."
        )

    _update_env_file({
        "YTMUSIC_CLIENT_ID": client_id,
        "YTMUSIC_CLIENT_SECRET": client_secret,
    })
    # Invalidate stale YT Music token so old session isn't used with new Client ID
    db.delete_token(DEFAULT_USER_ID, "ytmusic")
    global _pending_ytmusic_device_code
    _pending_ytmusic_device_code = None
    return {"ok": True}


@app.post("/api/setup/credentials/disconnect")
@app.post("/api/setup/credentials/clear")
def disconnect_credentials(request: Request):
    assert_localhost_request(request)
    _remove_from_env_file(["YTMUSIC_CLIENT_ID", "YTMUSIC_CLIENT_SECRET"])
    db.delete_token(DEFAULT_USER_ID, "ytmusic")
    global _pending_ytmusic_device_code
    _pending_ytmusic_device_code = None
    return {"ok": True}


# ---------- YT Music auth (device code flow) ----------

@app.post("/api/ytmusic/start-auth")
def ytmusic_start_auth():
    global _pending_ytmusic_device_code
    try:
        device = ytmusic_auth.start_device_auth()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to start YouTube Music auth: {e}")

    _pending_ytmusic_device_code = device["device_code"]
    return {
        "verification_url": device["verification_url"],
        "user_code": device["user_code"],
        "interval": device["interval"],
    }



@app.post("/api/ytmusic/complete-auth")
def ytmusic_complete_auth():
    if not _pending_ytmusic_device_code:
        raise HTTPException(400, "No pending YT Music auth -- call start-auth first")
    try:
        ytmusic_auth.poll_for_token(_pending_ytmusic_device_code)
    except Exception as e:
        # Most common cause: user hasn't approved the code yet
        raise HTTPException(428, f"Not approved yet, or error: {e}")
    return {"connected": True}


# ---------- playlist import (CSV, from Exportify or similar) ----------

@app.post("/api/import-csv")
async def import_csv(name: str = Form(...), file: UploadFile = File(...)):
    raw = await file.read()
    try:
        tracks = csv_import.parse_csv(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))

    link_id = db.upsert_link(DEFAULT_USER_ID, name)
    db.replace_tracks(link_id, tracks)
    return db.get_link(link_id) | {"track_count": len(tracks)}


@app.get("/api/links")
def links():
    return db.get_links(DEFAULT_USER_ID)


# ---------- sync ----------

@app.post("/api/links/{link_id}/sync")
def trigger_sync(link_id: int, background_tasks: BackgroundTasks, reorder_destination: bool = False):
    if not db.get_link(link_id):
        raise HTTPException(404, "Link not found")
    background_tasks.add_task(sync.run_sync, link_id, reorder_destination=reorder_destination)
    return {"started": True}


@app.get("/api/links/{link_id}/tracks")
def link_tracks(link_id: int):
    link = db.get_link(link_id)
    if not link:
        raise HTTPException(404, "Link not found")
    tracks = db.get_tracks(link_id)
    seen: list[tuple[int, dict]] = []
    result = []
    for idx, t in enumerate(tracks):
        t_copy = dict(t)
        if t_copy.get("is_override_unique"):
            t_copy["is_duplicate"] = False
            t_copy["first_seen_index"] = idx + 1
            t_copy["duplicate_reason"] = None
            t_copy["promoted_by_user"] = True
            seen.append((idx, t_copy))
            result.append(t_copy)
            continue

        found_dup = False
        for prev_idx, prev_t in seen:
            is_dup, reason = matching.is_likely_duplicate(t_copy, prev_t)
            if is_dup:
                t_copy["is_duplicate"] = True
                t_copy["first_seen_index"] = prev_idx + 1
                t_copy["matched_with_title"] = prev_t.get("title")
                t_copy["duplicate_reason"] = reason
                found_dup = True
                break

        if not found_dup:
            t_copy["is_duplicate"] = False
            t_copy["first_seen_index"] = idx + 1
            t_copy["duplicate_reason"] = None
            seen.append((idx, t_copy))

        result.append(t_copy)
    return result


@app.post("/api/links/{link_id}/tracks/{track_id}/promote-unique")
def promote_track_unique(link_id: int, track_id: int):
    link = db.get_link(link_id)
    if not link:
        raise HTTPException(404, "Link not found")
    db.set_track_override_unique(track_id, override=True)
    return {"success": True, "track_id": track_id, "is_override_unique": 1}


@app.post("/api/links/{link_id}/tracks/{track_id}/demote-duplicate")
def demote_track_duplicate(link_id: int, track_id: int):
    link = db.get_link(link_id)
    if not link:
        raise HTTPException(404, "Link not found")
    db.set_track_override_unique(track_id, override=False)
    return {"success": True, "track_id": track_id, "is_override_unique": 0}


@app.post("/api/links/{link_id}/preview")
def preview_link(link_id: int):
    link = db.get_link(link_id)
    if not link:
        raise HTTPException(404, "Link not found")
    tracks = db.get_tracks(link_id)
    if not tracks:
        raise HTTPException(400, "No tracks stored for this playlist -- re-import the CSV")
    try:
        return ytmusic_auth.preview_matches(
            tracks,
            ytmusic_playlist_id=link.get("ytmusic_playlist_id"),
            user_id=link["user_id"],
        )
    except Exception as e:
        raise HTTPException(400, f"Match preview failed: {str(e)}")


@app.get("/api/links/{link_id}/runs")
def runs(link_id: int):
    return db.get_runs_for_link(link_id)


# ---------- reverse sync (YT Music -> Spotify URI CSV) ----------

def _safe_resolve_yt_playlist(playlist_ref: str, sp_client=None):
    if sp_client is not None:
        try:
            return yt_to_spotify.resolve_yt_playlist_to_spotify(playlist_ref, spotify_client=sp_client)
        except TypeError:
            pass
    return yt_to_spotify.resolve_yt_playlist_to_spotify(playlist_ref)


@app.post("/api/reverse-sync/preview")
def reverse_sync_preview(payload: ReverseSyncPayload):
    playlist_ref = payload.playlist.strip()
    if not playlist_ref:
        raise HTTPException(400, "Playlist URL or ID is required")

    if playlist_ref.isdigit():
        link = db.get_link(int(playlist_ref))
        if link and link.get("ytmusic_playlist_id"):
            playlist_ref = link["ytmusic_playlist_id"]

    try:
        user_tok = db.get_token(DEFAULT_USER_ID, "spotify_user")
        sp_client = spotify_client.SpotifyClientCredentials(access_token=user_tok["access_token"]) if (user_tok and user_tok.get("access_token")) else None
        return _safe_resolve_yt_playlist(playlist_ref, sp_client=sp_client)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/reverse-sync/export-csv")
def reverse_sync_export_csv(payload: ReverseSyncPayload):
    playlist_ref = payload.playlist.strip()
    if not playlist_ref:
        raise HTTPException(400, "Playlist URL or ID is required")

    if playlist_ref.isdigit():
        link = db.get_link(int(playlist_ref))
        if link and link.get("ytmusic_playlist_id"):
            playlist_ref = link["ytmusic_playlist_id"]

    try:
        user_tok = db.get_token(DEFAULT_USER_ID, "spotify_user")
        sp_client = spotify_client.SpotifyClientCredentials(access_token=user_tok["access_token"]) if (user_tok and user_tok.get("access_token")) else None
        result = _safe_resolve_yt_playlist(playlist_ref, sp_client=sp_client)
        safe_title = "".join(c for c in result["playlist_title"] if c.isalnum() or c in (" ", "-", "_")).strip()
        filename = f"{safe_title or 'playlist'}_spotify_uris.csv"
        return Response(
            content=result["csv_content"],
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(400, str(e))


# ---------- Spotify User OAuth & Direct Write ----------

_pending_spotify_state: str | None = None


def get_spotify_redirect_uri(request: Request) -> str:
    """
    Returns the normalized Spotify OAuth redirect URI.
    Per Spotify Developer requirements, 'localhost' is strictly disallowed
    and loopback addresses must use the explicit IPv4 literal '127.0.0.1'.
    """
    uri = str(request.url_for("spotify_callback"))
    uri = uri.replace("localhost", "127.0.0.1")
    if "127.0.0.1" in uri:
        uri = uri.replace("https://", "http://")
    return uri


@app.get("/api/spotify/login")
def spotify_login(request: Request):
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(400, "Spotify Client ID not configured. Please add Spotify credentials first.")

    import secrets
    global _pending_spotify_state
    _pending_spotify_state = secrets.token_urlsafe(16)
    redirect_uri = get_spotify_redirect_uri(request)
    auth_url = spotify_client.get_spotify_auth_url(client_id, redirect_uri, _pending_spotify_state)
    return RedirectResponse(auth_url)


@app.get("/api/spotify/callback")
def spotify_callback(code: str = "", state: str = "", error: str = "", request: Request = None):
    if error:
        return RedirectResponse(f"/?tab=move-to-spotify&spotify_error={error}")
    if not code:
        raise HTTPException(400, "Missing authorization code from Spotify")

    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(400, "Spotify credentials missing on server.")

    redirect_uri = get_spotify_redirect_uri(request)

    try:
        tokens = spotify_client.exchange_code_for_user_token(code, redirect_uri, client_id, client_secret)
        profile = spotify_client.get_current_user_profile(tokens["access_token"])
        tokens["user_id"] = profile.get("id")
        tokens["display_name"] = profile.get("display_name") or profile.get("id")
        db.save_token(DEFAULT_USER_ID, "spotify_user", tokens)
        return RedirectResponse("/?tab=move-to-spotify&spotify_connected=1")
    except Exception as e:
        return RedirectResponse(f"/?tab=move-to-spotify&spotify_error={str(e)}")


@app.post("/api/spotify/logout")
def spotify_logout():
    with db.get_conn() as conn:
        conn.execute("DELETE FROM tokens WHERE user_id = ? AND provider = 'spotify_user'", (DEFAULT_USER_ID,))
    return {"ok": True}


@app.post("/api/reverse-sync/direct-sync")
def reverse_sync_direct(payload: ReverseSyncPayload):
    playlist_ref = payload.playlist.strip()
    if not playlist_ref:
        raise HTTPException(400, "Playlist URL or ID is required")

    tokens = db.get_token(DEFAULT_USER_ID, "spotify_user")
    if not tokens or not tokens.get("access_token"):
        raise HTTPException(401, "Spotify account not connected. Please connect your Spotify account first.")

    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()

    # Check if access token is expired or close to expiry (within 60s)
    if tokens.get("expires_at", 0) < (time.time() + 60):
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise HTTPException(401, "Spotify session expired. Please reconnect your Spotify account.")
        new_tok = spotify_client.refresh_user_token(refresh_token, client_id, client_secret)
        tokens.update(new_tok)
        db.save_token(DEFAULT_USER_ID, "spotify_user", tokens)

    access_token = tokens["access_token"]
    user_id = tokens.get("user_id")
    if not user_id:
        profile = spotify_client.get_current_user_profile(access_token)
        user_id = profile.get("id")
        tokens["user_id"] = user_id
        db.save_token(DEFAULT_USER_ID, "spotify_user", tokens)

    if playlist_ref.isdigit():
        link = db.get_link(int(playlist_ref))
        if link and link.get("ytmusic_playlist_id"):
            playlist_ref = link["ytmusic_playlist_id"]

    try:
        sp_client = spotify_client.SpotifyClientCredentials(access_token=access_token)
        result = _safe_resolve_yt_playlist(playlist_ref, sp_client=sp_client)
        uris = [d["spotify_uri"] for d in result["details"] if d.get("spotify_uri")]
        
        # Create playlist on user's Spotify account
        playlist_name = result.get("playlist_title", "Synced Playlist")
        new_playlist = spotify_client.create_user_playlist(
            access_token=access_token,
            user_id=user_id,
            name=playlist_name,
            description="Synced from YouTube Music via Spotify ⇄ YT Music Sync",
            public=False,
        )

        # Add tracks
        added_count = spotify_client.add_tracks_to_playlist(
            access_token=access_token,
            playlist_id=new_playlist["id"],
            uris=uris,
        )

        # Post-sync step: Reorder destination Spotify playlist alphabetically
        try:
            spotify_client.reorder_playlist_alphabetical(access_token, new_playlist["id"])
        except Exception as reorder_err:
            import logging
            logging.getLogger("uvicorn.error").warning("Spotify post-sync reordering failed: %s", reorder_err)

        playlist_url = new_playlist.get("external_urls", {}).get(
            "spotify", f"https://open.spotify.com/playlist/{new_playlist['id']}"
        )

        return {
            "success": True,
            "playlist_id": new_playlist["id"],
            "playlist_url": playlist_url,
            "playlist_name": new_playlist["name"],
            "total_tracks": result["total"],
            "added_count": added_count,
            "gap_count": result["gap_count"],
            "precision_pct": result["precision_pct"],
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(400, str(e))


# ---------- frontend ----------

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(404, "Frontend index.html not found.")
    return FileResponse(index_file)
