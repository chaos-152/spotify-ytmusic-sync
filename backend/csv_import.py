"""
Parses Exportify-style CSV exports of Spotify playlists.

Exportify (https://exportify.net) runs client-side against your own Spotify
login session and downloads a CSV — no developer app, no API keys, no
Premium requirement. Column names have shifted a bit across Exportify
versions, so we match on a few known aliases per field rather than one
exact header.
"""
import csv
import io

# Each field maps to a list of header names we've seen in the wild, checked in order.
FIELD_ALIASES = {
    "title": ["Track Name", "Name", "Title"],
    "artist": ["Artist Name(s)", "Artist Name", "Artist(s)", "Artist"],
    "album": ["Album Name", "Album"],
    "duration_ms": [
        "Track Duration (ms)",
        "Duration (ms)",
        "Duration ms",
        "Track Duration",
        "Duration",
    ],
}


def _parse_duration_ms(val: str | None) -> int | None:
    if not val:
        return None
    val = val.strip()
    if not val:
        return None
    if ":" in val:
        parts = val.split(":")
        try:
            if len(parts) == 2:
                secs = int(parts[0]) * 60 + float(parts[1])
                return int(secs * 1000)
            elif len(parts) == 3:
                secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                return int(secs * 1000)
        except ValueError:
            return None
    try:
        return int(float(val))
    except ValueError:
        return None


def _find_header(fieldnames: list[str], aliases: list[str]) -> str | None:
    lower_map = {f.lower().strip(): f for f in fieldnames}
    for alias in aliases:
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    return None


def parse_csv(raw_bytes: bytes) -> list[dict]:
    """Returns [{title, artist, album, duration_ms}] in playlist order. Raises ValueError if
    the CSV doesn't look like a recognizable playlist export."""
    text = raw_bytes.decode("utf-8-sig")  # Exportify exports with a BOM
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValueError("CSV appears to be empty")

    title_col = _find_header(reader.fieldnames, FIELD_ALIASES["title"])
    artist_col = _find_header(reader.fieldnames, FIELD_ALIASES["artist"])

    if not title_col or not artist_col:
        raise ValueError(
            "Couldn't find track name / artist columns. Expected an Exportify-style "
            f"export. Found columns: {reader.fieldnames}"
        )

    album_col = _find_header(reader.fieldnames, FIELD_ALIASES["album"])
    duration_col = _find_header(reader.fieldnames, FIELD_ALIASES["duration_ms"])

    tracks = []
    for row in reader:
        title = (row.get(title_col) or "").strip()
        artist = (row.get(artist_col) or "").strip()
        if not title or not artist:
            continue  # skip malformed/blank rows
        tracks.append({
            "title": title,
            "artist": artist,
            "album": (row.get(album_col) or "").strip() if album_col else "",
            "duration_ms": _parse_duration_ms(row.get(duration_col)) if duration_col else None,
        })

    if not tracks:
        raise ValueError("No valid tracks found in this CSV")

    return tracks

