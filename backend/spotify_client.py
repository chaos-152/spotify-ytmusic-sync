"""
Spotify Web API Client using the Client Credentials Flow.
Handles token retrieval, automatic in-memory refresh, and track searching.
Does NOT require user login, redirect URIs, or OAuth scopes.
"""
import os
import time
import base64
import urllib.request
import urllib.parse
import json
from typing import Optional


class SpotifyClientCredentials:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        self.client_secret = client_secret or os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
        self._access_token: Optional[str] = access_token
        self._expires_at: float = (time.time() + 3600) if access_token else 0.0

    @property
    def is_configured(self) -> bool:
        if self._access_token:
            return True
        if self.client_id and self.client_secret:
            return True
        try:
            from backend import db
            user_tok = db.get_token("me", "spotify_user")
            if user_tok and user_tok.get("access_token"):
                return True
        except Exception:
            pass
        return False

    def get_access_token(self) -> str:
        """Returns a valid access token, refreshing if expired."""
        now = time.time()
        if self._access_token and now < (self._expires_at - 60):
            return self._access_token

        # 1. Try to use user OAuth access token if available
        try:
            from backend import db
            user_tok = db.get_token("me", "spotify_user")
            if user_tok and user_tok.get("access_token"):
                if now < (user_tok.get("expires_at", 0) - 60):
                    self._access_token = user_tok["access_token"]
                    self._expires_at = user_tok.get("expires_at", now + 3600)
                    return self._access_token
                refresh_token = user_tok.get("refresh_token")
                if refresh_token and self.client_id and self.client_secret:
                    refreshed = refresh_user_token(refresh_token, self.client_id, self.client_secret)
                    user_tok.update(refreshed)
                    db.save_token("me", "spotify_user", user_tok)
                    self._access_token = refreshed["access_token"]
                    self._expires_at = refreshed["expires_at"]
                    return self._access_token
        except Exception:
            pass

        # 2. Try Client Credentials Flow
        if not (self.client_id and self.client_secret):
            raise ValueError(
                "Spotify credentials not configured. Please add SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET to your backend/.env file, or connect your Spotify account."
            )

        auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=data,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode())
                self._access_token = payload["access_token"]
                self._expires_at = now + payload.get("expires_in", 3600)
                return self._access_token
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            raise RuntimeError(f"Spotify token request failed ({e.code}): {err_body}")

    def search_tracks(self, query: str, limit: int = 5) -> list[dict]:
        """
        Searches Spotify catalog for track items.
        Returns normalized list of candidate dictionaries.
        """
        token = self.get_access_token()
        params = urllib.parse.urlencode({
            "q": query,
            "type": "track",
            "limit": str(limit),
        })
        url = f"https://api.spotify.com/v1/search?{params}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                items = data.get("tracks", {}).get("items", [])
                candidates = []
                for item in items:
                    artists = [a.get("name", "") for a in item.get("artists", [])]
                    album = item.get("album", {}).get("name", "")
                    candidates.append({
                        "id": item.get("id"),
                        "uri": item.get("uri"),
                        "title": item.get("name", ""),
                        "artist": "; ".join(artists),
                        "artists": [{"name": a} for a in artists],
                        "album": album,
                        "duration_ms": item.get("duration_ms"),
                        "duration_seconds": round(item.get("duration_ms", 0) / 1000) if item.get("duration_ms") else None,
                        "isrc": item.get("external_ids", {}).get("isrc"),
                        "popularity": item.get("popularity", 0),
                    })
                return candidates
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            raise RuntimeError(f"Spotify search failed ({e.code}): {err_body}")


# ==============================================================================
# Spotify User OAuth (Authorization Code Flow) & Playlist Write Helpers
# ==============================================================================

SPOTIFY_SCOPES = "playlist-modify-public playlist-modify-private user-read-private"


def get_spotify_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Generates the Spotify authorization URL for User OAuth consent."""
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SPOTIFY_SCOPES,
        "state": state,
        "show_dialog": "true",
    })
    return f"https://accounts.spotify.com/authorize?{params}"


def exchange_code_for_user_token(code: str, redirect_uri: str, client_id: str, client_secret: str) -> dict:
    """Exchanges an authorization code for Spotify user access & refresh tokens."""
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
            payload["expires_at"] = time.time() + payload.get("expires_in", 3600)
            return payload
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"Spotify token exchange failed ({e.code}): {err_body}")


def refresh_user_token(refresh_token: str, client_id: str, client_secret: str) -> dict:
    """Refreshes an expired Spotify user token using the refresh_token."""
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
            payload["expires_at"] = time.time() + payload.get("expires_in", 3600)
            if "refresh_token" not in payload:
                payload["refresh_token"] = refresh_token
            return payload
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"Spotify token refresh failed ({e.code}): {err_body}")


def get_current_user_profile(access_token: str) -> dict:
    """Fetches the authenticated user's Spotify profile (user ID, display name)."""
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"Failed to fetch Spotify user profile ({e.code}): {err_body}")


def create_user_playlist(access_token: str, user_id: str = "", name: str = "", description: str = "", public: bool = False) -> dict:
    """Creates a new playlist on the authenticated user's Spotify account."""
    payload = json.dumps({
        "name": name,
        "description": description or "Synced from YouTube Music via Spotify ⇄ YT Music Sync",
        "public": public,
    }).encode()
    # Modern Spotify endpoint /v1/me/playlists avoids user_id mismatch issues
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/playlists",
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        if e.code == 403:
            raise RuntimeError(
                "Spotify returned 403 Forbidden. If your Spotify app is in Development Mode, "
                "the Spotify account you logged into must be added to 'User Management' in your "
                "Spotify Developer Dashboard (or be the developer app owner's account)."
            )
        raise RuntimeError(f"Failed to create Spotify playlist ({e.code}): {err_body}")


def add_tracks_to_playlist(access_token: str, playlist_id: str, uris: list[str]) -> int:
    """
    Adds tracks to a Spotify playlist in batches of up to 100 items.
    Returns total count of tracks successfully added.
    """
    if not uris:
        return 0

    added_count = 0
    # Spotify allows a maximum of 100 tracks per POST request
    batch_size = 100
    for i in range(0, len(uris), batch_size):
        batch = uris[i:i + batch_size]
        payload = json.dumps({"uris": batch}).encode()
        req = urllib.request.Request(
            f"https://api.spotify.com/v1/playlists/{urllib.parse.quote(playlist_id)}/tracks",
            data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
                added_count += len(batch)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                try:
                    req_items = urllib.request.Request(
                        f"https://api.spotify.com/v1/playlists/{urllib.parse.quote(playlist_id)}/items",
                        data=payload,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req_items, timeout=10) as resp2:
                        resp2.read()
                        added_count += len(batch)
                        continue
                except Exception:
                    pass
            err_body = e.read().decode()
            raise RuntimeError(f"Failed to add tracks to Spotify playlist ({e.code}): {err_body}")

    return added_count
