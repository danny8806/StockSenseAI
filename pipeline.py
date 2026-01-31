import json
from datetime import datetime, timezone
from news_fetcher import fetch_news
from deduplicator import is_duplicate, add_vector
from llm_engine import extract_llm

def run_pipeline(conn):
    cur = conn.cursor()
    news = fetch_news()

    for n in news:
        if is_duplicate(n["full_text"]):
            continue

        add_vector(n["news_id"], n["full_text"])

        cur.execute(
            "INSERT OR IGNORE INTO news_raw VALUES (?,?,?,?,?)",
            (n["news_id"], n["source"], n["headline"], n["full_text"], n["fetched_at"])
        )
        conn.commit()

        llm = extract_llm(n["full_text"])
        if not llm:
            continue

        cur.execute("""
        INSERT INTO news_llm (
            news_id, stocks, event_type, sentiment,
            impact_horizon, suggestion, confidence,
            reasoning, model_name, processed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            n["news_id"],
            json.dumps(llm["stocks"]),
            llm["event_type"],
            llm["sentiment"],
            llm["impact_horizon"],
            llm["suggestion"],
            llm["confidence"],
            llm["reasoning"],
            "llama-3.1-8b-instant",
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
