import sqlite3
from backend import db


def test_token_save_and_get():
    assert db.get_token("user1", "ytmusic") is None

    token_data = {"access_token": "abc", "refresh_token": "def", "expires_at": 12345}
    db.save_token("user1", "ytmusic", token_data)

    retrieved = db.get_token("user1", "ytmusic")
    assert retrieved == token_data

    # Update token
    updated_data = {"access_token": "new_abc", "refresh_token": "new_def"}
    db.save_token("user1", "ytmusic", updated_data)
    assert db.get_token("user1", "ytmusic") == updated_data


def test_links_and_tracks():
    link_id = db.upsert_link("me", "Road Trip Vibes")
    assert link_id > 0

    link = db.get_link(link_id)
    assert link["source_name"] == "Road Trip Vibes"
    assert link["ytmusic_playlist_id"] is None

    db.set_ytmusic_playlist_id(link_id, "yt_pl_123")
    link = db.get_link(link_id)
    assert link["ytmusic_playlist_id"] == "yt_pl_123"

    tracks = [
        {"title": "Track 1", "artist": "Artist 1", "album": "Album 1", "duration_ms": 200000},
        {"title": "Track 2", "artist": "Artist 2", "album": "Album 2", "duration_ms": 250000},
    ]
    db.replace_tracks(link_id, tracks)

    stored_tracks = db.get_tracks(link_id)
    assert len(stored_tracks) == 2
    assert stored_tracks[0]["title"] == "Track 1"
    assert stored_tracks[0]["duration_ms"] == 200000
    assert stored_tracks[1]["title"] == "Track 2"
    assert stored_tracks[1]["duration_ms"] == 250000

    # Test replace wipes old tracks
    new_tracks = [{"title": "Track 3", "artist": "Artist 3", "album": "", "duration_ms": None}]
    db.replace_tracks(link_id, new_tracks)
    stored_tracks = db.get_tracks(link_id)
    assert len(stored_tracks) == 1
    assert stored_tracks[0]["title"] == "Track 3"
    assert stored_tracks[0]["duration_ms"] is None

    # Verify track_count in get_links
    links = db.get_links("me")
    assert len(links) == 1
    assert links[0]["track_count"] == 1


def test_sync_runs():
    link_id = db.upsert_link("me", "Chill Playlist")
    run_id = db.start_run(link_id)
    assert run_id > 0

    runs = db.get_runs_for_link(link_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "running"

    errors = [{"track": "Unknown Song", "reason": "no search results"}]
    db.finish_run(run_id, "done", added=5, skipped=1, errors=errors)

    runs = db.get_runs_for_link(link_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "done"
    assert runs[0]["added"] == 5
    assert runs[0]["skipped"] == 1
    assert "Unknown Song" in runs[0]["errors"]


def test_schema_migration_adds_duration_ms(tmp_path, monkeypatch):
    """Verify that an older DB without duration_ms column is safely migrated."""
    old_db = tmp_path / "legacy.db"
    monkeypatch.setattr(db, "DB_PATH", old_db)

    # Manually create legacy schema without duration_ms
    conn = sqlite3.connect(old_db)
    conn.execute(
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            album TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO tracks (link_id, position, title, artist, album) VALUES (1, 0, 'Legacy Track', 'Legacy Artist', 'Legacy Album')"
    )
    conn.commit()
    conn.close()

    # Call init_db(), which should run the migration
    db.init_db()

    conn = sqlite3.connect(old_db)
    conn.row_factory = sqlite3.Row
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(tracks)").fetchall()]
    assert "duration_ms" in cols

    row = conn.execute("SELECT * FROM tracks WHERE id=1").fetchone()
    assert row["title"] == "Legacy Track"
    assert row["duration_ms"] is None
    conn.close()
