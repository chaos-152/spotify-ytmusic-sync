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

    def add_playlist_items(self, playlist_id: str, video_ids: list[str], duplicates: bool = False) -> int:
        url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        added_count = 0
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
            if resp.status_code in (200, 201):
                added_count += 1
            elif resp.status_code == 403 and "quotaExceeded" in resp.text:
                # Stop immediately if daily quota ceiling is reached
                break
        return added_count


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


def _is_in_existing_keys(title: str, artist: str, existing_keys: set) -> bool:
    t = title.lower().strip()
    a = artist.lower().strip()
    if (t, a) in existing_keys:
        return True
    if t in existing_keys and not any(isinstance(k, tuple) for k in existing_keys):
        return True
    for k in existing_keys:
        if isinstance(k, tuple):
            k_title, k_artist = k
            if k_title == t:
                if not k_artist or not a or k_artist in a or a in k_artist:
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
        for i in range(0, len(video_ids_to_add), batch_size):
            chunk = video_ids_to_add[i:i + batch_size]
            res = yt.add_playlist_items(playlist_id, chunk, duplicates=False)
            actually_added = res if isinstance(res, int) else len(chunk)
            added += actually_added
            if actually_added < len(chunk):
                unprocessed = len(video_ids_to_add) - added
                skipped += unprocessed
                errors.append({"track": "*", "reason": f"YouTube Data API write limit reached. {added} tracks saved; resuming will skip existing tracks."})
                break

    return {"added": added, "skipped": skipped, "errors": errors, "details": details}


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
    yt = get_client(user_id)
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
