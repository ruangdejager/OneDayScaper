import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "subscriptions.db")
SCRAPE_HOUR: int = int(os.getenv("SCRAPE_HOUR", "4"))
SCRAPE_MINUTE: int = int(os.getenv("SCRAPE_MINUTE", "0"))
TIMEZONE = ZoneInfo("Africa/Johannesburg")
BASE_URL: str = "https://www.onedayonly.co.za"
