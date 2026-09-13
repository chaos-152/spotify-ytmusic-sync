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


def test_artist_gate_rejects_unrelated_artist_cover():
    """Exact title match with 0 artist correlation must be rejected by the artist gate."""
    target = {"title": "New Sensation", "artist": "INXS", "duration_ms": 219813}
    cover_candidate = {
        "videoId": "alterboy_vid",
        "title": "New Sensation",
        "artists": [{"name": "Alterboy"}],
        "duration": "3:33",
    }
    score = matching.score_candidate(target, cover_candidate)
    assert score == 0.0
    match, best_score = matching.find_best_match(target, [cover_candidate])
    assert match is None
    assert best_score == 0.0


def test_duration_cannot_override_title_mismatch():
    """Identical duration and matching artist must not allow a totally different title to pass."""
    target = {"title": "Anthem", "artist": "NJOI", "duration_ms": 198000}
    different_song_candidate = {
        "videoId": "acid_machine_vid",
        "title": "Acid Machine",
        "artists": [{"name": "Njoi"}],
        "duration": "3:17",  # 197s (1s diff from 198s)
    }
    score = matching.score_candidate(target, different_song_candidate)
    assert score == 0.0
    match, best_score = matching.find_best_match(target, [different_song_candidate])
    assert match is None


def test_core_title_extraction_prevents_remaster_crossmatch():
    """Shared '(Remastered)' boilerplate suffix must not inflate similarity between different songs."""
    target = {"title": "Alright - Remastered", "artist": "Jamiroquai", "duration_ms": 263920}
    wrong_song_same_suffix = {
        "videoId": "high_times_vid",
        "title": "High Times (Remastered 2006)",
        "artists": [{"name": "Jamiroquai"}],
        "duration": "4:11",
    }
    right_song_studio = {
        "videoId": "alright_vid",
        "title": "Alright",
        "artists": [{"name": "Jamiroquai"}],
        "duration": "4:24",  # 264s (exact match)
    }
    # Wrong song has 0 core title similarity ("alright" vs "high times")
    assert matching.score_candidate(target, wrong_song_same_suffix) == 0.0

    match, best_score = matching.find_best_match(target, [wrong_song_same_suffix, right_song_studio])
    assert match is not None
    assert match["videoId"] == "alright_vid"
    assert best_score >= 80.0


def test_karaoke_and_tribute_phrases_disqualified():
    """Tracks with 'In the style of' or 'Karaoke' in title must be rejected when target is original."""
    target = {"title": "New Sensation", "artist": "INXS", "duration_ms": 219813}
    karaoke_candidate = {
        "videoId": "karaoke_vid",
        "title": "New Sensation [In the Style of Inxs] {Karaoke Version}",
        "artists": [{"name": "The Karaoke Channel"}],
        "duration": "3:41",
    }
    score = matching.score_candidate(target, karaoke_candidate)
    assert score == 0.0


def test_ugc_user_upload_matching_artist_in_title():
    """User-uploaded video where artist is in the title (not channel metadata) must pass artist gate."""
    target = {"title": "Bohemian Rhapsody", "artist": "Queen", "duration_ms": 354000}
    ugc_candidate = {
        "videoId": "ugc_vid",
        "title": "Queen - Bohemian Rhapsody (Audio)",
        "artists": [{"name": "ClassicRockFan99"}],
        "duration": "5:54",
    }
    score = matching.score_candidate(target, ugc_candidate)
    assert score >= 70.0
    match, best_score = matching.find_best_match(target, [ugc_candidate])
    assert match is not None
    assert match["videoId"] == "ugc_vid"


def test_single_word_overlap_insufficient_for_short_title():
    """Matching 1 word out of 2 on a short title must be rejected, even if artist matches."""
    target = {"title": "Sarkaru Raa", "artist": "Thaman S", "duration_ms": 158476}
    candidate = {
        "videoId": "wrong_vid",
        "title": "Sarkaru Vaari Paata-Title Song",
        "artists": [{"name": "Thaman S"}, {"name": "Harika Narayan"}],
        "duration": "2:37",
    }
    score = matching.score_candidate(target, candidate)
    assert score == 0.0
    match, _ = matching.find_best_match(target, [candidate])
    assert match is None


def test_canonical_artist_outranks_tribute_mention():
    """Tribute cover by another artist mentioning original artist in title must be rejected over canonical release."""
    target = {"title": "One Dance", "artist": "Drake;Wizkid;Kyla", "duration_ms": 173986}
    tribute_cand = {
        "videoId": "tribute_vid",
        "title": "One Dance [Reprise to Drake Feat Wizkid & Kyla]",
        "artists": [{"name": "Michael Williams"}],
        "duration": "2:51",  # closer duration
    }
    official_cand = {
        "videoId": "official_vid",
        "title": "One Dance",
        "artists": [{"name": "Drake"}],
        "duration": "3:47",  # album cut duration
    }
    assert matching.score_candidate(target, tribute_cand) == 0.0
    match, best_score = matching.find_best_match(target, [tribute_cand, official_cand])
    assert match is not None
    assert match["videoId"] == "official_vid"
    assert best_score >= 50.0

