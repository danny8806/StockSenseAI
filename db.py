import sqlite3

def get_connection(db_path="news.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS news_raw (
        news_id TEXT PRIMARY KEY,
        source TEXT,
        headline TEXT,
        full_text TEXT,
        fetched_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS news_llm (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        news_id TEXT,
        stocks TEXT,
        event_type TEXT,
        sentiment TEXT,
        impact_horizon TEXT,
        suggestion TEXT,
        confidence REAL,
        reasoning TEXT,
        model_name TEXT,
        processed_at TEXT
    )
    """)

    conn.commit()
    return 