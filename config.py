import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]

_default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscriptions.db")
DATABASE_PATH: str = os.getenv("DATABASE_PATH") or _default_db

SCRAPE_HOUR: int = int(os.getenv("SCRAPE_HOUR", "4"))
SCRAPE_MINUTE: int = int(os.getenv("SCRAPE_MINUTE", "0"))
TIMEZONE = ZoneInfo("Africa/Johannesburg")
BASE_URL: str = "https://www.onedayonly.co.za"
