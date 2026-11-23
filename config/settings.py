import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(BASE_DIR / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "gemini-3.1-flash-lite"
)

DATABASE_PATH = BASE_DIR / "database" / "northwind.sqlite"

MAX_SQL_ROWS = int(os.getenv("MAX_SQL_ROWS", "500"))

MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", "2"))