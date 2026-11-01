"""Measure the Python engine. This does not measure kdb+."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from marketstream.feed.handler import FeedHandler
from marketstream.market.analytics import ohlc, vwap_ticks
from marketstream.market.book import BookService
from marketstream.simulation.engine import Simulator


def run(events_target: int) -> dict:
    symbols = ["ATHR", "BRDL", "NL100", "HLX", "LUMN"]
    simulator = Simulator("bench", symbols, seed=1, start=datetime(2026, 6, 2, tzinfo=timezone.utc))
    generated = []
    started = time.perf_counter()
    while len(generated) < events_target:
        generated.extend(simulator.pulse())
    generated = generated[:events_target]
    generate_s = time.perf_counter() - started

    feed = FeedHandler()
    started = time.perf_counter()
    accepted = feed.handle_many(generated).accepted
    feed_s = time.perf_counter() - started

    books = BookService()
    started = time.perf_counter()
    for event in accepted:
        books.on_event(event)
    book_s = time.perf_counter() - started

    trades = [event for event in accepted if event.event_type == "trade" and event.symbol == "ATHR"]
    started = time.perf_counter()
    bars = ohlc(trades, 5)
    vwap = vwap_ticks(trades)
    analytics_s = time.perf_counter() - started
    return {
        "events": len(generated),
        "accepted": len(accepted),
        "generate_eps": len(generated) / generate_s,
        "feed_eps": len(accepted) / feed_s if feed_s else None,
        "book_eps": len(accepted) / book_s if book_s else None,
        "analytics_s": analytics_s,
        "athr_trades": len(trades),
        "athr_bars": len(bars),
        "vwap": None if vwap is None else f"{vwap:.2f}",
        "generate_s": generate_s,
        "feed_s": feed_s,
        "book_s": book_s,
    }


def main() -> None:
    print("| events | generate evt/s | feed evt/s | book evt/s | ATHR bars |")
    print("| ---: | ---: | ---: | ---: | ---: |")
    for size in (10_000, 100_000, 1_000_000):
        row = run(size)
        print(
            f"| {row['events']} | {row['generate_eps']:.0f} | {row['feed_eps']:.0f} | {row['book_eps']:.0f} | {row['athr_bars']} |"
        )


if __name__ == "__main__":
    main()
