from pathlib import Path
from typing import Optional

from osu_spotify_sync.local_osu import scan_local as _scan
from osu_spotify_sync.export import export_songs_csv, export_songs_json

import typer
from rich.console import Console

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
    user: str = typer.Option(..., "--user", help="osu! username (@name) or numeric user ID"),
    type_: str = typer.Option(
        ..., "--type",
        help="recent | best | firsts | favourite | most_played",
    ),
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
) -> None:
    """Fetch osu! activity from the API and export to CSV."""
    console.print("[yellow]fetch-osu not implemented yet.[/yellow]")
    raise typer.Exit(1)


@app.command("match-spotify")
def match_spotify(
    input_: Path = typer.Option(..., "--input", help="osu! songs CSV produced by scan-local or fetch-osu"),
    out: Path = typer.Option(Path("exports/spotify_matches.csv"), "--out", help="Matches output CSV path"),
    unmatched_out: Path = typer.Option(
        Path("exports/spotify_unmatched.csv"), "--unmatched-out", help="Unmatched output CSV path"
    ),
) -> None:
    """Match osu! songs against Spotify and produce matched/unmatched CSVs."""
    console.print("[yellow]match-spotify not implemented yet.[/yellow]")
    raise typer.Exit(1)


@app.command("create-playlist")
def create_playlist(
    matches: Path = typer.Option(..., "--matches", help="Spotify matches CSV"),
    playlist_name: str = typer.Option("osu! imports", "--playlist-name", help="Name for the Spotify playlist"),
    private: bool = typer.Option(False, "--private/--public", help="Create playlist as private"),
) -> None:
    """Create a Spotify playlist from high-confidence matched tracks."""
    console.print("[yellow]create-playlist not implemented yet.[/yellow]")
    raise typer.Exit(1)
