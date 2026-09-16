"""
YouTube Music auth via ytmusicapi's OAuth (device-code flow).

There's no official "YouTube Music API" — ytmusicapi drives the same
endpoints the web client uses, authenticated with a Google OAuth token that
has YouTube scope. Device-code flow means no redirect URI needed: the user
visits a short google.com URL and enters a code we display.

Requires a Google Cloud OAuth client (type: "TVs and Limited Input devices")
with the YouTube Data API v3 enabled.
Env vars needed: YTMUSIC_CLIENT_ID, YTMUSIC_CLIENT_SECRET
"""
import os
import re
import time
import requests
from ytmusicapi.auth.oauth import OAuthCredentials
from ytmusicapi import YTMusic
from ytmusicapi.constants import OAUTH_TOKEN_URL, OAUTH_SCOPE, OAUTH_USER_AGENT

from . import db
from . import matching

DEFAULT_USER_ID = "me"

# Canonical Google OAuth 2.0 Device Authorization endpoint (RFC 8628).
# Used as a resilient fallback if ytmusicapi's endpoint (www.youtube.com/o/oauth2/device/code)
# is blocked or returns a non-JSON error. Aligned with ytmusicapi's OAUTH_SCOPE and OAUTH_TOKEN_URL.
GOOGLE_OAUTH_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"


def _credentials() -> OAuthCredentials:
    client_id = os.getenv("YTMUSIC_CLIENT_ID")
    client_secret = os.getenv("YTMUSIC_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError(
            "Missing YTMUSIC_CLIENT_ID or YTMUSIC_CLIENT_SECRET. "
            "Please create backend/.env with your Google Cloud OAuth credentials."
        )
    return OAuthCredentials(
        client_id=client_id,
        client_secret=client_secret,
    )



def start_device_auth() -> dict:
    """Kick off the device flow. Returns {verification_url, user_code, device_code, interval, expires_in}."""
    creds = _credentials()
    code = None
    try:
        code = creds.get_code()
    except Exception as e:
        # Fallback to direct call to oauth2.googleapis.com if ytmusicapi's default URL fails or returns non-JSON
        try:
            resp = requests.post(
                GOOGLE_OAUTH_DEVICE_CODE_URL,
                data={"client_id": creds.client_id, "scope": OAUTH_SCOPE},
                headers={"User-Agent": OAUTH_USER_AGENT},
                timeout=10,
            )
            if resp.status_code == 200:
                code = resp.json()
            else:
                err_msg = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("error_description", err_json.get("error", resp.text))
                except Exception:
                    pass
                raise RuntimeError(f"Google OAuth rejected Client ID ({resp.status_code}): {err_msg}")
        except RuntimeError:
            raise
        except Exception as fallback_err:
            raise RuntimeError(f"Failed to connect to Google OAuth service: {e}") from fallback_err

    if not isinstance(code, dict) or "verification_url" not in code:
        raise RuntimeError(f"Unexpected response from Google authorization server: {code}")

    return {
        "verification_url": code["verification_url"],
        "user_code": code["user_code"],
        "device_code": code["device_code"],
        "interval": code.get("interval", 5),
        "expires_in": code.get("expires_in", 1800),
    }


def poll_for_token(device_code: str, user_id: str = DEFAULT_USER_ID) -> dict:
    """
    Call after the user has visited verification_url and entered the code.
    Raises if the user hasn't approved yet (caller should retry after `interval` seconds).
    """
    creds = _credentials()
    try:
        token = creds.token_from_code(device_code)
    except Exception as e:
        # Fallback to direct call to oauth2.googleapis.com/token
        try:
            resp = requests.post(
                OAUTH_TOKEN_URL,
                data={
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "code": device_code,
                    "grant_type": "http://oauth.net/grant_type/device/1.0",
                },
                headers={"User-Agent": OAUTH_USER_AGENT},
                timeout=10,
            )
            token = resp.json()
        except Exception:
            raise RuntimeError(f"Failed to retrieve token from Google: {e}")

    # Google returns {"error": "authorization_pending"} (or "slow_down")
    # when the user hasn't approved yet — don't save that as a token.
    if "error" in token:
        raise RuntimeError(token.get("error_description", token["error"]))

    if "access_token" not in token:
        raise RuntimeError("Token response missing access_token — user may not have approved yet")

    now = time.time()
    expires_in = token.get("expires_in", 3599)
    token["expires_at"] = now + expires_in

    # If Google did not return a refresh_token (e.g. user already consented previously),
    # preserve the previously saved refresh_token if we have one.
    existing = db.get_token(user_id, "ytmusic")
    if existing and existing.get("refresh_token") and not token.get("refresh_token"):
        token["refresh_token"] = existing["refresh_token"]

    token["filepath"] = None  # we don't use ytmusicapi's file-based cache
    db.save_token(user_id, "ytmusic", token)
    return token


def is_connected(user_id: str = DEFAULT_USER_ID) -> bool:
    token = db.get_token(user_id, "ytmusic")
    if not token or "access_token" not in token:
        return False
    # If token has a refresh_token, it can be renewed automatically only if Google credentials are configured
    has_creds = bool(os.getenv("YTMUSIC_CLIENT_ID") and os.getenv("YTMUSIC_CLIENT_SECRET"))
    if token.get("refresh_token") and has_creds:
        return True
    # Otherwise check if the current access token is still unexpired (with 60s buffer)
    return token.get("expires_at", 0) > time.time() + 60


class PlaylistAddResult(int):
    """
    Subclass of int for full backward compatibility with callers/tests expecting an integer count,
    while also carrying per-item success and failure diagnostic mappings.
    """
    def __new__(cls, val: int, successful_ids: set[str] | None = None, failed_ids: dict[str, str] | None = None):
        obj = super().__new__(cls, val)
        obj.successful_ids = successful_ids if successful_ids is not None else set()
        obj.failed_ids = failed_ids if failed_ids is not None else {}
        return obj


class YouTubeSyncClient:
    """
    YouTube client that uses the official YouTube Data API v3 for playlist
    creation and item management (using the user's OAuth token), and ytmusicapi
    for fast, high-quality song searching and metadata scoring.
    """

    def __init__(self, access_token: str):
        self.access_token = access_token
        self._ytm = YTMusic()

    def create_playlist(self, title: str, description: str = "") -> str:
        url = "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        body = {
            "snippet": {
                "title": title,
                "description": description,
            },
            "status": {
                "privacyStatus": "private",
            },
        }
        resp = requests.post(url, json=body, headers=headers)
        if resp.status_code >= 400:
            raise RuntimeError(f"Failed to create playlist on YouTube: {resp.status_code} {resp.text}")
        data = resp.json()
        return data["id"]

    def get_playlist(self, playlist_id: str, limit: int | None = None) -> dict:
        url = "https://www.googleapis.com/youtube/v3/playlistItems"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        video_ids = []
        page_token = None
        while True:
            params = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            resp = requests.get(url, params=params, headers=headers)
            if resp.status_code >= 400:
                break
            data = resp.json()
            for item in data.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if vid:
                    video_ids.append({"videoId": vid})
            page_token = data.get("nextPageToken")
            if not page_token or (limit and len(video_ids) >= limit):
                break
        return {"tracks": video_ids}

    def search(self, query: str, filter: str = "songs", limit: int = 5) -> list:
        return self._ytm.search(query, filter=filter, limit=limit)

    def add_playlist_items(self, playlist_id: str, video_ids: list[str], duplicates: bool = False) -> PlaylistAddResult:
        url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        added_count = 0
        successful_ids: set[str] = set()
        failed_ids: dict[str, str] = {}

        for idx, vid in enumerate(video_ids):
            body = {
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": vid,
                    },
                }
            }
            resp = requests.post(url, json=body, headers=headers)
            if resp.status_code in (200, 201):
                added_count += 1
                successful_ids.add(vid)
            elif resp.status_code == 403 and "quotaExceeded" in resp.text:
                # Stop immediately if daily quota ceiling is reached
                failed_ids[vid] = "YouTube API daily quota ceiling reached"
                for remaining_vid in video_ids[idx + 1:]:
                    failed_ids[remaining_vid] = "YouTube API daily quota ceiling reached"
                break
            else:
                reason = f"YouTube API rejected insert ({resp.status_code})"
                try:
                    err_data = resp.json().get("error", {})
                    msg = err_data.get("message")
                    if msg:
                        reason = f"YouTube API: {msg}"
                except Exception:
                    pass
                failed_ids[vid] = reason

        return PlaylistAddResult(added_count, successful_ids, failed_ids)

    def reorder_playlist_alphabetical(self, playlist_id: str, max_moves: int = 20) -> dict:
        """
        Reorders items in a YouTube Music playlist alphabetically by track title (artist as tiebreaker).
        YouTube Data API v3 requires 1 PUT playlistItems call (50 quota units) per moved item.
        Applies a quota guardrail: if required moves > max_moves (default 20 = 1000 quota units),
        the operation is skipped with a clear explanation to protect daily quota.
        """
        url = "https://www.googleapis.com/youtube/v3/playlistItems"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        items = []
        page_token = None
        while True:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            resp = requests.get(url, params=params, headers=headers)
            if resp.status_code >= 400:
                break
            data = resp.json()
            for item in data.get("items", []):
                items.append(item)
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        if len(items) <= 1:
            return {"reordered": True, "moves": 0, "total_tracks": len(items), "quota_used": 0}

        sorted_items = sorted(
            items,
            key=lambda x: (
                (x.get("snippet", {}).get("title") or "").lower().strip(),
                (x.get("snippet", {}).get("videoOwnerChannelTitle") or "").lower().strip()
            )
        )

        current_ids = [it["id"] for it in items]
        target_ids = [it["id"] for it in sorted_items]

        moves_needed = sum(1 for c, t in zip(current_ids, target_ids) if c != t)
        if moves_needed == 0:
            return {"reordered": True, "moves": 0, "total_tracks": len(items), "quota_used": 0}

        if moves_needed > max_moves:
            return {
                "reordered": False,
                "reason": "quota_guardrail_exceeded",
                "moves_needed": moves_needed,
                "quota_needed": moves_needed * 50,
                "max_moves_allowed": max_moves,
                "total_tracks": len(items),
                "message": (
                    f"Skipping reorder to protect YouTube API quota: {moves_needed} moves needed "
                    f"({moves_needed * 50} quota units), exceeding guardrail limit of {max_moves} moves."
                ),
            }

        moves_done = 0
        update_url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
        for target_pos, target_item in enumerate(sorted_items):
            if target_pos < len(items) and items[target_pos]["id"] == target_item["id"]:
                continue

            body = {
                "id": target_item["id"],
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": target_item.get("snippet", {}).get("resourceId", {
                        "kind": "youtube#video",
                        "videoId": target_item.get("contentDetails", {}).get("videoId")
                    }),
                    "position": target_pos,
                }
            }
            put_resp = requests.put(update_url, json=body, headers=headers)
            if put_resp.status_code in (200, 201):
                moves_done += 1
            elif put_resp.status_code == 403 and "quotaExceeded" in put_resp.text:
                return {
                    "reordered": False,
                    "reason": "quota_exceeded",
                    "moves_done": moves_done,
                    "quota_used": moves_done * 50,
                    "total_tracks": len(items),
                }

        return {
            "reordered": True,
            "moves": moves_done,
            "quota_used": moves_done * 50,
            "total_tracks": len(items),
        }


def get_client(user_id: str = DEFAULT_USER_ID) -> YouTubeSyncClient:
    token = db.get_token(user_id, "ytmusic")
    if not token or "access_token" not in token:
        raise RuntimeError("YouTube Music not connected yet — please click 'Connect YT Music' first.")

    now = time.time()
    expires_at = token.get("expires_at", 0)

    # Check if token is close to expiry
    if expires_at < now + 60:
        refresh_tok = token.get("refresh_token")
        if not refresh_tok:
            raise RuntimeError(
                "Your YouTube Music session has expired (access tokens expire after 1 hour). "
                "Please click 'Connect YT Music' to reconnect."
            )
        try:
            creds = _credentials()
        except ValueError as e:
            raise RuntimeError(
                "YouTube credentials not configured. Please click '⚙️ Setup Google Credentials' first."
            ) from e

        try:
            refreshed = creds.refresh_token(refresh_tok)
            if "access_token" in refreshed:
                token["access_token"] = refreshed["access_token"]
                token["expires_in"] = refreshed.get("expires_in", 3599)
                token["expires_at"] = time.time() + token["expires_in"]
                if "refresh_token" in refreshed:
                    token["refresh_token"] = refreshed["refresh_token"]
                token["filepath"] = None
                db.save_token(user_id, "ytmusic", token)
        except Exception as e:
            raise RuntimeError(
                f"Your YouTube Music session has expired (Google Testing-mode refresh tokens expire every 7 days). "
                f"Please click 'Connect YT Music' in the UI to reconnect: {e}"
            )

    return YouTubeSyncClient(access_token=token["access_token"])



def create_playlist(title: str, description: str, user_id: str = DEFAULT_USER_ID) -> str:
    yt = get_client(user_id)
    return yt.create_playlist(title, description)


def _is_in_existing_keys(title: str, artist: str, existing_keys: set) -> bool:
    t = title.lower().strip()
    a = artist.lower().strip()
    if (t, a) in existing_keys:
        return True
    if t in existing_keys and not any(isinstance(k, tuple) for k in existing_keys):
        return True

    core_t = matching.strip_featured_and_version_suffixes(title)

    for k in existing_keys:
        if isinstance(k, tuple):
            k_title, k_artist = k
            if k_title == t:
                if not k_artist or not a or k_artist in a or a in k_artist:
                    return True
            if core_t:
                core_k = matching.strip_featured_and_version_suffixes(k_title)
                if core_k and core_k == core_t:
                    if not k_artist or not a or k_artist in a or a in k_artist:
                        return True
        elif isinstance(k, str):
            if k == t:
                return True
            if core_t and matching.strip_featured_and_version_suffixes(k) == core_t:
                return True
    return False


def get_playlist_existing_tracks(playlist_id: str, user_id: str = DEFAULT_USER_ID) -> tuple[set[str], set]:
    """
    Retrieves all existing tracks in a YouTube Music playlist.
    Returns:
        (video_id_set, title_key_set)
        video_id_set  -- raw videoIds already in the playlist
        title_key_set -- normalized (title, artist) tuples for semantic dedup across sessions
    """
    yt = get_client(user_id)
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    headers = {"Authorization": f"Bearer {yt.access_token}"}
    video_ids: set[str] = set()
    title_keys: set = set()
    page_token = None
    try:
        while True:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            resp = requests.get(url, params=params, headers=headers)
            if resp.status_code >= 400:
                break
            data = resp.json()
            for item in data.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                snippet = item.get("snippet", {})
                title = snippet.get("title", "").lower().strip()
                channel = (snippet.get("videoOwnerChannelTitle") or "").lower().replace(" - topic", "").strip()
                if vid:
                    video_ids.add(vid)
                if title:
                    title_keys.add((title, channel) if channel else (title, ""))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    except Exception:
        pass
    return video_ids, title_keys


def get_playlist_video_ids(playlist_id: str, user_id: str = DEFAULT_USER_ID) -> set[str]:
    """Backwards-compatible wrapper — returns videoId set only."""
    video_ids, _ = get_playlist_existing_tracks(playlist_id, user_id)
    return video_ids


def sanitize_search_query(title: str, artist: str) -> str:
    """
    Sanitizes track title and artist for YouTube Music search:
    - Strips literal and escaped quotes (\", ", ') which force exact phrase syntax
    - Strips stray backslashes and pipe characters
    - Normalizes semicolons/commas in compound artists into spaces
    - Normalizes multiple spaces and trims
    """
    cleaned_title = re.sub(r'[\"\'\\]', " ", title or "")
    cleaned_artist = re.sub(r'[\"\'\\]', " ", artist or "")
    cleaned_artist = re.sub(r"[;,]", " ", cleaned_artist)
    query = f"{cleaned_title} {cleaned_artist}"
    return " ".join(query.split())


def search_and_add(
    playlist_id: str,
    tracks: list[dict],
    user_id: str = DEFAULT_USER_ID,
    on_progress=None,
    reorder_destination: bool = False,
) -> dict:
    """
    For each track from the imported CSV:
    1. Check existing playlist items by BOTH videoId AND normalized title to prevent
       semantic duplicates when YouTube search returns alternate uploads across sessions.
    2. Search YT Music for candidates with query sanitization and fallback.
    3. Add only new, validated matches to the YouTube Music playlist in batches.
    Returns {added: int, skipped: int, errors: [{track, reason}], details: [{track telemetry}]}.
    """
    yt = get_client(user_id)
    existing_video_ids, existing_title_keys = get_playlist_existing_tracks(playlist_id, user_id)

    # If this is a new/empty playlist, sort the queue alphabetically upfront (0 extra quota cost)
    if len(existing_video_ids) == 0:
        tracks = sorted(
            tracks,
            key=lambda t: (
                (t.get("title") or "").lower().strip(),
                (t.get("artist") or "").lower().strip()
            )
        )

    added, skipped, errors = 0, 0, []
    video_ids_to_add = []
    details = []

    for idx, t in enumerate(tracks):
        if on_progress:
            on_progress(idx + 1, len(tracks), t.get("title", ""))

        query = sanitize_search_query(t.get("title", ""), t.get("artist", ""))
        try:
            results = yt.search(query, filter="songs", limit=5)
            if not results:
                # Try fallback query
                fallback_query = sanitize_search_query(t.get("artist", ""), t.get("title", ""))
                if fallback_query != query:
                    results = yt.search(fallback_query, filter="songs", limit=5)

            if not results:
                skipped += 1
                errors.append({"track": query, "reason": "no search results"})
                details.append({
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "status": "skipped",
                    "category": "no_results",
                    "score": 0.0,
                    "reason": "no search results",
                })
                continue

            best_match, score = matching.find_best_match(t, results)

            # Fallback: try artist-first query if first pass fell below threshold
            if not best_match:
                fallback_query = sanitize_search_query(t.get("artist", ""), t.get("title", ""))
                if fallback_query != query:
                    fallback_results = yt.search(fallback_query, filter="songs", limit=5)
                    if fallback_results:
                        fb_match, fb_score = matching.find_best_match(t, fallback_results)
                        if fb_match and fb_score > score:
                            best_match, score = fb_match, fb_score

            if not best_match:
                skipped += 1
                errors.append({"track": query, "reason": f"no match met confidence threshold (best score: {score:.1f})"})
                details.append({
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "status": "skipped",
                    "category": "threshold_miss",
                    "score": round(score, 1),
                    "reason": f"no match met confidence threshold (best score: {score:.1f})",
                })
                continue

            vid = best_match["videoId"]
            match_title = best_match.get("title", "").strip()
            match_artist = ""
            if best_match.get("artists"):
                match_artist = best_match["artists"][0].get("name", "").strip()
            elif t.get("artist"):
                match_artist = t["artist"].split(";")[0].split(",")[0].strip()

            # Dual-layer dedup: videoId OR normalized (title, artist) already in playlist
            if vid in existing_video_ids or _is_in_existing_keys(match_title, match_artist, existing_title_keys):
                skipped += 1
                details.append({
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "status": "skipped",
                    "category": "duplicate",
                    "matched_title": match_title,
                    "matched_artist": match_artist,
                    "videoId": vid,
                    "reason": "already in playlist",
                })
                continue

            video_ids_to_add.append(vid)
            existing_video_ids.add(vid)
            existing_title_keys.add((match_title.lower(), match_artist.lower()))
            details.append({
                "title": t.get("title", ""),
                "artist": t.get("artist", ""),
                "status": "added",
                "category": "match",
                "matched_title": match_title,
                "matched_artist": match_artist,
                "videoId": vid,
                "score": round(score, 1),
            })
        except Exception as e:
            skipped += 1
            errors.append({"track": query, "reason": str(e)})
            details.append({
                "title": t.get("title", ""),
                "artist": t.get("artist", ""),
                "status": "error",
                "category": "error",
                "reason": str(e),
            })

    # Add new items in batches of 50 to avoid oversized request payloads
    if video_ids_to_add:
        batch_size = 50
        failed_vids_map: dict[str, str] = {}
        for i in range(0, len(video_ids_to_add), batch_size):
            chunk = video_ids_to_add[i:i + batch_size]
            res = yt.add_playlist_items(playlist_id, chunk, duplicates=False)
            actually_added = res if isinstance(res, int) else len(chunk)
            added += actually_added

            if hasattr(res, "failed_ids") and res.failed_ids:
                failed_vids_map.update(res.failed_ids)
            elif actually_added < len(chunk):
                # Fallback for mock/legacy returning raw int: assume trailing items failed
                for unadded_vid in chunk[actually_added:]:
                    failed_vids_map[unadded_vid] = "YouTube Data API write limit reached"

            if actually_added < len(chunk):
                unprocessed = len(video_ids_to_add) - added
                skipped += unprocessed
                for unproc_vid in video_ids_to_add[i + len(chunk):]:
                    failed_vids_map[unproc_vid] = "YouTube Data API write limit reached"
                errors.append({"track": "*", "reason": f"YouTube Data API write limit reached. {added} tracks saved; resuming will skip existing tracks."})
                break

        # Reconcile details with failed video IDs so telemetry tabs accurately reflect true outcomes
        if failed_vids_map:
            for d in details:
                vid = d.get("videoId")
                if d.get("status") == "added" and vid in failed_vids_map:
                    d["status"] = "error"
                    d["category"] = "insert_failed"
                    d["reason"] = failed_vids_map[vid]
                    errors.append({"track": d.get("title", "Track"), "reason": failed_vids_map[vid]})

    reorder_result = None
    if reorder_destination and len(existing_video_ids) > 0:
        try:
            reorder_result = yt.reorder_playlist_alphabetical(playlist_id)
        except Exception as e:
            reorder_result = {"reordered": False, "error": str(e)}

    return {
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "details": details,
        "reorder": reorder_result,
    }


def preview_matches(
    tracks: list[dict],
    ytmusic_playlist_id: str | None = None,
    user_id: str = DEFAULT_USER_ID,
    on_progress=None,
) -> dict:
    """
    Dry-run matching against YouTube Music at zero write-quota cost.
    Searches and scores candidates for each track without modifying any playlist.
    Identifies catalog gaps, confidence misses, and playlist/batch duplicates.
    """
    try:
        yt = get_client(user_id)
    except Exception:
        # Dry-run match preview does not mutate playlists and does not require OAuth.
        # Fallback to an unauthenticated YTMusic client so preview works even before connecting.
        class _PreviewFallbackClient:
            def __init__(self):
                self._yt = YTMusic()
            def search(self, *args, **kwargs):
                return self._yt.search(*args, **kwargs)
        yt = _PreviewFallbackClient()
    matched_count = 0
    skipped_count = 0
    duplicate_count = 0
    details = []

    existing_video_ids: set[str] = set()
    existing_title_keys: set = set()
    if ytmusic_playlist_id:
        try:
            existing_video_ids, existing_title_keys = get_playlist_existing_tracks(ytmusic_playlist_id, user_id)
        except Exception:
            existing_video_ids, existing_title_keys = set(), set()

    for idx, t in enumerate(tracks):
        if on_progress:
            on_progress(idx + 1, len(tracks), t.get("title", ""))
        query = sanitize_search_query(t.get("title", ""), t.get("artist", ""))
        try:
            results = yt.search(query, filter="songs", limit=5)
            if not results:
                fallback_query = sanitize_search_query(t.get("artist", ""), t.get("title", ""))
                if fallback_query != query:
                    results = yt.search(fallback_query, filter="songs", limit=5)

            if not results:
                skipped_count += 1
                details.append({
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "album": t.get("album", ""),
                    "status": "skipped",
                    "category": "no_results",
                    "score": 0.0,
                    "reason": "no search results",
                })
                continue

            best_match, score = matching.find_best_match(t, results)
            if not best_match:
                fallback_query = sanitize_search_query(t.get("artist", ""), t.get("title", ""))
                if fallback_query != query:
                    fallback_results = yt.search(fallback_query, filter="songs", limit=5)
                    if fallback_results:
                        fb_match, fb_score = matching.find_best_match(t, fallback_results)
                        if fb_match and fb_score > score:
                            best_match, score = fb_match, fb_score

            if not best_match:
                skipped_count += 1
                details.append({
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "album": t.get("album", ""),
                    "status": "skipped",
                    "category": "threshold_miss",
                    "score": round(score, 1),
                    "reason": f"no match met confidence threshold (best score: {score:.1f})",
                })
                continue

            vid = best_match.get("videoId")
            match_title = best_match.get("title", "").strip()
            match_artist = ""
            if best_match.get("artists"):
                match_artist = best_match["artists"][0].get("name", "").strip()
            elif t.get("artist"):
                match_artist = t["artist"].split(";")[0].split(",")[0].strip()

            is_dup = (vid in existing_video_ids or _is_in_existing_keys(match_title, match_artist, existing_title_keys))
            if is_dup:
                skipped_count += 1
                duplicate_count += 1
                details.append({
                    "title": t.get("title", ""),
                    "artist": t.get("artist", ""),
                    "album": t.get("album", ""),
                    "status": "skipped",
                    "category": "duplicate",
                    "matched_title": match_title,
                    "matched_artist": match_artist,
                    "videoId": vid,
                    "score": round(score, 1),
                    "reason": "already in destination playlist" if ytmusic_playlist_id else "duplicate match in CSV",
                })
                continue

            existing_video_ids.add(vid)
            existing_title_keys.add((match_title.lower(), match_artist.lower()))
            matched_count += 1
            details.append({
                "title": t.get("title", ""),
                "artist": t.get("artist", ""),
                "album": t.get("album", ""),
                "status": "matched",
                "category": "match",
                "matched_title": match_title,
                "matched_artist": match_artist,
                "videoId": vid,
                "score": round(score, 1),
            })
        except Exception as e:
            skipped_count += 1
            details.append({
                "title": t.get("title", ""),
                "artist": t.get("artist", ""),
                "album": t.get("album", ""),
                "status": "error",
                "category": "error",
                "reason": str(e),
            })

    return {
        "total": len(tracks),
        "matched_count": matched_count,
        "skipped_count": skipped_count,
        "duplicate_count": duplicate_count,
        "details": details,
    }
