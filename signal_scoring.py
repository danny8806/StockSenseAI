import re
from datetime import datetime, timezone

SOURCE_RELIABILITY = {
    "BusinessStandard": 0.84,
    "EconomicTimes": 0.82,
    "Moneycontrol": 0.8,
    "LiveMint": 0.78,
    "NSEIndia": 0.86,
}

EVENT_WEIGHT = {
    "BROKER_CALL": 0.78,
    "FUND_FLOW": 0.74,
    "MACRO": 0.68,
    "PRICE_ACTION": 0.7,
    "GLOBAL": 0.64,
}

ACTION_WEIGHT = {
    "BUY": 1.0,
    "SELL": 1.0,
    "HOLD": 0.72,
    "WATCH": 0.62,
}

STRONG_WORDS = {
    "record", "surge", "crash", "upgrade", "downgrade", "beats", "misses",
    "order", "stake", "block deal", "insider", "rbi", "sebi", "result",
    "profit", "loss", "guidance", "target price", "inflow", "outflow"
}

WEAK_WORDS = {"may", "could", "likely", "expects", "plans", "proposal", "consider"}


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _clamp(value, low=0.35, high=0.95):
    return max(low, min(high, value))


def _freshness_score(published_at, fetched_at):
    dt = _parse_dt(published_at) or _parse_dt(fetched_at)
    if not dt:
        return 0.58, "unknown age"
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)

    age_hours = max((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 0)
    if age_hours <= 6:
        return 0.94, "fresh"
    if age_hours <= 24:
        return 0.84, "same day"
    if age_hours <= 72:
        return 0.68, "recent"
    return 0.46, "stale"


def enrich_signal(llm, news_item):
    text = f"{news_item.get('headline', '')} {news_item.get('full_text', '')}".lower()
    words = re.findall(r"[a-z0-9]+", text)
    word_count = len(words)
    stocks = llm.get("stocks") or []
    source = news_item.get("source", "")

    source_score = SOURCE_RELIABILITY.get(source, 0.72)
    event_score = EVENT_WEIGHT.get(llm.get("event_type"), 0.66)
    action_score = ACTION_WEIGHT.get(llm.get("suggestion"), 0.62)
    freshness, freshness_reason = _freshness_score(news_item.get("published_at"), news_item.get("fetched_at"))

    specificity = 0.54
    if 1 <= len(stocks) <= 3:
        specificity += 0.18
    elif len(stocks) > 3:
        specificity += 0.08
    if word_count >= 35:
        specificity += 0.1
    if re.search(r"\b(rs|₹|\$|%|crore|lakh|q[1-4]|fy\d{2})\b", text):
        specificity += 0.1
    specificity = _clamp(specificity, 0.4, 0.92)

    strength_hits = sum(1 for word in STRONG_WORDS if word in text)
    weak_hits = sum(1 for word in WEAK_WORDS if word in text)
    language_score = _clamp(0.62 + min(strength_hits, 4) * 0.055 - min(weak_hits, 3) * 0.04, 0.42, 0.9)

    consistency = 0.72
    if llm.get("suggestion") == "BUY" and llm.get("sentiment") == "POSITIVE":
        consistency = 0.9
    elif llm.get("suggestion") == "SELL" and llm.get("sentiment") == "NEGATIVE":
        consistency = 0.9
    elif llm.get("suggestion") in {"HOLD", "WATCH"} and llm.get("sentiment") == "NEUTRAL":
        consistency = 0.82
    elif llm.get("suggestion") in {"BUY", "SELL"} and llm.get("sentiment") == "NEUTRAL":
        consistency = 0.55

    raw_llm_confidence = float(llm.get("confidence") or 0.55)
    calibrated = (
        source_score * 0.14
        + event_score * 0.12
        + action_score * 0.1
        + freshness * 0.18
        + specificity * 0.18
        + language_score * 0.16
        + consistency * 0.12
    )

    if raw_llm_confidence < 0.6:
        calibrated -= 0.05
    elif raw_llm_confidence > 0.9:
        calibrated += 0.025

    confidence = round(_clamp(calibrated), 2)
    directional = 1 if llm.get("suggestion") == "BUY" else -1 if llm.get("suggestion") == "SELL" else 0
    signal_score = round((confidence * 100) * directional, 1)

    risk_level = "LOW"
    if llm.get("event_type") in {"GLOBAL", "MACRO"} or llm.get("impact_horizon") == "INTRADAY":
        risk_level = "HIGH"
    elif llm.get("suggestion") in {"BUY", "SELL"} or len(stocks) > 3:
        risk_level = "MEDIUM"

    priority = "LOW"
    if confidence >= 0.82 and abs(signal_score) >= 75:
        priority = "HIGH"
    elif confidence >= 0.68 or llm.get("suggestion") in {"BUY", "SELL"}:
        priority = "MEDIUM"

    reasons = [
        f"{source or 'Unknown source'} source",
        freshness_reason,
        f"{llm.get('event_type', 'event').replace('_', ' ').lower()} event",
    ]
    if strength_hits:
        reasons.append("strong market wording")
    if specificity >= 0.75:
        reasons.append("specific stock or numeric detail")
    if consistency >= 0.88:
        reasons.append("sentiment matches action")
    if weak_hits:
        reasons.append("speculative wording penalty")

    llm["confidence"] = confidence
    llm["signal_score"] = signal_score
    llm["priority"] = priority
    llm["risk_level"] = risk_level
    llm["confidence_reasons"] = reasons[:5]
    return llm
