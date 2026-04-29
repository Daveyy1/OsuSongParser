from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from OsuSongParser.export import (
    export_matches_csv,
    export_songs_csv,
    export_songs_json,
    export_unmatched_csv,
)
from OsuSongParser.local_osu import scan_local as _scan
from OsuSongParser.matching import match_songs
from OsuSongParser.models import OsuSong
from OsuSongParser.osu_api import (
    BEATMAPSET_TYPES,
    SCORE_API_CAPS,
    OsuApiClient,
    songs_from_beatmapsets,
    songs_from_most_played,
    songs_from_scores,
)
from OsuSongParser.spotify_api import get_client

app = typer.Typer(help="osu! Song Exporter + Spotify Playlist Sync")
console = Console()


@app.command("scan-local")
def scan_local(
    songs_path: Path = typer.Option(..., "--songs-path", help="Path to osu! Songs folder"),
    out: Path = typer.Option(Path("exports/osu_songs.csv"), "--out", help="Output CSV path"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Optional JSON output path"),
) -> None:
    """Scan local osu! Songs folder and export metadata to CSV (and optionally JSON)."""

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


@app.command("fetch-osu")
def fetch_osu(
    type_: str = typer.Option(
        ..., "--type",
        help="recent | best | firsts | favourite | most_played",
    ),
    limit: int = typer.Option(500, "--limit", help="Maximum number of results to fetch"),
    mode: str = typer.Option("osu", "--mode", help="Ruleset: osu | taiko | fruits | mania"),
) -> None:
    """Fetch osu! activity from the API and export to CSV."""
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


@app.command("match-spotify")
def match_spotify(
    input_: Path = typer.Option(..., "--input", help="osu! songs CSV from scan-local or fetch-osu"),
    out: Path = typer.Option(Path("exports/spotify_matches.csv"), "--out", help="Matched results CSV"),
    unmatched_out: Path = typer.Option(
        Path("exports/spotify_unmatched.csv"), "--unmatched-out", help="Unmatched results CSV"
    ),
) -> None:
    """Match osu! songs against Spotify and produce matched/review/unmatched CSVs."""
    import csv
    from OsuSongParser import config

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

    console.print("Matching songs against Spotify ...")
    matches = match_songs(sp, songs)

    songs_by_key = {
        (str(s.beatmapset_id) if s.beatmapset_id else f"{s.artist}|{s.title}"): s
        for s in songs
    }

    matched = sum(1 for m in matches if m.status == "matched")
    review = sum(1 for m in matches if m.status == "review")
    unmatched = sum(1 for m in matches if m.status == "unmatched")

    console.print(
        f"Results: [green]{matched} matched[/green], "
        f"[yellow]{review} review[/yellow], "
        f"[red]{unmatched} unmatched[/red]"
    )

    export_matches_csv(matches, songs_by_key, out)
    console.print(f"Matches written to [cyan]{out}[/cyan]")

    export_unmatched_csv(matches, songs_by_key, unmatched_out)
    console.print(f"Unmatched written to [cyan]{unmatched_out}[/cyan]")


@app.command("create-playlist")
def create_playlist(
    matches: Path = typer.Option(..., "--matches", help="Spotify matches CSV"),
    playlist_name: str = typer.Option("osu! imports", "--playlist-name", help="Name for the Spotify playlist"),
    private: bool = typer.Option(False, "--private/--public", help="Create playlist as private"),
) -> None:
    """Create a Spotify playlist from high-confidence matched tracks."""
    console.print("[yellow]create-playlist not implemented yet.[/yellow]")
    raise typer.Exit(1)
