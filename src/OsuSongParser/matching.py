from rapidfuzz import fuzz
from spotipy import Spotify

from OsuSongParser.models import OsuSong, SpotifyMatch
from OsuSongParser.normalize import best_artist, best_title, clean_title, normalize_for_comparison
from OsuSongParser.spotify_api import search_track

_MATCH_THRESHOLD = 85.0
_REVIEW_THRESHOLD = 70.0


"""Score a Spotify candidate against normalized osu! metadata (0–100)."""
def _score(osu_title: str, osu_artist: str, candidate: dict) -> float:
    spotify_title = normalize_for_comparison(candidate.get("name", ""))
    spotify_artist = normalize_for_comparison(
        " ".join(a["name"] for a in candidate.get("artists", []))
    )

    title_sim = fuzz.token_sort_ratio(osu_title, spotify_title)
    artist_sim = fuzz.token_sort_ratio(osu_artist, spotify_artist)

    return 0.65 * title_sim + 0.35 * artist_sim


def song_key(song: OsuSong) -> str:
    if song.beatmapset_id is not None:
        return str(song.beatmapset_id)
    return f"{song.artist}|{song.title}"


"""Match a single OsuSong against Spotify and return a SpotifyMatch."""
def match_song(sp: Spotify, song: OsuSong) -> SpotifyMatch:
    # Clean noise from titles before sending to Spotify (better first-hit rate)
    romanized_title = clean_title(best_title(song.title, song.title_romanized))
    romanized_artist = best_artist(song.artist, song.artist_romanized)

    norm_title = normalize_for_comparison(romanized_title)
    norm_artist = normalize_for_comparison(romanized_artist)

    # Step 1: romanized/ASCII search (strict query only)
    candidates_by_uri: dict[str, dict] = {
        c["uri"]: c for c in search_track(sp, romanized_title, romanized_artist)
    }

    # Step 2: unicode search — only if romanized returned nothing AND strings are significantly different.
    # More selective to minimize API calls while still catching Japanese/Korean/Chinese titles.
    unicode_title = clean_title(song.title)
    unicode_artist = song.artist
    should_try_unicode = (
        not candidates_by_uri
        and (
            abs(len(unicode_title) - len(romanized_title)) > 3  # Significant length difference
            or any(ord(c) > 127 for c in unicode_title)  # Contains non-ASCII characters
            or any(ord(c) > 127 for c in unicode_artist)
        )
    )
    if should_try_unicode:
        for c in search_track(sp, unicode_title, unicode_artist):
            candidates_by_uri.setdefault(c["uri"], c)

    candidates = list(candidates_by_uri.values())
    key = song_key(song)

    if not candidates:
        return SpotifyMatch(
            osu_song_key=key,
            spotify_track_id=None,
            spotify_uri=None,
            spotify_url=None,
            matched_artist=None,
            matched_title=None,
            confidence=0.0,
            status="unmatched",
        )

    best = max(candidates, key=lambda c: _score(norm_title, norm_artist, c))
    confidence = _score(norm_title, norm_artist, best)

    if confidence >= _MATCH_THRESHOLD:
        status = "matched"
    elif confidence >= _REVIEW_THRESHOLD:
        status = "review"
    else:
        status = "unmatched"

    return SpotifyMatch(
        osu_song_key=key,
        spotify_track_id=best["id"],
        spotify_uri=best["uri"],
        spotify_url=best["external_urls"].get("spotify"),
        matched_artist=", ".join(a["name"] for a in best["artists"]),
        matched_title=best["name"],
        confidence=round(confidence, 2),
        status=status,
    )


"""Yield one SpotifyMatch per OsuSong so callers can show progress."""
def match_songs(sp: Spotify, songs: list[OsuSong]):
    for song in songs:
        yield match_song(sp, song)
