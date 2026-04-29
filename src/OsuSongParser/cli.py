from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from OsuSongParser.export import (
    export_matches_csv,
    export_review_csv,
    export_songs_csv,
    export_songs_json,
    export_unmatched_csv,
)
from OsuSongParser.local_osu import scan_local as _scan, scan_lazer_files as _scan_lazer
from OsuSongParser.matching import match_songs, song_key
from OsuSongParser.models import OsuSong
from OsuSongParser.osu_api import (
    BEATMAPSET_TYPES,
    SCORE_API_CAPS,
    OsuApiClient,
    songs_from_beatmapsets,
    songs_from_most_played,
    songs_from_scores,
)
from OsuSongParser.spotify_api import get_client, get_api_call_count, reset_api_call_count

app = typer.Typer(help="osu! Song Exporter + Spotify Playlist Sync")
console = Console()


"""Scan local osu! Songs folder and export metadata to CSV."""
@app.command("scan-local")
def scan_local(
    songs_path: Path = typer.Option(..., "--songs-path", help="Path to osu! Songs folder"),
    out: Path = typer.Option(Path("exports/osu_songs.csv"), "--out", help="Output CSV path"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Optional JSON output path"),
) -> None:

    if not songs_path.exists():
        console.print(f"[red]Error:[/red] songs path does not exist: {songs_path}")
        raise typer.Exit(1)

    console.print(f"Scanning [cyan]{songs_path}[/cyan] ...")
    songs = _scan(songs_path)
    console.print(f"Found [green]{len(songs)}[/green] unique beatmapsets.")

    export_songs_csv(songs, out)
    console.print(f"CSV written to [cyan]{out}[/cyan]")

    if json_out:
        export_songs_json(songs, json_out)
        console.print(f"JSON written to [cyan]{json_out}[/cyan]")


"""Scan osu!lazer hashed files directory and export metadata to CSV."""
@app.command("scan-lazer")
def scan_lazer(
    lazer_root: Path = typer.Option(
        ..., "--lazer-root", help="Path to osu!lazer root (e.g., C:\\Users\\<name>\\AppData\\Roaming\\osu)"
    ),
    out: Path = typer.Option(Path("exports/lazer_songs.csv"), "--out", help="Output CSV path"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Optional JSON output path"),
) -> None:

    if not lazer_root.exists():
        console.print(f"[red]Error:[/red] lazer root path does not exist: {lazer_root}")
        raise typer.Exit(1)

    files_dir = lazer_root / "files"
    if not files_dir.exists():
        console.print(
            f"[red]Error:[/red] files directory not found at {files_dir}\n"
            f"Make sure you're pointing to the osu!lazer root directory."
        )
        raise typer.Exit(1)

    console.print(f"Scanning osu!lazer files in [cyan]{files_dir}[/cyan] ...")
    console.print("[yellow]Note:[/yellow] This may take a while as it scans hashed files...")
    songs = _scan_lazer(lazer_root)
    console.print(f"Found [green]{len(songs)}[/green] unique beatmapsets.")

    export_songs_csv(songs, out)
    console.print(f"CSV written to [cyan]{out}[/cyan]")

    if json_out:
        export_songs_json(songs, json_out)
        console.print(f"JSON written to [cyan]{json_out}[/cyan]")


"""Fetch osu! activity from the API and export to CSV."""
@app.command("fetch-osu")
def fetch_osu(
    type_: str = typer.Option(
        ..., "--type",
        help="recent | best | firsts | favourite | most_played",
    ),
    limit: int = typer.Option(500, "--limit", help="Maximum number of results to fetch"),
    mode: str = typer.Option("osu", "--mode", help="Ruleset: osu | taiko | fruits | mania"),
) -> None:
    from OsuSongParser import config

    valid_types = set(SCORE_API_CAPS) | BEATMAPSET_TYPES
    if type_ not in valid_types:
        console.print(f"[red]Error:[/red] unknown type '{type_}'. Choose from: {', '.join(sorted(valid_types))}")
        raise typer.Exit(1)

    if not config.OSU_CLIENT_ID or not config.OSU_CLIENT_SECRET:
        console.print("[red]Error:[/red] OSU_CLIENT_ID and OSU_CLIENT_SECRET must be set in .env")
        raise typer.Exit(1)

    user = config.OSU_USER_ID
    if not user:
        console.print("[red]Error:[/red] OSU_USER_ID must be set in .env")
        raise typer.Exit(1)

    out = Path(f"exports/{type_}.csv")
    client = OsuApiClient(config.OSU_CLIENT_ID, config.OSU_CLIENT_SECRET)

    console.print(f"Fetching [cyan]{type_}[/cyan] for user [cyan]{user}[/cyan] ...")

    try:
        if type_ in SCORE_API_CAPS:
            api_cap = SCORE_API_CAPS[type_]
            raw = client.get_scores(user, type_, mode=mode, limit=limit)
            songs = songs_from_scores(raw, source=f"osu_api_{type_}")
            count = len(songs)
            console.print(
                f"Fetched [green]{count}[/green] unique beatmapsets "
                f"(API cap for '{type_}': {api_cap} scores)."
            )
        elif type_ == "most_played":
            raw = client.get_beatmapsets(user, type_, limit=limit)
            songs = songs_from_most_played(raw)
            count = len(songs)
            console.print(
                f"Fetched [green]{count}[/green] unique beatmapsets "
                f"(limit: {limit})."
            )
            if count >= limit:
                console.print(
                    f"[yellow]Result count hit the limit of {limit}. "
                    f"Pass --limit {limit * 2} if you want more.[/yellow]"
                )
        else:
            raw = client.get_beatmapsets(user, type_, limit=limit)
            songs = songs_from_beatmapsets(raw, source=f"osu_api_{type_}")
            count = len(songs)
            console.print(
                f"Fetched [green]{count}[/green] beatmapsets "
                f"(limit: {limit})."
            )
            if count >= limit:
                console.print(
                    f"[yellow]Result count hit the limit of {limit}. "
                    f"Pass --limit {limit * 2} if you want more.[/yellow]"
                )
    except Exception as exc:
        console.print(f"[red]API error:[/red] {exc}")
        raise typer.Exit(1)

    export_songs_csv(songs, out)
    console.print(f"CSV written to [cyan]{out}[/cyan]")


"""Match osu! songs against Spotify and produce matched/review/unmatched CSVs."""
@app.command("match-spotify")
def match_spotify(
    input_: Path = typer.Option(..., "--input", help="osu! songs CSV from scan-local or fetch-osu"),
    out: Path = typer.Option(Path("exports/spotify_matches.csv"), "--out", help="Matched results CSV"),
    review_out: Path = typer.Option(Path("exports/spotify_review.csv"), "--review-out", help="Review results CSV"),
    unmatched_out: Path = typer.Option(
        Path("exports/spotify_unmatched.csv"), "--unmatched-out", help="Unmatched results CSV"
    ),
) -> None:
    import csv
    import json
    from OsuSongParser import config
    from OsuSongParser.models import SpotifyMatch

    if not config.SPOTIPY_CLIENT_ID or not config.SPOTIPY_CLIENT_SECRET:
        console.print("[red]Error:[/red] SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set in .env")
        raise typer.Exit(1)

    if not input_.exists():
        console.print(f"[red]Error:[/red] input file not found: {input_}")
        raise typer.Exit(1)

    with input_.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        songs: list[OsuSong] = []
        for row in reader:
            songs.append(OsuSong(
                source=row.get("source", ""),
                artist=row.get("artist", ""),
                title=row.get("title", ""),
                artist_romanized=row.get("artist_romanized") or None,
                title_romanized=row.get("title_romanized") or None,
                beatmapset_id=int(row["beatmapset_id"]) if row.get("beatmapset_id") else None,
                beatmap_id=int(row["beatmap_id"]) if row.get("beatmap_id") else None,
                audio_filename=row.get("audio_filename") or None,
                creator=row.get("creator") or None,
                difficulty=row.get("difficulty") or None,
                tags=row.get("tags") or None,
                osu_beatmapset_url=row.get("osu_beatmapset_url") or None,
                osu_beatmap_url=row.get("osu_beatmap_url") or None,
            ))

    console.print(f"Loaded [green]{len(songs)}[/green] songs from [cyan]{input_}[/cyan]")
    console.print("Authenticating with Spotify (browser window may open) ...")

    try:
        sp = get_client(
            config.SPOTIPY_CLIENT_ID,
            config.SPOTIPY_CLIENT_SECRET,
            config.SPOTIPY_REDIRECT_URI,
        )
    except Exception as exc:
        console.print(f"[red]Spotify auth error:[/red] {exc}")
        raise typer.Exit(1)

    songs_by_key = {
        (str(s.beatmapset_id) if s.beatmapset_id else f"{s.artist}|{s.title}"): s
        for s in songs
    }

    cache_path = Path("exports/spotify_cache.json")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, dict] = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}

    from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

    matches: list = []
    cache_hits = 0
    CACHE_SAVE_INTERVAL = 50  # Save cache every 50 songs to reduce disk I/O

    def _save_cache() -> None:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    # Reset API call counter at the start of matching
    reset_api_call_count()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Matching against Spotify...", total=len(songs))
        for idx, song in enumerate(songs):
            key = song_key(song)
            if key in cache:
                cached = cache[key]
                match = SpotifyMatch(
                    osu_song_key=key,
                    spotify_track_id=cached.get("spotify_track_id"),
                    spotify_uri=cached.get("spotify_uri"),
                    spotify_url=cached.get("spotify_url"),
                    matched_artist=cached.get("matched_artist"),
                    matched_title=cached.get("matched_title"),
                    confidence=cached.get("confidence", 0.0),
                    status=cached.get("status", "unmatched"),
                )
                cache_hits += 1
            else:
                match = next(match_songs(sp, [song]))
                cache[key] = {
                    "spotify_track_id": match.spotify_track_id,
                    "spotify_uri": match.spotify_uri,
                    "spotify_url": match.spotify_url,
                    "matched_artist": match.matched_artist,
                    "matched_title": match.matched_title,
                    "confidence": match.confidence,
                    "status": match.status,
                }
                # Batch save: only save every N songs to reduce disk I/O
                if (idx + 1) % CACHE_SAVE_INTERVAL == 0:
                    _save_cache()
            matches.append(match)
            progress.advance(task)

    # Final cache save after loop completes
    _save_cache()

    new_lookups = len(matches) - cache_hits
    api_calls = get_api_call_count()
    console.print(
        f"Cache: [cyan]{cache_hits} hits[/cyan], [green]{new_lookups} new lookups[/green] "
        f"(cache saved to [cyan]{cache_path}[/cyan])"
    )
    console.print(f"API calls: [cyan]{api_calls}[/cyan] (avg {api_calls / new_lookups:.1f} per lookup)" if new_lookups > 0 else f"API calls: [cyan]{api_calls}[/cyan]")

    matched = sum(1 for m in matches if m.status == "matched")
    review = sum(1 for m in matches if m.status == "review")
    unmatched = sum(1 for m in matches if m.status == "unmatched")

    console.print(
        f"Results: [green]{matched} matched[/green], "
        f"[yellow]{review} review[/yellow], "
        f"[red]{unmatched} unmatched[/red]"
    )

    export_matches_csv(matches, songs_by_key, out)
    console.print(f"Matched written to [cyan]{out}[/cyan]")

    export_review_csv(matches, songs_by_key, review_out)
    console.print(f"Review written to [cyan]{review_out}[/cyan]")

    export_unmatched_csv(matches, songs_by_key, unmatched_out)
    console.print(f"Unmatched written to [cyan]{unmatched_out}[/cyan]")


_PLAYLIST_NAMES: dict[str, str] = {
    "osu_api_most_played": "MostPlayedOsuMaps",
    "osu_api_best": "BestOsuMaps",
    "osu_api_recent": "RecentOsuMaps",
    "local": "LocalOsuMaps",
}


"""Create a Spotify playlist from matched and/or review songs."""
@app.command("create-playlist")
def create_playlist(
    matches: Optional[Path] = typer.Option(None, "--matches", help="Matched songs CSV (spotify_matches.csv)"),
    review: Optional[Path] = typer.Option(None, "--review", help="Review songs CSV (spotify_review.csv)"),
    private: bool = typer.Option(True, "--private/--public", help="Create as private playlist"),
) -> None:
    import csv as _csv
    from OsuSongParser import config
    from OsuSongParser.spotify_api import (
        get_or_create_playlist as _get_or_create_playlist,
        get_playlist_track_uris as _get_playlist_track_uris,
        add_tracks as _add_tracks,
    )

    if not matches and not review:
        console.print("[red]Error:[/red] provide at least one of --matches or --review")
        raise typer.Exit(1)

    if not config.SPOTIPY_CLIENT_ID or not config.SPOTIPY_CLIENT_SECRET:
        console.print("[red]Error:[/red] SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set in .env")
        raise typer.Exit(1)

    def read_uris(path: Path) -> tuple[list[str], str]:
        """Return (uris, source) from a match/review CSV."""
        uris: list[str] = []
        source = ""
        with path.open(encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                uri = row.get("spotify_uri", "").strip()
                if uri:
                    uris.append(uri)
                if not source:
                    source = row.get("source", "")
        return uris, source

    all_uris: list[str] = []
    source = ""

    for path in filter(None, [matches, review]):
        if not path.exists():
            console.print(f"[red]Error:[/red] file not found: {path}")
            raise typer.Exit(1)
        uris, src = read_uris(path)
        all_uris.extend(uris)
        if not source:
            source = src

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_uris = [u for u in all_uris if not (u in seen or seen.add(u))]  # type: ignore[func-returns-value]

    if not unique_uris:
        console.print("[yellow]No Spotify URIs found in the provided files — nothing to add.[/yellow]")
        raise typer.Exit(0)

    playlist_name = _PLAYLIST_NAMES.get(source, "OsuMaps")
    console.print(f"Looking up playlist [cyan]{playlist_name}[/cyan] ...")
    console.print("Authenticating with Spotify (browser window may open) ...")

    try:
        sp = get_client(config.SPOTIPY_CLIENT_ID, config.SPOTIPY_CLIENT_SECRET, config.SPOTIPY_REDIRECT_URI)
        playlist_id, created = _get_or_create_playlist(sp, playlist_name, public=not private)
        if created:
            console.print(f"Created new playlist [cyan]{playlist_name}[/cyan].")
            new_uris = unique_uris
        else:
            console.print(f"Found existing playlist [cyan]{playlist_name}[/cyan] — checking for duplicates ...")
            existing = _get_playlist_track_uris(sp, playlist_id)
            new_uris = [u for u in unique_uris if u not in existing]
            skipped = len(unique_uris) - len(new_uris)
            if skipped:
                console.print(f"Skipping [yellow]{skipped}[/yellow] tracks already in the playlist.")
        if not new_uris:
            console.print("[yellow]No new tracks to add.[/yellow]")
            raise typer.Exit(0)
        console.print(f"Adding [green]{len(new_uris)}[/green] tracks ...")
        _add_tracks(sp, playlist_id, new_uris)
    except Exception as exc:
        console.print(f"[red]Spotify error:[/red] {exc}")
        raise typer.Exit(1)

    playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    console.print(f"[green]Done![/green] Playlist: [cyan]{playlist_url}[/cyan]")
