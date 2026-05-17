from datetime import datetime, timezone
from html import escape

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED


def telegram_configured():
    return TELEGRAM_ENABLED and bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def build_telegram_message(news_item, signal):
    stocks = ", ".join(signal.get("stocks") or []) or "No tradable ticker"
    reasons = signal.get("confidence_reasons") or []
    confidence_notes = "\n".join(f"- {escape(item)}" for item in reasons[:4]) or "- No extra confidence notes"

    lines = [
        "<b>StockSenseAI New Signal</b>",
        f"<b>Headline:</b> {escape(news_item.get('headline', ''))}",
        f"<b>Source:</b> {escape(news_item.get('source', ''))}",
        f"<b>Published:</b> {escape(news_item.get('published_at') or news_item.get('fetched_at') or '')}",
        f"<b>Stocks:</b> {escape(stocks)}",
        f"<b>Suggestion:</b> {escape(signal.get('suggestion', 'WATCH'))}",
        f"<b>Sentiment:</b> {escape(signal.get('sentiment', 'NEUTRAL'))}",
        f"<b>Event:</b> {escape(signal.get('event_type', 'PRICE_ACTION'))}",
        f"<b>Horizon:</b> {escape(signal.get('impact_horizon', 'SHORT_TERM'))}",
        f"<b>Priority:</b> {escape(signal.get('priority', 'MEDIUM'))}",
        f"<b>Risk:</b> {escape(signal.get('risk_level', 'MEDIUM'))}",
        f"<b>Confidence:</b> {float(signal.get('confidence') or 0):.2f}",
        f"<b>Action Score:</b> {float(signal.get('signal_score') or 0):.1f}",
        f"<b>Reasoning:</b> {escape(signal.get('reasoning', ''))}",
        "<b>Confidence Notes:</b>",
        confidence_notes,
    ]
    if news_item.get("url"):
        lines.append(f"<b>Link:</b> {escape(news_item['url'])}")
    return "\n".join(lines)[:3900]


def send_telegram_if_needed(conn, news_id, news_item, signal):
    if not telegram_configured():
        return None

    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id FROM alert_log WHERE news_id=? AND channel='telegram'",
        (news_id,)
    ).fetchone()
    if existing:
        return None

    message = build_telegram_message(news_item, signal)
    status = "sent"
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=12,
        )
        if not response.ok:
            status = f"failed:{response.status_code}"
    except Exception as exc:
        status = f"failed:{exc}"

    cur.execute(
        """
        INSERT OR IGNORE INTO alert_log (news_id, channel, status, message, sent_at)
        VALUES (?,?,?,?,?)
        """,
        (news_id, "telegram", status, message, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    return {"channel": "telegram", "status": status}


def send_telegram_manual(conn, news_id, news_item, signal):
    if not telegram_configured():
        return {"channel": "telegram", "status": "not_configured"}

    message = build_telegram_message(news_item, signal)
    status = "sent"
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=12,
        )
        if not response.ok:
            status = f"failed:{response.status_code}"
    except Exception as exc:
        status = f"failed:{exc}"

    sent_at = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO alert_log (news_id, channel, status, message, sent_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(news_id, channel) DO UPDATE SET
            status=excluded.status,
            message=excluded.message,
            sent_at=excluded.sent_at
        """,
        (news_id, "telegram_manual", status, message, sent_at)
    )
    conn.commit()
    return {"channel": "telegram_manual", "status": status}
