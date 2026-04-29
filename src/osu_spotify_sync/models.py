from dataclasses import dataclass


@dataclass
class OsuSong:
    source: str  # local | osu_api_recent | osu_api_best | osu_api_favourite | osu_api_most_played
    artist: str
    title: str
    artist_romanized: str | None
    title_romanized: str | None
    beatmapset_id: int | None
    beatmap_id: int | None
    audio_filename: str | None
    creator: str | None
    difficulty: str | None
    tags: str | None
    osu_beatmapset_url: str | None
    osu_beatmap_url: str | None


@dataclass
class SpotifyMatch:
    osu_song_key: str
    spotify_track_id: str | None
    spotify_uri: str | None
    spotify_url: str | None
    matched_artist: str | None
    matched_title: str | None
    confidence: float
    status: str  # matched | review | unmatched
