from pathlib import Path
from typing import Optional
import sys

from rich.console import Console
from rich.prompt import Prompt, Confirm

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

console = Console()


def scan_local_stable() -> Path:
    """Scan local osu! stable Songs folder and export metadata to CSV."""
    console.print("\n[bold cyan]Scanning osu! stable local songs[/bold cyan]")

    default_path = Path.home() / "AppData" / "Local" / "osu!" / "Songs"
    songs_path_str = Prompt.ask(
        "Enter path to osu! Songs folder, if the listed folder is the correct one, press enter.",
        default=str(default_path) if default_path.exists() else ""
    )
    songs_path = Path(songs_path_str)

    if not songs_path.exists():
        console.print(f"[red]Error:[/red] songs path does not exist: {songs_path}")
        sys.exit(1)

    # Count files first for progress bar
    console.print(f"Counting .osu files in [cyan]{songs_path}[/cyan] ...")
    osu_files = list(songs_path.rglob("*.osu"))
    total_files = len(osu_files)
    console.print(f"Found {total_files} .osu files. Scanning...")

    # Scan with progress bar
    from OsuSongParser.local_osu import _parse_osu_file, _build_song, _dedup_key
    from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

    seen: set[str] = set()
    songs: list[OsuSong] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        refresh_per_second=10,
    ) as progress:
        task = progress.add_task("Scanning beatmaps...", total=total_files)
        for osu_file in sorted(osu_files):
            fields = _parse_osu_file(osu_file)
            song = _build_song(fields)
            if song is not None:
                key = _dedup_key(song)
                if key not in seen:
                    seen.add(key)
                    songs.append(song)
            progress.advance(task)

    console.print(f"Found [green]{len(songs)}[/green] unique beatmapsets.")

    out = Path("exports/scans/local_stable_songs.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    export_songs_csv(songs, out)
    console.print(f"CSV written to [cyan]{out}[/cyan]")

    return out


def scan_local_lazer() -> Path:
    """Scan osu!lazer hashed files directory and export metadata to CSV."""
    console.print("\n[bold cyan]Scanning osu! lazer local songs[/bold cyan]")

    default_path = Path.home() / "AppData" / "Roaming" / "osu"
    lazer_root_str = Prompt.ask(
        "Enter path to osu!lazer root folder, if the listed one is the correct one, press enter.",
        default=str(default_path) if default_path.exists() else ""
    )
    lazer_root = Path(lazer_root_str)

    if not lazer_root.exists():
        console.print(f"[red]Error:[/red] lazer root path does not exist: {lazer_root}")
        sys.exit(1)

    files_dir = lazer_root / "files"
    if not files_dir.exists():
        console.print(
            f"[red]Error:[/red] files directory not found at {files_dir}\n"
            f"Make sure you're pointing to the osu!lazer root directory."
        )
        sys.exit(1)

    # Count files first for progress bar
    console.print(f"Counting files in [cyan]{files_dir}[/cyan] ...")
    all_files = [f for f in files_dir.rglob("*") if f.is_file()]
    total_files = len(all_files)
    console.print(f"Found {total_files} files. Scanning...")
    console.print("[yellow]Note:[/yellow] This may take a while as it scans hashed files...")

    # Scan with progress bar
    from OsuSongParser.local_osu import _parse_osu_file, _build_song, _dedup_key
    from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

    seen: set[str] = set()
    songs: list[OsuSong] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        refresh_per_second=10,
    ) as progress:
        task = progress.add_task("Scanning lazer files...", total=total_files)
        for file_path in all_files:
            try:
                fields = _parse_osu_file(file_path)
                song = _build_song(fields)
                if song is not None:
                    key = _dedup_key(song)
                    if key not in seen:
                        seen.add(key)
                        songs.append(song)
            except Exception:
                # Skip files that can't be parsed
                pass
            progress.advance(task)

    console.print(f"Found [green]{len(songs)}[/green] unique beatmapsets.")

    out = Path("exports/scans/local_lazer_songs.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    export_songs_csv(songs, out)
    console.print(f"CSV written to [cyan]{out}[/cyan]")

    return out


def fetch_from_osu_api(type_: str) -> Path:
    """Fetch osu! activity from the API and export to CSV."""
    from OsuSongParser import config

    console.print(f"\n[bold cyan]Fetching {type_} from osu! API[/bold cyan]")

    if not config.OSU_CLIENT_ID or not config.OSU_CLIENT_SECRET:
        console.print("[red]Error:[/red] OSU_CLIENT_ID and OSU_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    user = config.OSU_USER_ID
    if not user:
        console.print("[red]Error:[/red] OSU_USER_ID must be set in .env")
        sys.exit(1)

    limit = 500
    mode = "osu"
    out = Path(f"exports/scans/{type_}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
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
                    f"[yellow]Result count hit the limit of {limit}.[/yellow]"
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
                    f"[yellow]Result count hit the limit of {limit}.[/yellow]"
                )
    except Exception as exc:
        console.print(f"[red]API error:[/red] {exc}")
        sys.exit(1)

    export_songs_csv(songs, out)
    console.print(f"CSV written to [cyan]{out}[/cyan]")

    return out


def match_with_spotify(input_: Path) -> tuple[Path, Path, Path]:
    """Match osu! songs against Spotify and produce matched/review/unmatched CSVs."""
    console.print(f"\n[bold cyan]Matching songs with Spotify[/bold cyan]")
    import csv
    import json
    from OsuSongParser import config
    from OsuSongParser.models import SpotifyMatch

    # Generate output file paths based on input file name
    input_stem = input_.stem
    out = Path(f"exports/spotify/matched/{input_stem}_spotify_matches.csv")
    review_out = Path(f"exports/spotify/review/{input_stem}_spotify_review.csv")
    unmatched_out = Path(f"exports/spotify/unmatched/{input_stem}_spotify_unmatched.csv")

    if not config.SPOTIPY_CLIENT_ID or not config.SPOTIPY_CLIENT_SECRET:
        console.print("[red]Error:[/red] SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    if not input_.exists():
        console.print(f"[red]Error:[/red] input file not found: {input_}")
        sys.exit(1)

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
        sys.exit(1)

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

    matches: list = []
    cache_hits = 0
    CACHE_SAVE_INTERVAL = 50

    def _save_cache() -> None:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    reset_api_call_count()

    console.print(f"Matching [green]{len(songs)}[/green] songs against Spotify...")
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
            if (idx + 1) % CACHE_SAVE_INTERVAL == 0:
                _save_cache()
        matches.append(match)
        label = f"{song.artist} - {song.title}"
        console.print(f"  [{idx+1}/{len(songs)}] {label[:70]}")

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

    return out, review_out, unmatched_out


_PLAYLIST_NAMES: dict[str, str] = {
    "osu_api_most_played": "MostPlayedOsuMaps",
    "osu_api_best": "BestOsuMaps",
    "osu_api_recent": "RecentOsuMaps",
    "local": "LocalOsuMaps",
}


def add_to_spotify_playlist(matches: Optional[Path], review: Optional[Path]) -> None:
    """Create a Spotify playlist from matched and/or review songs."""
    console.print(f"\n[bold cyan]Adding songs to Spotify playlist[/bold cyan]")
    private = True
    import csv as _csv
    from OsuSongParser import config
    from OsuSongParser.spotify_api import (
        get_or_create_playlist as _get_or_create_playlist,
        get_playlist_track_uris as _get_playlist_track_uris,
        add_tracks as _add_tracks,
    )

    if not matches and not review:
        console.print("[red]Error:[/red] provide at least one matched/review CSV file")
        sys.exit(1)

    if not config.SPOTIPY_CLIENT_ID or not config.SPOTIPY_CLIENT_SECRET:
        console.print("[red]Error:[/red] SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set in .env")
        sys.exit(1)

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
            sys.exit(1)
        uris, src = read_uris(path)
        all_uris.extend(uris)
        if not source:
            source = src

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_uris = [u for u in all_uris if not (u in seen or seen.add(u))]  # type: ignore[func-returns-value]

    if not unique_uris:
        console.print("[yellow]No Spotify URIs found in the provided files — nothing to add.[/yellow]")
        return

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
            return

        from OsuSongParser.spotify_api import _get_rate_limiter

        rate_limiter = _get_rate_limiter()

        console.print(f"Adding [green]{len(new_uris)}[/green] tracks to [cyan]{playlist_name}[/cyan]...")
        for idx, uri in enumerate(new_uris):
            rate_limiter.wait_if_needed()
            sp.playlist_add_items(playlist_id, [uri])
            console.print(f"  [{idx+1}/{len(new_uris)}] added")
    except Exception as exc:
        console.print(f"[red]Spotify error:[/red] {exc}")
        sys.exit(1)

    playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    console.print(f"[green]Done![/green] Playlist: [cyan]{playlist_url}[/cyan]")


def scan_workflow() -> None:
    """Workflow for scanning osu! songs."""
    # Ask if stable or lazer
    osu_version = Prompt.ask(
        "Are you playing osu! stable or osu! lazer?",
        choices=["s", "l"],
        default="l",
        show_default=False
    ).lower()

    # Ask if local or account-linked
    scan_type = Prompt.ask(
        "Do you want to scan your [cyan]local maps[/cyan] or the ones [cyan]linked to your account[/cyan]?",
        choices=["local", "account"],
        default="local",
        show_default=False
    )

    # Process based on scan type
    if scan_type == "local":
        if osu_version == "s":
            output_csv = scan_local_stable()
        else:
            output_csv = scan_local_lazer()
    else:
        # Ask which type of account data
        api_type_input = Prompt.ask(
            "Which type do you want? [cyan]b[/cyan]est scores, [cyan]r[/cyan]ecent, [cyan]f[/cyan]avorites, or [cyan]m[/cyan]ost played?",
            choices=["b", "r", "f", "m"],
            default="b",
            show_default=False
        ).lower()

        # Map input to API type
        type_map = {
            "b": "best",
            "r": "recent",
            "f": "favourite",
            "m": "most_played"
        }
        api_type = type_map[api_type_input]
        output_csv = fetch_from_osu_api(api_type)

    console.print(f"\n[green]Scan complete![/green]")
    console.print(f"Output CSV: [cyan]{output_csv}[/cyan]")

    # Ask if they want to continue with matching
    if Confirm.ask("\nDo you want to match these songs with Spotify now?", default=True, show_default=False):
        matched_csv, review_csv, unmatched_csv = match_with_spotify(output_csv)

        # Ask if they want to add to playlist
        if Confirm.ask("\nDo you want to add the matched songs to your Spotify playlist?", default=True, show_default=False):
            add_to_spotify_playlist(matched_csv, review_csv)
            console.print("\n[green]All done! Enjoy your playlist![/green]")
        else:
            console.print("\n[green]All done! Your matched songs are saved.[/green]")
    else:
        console.print("\n[green]All done! You can match these songs later.[/green]")


def match_workflow() -> None:
    """Workflow for matching existing osu! song CSVs with Spotify."""
    scans_dir = Path("exports/scans")
    if not scans_dir.exists():
        console.print("[red]Error:[/red] No scans directory found. Please scan some songs first.")
        return

    available_csvs = list(scans_dir.glob("*.csv"))

    if not available_csvs:
        console.print("[yellow]No osu! song CSV files found. Please scan some songs first.[/yellow]")
        return

    console.print("\n[bold cyan]Available osu! song files:[/bold cyan]")
    for idx, csv_file in enumerate(available_csvs, 1):
        console.print(f"  {idx}. {csv_file.name}")

    # Ask which file(s) to match
    choice = Prompt.ask(
        "\nWhich file do you want to match with Spotify? (enter number or 'all')",
        default="1",
        show_default=False
    )

    files_to_process: list[Path] = []
    if choice.lower() == "all":
        files_to_process = available_csvs
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(available_csvs):
                files_to_process = [available_csvs[idx]]
            else:
                console.print("[red]Invalid selection[/red]")
                return
        except ValueError:
            console.print("[red]Invalid input[/red]")
            return

    # Match with Spotify
    matched_files: list[tuple[Path, Path, Path]] = []
    for csv_file in files_to_process:
        console.print(f"\n[bold]Matching {csv_file.name}[/bold]")
        matched_csv, review_csv, unmatched_csv = match_with_spotify(csv_file)
        matched_files.append((matched_csv, review_csv, unmatched_csv))

    console.print(f"\n[green]Matching complete![/green]")

    # Ask if they want to add to playlist
    if Confirm.ask("\nDo you want to add the matched songs to your Spotify playlist?", default=True, show_default=False):
        for matched_csv, review_csv, unmatched_csv in matched_files:
            add_to_spotify_playlist(matched_csv, review_csv)
        console.print("\n[green]All done! Enjoy your playlists![/green]")
    else:
        console.print("\n[green]All done! Your matched songs are saved.[/green]")


def playlist_workflow() -> None:
    """Workflow for adding matched songs to Spotify playlists."""
    matched_dir = Path("exports/spotify/matched")
    review_dir = Path("exports/spotify/review")
    if not matched_dir.exists():
        console.print("[red]Error:[/red] No matched files directory found. Please match some songs first.")
        return

    matched_csvs = list(matched_dir.glob("*.csv"))

    if not matched_csvs:
        console.print("[yellow]No matched Spotify files found. Please match some songs first.[/yellow]")
        return

    console.print("\n[bold cyan]Available matched files:[/bold cyan]")
    for idx, csv_file in enumerate(matched_csvs, 1):
        review_file = review_dir / csv_file.name.replace("_matches.csv", "_review.csv")
        console.print(f"  {idx}. {csv_file.name}")
        if review_file.exists():
            console.print(f"      (with review file: {review_file.name})")

    # Ask which file(s) to add
    choice = Prompt.ask(
        "\nWhich matched file do you want to add to a playlist? (enter number or 'all')",
        default="1",
        show_default=False
    )

    files_to_process: list[Path] = []
    if choice.lower() == "all":
        files_to_process = matched_csvs
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(matched_csvs):
                files_to_process = [matched_csvs[idx]]
            else:
                console.print("[red]Invalid selection[/red]")
                return
        except ValueError:
            console.print("[red]Invalid input[/red]")
            return

    # Add to playlist
    for matched_csv in files_to_process:
        review_csv = review_dir / matched_csv.name.replace("_matches.csv", "_review.csv")
        review_csv = review_csv if review_csv.exists() else None
        add_to_spotify_playlist(matched_csv, review_csv)

    console.print("\n[green]All done! Enjoy your playlists![/green]")


def app() -> None:
    """Main interactive CLI application."""
    console.print("\n[bold magenta]osu! Song Exporter + Spotify Playlist Sync[/bold magenta]\n")

    # Ask what the user wants to do
    action = Prompt.ask(
        "What would you like to do?\n"
        "  [cyan]s[/cyan] - Scan osu! songs (local or from API)\n"
        "  [cyan]m[/cyan] - Match saved songs with Spotify\n"
        "  [cyan]p[/cyan] - Add matched songs to Spotify playlist\n"
        "Choose an option",
        choices=["s", "m", "p"],
        default="s",
        show_default=False
    ).lower()

    if action == "s":
        scan_workflow()
    elif action == "m":
        match_workflow()
    elif action == "p":
        playlist_workflow()
