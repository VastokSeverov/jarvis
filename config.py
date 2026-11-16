import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()


def _req(name):
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing {name} in .env")
    return value


BOT_TOKEN = _req("BOT_TOKEN")
OWNER_ID = int(_req("OWNER_ID"))
DATABASE_URL = _req("DATABASE_URL")
OLLAMA_MODEL = _req("OLLAMA_MODEL")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
TZ = ZoneInfo(os.getenv("TZ_NAME", "Asia/Tashkent"))
BRIEFING_HOUR = int(os.getenv("BRIEFING_HOUR", "8"))
REMIND_HOUR = int(os.getenv("REMIND_HOUR", "9"))
