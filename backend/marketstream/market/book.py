"""Level 2 market-by-price reconstruction.

The book is built only from snapshots and absolute deltas. Trades do not
mutate levels. Individual order identities are not invented.

A sequence gap or an invalid book update marks the book stale. Deltas
are quarantined until a fresh snapshot recovers the book. A stale book
is never reported as healthy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from marketstream.core.instruments import Instrument
from marketstream.core.models import (
    BookDeltaEvent,
    BookLevel,
    BookSnapshotEvent,
    MarketEvent,
    QuoteEvent,
)


@dataclass
class LevelState:
    quantity_lots: int
    order_count: int | None = None


@dataclass
class BookHealth:
    state: str  # live, stale, empty, one_sided, locked, crossed
    stale: bool
    gap_count: int
    duplicate_count: int
    quarantine_count: int
    last_sequence: int | None
    last_event_timestamp: datetime | None
    detail: str = ""


@dataclass
class BookView:
    symbol: str
    bids: list[dict]
    asks: list[dict]
    best_bid_ticks: int | None
    best_ask_ticks: int | None
    mid_ticks: Decimal | None
    spread_ticks: int | None
    spread_bps: Decimal | None
    bid_depth_lots: int
    ask_depth_lots: int
    imbalance: Decimal | None
    top5_imbalance: Decimal | None
    microprice_ticks: Decimal | None
    bid_concentration: Decimal | None
    ask_concentration: Decimal | None
    health: BookHealth
    sequence: int | None
    event_timestamp: datetime | None

    def to_public(self, instrument: Instrument, price_fn, qty_fn) -> dict:
        def levels(rows: list[dict]) -> list[dict]:
            rendered = []
            for row in rows:
                rendered.append(
                    {
                        "price": price_fn(row["price_ticks"], instrument),
                        "price_ticks": row["price_ticks"],
                        "quantity_lots": row["quantity_lots"],
                        "quantity": qty_fn(row["quantity_lots"], instrument),
                        "cumulative_lots": row["cumulative_lots"],
                        "order_count": row["order_count"],
                    }
                )
            return rendered

        health = self.health
        return {
            "symbol": self.symbol,
            "bids": levels(self.bids),
            "asks": levels(self.asks),
            "best_bid": price_fn(self.best_bid_ticks, instrument) if self.best_bid_ticks is not None else None,
            "best_ask": price_fn(self.best_ask_ticks, instrument) if self.best_ask_ticks is not None else None,
            "best_bid_ticks": self.best_bid_ticks,
            "best_ask_ticks": self.best_ask_ticks,
            "mid": _fmt_mid(self.mid_ticks, instrument),
            "spread": price_fn(self.spread_ticks, instrument) if self.spread_ticks is not None else None,
            "spread_ticks": self.spread_ticks,
            "spread_bps": _fmt_decimal(self.spread_bps, 2),
            "bid_depth_lots": self.bid_depth_lots,
            "ask_depth_lots": self.ask_depth_lots,
            "imbalance": _fmt_decimal(self.imbalance, 4),
            "top5_imbalance": _fmt_decimal(self.top5_imbalance, 4),
            "microprice": _fmt_mid(self.microprice_ticks, instrument),
            "bid_concentration": _fmt_decimal(self.bid_concentration, 4),
            "ask_concentration": _fmt_decimal(self.ask_concentration, 4),
            "sequence": self.sequence,
            "event_timestamp": self.event_timestamp.isoformat() if self.event_timestamp else None,
            "health": {
                "state": health.state,
                "stale": health.stale,
                "gap_count": health.gap_count,
                "duplicate_count": health.duplicate_count,
                "quarantine_count": health.quarantine_count,
                "last_sequence": health.last_sequence,
                "detail": health.detail,
            },
            "simulated": True,
        }


def _fmt_decimal(value: Decimal | None, places: int) -> str | None:
    if value is None:
        return None
    return f"{value:.{places}f}"


def _fmt_mid(ticks: Decimal | None, instrument: Instrument) -> str | None:
    if ticks is None:
        return None
    price = ticks * instrument.tick_size
    return f"{price:.{instrument.price_precision}f}"


@dataclass
class SymbolBook:
    symbol: str
    bids: dict[int, LevelState] = field(default_factory=dict)
    asks: dict[int, LevelState] = field(default_factory=dict)
    last_seq: int | None = None
    stale: bool = False
    gap_count: int = 0
    duplicate_count: int = 0
    quarantine_count: int = 0
    detail: str = ""
    last_event_timestamp: datetime | None = None
    initialised: bool = False

    def on_event(self, event: MarketEvent) -> str:
        seq = event.sequence_number
        if self.last_seq is not None and seq <= self.last_seq:
            self.duplicate_count += 1
            self.detail = f"duplicate sequence {seq}"
            return "duplicate"

        gap = self.last_seq is not None and seq > self.last_seq + 1
        if gap and not self.stale:
            self.stale = True
            self.gap_count += 1
            self.detail = f"sequence gap {self.last_seq + 1}..{seq - 1}"

        if self.stale and event.event_type != "book_snapshot":
            self.quarantine_count += 1
            self.detail = self.detail or "book stale; waiting for snapshot"
            return "quarantine"

        if event.event_type == "book_snapshot":
            problem = self._validate_levels(event.levels)
            if problem:
                self.stale = True
                self.quarantine_count += 1
                self.last_seq = seq
                self.last_event_timestamp = event.event_timestamp
                self.detail = problem
                return "quarantine"
            self._apply_snapshot(event)
            self.stale = False
            self.initialised = True
            self.last_seq = seq
            self.last_event_timestamp = event.event_timestamp
            self.detail = "recovered from snapshot" if gap else ""
            return "snapshot"

        if event.event_type == "book_delta":
            problem = self._validate_delta(event)
            if problem:
                self.stale = True
                self.quarantine_count += 1
                self.last_seq = seq
                self.last_event_timestamp = event.event_timestamp
                self.detail = problem
                return "quarantine"
            self._apply_delta(event)
            self.last_seq = seq
            self.last_event_timestamp = event.event_timestamp
            return "delta"

        if event.event_type == "quote":
            self.last_seq = seq
            self.last_event_timestamp = event.event_timestamp
            mismatch = self._quote_mismatch(event)
            if mismatch:
                self.detail = mismatch
                return "mismatch"
            return "quote"

        self.last_seq = seq
        self.last_event_timestamp = event.event_timestamp
        return "advance"

    def _validate_levels(self, levels: list[BookLevel]) -> str | None:
        for level in levels:
            if level.price_ticks <= 0:
                return "invalid price on snapshot"
            if level.quantity_lots < 0:
                return "negative quantity on snapshot"
        return None

    def _validate_delta(self, event: BookDeltaEvent) -> str | None:
        if event.semantics != "absolute":
            return "only absolute book quantities are accepted"
        if event.price_ticks <= 0:
            return "invalid price on delta"
        if event.quantity_lots < 0:
            return "negative quantity on delta"
        return None

    def _apply_snapshot(self, event: BookSnapshotEvent) -> None:
        self.bids.clear()
        self.asks.clear()
        for level in event.levels:
            if level.quantity_lots == 0:
                continue
            target = self.bids if level.side == "bid" else self.asks
            target[level.price_ticks] = LevelState(level.quantity_lots, level.order_count)

    def _apply_delta(self, event: BookDeltaEvent) -> None:
        target = self.bids if event.side == "bid" else self.asks
        remove = event.update_action == "delete" or event.quantity_lots == 0
        if remove:
            target.pop(event.price_ticks, None)
            return
        target[event.price_ticks] = LevelState(event.quantity_lots, event.order_count)

    def _quote_mismatch(self, event: QuoteEvent) -> str | None:
        if not self.initialised or self.stale:
            return None
        best_bid = self._best_bid()
        best_ask = self._best_ask()
        if event.bid_ticks is not None and best_bid is not None and event.bid_ticks != best_bid:
            return "quote bid differs from reconstructed book"
        if event.ask_ticks is not None and best_ask is not None and event.ask_ticks != best_ask:
            return "quote ask differs from reconstructed book"
        return None

    def _best_bid(self) -> int | None:
        return max(self.bids) if self.bids else None

    def _best_ask(self) -> int | None:
        return min(self.asks) if self.asks else None

    def view(self) -> BookView:
        bid_prices = sorted(self.bids, reverse=True)
        ask_prices = sorted(self.asks)
        bids = _cumulative(
            [
                {
                    "price_ticks": price,
                    "quantity_lots": self.bids[price].quantity_lots,
                    "order_count": self.bids[price].order_count,
                }
                for price in bid_prices
            ]
        )
        asks = _cumulative(
            [
                {
                    "price_ticks": price,
                    "quantity_lots": self.asks[price].quantity_lots,
                    "order_count": self.asks[price].order_count,
                }
                for price in ask_prices
            ]
        )
        best_bid = bid_prices[0] if bid_prices else None
        best_ask = ask_prices[0] if ask_prices else None
        bid_depth = sum(level.quantity_lots for level in self.bids.values())
        ask_depth = sum(level.quantity_lots for level in self.asks.values())
        mid = spread = spread_bps = None
        micro = None
        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid
            mid = (Decimal(best_bid) + Decimal(best_ask)) / Decimal(2)
            if mid > 0 and spread is not None:
                spread_bps = (Decimal(spread) / mid) * Decimal(10000)
            bid_qty = self.bids[best_bid].quantity_lots
            ask_qty = self.asks[best_ask].quantity_lots
            if bid_qty + ask_qty > 0:
                # Size-weighted microprice. Heavier bid size pulls toward the ask.
                micro = (
                    Decimal(best_ask) * Decimal(bid_qty) + Decimal(best_bid) * Decimal(ask_qty)
                ) / Decimal(bid_qty + ask_qty)
        imbalance = _imbalance(bid_depth, ask_depth)
        top5_imbalance = _imbalance(
            sum(row["quantity_lots"] for row in bids[:5]),
            sum(row["quantity_lots"] for row in asks[:5]),
        )
        state = _structural_state(best_bid, best_ask, self.stale, self.initialised)
        health = BookHealth(
            state=state,
            stale=self.stale or not self.initialised,
            gap_count=self.gap_count,
            duplicate_count=self.duplicate_count,
            quarantine_count=self.quarantine_count,
            last_sequence=self.last_seq,
            last_event_timestamp=self.last_event_timestamp,
            detail="" if self.initialised else "waiting for snapshot",
        )
        if self.detail:
            health.detail = self.detail
        if not self.initialised:
            health.stale = True
            health.state = "stale"
        return BookView(
            symbol=self.symbol,
            bids=bids,
            asks=asks,
            best_bid_ticks=best_bid,
            best_ask_ticks=best_ask,
            mid_ticks=mid,
            spread_ticks=spread,
            spread_bps=spread_bps,
            bid_depth_lots=bid_depth,
            ask_depth_lots=ask_depth,
            imbalance=imbalance,
            top5_imbalance=top5_imbalance,
            microprice_ticks=micro,
            bid_concentration=_concentration(bids),
            ask_concentration=_concentration(asks),
            health=health,
            sequence=self.last_seq,
            event_timestamp=self.last_event_timestamp,
        )


def _cumulative(rows: list[dict]) -> list[dict]:
    running = 0
    rendered = []
    for row in rows:
        running += row["quantity_lots"]
        rendered.append({**row, "cumulative_lots": running})
    return rendered


def _imbalance(bid: int, ask: int) -> Decimal | None:
    total = bid + ask
    if total <= 0:
        return None
    return (Decimal(bid) - Decimal(ask)) / Decimal(total)


def _concentration(rows: list[dict]) -> Decimal | None:
    if not rows:
        return None
    total = rows[-1]["cumulative_lots"] if rows else 0
    if total <= 0:
        return None
    return Decimal(rows[0]["quantity_lots"]) / Decimal(total)


def _structural_state(
    best_bid: int | None,
    best_ask: int | None,
    stale: bool,
    initialised: bool,
) -> str:
    if stale or not initialised:
        return "stale"
    if best_bid is None and best_ask is None:
        return "empty"
    if best_bid is None or best_ask is None:
        return "one_sided"
    if best_bid > best_ask:
        return "crossed"
    if best_bid == best_ask:
        return "locked"
    return "live"


class BookService:
    """One reconstructed book per symbol, plus a short snapshot history."""

    def __init__(self) -> None:
        self.books: dict[str, SymbolBook] = {}
        self.history: dict[str, list[dict]] = {}

    def book(self, symbol: str) -> SymbolBook:
        if symbol not in self.books:
            self.books[symbol] = SymbolBook(symbol)
            self.history[symbol] = []
        return self.books[symbol]

    def on_event(self, event: MarketEvent) -> str:
        result = self.book(event.symbol).on_event(event)
        if event.event_type == "book_snapshot" and result == "snapshot":
            view = self.book(event.symbol).view()
            self.history[event.symbol].append(
                {
                    "sequence": event.sequence_number,
                    "event_timestamp": event.event_timestamp.isoformat(),
                    "bids": view.bids[:12],
                    "asks": view.asks[:12],
                    "spread_ticks": view.spread_ticks,
                    "imbalance": str(view.imbalance) if view.imbalance is not None else None,
                    "stale": view.health.stale,
                }
            )
            self.history[event.symbol] = self.history[event.symbol][-180:]
        return result

    def view(self, symbol: str) -> BookView:
        return self.book(symbol).view()

    def depth_history(self, symbol: str) -> list[dict]:
        return list(self.history.get(symbol, []))
