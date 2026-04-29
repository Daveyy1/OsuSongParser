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


def create_playlist(
    sp: Spotify,
    name: str,
    public: bool = False,
    description: str = "Generated from osu! beatmaps.",
) -> str:
    """Create a Spotify playlist and return its ID."""
    playlist = sp.current_user_playlist_create(
        name=name,
        public=public,
        description=description,
    )
    return playlist["id"]


def add_tracks(sp: Spotify, playlist_id: str, uris: list[str]) -> None:
    """Add tracks to a playlist in batches of 100 (Spotify API limit)."""
    for i in range(0, len(uris), 100):
        sp.playlist_add_items(playlist_id, uris[i : i + 100])
