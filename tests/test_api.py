import io
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
