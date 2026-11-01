"""Domain tests for prices, books, fills, and P&L."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from marketstream.core.instruments import get_instrument
from marketstream.core.models import (
    BookDeltaEvent,
    BookLevel,
    BookSnapshotEvent,
    OrderRequest,
    TradeEvent,
)
from marketstream.core.money import from_ticks, to_ticks
from marketstream.execution.engine import ExecutionEngine
from marketstream.feed.handler import FeedHandler
from marketstream.market.analytics import ohlc, vwap_ticks
from marketstream.market.book import BookService
from marketstream.portfolio.pnl import Mark, PositionBook
from marketstream.risk.engine import RiskEngine
from marketstream.simulation.engine import Simulator


T0 = datetime(2026, 6, 2, 14, 30, tzinfo=timezone.utc)


def _event_base(**kwargs):
    base = dict(
        event_id="e",
        session_id="s",
        venue="MSX",
        symbol="ATHR",
        sequence_number=1,
        event_timestamp=T0,
        receive_timestamp=T0,
    )
    base.update(kwargs)
    return base


def test_tick_alignment_rejects_off_tick_prices():
    instrument = get_instrument("ATHR")
    assert to_ticks(Decimal("186.40"), instrument.tick_size) == 18640
    with pytest.raises(ValueError):
        to_ticks(Decimal("186.401"), instrument.tick_size)


def test_vwap_and_ohlc_match_hand_calculation():
    trades = [
        TradeEvent(**_event_base(sequence_number=1, event_id="1", trade_id="t1", price_ticks=1000, quantity_lots=100, aggressor_side="buy")),
        TradeEvent(**_event_base(sequence_number=2, event_id="2", trade_id="t2", price_ticks=1200, quantity_lots=50, aggressor_side="buy")),
        TradeEvent(**_event_base(sequence_number=3, event_id="3", trade_id="t3", price_ticks=1100, quantity_lots=50, aggressor_side="sell")),
    ]
    assert vwap_ticks(trades) == Decimal("1075")
    bars = ohlc(trades, 60)
    assert len(bars) == 1
    assert bars[0]["open_ticks"] == 1000
    assert bars[0]["high_ticks"] == 1200
    assert bars[0]["low_ticks"] == 1000
    assert bars[0]["close_ticks"] == 1100
    assert bars[0]["volume_lots"] == 200
    assert bars[0]["vwap_ticks"] == Decimal("1075")


def test_book_reconstructs_snapshot_and_absolute_deltas():
    books = BookService()
    books.on_event(
        BookSnapshotEvent(
            **_event_base(sequence_number=1, event_id="snap"),
            levels=[
                BookLevel(side="bid", price_ticks=100, quantity_lots=10),
                BookLevel(side="bid", price_ticks=99, quantity_lots=8),
                BookLevel(side="ask", price_ticks=102, quantity_lots=7),
                BookLevel(side="ask", price_ticks=103, quantity_lots=9),
            ],
            depth=4,
        )
    )
    books.on_event(
        BookDeltaEvent(
            **_event_base(sequence_number=2, event_id="d1"),
            side="bid",
            price_ticks=100,
            quantity_lots=15,
            update_action="upsert",
        )
    )
    books.on_event(
        BookDeltaEvent(
            **_event_base(sequence_number=3, event_id="d2"),
            side="ask",
            price_ticks=102,
            quantity_lots=0,
            update_action="delete",
        )
    )
    view = books.view("ATHR")
    assert view.health.state == "live"
    assert view.health.stale is False
    assert view.best_bid_ticks == 100
    assert view.best_ask_ticks == 103
    assert view.spread_ticks == 3
    assert view.bids[0]["quantity_lots"] == 15
    assert view.bids[0]["cumulative_lots"] == 15
    assert view.bids[1]["cumulative_lots"] == 23
    assert all(level["price_ticks"] != 102 for level in view.asks)
    # (103 * 15 + 100 * 9) / 24
    assert view.microprice_ticks == (Decimal(103) * 15 + Decimal(100) * 9) / Decimal(24)


def test_gap_stales_the_book_until_a_snapshot():
    books = BookService()
    books.on_event(
        BookSnapshotEvent(
            **_event_base(sequence_number=1, event_id="snap"),
            levels=[BookLevel(side="bid", price_ticks=100, quantity_lots=5), BookLevel(side="ask", price_ticks=101, quantity_lots=5)],
            depth=2,
        )
    )
    result = books.on_event(
        BookDeltaEvent(
            **_event_base(sequence_number=4, event_id="gap"),
            side="bid",
            price_ticks=100,
            quantity_lots=9,
            update_action="upsert",
        )
    )
    assert result == "quarantine"
    assert books.view("ATHR").health.stale is True
    assert books.view("ATHR").health.gap_count == 1
    assert books.view("ATHR").bids[0]["quantity_lots"] == 5
    books.on_event(
        BookDeltaEvent(
            **_event_base(sequence_number=5, event_id="still-gapped"),
            side="bid",
            price_ticks=100,
            quantity_lots=1,
            update_action="upsert",
        )
    )
    assert books.view("ATHR").health.gap_count == 1
    assert books.view("ATHR").health.stale is True
    books.on_event(
        BookSnapshotEvent(
            **_event_base(sequence_number=6, event_id="recover"),
            levels=[BookLevel(side="bid", price_ticks=110, quantity_lots=3), BookLevel(side="ask", price_ticks=112, quantity_lots=4)],
            depth=2,
        )
    )
    recovered = books.view("ATHR")
    assert recovered.health.stale is False
    assert recovered.best_bid_ticks == 110
    assert recovered.best_ask_ticks == 112


def test_duplicate_sequence_is_ignored():
    books = BookService()
    snapshot = BookSnapshotEvent(
        **_event_base(sequence_number=1, event_id="snap"),
        levels=[BookLevel(side="bid", price_ticks=10, quantity_lots=1), BookLevel(side="ask", price_ticks=12, quantity_lots=1)],
        depth=2,
    )
    books.on_event(snapshot)
    assert books.on_event(snapshot) == "duplicate"
    assert books.view("ATHR").health.duplicate_count == 1


def test_simulator_is_deterministic_and_keeps_a_two_sided_book():
    left = Simulator("s", ["ATHR", "HLX"], seed=7)
    right = Simulator("s", ["ATHR", "HLX"], seed=7)
    left_events = [event.model_dump(mode="json") for _ in range(25) for event in left.pulse()]
    right_events = [event.model_dump(mode="json") for _ in range(25) for event in right.pulse()]
    assert left_events == right_events
    fresh = Simulator("s", ["ATHR", "HLX"], seed=7)
    books = BookService()
    feed = FeedHandler()
    for _ in range(3):
        for event in feed.handle_many(fresh.pulse()).accepted:
            books.on_event(event)
    view = books.view("ATHR")
    assert view.health.stale is False
    assert view.best_bid_ticks is not None
    assert view.best_ask_ticks is not None
    assert view.best_bid_ticks < view.best_ask_ticks


def test_low_liquidity_regime_widens_the_spread_and_cuts_depth():
    calm = _book_after("normal", 11)
    thin = _book_after("low_liquidity", 303)
    assert thin.spread_ticks > calm.spread_ticks
    assert thin.bid_depth_lots < calm.bid_depth_lots


def _book_after(regime: str, seed: int):
    sim = Simulator("s", ["ATHR"], seed=seed)
    sim.set_regime(regime)
    books = BookService()
    feed = FeedHandler()
    for _ in range(8):
        for event in feed.handle_many(sim.pulse()).accepted:
            books.on_event(event)
    return books.view("ATHR")


def _live_book():
    books = BookService()
    books.on_event(
        BookSnapshotEvent(
            **_event_base(sequence_number=1, event_id="snap"),
            levels=[
                BookLevel(side="bid", price_ticks=10000, quantity_lots=50),
                BookLevel(side="bid", price_ticks=9990, quantity_lots=40),
                BookLevel(side="ask", price_ticks=10010, quantity_lots=30),
                BookLevel(side="ask", price_ticks=10020, quantity_lots=40),
            ],
            depth=4,
        )
    )
    return books


def test_market_buy_walks_asks_and_cancels_the_remainder():
    books = _live_book()
    engine = ExecutionEngine(commission_bps=Decimal("0"))
    request = OrderRequest(client_order_id="c1", symbol="ATHR", side="buy", order_type="market", quantity_lots=100)
    order, fills = engine.submit(request, books.view("ATHR"), "s", T0, None, None)
    assert order.status == "cancelled"
    assert order.filled_lots == 70
    assert fills[0].price_ticks == 10010
    assert fills[0].quantity_lots == 30
    assert fills[1].price_ticks == 10020
    again, more = engine.submit(request, books.view("ATHR"), "s", T0, None, None)
    assert again.order_id == order.order_id
    assert more == []


def test_limit_does_not_fill_at_a_worse_price_and_resting_needs_a_trade_through():
    books = _live_book()
    engine = ExecutionEngine(commission_bps=Decimal("0"))
    request = OrderRequest(
        client_order_id="bid",
        symbol="ATHR",
        side="buy",
        order_type="limit",
        quantity_lots=10,
        limit_price="100.00",
    )
    order, fills = engine.submit(request, books.view("ATHR"), "s", T0, None, None)
    assert fills == []
    assert order.status == "working"
    at_touch = TradeEvent(
        **_event_base(sequence_number=2, event_id="t", trade_id="t"),
        price_ticks=10000,
        quantity_lots=10,
        aggressor_side="sell",
    )
    assert engine.on_trade(at_touch, T0, "live") == []
    through = TradeEvent(
        **_event_base(sequence_number=3, event_id="t2", trade_id="t2"),
        price_ticks=9990,
        quantity_lots=4,
        aggressor_side="sell",
    )
    filled = engine.on_trade(through, T0, "live")
    assert filled[0].quantity_lots == 4
    assert filled[0].price_ticks == 9990
    assert engine.orders[order.order_id].status == "partially_filled"


def test_risk_limit_rejects_with_the_rule_name():
    engine = ExecutionEngine()
    risk = RiskEngine()
    instrument = get_instrument("ATHR")
    request = OrderRequest(client_order_id="big", symbol="ATHR", side="buy", order_type="market", quantity_lots=5000)
    rule, reason = risk.check_order(request, instrument, 18640, {}, {}, Decimal("0"))
    assert rule == "max_order_quantity"
    books = _live_book()
    order, fills = engine.submit(request, books.view("ATHR"), "s", T0, rule, reason)
    assert order.status == "rejected"
    assert order.reject_rule == "max_order_quantity"
    assert fills == []
    assert reason


def test_weighted_average_long_short_and_cash_reconciliation():
    account = PositionBook(Decimal("1000000"))
    instrument = get_instrument("ATHR")
    engine = ExecutionEngine(commission_bps=Decimal("0"))
    books = _live_book()
    # Direct fills, so the numbers are the ones in the assertion rather than the book walk.
    from marketstream.core.models import FillRecord

    def fill(execution_id: str, side: str, lots: int, ticks: int) -> FillRecord:
        price = from_ticks(ticks, instrument.tick_size)
        return FillRecord(
            execution_id=execution_id,
            order_id="live-1",
            client_order_id="c",
            session_id="s",
            symbol="ATHR",
            side=side,  # type: ignore[arg-type]
            quantity_lots=lots,
            price_ticks=ticks,
            fee="1.0000",
            fee_currency="USD",
            timestamp=T0,
            liquidity="take",
            assumptions="test",
        )

    account.apply_fill(fill("e1", "buy", 100, 1000))  # 10.00
    account.apply_fill(fill("e2", "buy", 100, 1200))  # 12.00
    position = account.positions["ATHR"]
    assert position.quantity_lots == 200
    assert position.average_cost == Decimal("11")
    mark = Mark(price=Decimal("13"), source="mid", stale=False, timestamp=T0)
    view = account.view("ATHR", mark, instrument)
    assert view["unrealised_pnl"] == "400.00"
    account.apply_fill(fill("e3", "sell", 150, 1300))
    position = account.positions["ATHR"]
    assert position.quantity_lots == 50
    assert position.average_cost == Decimal("11")
    assert position.realised == Decimal("300")
    view = account.view("ATHR", mark, instrument)
    assert view["unrealised_pnl"] == "100.00"
    assert view["fees"] == "3.0000"
    assert view["net_pnl"] == "397.00"

    short = PositionBook(Decimal("1000000"))
    short.apply_fill(fill("s1", "sell", 100, 1000))
    short.apply_fill(fill("s2", "buy", 40, 800))
    assert short.positions["ATHR"].quantity_lots == -60
    assert short.positions["ATHR"].average_cost == Decimal("10")
    assert short.positions["ATHR"].realised == Decimal("80")
    rebuilt = PositionBook(Decimal("1000000"))
    rebuilt.rebuild(
        [
            fill("e1", "buy", 100, 1000),
            fill("e2", "buy", 100, 1200),
            fill("e3", "sell", 150, 1300),
        ]
    )
    assert rebuilt.positions["ATHR"].realised == account.positions["ATHR"].realised
    assert rebuilt.cash["USD"] == account.cash["USD"]


def test_flat_round_trip_cash_equals_net_pnl():
    account = PositionBook(Decimal("1000000"))
    from marketstream.core.models import FillRecord

    def fill(execution_id: str, side: str, lots: int, ticks: int, fee: str) -> FillRecord:
        return FillRecord(
            execution_id=execution_id,
            order_id="live-1",
            client_order_id="c",
            session_id="s",
            symbol="ATHR",
            side=side,  # type: ignore[arg-type]
            quantity_lots=lots,
            price_ticks=ticks,
            fee=fee,
            fee_currency="USD",
            timestamp=T0,
            liquidity="take",
            assumptions="test",
        )

    account.apply_fill(fill("a", "buy", 10, 10000, "1.0000"))
    account.apply_fill(fill("b", "sell", 10, 11000, "1.0000"))
    instrument = get_instrument("ATHR")
    view = account.view("ATHR", Mark(price=Decimal("110"), source="mid", stale=False, timestamp=T0), instrument)
    assert account.positions["ATHR"].quantity_lots == 0
    assert view["realised_pnl"] == "100.00"
    assert view["net_pnl"] == "98.00"
    assert account.cash["USD"] == Decimal("1000098.00")


def test_feed_quarantines_unknown_symbols_and_bad_quantities():
    feed = FeedHandler()
    bad_symbol = TradeEvent(
        **_event_base(symbol="NOPE", sequence_number=1, event_id="x", trade_id="t"),
        price_ticks=10,
        quantity_lots=1,
        aggressor_side="buy",
    )
    bad_qty = TradeEvent(
        **_event_base(sequence_number=1, event_id="y", trade_id="t2"),
        price_ticks=10,
        quantity_lots=-5,
        aggressor_side="buy",
    )
    assert feed.handle(bad_symbol) is None
    assert feed.handle(bad_qty) is None
    assert feed.quarantined == 2


def test_decision_spread_rule_records_inputs():
    from marketstream.decision_engine.rules import DecisionEngine

    engine = DecisionEngine()
    decisions = engine.evaluate("ATHR", {"spread_bps": "20.00", "imbalance": "0.10"}, T0)
    spread = next(item for item in decisions if item.rule_id == "spread_widening")
    assert spread.result == "trigger"
    assert spread.inputs["spread_bps"] == "20.00"
    assert "8" in spread.explanation


def test_replay_depth_samples_follow_the_cursor(tmp_path):
    from marketstream.replay.engine import ReplayStudio

    simulator = Simulator("replay-test", ["ATHR"], seed=3, start=T0)
    lines = []
    for _ in range(30):
        for event in simulator.pulse():
            lines.append(event.model_dump_json())
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    studio = ReplayStudio()
    studio.load_file(path)
    samples = studio.depth_samples["ATHR"]
    assert samples
    studio.seek(40)
    visible = [row for row in samples if row["index"] <= studio.cursor]
    assert visible[-1]["index"] <= 40
    assert all(row["bids"] or row["asks"] for row in visible)
    studio.seek_time("2026-06-02T14:30:00+00:00")
    assert studio.cursor >= 1
    assert studio.cursor < 40
