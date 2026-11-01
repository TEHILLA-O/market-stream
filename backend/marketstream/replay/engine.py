"""Replay studio.

Playback walks a recorded event log through a fresh order-book engine.
Checkpoints every 250 events make seeks proportional to the gap from the
last checkpoint, not to the start of the session.

The live position ledger is not updated here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter

from marketstream.core.models import MarketEvent
from marketstream.market.book import BookService, LevelState, SymbolBook

ADAPTER = TypeAdapter(MarketEvent)


class ReplayStudio:
    def __init__(self) -> None:
        self.session_id: str | None = None
        self.events: list[MarketEvent] = []
        self.cursor = 0
        self.books = BookService()
        self.checkpoints: list[tuple[int, dict]] = []
        self.markers: list[dict] = []
        self.playing = False
        self.speed = 8.0
        self.meta: dict = {}
        self.depth_samples: dict[str, list[dict]] = {}

    def load_file(self, path: Path, meta: dict | None = None) -> dict:
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(ADAPTER.validate_json(line))
        self.session_id = path.parent.name
        self.events = events
        self.meta = meta or {}
        self.cursor = 0
        self.books = BookService()
        self.playing = False
        self._build_checkpoints()
        self._build_markers()
        if events:
            self.seek(min(len(events), 40))
        return self.status()

    def play(self) -> None:
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def step(self, count: int = 1) -> None:
        if count >= 0:
            self._advance_to(min(len(self.events), self.cursor + count))
        else:
            self.seek(max(0, self.cursor + count))

    def seek(self, index: int) -> None:
        index = max(0, min(len(self.events), index))
        start, state = self._checkpoint_at(index)
        self.books = BookService()
        _restore(self.books, state)
        self.cursor = start
        self._advance_to(index)

    def seek_time(self, iso_timestamp: str) -> None:
        target = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        for index, event in enumerate(self.events):
            if event.event_timestamp >= target:
                self.seek(index + 1)
                return
        self.seek(len(self.events))

    def tick(self, max_events: int) -> int:
        if not self.playing:
            return 0
        before = self.cursor
        self._advance_to(min(len(self.events), self.cursor + max_events))
        if self.cursor >= len(self.events):
            self.playing = False
        return self.cursor - before

    def status(self) -> dict:
        current = self.events[self.cursor - 1] if self.cursor else None
        return {
            "session_id": self.session_id,
            "event_count": len(self.events),
            "cursor": self.cursor,
            "playing": self.playing,
            "speed": self.speed,
            "event_time": current.event_timestamp.isoformat() if current else None,
            "isolated_from_live_ledger": True,
            "meta": self.meta,
            "markers": self.markers,
        }

    def _advance_to(self, index: int) -> None:
        while self.cursor < index:
            self.books.on_event(self.events[self.cursor])
            self.cursor += 1

    def _build_checkpoints(self) -> None:
        self.checkpoints = [(0, {})]
        self.depth_samples = {}
        books = BookService()
        for index, event in enumerate(self.events, start=1):
            books.on_event(event)
            if index % 250 == 0:
                self.checkpoints.append((index, _capture(books)))
            if index % 40 == 0:
                _sample_depth(self.depth_samples, books, index)

    def _checkpoint_at(self, index: int) -> tuple[int, dict]:
        chosen = self.checkpoints[0]
        for point in self.checkpoints:
            if point[0] <= index:
                chosen = point
            else:
                break
        return chosen

    def _build_markers(self) -> None:
        sizes = [event.quantity_lots for event in self.events if event.event_type == "trade"]
        if not sizes:
            self.markers = []
            return
        ordered = sorted(sizes)
        median = ordered[len(ordered) // 2]
        large = max(median * 4, 1)
        markers = []
        last_sequence: dict[str, int] = {}
        for index, event in enumerate(self.events):
            previous = last_sequence.get(event.symbol)
            if previous is not None and event.sequence_number > previous + 1:
                markers.append(
                    {
                        "index": index,
                        "kind": "feed_disruption",
                        "symbol": event.symbol,
                        "time": event.event_timestamp.isoformat(),
                        "detail": f"sequence gap {previous + 1}..{event.sequence_number - 1}",
                    }
                )
            last_sequence[event.symbol] = event.sequence_number
            if event.event_type == "trade" and event.quantity_lots >= large:
                markers.append(
                    {
                        "index": index,
                        "kind": "large_trade",
                        "symbol": event.symbol,
                        "time": event.event_timestamp.isoformat(),
                        "detail": f"{event.symbol} {event.quantity_lots} lots",
                    }
                )
            elif event.event_type == "feed_quality" and event.quality == "gap":
                markers.append(
                    {
                        "index": index,
                        "kind": "feed_disruption",
                        "symbol": event.symbol,
                        "time": event.event_timestamp.isoformat(),
                        "detail": event.detail,
                    }
                )
            elif event.event_type == "market_status" and event.status in {"halt", "closed"}:
                markers.append(
                    {
                        "index": index,
                        "kind": "trading_status",
                        "symbol": event.symbol,
                        "time": event.event_timestamp.isoformat(),
                        "detail": event.status,
                    }
                )
        self.markers = markers[:80]


def _sample_depth(store: dict[str, list], books: BookService, index: int) -> None:
    """Keep a reconstructed ladder. These are not invented from the latest book."""

    for symbol, book in books.books.items():
        if not book.initialised:
            continue
        bids = sorted(book.bids.items(), key=lambda item: item[0], reverse=True)[:6]
        asks = sorted(book.asks.items(), key=lambda item: item[0])[:6]
        store.setdefault(symbol, []).append(
            {
                "index": index,
                "bids": [{"price_ticks": price, "quantity_lots": level.quantity_lots} for price, level in bids],
                "asks": [{"price_ticks": price, "quantity_lots": level.quantity_lots} for price, level in asks],
            }
        )


def _capture(books: BookService) -> dict:
    captured = {}
    for symbol, book in books.books.items():
        captured[symbol] = {
            "bids": {price: (level.quantity_lots, level.order_count) for price, level in book.bids.items()},
            "asks": {price: (level.quantity_lots, level.order_count) for price, level in book.asks.items()},
            "last_seq": book.last_seq,
            "stale": book.stale,
            "gap_count": book.gap_count,
            "duplicate_count": book.duplicate_count,
            "quarantine_count": book.quarantine_count,
            "detail": book.detail,
            "initialised": book.initialised,
        }
    return captured


def _restore(books: BookService, state: dict) -> None:
    for symbol, payload in state.items():
        book = books.book(symbol)
        book.bids = {
            int(price): LevelState(qty, count) for price, (qty, count) in payload["bids"].items()
        }
        book.asks = {
            int(price): LevelState(qty, count) for price, (qty, count) in payload["asks"].items()
        }
        book.last_seq = payload["last_seq"]
        book.stale = payload["stale"]
        book.gap_count = payload["gap_count"]
        book.duplicate_count = payload["duplicate_count"]
        book.quarantine_count = payload["quarantine_count"]
        book.detail = payload["detail"]
        book.initialised = payload["initialised"]


def read_meta(path: Path) -> dict:
    meta_path = path.parent / "meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))
