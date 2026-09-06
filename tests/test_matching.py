from backend import matching


def test_parse_duration_seconds():
    assert matching.parse_duration_seconds(None) is None
    assert matching.parse_duration_seconds(180) == 180
    assert matching.parse_duration_seconds(180.9) == 180
    assert matching.parse_duration_seconds("3:45") == 225
    assert matching.parse_duration_seconds("03:45") == 225
    assert matching.parse_duration_seconds("1:02:15") == 3735
    assert matching.parse_duration_seconds("invalid") is None
    assert matching.parse_duration_seconds("") is None


def test_clean_text():
    assert matching.clean_text("Get Lucky (Official Video)") == "get lucky"
    assert matching.clean_text("Song Title [Official Audio] [Lyrics]") == "song title"
    assert matching.clean_text("Artist & Co. - The Hits!") == "artist co the hits"


def test_exact_match_high_score():
    target = {
        "title": "Bohemian Rhapsody",
        "artist": "Queen",
        "album": "A Night at the Opera",
        "duration_ms": 354000,
    }
    candidate = {
        "videoId": "fJ9rUzIMcZQ",
        "title": "Bohemian Rhapsody",
        "artists": [{"name": "Queen"}],
        "album": {"name": "A Night at the Opera"},
        "duration": "5:54",  # 354 seconds
    }
    score = matching.score_candidate(target, candidate)
    assert score >= 90.0

    match, best_score = matching.find_best_match(target, [candidate])
    assert match is not None
    assert match["videoId"] == "fJ9rUzIMcZQ"
    assert best_score >= 90.0


def test_live_penalty_prefers_studio_version():
    target = {
        "title": "Hotel California",
        "artist": "Eagles",
        "album": "Hotel California",
        "duration_ms": 391000,
    }
    live_candidate = {
        "videoId": "live_vid",
        "title": "Hotel California (Live at The Forum)",
        "artists": [{"name": "Eagles"}],
        "duration": "7:10",  # 430 seconds
    }
    studio_candidate = {
        "videoId": "studio_vid",
        "title": "Hotel California",
        "artists": [{"name": "Eagles"}],
        "duration": "6:31",  # 391 seconds
    }

    match, score = matching.find_best_match(target, [live_candidate, studio_candidate])
    assert match is not None
    assert match["videoId"] == "studio_vid"
    assert matching.score_candidate(target, studio_candidate) > matching.score_candidate(target, live_candidate)


def test_target_live_prefers_live_candidate():
    target = {
        "title": "Hotel California - Live",
        "artist": "Eagles",
        "duration_ms": 430000,
    }
    live_candidate = {
        "videoId": "live_vid",
        "title": "Hotel California (Live)",
        "artists": [{"name": "Eagles"}],
        "duration": "7:10",
    }
    studio_candidate = {
        "videoId": "studio_vid",
        "title": "Hotel California",
        "artists": [{"name": "Eagles"}],
        "duration": "6:31",
    }

    match, _ = matching.find_best_match(target, [studio_candidate, live_candidate])
    assert match is not None
    assert match["videoId"] == "live_vid"


def test_remix_penalty():
    target = {
        "title": "Get Lucky",
        "artist": "Daft Punk",
        "duration_ms": 248000,
    }
    remix_candidate = {
        "videoId": "remix_vid",
        "title": "Get Lucky (Lifelike Remix)",
        "artists": [{"name": "Daft Punk"}],
        "duration": "4:10",
    }
    original_candidate = {
        "videoId": "orig_vid",
        "title": "Get Lucky",
        "artists": [{"name": "Daft Punk"}],
        "duration": "4:08",
    }

    match, _ = matching.find_best_match(target, [remix_candidate, original_candidate])
    assert match is not None
    assert match["videoId"] == "orig_vid"


def test_duration_difference_penalized():
    target = {
        "title": "Short Song",
        "artist": "Artist X",
        "duration_ms": 180000,  # 3 minutes
    }
    extended_candidate = {
        "videoId": "extended_vid",
        "title": "Short Song",
        "artists": [{"name": "Artist X"}],
        "duration": "10:30",  # 10.5 minutes
    }
    accurate_candidate = {
        "videoId": "accurate_vid",
        "title": "Short Song",
        "artists": [{"name": "Artist X"}],
        "duration": "3:02",  # 182 seconds
    }

    match, _ = matching.find_best_match(target, [extended_candidate, accurate_candidate])
    assert match is not None
    assert match["videoId"] == "accurate_vid"


def test_acoustic_and_instrumental_penalties():
    target = {"title": "Layla", "artist": "Eric Clapton", "duration_ms": 424000}
    acoustic_cand = {
        "videoId": "acoustic_vid",
        "title": "Layla (Acoustic)",
        "artists": [{"name": "Eric Clapton"}],
        "duration": "4:49",
    }
    studio_cand = {
        "videoId": "studio_vid",
        "title": "Layla",
        "artists": [{"name": "Derek & the Dominos, Eric Clapton"}],
        "duration": "7:04",
    }
    match, _ = matching.find_best_match(target, [acoustic_cand, studio_cand])
    assert match is not None
    assert match["videoId"] == "studio_vid"


def test_album_matching_bonus():
    target = {
        "title": "Come Together",
        "artist": "The Beatles",
        "album": "Abbey Road",
        "duration_ms": 259000,
    }
    compilation_cand = {
        "videoId": "comp_vid",
        "title": "Come Together",
        "artists": [{"name": "The Beatles"}],
        "album": {"name": "1 (2015 Version)"},
        "duration": "4:19",
    }
    abbey_road_cand = {
        "videoId": "abbey_vid",
        "title": "Come Together",
        "artists": [{"name": "The Beatles"}],
        "album": {"name": "Abbey Road (Super Deluxe Edition)"},
        "duration": "4:19",
    }
    assert matching.score_candidate(target, abbey_road_cand) > matching.score_candidate(target, compilation_cand)
    match, _ = matching.find_best_match(target, [compilation_cand, abbey_road_cand])
    assert match["videoId"] == "abbey_vid"


def test_ranking_across_multiple_candidate_variants():
    target = {"title": "Creep", "artist": "Radiohead", "duration_ms": 238000}
    candidates = [
        {"videoId": "live_vid", "title": "Creep (Live at Glastonbury)", "artists": [{"name": "Radiohead"}], "duration": "4:15"},
        {"videoId": "cover_vid", "title": "Creep (Cover)", "artists": [{"name": "Postmodern Jukebox"}], "duration": "4:20"},
        {"videoId": "acoustic_vid", "title": "Creep (Acoustic)", "artists": [{"name": "Radiohead"}], "duration": "4:18"},
        {"videoId": "studio_vid", "title": "Creep", "artists": [{"name": "Radiohead"}], "duration": "3:58"},
    ]
    match, score = matching.find_best_match(target, candidates)
    assert match is not None
    assert match["videoId"] == "studio_vid"


def test_below_threshold_rejection():
    target = {
        "title": "Midnight City",
        "artist": "M83",
        "duration_ms": 243000,
    }
    completely_unrelated = {
        "videoId": "unrelated_vid",
        "title": "Canon in D",
        "artists": [{"name": "Pachelbel"}],
        "duration": "5:30",
    }
    match, score = matching.find_best_match(target, [completely_unrelated])
    assert match is None
    assert score < matching.MIN_SCORE_THRESHOLD


def test_candidate_handles_missing_fields_gracefully():
    target = {"title": "Hello", "artist": "Adele"}
    minimal_candidate = {
        "videoId": "hello_vid",
        "title": "Hello",
        "artists": "Adele",  # string format
    }
    match, score = matching.find_best_match(target, [minimal_candidate])
    assert match is not None
    assert match["videoId"] == "hello_vid"

