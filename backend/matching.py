"""
Intelligent track matching between Spotify track metadata and YouTube Music search results.

Scores candidates based on:
1. Title similarity & exact matching
2. Version keyword consistency (penalizes studio vs. live/remix/acoustic mismatches)
3. Artist matching
4. Duration tolerance (matching within seconds vs. penalizing large discrepancies)
5. Album matching
"""
import re
from difflib import SequenceMatcher

VERSION_KEYWORDS = [
    "live",
    "remix",
    "acoustic",
    "instrumental",
    "karaoke",
    "cover",
    "orchestral",
    "demo",
    "slowed",
    "reverb",
    "sped up",
    "speed up",
    "remaster",
    "remastered",
    "radio edit",
    "extended",
]

# Common non-version video/audio fluff to clean from search titles
NOISE_PATTERNS = [
    r"\(official\s*(music)?\s*video\)",
    r"\[official\s*(music)?\s*video\]",
    r"\(official\s*audio\)",
    r"\[official\s*audio\]",
    r"\(audio\)",
    r"\[audio\]",
    r"\(lyrics?\)",
    r"\[lyrics?\]",
    r"\(visualizer\)",
    r"\[visualizer\]",
    r"\(hd\)",
    r"\[hd\]",
    r"\(4k\)",
    r"\[4k\]",
]

MIN_SCORE_THRESHOLD = 35.0


def parse_duration_seconds(val: str | int | float | None) -> int | None:
    """Parses candidate duration into integer seconds. Handles int, float, or 'M:SS' / 'H:MM:SS' strings."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        if ":" in val:
            parts = val.split(":")
            try:
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(float(parts[1]))
                elif len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
            except ValueError:
                return None
        try:
            return int(float(val))
        except ValueError:
            return None
    return None


def clean_text(text: str) -> str:
    """Normalizes string for comparison: lowercase, strips noise tags, removes punctuation."""
    if not text:
        return ""
    cleaned = text.lower()
    for pat in NOISE_PATTERNS:
        cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def extract_candidate_artists(candidate: dict) -> list[str]:
    """Extracts artist names list from various ytmusicapi candidate shapes."""
    raw = candidate.get("artists")
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw.strip()]
    if isinstance(raw, list):
        names = []
        for item in raw:
            if isinstance(item, dict) and "name" in item:
                names.append(item["name"].strip())
            elif isinstance(item, str):
                names.append(item.strip())
        return names
    return []


def extract_candidate_album(candidate: dict) -> str:
    """Extracts album name from various ytmusicapi candidate shapes."""
    raw = candidate.get("album")
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict) and "name" in raw:
        return (raw["name"] or "").strip()
    return ""


def extract_candidate_duration_sec(candidate: dict) -> int | None:
    """Extracts duration in seconds from candidate."""
    if "duration_seconds" in candidate and candidate["duration_seconds"] is not None:
        return parse_duration_seconds(candidate["duration_seconds"])
    if "duration" in candidate and candidate["duration"] is not None:
        return parse_duration_seconds(candidate["duration"])
    return None


def score_candidate(target: dict, candidate: dict) -> float:
    """
    Computes a match score (roughly 0 to 100) between target track metadata
    and a YouTube Music search result candidate.
    """
    score = 0.0

    target_title = target.get("title", "")
    target_artist = target.get("artist", "")
    target_album = target.get("album", "")
    target_duration_ms = target.get("duration_ms")

    cand_title = candidate.get("title", "")
    cand_artists = extract_candidate_artists(candidate)
    cand_album = extract_candidate_album(candidate)
    cand_duration_s = extract_candidate_duration_sec(candidate)

    norm_t_title = clean_text(target_title)
    norm_c_title = clean_text(cand_title)

    # 1. Title Similarity (0 - 35 pts) + exact match bonus (+10 pts)
    if norm_t_title and norm_c_title:
        title_ratio = SequenceMatcher(None, norm_t_title, norm_c_title).ratio()
        score += title_ratio * 35.0

        if norm_t_title == norm_c_title:
            score += 10.0
        elif norm_t_title in norm_c_title or norm_c_title in norm_t_title:
            score += 5.0

    # 2. Version keyword penalties/bonuses
    # e.g., if target doesn't say "live" but candidate does, penalize heavily (-25)
    t_words = set(norm_t_title.split())
    c_words = set(norm_c_title.split())

    for kw in VERSION_KEYWORDS:
        in_target = kw in norm_t_title or kw in t_words
        in_cand = kw in norm_c_title or kw in c_words

        if in_target and not in_cand:
            # Special case for "remaster" / "remastered": often omitted on YT Music
            if "remaster" in kw:
                score -= 5.0
            else:
                score -= 25.0
        elif not in_target and in_cand:
            if "remaster" in kw:
                score -= 5.0
            else:
                score -= 25.0
        elif in_target and in_cand:
            score += 15.0

    # 3. Artist Matching (0 - 30 pts)
    norm_t_artist = clean_text(target_artist)
    norm_c_artists = [clean_text(a) for a in cand_artists if a]

    matched_artist = False
    if norm_t_artist and norm_c_artists:
        # Check if primary artist is among candidates
        for c_art in norm_c_artists:
            if c_art == norm_t_artist or c_art in norm_t_artist or norm_t_artist in c_art:
                score += 30.0
                matched_artist = True
                break
            elif SequenceMatcher(None, norm_t_artist, c_art).ratio() > 0.75:
                score += 20.0
                matched_artist = True
                break

        if not matched_artist:
            score -= 15.0
    elif norm_t_artist:
        # If candidate has no artist info parsed, check if artist name appears in candidate title
        if norm_t_artist in norm_c_title:
            score += 15.0

    # 4. Duration Tolerance (-30 to +20 pts)
    if target_duration_ms and cand_duration_s is not None and target_duration_ms > 0:
        target_s = target_duration_ms / 1000.0
        diff_s = abs(target_s - cand_duration_s)

        if diff_s <= 3:
            score += 20.0
        elif diff_s <= 8:
            score += 15.0
        elif diff_s <= 15:
            score += 5.0
        elif diff_s <= 30:
            score -= 10.0
        else:
            score -= 30.0

    # 5. Album Matching (0 - 10 pts)
    norm_t_album = clean_text(target_album)
    norm_c_album = clean_text(cand_album)
    if norm_t_album and norm_c_album:
        if norm_t_album == norm_c_album or norm_t_album in norm_c_album or norm_c_album in norm_t_album:
            score += 10.0
        elif SequenceMatcher(None, norm_t_album, norm_c_album).ratio() > 0.8:
            score += 7.0

    return score


def find_best_match(
    target: dict,
    candidates: list[dict],
    min_threshold: float = MIN_SCORE_THRESHOLD,
) -> tuple[dict | None, float]:
    """
    Evaluates candidate search results and returns the best matching candidate
    along with its score, or (None, best_score) if no candidate passes min_threshold.
    """
    if not candidates:
        return None, 0.0

    best_candidate = None
    best_score = float("-inf")

    for cand in candidates:
        # Candidate must have a videoId to be playable/addable
        if not cand or not cand.get("videoId"):
            continue

        score = score_candidate(target, cand)
        if score > best_score:
            best_score = score
            best_candidate = cand

    if best_candidate and best_score >= min_threshold:
        return best_candidate, best_score

    return None, max(0.0, best_score) if best_score != float("-inf") else 0.0
