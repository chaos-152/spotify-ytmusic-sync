"""
Intelligent track matching between Spotify track metadata and YouTube Music search results.

Scores candidates based on:
1. Plausibility Gates (Artist compatibility & Base Title similarity)
2. Core Title similarity (decoupled from version/remaster suffixes)
3. Artist matching (handles multi-artist delimiters and UGC titles)
4. Duration tolerance (conditional tiebreaker, not independent driver)
5. Version keyword consistency (live/remix/acoustic/karaoke penalties)
6. Album matching
"""
import re
from difflib import SequenceMatcher

VERSION_KEYWORDS = [
    "live",
    "remix",
    "mix",
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
    "club mix",
    "extended",
    "single version",
    "single edit",
]

VERSION_OR_NOISE_RE = re.compile(
    r"\b(live|remix|mix|acoustic|instrumental|karaoke|cover|orchestral|demo|slowed|reverb|"
    r"sped\s*up|speed\s*up|remaster(ed)?|\d{4}\s*remaster(ed)?|radio\s*edit|club\s*mix|extended|"
    r"single\s*(version|edit)|album\s*version|bonus(\s*track)?|deluxe(\s*edition)?|"
    r"feat(\.|\b)|ft(\.|\b)|with\b|official|audio|video|visualizer|lyrics?|hd|4k)\b",
    re.IGNORECASE,
)

KARAOKE_OR_COVER_RE = re.compile(
    r"\b(in\s*the\s*style\s*of|originally\s*performed\s*by|made\s*popular\s*by|tribute\s*to|"
    r"tribute\s*band|reprise\s*(to|of)|cover\s*(by|of)|karaoke\s*version|karaoke\s*backing|backing\s*track)\b",
    re.IGNORECASE,
)

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


def extract_core_title_and_versions(title: str) -> tuple[str, set[str]]:
    """
    Separates the base track title from version descriptors and boilerplate noise.
    Extracts version keywords (remaster, live, radio edit, etc.) into a set and
    returns a cleaned core title for base comparison.
    """
    raw = (title or "").strip()
    detected_versions: set[str] = set()

    # Check for karaoke or tribute phrases in raw title
    if KARAOKE_OR_COVER_RE.search(raw):
        detected_versions.add("karaoke")
        detected_versions.add("cover")

    # 1. Inspect brackets/parentheses: (Remastered 2006), [Live], {Karaoke Version}
    def check_bracket(match: re.Match) -> str:
        content = match.group(1)
        if VERSION_OR_NOISE_RE.search(content) or KARAOKE_OR_COVER_RE.search(content):
            for kw in VERSION_KEYWORDS:
                if re.search(r"\b" + re.escape(kw) + r"\b", content, re.IGNORECASE):
                    detected_versions.add(kw)
            return " "
        return match.group(0)

    stripped = re.sub(r"[\(\[\{]([^\)\]\}]+)[\)\]\}]", check_bracket, raw)

    # 2. Inspect hyphenated / dash suffixes (e.g. ' - Remastered', ' - Live', ' - Single Edit')
    parts = re.split(r"\s+[-–—]\s+", stripped)
    if len(parts) > 1:
        core_parts = [parts[0]]
        for p in parts[1:]:
            if VERSION_OR_NOISE_RE.search(p) or KARAOKE_OR_COVER_RE.search(p):
                for kw in VERSION_KEYWORDS:
                    if re.search(r"\b" + re.escape(kw) + r"\b", p, re.IGNORECASE):
                        detected_versions.add(kw)
            else:
                core_parts.append(p)
        stripped = " - ".join(core_parts)

    core = clean_text(stripped)
    return core, detected_versions


def split_artists(raw_artist: str) -> list[str]:
    """Splits compound artist strings (e.g. 'Fergie;Ludacris', 'Daryl Hall & John Oates') into normalized names."""
    if not raw_artist:
        return []
    parts = re.split(r"[;,&]|\bfeat\.?|\bft\.?|\bwith\b", raw_artist, flags=re.IGNORECASE)
    return [clean_text(p) for p in parts if clean_text(p)]


def check_artist_compatibility(
    target_artist: str,
    cand_artists: list[str],
    cand_title: str,
    cand_channel: str = "",
) -> tuple[bool, float]:
    """
    Evaluates whether the candidate is plausibly by the target artist, prioritizing canonical releases:
    1. Structured Canonical Artist Match: Candidate metadata has an artist matching the target.
       Awarded maximum priority (35 pts).
    2. UGC / Community Upload Match: If title uses 'Artist - Title' format (e.g. 'Queen - Bohemian Rhapsody'),
       verify the artist prefix against the target. Awarded secondary score (20 pts).
    3. Explicit non-matching structured artists (e.g. 'Michael Williams' for 'Drake') are disqualified.
    Guards against tribute/karaoke/reprise titles ('In the style of INXS', 'Reprise to Drake').
    Returns (is_compatible, artist_score).
    """
    t_arts = split_artists(target_artist)
    c_arts = [clean_text(a) for a in cand_artists if clean_text(a)]

    if not t_arts:
        return True, 0.0

    # Explicit cover/tribute/reprise markers in title disqualify candidate
    if KARAOKE_OR_COVER_RE.search(cand_title):
        return False, -40.0

    # 1. Canonical / Official Artist Match (Structured artists metadata)
    for t_art in t_arts:
        for c_art in c_arts:
            if t_art == c_art or t_art in c_art or c_art in t_art:
                return True, 35.0
            ratio = SequenceMatcher(None, t_art, c_art).ratio()
            if ratio >= 0.75:
                return True, 25.0
            elif ratio >= 0.60:
                return True, 15.0

    # 2. UGC / Community Upload check: candidate title follows 'Artist - Song' format
    parts = re.split(r"\s+[-–—]\s+", cand_title)
    if len(parts) >= 2:
        ugc_artist_prefix = clean_text(parts[0].strip())
        for t_art in t_arts:
            if t_art == ugc_artist_prefix or t_art in ugc_artist_prefix or ugc_artist_prefix in t_art:
                return True, 20.0
            if SequenceMatcher(None, t_art, ugc_artist_prefix).ratio() >= 0.75:
                return True, 15.0

    # 3. Channel name match
    norm_channel = clean_text(cand_channel)
    if norm_channel:
        for t_art in t_arts:
            if t_art == norm_channel or t_art in norm_channel:
                return True, 20.0

    return False, -35.0


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
    and a YouTube Music search result candidate using two-phase evaluation:
    Phase 1: Plausibility gates (artist correlation + minimum core title similarity)
    Phase 2: Fine-grained ranking (core title match + duration tiebreaker + version consistency + album)
    """
    target_title = target.get("title", "")
    target_artist = target.get("artist", "")
    target_album = target.get("album", "")
    target_duration_ms = target.get("duration_ms")

    cand_title = candidate.get("title", "")
    cand_artists = extract_candidate_artists(candidate)
    cand_album = extract_candidate_album(candidate)
    cand_duration_s = extract_candidate_duration_sec(candidate)

    # ------------------------------------------------------------------
    # PHASE 1: Plausibility Gates
    # ------------------------------------------------------------------
    # Gate 1: Artist Compatibility
    is_compat, artist_score = check_artist_compatibility(
        target_artist=target_artist,
        cand_artists=cand_artists,
        cand_title=cand_title,
    )
    if not is_compat:
        return 0.0  # Disqualified: candidate has zero artist correlation

    # Gate 2: Core Title Plausibility
    core_t, t_vers = extract_core_title_and_versions(target_title)
    core_c, c_vers = extract_core_title_and_versions(cand_title)

    title_ratio = SequenceMatcher(None, core_t, core_c).ratio() if core_t and core_c else 0.0
    substring_match = bool(core_t and core_c and (core_t in core_c or core_c in core_t))
    t_words = set(core_t.split())
    c_words = set(core_c.split())
    overlap = t_words & c_words
    word_recall = len(overlap) / len(t_words) if t_words else 0.0

    # Weak title similarity must NEVER be rescuable by artist match alone.
    # Short titles (<= 3 words) must have strong word coverage (>= 65%) OR high fuzzy ratio (>= 0.70)
    # to prevent a single shared word (e.g. 'Sarkaru Raa' -> 'Sarkaru Vaari Paata') from matching.
    if len(t_words) <= 3:
        if word_recall < 0.65 and title_ratio < 0.70 and not substring_match:
            return 0.0  # Disqualified: weak title match on short title
    else:
        if word_recall < 0.40 and title_ratio < 0.60 and not substring_match:
            return 0.0  # Disqualified: weak title match on long title

    # ------------------------------------------------------------------
    # PHASE 2: Fine-Grained Scoring & Ranking
    # ------------------------------------------------------------------
    score = 0.0

    # 1. Base Title Score (0 - 45 pts)
    score += title_ratio * 35.0
    if core_t == core_c:
        score += 10.0
    elif substring_match:
        score += 5.0

    # 2. Artist Score (0 - 30 pts)
    score += artist_score

    # 3. Duration Score (Conditional Tiebreaker / Validator)
    # Only applied when title similarity is already solid, preventing duration
    # agreement from turning completely different tracks into matches.
    if target_duration_ms and cand_duration_s is not None and target_duration_ms > 0:
        target_s = target_duration_ms / 1000.0
        diff_s = abs(target_s - cand_duration_s)

        if title_ratio >= 0.50 or substring_match:
            if diff_s <= 3:
                score += 20.0
            elif diff_s <= 8:
                score += 15.0
            elif diff_s <= 15:
                score += 5.0
            elif diff_s <= 30:
                score -= 10.0
            else:
                score -= 25.0

    # 4. Version Keyword Consistency
    for kw in VERSION_KEYWORDS:
        in_target = kw in t_vers
        in_cand = kw in c_vers

        if in_cand and not in_target:
            if kw in ("karaoke", "cover"):
                score -= 40.0
            elif kw in ("live", "remix"):
                score -= 25.0
            elif kw in ("acoustic", "instrumental"):
                score -= 20.0
            elif "remaster" in kw:
                pass  # Remaster vs studio album release is the same song; no penalty
            else:
                score -= 10.0
        elif in_target and not in_cand:
            if "remaster" in kw:
                pass  # Remaster vs original is acceptable
            elif kw in ("live", "remix"):
                score -= 20.0
            else:
                score -= 10.0
        elif in_target and in_cand:
            if kw in ("live", "remix"):
                score += 15.0
            elif kw in ("radio edit", "club mix", "extended"):
                score += 10.0
            else:
                score += 5.0

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
