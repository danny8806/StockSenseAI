import sqlite3
from config import DB_PATH

def _ensure_column(cur, table, column, definition):
    columns = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def _create_schema(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS news_raw (
        news_id TEXT PRIMARY KEY,
        source TEXT,
        headline TEXT,
        full_text TEXT,
        url TEXT,
        published_at TEXT,
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
        signal_score REAL,
        priority TEXT,
        risk_level TEXT,
        confidence_reasons TEXT,
        price_at_signal REAL,
        price_checked_at TEXT,
        price_change_pct REAL,
        reasoning TEXT,
        model_name TEXT,
        processed_at TEXT,
        UNIQUE(news_id),
        FOREIGN KEY(news_id) REFERENCES news_raw(news_id) ON DELETE CASCADE
    )
    """)

    _ensure_column(cur, "news_llm", "signal_score", "REAL")
    _ensure_column(cur, "news_llm", "priority", "TEXT")
    _ensure_column(cur, "news_llm", "risk_level", "TEXT")
    _ensure_column(cur, "news_llm", "confidence_reasons", "TEXT")
    _ensure_column(cur, "news_llm", "price_at_signal", "REAL")
    _ensure_column(cur, "news_llm", "price_checked_at", "TEXT")
    _ensure_column(cur, "news_llm", "price_change_pct", "REAL")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS source_health (
        source TEXT PRIMARY KEY,
        url TEXT,
        status TEXT,
        item_count INTEGER,
        error TEXT,
        checked_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS alert_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        news_id TEXT,
        channel TEXT,
        status TEXT,
        message TEXT,
        sent_at TEXT,
        UNIQUE(news_id, channel)
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_news_raw_fetched_at ON news_raw(fetched_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_news_llm_suggestion ON news_llm(suggestion)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_news_llm_event_type ON news_llm(event_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_news_llm_sentiment ON news_llm(sentiment)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_news_llm_priority ON news_llm(priority)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_news_llm_score ON news_llm(signal_score)")

    conn.commit()

def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    _create_schema(conn)
    return conn

def reset_database(db_path=DB_PATH):
    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS news_llm")
    cur.execute("DROP TABLE IF EXISTS news_raw")
    cur.execute("DROP TABLE IF EXISTS source_health")
    cur.execute("DROP TABLE IF EXISTS alert_log")
    conn.commit()
    _create_schema(conn)
    conn.close()
