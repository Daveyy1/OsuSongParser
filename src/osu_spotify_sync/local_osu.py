from pathlib import Path

from osu_spotify_sync.models import OsuSong


def _parse_osu_file(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_section: str | None = None
    target_sections = {"[General]", "[Metadata]"}

    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return fields

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped
            continue
        if current_section not in target_sections:
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            fields[key.strip()] = value.strip()

    return fields


def _build_song(fields: dict[str, str]) -> OsuSong | None:
    title_unicode = fields.get("TitleUnicode", "").strip()
    title_ascii = fields.get("Title", "").strip()
    artist_unicode = fields.get("ArtistUnicode", "").strip()
    artist_ascii = fields.get("Artist", "").strip()

    primary_title = title_unicode or title_ascii
    primary_artist = artist_unicode or artist_ascii

    if not primary_title or not primary_artist:
        return None

    def parse_id(raw: str) -> int | None:
        try:
            value = int(raw)
            return None if value == -1 else value
        except (ValueError, TypeError):
            return None

    beatmapset_id = parse_id(fields.get("BeatmapSetID", ""))
    beatmap_id = parse_id(fields.get("BeatmapID", ""))

    return OsuSong(
        source="local",
        artist=primary_artist,
        title=primary_title,
        artist_romanized=artist_ascii if artist_ascii != primary_artist else None,
        title_romanized=title_ascii if title_ascii != primary_title else None,
        beatmapset_id=beatmapset_id,
        beatmap_id=beatmap_id,
        audio_filename=fields.get("AudioFilename") or None,
        creator=fields.get("Creator") or None,
        difficulty=fields.get("Version") or None,
        tags=fields.get("Tags") or None,
        osu_beatmapset_url=(
            f"https://osu.ppy.sh/beatmapsets/{beatmapset_id}" if beatmapset_id else None
        ),
        osu_beatmap_url=(
            f"https://osu.ppy.sh/beatmaps/{beatmap_id}" if beatmap_id else None
        ),
    )


def _dedup_key(song: OsuSong) -> str:
    if song.beatmapset_id is not None:
        return f"id:{song.beatmapset_id}"
    return f"name:{song.artist.casefold().strip()}|{song.title.casefold().strip()}"


def scan_local(songs_path: Path) -> list[OsuSong]:
    """Return one OsuSong per unique beatmapset found under songs_path."""
    seen: set[str] = set()
    results: list[OsuSong] = []

    for osu_file in sorted(songs_path.rglob("*.osu")):
        fields = _parse_osu_file(osu_file)
        song = _build_song(fields)
        if song is None:
            continue
        key = _dedup_key(song)
        if key in seen:
            continue
        seen.add(key)
        results.append(song)

    return results
