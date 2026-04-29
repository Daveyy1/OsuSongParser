import re
import unicodedata

# Stripped from titles before Spotify search.
# The broad r"\[.*?\]" is intentionally excluded — it removes legitimate title content.
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    # TV size markers
    re.compile(r"\(TV\s*[Ss]ize\)", re.IGNORECASE),
    re.compile(r"\[TV\s*[Ss]ize\]", re.IGNORECASE),
    # Any parenthetical ending in "Ver." or "Version" — catches Rock Ver., Sped Up & Cut Ver., Full Ver., etc.
    re.compile(r"\([^)]*\bver(?:sion)?\.?\)", re.IGNORECASE),
    # feat. in parentheses or bare
    re.compile(r"\(feat\.[^)]*\)", re.IGNORECASE),
    re.compile(r"\s*feat\.\s+[^(\[]+", re.IGNORECASE),
    # Standalone edit/remix/mix tags that don't belong in the Spotify search
    re.compile(r"\(sped[\s\-]*up\)", re.IGNORECASE),
    re.compile(r"\(slowed(?:\s*[\+&]\s*reverb)?\)", re.IGNORECASE),
    re.compile(r"\(nightcore(?:\s*edit)?\)", re.IGNORECASE),
    re.compile(r"\((?:full\s+)?extended(?:\s+mix)?\)", re.IGNORECASE),
]


def _to_ascii(text: str) -> str:
    """Decompose unicode characters and drop non-ASCII, e.g. café -> cafe."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def clean_title(title: str) -> str:
    """Remove osu!/anime metadata noise from a title for Spotify search."""
    result = title
    for pattern in _NOISE_PATTERNS:
        result = pattern.sub("", result)
    return result.strip()


def normalize_for_comparison(text: str) -> str:
    """Lowercase, strip noise, collapse whitespace for fuzzy comparison.

    Tries ASCII normalization first. Falls back to lowercased unicode for strings
    that are fully non-ASCII (e.g. Japanese), so they still compare meaningfully.
    """
    cleaned = clean_title(text)
    ascii_version = re.sub(r"\s+", " ", _to_ascii(cleaned).lower()).strip()
    if ascii_version:
        return ascii_version
    return re.sub(r"\s+", " ", cleaned.lower()).strip()


def best_title(title: str, title_romanized: str | None) -> str:
    """Return the best title to use for Spotify search.

    Prefer the romanized version if it exists and is ASCII-safe,
    otherwise fall back to the unicode title.
    """
    if title_romanized and title_romanized.strip():
        return title_romanized
    ascii_attempt = _to_ascii(title)
    return ascii_attempt if ascii_attempt.strip() else title


def best_artist(artist: str, artist_romanized: str | None) -> str:
    """Return the best artist string to use for Spotify search."""
    if artist_romanized and artist_romanized.strip():
        return artist_romanized
    ascii_attempt = _to_ascii(artist)
    return ascii_attempt if ascii_attempt.strip() else artist
