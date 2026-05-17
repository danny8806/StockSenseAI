from datetime import datetime, timezone

import requests

from config import ALERT_WEBHOOK_URL


def should_alert(signal):
    return (
        signal.get("priority") == "HIGH"
        and signal.get("suggestion") in {"BUY", "SELL"}
        and abs(float(signal.get("signal_score") or 0)) >= 80
    )


def send_alert_if_needed(conn, news_id, news_item, signal):
    if not should_alert(signal):
        return None

    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id FROM alert_log WHERE news_id=? AND channel=?",
        (news_id, "webhook" if ALERT_WEBHOOK_URL else "local")
    ).fetchone()
    if existing:
        return None

    message = (
        f"{signal['suggestion']} {', '.join(signal.get('stocks') or [])} "
        f"score {signal.get('signal_score')} confidence {signal.get('confidence')}: "
        f"{news_item.get('headline')}"
    )
    channel = "local"
    status = "recorded"

    if ALERT_WEBHOOK_URL:
        channel = "webhook"
        try:
            response = requests.post(
                ALERT_WEBHOOK_URL,
                json={
                    "news_id": news_id,
                    "headline": news_item.get("headline"),
                    "source": news_item.get("source"),
                    "url": news_item.get("url"),
                    "signal": signal,
                    "message": message,
                },
                timeout=8,
            )
            status = "sent" if response.ok else f"failed:{response.status_code}"
        except Exception as exc:
            status = f"failed:{exc}"

    cur.execute(
        """
        INSERT OR IGNORE INTO alert_log (news_id, channel, status, message, sent_at)
        VALUES (?,?,?,?,?)
        """,
        (news_id, channel, status, message, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    return {"channel": channel, "status": status, "message": message}
