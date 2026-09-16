import io
import os
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from backend import ytmusic_auth, main, db


def test_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    assert "ytmusic_connected" in res.json()


def test_ytmusic_auth_flow(client, monkeypatch):
    monkeypatch.setattr(
        ytmusic_auth,
        "start_device_auth",
        lambda: {
            "device_code": "dev123",
            "user_code": "USER-456",
            "verification_url": "https://google.com/device",
            "interval": 5,
        },
    )
    start_res = client.post("/api/ytmusic/start-auth")
    assert start_res.status_code == 200
    data = start_res.json()
    assert data["user_code"] == "USER-456"
    assert data["verification_url"] == "https://google.com/device"

    # Complete auth when approved
    monkeypatch.setattr(
        ytmusic_auth,
        "poll_for_token",
        lambda device_code: {"access_token": "token_abc"},
    )
    complete_res = client.post("/api/ytmusic/complete-auth")
    assert complete_res.status_code == 200
    assert complete_res.json()["connected"] is True


def test_ytmusic_complete_auth_without_start(client):
    # Reset pending code
    main._pending_ytmusic_device_code = None
    res = client.post("/api/ytmusic/complete-auth")
    assert res.status_code == 400


def test_import_csv_success(client, exportify_csv_bytes):
    files = {"file": ("playlist.csv", io.BytesIO(exportify_csv_bytes), "text/csv")}
    data = {"name": "Top Hits"}

    res = client.post("/api/import-csv", data=data, files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["source_name"] == "Top Hits"
    assert body["track_count"] == 3

    # Check links listing
    links_res = client.get("/api/links")
    assert links_res.status_code == 200
    links = links_res.json()
    assert len(links) == 1
    assert links[0]["source_name"] == "Top Hits"
    assert links[0]["track_count"] == 3


def test_import_csv_malformed_returns_400(client):
    files = {"file": ("playlist.csv", io.BytesIO(b"Bad,Headers\n1,2\n"), "text/csv")}
    data = {"name": "Broken Playlist"}

    res = client.post("/api/import-csv", data=data, files=files)
    assert res.status_code == 400
    assert "Couldn't find track name / artist columns" in res.json()["detail"]


def test_sync_trigger_not_found(client):
    res = client.post("/api/links/99999/sync")
    assert res.status_code == 404


def test_sync_trigger_and_runs(client, exportify_csv_bytes, monkeypatch):
    # Import a playlist
    files = {"file": ("playlist.csv", io.BytesIO(exportify_csv_bytes), "text/csv")}
    import_res = client.post("/api/import-csv", data={"name": "Rock Classics"}, files=files)
    link_id = import_res.json()["id"]

    # Mock YTMusic
    mock_yt = MagicMock()
    mock_yt.create_playlist.return_value = "yt_rock_pl"
    mock_yt.get_playlist.return_value = {"tracks": []}
    mock_yt.search.return_value = [
        {"videoId": "rock_vid_1", "title": "Get Lucky", "artists": [{"name": "Daft Punk"}], "duration": "6:09"}
    ]
    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    # Trigger sync
    sync_res = client.post(f"/api/links/{link_id}/sync")
    assert sync_res.status_code == 200
    assert sync_res.json()["started"] is True

    # Check runs endpoint
    runs_res = client.get(f"/api/links/{link_id}/runs")
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 1


def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Spotify → YT Music Sync" in res.text


def test_get_link_tracks_success(client, exportify_csv_bytes):
    files = {"file": ("playlist.csv", io.BytesIO(exportify_csv_bytes), "text/csv")}
    import_res = client.post("/api/import-csv", data={"name": "Track Preview Test"}, files=files)
    link_id = import_res.json()["id"]

    res = client.get(f"/api/links/{link_id}/tracks")
    assert res.status_code == 200
    tracks = res.json()
    assert len(tracks) == 3
    assert tracks[0]["title"] == "Get Lucky"
    assert tracks[0]["artist"] == "Daft Punk"


def test_get_link_tracks_not_found(client):
    res = client.get("/api/links/99999/tracks")
    assert res.status_code == 404


def test_preview_link_success(client, exportify_csv_bytes, monkeypatch):
    files = {"file": ("playlist.csv", io.BytesIO(exportify_csv_bytes), "text/csv")}
    import_res = client.post("/api/import-csv", data={"name": "Preview Test"}, files=files)
    link_id = import_res.json()["id"]

    mock_yt = MagicMock()
    mock_yt.search.return_value = [
        {"videoId": "vid_preview_1", "title": "Get Lucky", "artists": [{"name": "Daft Punk"}], "duration": "6:09"}
    ]
    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    res = client.post(f"/api/links/{link_id}/preview")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert "details" in data
    assert len(data["details"]) == 3
    assert data["details"][0]["status"] == "matched"
    assert data["details"][0]["matched_title"] == "Get Lucky"


def test_get_link_tracks_duplicate_detection(client):
    csv_content = (
        b"Track Name,Artist Name(s),Album Name,Duration (ms)\n"
        b"Song A,Artist A,Album A,180000\n"
        b"Song B,Artist B,Album B,200000\n"
        b"Song A,Artist A,Album A,180000\n"
    )
    files = {"file": ("dup_playlist.csv", io.BytesIO(csv_content), "text/csv")}
    import_res = client.post("/api/import-csv", data={"name": "Dup Track Test"}, files=files)
    link_id = import_res.json()["id"]

    res = client.get(f"/api/links/{link_id}/tracks")
    assert res.status_code == 200
    tracks = res.json()
    assert len(tracks) == 3
    assert tracks[0]["is_duplicate"] is False
    assert tracks[1]["is_duplicate"] is False
    assert tracks[2]["is_duplicate"] is True
    assert tracks[2]["first_seen_index"] == 1


def test_preview_link_duplicate_detection(client, monkeypatch):
    csv_content = (
        b"Track Name,Artist Name(s),Album Name,Duration (ms)\n"
        b"Song A,Artist A,Album A,180000\n"
        b"Song A,Artist A,Album A,180000\n"
    )
    files = {"file": ("dup_preview.csv", io.BytesIO(csv_content), "text/csv")}
    import_res = client.post("/api/import-csv", data={"name": "Dup Preview Test"}, files=files)
    link_id = import_res.json()["id"]

    mock_yt = MagicMock()
    mock_yt.search.return_value = [
        {"videoId": "vid_dup_1", "title": "Song A", "artists": [{"name": "Artist A"}], "duration": "3:00"}
    ]
    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    res = client.post(f"/api/links/{link_id}/preview")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert data["matched_count"] == 1
    assert data["duplicate_count"] == 1
    assert data["details"][0]["status"] == "matched"
    assert data["details"][1]["status"] == "skipped"
    assert data["details"][1]["category"] == "duplicate"


def test_setup_credentials_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ENV_FILE", tmp_path / ".env")
    res = client.post(
        "/api/setup/credentials",
        json={"client_id": "test_client_id_123", "client_secret": "test_client_secret_456"},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert os.getenv("YTMUSIC_CLIENT_ID") == "test_client_id_123"
    assert os.getenv("YTMUSIC_CLIENT_SECRET") == "test_client_secret_456"

    # Test blank payload rejection
    res_err = client.post("/api/setup/credentials", json={"client_id": "", "client_secret": ""})
    assert res_err.status_code == 400


def test_setup_spotify_credentials_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ENV_FILE", tmp_path / ".env")
    res = client.post(
        "/api/setup/spotify-credentials",
        json={"client_id": "sp_client_123", "client_secret": "sp_secret_456"},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert os.getenv("SPOTIFY_CLIENT_ID") == "sp_client_123"
    assert os.getenv("SPOTIFY_CLIENT_SECRET") == "sp_secret_456"

    # Status reflects spotify_configured
    status_res = client.get("/api/status")
    assert status_res.status_code == 200
    assert status_res.json()["spotify_configured"] is True

    # Test blank payload rejection
    res_err = client.post("/api/setup/spotify-credentials", json={"client_id": "", "client_secret": ""})
    assert res_err.status_code == 400


def test_setup_credentials_localhost_guard_rejects_remote(client, monkeypatch):
    """Verify that remote network callers are rejected with 403 Forbidden on both setup endpoints."""
    from fastapi import Request, HTTPException
    mock_remote_req = MagicMock(spec=Request)
    mock_remote_req.client = MagicMock(host="192.168.1.100")
    with pytest.raises(HTTPException) as exc1:
        main.assert_localhost_request(mock_remote_req)
    assert exc1.value.status_code == 403
    assert "localhost" in exc1.value.detail.lower()

    for allowed in ("127.0.0.1", "::1", "localhost", "testclient"):
        mock_local = MagicMock(spec=Request)
        mock_local.client = MagicMock(host=allowed)
        main.assert_localhost_request(mock_local)

    # Test HTTP endpoint rejection when guard triggers
    def mock_guard_fail(request):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Credential setup endpoints can only be accessed from localhost.",
        )

    monkeypatch.setattr(main, "assert_localhost_request", mock_guard_fail)
    res1 = client.post(
        "/api/setup/credentials",
        json={"client_id": "evil_client", "client_secret": "evil_secret"},
    )
    assert res1.status_code == 403
    assert "localhost" in res1.json()["detail"].lower()

    res2 = client.post(
        "/api/setup/spotify-credentials",
        json={"client_id": "evil_client", "client_secret": "evil_secret"},
    )
    assert res2.status_code == 403
    assert "localhost" in res2.json()["detail"].lower()


def test_setup_credentials_non_clobbering(client, tmp_path, monkeypatch):
    """Verify that setting Spotify credentials preserves Google credentials, and vice versa."""
    fake_env = tmp_path / ".env"
    monkeypatch.setattr(main, "ENV_FILE", fake_env)

    client.post(
        "/api/setup/spotify-credentials",
        json={"client_id": "spotify_preserve_id", "client_secret": "spotify_preserve_secret"},
    )
    client.post(
        "/api/setup/credentials",
        json={"client_id": "google_preserve_id", "client_secret": "google_preserve_secret"},
    )

    content = fake_env.read_text(encoding="utf-8")
    assert "SPOTIFY_CLIENT_ID=spotify_preserve_id" in content
    assert "SPOTIFY_CLIENT_SECRET=spotify_preserve_secret" in content
    assert "YTMUSIC_CLIENT_ID=google_preserve_id" in content
    assert "YTMUSIC_CLIENT_SECRET=google_preserve_secret" in content


def test_reverse_sync_endpoints(client, monkeypatch):
    mock_result = {
        "playlist_title": "Synthwave Chill",
        "total_tracks": 2,
        "matched_count": 2,
        "gap_count": 0,
        "match_precision": 100.0,
        "details": [
            {
                "yt_title": "Resonance",
                "yt_artist": "HOME",
                "spotify_uri": "spotify:track:123",
                "matched_title": "Resonance",
                "matched_artist": "HOME",
                "status": "matched",
                "confidence": 1.0,
            }
        ],
        "csv_content": "Spotify URI,Track Name,Artist Name(s),Album Name,Duration (ms)\r\nspotify:track:123,Resonance,HOME,Odyssey,212000\r\n",
    }
    monkeypatch.setattr(main.yt_to_spotify, "resolve_yt_playlist_to_spotify", lambda ref: mock_result)

    # Empty validation
    err_res = client.post("/api/reverse-sync/preview", json={"playlist": ""})
    assert err_res.status_code == 400

    # Preview success
    preview_res = client.post("/api/reverse-sync/preview", json={"playlist": "PL12345"})
    assert preview_res.status_code == 200
    pdata = preview_res.json()
    assert pdata["playlist_title"] == "Synthwave Chill"
    assert pdata["matched_count"] == 2

    # Export CSV success
    export_res = client.post("/api/reverse-sync/export-csv", json={"playlist": "PL12345"})
    assert export_res.status_code == 200
    assert export_res.headers["content-type"].startswith("text/csv")
    assert "Synthwave Chill_spotify_uris.csv" in export_res.headers["content-disposition"]
    assert "spotify:track:123" in export_res.text


def test_spotify_user_oauth_and_direct_sync(client, monkeypatch, test_db):
    """Verify Spotify User OAuth flow, callback token persistence, and direct playlist sync."""
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_sp_client")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_sp_secret")

    # 1. Login endpoint generates redirect
    login_res = client.get("/api/spotify/login", follow_redirects=False)
    assert login_res.status_code == 307
    assert "accounts.spotify.com/authorize" in login_res.headers["location"]

    # 2. Mock token exchange and user profile for callback
    monkeypatch.setattr(
        main.spotify_client,
        "exchange_code_for_user_token",
        lambda code, redirect_uri, c_id, c_sec: {
            "access_token": "mock_user_tok",
            "refresh_token": "mock_user_ref",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
        },
    )
    monkeypatch.setattr(
        main.spotify_client,
        "get_current_user_profile",
        lambda token: {"id": "spotify_user_42", "display_name": "Sai"},
    )

    cb_res = client.get("/api/spotify/callback?code=mock_code&state=abc", follow_redirects=False)
    assert cb_res.status_code == 307
    assert "spotify_connected=1" in cb_res.headers["location"]

    # 3. Status reflects user connected
    status_res = client.get("/api/status")
    assert status_res.status_code == 200
    sdata = status_res.json()
    assert sdata["spotify_user_connected"] is True
    assert sdata["spotify_user_name"] == "Sai"

    # 4. Direct sync endpoint
    mock_resolve = {
        "playlist_title": "Lo-Fi Beats",
        "total": 2,
        "matched_count": 2,
        "gap_count": 0,
        "precision_pct": 100.0,
        "details": [
            {"spotify_uri": "spotify:track:aaa"},
            {"spotify_uri": "spotify:track:bbb"},
        ],
    }
    monkeypatch.setattr(main.yt_to_spotify, "resolve_yt_playlist_to_spotify", lambda ref: mock_resolve)
    monkeypatch.setattr(
        main.spotify_client,
        "create_user_playlist",
        lambda access_token, user_id, name, description, public: {
            "id": "pl_new_123",
            "name": name,
            "external_urls": {"spotify": "https://open.spotify.com/playlist/pl_new_123"},
        },
    )
    monkeypatch.setattr(main.spotify_client, "add_tracks_to_playlist", lambda access_token, playlist_id, uris: len(uris))

    sync_res = client.post("/api/reverse-sync/direct-sync", json={"playlist": "PLtest123"})
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert sync_data["success"] is True
    assert sync_data["playlist_id"] == "pl_new_123"
    assert sync_data["added_count"] == 2
    assert "open.spotify.com/playlist/pl_new_123" in sync_data["playlist_url"]

    # 5. Logout endpoint
    logout_res = client.post("/api/spotify/logout")
    assert logout_res.status_code == 200
    status_after = client.get("/api/status").json()
    assert status_after["spotify_user_connected"] is False


def test_ytmusic_credential_swap_and_token_invalidation(client, tmp_path, test_db, monkeypatch):
    """Verify overwriting Google/YT credentials updates env, invalidates cached token, and preserves Spotify."""
    fake_env = tmp_path / ".env"
    monkeypatch.setattr(main, "ENV_FILE", fake_env)

    # Initial credentials & token
    client.post("/api/setup/spotify-credentials", json={"client_id": "sp_orig_id", "client_secret": "sp_orig_sec"})
    client.post("/api/setup/credentials", json={"client_id": "yt_orig_id", "client_secret": "yt_orig_sec"})
    db.save_token("me", "ytmusic", {"access_token": "stale_yt_token", "refresh_token": "stale_ref"})
    assert db.get_token("me", "ytmusic") is not None

    # Overwrite YT credentials
    res = client.post("/api/setup/credentials", json={"client_id": "yt_new_id", "client_secret": "yt_new_sec"})
    assert res.status_code == 200

    content = fake_env.read_text(encoding="utf-8")
    assert "YTMUSIC_CLIENT_ID=yt_new_id" in content
    assert "YTMUSIC_CLIENT_SECRET=yt_new_sec" in content
    assert "SPOTIFY_CLIENT_ID=sp_orig_id" in content
    assert "SPOTIFY_CLIENT_SECRET=sp_orig_sec" in content

    # Verify cached token was purged
    assert db.get_token("me", "ytmusic") is None


def test_ytmusic_credential_disconnect(client, tmp_path, test_db, monkeypatch):
    """Verify disconnecting YT credentials removes them from env, purges token, and leaves Spotify intact."""
    fake_env = tmp_path / ".env"
    monkeypatch.setattr(main, "ENV_FILE", fake_env)

    client.post("/api/setup/spotify-credentials", json={"client_id": "sp_keep_id", "client_secret": "sp_keep_sec"})
    client.post("/api/setup/credentials", json={"client_id": "yt_del_id", "client_secret": "yt_del_sec"})
    db.save_token("me", "ytmusic", {"access_token": "yt_token_to_purge"})

    res = client.post("/api/setup/credentials/disconnect")
    assert res.status_code == 200

    content = fake_env.read_text(encoding="utf-8")
    assert "YTMUSIC_CLIENT_ID" not in content
    assert "YTMUSIC_CLIENT_SECRET" not in content
    assert "SPOTIFY_CLIENT_ID=sp_keep_id" in content
    assert "SPOTIFY_CLIENT_SECRET=sp_keep_sec" in content

    assert db.get_token("me", "ytmusic") is None
    status = client.get("/api/status").json()
    assert status["ytmusic_configured"] is False
    assert status["ytmusic_connected"] is False


def test_spotify_credential_swap_and_token_invalidation(client, tmp_path, test_db, monkeypatch):
    """Verify overwriting Spotify credentials updates env, invalidates cached user token, and preserves YT."""
    fake_env = tmp_path / ".env"
    monkeypatch.setattr(main, "ENV_FILE", fake_env)

    client.post("/api/setup/credentials", json={"client_id": "yt_keep_id", "client_secret": "yt_keep_sec"})
    client.post("/api/setup/spotify-credentials", json={"client_id": "sp_orig_id", "client_secret": "sp_orig_sec"})
    db.save_token("me", "spotify_user", {"access_token": "stale_user_token"})
    assert db.get_token("me", "spotify_user") is not None

    res = client.post("/api/setup/spotify-credentials", json={"client_id": "sp_new_id", "client_secret": "sp_new_sec"})
    assert res.status_code == 200

    content = fake_env.read_text(encoding="utf-8")
    assert "SPOTIFY_CLIENT_ID=sp_new_id" in content
    assert "SPOTIFY_CLIENT_SECRET=sp_new_sec" in content
    assert "YTMUSIC_CLIENT_ID=yt_keep_id" in content

    # Cached user session purged
    assert db.get_token("me", "spotify_user") is None


def test_spotify_credential_disconnect(client, tmp_path, test_db, monkeypatch):
    """Verify disconnecting Spotify credentials removes them from env, purges token, and leaves YT intact."""
    fake_env = tmp_path / ".env"
    monkeypatch.setattr(main, "ENV_FILE", fake_env)

    client.post("/api/setup/credentials", json={"client_id": "yt_keep_id", "client_secret": "yt_keep_sec"})
    client.post("/api/setup/spotify-credentials", json={"client_id": "sp_del_id", "client_secret": "sp_del_sec"})
    db.save_token("me", "spotify_user", {"access_token": "sp_token_to_purge"})

    res = client.post("/api/setup/spotify-credentials/disconnect")
    assert res.status_code == 200

    content = fake_env.read_text(encoding="utf-8")
    assert "SPOTIFY_CLIENT_ID" not in content
    assert "SPOTIFY_CLIENT_SECRET" not in content
    assert "YTMUSIC_CLIENT_ID=yt_keep_id" in content

    assert db.get_token("me", "spotify_user") is None
    status = client.get("/api/status").json()
    assert status["spotify_configured"] is False
    assert status["spotify_user_connected"] is False


def test_disconnect_endpoints_localhost_guard(client, monkeypatch):
    """Verify that remote network callers cannot invoke disconnect endpoints."""
    from fastapi import HTTPException
    def mock_guard_fail(request):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Credential setup endpoints can only be accessed from localhost.",
        )

    monkeypatch.setattr(main, "assert_localhost_request", mock_guard_fail)
    res1 = client.post("/api/setup/credentials/disconnect")
    assert res1.status_code == 403
    assert "localhost" in res1.json()["detail"].lower()

    res2 = client.post("/api/setup/spotify-credentials/disconnect")
    assert res2.status_code == 403
    assert "localhost" in res2.json()["detail"].lower()


def test_ytmusic_oauth_constants_and_contract_compatibility():
    """Ensure ytmusicapi constants match our expectations and catch silent drift on upgrades."""
    from ytmusicapi.constants import OAUTH_TOKEN_URL, OAUTH_SCOPE, OAUTH_USER_AGENT
    assert ytmusic_auth.OAUTH_TOKEN_URL == "https://oauth2.googleapis.com/token"
    assert ytmusic_auth.OAUTH_TOKEN_URL == OAUTH_TOKEN_URL
    assert "youtube" in OAUTH_SCOPE.lower()
    assert ytmusic_auth.OAUTH_SCOPE == OAUTH_SCOPE
    assert bool(OAUTH_USER_AGENT)
    assert ytmusic_auth.GOOGLE_OAUTH_DEVICE_CODE_URL == "https://oauth2.googleapis.com/device/code"


def test_setup_credentials_validation_rejects_invalid_format(client, tmp_path, monkeypatch):
    """Verify that credentials endpoints reject invalid format, whitespace, and bad domains."""
    monkeypatch.setattr(main, "ENV_FILE", tmp_path / ".env")

    # 1. Google Client ID with spaces
    res = client.post("/api/setup/credentials", json={"client_id": "invalid id with spaces", "client_secret": "secret"})
    assert res.status_code == 400
    assert "whitespace" in res.json()["detail"].lower()

    # 2. Google Client Secret with spaces
    res = client.post("/api/setup/credentials", json={"client_id": "123.apps.googleusercontent.com", "client_secret": "secret with space"})
    assert res.status_code == 400
    assert "whitespace" in res.json()["detail"].lower()

    # 3. Google Client ID without .apps.googleusercontent.com domain
    res = client.post("/api/setup/credentials", json={"client_id": "unauthorized-client-id", "client_secret": "valid_secret"})
    assert res.status_code == 400
    assert "google client id format" in res.json()["detail"].lower()

    # 4. Spotify Client ID with spaces
    res = client.post("/api/setup/spotify-credentials", json={"client_id": "sp id with spaces", "client_secret": "valid_secret"})
    assert res.status_code == 400
    assert "whitespace" in res.json()["detail"].lower()

    # 5. Spotify Client ID with invalid length / not hex
    res = client.post("/api/setup/spotify-credentials", json={"client_id": "bad_short_id", "client_secret": "valid_secret"})
    assert res.status_code == 400
    assert "spotify client id format" in res.json()["detail"].lower()

    # 6. Valid Google Client ID with official domain succeeds
    res = client.post("/api/setup/credentials", json={"client_id": "123456789-abcdef.apps.googleusercontent.com", "client_secret": "GOCSPX-validsecret"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    # 7. Valid Spotify Client ID with 32 alphanumeric chars succeeds
    res = client.post("/api/setup/spotify-credentials", json={"client_id": "0123456789abcdef0123456789abcdef", "client_secret": "fedcba9876543210fedcba9876543210"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_status_endpoint_onboarding_states(client, monkeypatch):
    """Verify that /api/status correctly exposes State 1, State 2, and State 3 for onboarding."""
    # State 1: Fresh clone - neither configured
    monkeypatch.delenv("YTMUSIC_CLIENT_ID", raising=False)
    monkeypatch.delenv("YTMUSIC_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)

    s1 = client.get("/api/status").json()
    assert s1["ytmusic_configured"] is False
    assert s1["spotify_configured"] is False

    # State 2: Resume Point - Google configured, Spotify not yet configured
    monkeypatch.setenv("YTMUSIC_CLIENT_ID", "123.apps.googleusercontent.com")
    monkeypatch.setenv("YTMUSIC_CLIENT_SECRET", "secret")
    s2 = client.get("/api/status").json()
    assert s2["ytmusic_configured"] is True
    assert s2["spotify_configured"] is False

    # State 3: Both configured - ready to sync
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "fedcba9876543210fedcba9876543210")
    s3 = client.get("/api/status").json()
    assert s3["ytmusic_configured"] is True
    assert s3["spotify_configured"] is True


def test_setup_credentials_localhost_guard_remote_rejection(client, monkeypatch):
    """Exhaustive security audit of assert_localhost_request against remote IPs and spoofed headers."""
    from fastapi import Request, HTTPException

    remote_ips = ["192.168.1.50", "10.0.0.1", "8.8.8.8", "172.16.0.5", "203.0.113.195"]
    for ip in remote_ips:
        mock_req = MagicMock(spec=Request)
        mock_req.client = MagicMock(host=ip)
        with pytest.raises(HTTPException) as exc:
            main.assert_localhost_request(mock_req)
        assert exc.value.status_code == 403

    # Verify that spoofed proxy headers cannot bypass assert_localhost_request
    spoof_headers = [
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Real-IP": "127.0.0.1"},
        {"Forwarded": "for=127.0.0.1;proto=http;by=127.0.0.1"},
        {"Host": "localhost"},
    ]
    for headers in spoof_headers:
        mock_req = MagicMock(spec=Request)
        mock_req.client = MagicMock(host="192.168.1.50")
        mock_req.headers = headers
        with pytest.raises(HTTPException) as exc:
            main.assert_localhost_request(mock_req)
        assert exc.value.status_code == 403

    # Verify missing client (None) is rejected
    mock_no_client = MagicMock(spec=Request)
    mock_no_client.client = None
    with pytest.raises(HTTPException) as exc:
        main.assert_localhost_request(mock_no_client)
    assert exc.value.status_code == 403


def test_check_network_endpoint(client, monkeypatch):
    """Verify /api/setup/check-network returns reachability status."""
    monkeypatch.setattr(main, "check_google_oauth_reachability", lambda timeout=3.0: True)
    res = client.get("/api/setup/check-network")
    assert res.status_code == 200
    assert res.json() == {"reachable": True}

    monkeypatch.setattr(main, "check_google_oauth_reachability", lambda timeout=3.0: False)
    res = client.get("/api/setup/check-network")
    assert res.status_code == 200
    assert res.json() == {"reachable": False}

    # Verify remote callers are rejected with 403 Forbidden
    from fastapi import HTTPException
    monkeypatch.setattr(
        main,
        "assert_localhost_request",
        lambda req: (_ for _ in ()).throw(HTTPException(403, "Forbidden: Credential setup endpoints can only be accessed from localhost.")),
    )
    res_remote = client.get("/api/setup/check-network")
    assert res_remote.status_code == 403
    assert "localhost" in res_remote.json()["detail"].lower()





