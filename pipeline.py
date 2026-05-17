import json
from datetime import datetime, timezone
from news_fetcher import fetch_news, get_source_health
from deduplicator import is_duplicate, add_vector
from llm_engine import extract_llm
from config import GROQ_MODEL, ENABLE_SEMANTIC_DEDUPE
from signal_scoring import enrich_signal
from ticker_utils import clean_tickers
from price_service import first_quote
from alerts import send_alert_if_needed
from telegram_alerts import send_telegram_if_needed

def _record_source_health(cur):
    for item in get_source_health():
        cur.execute(
            """
            INSERT INTO source_health (source, url, status, item_count, error, checked_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(source) DO UPDATE SET
                url=excluded.url,
                status=excluded.status,
                item_count=excluded.item_count,
                error=excluded.error,
                checked_at=excluded.checked_at
            """,
            (
                item["source"],
                item["url"],
                item["status"],
                item["item_count"],
                item["error"],
                item["checked_at"],
            )
        )

def run_pipeline(conn, limit=30):
    cur = conn.cursor()
    news = fetch_news(limit=limit)
    _record_source_health(cur)
    conn.commit()
    stats = {
        "fetched": len(news),
        "inserted": 0,
        "duplicates": 0,
        "processed": 0,
        "errors": []
    }

    for n in news:
        try:
            cur.execute(
                """
                INSERT OR IGNORE INTO news_raw (
                    news_id, source, headline, full_text, url, published_at, fetched_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    n["news_id"],
                    n["source"],
                    n["headline"],
                    n["full_text"],
                    n.get("url", ""),
                    n.get("published_at"),
                    n["fetched_at"]
                )
            )

            if cur.rowcount == 0:
                stats["duplicates"] += 1
                continue

            if ENABLE_SEMANTIC_DEDUPE and is_duplicate(n["full_text"]):
                stats["duplicates"] += 1
                continue

            add_vector(n["news_id"], n["full_text"])
            stats["inserted"] += 1

            llm = extract_llm(n["full_text"])
            if not llm:
                continue
            llm["stocks"] = clean_tickers(llm.get("stocks"))
            if not llm["stocks"]:
                llm["suggestion"] = "WATCH"
                llm["stocks"] = []
            llm = enrich_signal(llm, n)
            quote = first_quote(llm["stocks"])

            cur.execute("""
            INSERT INTO news_llm (
                news_id, stocks, event_type, sentiment,
                impact_horizon, suggestion, confidence,
                signal_score, priority, risk_level, confidence_reasons,
                price_at_signal, price_checked_at, price_change_pct,
                reasoning, model_name, processed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(news_id) DO UPDATE SET
                stocks=excluded.stocks,
                event_type=excluded.event_type,
                sentiment=excluded.sentiment,
                impact_horizon=excluded.impact_horizon,
                suggestion=excluded.suggestion,
                confidence=excluded.confidence,
                signal_score=excluded.signal_score,
                priority=excluded.priority,
                risk_level=excluded.risk_level,
                confidence_reasons=excluded.confidence_reasons,
                price_at_signal=COALESCE(news_llm.price_at_signal, excluded.price_at_signal),
                price_checked_at=excluded.price_checked_at,
                price_change_pct=excluded.price_change_pct,
                reasoning=excluded.reasoning,
                model_name=excluded.model_name,
                processed_at=excluded.processed_at
            """, (
                n["news_id"],
                json.dumps(llm["stocks"]),
                llm["event_type"],
                llm["sentiment"],
                llm["impact_horizon"],
                llm["suggestion"],
                llm["confidence"],
                llm["signal_score"],
                llm["priority"],
                llm["risk_level"],
                json.dumps(llm["confidence_reasons"]),
                quote["close"] if quote else None,
                quote["checked_at"] if quote else None,
                quote["change_pct"] if quote else None,
                llm["reasoning"],
                GROQ_MODEL,
                datetime.now(timezone.utc).isoformat()
            ))
            stats["processed"] += 1
            conn.commit()
            send_alert_if_needed(conn, n["news_id"], n, llm)
            send_telegram_if_needed(conn, n["news_id"], n, llm)
        except Exception as exc:
            conn.rollback()
            stats["errors"].append({"headline": n.get("headline", ""), "error": str(exc)})

    return stats
