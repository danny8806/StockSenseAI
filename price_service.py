from datetime import datetime, timezone

from ticker_utils import is_tradable_ticker


def quote_snapshot(tickers, limit=16):
    try:
        import yfinance as yf
    except ImportError:
        return {"quotes": [], "error": "yfinance is not installed"}

    quotes = []
    for ticker in tickers[:limit]:
        if not is_tradable_ticker(ticker):
            continue
        try:
            data = yf.Ticker(ticker).history(period="5d", interval="1d")
            if data.empty:
                continue
            last = data.iloc[-1]
            prev = data.iloc[-2] if len(data) > 1 else last
            close = float(last["Close"])
            previous = float(prev["Close"]) or close
            change_pct = ((close - previous) / previous) * 100 if previous else 0
            quotes.append({
                "ticker": ticker,
                "close": round(close, 2),
                "change_pct": round(change_pct, 2),
                "volume": int(last.get("Volume", 0)),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            continue
    return {"quotes": quotes}


def first_quote(tickers):
    quotes = quote_snapshot(tickers, limit=4).get("quotes", [])
    return quotes[0] if quotes else None
