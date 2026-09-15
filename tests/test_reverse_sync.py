"""
Unit tests for the Reverse Sync Engine (YouTube Music -> Spotify URI CSV).
"""
import io
import json
from unittest.mock import MagicMock
import pytest
from backend import yt_to_spotify, spotify_client


def test_clean_channel_name():
    assert yt_to_spotify.clean_channel_name("Daft Punk - Topic") == "Daft Punk"
    assert yt_to_spotify.clean_channel_name("The Weeknd VEVO") == "The Weeknd"
    assert yt_to_spotify.clean_channel_name("Drake Official") == "Drake"
    assert yt_to_spotify.clean_channel_name("Independent Artist") == "Independent Artist"


def test_parse_yt_title_standard_delimiters():
    title, artist = yt_to_spotify.parse_yt_title("Daft Punk - Get Lucky (Official Music Video)")
    assert title == "Get Lucky"
    assert artist == "Daft Punk"

    title, artist = yt_to_spotify.parse_yt_title("The Weeknd — Blinding Lights [Audio]")
    assert title == "Blinding Lights"
    assert artist == "The Weeknd"


def test_parse_yt_title_featured_artists():
    title, artist = yt_to_spotify.parse_yt_title(
        "Calvin Harris - Slide (feat. Frank Ocean & Migos) [Official Audio]"
    )
    assert title == "Slide"
    assert "Calvin Harris" in artist
    assert "Frank Ocean" in artist
    assert "Migos" in artist


def test_parse_yt_title_fallback_to_channel():
    title, artist = yt_to_spotify.parse_yt_title("Midnight City", "M83 - Topic")
    assert title == "Midnight City"
    assert artist == "M83"


def test_extract_playlist_id():
    url = "https://music.youtube.com/playlist?list=PLbaQ5acMJ2hA&si=123"
    assert yt_to_spotify.extract_playlist_id(url) == "PLbaQ5acMJ2hA"
    assert yt_to_spotify.extract_playlist_id("PLbaQ5acMJ2hA") == "PLbaQ5acMJ2hA"


def test_spotify_client_credentials_search_mocked(monkeypatch):
    """Confirm client credentials token retrieval and catalog search are fully mocked (zero live network)."""
    client = spotify_client.SpotifyClientCredentials(client_id="test_id", client_secret="test_secret")
    
    # Mock token response
    mock_token_resp = io.BytesIO(json.dumps({"access_token": "mock_token_123", "expires_in": 3600}).encode())
    # Mock search response
    mock_search_resp = io.BytesIO(json.dumps({
        "tracks": {
            "items": [
                {
                    "id": "track_123",
                    "uri": "spotify:track:track_123",
                    "name": "Get Lucky",
                    "artists": [{"name": "Daft Punk"}],
                    "album": {"name": "Random Access Memories"},
                    "duration_ms": 248000,
                    "external_ids": {"isrc": "USAT21300898"},
                    "popularity": 85,
                }
            ]
        }
    }).encode())

    responses = [mock_token_resp, mock_search_resp]
    def mock_urlopen(req, timeout=10):
        resp = responses.pop(0)
        mock = MagicMock()
        mock.__enter__.return_value = mock
        mock.read.return_value = resp.getvalue()
        return mock

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    candidates = client.search_tracks("Get Lucky Daft Punk")
    assert len(candidates) == 1
    assert candidates[0]["uri"] == "spotify:track:track_123"
    assert candidates[0]["title"] == "Get Lucky"
    assert candidates[0]["artist"] == "Daft Punk"
    assert candidates[0]["duration_ms"] == 248000


def test_resolve_yt_playlist_to_spotify_mocked(monkeypatch):
    mock_yt = MagicMock()
    mock_yt.get_playlist.return_value = {
        "title": "Road Trip Hits",
        "tracks": [
            {
                "title": "Daft Punk - Get Lucky (Official Video)",
                "artists": [{"name": "Daft Punk"}],
                "duration_seconds": 248,
            },
            {
                "title": "Unknown Song From Unknown Artist",
                "artists": [{"name": "Nobody"}],
                "duration_seconds": 120,
            },
        ],
    }
    monkeypatch.setattr(yt_to_spotify, "YTMusic", lambda: mock_yt)

    mock_client = MagicMock()
    mock_client.is_configured = True
    # First search returns Get Lucky, second search returns nothing
    mock_client.search_tracks.side_effect = [
        [
            {
                "uri": "spotify:track:69kOkLBsCcIZAjOpkcw2nQ",
                "title": "Get Lucky",
                "artist": "Daft Punk",
                "artists": [{"name": "Daft Punk"}],
                "album": "Random Access Memories",
                "duration_ms": 248000,
                "duration_seconds": 248,
            }
        ],
        [],
    ]

    result = yt_to_spotify.resolve_yt_playlist_to_spotify("PLmock123", spotify_client=mock_client)
    assert result["total"] == 2
    assert result["matched_count"] == 1
    assert result["gap_count"] == 1
    assert result["precision_pct"] == 50.0
    assert "Spotify URI,Track Name,Artist Name(s),Album Name,Duration (ms)" in result["csv_content"]
    assert "spotify:track:69kOkLBsCcIZAjOpkcw2nQ" in result["csv_content"]
    assert result["details"][0]["yt_title"] == "Get Lucky"
    assert result["details"][0]["matched_title"] == "Get Lucky"
    assert result["details"][0]["confidence"] > 0


def test_spotify_user_oauth_helpers_mocked(monkeypatch):
    """Test Spotify User OAuth authorization URL generation, profile fetching, and playlist writes."""
    auth_url = spotify_client.get_spotify_auth_url("client_123", "http://localhost/callback", "state_abc")
    assert "https://accounts.spotify.com/authorize" in auth_url
    assert "client_123" in auth_url
    assert "playlist-modify-private" in auth_url

    # Mock token exchange
    mock_token_resp = io.BytesIO(json.dumps({
        "access_token": "user_tok_123",
        "refresh_token": "user_ref_456",
        "expires_in": 3600,
    }).encode())
    
    # Mock profile response
    mock_profile_resp = io.BytesIO(json.dumps({
        "id": "spotify_user_999",
        "display_name": "Test User",
    }).encode())

    # Mock playlist creation response
    mock_playlist_resp = io.BytesIO(json.dumps({
        "id": "pl_spotify_abc",
        "name": "New Playlist",
        "external_urls": {"spotify": "https://open.spotify.com/playlist/pl_spotify_abc"},
    }).encode())

    # Mock add tracks response
    mock_add_resp = io.BytesIO(json.dumps({"snapshot_id": "snap_1"}).encode())

    responses = [mock_token_resp, mock_profile_resp, mock_playlist_resp, mock_add_resp]

    def mock_urlopen(req, timeout=10):
        resp = responses.pop(0)
        mock = MagicMock()
        mock.__enter__.return_value = mock
        mock.read.return_value = resp.getvalue()
        return mock

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    token = spotify_client.exchange_code_for_user_token("auth_code", "http://localhost/callback", "c_id", "c_sec")
    assert token["access_token"] == "user_tok_123"
    assert token["refresh_token"] == "user_ref_456"

    profile = spotify_client.get_current_user_profile("user_tok_123")
    assert profile["id"] == "spotify_user_999"

    pl = spotify_client.create_user_playlist("user_tok_123", "spotify_user_999", "New Playlist")
    assert pl["id"] == "pl_spotify_abc"

    added = spotify_client.add_tracks_to_playlist("user_tok_123", "pl_spotify_abc", ["spotify:track:1", "spotify:track:2"])
    assert added == 2
