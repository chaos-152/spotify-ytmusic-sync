import io
import os
from unittest.mock import MagicMock
from backend import ytmusic_auth, main


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




