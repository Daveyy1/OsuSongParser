from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

_SCOPES = "playlist-modify-private playlist-modify-public"


def get_client(client_id: str, client_secret: str, redirect_uri: str) -> Spotify:
    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=_SCOPES,
    )
    return Spotify(auth_manager=auth)


def search_track(
    sp: Spotify,
    title: str,
    artist: str,
) -> list[dict]:
    """Search Spotify for a track. Tries strict query first, then broad fallback."""
    strict = f'track:"{title}" artist:"{artist}"'
    results = sp.search(q=strict, type="track", limit=5)
    tracks = results["tracks"]["items"]

    if not tracks:
        broad = f"{artist} {title}"
        results = sp.search(q=broad, type="track", limit=5)
        tracks = results["tracks"]["items"]

    return tracks


def create_playlist(
    sp: Spotify,
    name: str,
    public: bool = False,
    description: str = "Generated from osu! beatmaps.",
) -> str:
    """Create a Spotify playlist and return its ID."""
    user_id = sp.current_user()["id"]
    playlist = sp.user_playlist_create(
        user=user_id,
        name=name,
        public=public,
        description=description,
    )
    return playlist["id"]


def add_tracks(sp: Spotify, playlist_id: str, uris: list[str]) -> None:
    """Add tracks to a playlist in batches of 100 (Spotify API limit)."""
    for i in range(0, len(uris), 100):
        sp.playlist_add_items(playlist_id, uris[i : i + 100])
