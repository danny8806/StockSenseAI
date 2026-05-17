import re

INVALID_TICKERS = {
    "TICKER.NS", "MARKET.NS", "SEBI", "SEBI.NS", "INR", "SENSEX", "NIFTY",
    "SENSEX|NIFTY", "INDIA.NS", "NIFTY50.NS", "BANK.NS", "FINANCIALS.NS",
    "INFRA.NS", "BANKNIFTY.NS", "NIFTY.NS", "SENSEX.NS"
}

INDEX_TICKERS = {
    "NIFTY": "^NSEI",
    "SENSEX": "^BSESN",
    "BANKNIFTY": "^NSEBANK",
}


def normalize_ticker(raw):
    ticker = str(raw or "").strip().upper()
    ticker = ticker.replace(" ", "")
    if not ticker:
        return None
    if ticker in INDEX_TICKERS:
        return INDEX_TICKERS[ticker]
    if ticker in INVALID_TICKERS:
        return None
    if ticker.startswith("^"):
        return ticker
    if re.fullmatch(r"[A-Z0-9&-]{2,20}", ticker):
        ticker = f"{ticker}.NS"
    if not re.fullmatch(r"[A-Z0-9&-]{2,20}\.NS", ticker):
        return None
    return ticker


def clean_tickers(values):
    cleaned = []
    for value in values or []:
        ticker = normalize_ticker(value)
        if ticker and ticker not in cleaned:
            cleaned.append(ticker)
    return cleaned


def is_tradable_ticker(ticker):
    return bool(ticker and (ticker.endswith(".NS") or ticker.startswith("^")))
