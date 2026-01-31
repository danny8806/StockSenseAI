import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY missing")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

BROKER_KEYWORDS = [
    "securities", "broker", "broking", "icici", "motilal",
    "kotak", "axis", "jefferies", "goldman", "jp morgan"
]