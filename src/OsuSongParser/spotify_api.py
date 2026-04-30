import time
from collections import deque

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException

_SCOPES = "playlist-read-private playlist-modify-private playlist-modify-public"
_api_call_count = 0


class SpotifyRateLimiter:
    """
    Rate limiter using a sliding 30-second window to prevent hitting Spotify's API limits.
    Enforces both:
    1. Maximum requests per window (e.g., 30 requests per 30 seconds)
    2. Minimum spacing between requests (e.g., 1 second between consecutive requests)
    """
    def __init__(self, max_requests_per_window: int = 30, window_seconds: int = 30):
        self.max_requests = max_requests_per_window
        self.window = window_seconds
        self.min_delay = window_seconds / max_requests_per_window  # e.g., 30/30 = 1 second
        self.timestamps = deque()  # Stores timestamps of recent requests

    def wait_if_needed(self) -> None:
        """
        Proactively wait to enforce rate limits.
        Ensures:
        - Never exceed max_requests in any window
        - Minimum delay between consecutive requests (even pacing)
        """
        now = time.time()

        # Enforce minimum spacing between consecutive requests
        if self.timestamps:
            time_since_last = now - self.timestamps[-1]
            if time_since_last < self.min_delay:
                sleep_time = self.min_delay - time_since_last
                time.sleep(sleep_time)
                now = time.time()  # Update now after sleeping

        # Remove timestamps outside the current window
        while self.timestamps and self.timestamps[0] < now - self.window:
            self.timestamps.popleft()

        # If at limit, wait until the oldest request ages out of the window
        if len(self.timestamps) >= self.max_requests:
            # Calculate how long to wait for oldest request to exit the window
            sleep_time = (self.timestamps[0] + self.window) - now + 0.1  # +0.1s buffer
            if sleep_time > 0:
                time.sleep(sleep_time)
            # Re-check after sleeping (clean up old timestamps)
            self.wait_if_needed()
            return

        # Record this request timestamp
        self.timestamps.append(time.time())

    def get_current_rate(self) -> tuple[int, int]:
        """Returns (requests_in_window, max_requests) for monitoring."""
        now = time.time()
        # Clean up old timestamps
        while self.timestamps and self.timestamps[0] < now - self.window:
            self.timestamps.popleft()
        return (len(self.timestamps), self.max_requests)


# Global rate limiter instance (will be initialized with config value)
_rate_limiter: SpotifyRateLimiter | None = None


def _get_rate_limiter() -> SpotifyRateLimiter | None:
    """Lazy initialization of rate limiter with config value."""
    global _rate_limiter
    if _rate_limiter is None:
        from OsuSongParser import config
        _rate_limiter = SpotifyRateLimiter(max_requests_per_window=config.SPOTIFY_RATE_LIMIT)
    return _rate_limiter


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
    """
    Search with proactive rate limiting and exponential backoff.
    Uses a sliding 30-second window to prevent hitting Spotify's rate limits.
    """
    global _api_call_count
    rate_limiter = _get_rate_limiter()

    for attempt in range(max_retries):
        try:
            # Exponential backoff on retries (for transient errors)
            if attempt > 0:
                delay = min(2 ** attempt, 10)  # Exponential backoff, max 10s
                time.sleep(delay)

            # Proactive rate limiting - wait if we're at the limit
            rate_limiter.wait_if_needed()

            _api_call_count += 1
            result = sp.search(q=q, type="track", limit=limit)
            return result["tracks"]["items"] if result and result.get("tracks") else []

        except SpotifyException as e:
            if e.http_status == 429:  # Rate limited (shouldn't happen with proactive limiting)
                # Respect Retry-After header + add buffer for safety
                retry_after = int(e.headers.get("Retry-After", 5)) + 5
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
    rate_limiter = _get_rate_limiter()
    offset = 0
    while True:
        rate_limiter.wait_if_needed()
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
    rate_limiter = _get_rate_limiter()
    existing_id = find_playlist(sp, name)
    if existing_id:
        return existing_id, False
    rate_limiter.wait_if_needed()
    playlist = sp.current_user_playlist_create(
        name=name,
        public=public,
        description=description,
    )
    return playlist["id"], True


def get_playlist_track_uris(sp: Spotify, playlist_id: str) -> set[str]:
    """Return the set of track URIs already in a playlist."""
    rate_limiter = _get_rate_limiter()
    uris: set[str] = set()
    offset = 0
    while True:
        rate_limiter.wait_if_needed()
        page = sp.playlist_items(playlist_id, fields="items(track(uri)),next", limit=100, offset=offset, additional_types=("track",))
        for item in page["items"]:
            track = item.get("track")
            if track and track.get("uri"):
                uris.add(track["uri"])
        if page["next"] is None:
            return uris
        offset += len(page["items"])


def add_tracks(sp: Spotify, playlist_id: str, uris: list[str]) -> None:
    """Add tracks to a playlist one at a time, respecting the configured rate limit."""
    rate_limiter = _get_rate_limiter()
    for uri in uris:
        rate_limiter.wait_if_needed()
        sp.playlist_add_items(playlist_id, [uri])


def get_api_call_count() -> int:
    """Return the total number of Spotify API search calls made."""
    return _api_call_count


def reset_api_call_count() -> None:
    """Reset the API call counter to zero."""
    global _api_call_count
    _api_call_count = 0
