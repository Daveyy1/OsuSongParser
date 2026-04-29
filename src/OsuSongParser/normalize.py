import re
import unicodedata

# Stripped from titles before Spotify search.
# The broad r"\[.*?\]" is intentionally excluded — it removes legitimate title content.
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\(TV\s*[Ss]ize\)", re.IGNORECASE),
    re.compile(r"\[TV\s*[Ss]ize\]", re.IGNORECASE),
    re.compile(r"\(Short\s*Ver\.?\)", re.IGNORECASE),
    re.compile(r"\(Game\s*Ver\.?\)", re.IGNORECASE),
    re.compile(r"\(Cut\s*Ver\.?\)", re.IGNORECASE),
    re.compile(r"\(feat\.[^)]*\)", re.IGNORECASE),
    re.compile(r"\s*feat\.\s+\S+", re.IGNORECASE),
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
    """Lowercase, strip noise, collapse whitespace, and drop non-ASCII for fuzzy comparison."""
    text = clean_title(text)
    text = _to_ascii(text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
