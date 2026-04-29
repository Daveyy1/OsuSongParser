import time

import requests

from osu_spotify_sync.models import OsuSong

_BASE_URL = "https://osu.ppy.sh/api/v2"
_TOKEN_URL = "https://osu.ppy.sh/oauth/token"

# Hard API caps per score type (single-request endpoints)
SCORE_API_CAPS: dict[str, int] = {"recent": 50, "best": 100, "firsts": 100}

# Beatmapset types that use the paginated /beatmapsets/{type} endpoint
BEATMAPSET_TYPES = {"favourite", "most_played", "ranked", "loved"}

_BEATMAPSET_PAGE_SIZE = 100


class OsuApiClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def _ensure_token(self) -> None:
        if self._token and time.monotonic() < self._token_expires_at:
            return
        resp = self._session.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
                "scope": "public",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.monotonic() + data["expires_in"] - 60
        self._session.headers.update({"Authorization": f"Bearer {self._token}"})

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        self._ensure_token()
        resp = self._session.get(f"{_BASE_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_user(self, user: str, mode: str = "osu") -> dict:
        return self._get(f"/users/{user}/{mode}")

    def get_scores(
        self,
        user: str,
        type_: str,
        mode: str = "osu",
        limit: int = 100,
    ) -> list[dict]:
        api_cap = SCORE_API_CAPS.get(type_, 100)
        params: dict = {"mode": mode, "limit": min(limit, api_cap)}
        if type_ == "recent":
            params["include_fails"] = 1
        result = self._get(f"/users/{user}/scores/{type_}", params=params)
        return result if isinstance(result, list) else []

    def get_beatmapsets(
        self,
        user: str,
        type_: str,
        limit: int = 500,
    ) -> list[dict]:
        results: list[dict] = []
        offset = 0
        while len(results) < limit:
            fetch = min(_BEATMAPSET_PAGE_SIZE, limit - len(results))
            page = self._get(
                f"/users/{user}/beatmapsets/{type_}",
                params={"limit": fetch, "offset": offset},
            )
            if not isinstance(page, list) or not page:
                break
            results.extend(page)
            if len(page) < fetch:
                break
            offset += len(page)
        return results


# --- Response converters ---

def _build_song(
    beatmapset: dict,
    source: str,
    beatmap: dict | None = None,
) -> OsuSong | None:
    artist_unicode = beatmapset.get("artist_unicode", "").strip()
    artist_ascii = beatmapset.get("artist", "").strip()
    title_unicode = beatmapset.get("title_unicode", "").strip()
    title_ascii = beatmapset.get("title", "").strip()

    primary_artist = artist_unicode or artist_ascii
    primary_title = title_unicode or title_ascii

    if not primary_artist or not primary_title:
        return None

    beatmapset_id: int | None = beatmapset.get("id")
    beatmap_id: int | None = beatmap.get("id") if beatmap else None

    return OsuSong(
        source=source,
        artist=primary_artist,
        title=primary_title,
        artist_romanized=artist_ascii if artist_ascii != primary_artist else None,
        title_romanized=title_ascii if title_ascii != primary_title else None,
        beatmapset_id=beatmapset_id,
        beatmap_id=beatmap_id,
        audio_filename=None,
        creator=beatmapset.get("creator") or None,
        difficulty=beatmap.get("version") if beatmap else None,
        tags=beatmapset.get("tags") or None,
        osu_beatmapset_url=(
            f"https://osu.ppy.sh/beatmapsets/{beatmapset_id}" if beatmapset_id else None
        ),
        osu_beatmap_url=(
            f"https://osu.ppy.sh/beatmaps/{beatmap_id}" if beatmap_id else None
        ),
    )


def _dedup(songs: list[OsuSong]) -> list[OsuSong]:
    seen: set[int] = set()
    out: list[OsuSong] = []
    for song in songs:
        if song.beatmapset_id is not None:
            if song.beatmapset_id in seen:
                continue
            seen.add(song.beatmapset_id)
        out.append(song)
    return out


def songs_from_scores(scores: list[dict], source: str) -> list[OsuSong]:
    raw = [
        _build_song(s.get("beatmapset", {}), source, s.get("beatmap"))
        for s in scores
    ]
    return _dedup([s for s in raw if s is not None])


def songs_from_most_played(items: list[dict]) -> list[OsuSong]:
    raw = []
    for item in items:
        beatmap = item.get("beatmap", {})
        beatmapset = beatmap.get("beatmapset", {})
        song = _build_song(beatmapset, "osu_api_most_played", beatmap)
        if song is not None:
            raw.append(song)
    return _dedup(raw)


def songs_from_beatmapsets(items: list[dict], source: str) -> list[OsuSong]:
    raw = [_build_song(item, source) for item in items]
    return _dedup([s for s in raw if s is not None])
