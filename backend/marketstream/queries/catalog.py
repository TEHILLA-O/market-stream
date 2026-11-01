"""Allowlisted analytics. Raw q text from the client is never executed."""

from __future__ import annotations

INTERVALS = {"5s": 5, "15s": 15, "1m": 60, "5m": 300}


QUERIES: dict[str, dict] = {
    "latest": {
        "title": "Latest trade and quote",
        "summary": "Last trade print beside the latest two-sided quote.",
        "q": "select last price, last bid, last ask by sym from aj[`sym`time;trade;quote]",
        "explanation": (
            "An as-of join attaches the prevailing quote to each trade. "
            "The rows below are the Python reference for that join on the current session, "
            "reduced to the latest trade per symbol."
        ),
    },
    "ohlc": {
        "title": "Trade OHLC",
        "summary": "Open, high, low, close, volume, and VWAP by time bucket.",
        "q": (
            "select open:first price, high:max price, low:min price, close:last price, "
            "volume:sum qty, vwap:qty wavg price by bucket xbar time from trade where sym=s"
        ),
        "explanation": (
            "Each bucket uses trades only. Empty buckets are omitted rather than forward-filled. "
            "VWAP is sum(price × quantity) / sum(quantity), in tick space, then converted for display."
        ),
    },
    "vwap": {
        "title": "Session VWAP",
        "summary": "Volume-weighted average trade price for the session.",
        "q": "select sym, vwap:qty wavg price, volume:sum qty from trade",
        "explanation": "Weights are lot quantities. The result is an average price, not a notional in currency until multiplied by lot size.",
    },
    "volatility": {
        "title": "Rolling log-return volatility",
        "summary": "Sample standard deviation of log returns over the last 20 closes.",
        "q": "dev {log x%prev x} close",
        "explanation": (
            "Not annualised. The window is 20 OHLC closes of the selected interval. "
            "A short synthetic window is not a forecast of future variance."
        ),
    },
    "asof": {
        "title": "Trade as-of quote",
        "summary": "Prevailing bid and ask at or before each recent trade.",
        "q": "aj[`sym`time;select from trade where sym=s;select from quote where sym=s]",
        "explanation": (
            "q's aj requires both tables to be sorted by time within the as-of columns. "
            "The Python version sorts explicitly and walks a cursor. It does not look into the future."
        ),
    },
    "spread": {
        "title": "Quoted spread",
        "summary": "Bid-ask spread in ticks and basis points.",
        "q": "select time, spread:ask-bid, mid:0.5*bid+ask from quote where sym=s",
        "explanation": "Basis points use the quoted mid as the denominator. One-sided quotes are skipped.",
    },
}


def list_queries(engine: str) -> list[dict]:
    rows = []
    for key, spec in QUERIES.items():
        rows.append(
            {
                "id": key,
                "title": spec["title"],
                "summary": spec["summary"],
                "q": spec["q"],
                "explanation": spec["explanation"],
                "engine": engine,
            }
        )
    return rows
