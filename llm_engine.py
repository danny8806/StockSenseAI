import json, re
from openai import OpenAI
from config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL, BROKER_KEYWORDS, WATCHLIST

client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL) if GROQ_API_KEY else None

EVENT_TYPES = {"BROKER_CALL", "FUND_FLOW", "MACRO", "PRICE_ACTION", "GLOBAL"}
SENTIMENTS = {"POSITIVE", "NEGATIVE", "NEUTRAL"}
HORIZONS = {"INTRADAY", "SHORT_TERM", "LONG_TERM"}
SUGGESTIONS = {"BUY", "SELL", "HOLD", "WATCH"}

def _safe_json(text):
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        return json.loads(m.group()) if m else None

def _fallback_extract(news_text):
    lower = news_text.lower()
    positive_words = ["gain", "rally", "surge", "upgrade", "beats", "strong", "buy", "record"]
    negative_words = ["fall", "crash", "loss", "downgrade", "weak", "sell", "probe", "decline"]

    sentiment = "NEUTRAL"
    suggestion = "WATCH"
    if any(w in lower for w in positive_words):
        sentiment = "POSITIVE"
        suggestion = "BUY"
    if any(w in lower for w in negative_words):
        sentiment = "NEGATIVE"
        suggestion = "SELL"

    event_type = "PRICE_ACTION"
    if any(k in lower for k in BROKER_KEYWORDS):
        event_type = "BROKER_CALL"
    elif any(k in lower for k in ["inflation", "rbi", "rate", "gdp", "rupee", "crude"]):
        event_type = "MACRO"
    elif any(k in lower for k in ["fii", "dii", "mutual fund", "fund flow"]):
        event_type = "FUND_FLOW"
    elif any(k in lower for k in ["global", "nasdaq", "dow", "fed", "china", "us market"]):
        event_type = "GLOBAL"

    stocks = [ticker for ticker in WATCHLIST if ticker.replace(".NS", "").lower() in lower]
    return {
        "stocks": stocks or ["MARKET.NS"],
        "event_type": event_type,
        "sentiment": sentiment,
        "impact_horizon": "SHORT_TERM",
        "suggestion": suggestion,
        "confidence": 0.55,
        "reasoning": "Rule-based fallback used because the LLM response was unavailable."
    }

def _normalize(parsed, news_text):
    parsed = parsed or _fallback_extract(news_text)
    if any(k in news_text.lower() for k in BROKER_KEYWORDS):
        parsed["event_type"] = "BROKER_CALL"

    stocks = parsed.get("stocks") or []
    if isinstance(stocks, str):
        stocks = [stocks]

    parsed["stocks"] = stocks[:8] or ["MARKET.NS"]
    parsed["event_type"] = parsed.get("event_type") if parsed.get("event_type") in EVENT_TYPES else "PRICE_ACTION"
    parsed["sentiment"] = parsed.get("sentiment") if parsed.get("sentiment") in SENTIMENTS else "NEUTRAL"
    parsed["impact_horizon"] = parsed.get("impact_horizon") if parsed.get("impact_horizon") in HORIZONS else "SHORT_TERM"
    parsed["suggestion"] = parsed.get("suggestion") if parsed.get("suggestion") in SUGGESTIONS else "WATCH"
    parsed["confidence"] = max(0.0, min(float(parsed.get("confidence", 0.5)), 0.95))
    parsed["reasoning"] = str(parsed.get("reasoning", "No reasoning returned."))[:600]
    return parsed

def extract_llm(news_text):
    if not client:
        return _fallback_extract(news_text)

    prompt = f"""
Return ONLY valid JSON.
Use confidence carefully. Do not return the same confidence for every story.
Confidence should be lower for vague, stale, broad-market, speculative, or weakly sourced news.
Confidence should be higher only for specific, fresh, material, stock-linked events.

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

    try:
        res = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a careful Indian equity market analyst. Return JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        parsed = _safe_json(res.choices[0].message.content)
        return _normalize(parsed, news_text)
    except Exception:
        return _fallback_extract(news_text)
