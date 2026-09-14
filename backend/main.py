import os
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).parent / ".env")


from . import db, csv_import, ytmusic_auth, sync, matching

app = FastAPI(title="Spotify (CSV) -> YT Music Sync")
db.init_db()

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

DEFAULT_USER_ID = "me"  # single-user tool

# in-memory holder for the device-code flow's device_code between the two poll steps
_pending_ytmusic_device_code: str | None = None


from pydantic import BaseModel


class CredentialsPayload(BaseModel):
    client_id: str
    client_secret: str


# ---------- status & setup ----------

@app.get("/api/status")
def status():
    configured = bool(os.getenv("YTMUSIC_CLIENT_ID") and os.getenv("YTMUSIC_CLIENT_SECRET"))
    return {
        "ytmusic_connected": ytmusic_auth.is_connected(),
        "ytmusic_configured": configured,
    }


@app.post("/api/setup/credentials")
def save_credentials(payload: CredentialsPayload):
    client_id = payload.client_id.strip()
    client_secret = payload.client_secret.strip()
    if not client_id or not client_secret:
        raise HTTPException(400, "Client ID and Client Secret cannot be empty")

    env_file = Path(__file__).parent / ".env"
    content = (
        "# Google Cloud OAuth Credentials\n"
        f"YTMUSIC_CLIENT_ID={client_id}\n"
        f"YTMUSIC_CLIENT_SECRET={client_secret}\n"
    )
    env_file.write_text(content, encoding="utf-8")
    os.environ["YTMUSIC_CLIENT_ID"] = client_id
    os.environ["YTMUSIC_CLIENT_SECRET"] = client_secret
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
def trigger_sync(link_id: int, background_tasks: BackgroundTasks):
    if not db.get_link(link_id):
        raise HTTPException(404, "Link not found")
    background_tasks.add_task(sync.run_sync, link_id)
    return {"started": True}


@app.get("/api/links/{link_id}/tracks")
def link_tracks(link_id: int):
    link = db.get_link(link_id)
    if not link:
        raise HTTPException(404, "Link not found")
    tracks = db.get_tracks(link_id)
    seen: dict[tuple[str, str], int] = {}
    result = []
    for idx, t in enumerate(tracks):
        key = (matching.clean_text(t.get("title", "")), matching.clean_text(t.get("artist", "")))
        t_copy = dict(t)
        if key in seen:
            t_copy["is_duplicate"] = True
            t_copy["first_seen_index"] = seen[key] + 1
        else:
            seen[key] = idx
            t_copy["is_duplicate"] = False
            t_copy["first_seen_index"] = idx + 1
        result.append(t_copy)
    return result


@app.post("/api/links/{link_id}/preview")
def preview_link(link_id: int):
    link = db.get_link(link_id)
    if not link:
        raise HTTPException(404, "Link not found")
    tracks = db.get_tracks(link_id)
    if not tracks:
        raise HTTPException(400, "No tracks stored for this playlist -- re-import the CSV")
    return ytmusic_auth.preview_matches(
        tracks,
        ytmusic_playlist_id=link.get("ytmusic_playlist_id"),
        user_id=link["user_id"],
    )


@app.get("/api/links/{link_id}/runs")
def runs(link_id: int):
    return db.get_runs_for_link(link_id)


# ---------- frontend ----------

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
