import csv
from dataclasses import asdict
from pathlib import Path

from OsuSongParser.models import OsuSong, SpotifyMatch

_OSU_SONG_FIELDS = [
    "source", "artist", "title", "artist_romanized", "title_romanized",
    "beatmapset_id", "beatmap_id", "creator", "difficulty",
    "audio_filename", "tags", "osu_beatmapset_url", "osu_beatmap_url",
]

_SPOTIFY_MATCH_FIELDS = [
    "source", "artist", "title", "spotify_artist", "spotify_title",
    "spotify_uri", "spotify_url", "confidence", "status", "osu_beatmapset_url",
]

_SPOTIFY_UNMATCHED_FIELDS = [
    "artist", "title", "reason", "osu_beatmapset_url",
]


def export_songs_csv(songs: list[OsuSong], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_OSU_SONG_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for song in songs:
            writer.writerow(asdict(song))


def _write_spotify_rows(
    matches: list[SpotifyMatch],
    songs_by_key: dict[str, OsuSong],
    path: Path,
    status_filter: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_SPOTIFY_MATCH_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for match in matches:
            if match.status != status_filter:
                continue
            song = songs_by_key.get(match.osu_song_key)
            writer.writerow({
                "source": song.source if song else "",
                "artist": song.artist if song else "",
                "title": song.title if song else "",
                "spotify_artist": match.matched_artist,
                "spotify_title": match.matched_title,
                "spotify_uri": match.spotify_uri,
                "spotify_url": match.spotify_url,
                "confidence": match.confidence,
                "status": match.status,
                "osu_beatmapset_url": song.osu_beatmapset_url if song else "",
            })


def export_matches_csv(
    matches: list[SpotifyMatch],
    songs_by_key: dict[str, OsuSong],
    path: Path,
) -> None:
    _write_spotify_rows(matches, songs_by_key, path, "matched")


def export_review_csv(
    matches: list[SpotifyMatch],
    songs_by_key: dict[str, OsuSong],
    path: Path,
) -> None:
    _write_spotify_rows(matches, songs_by_key, path, "review")


def export_unmatched_csv(
    matches: list[SpotifyMatch],
    songs_by_key: dict[str, OsuSong],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_SPOTIFY_UNMATCHED_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for match in matches:
            if match.status != "unmatched":
                continue
            song = songs_by_key.get(match.osu_song_key)
            writer.writerow({
                "artist": song.artist if song else "",
                "title": song.title if song else "",
                "reason": "no confident match found",
                "osu_beatmapset_url": song.osu_beatmapset_url if song else "",
            })
