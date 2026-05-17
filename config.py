import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
DB_PATH = os.getenv("STOCKSENSE_DB_PATH", "news.db")
CHROMA_PATH = os.getenv("STOCKSENSE_CHROMA_PATH", ".chroma")
ENABLE_SEMANTIC_DEDUPE = os.getenv("STOCKSENSE_ENABLE_SEMANTIC_DEDUPE", "0") == "1"
SECRET_KEY = os.getenv("STOCKSENSE_SECRET_KEY", "change-this-before-publishing")
AUTH_ENABLED = os.getenv("STOCKSENSE_AUTH_ENABLED", "1") == "1"
ADMIN_USERNAME = os.getenv("STOCKSENSE_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("STOCKSENSE_ADMIN_PASSWORD", "stocksense")
SERVER_REFRESH_SECONDS = int(os.getenv("STOCKSENSE_SERVER_REFRESH_SECONDS", "60"))
SERVER_SCHEDULER_ENABLED = os.getenv("STOCKSENSE_SERVER_SCHEDULER_ENABLED", "1") == "1"
ALERT_WEBHOOK_URL = os.getenv("STOCKSENSE_ALERT_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("STOCKSENSE_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("STOCKSENSE_TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = os.getenv("STOCKSENSE_TELEGRAM_ENABLED", "1") == "1"

BROKER_KEYWORDS = [
    "securities", "broker", "broking", "icici", "motilal",
    "kotak", "axis", "jefferies", "goldman", "jp morgan",
    "upgrade", "downgrade", "target price", "rating"
]

WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "AXISBANK.NS",
    "KOTAKBANK.NS", "BAJFINANCE.NS", "MARUTI.NS", "TATAMOTORS.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "HINDUNILVR.NS", "SUNPHARMA.NS",
    "WIPRO.NS", "HCLTECH.NS"
]

USER_WATCHLIST = [
    item.strip().upper()
    for item in os.getenv("STOCKSENSE_WATCHLIST", "").split(",")
    if item.strip()
]
