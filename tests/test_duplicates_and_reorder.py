import pytest
from unittest.mock import MagicMock, patch
from backend import matching, db, ytmusic_auth, spotify_client


# ==============================================================================
# 1. Duplicate Detection & Tolerance Logic Tests
# ==============================================================================

def test_duration_tolerance_constant():
    """Ensure DURATION_TOLERANCE_SECONDS is exported and equals 15s."""
    assert hasattr(matching, "DURATION_TOLERANCE_SECONDS")
    assert matching.DURATION_TOLERANCE_SECONDS == 15


def test_strip_featured_and_version_suffixes():
    """Verify suffix stripping cleans feat, ft, with, featuring in parentheses and trailers."""
    assert matching.strip_featured_and_version_suffixes("Ric Flair Drip (with Metro Boomin)") == "ric flair drip"
    assert matching.strip_featured_and_version_suffixes("lovely (with Khalid)") == "lovely"
    assert matching.strip_featured_and_version_suffixes("Dracula [feat. Jennie]") == "dracula"
    assert matching.strip_featured_and_version_suffixes("Song Title - with Metro Boomin") == "song title"
    assert matching.strip_featured_and_version_suffixes("Starboy feat. Daft Punk") == "starboy"
    assert matching.strip_featured_and_version_suffixes("Plain Title") == "plain title"


def test_extract_artist_set():
    """Verify artist set extraction normalizes names and handles compound separators."""
    artists = matching.extract_artist_set("Offset; Metro Boomin")
    assert "offset" in artists
    assert "metro boomin" in artists

    artists_feat = matching.extract_artist_set("Billie Eilish feat. Khalid")
    assert "billie eilish" in artists_feat
    assert "khalid" in artists_feat


def test_is_likely_duplicate_ric_flair_drip():
    """'Ric Flair Drip' vs 'Ric Flair Drip (with Metro Boomin)' within 15s tolerance -> Flagged."""
    track_a = {
        "title": "Ric Flair Drip",
        "artist": "Offset; Metro Boomin",
        "duration_ms": 172000,
    }
    track_b = {
        "title": "Ric Flair Drip (with Metro Boomin)",
        "artist": "Offset",
        "duration_ms": 175000,  # 3s diff <= 15s
    }
    is_dup, reason = matching.is_likely_duplicate(track_a, track_b)
    assert is_dup is True
    assert "likely duplicate" in reason.lower()
    assert "tolerance" in reason.lower()


def test_is_likely_duplicate_duration_exceeds_tolerance():
    """Same core title & overlapping artist but duration diff > 15s -> Distinct (NOT duplicate)."""
    track_a = {
        "title": "Dracula",
        "artist": "Artist A",
        "duration_ms": 180000,  # 3:00
    }
    track_b = {
        "title": "Dracula (with Jennie)",
        "artist": "Artist A; Jennie",
        "duration_ms": 230000,  # 3:50 (50s diff > 15s)
    }
    is_dup, reason = matching.is_likely_duplicate(track_a, track_b)
    assert is_dup is False
    assert "exceeds" in reason.lower()


def test_is_likely_duplicate_lovely_with_khalid():
    """'lovely' vs 'lovely (with Khalid)' within duration tolerance -> Flagged."""
    track_a = {
        "title": "lovely",
        "artist": "Billie Eilish, Khalid",
        "duration_ms": 200186,
    }
    track_b = {
        "title": "lovely (with Khalid)",
        "artist": "Billie Eilish",
        "duration_ms": 200186,
    }
    is_dup, reason = matching.is_likely_duplicate(track_a, track_b)
    assert is_dup is True


def test_is_likely_duplicate_different_artist_not_flagged():
    """Same title but no artist overlap -> NOT duplicate."""
    track_a = {
        "title": "Hello",
        "artist": "Adele",
        "duration_ms": 295000,
    }
    track_b = {
        "title": "Hello",
        "artist": "Lionel Richie",
        "duration_ms": 295000,
    }
    is_dup, reason = matching.is_likely_duplicate(track_a, track_b)
    assert is_dup is False
    assert "artist overlap" in reason.lower()


def test_is_likely_duplicate_missing_duration_fallback():
    """Missing duration metadata on either track falls back to core title + primary artist match."""
    track_a = {
        "title": "Song Without Duration (feat. Drake)",
        "artist": "Future",
    }
    track_b = {
        "title": "Song Without Duration",
        "artist": "Future",
        "duration_ms": 210000,
    }
    is_dup, reason = matching.is_likely_duplicate(track_a, track_b)
    assert is_dup is True
    assert "duration unavailable" in reason.lower()


# ==============================================================================
# 2. Promote-to-Unique & Track Listing Endpoint Tests
# ==============================================================================

def test_promote_to_unique_flow(client, test_db):
    """Test flagging as duplicate, promoting via API, and verifying override persists."""
    link_id = db.upsert_link("me", "Test Playlist")
    tracks = [
        {"position": 1, "title": "lovely", "artist": "Billie Eilish", "album": "dont smile at me", "duration_ms": 200000},
        {"position": 2, "title": "lovely (with Khalid)", "artist": "Billie Eilish; Khalid", "album": "13 Reasons Why", "duration_ms": 202000},
    ]
    db.replace_tracks(link_id, tracks)

    # 1. Fetch tracks before promotion: second track should be flagged as duplicate
    res1 = client.get(f"/api/links/{link_id}/tracks")
    assert res1.status_code == 200
    tracks_data1 = res1.json()
    assert len(tracks_data1) == 2
    assert tracks_data1[0]["is_duplicate"] is False
    assert tracks_data1[1]["is_duplicate"] is True
    assert tracks_data1[1]["first_seen_index"] == 1
    second_track_id = tracks_data1[1]["id"]

    # 2. Promote second track to unique
    promote_res = client.post(f"/api/links/{link_id}/tracks/{second_track_id}/promote-unique")
    assert promote_res.status_code == 200
    assert promote_res.json()["is_override_unique"] == 1

    # 3. Re-fetch tracks: second track is now unique and marked promoted_by_user
    res2 = client.get(f"/api/links/{link_id}/tracks")
    assert res2.status_code == 200
    tracks_data2 = res2.json()
    assert tracks_data2[1]["is_duplicate"] is False
    assert tracks_data2[1]["promoted_by_user"] is True

    # 4. Demote back to duplicate
    demote_res = client.post(f"/api/links/{link_id}/tracks/{second_track_id}/demote-duplicate")
    assert demote_res.status_code == 200
    assert demote_res.json()["is_override_unique"] == 0

    res3 = client.get(f"/api/links/{link_id}/tracks")
    assert res3.json()[1]["is_duplicate"] is True


def test_alphabetical_sorting_grouping_simulation():
    """
    Simulate the UI sorting logic for duplicates view:
    Full track title (artist tiebreaker) ensures base track precedes featuring variants.
    """
    dups = [
        {"title": "lovely (with Khalid)", "artist": "Billie Eilish"},
        {"title": "Ric Flair Drip (with Metro Boomin)", "artist": "Offset"},
        {"title": "lovely", "artist": "Billie Eilish"},
        {"title": "Ric Flair Drip", "artist": "Offset"},
    ]
    sorted_dups = sorted(dups, key=lambda x: (x["title"].lower(), x["artist"].lower()))
    titles = [x["title"] for x in sorted_dups]

    assert titles.index("Ric Flair Drip") < titles.index("Ric Flair Drip (with Metro Boomin)")
    assert titles.index("lovely") < titles.index("lovely (with Khalid)")


# ==============================================================================
# 3. Destination Playlist Reordering Tests
# ==============================================================================

def test_spotify_reorder_playlist_alphabetical_mocked(monkeypatch):
    """Verify Spotify alphabetical reordering gets tracks, sorts them, and calls PUT."""
    fake_items = {
        "items": [
            {"track": {"uri": "spotify:track:2", "name": "Zebra", "artists": [{"name": "Band B"}]}},
            {"track": {"uri": "spotify:track:1", "name": "Apple", "artists": [{"name": "Band A"}]}},
        ]
    }

    put_payload = []

    class FakeResponse:
        def __init__(self, data):
            self._data = data
        def read(self):
            import json
            return json.dumps(self._data).encode()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_urlopen(req, timeout=10):
        import json
        if req.get_method() == "GET":
            return FakeResponse(fake_items)
        elif req.get_method() == "PUT":
            put_payload.append(json.loads(req.data.decode()))
            return FakeResponse({"snapshot_id": "snap123"})
        raise ValueError(f"Unexpected method {req.get_method()}")

    monkeypatch.setattr(spotify_client.urllib.request, "urlopen", mock_urlopen)

    res = spotify_client.reorder_playlist_alphabetical("fake_token", "fake_pl_id")
    assert res["reordered"] is True
    assert res["total_tracks"] == 2
    assert len(put_payload) == 1
    assert put_payload[0]["uris"] == ["spotify:track:1", "spotify:track:2"]


def test_ytmusic_reorder_guardrail_exceeded(monkeypatch):
    """When needed moves exceed max_moves guardrail, skip and report quota protection."""
    client = ytmusic_auth.YouTubeSyncClient(access_token="fake_token")

    items = []
    for i in range(30):
        items.append({
            "id": f"item_{i}",
            "snippet": {
                "title": f"Track {30 - i:02d}",
                "position": i,
                "videoOwnerChannelTitle": "Artist",
                "resourceId": {"videoId": f"vid_{i}"},
            },
            "contentDetails": {"videoId": f"vid_{i}"},
        })

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": items, "nextPageToken": None}

    with patch("requests.get", return_value=mock_resp):
        res = client.reorder_playlist_alphabetical("fake_playlist", max_moves=20)
        assert res["reordered"] is False
        assert res["reason"] == "quota_guardrail_exceeded"
        assert res["moves_needed"] > 20
        assert res["quota_needed"] == res["moves_needed"] * 50


def test_ytmusic_reorder_within_guardrail(monkeypatch):
    """When moves are <= max_moves, reorder executes successfully."""
    client = ytmusic_auth.YouTubeSyncClient(access_token="fake_token")

    items = [
        {"id": "item_z", "snippet": {"title": "Zebra", "videoOwnerChannelTitle": "A", "resourceId": {"videoId": "v_z"}}, "contentDetails": {"videoId": "v_z"}},
        {"id": "item_a", "snippet": {"title": "Apple", "videoOwnerChannelTitle": "A", "resourceId": {"videoId": "v_a"}}, "contentDetails": {"videoId": "v_a"}},
    ]

    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = {"items": items, "nextPageToken": None}

    mock_put = MagicMock()
    mock_put.status_code = 200

    with patch("requests.get", return_value=mock_get), patch("requests.put", return_value=mock_put) as patched_put:
        res = client.reorder_playlist_alphabetical("fake_playlist", max_moves=20)
        assert res["reordered"] is True
        assert res["moves"] >= 1
        assert res["quota_used"] == res["moves"] * 50
        assert patched_put.called


def test_ytmusic_search_and_add_upfront_alphabetical_sorting(monkeypatch):
    """New/empty playlist sorts track queue upfront prior to insertion at 0 quota overhead."""
    fake_client = MagicMock()
    fake_client.search.side_effect = lambda query, filter, limit: [
        {"videoId": "v_" + query.split()[0].lower(), "title": query.split()[0], "artists": [{"name": "Artist"}], "duration": "3:00"}
    ]
    fake_client.add_playlist_items.return_value = 2

    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": fake_client)
    monkeypatch.setattr(ytmusic_auth, "get_playlist_existing_tracks", lambda pl_id, u_id: (set(), set()))

    unsorted_tracks = [
        {"title": "Zebra", "artist": "Artist", "duration_ms": 180000},
        {"title": "Apple", "artist": "Artist", "duration_ms": 180000},
    ]

    added_calls = []
    def fake_add(pl_id, vids, duplicates=False):
        added_calls.extend(vids)
        return len(vids)
    fake_client.add_playlist_items.side_effect = fake_add

    res = ytmusic_auth.search_and_add("pl_123", unsorted_tracks)
    assert res["added"] == 2
    assert added_calls == ["v_apple", "v_zebra"]


def test_is_likely_duplicate_radio_edit_flagged():
    """Radio edit versions should be flagged as likely duplicates even if duration differs beyond 15s."""
    track_album = {
        "title": "Get Lucky (feat. Pharrell Williams and Nile Rodgers)",
        "artist": "Daft Punk;Pharrell Williams;Nile Rodgers",
        "duration_ms": 369626,  # 6:09
    }
    track_radio = {
        "title": "Get Lucky (Radio Edit) [feat. Pharrell Williams and Nile Rodgers]",
        "artist": "Daft Punk;Pharrell Williams;Nile Rodgers",
        "duration_ms": 247632,  # 4:07 (122s diff)
    }
    is_dup, reason = matching.is_likely_duplicate(track_album, track_radio)
    assert is_dup is True
    assert "radio/single edit" in reason.lower()


def test_is_in_existing_keys_matches_normalized_version_suffixes():
    """_is_in_existing_keys matches core titles with differing feat/version suffixes."""
    existing_keys = {("get lucky (feat. pharrell williams and nile rodgers)", "daft punk")}
    assert ytmusic_auth._is_in_existing_keys(
        "Get Lucky (Radio Edit - feat. Pharrell Williams and Nile Rodgers)",
        "Daft Punk",
        existing_keys,
    ) is True


def test_ytmusic_search_and_add_partial_insertion_reconciliation(monkeypatch):
    """When a video fails to insert during add_playlist_items (e.g. unavailable video), details is reconciled."""
    fake_client = MagicMock()
    fake_client.search.side_effect = lambda query, filter, limit: [
        {"videoId": "v_succ" if "Good" in query else "v_fail", "title": query, "artists": [{"name": "Artist"}], "duration": "3:00"}
    ]

    add_res = ytmusic_auth.PlaylistAddResult(
        1,
        successful_ids={"v_succ"},
        failed_ids={"v_fail": "YouTube API: Video unavailable or insert rejected (400)"},
    )
    fake_client.add_playlist_items.return_value = add_res

    monkeypatch.setattr(ytmusic_auth, "get_client", lambda user_id="me": fake_client)
    monkeypatch.setattr(ytmusic_auth, "get_playlist_existing_tracks", lambda pl_id, u_id: (set(), set()))

    tracks = [
        {"title": "Good Song", "artist": "Artist", "duration_ms": 180000},
        {"title": "Unplayable Song", "artist": "Artist", "duration_ms": 180000},
    ]

    res = ytmusic_auth.search_and_add("pl_test", tracks)
    assert res["added"] == 1
    assert res["skipped"] == 1

    added_details = [d for d in res["details"] if d.get("status") in ("added", "matched")]
    skipped_details = [d for d in res["details"] if d.get("status") in ("skipped", "error")]
    assert len(added_details) == 1
    assert len(skipped_details) == 1
    assert skipped_details[0]["status"] == "error"
    assert skipped_details[0]["category"] == "insert_failed"
    assert "Video unavailable" in skipped_details[0]["reason"]
