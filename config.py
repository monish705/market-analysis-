import os
from pathlib import Path

from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "pyramid_scans.sqlite3"

CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama3.1-70b")
CEREBRAS_BASE_URL = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

POLYMARKET_GAMMA_URL = os.getenv(
    "POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com"
)
POLYMARKET_CLOB_URL = os.getenv(
    "POLYMARKET_CLOB_URL", "https://clob.polymarket.com"
)

HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.25"))
POLYMARKET_MAX_ATTEMPTS = int(os.getenv("POLYMARKET_MAX_ATTEMPTS", "3"))
POLYMARKET_PUBLIC_DNS_FALLBACK = (
    os.getenv("POLYMARKET_PUBLIC_DNS_FALLBACK", "true").lower() == "true"
)
POLYMARKET_PUBLIC_IPS = [
    ip.strip()
    for ip in os.getenv("POLYMARKET_PUBLIC_IPS", "104.18.34.205,172.64.153.51").split(",")
    if ip.strip()
]

MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "20000"))
MIN_EDGE = float(os.getenv("MIN_EDGE", "0.08"))
MAX_POSITION_FRACTION = float(os.getenv("MAX_POSITION_FRACTION", "0.02"))
DEFAULT_BANKROLL_USD = float(os.getenv("DEFAULT_BANKROLL_USD", "10000"))
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.25"))


def cerebras_client() -> Cerebras | None:
    if not CEREBRAS_KEY:
        return None
    return Cerebras(api_key=CEREBRAS_KEY)
