"""Bounded in-memory tick store for the current session.

This is the Python stand-in for an RDB. It is not kdb+. Completed sessions
are appended to the session log and can be reopened by replay.
"""

from __future__ import annotations

from collections import defaultdict, deque

from marketstream.core.models import MarketEvent, QuoteEvent, TradeEvent


class TickStore:
    def __init__(self, trade_limit: int = 20000, quote_limit: int = 8000) -> None:
        self.trades: dict[str, deque[TradeEvent]] = defaultdict(lambda: deque(maxlen=trade_limit))
        self.quotes: dict[str, deque[QuoteEvent]] = defaultdict(lambda: deque(maxlen=quote_limit))
        self.tape: deque[TradeEvent] = deque(maxlen=2000)
        self.quality: deque[MarketEvent] = deque(maxlen=400)
        self.status: deque[MarketEvent] = deque(maxlen=200)
        self.count = 0

    def add(self, event: MarketEvent) -> None:
        self.count += 1
        if event.event_type == "trade":
            self.trades[event.symbol].append(event)
            self.tape.append(event)
        elif event.event_type == "quote":
            self.quotes[event.symbol].append(event)
        elif event.event_type == "feed_quality":
            self.quality.append(event)
        elif event.event_type == "market_status":
            self.status.append(event)

    def clear(self) -> None:
        self.trades.clear()
        self.quotes.clear()
        self.tape.clear()
        self.quality.clear()
        self.status.clear()
        self.count = 0
