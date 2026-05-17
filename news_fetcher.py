import feedparser, uuid, re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

RSS_FEEDS = {
    "Moneycontrol": "https://www.moneycontrol.com/rss/marketreports.xml",
    "EconomicTimes": "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
    "LiveMint": "https://www.livemint.com/rss/markets",
    "BusinessStandard": "https://www.business-standard.com/rss/markets-106.rss",
    "NSEIndia": "https://www.nseindia.com/rss-feed"
}

LAST_SOURCE_HEALTH = {}

def clean(text):
    return re.sub(r"\s+", " ", BeautifulSoup(text, "html.parser").get_text()).strip()

def _entry_time(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()

def _stable_id(source, entry):
    key = entry.get("link") or entry.get("id") or entry.get("title", "")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}:{key}"))

def fetch_news(limit=10):
    items = []
    for source, url in RSS_FEEDS.items():
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            response = requests.get(
                url,
                timeout=12,
                headers={"User-Agent": "StockSenseAI/1.0"}
            )
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            LAST_SOURCE_HEALTH[source] = {
                "source": source,
                "url": url,
                "status": "ok",
                "item_count": len(feed.entries),
                "error": "",
                "checked_at": checked_at,
            }
        except Exception:
            LAST_SOURCE_HEALTH[source] = {
                "source": source,
                "url": url,
                "status": "error",
                "item_count": 0,
                "error": "Feed request failed",
                "checked_at": checked_at,
            }
            continue

        for e in feed.entries[:limit]:
            headline = clean(e.get("title", ""))
            summary = clean(e.get("summary", ""))
            if not headline:
                continue
            items.append({
                "news_id": _stable_id(source, e),
                "source": source,
                "headline": headline,
                "full_text": clean(f"{headline} {summary}"),
                "url": e.get("link", ""),
                "published_at": _entry_time(e),
                "fetched_at": datetime.now(timezone.utc).isoformat()
            })
    return items

def get_source_health():
    return list(LAST_SOURCE_HEALTH.values())
