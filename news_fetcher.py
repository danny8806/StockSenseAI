import feedparser, uuid, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

RSS_FEEDS = {
    "Moneycontrol": "https://www.moneycontrol.com/rss/marketreports.xml",
    "EconomicTimes": "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
    "LiveMint": "https://www.livemint.com/rss/markets"
}

def clean(text):
    return re.sub(r"\s+", " ", BeautifulSoup(text, "html.parser").get_text()).strip()

def fetch_news(limit=10):
    items = []
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for e in feed.entries[:limit]:
            items.append({
                "news_id": str(uuid.uuid4()),
                "source": source,
                "headline": e.title,
                "full_text": clean(e.title + " " + e.get("summary", "")),
                "fetched_at": datetime.now(timezone.utc).isoformat()
            })
    return items
