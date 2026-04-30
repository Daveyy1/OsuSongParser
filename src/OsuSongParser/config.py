from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

OSU_CLIENT_ID: str = os.getenv("OSU_CLIENT_ID", "")
OSU_CLIENT_SECRET: str = os.getenv("OSU_CLIENT_SECRET", "")
OSU_USERNAME: str = os.getenv("OSU_USERNAME", "")
OSU_USER_ID: str = os.getenv("OSU_USER_ID", "")
OSU_RULESET: str = os.getenv("OSU_RULESET", "osu")
OSU_SONGS_PATH: Path = Path(
    os.getenv("OSU_SONGS_PATH", r"C:\Users\Default\AppData\Local\osu!\Songs")
)

SPOTIPY_CLIENT_ID: str = os.getenv("SPOTIPY_CLIENT_ID", "")
SPOTIPY_CLIENT_SECRET: str = os.getenv("SPOTIPY_CLIENT_SECRET", "")
SPOTIPY_REDIRECT_URI: str = os.getenv(
    "SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback"
)
SPOTIFY_RATE_LIMIT: int = int(os.getenv("SPOTIFY_RATE_LIMIT", "30"))
