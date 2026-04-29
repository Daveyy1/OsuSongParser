import re

# Patterns stripped from titles before Spotify search.
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\(TV\s*[Ss]ize\)", re.IGNORECASE),
    re.compile(r"\[TV\s*[Ss]ize\]", re.IGNORECASE),
    re.compile(r"\(Short\s*Ver\.?\)", re.IGNORECASE),
    re.compile(r"\(Game\s*Ver\.?\)", re.IGNORECASE),
    re.compile(r"\(Cut\s*Ver\.?\)", re.IGNORECASE),
    re.compile(r"\(feat\.[^)]*\)", re.IGNORECASE),
]
