import time

from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

_SCOPES = "playlist-modify-private playlist-modify-public"
_MAX_RETRIES = 5


def get_client(client_id: str, client_secret: str, redirect_uri: str) -> Spotify:
    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=_SCOPES,
        show_dialog=True,
    )
    return Spotify(auth_manager=auth)


def _search(sp: Spotify, q: str, limit: int = 5) -> list[dict]:
    """Execute one Spotify search query, retrying up to _MAX_RETRIES times on rate limit."""
    for attempt in range(_MAX_RETRIES):
        try:
            return sp.search(q=q, type="track", limit=limit)["tracks"]["items"]
        except SpotifyException as exc:
            if exc.http_status != 429:
                raise
            # Honour Retry-After if present, otherwise use exponential backoff
            wait = int((exc.headers or {}).get("Retry-After", 2 ** attempt))
            time.sleep(wait)
    return []


def search_track(sp: Spotify, title: str, artist: str) -> list[dict]:
    """Search for a track using a strict query first, falling back to a broad query."""
    tracks = _search(sp, f'track:"{title}" artist:"{artist}"')
    if not tracks:
        tracks = _search(sp, f"{artist} {title}")
    return tracks


def find_playlist(sp: Spotify, name: str) -> str | None:
    """Return the ID of the first user playlist matching name, or None."""
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        for item in page["items"]:
            if item["name"] == name:
                return item["id"]
        if page["next"] is None:
            return None
        offset += len(page["items"])


def get_or_create_playlist(
    sp: Spotify,
    name: str,
    public: bool = False,
    description: str = "Generated from osu! beatmaps.",
) -> tuple[str, bool]:
    """Return (playlist_id, created) — reuses an existing playlist if found."""
    existing_id = find_playlist(sp, name)
    if existing_id:
        return existing_id, False
    playlist = sp.current_user_playlist_create(
        name=name,
        public=public,
        description=description,
    )
    return playlist["id"], True


def get_playlist_track_uris(sp: Spotify, playlist_id: str) -> set[str]:
    """Return the set of track URIs already in a playlist."""
    uris: set[str] = set()
    offset = 0
    while True:
        page = sp.playlist_tracks(playlist_id, fields="items(track(uri)),next", limit=100, offset=offset)
        for item in page["items"]:
            track = item.get("track")
            if track and track.get("uri"):
                uris.add(track["uri"])
        if page["next"] is None:
            return uris
        offset += len(page["items"])


def add_tracks(sp: Spotify, playlist_id: str, uris: list[str]) -> None:
    """Add tracks to a playlist in batches of 25 (Spotify API limit)."""
    for i in range(0, len(uris), 25):
        sp.playlist_add_items(playlist_id, uris[i : i + 25])
