import json, re
from datetime import datetime, timezone
from openai import OpenAI
from config import GROQ_API_KEY, GROQ_BASE_URL, BROKER_KEYWORDS

client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

def _safe_json(text):
    try:
        return json.loads(text)
    except:
        m = re.search(r"\{[\s\S]*\}", text)
        return json.loads(m.group()) if m else None

def extract_llm(news_text):
    prompt = f"""
Return ONLY valid JSON.

{{
 "stocks":["TICKER.NS"],
 "event_type":"BROKER_CALL|FUND_FLOW|MACRO|PRICE_ACTION|GLOBAL",
 "sentiment":"POSITIVE|NEGATIVE|NEUTRAL",
 "impact_horizon":"INTRADAY|SHORT_TERM|LONG_TERM",
 "suggestion":"BUY|SELL|HOLD|WATCH",
 "confidence":0.0,
 "reasoning":"short explanation"
}}

News:
\"\"\"{news_text}\"\"\"
"""

    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Return JSON only"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    parsed = _safe_json(res.choices[0].message.content)
    if not parsed:
        return None

    if any(k in news_text.lower() for k in BROKER_KEYWORDS):
        parsed["event_type"] = "BROKER_CALL"

    parsed["confidence"] = min(float(parsed.get("confidence", 0.5)), 0.95)
    return parsed
