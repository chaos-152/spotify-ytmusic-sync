"""
Reverse Synchronization Engine: YouTube Music -> Spotify URI-Resolved CSV.
Extracts YouTube Music playlist tracks, decouples video noise, queries the
Spotify catalog via Client Credentials, scores candidates using heuristic gates,
and generates a deterministic Spotify-import-ready CSV populated with exact Spotify URIs.
"""
import re
import csv
import io
from typing import Optional
from ytmusicapi import YTMusic
from . import matching
from .spotify_client import SpotifyClientCredentials

# Common YouTube channel noise suffixes
CHANNEL_NOISE_RE = re.compile(
    r"\s*(- topic|vevo|official|channel|music|records|tv)\b",
    re.IGNORECASE,
)

# Common featured artist patterns inside titles
FEAT_RE = re.compile(
    r"\s*[\(\[](?:feat\.?|ft\.?|with)\s+([^\)\]]+)[\)\]]",
    re.IGNORECASE,
)


def clean_channel_name(channel: str) -> str:
    """Strips automated YouTube channel fluff (e.g. 'Daft Punk - Topic' -> 'Daft Punk')."""
    if not channel:
        return ""
    cleaned = CHANNEL_NOISE_RE.sub("", channel).strip()
    return cleaned or channel.strip()


def parse_yt_title(video_title: str, channel_title: str = "") -> tuple[str, str]:
    """
    Parses a raw YouTube video title and channel name into clean (title, artist).
    Examples:
        'Daft Punk - Get Lucky (Official Video) ft. Pharrell' -> ('Get Lucky', 'Daft Punk; Pharrell')
        'Starboy' (channel: 'The Weeknd - Topic')             -> ('Starboy', 'The Weeknd')
    """
    cleaned_video = video_title.strip()

    # 1. Strip common bracketed noise like (Official Video), [Audio], [HD]
    for pattern in matching.NOISE_PATTERNS:
        cleaned_video = re.sub(pattern, "", cleaned_video, flags=re.IGNORECASE).strip()

    # 2. Extract featured artists from title brackets if present
    featured_artists = []
    feat_match = FEAT_RE.search(cleaned_video)
    if feat_match:
        featured_artists = [a.strip() for a in re.split(r"[,;&]", feat_match.group(1)) if a.strip()]
        cleaned_video = FEAT_RE.sub("", cleaned_video).strip()

    # 3. Check for standard 'Artist - Title' delimiters
    title = ""
    artist = ""
    for delimiter in [" - ", " — ", " – ", " : "]:
        if delimiter in cleaned_video:
            parts = cleaned_video.split(delimiter, 1)
            artist_part = parts[0].strip()
            title_part = parts[1].strip()
            if artist_part and title_part:
                artist = artist_part
                title = title_part
                break

    # If no delimiter found, fallback to using channel title as artist
    if not title:
        title = cleaned_video
        artist = clean_channel_name(channel_title)

    # Append any extracted featured artists
    if featured_artists:
        all_artists = [artist] if artist else []
        for fa in featured_artists:
            if fa.lower() not in [a.lower() for a in all_artists]:
                all_artists.append(fa)
        artist = "; ".join(all_artists)

    # Clean punctuation and quotes from ends
    title = title.strip("\"' -–—")
    artist = artist.strip("\"' -–—")

    return title, artist


def extract_playlist_id(link_or_id: str) -> str:
    """Extracts raw playlist ID from a YouTube Music URL or returns the input ID."""
    link_or_id = link_or_id.strip()
    if "list=" in link_or_id:
        return link_or_id.split("list=")[1].split("&")[0]
    return link_or_id


def resolve_yt_playlist_to_spotify(
    playlist_id_or_url: str,
    spotify_client: Optional[SpotifyClientCredentials] = None,
    on_progress=None,
) -> dict:
    """
    Fetches tracks from a YouTube Music playlist, resolves each track to an
    exact Spotify track    Resolves all items in a YouTube Music playlist against the Spotify Catalog,
    and returns full audit telemetry plus an exact Spotify URI CSV.
    """
    playlist_id = extract_playlist_id(playlist_id_or_url)
    yt = YTMusic()
    
    try:
        yt_playlist = yt.get_playlist(playlist_id, limit=500)
    except Exception as e:
        raise ValueError(f"Failed to fetch YouTube Music playlist '{playlist_id}': {e}")

    yt_tracks = yt_playlist.get("tracks", [])
    if not yt_tracks:
        raise ValueError(f"Playlist '{playlist_id}' contains no accessible tracks.")

    client = spotify_client or SpotifyClientCredentials()
    if not client.is_configured:
        raise ValueError(
            "Spotify credentials not configured. Please add SPOTIFY_CLIENT_ID and "
            "SPOTIFY_CLIENT_SECRET to your backend/.env to resolve Spotify URIs."
        )

    matched_count = 0
    gap_count = 0
    details = []
    csv_rows = []

    total = len(yt_tracks)
    for idx, yt_item in enumerate(yt_tracks):
        raw_title = yt_item.get("title", "")
        artists_list = [a.get("name", "") for a in yt_item.get("artists", [])]
        channel_name = "; ".join(artists_list) or (yt_item.get("author") or "")
        dur_s = yt_item.get("duration_seconds")
        target_dur_ms = (dur_s * 1000) if dur_s else None

        clean_title, clean_artist = parse_yt_title(raw_title, channel_name)

        if on_progress:
            on_progress(idx + 1, total, clean_title)

        target_metadata = {
            "title": clean_title,
            "artist": clean_artist,
            "album": yt_item.get("album", {}).get("name", "") if isinstance(yt_item.get("album"), dict) else "",
            "duration_ms": target_dur_ms,
        }

        # Stage 1: Strict query, Stage 2: Fallback query
        queries = []
        if clean_title and clean_artist:
            # Field filter
            first_artist = clean_artist.split(";")[0].strip()
            queries.append(f'track:"{clean_title}" artist:"{first_artist}"')
            queries.append(f"{clean_title} {first_artist}")
        elif clean_title:
            queries.append(clean_title)

        candidates = []
        for q in queries:
            try:
                candidates = client.search_tracks(q, limit=5)
                if candidates:
                    break
            except Exception as e:
                import logging
                logging.getLogger("uvicorn.error").warning("Spotify search failed for '%s': %s", q, e)
                continue

        best_match, score = matching.find_best_match(target_metadata, candidates)

        if best_match and score >= matching.MIN_SCORE_THRESHOLD:
            matched_count += 1
            details.append({
                "source_title": raw_title,
                "clean_title": clean_title,
                "clean_artist": clean_artist,
                "yt_title": clean_title or raw_title,
                "yt_artist": clean_artist or (best_match["artist"] if best_match else "Unknown Artist"),
                "status": "matched",
                "spotify_uri": best_match["uri"],
                "spotify_title": best_match["title"],
                "spotify_artist": best_match["artist"],
                "matched_title": best_match["title"],
                "matched_artist": best_match["artist"],
                "spotify_album": best_match["album"],
                "duration_ms": best_match["duration_ms"],
                "score": round(score, 1),
                "confidence": round(score, 1),
            })
            csv_rows.append({
                "Spotify URI": best_match["uri"],
                "Track Name": best_match["title"],
                "Artist Name(s)": best_match["artist"],
                "Album Name": best_match["album"],
                "Duration (ms)": best_match["duration_ms"],
            })
        else:
            gap_count += 1
            details.append({
                "source_title": raw_title,
                "clean_title": clean_title,
                "clean_artist": clean_artist,
                "yt_title": clean_title or raw_title,
                "yt_artist": clean_artist or "Unknown Artist",
                "status": "skipped",
                "category": "catalog_gap",
                "spotify_uri": None,
                "spotify_title": best_match["title"] if best_match else "—",
                "spotify_artist": best_match["artist"] if best_match else "—",
                "matched_title": best_match["title"] if best_match else "—",
                "matched_artist": best_match["artist"] if best_match else "—",
                "score": round(score, 1) if best_match else 0.0,
                "confidence": round(score, 1) if best_match else 0.0,
                "reason": f"No confident Spotify match (score: {score:.1f})" if best_match else "Zero Spotify search results",
            })

    # Generate CSV output compatible with SpotMyBackup / Playlist-Backup / Spotlistr
    output = io.StringIO()
    fieldnames = ["Spotify URI", "Track Name", "Artist Name(s)", "Album Name", "Duration (ms)"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in csv_rows:
        writer.writerow(row)

    return {
        "playlist_title": yt_playlist.get("title", "YouTube Music Playlist"),
        "total": total,
        "matched_count": matched_count,
        "gap_count": gap_count,
        "precision_pct": round((matched_count / total) * 100, 1) if total else 0.0,
        "details": details,
        "csv_content": output.getvalue(),
    }
