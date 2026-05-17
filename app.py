import json
import sqlite3
import threading
import time
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    AUTH_ENABLED,
    DB_PATH,
    SECRET_KEY,
    SERVER_REFRESH_SECONDS,
    SERVER_SCHEDULER_ENABLED,
)
from db import get_connection, reset_database
from deduplicator import reset_vectors
from pipeline import run_pipeline
from price_service import quote_snapshot
from ticker_utils import clean_tickers
from telegram_alerts import send_telegram_manual

app = Flask(__name__)
app.secret_key = SECRET_KEY
pipeline_lock = threading.Lock()
last_scheduler_run = {"status": "idle", "stats": None, "ran_at": None}
scheduler_started = False


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not AUTH_ENABLED or session.get("authenticated"):
            return fn(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "authentication required"}), 401
        return redirect(url_for("login"))
    return wrapper


def run_pipeline_safely(limit=30, reason="manual"):
    if not pipeline_lock.acquire(blocking=False):
        return {"status": "busy", "reason": reason}
    try:
        conn = get_connection()
        stats = run_pipeline(conn, limit=limit)
        conn.close()
        last_scheduler_run.update({
            "status": "ok",
            "stats": stats,
            "ran_at": datetime.now().isoformat(timespec="seconds"),
            "reason": reason,
        })
        return stats
    except Exception as exc:
        last_scheduler_run.update({
            "status": "error",
            "stats": {"errors": [str(exc)]},
            "ran_at": datetime.now().isoformat(timespec="seconds"),
            "reason": reason,
        })
        return {"status": "error", "errors": [str(exc)]}
    finally:
        pipeline_lock.release()


def start_scheduler():
    global scheduler_started
    if not SERVER_SCHEDULER_ENABLED:
        return
    if scheduler_started:
        return
    scheduler_started = True

    def loop():
        while True:
            time.sleep(SERVER_REFRESH_SECONDS)
            run_pipeline_safely(limit=30, reason="scheduler")

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _rows_to_signals(rows):
    signals = []
    for row in rows:
        item = dict(row)
        try:
            item["stocks"] = json.loads(item.get("stocks") or "[]")
        except json.JSONDecodeError:
            item["stocks"] = []
        item["stocks"] = clean_tickers(item["stocks"])
        try:
            item["confidence_reasons"] = json.loads(item.get("confidence_reasons") or "[]")
        except json.JSONDecodeError:
            item["confidence_reasons"] = []
        item["confidence"] = float(item.get("confidence") or 0)
        item["signal_score"] = float(item.get("signal_score") or 0)
        item["price_at_signal"] = float(item["price_at_signal"]) if item.get("price_at_signal") is not None else None
        item["price_change_pct"] = float(item["price_change_pct"]) if item.get("price_change_pct") is not None else None
        signals.append(item)
    return signals


def _summary(signals):
    total = len(signals)
    avg_confidence = round(sum(s["confidence"] for s in signals) / total, 2) if total else 0
    avg_score = round(sum(abs(s["signal_score"]) for s in signals) / total, 1) if total else 0
    suggestions = {}
    sentiments = {}
    event_types = {}
    priorities = {}
    risks = {}
    stocks = {}

    for signal in signals:
        suggestions[signal["suggestion"]] = suggestions.get(signal["suggestion"], 0) + 1
        sentiments[signal["sentiment"]] = sentiments.get(signal["sentiment"], 0) + 1
        event_types[signal["event_type"]] = event_types.get(signal["event_type"], 0) + 1
        priorities[signal.get("priority") or "LOW"] = priorities.get(signal.get("priority") or "LOW", 0) + 1
        risks[signal.get("risk_level") or "LOW"] = risks.get(signal.get("risk_level") or "LOW", 0) + 1
        for stock in signal["stocks"]:
            stocks[stock] = stocks.get(stock, 0) + 1

    return {
        "total": total,
        "buy": suggestions.get("BUY", 0),
        "sell": suggestions.get("SELL", 0),
        "watch": suggestions.get("WATCH", 0),
        "hold": suggestions.get("HOLD", 0),
        "avg_confidence": avg_confidence,
        "avg_score": avg_score,
        "high_priority": priorities.get("HIGH", 0),
        "suggestions": suggestions,
        "sentiments": sentiments,
        "event_types": event_types,
        "priorities": priorities,
        "risks": risks,
        "top_stocks": sorted(stocks.items(), key=lambda item: item[1], reverse=True)[:8],
        "action_queue": sorted(
            [s for s in signals if s["suggestion"] in {"BUY", "SELL"}],
            key=lambda item: (item.get("priority") == "HIGH", abs(item["signal_score"]), item["confidence"]),
            reverse=True
        )[:6],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def load_signals(filters=None):
    filters = filters or {}
    where = []
    params = []

    for field in ("event_type", "sentiment", "suggestion", "source", "priority", "risk_level"):
        value = filters.get(field)
        if value:
            table = "r" if field == "source" else "l"
            where.append(f"{table}.{field} = ?")
            params.append(value)

    min_confidence = filters.get("min_confidence")
    if min_confidence not in (None, ""):
        where.append("l.confidence >= ?")
        params.append(float(min_confidence))

    stock = filters.get("stock")
    if stock:
        where.append("l.stocks LIKE ?")
        params.append(f"%{stock}%")

    sql = """
        SELECT
            r.news_id,
            r.source,
            r.headline,
            r.full_text,
            r.url,
            r.published_at,
            r.fetched_at,
            l.stocks,
            l.event_type,
            l.sentiment,
            l.impact_horizon,
            l.suggestion,
            l.confidence,
            l.signal_score,
            l.priority,
            l.risk_level,
            l.confidence_reasons,
            l.price_at_signal,
            l.price_checked_at,
            l.price_change_pct,
            l.reasoning,
            l.model_name,
            l.processed_at
        FROM news_raw r
        JOIN news_llm l ON r.news_id = l.news_id
    """

    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY datetime(COALESCE(r.published_at, r.fetched_at)) DESC LIMIT 250"

    conn = _connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return _rows_to_signals(rows)


def _load_signal_by_news_id(news_id):
    conn = _connect()
    row = conn.execute(
        """
        SELECT
            r.news_id,
            r.source,
            r.headline,
            r.full_text,
            r.url,
            r.published_at,
            r.fetched_at,
            l.stocks,
            l.event_type,
            l.sentiment,
            l.impact_horizon,
            l.suggestion,
            l.confidence,
            l.signal_score,
            l.priority,
            l.risk_level,
            l.confidence_reasons,
            l.price_at_signal,
            l.price_checked_at,
            l.price_change_pct,
            l.reasoning,
            l.model_name,
            l.processed_at
        FROM news_raw r
        JOIN news_llm l ON r.news_id = l.news_id
        WHERE r.news_id = ?
        """,
        (news_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _rows_to_signals([row])[0]


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if not AUTH_ENABLED:
        session["authenticated"] = True
        return redirect(url_for("index"))
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Invalid username or password"
    return render_template("login.html", error=error)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/api/signals")
@login_required
def api_signals():
    signals = load_signals(request.args)
    return jsonify({"signals": signals, "summary": _summary(signals)})


@app.get("/api/dashboard")
@login_required
def api_dashboard():
    signals = load_signals()
    return jsonify({"signals": signals, "summary": _summary(signals)})


@app.get("/api/quotes")
@login_required
def api_quotes():
    tickers = request.args.get("tickers", "")
    requested = [ticker.strip().upper() for ticker in tickers.split(",") if ticker.strip()]
    if not requested:
        signals = load_signals()
        seen = []
        for signal in signals:
            for ticker in signal["stocks"]:
                if ticker not in seen:
                    seen.append(ticker)
        requested = seen[:12]
    return jsonify(quote_snapshot(requested))


@app.get("/api/source-health")
@login_required
def api_source_health():
    conn = _connect()
    rows = conn.execute("SELECT * FROM source_health ORDER BY source").fetchall()
    conn.close()
    return jsonify({"sources": [dict(row) for row in rows]})


@app.get("/api/alerts")
@login_required
def api_alerts():
    conn = _connect()
    rows = conn.execute("SELECT * FROM alert_log ORDER BY sent_at DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify({"alerts": [dict(row) for row in rows]})


@app.get("/api/stock/<ticker>")
@login_required
def api_stock_history(ticker):
    signals = load_signals({"stock": ticker.upper()})
    return jsonify({"ticker": ticker.upper(), "signals": signals, "summary": _summary(signals)})


@app.get("/api/scheduler")
@login_required
def api_scheduler():
    return jsonify({
        "enabled": SERVER_SCHEDULER_ENABLED,
        "interval_seconds": SERVER_REFRESH_SECONDS,
        "last_run": last_scheduler_run,
        "running": pipeline_lock.locked(),
    })


@app.post("/api/run-pipeline")
@login_required
def api_run_pipeline():
    payload = request.get_json(silent=True) or {}
    limit = int(payload.get("limit", 30))
    stats = run_pipeline_safely(limit=limit, reason="manual")
    return jsonify(stats)


@app.post("/api/reset-db")
@login_required
def api_reset_db():
    reset_database()
    reset_vectors()
    return jsonify({"ok": True, "message": "Database and vector store reset."})


@app.post("/api/send-telegram/<news_id>")
@login_required
def api_send_telegram(news_id):
    signal = _load_signal_by_news_id(news_id)
    if not signal:
        return jsonify({"error": "signal not found"}), 404

    news_item = {
        "headline": signal["headline"],
        "source": signal["source"],
        "url": signal["url"],
        "published_at": signal["published_at"],
        "fetched_at": signal["fetched_at"],
    }
    conn = get_connection()
    result = send_telegram_manual(conn, news_id, news_item, signal)
    conn.close()
    return jsonify(result)


if __name__ == "__main__":
    get_connection().close()
    start_scheduler()
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
else:
    get_connection().close()
    start_scheduler()
