"""In-process time-series analytics.

These functions are the Python reference for the q analytics in
`q/analytics/analytics.q`. They are used when no q process is connected.
They are not a kdb+ engine.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from math import log, sqrt

from marketstream.core.instruments import Instrument
from marketstream.core.models import QuoteEvent, TradeEvent


def _bucket(ts: datetime, interval_s: int) -> datetime:
    epoch = int(ts.timestamp())
    start = epoch - (epoch % interval_s)
    return datetime.fromtimestamp(start, tz=timezone.utc)


def ohlc(
    trades: list[TradeEvent],
    interval_s: int,
) -> list[dict]:
    """Trade OHLC. Buckets with no trades are omitted, not forward-filled."""

    if interval_s <= 0:
        raise ValueError("interval must be positive")
    grouped: dict[datetime, list[TradeEvent]] = defaultdict(list)
    for trade in trades:
        grouped[_bucket(trade.event_timestamp, interval_s)].append(trade)
    bars = []
    for start in sorted(grouped):
        rows = grouped[start]
        prices = [row.price_ticks for row in rows]
        qty = [row.quantity_lots for row in rows]
        notion = sum(price * size for price, size in zip(prices, qty, strict=True))
        volume = sum(qty)
        bars.append(
            {
                "time": start,
                "open_ticks": prices[0],
                "high_ticks": max(prices),
                "low_ticks": min(prices),
                "close_ticks": prices[-1],
                "volume_lots": volume,
                "trade_count": len(rows),
                "vwap_ticks": (Decimal(notion) / Decimal(volume)) if volume else None,
            }
        )
    return bars


def vwap_ticks(trades: list[TradeEvent]) -> Decimal | None:
    volume = sum(trade.quantity_lots for trade in trades)
    if volume <= 0:
        return None
    notion = sum(trade.price_ticks * trade.quantity_lots for trade in trades)
    return Decimal(notion) / Decimal(volume)


def session_high_low(trades: list[TradeEvent]) -> tuple[int | None, int | None]:
    if not trades:
        return None, None
    prices = [trade.price_ticks for trade in trades]
    return max(prices), min(prices)


def trade_returns(closes: list[int]) -> list[float]:
    """Simple log returns between successive positive prices."""

    out = []
    for previous, current in zip(closes, closes[1:], strict=False):
        if previous > 0 and current > 0:
            out.append(log(current / previous))
    return out


def rolling_volatility(closes: list[int], window: int) -> float | None:
    """Standard deviation of log returns over the last `window` closes.

    This is not annualised. The window is in bars, not calendar time.
    """

    if window < 2 or len(closes) < window:
        return None
    sample = closes[-window:]
    returns = trade_returns(sample)
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    return sqrt(variance)


def spread_series(quotes: list[QuoteEvent]) -> list[dict]:
    rows = []
    for quote in quotes:
        if quote.bid_ticks is None or quote.ask_ticks is None:
            continue
        spread = quote.ask_ticks - quote.bid_ticks
        mid = (quote.bid_ticks + quote.ask_ticks) / 2
        bps = (spread / mid * 10000) if mid else None
        rows.append(
            {
                "time": quote.event_timestamp,
                "spread_ticks": spread,
                "spread_bps": bps,
                "mid_ticks": mid,
            }
        )
    return rows


def asof_quote(trades: list[TradeEvent], quotes: list[QuoteEvent]) -> list[dict]:
    """Last quote at or before each trade, per symbol. Both inputs must share one symbol."""

    ordered_quotes = sorted(quotes, key=lambda item: (item.event_timestamp, item.sequence_number))
    cursor = 0
    current: QuoteEvent | None = None
    joined = []
    for trade in sorted(trades, key=lambda item: (item.event_timestamp, item.sequence_number)):
        while cursor < len(ordered_quotes) and (
            ordered_quotes[cursor].event_timestamp,
            ordered_quotes[cursor].sequence_number,
        ) <= (trade.event_timestamp, trade.sequence_number):
            current = ordered_quotes[cursor]
            cursor += 1
        joined.append(
            {
                "trade_id": trade.trade_id,
                "price_ticks": trade.price_ticks,
                "bid_ticks": current.bid_ticks if current else None,
                "ask_ticks": current.ask_ticks if current else None,
            }
        )
    return joined


def price_text(ticks: Decimal | int | None, instrument: Instrument) -> str | None:
    if ticks is None:
        return None
    value = Decimal(ticks) * instrument.tick_size
    return f"{value:.{instrument.price_precision}f}"
