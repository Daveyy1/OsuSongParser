import time

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException

_SCOPES = "playlist-read-private playlist-modify-private playlist-modify-public"
_api_call_count = 0


def get_client(client_id: str, client_secret: str, redirect_uri: str) -> Spotify:
    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=_SCOPES,
        show_dialog=True,
    )
    return Spotify(auth_manager=auth)


def _search(sp: Spotify, q: str, limit: int = 5, max_retries: int = 3) -> list[dict]:
    """Search with adaptive rate limiting and exponential backoff."""
    global _api_call_count

    for attempt in range(max_retries):
        try:
            # Adaptive delay: minimal on first attempt, exponential backoff on retries
            if attempt > 0:
                delay = min(2 ** attempt, 10)  # Exponential backoff, max 10s
                time.sleep(delay)
            else:
                time.sleep(0.2)  # Minimal delay for first attempt

            _api_call_count += 1
            result = sp.search(q=q, type="track", limit=limit)
            return result["tracks"]["items"] if result and result.get("tracks") else []

        except SpotifyException as e:
            if e.http_status == 429:  # Rate limited
                retry_after = int(e.headers.get("Retry-After", 5))
                if attempt < max_retries - 1:
                    time.sleep(retry_after)
                    continue
            raise

    return []


def search_track(sp: Spotify, title: str, artist: str) -> list[dict]:
    """Search Spotify with strict query only."""
    return _search(sp, f'track:"{title}" artist:"{artist}"')


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
        page = sp.playlist_items(playlist_id, fields="items(track(uri)),next", limit=100, offset=offset, additional_types=("track",))
        for item in page["items"]:
            track = item.get("track")
            if track and track.get("uri"):
                uris.add(track["uri"])
        if page["next"] is None:
            return uris
        offset += len(page["items"])


def add_tracks(sp: Spotify, playlist_id: str, uris: list[str]) -> None:
    """Add tracks to a playlist in batches of 25 (To not get rate-limited immediately by Spotify)."""
    for i in range(0, len(uris), 25):
        sp.playlist_add_items(playlist_id, uris[i : i + 25])


def get_api_call_count() -> int:
    """Return the total number of Spotify API search calls made."""
    return _api_call_count


def reset_api_call_count() -> None:
    """Reset the API call counter to zero."""
    global _api_call_count
    _api_call_count = 0
