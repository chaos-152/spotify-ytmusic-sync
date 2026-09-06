import pytest
from backend import csv_import


def test_parse_standard_exportify(exportify_csv_bytes):
    tracks = csv_import.parse_csv(exportify_csv_bytes)
    assert len(tracks) == 3

    assert tracks[0]["title"] == "Get Lucky"
    assert tracks[0]["artist"] == "Daft Punk"
    assert tracks[0]["album"] == "Random Access Memories"
    assert tracks[0]["duration_ms"] == 369626

    assert tracks[1]["title"] == "Bohemian Rhapsody"
    assert tracks[1]["artist"] == "Queen"
    assert tracks[1]["duration_ms"] == 354320

    assert tracks[2]["title"] == "Hotel California"
    assert tracks[2]["artist"] == "Eagles"
    assert tracks[2]["duration_ms"] == 391376


def test_parse_alternate_headers(alternate_csv_bytes):
    tracks = csv_import.parse_csv(alternate_csv_bytes)
    assert len(tracks) == 2

    assert tracks[0]["title"] == "Starboy"
    assert tracks[0]["artist"] == "The Weeknd"
    assert tracks[0]["album"] == "Starboy"
    # "3:50" -> 3 * 60 + 50 = 230s -> 230000ms
    assert tracks[0]["duration_ms"] == 230000

    assert tracks[1]["title"] == "Blinding Lights"
    assert tracks[1]["duration_ms"] == 200000


def test_parse_csv_empty_raises():
    with pytest.raises(ValueError, match="CSV appears to be empty"):
        csv_import.parse_csv(b"")


def test_parse_csv_missing_headers_raises():
    bad_csv = b"Song Name,Release Year\nSong A,2021\n"
    with pytest.raises(ValueError, match="Couldn't find track name / artist columns"):
        csv_import.parse_csv(bad_csv)


def test_parse_csv_blank_rows_skipped():
    csv_data = (
        "Track Name,Artist Name\n"
        "Song A,Artist A\n"
        ",\n"
        "   ,   \n"
        "Song B,Artist B\n"
    ).encode("utf-8")
    tracks = csv_import.parse_csv(csv_data)
    assert len(tracks) == 2
    assert tracks[0]["title"] == "Song A"
    assert tracks[1]["title"] == "Song B"


def test_parse_csv_no_valid_tracks_raises():
    csv_data = b"Track Name,Artist Name\n,\n"
    with pytest.raises(ValueError, match="No valid tracks found in this CSV"):
        csv_import.parse_csv(csv_data)


def test_parse_duration_ms_helper():
    assert csv_import._parse_duration_ms(None) is None
    assert csv_import._parse_duration_ms("") is None
    assert csv_import._parse_duration_ms("   ") is None
    assert csv_import._parse_duration_ms("180000") == 180000
    assert csv_import._parse_duration_ms("180000.5") == 180000
    # "2:30" = 150 seconds = 150000 ms
    assert csv_import._parse_duration_ms("2:30") == 150000
    # "1:01:10" = 3670 seconds = 3670000 ms
    assert csv_import._parse_duration_ms("1:01:10") == 3670000
    assert csv_import._parse_duration_ms("invalid:time:format:extra") is None
    assert csv_import._parse_duration_ms("not-a-number") is None


def test_parse_csv_quoted_commas_and_aliases():
    csv_data = (
        'Name,Artist(s),Album,Duration ms\n'
        '"EARFQUAKE","Tyler, The Creator","IGOR",190000\n'
        '"Theme, Pt. 1","Composer, Jr.","Soundtrack, Vol. 1",145000\n'
    ).encode("utf-8")
    tracks = csv_import.parse_csv(csv_data)
    assert len(tracks) == 2
    assert tracks[0]["title"] == "EARFQUAKE"
    assert tracks[0]["artist"] == "Tyler, The Creator"
    assert tracks[0]["album"] == "IGOR"
    assert tracks[0]["duration_ms"] == 190000

    assert tracks[1]["title"] == "Theme, Pt. 1"
    assert tracks[1]["artist"] == "Composer, Jr."
    assert tracks[1]["album"] == "Soundtrack, Vol. 1"
    assert tracks[1]["duration_ms"] == 145000

