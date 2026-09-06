from unittest.mock import MagicMock
import pytest
from backend import db, sync, ytmusic_auth


def test_run_sync_first_time_creates_playlist(monkeypatch):
    # Setup link and tracks
    link_id = db.upsert_link("me", "Synthwave Essentials")
    tracks = [
        {"title": "Resonance", "artist": "HOME", "album": "Odyssey", "duration_ms": 212000},
        {"title": "Tech Noir", "artist": "Gunship", "album": "Gunship", "duration_ms": 297000},
    ]
    db.replace_tracks(link_id, tracks)

    song_catalog = {
        "Resonance": {"videoId": "vid_resonance", "title": "Resonance", "artist": "HOME", "duration": "3:32"},
        "Tech Noir": {"videoId": "vid_tech", "title": "Tech Noir", "artist": "Gunship", "duration": "4:57"},
    }

    # Mock YTMusic client
    mock_yt = MagicMock()
    mock_yt.create_playlist.return_value = "yt_synth_playlist_id"
    mock_yt.get_playlist.return_value = {"tracks": []}
    mock_yt.search.side_effect = lambda query, filter, limit: [
        {
            "videoId": info["videoId"],
            "title": info["title"],
            "artists": [{"name": info["artist"]}],
            "duration": info["duration"],
        }
        for title, info in song_catalog.items()
        if title.lower() in query.lower()
    ]

    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    run_id = sync.run_sync(link_id)

    # Verify link has playlist ID saved
    link = db.get_link(link_id)
    assert link["ytmusic_playlist_id"] == "yt_synth_playlist_id"

    # Verify items were added
    mock_yt.add_playlist_items.assert_called_once()
    added_ids = mock_yt.add_playlist_items.call_args[0][1]
    assert len(added_ids) == 2
    assert "vid_resonance" in added_ids
    assert "vid_tech" in added_ids

    # Verify run record in DB
    runs = db.get_runs_for_link(link_id)
    assert len(runs) == 1
    assert runs[0]["id"] == run_id
    assert runs[0]["status"] == "done"
    assert runs[0]["added"] == 2
    assert runs[0]["skipped"] == 0


def test_run_sync_cross_run_deduplication(monkeypatch):
    # Setup link with existing playlist ID
    link_id = db.upsert_link("me", "Synthwave Essentials")
    db.set_ytmusic_playlist_id(link_id, "yt_existing_pl")
    tracks = [
        {"title": "Resonance", "artist": "HOME", "album": "Odyssey", "duration_ms": 212000},
        {"title": "Tech Noir", "artist": "Gunship", "album": "Gunship", "duration_ms": 297000},
        {"title": "Fly For Your Life", "artist": "Gunship", "album": "Gunship", "duration_ms": 279000},
    ]
    db.replace_tracks(link_id, tracks)

    song_catalog = {
        "Resonance": {"videoId": "vid_resonance", "title": "Resonance", "artist": "HOME", "duration": "3:32"},
        "Tech Noir": {"videoId": "vid_tech", "title": "Tech Noir", "artist": "Gunship", "duration": "4:57"},
        "Fly For Your Life": {"videoId": "vid_fly", "title": "Fly For Your Life", "artist": "Gunship", "duration": "4:39"},
    }

    mock_yt = MagicMock()
    # Assume "vid_resonance" is ALREADY in the playlist
    mock_yt.get_playlist.return_value = {
        "tracks": [{"videoId": "vid_resonance", "title": "Resonance"}]
    }

    mock_yt.search.side_effect = lambda query, filter, limit: [
        {
            "videoId": info["videoId"],
            "title": info["title"],
            "artists": [{"name": info["artist"]}],
            "duration": info["duration"],
        }
        for title, info in song_catalog.items()
        if title.lower() in query.lower()
    ]

    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    run_id = sync.run_sync(link_id)

    # Should only add Tech Noir and Fly For Your Life, skipping Resonance
    mock_yt.add_playlist_items.assert_called_once()
    added_ids = mock_yt.add_playlist_items.call_args[0][1]
    assert len(added_ids) == 2

    assert "vid_tech" in added_ids
    assert "vid_fly" in added_ids
    assert "vid_resonance" not in added_ids

    runs = db.get_runs_for_link(link_id)
    assert runs[0]["status"] == "done"
    assert runs[0]["added"] == 2
    assert runs[0]["skipped"] == 1


def test_run_sync_idempotent_all_skipped(monkeypatch):
    link_id = db.upsert_link("me", "Synthwave Essentials")
    db.set_ytmusic_playlist_id(link_id, "yt_existing_pl")
    tracks = [
        {"title": "Resonance", "artist": "HOME", "album": "Odyssey", "duration_ms": 212000},
    ]
    db.replace_tracks(link_id, tracks)

    mock_yt = MagicMock()
    # Track is already present
    mock_yt.get_playlist.return_value = {
        "tracks": [{"videoId": "vid_resonance", "title": "Resonance"}]
    }
    mock_yt.search.return_value = [
        {"videoId": "vid_resonance", "title": "Resonance", "artists": [{"name": "HOME"}], "duration": "3:32"}
    ]

    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    sync.run_sync(link_id)

    # add_playlist_items shouldn't even be called since 0 new items
    mock_yt.add_playlist_items.assert_not_called()

    runs = db.get_runs_for_link(link_id)
    assert runs[0]["status"] == "done"
    assert runs[0]["added"] == 0
    assert runs[0]["skipped"] == 1


def test_run_sync_empty_tracks_raises():
    link_id = db.upsert_link("me", "Empty Playlist")
    with pytest.raises(ValueError, match="No tracks stored for this playlist"):
        sync.run_sync(link_id)

    runs = db.get_runs_for_link(link_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "error"


def test_run_sync_intra_csv_dedup(monkeypatch):
    """If the same track appears multiple times in the CSV, it should only be added once."""
    link_id = db.upsert_link("me", "Repeats Playlist")
    db.set_ytmusic_playlist_id(link_id, "yt_repeats_pl")
    tracks = [
        {"title": "Song A", "artist": "Artist A", "album": "Album A", "duration_ms": 180000},
        {"title": "Song A", "artist": "Artist A", "album": "Album A", "duration_ms": 180000},
    ]
    db.replace_tracks(link_id, tracks)

    mock_yt = MagicMock()
    mock_yt.get_playlist.return_value = {"tracks": []}
    mock_yt.search.return_value = [
        {"videoId": "vid_song_a", "title": "Song A", "artists": [{"name": "Artist A"}], "duration": "3:00"}
    ]
    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    sync.run_sync(link_id)

    mock_yt.add_playlist_items.assert_called_once()
    added_ids = mock_yt.add_playlist_items.call_args[0][1]
    assert added_ids == ["vid_song_a"]

    runs = db.get_runs_for_link(link_id)
    assert runs[0]["added"] == 1
    assert runs[0]["skipped"] == 1


def test_run_sync_batches_over_50_items(monkeypatch):
    """Verifies that large playlists are sent in chunks of 50."""
    link_id = db.upsert_link("me", "Huge Playlist")
    db.set_ytmusic_playlist_id(link_id, "yt_huge_pl")
    tracks = [
        {"title": f"Song {i}", "artist": f"Artist {i}", "duration_ms": 180000}
        for i in range(55)
    ]
    db.replace_tracks(link_id, tracks)

    mock_yt = MagicMock()
    mock_yt.get_playlist.return_value = {"tracks": []}
    mock_yt.search.side_effect = lambda query, filter, limit: [
        {
            "videoId": f"vid_{query}",
            "title": query.split()[0] + " " + query.split()[1],
            "artists": [{"name": query.split()[2] + " " + query.split()[3]}],
            "duration": "3:00",
        }
    ]
    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    sync.run_sync(link_id)

    assert mock_yt.add_playlist_items.call_count == 2
    batch1 = mock_yt.add_playlist_items.call_args_list[0][0][1]
    batch2 = mock_yt.add_playlist_items.call_args_list[1][0][1]
    assert len(batch1) == 50
    assert len(batch2) == 5


def test_run_sync_partial_failures_recorded(monkeypatch):
    link_id = db.upsert_link("me", "Mixed Playlist")
    db.set_ytmusic_playlist_id(link_id, "yt_mixed_pl")
    tracks = [
        {"title": "Working Song", "artist": "Good Artist", "duration_ms": 180000},
        {"title": "Broken Song", "artist": "Bad Artist", "duration_ms": 180000},
        {"title": "Missing Song", "artist": "Ghost Artist", "duration_ms": 180000},
    ]
    db.replace_tracks(link_id, tracks)

    mock_yt = MagicMock()
    mock_yt.get_playlist.return_value = {"tracks": []}

    def mock_search(query, filter, limit):
        if "Working" in query:
            return [{"videoId": "vid_work", "title": "Working Song", "artists": [{"name": "Good Artist"}], "duration": "3:00"}]
        elif "Broken" in query:
            raise RuntimeError("YT API rate limit error")
        return []  # Missing Song returns no search results

    mock_yt.search.side_effect = mock_search
    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": mock_yt)

    sync.run_sync(link_id)

    mock_yt.add_playlist_items.assert_called_once()
    assert mock_yt.add_playlist_items.call_args[0][1] == ["vid_work"]

    runs = db.get_runs_for_link(link_id)
    assert runs[0]["status"] == "done"
    assert runs[0]["added"] == 1
    assert runs[0]["skipped"] == 2
    assert "YT API rate limit error" in runs[0]["errors"]
    assert "no search results" in runs[0]["errors"]

