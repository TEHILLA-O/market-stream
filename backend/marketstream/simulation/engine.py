"""Deterministic synthetic market simulator.

A single `random.Random` stream, a fixed symbol order, and an explicit
virtual clock make identical seeds produce identical events. Wall-clock
speed only changes how fast pulses are released, not their contents.

The public book is independent of paper orders. Fills elsewhere do not
remove displayed liquidity.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from marketstream.core.instruments import Instrument, get_instrument
from marketstream.core.models import (
    BookDeltaEvent,
    BookLevel,
    BookSnapshotEvent,
    FeedQualityEvent,
    HeartbeatEvent,
    MarketStatusEvent,
    QuoteEvent,
    TradeEvent,
)

REGIMES: dict[str, dict] = {
    "normal": {"vol": 0.00035, "drift": 0.0, "spread": 1.0, "depth": 1.0, "trade_p": 0.72, "phase": "open"},
    "low_liquidity": {"vol": 0.00028, "drift": 0.0, "spread": 2.4, "depth": 0.22, "trade_p": 0.34, "phase": "open"},
    "high_volatility": {"vol": 0.0018, "drift": 0.0, "spread": 1.9, "depth": 0.62, "trade_p": 0.84, "phase": "open"},
    "uptrend": {"vol": 0.00055, "drift": 0.00022, "spread": 1.05, "depth": 0.9, "trade_p": 0.74, "phase": "open"},
    "downtrend": {"vol": 0.00055, "drift": -0.00022, "spread": 1.2, "depth": 0.82, "trade_p": 0.74, "phase": "open"},
    "sideways": {"vol": 0.00016, "drift": 0.0, "spread": 0.9, "depth": 1.15, "trade_p": 0.48, "phase": "open"},
    "liquidity_withdrawal": {
        "vol": 0.0007,
        "drift": 0.0,
        "spread": 3.8,
        "depth": 0.1,
        "trade_p": 0.4,
        "phase": "open",
    },
    "price_shock": {"vol": 0.0032, "drift": 0.0, "spread": 4.2, "depth": 0.35, "trade_p": 0.9, "phase": "open", "shock": 0.018},
    "opening": {"vol": 0.0011, "drift": 0.00008, "spread": 2.6, "depth": 0.4, "trade_p": 0.88, "phase": "open"},
    "closing": {"vol": 0.0009, "drift": -0.00005, "spread": 1.7, "depth": 0.48, "trade_p": 0.8, "phase": "closed"},
}


@dataclass
class SymbolState:
    instrument: Instrument
    mid_ticks: int
    bids: dict[int, int] = field(default_factory=dict)
    asks: dict[int, int] = field(default_factory=dict)
    sequence: int = 0
    trade_no: int = 0
    shocked: bool = False
    phase: str = "open"


class Simulator:
    def __init__(
        self,
        session_id: str,
        symbols: list[str],
        seed: int,
        start: datetime | None = None,
    ) -> None:
        self.session_id = session_id
        self.seed = seed
        self.rng = random.Random(seed)
        self.clock = start or datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc)
        self.pulse_seconds = 1.0
        self.regime = "normal"
        self.symbols = list(symbols)
        self.states = {
            symbol: SymbolState(
                instrument=get_instrument(symbol),
                mid_ticks=_reference_ticks(get_instrument(symbol)),
            )
            for symbol in symbols
        }
        self.pulse_index = 0
        self.running = True
        self.paused = False
        self.pending_gap = 0
        self.force_snapshot = False
        self.suppress_snapshot = False
        self.pulses_until_recovery = 0
        self.halted = False
        self._source = "simulator"

    def set_regime(self, regime: str) -> None:
        if regime not in REGIMES:
            raise ValueError(f"unknown regime {regime}")
        self.regime = regime
        for state in self.states.values():
            state.shocked = False

    def inject_gap(self, skipped: int = 4) -> None:
        """Skip sequence numbers on the next pulse, then recover with a snapshot.

        The gap and the recovering snapshot are on different pulses so the
        book is observably stale in between.
        """

        self.pending_gap += skipped
        self.suppress_snapshot = True
        self.pulses_until_recovery = 2

    def pulse(self) -> list:
        """Advance the virtual clock by one pulse and emit every symbol."""

        self.pulse_index += 1
        self.clock += timedelta(seconds=self.pulse_seconds)
        if self.pulses_until_recovery:
            self.pulses_until_recovery -= 1
            if self.pulses_until_recovery == 0:
                self.force_snapshot = True
                self.suppress_snapshot = False
        events = []
        regime = REGIMES[self.regime]
        for symbol in self.symbols:
            events.extend(self._pulse_symbol(self.states[symbol], regime))
        self.force_snapshot = False
        return events

    def _next_sequence(self, state: SymbolState) -> int:
        state.sequence += 1
        if self.pending_gap:
            state.sequence += self.pending_gap
            self.pending_gap = 0
        return state.sequence

    def _stamp(self, state: SymbolState, received: datetime | None = None):
        seq = self._next_sequence(state)
        event_time = self.clock
        receive = received or event_time
        event_id = f"{self.session_id}:{state.instrument.symbol}:{seq}"
        return seq, event_time, receive, event_id

    def _pulse_symbol(self, state: SymbolState, regime: dict) -> list:
        instrument = state.instrument
        events = []
        phase = regime["phase"]
        if self.halted:
            phase = "halt"
        if phase != state.phase:
            state.phase = phase
            seq, event_time, receive, event_id = self._stamp(state)
            events.append(
                MarketStatusEvent(
                    event_id=event_id,
                    session_id=self.session_id,
                    venue=instrument.venue,
                    symbol=instrument.symbol,
                    sequence_number=seq,
                    event_timestamp=event_time,
                    receive_timestamp=receive,
                    status=phase,  # type: ignore[arg-type]
                    reason=f"regime:{self.regime}",
                    regime=self.regime,
                )
            )
        if phase in {"closed", "halt"}:
            seq, event_time, receive, event_id = self._stamp(state)
            events.append(
                HeartbeatEvent(
                    event_id=event_id,
                    session_id=self.session_id,
                    venue=instrument.venue,
                    symbol=instrument.symbol,
                    sequence_number=seq,
                    event_timestamp=event_time,
                    receive_timestamp=receive,
                    last_sequence=seq,
                )
            )
            return events

        self._evolve(state, regime)
        target_bids, target_asks = self._target_book(state, regime)
        force_snapshot = not self.suppress_snapshot and (
            self.pulse_index == 1 or self.pulse_index % 20 == 0 or not state.bids or self.force_snapshot
        )
        if force_snapshot:
            events.extend(self._emit_snapshot(state, target_bids, target_asks))
        else:
            events.extend(self._emit_deltas(state, target_bids, target_asks))
        state.bids = target_bids
        state.asks = target_asks
        best_bid = max(state.bids) if state.bids else None
        best_ask = min(state.asks) if state.asks else None
        seq, event_time, receive, event_id = self._stamp(state)
        events.append(
            QuoteEvent(
                event_id=event_id,
                session_id=self.session_id,
                venue=instrument.venue,
                symbol=instrument.symbol,
                sequence_number=seq,
                event_timestamp=event_time,
                receive_timestamp=receive,
                bid_ticks=best_bid,
                ask_ticks=best_ask,
                bid_quantity_lots=state.bids.get(best_bid, 0) if best_bid is not None else 0,
                ask_quantity_lots=state.asks.get(best_ask, 0) if best_ask is not None else 0,
            )
        )
        if best_bid is not None and best_ask is not None and self.rng.random() < regime["trade_p"]:
            events.extend(self._emit_trade(state, best_bid, best_ask, regime))
        return events

    def _evolve(self, state: SymbolState, regime: dict) -> None:
        shock = 0.0
        if regime.get("shock") and not state.shocked:
            shock = float(regime["shock"]) if self.rng.random() < 0.5 else -float(regime["shock"])
            state.shocked = True
        log_return = regime["drift"] + regime["vol"] * self.rng.gauss(0, 1) + shock
        stepped = int(round(state.mid_ticks * math.exp(log_return)))
        state.mid_ticks = max(2, stepped)

    def _target_book(self, state: SymbolState, regime: dict) -> tuple[dict[int, int], dict[int, int]]:
        instrument = state.instrument
        half = max(1, int(round(instrument.base_spread_ticks * regime["spread"])))
        levels = 6 if regime["depth"] >= 0.5 else 3
        bids: dict[int, int] = {}
        asks: dict[int, int] = {}
        for index in range(levels):
            decay = 0.74 ** index
            noise_bid = 0.7 + 0.6 * self.rng.random()
            noise_ask = 0.7 + 0.6 * self.rng.random()
            bid_qty = max(1, int(instrument.base_depth_lots * regime["depth"] * decay * noise_bid))
            ask_qty = max(1, int(instrument.base_depth_lots * regime["depth"] * decay * noise_ask))
            bid_px = state.mid_ticks - half - index
            ask_px = state.mid_ticks + half + index
            if bid_px > 0:
                bids[bid_px] = bid_qty
            asks[ask_px] = ask_qty
        return bids, asks

    def _emit_snapshot(self, state: SymbolState, bids: dict[int, int], asks: dict[int, int]) -> list:
        instrument = state.instrument
        seq, event_time, receive, event_id = self._stamp(state)
        levels = [
            BookLevel(side="bid", price_ticks=price, quantity_lots=qty, order_count=max(1, qty // 20))
            for price, qty in sorted(bids.items(), reverse=True)
        ] + [
            BookLevel(side="ask", price_ticks=price, quantity_lots=qty, order_count=max(1, qty // 20))
            for price, qty in sorted(asks.items())
        ]
        return [
            BookSnapshotEvent(
                event_id=event_id,
                session_id=self.session_id,
                venue=instrument.venue,
                symbol=instrument.symbol,
                sequence_number=seq,
                event_timestamp=event_time,
                receive_timestamp=receive,
                levels=levels,
                depth=len(levels),
            )
        ]

    def _emit_deltas(self, state: SymbolState, bids: dict[int, int], asks: dict[int, int]) -> list:
        events = []
        events.extend(self._diff(state, "bid", state.bids, bids))
        events.extend(self._diff(state, "ask", state.asks, asks))
        return events

    def _diff(self, state: SymbolState, side: str, previous: dict[int, int], target: dict[int, int]) -> list:
        instrument = state.instrument
        events = []
        prices = sorted(set(previous) | set(target), reverse=(side == "bid"))
        for price in prices:
            old = previous.get(price)
            new = target.get(price)
            if old == new:
                continue
            seq, event_time, receive, event_id = self._stamp(state)
            if new is None or new == 0:
                events.append(
                    BookDeltaEvent(
                        event_id=event_id,
                        session_id=self.session_id,
                        venue=instrument.venue,
                        symbol=instrument.symbol,
                        sequence_number=seq,
                        event_timestamp=event_time,
                        receive_timestamp=receive,
                        side=side,  # type: ignore[arg-type]
                        price_ticks=price,
                        quantity_lots=0,
                        update_action="delete",
                    )
                )
            else:
                events.append(
                    BookDeltaEvent(
                        event_id=event_id,
                        session_id=self.session_id,
                        venue=instrument.venue,
                        symbol=instrument.symbol,
                        sequence_number=seq,
                        event_timestamp=event_time,
                        receive_timestamp=receive,
                        side=side,  # type: ignore[arg-type]
                        price_ticks=price,
                        quantity_lots=new,
                        update_action="upsert",
                        order_count=max(1, new // 20),
                    )
                )
        return events

    def _emit_trade(self, state: SymbolState, best_bid: int, best_ask: int, regime: dict) -> list:
        instrument = state.instrument
        # Drift tilts aggressor, but the print still has to be at the touch.
        buy_bias = 0.5 + max(-0.35, min(0.35, regime["drift"] * 800))
        aggressor = "buy" if self.rng.random() < buy_bias else "sell"
        price = best_ask if aggressor == "buy" else best_bid
        displayed = state.asks[price] if aggressor == "buy" else state.bids[price]
        quantity = max(1, int(displayed * (0.05 + 0.25 * self.rng.random())))
        quantity = min(quantity, displayed)
        state.trade_no += 1
        seq, event_time, receive, event_id = self._stamp(state)
        # The print does not itself change the reconstructed book.
        # A later absolute delta or snapshot is the only book mutation.
        trade = TradeEvent(
            event_id=event_id,
            session_id=self.session_id,
            venue=instrument.venue,
            symbol=instrument.symbol,
            sequence_number=seq,
            event_timestamp=event_time,
            receive_timestamp=receive,
            trade_id=f"{instrument.symbol}-{self.session_id}-{state.trade_no}",
            price_ticks=price,
            quantity_lots=quantity,
            aggressor_side=aggressor,  # type: ignore[arg-type]
            trade_conditions=["synthetic"],
        )
        return [trade]


def _reference_ticks(instrument: Instrument) -> int:
    ticks = instrument.reference_price / instrument.tick_size
    return int(ticks)
