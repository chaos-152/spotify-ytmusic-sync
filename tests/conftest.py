import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure dummy credentials exist for tests that initialize client
os.environ.setdefault("YTMUSIC_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
os.environ.setdefault("YTMUSIC_CLIENT_SECRET", "test-client-secret")

from backend import db, main


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    """Sets up an isolated SQLite database for each test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    db.init_db()
    yield db_file


@pytest.fixture
def client():
    """FastAPI TestClient instance."""
    return TestClient(main.app)


@pytest.fixture
def exportify_csv_bytes():
    """Standard Exportify CSV format including duration."""
    return (
        "\ufeffTrack URI,Track Name,Artist Name(s),Album Name,Album Artist Name(s),Album Release Date,Disc Number,Track Number,Track Duration (ms),Explicit,Popularity,Added By,Added At\n"
        "spotify:track:1,Get Lucky,Daft Punk,Random Access Memories,Daft Punk,2013-05-17,1,8,369626,false,80,spotify:user:1,2023-01-01\n"
        "spotify:track:2,Bohemian Rhapsody,Queen,A Night at the Opera,Queen,1975-11-21,1,11,354320,false,85,spotify:user:1,2023-01-01\n"
        "spotify:track:3,Hotel California,Eagles,Hotel California,Eagles,1976-12-08,1,1,391376,false,88,spotify:user:1,2023-01-01\n"
    ).encode("utf-8")


@pytest.fixture
def alternate_csv_bytes():
    """Alternate header names (Title, Artist, Album, Duration)."""
    return (
        "Title,Artist,Album,Duration\n"
        "Starboy,The Weeknd,Starboy,3:50\n"
        "Blinding Lights,The Weeknd,After Hours,200000\n"
    ).encode("utf-8")
