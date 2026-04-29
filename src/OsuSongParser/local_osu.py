from pathlib import Path

from OsuSongParser.models import OsuSong


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


def _looks_like_osu_file(text: str) -> bool:
    """Quick check if file content appears to be an osu beatmap."""
    return (
        "osu file format" in text[:100].lower()
        and "[Metadata]" in text
        and "BeatmapSetID:" in text
    )


def scan_lazer_files(lazer_root: Path) -> list[OsuSong]:
    """
    Scan osu!lazer's hashed files directory for beatmaps.

    Args:
        lazer_root: Path to osu!lazer root (e.g., C:\\Users\\<name>\\AppData\\Roaming\\osu)

    Returns:
        List of unique OsuSong objects, deduplicated by beatmapset_id
    """
    files_dir = lazer_root / "files"

    if not files_dir.exists():
        return []

    seen: set[str] = set()
    results: list[OsuSong] = []

    # Scan all files in the hashed directory
    for file_path in files_dir.rglob("*"):
        if not file_path.is_file():
            continue

        # Try to read as text
        try:
            text = file_path.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            continue

        # Quick check if this looks like a beatmap file
        if not _looks_like_osu_file(text):
            continue

        # Parse the metadata from the text
        fields: dict[str, str] = {}
        current_section: str | None = None
        target_sections = {"[General]", "[Metadata]"}

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

        # Build the song object
        song = _build_song(fields)
        if song is None:
            continue

        # Deduplicate
        key = _dedup_key(song)
        if key in seen:
            continue
        seen.add(key)

        # Update source to indicate lazer
        song.source = "lazer_local"
        results.append(song)

    return results


"""Return one OsuSong per unique beatmapset found under songs_path."""
def scan_local(songs_path: Path) -> list[OsuSong]:
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
