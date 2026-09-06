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
import time
import requests
from ytmusicapi.auth.oauth import OAuthCredentials
from ytmusicapi import YTMusic

from . import db
from . import matching

DEFAULT_USER_ID = "me"


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
    code = creds.get_code()
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
    token = creds.token_from_code(device_code)

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
    # If token has a refresh_token, it can be renewed automatically
    if token.get("refresh_token"):
        return True
    # Otherwise check if the current access token is still unexpired (with 60s buffer)
    return token.get("expires_at", 0) > time.time() + 60


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

    def add_playlist_items(self, playlist_id: str, video_ids: list[str], duplicates: bool = False):
        url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        for vid in video_ids:
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
            if resp.status_code not in (200, 201, 409):
                # We do not crash the sync if a single song fails (e.g. region-restricted)
                pass


def get_client(user_id: str = DEFAULT_USER_ID) -> YouTubeSyncClient:
    token = db.get_token(user_id, "ytmusic")
    if not token or "access_token" not in token:
        raise RuntimeError("YouTube Music not connected yet — visit /auth/ytmusic/login first")

    now = time.time()
    expires_at = token.get("expires_at", 0)
    creds = _credentials()

    # Check if token is close to expiry
    if expires_at < now + 60:
        refresh_tok = token.get("refresh_token")
        if refresh_tok:
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
                raise RuntimeError(f"Failed to refresh YouTube Music token: {e}. Please reconnect in the UI.")
        else:
            raise RuntimeError(
                "Your YouTube Music session has expired (access tokens expire after 1 hour). "
                "Please click 'Connect YT Music' to reconnect."
            )

    return YouTubeSyncClient(access_token=token["access_token"])



def create_playlist(title: str, description: str, user_id: str = DEFAULT_USER_ID) -> str:
    yt = get_client(user_id)
    return yt.create_playlist(title, description)


def get_playlist_video_ids(playlist_id: str, user_id: str = DEFAULT_USER_ID) -> set[str]:
    """Retrieves all existing videoIds in a YouTube Music playlist to enable cross-run deduplication."""
    yt = get_client(user_id)
    try:
        playlist = yt.get_playlist(playlist_id, limit=None)
        tracks = playlist.get("tracks", []) or []
        return {t["videoId"] for t in tracks if t and t.get("videoId")}
    except Exception:
        return set()


def search_and_add(playlist_id: str, tracks: list[dict], user_id: str = DEFAULT_USER_ID) -> dict:
    """
    For each track from the imported CSV:
    1. Check existing playlist items to prevent re-adding already synced tracks.
    2. Search YT Music for candidates and score them against duration, album, and version.
    3. Add only new, validated matches to the YouTube Music playlist in batches.
    Returns {added: int, skipped: int, errors: [{track, reason}]}.
    """
    yt = get_client(user_id)
    existing_video_ids = get_playlist_video_ids(playlist_id, user_id)

    added, skipped, errors = 0, 0, []
    video_ids_to_add = []

    for t in tracks:
        query = f"{t['title']} {t['artist']}"
        try:
            results = yt.search(query, filter="songs", limit=5)
            if not results:
                skipped += 1
                errors.append({"track": query, "reason": "no search results"})
                continue

            best_match, score = matching.find_best_match(t, results)
            if not best_match:
                skipped += 1
                errors.append({"track": query, "reason": f"no match met confidence threshold (best score: {score:.1f})"})
                continue

            vid = best_match["videoId"]
            if vid in existing_video_ids:
                # Track is already in the playlist (from a previous run or earlier in CSV)
                skipped += 1
                continue

            video_ids_to_add.append(vid)
            existing_video_ids.add(vid)
        except Exception as e:
            skipped += 1
            errors.append({"track": query, "reason": str(e)})

    # Add new items in batches of 50 to avoid oversized request payloads
    if video_ids_to_add:
        batch_size = 50
        for i in range(0, len(video_ids_to_add), batch_size):
            chunk = video_ids_to_add[i:i + batch_size]
            yt.add_playlist_items(playlist_id, chunk, duplicates=False)
        added = len(video_ids_to_add)

    return {"added": added, "skipped": skipped, "errors": errors}

