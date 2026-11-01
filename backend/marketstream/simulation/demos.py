"""Deterministic demonstration sessions written as event logs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from marketstream.core.models import OrderRequest
from marketstream.execution.engine import ExecutionEngine
from marketstream.feed.handler import FeedHandler
from marketstream.market.book import BookService
from marketstream.portfolio.pnl import PositionBook
from marketstream.risk.engine import RiskEngine
from marketstream.simulation.engine import Simulator

DEMO_SPECS: list[dict] = [
    {
        "session_id": "demo-calm",
        "title": "Calm market",
        "summary": "Moderate volume, stable spreads, ordinary price movement.",
        "seed": 101,
        "script": [("normal", 100)],
    },
    {
        "session_id": "demo-shock",
        "title": "Volatility shock",
        "summary": "A calm open, then a price shock with wider spreads.",
        "seed": 202,
        "script": [("normal", 40), ("price_shock", 70)],
    },
    {
        "session_id": "demo-liquidity",
        "title": "Liquidity withdrawal",
        "summary": "Displayed depth falls and spreads widen.",
        "seed": 303,
        "script": [("normal", 30), ("liquidity_withdrawal", 70)],
    },
    {
        "session_id": "demo-disruption",
        "title": "Feed disruption",
        "summary": "A sequence gap marks the book stale until the next snapshot.",
        "seed": 404,
        "script": [("normal", 80)],
        "gap_at": 35,
    },
    {
        "session_id": "demo-strategy",
        "title": "Trading strategy",
        "summary": "A transparent mean-reversion paper rule, with fills, fees, and P&L.",
        "seed": 505,
        "script": [("sideways", 30), ("uptrend", 40), ("downtrend", 40)],
        "strategy": True,
    },
    {
        "session_id": "demo-risk",
        "title": "Portfolio risk",
        "summary": "A concentrated paper position, a second order blocked by the concentration limit, then a shock.",
        "seed": 606,
        "script": [("normal", 25), ("price_shock", 55)],
        "risk_case": True,
    },
]


def write_demo(root: Path, spec: dict) -> Path:
    session_id = spec["session_id"]
    folder = root / "sessions" / session_id
    folder.mkdir(parents=True, exist_ok=True)
    symbols = ["ATHR", "BRDL", "NL100", "HLX", "LUMN"]
    simulator = Simulator(
        session_id,
        symbols,
        spec["seed"],
        start=datetime(2026, 6, 2, 13, 30, tzinfo=timezone.utc),
    )
    feed = FeedHandler()
    books = BookService()
    execution = ExecutionEngine()
    account = PositionBook(Decimal("1000000"))
    risk = RiskEngine()
    orders = []
    fills = []
    pulse = 0
    handle = (folder / "events.jsonl").open("w", encoding="utf-8")
    try:
        for regime, count in spec["script"]:
            simulator.set_regime(regime)
            for _ in range(count):
                pulse += 1
                if spec.get("gap_at") == pulse:
                    simulator.inject_gap(5)
                events = feed.handle_many(simulator.pulse()).accepted
                for event in events:
                    books.on_event(event)
                    handle.write(event.model_dump_json())
                    handle.write("\n")
                if spec.get("strategy") and pulse % 15 == 0:
                    _strategy_step(simulator, books, execution, account, orders, fills, pulse)
                if spec.get("risk_case") and pulse == 10:
                    _risk_orders(simulator, books, execution, account, risk, orders, fills)
    finally:
        handle.close()
    meta = {
        "session_id": session_id,
        "title": spec["title"],
        "summary": spec["summary"],
        "seed": spec["seed"],
        "kind": "demo",
        "synthetic": True,
        "symbols": symbols,
        "isolated_from_live_ledger": True,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if orders:
        (folder / "orders.json").write_text(
            json.dumps([order.model_dump(mode="json") for order in orders], indent=2),
            encoding="utf-8",
        )
    if fills:
        (folder / "fills.json").write_text(
            json.dumps([fill.model_dump(mode="json") for fill in fills], indent=2),
            encoding="utf-8",
        )
        (folder / "pnl.json").write_text(
            json.dumps(
                {
                    "cash": {key: f"{value:.2f}" for key, value in account.cash.items()},
                    "positions": {
                        symbol: {
                            "quantity_lots": position.quantity_lots,
                            "average_cost": f"{position.average_cost:.6f}",
                            "realised": f"{position.realised:.2f}",
                            "fees": f"{position.fees:.4f}",
                        }
                        for symbol, position in account.positions.items()
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return folder


def _strategy_step(simulator, books, execution, account, orders, fills, pulse: int) -> None:
    book = books.view("ATHR")
    if book.health.stale or book.best_ask_ticks is None:
        return
    from marketstream.core.instruments import get_instrument
    from marketstream.core.money import from_ticks

    instrument = get_instrument("ATHR")
    mid = book.mid_ticks or Decimal(book.best_ask_ticks)
    price = from_ticks(int(mid), instrument.tick_size) if not isinstance(mid, Decimal) else mid * instrument.tick_size
    reference = instrument.reference_price
    side = None
    if price < reference * Decimal("0.995"):
        side = "buy"
    elif price > reference * Decimal("1.005"):
        side = "sell"
    if side is None:
        return
    request = OrderRequest(
        client_order_id=f"strategy-{pulse}",
        symbol="ATHR",
        side=side,
        order_type="market",
        quantity_lots=20,
        ledger="live",
    )
    order, new_fills = execution.submit(request, book, simulator.session_id, simulator.clock, None, None)
    for fill in new_fills:
        account.apply_fill(fill)
    orders.append(order)
    fills.extend(new_fills)


def _risk_orders(simulator, books, execution, account, risk, orders, fills) -> None:
    from marketstream.core.instruments import get_instrument

    instrument = get_instrument("ATHR")
    book = books.view("ATHR")
    first = OrderRequest(
        client_order_id="risk-open",
        symbol="ATHR",
        side="buy",
        order_type="market",
        quantity_lots=1200,
        ledger="live",
    )
    rule, reason = risk.check_order(first, instrument, book.best_ask_ticks, {}, {}, Decimal("0"))
    order, new_fills = execution.submit(first, book, simulator.session_id, simulator.clock, rule, reason)
    for fill in new_fills:
        account.apply_fill(fill)
    orders.append(order)
    fills.extend(new_fills)
    position = account.positions.get("ATHR")
    positions = {"ATHR": position.quantity_lots if position else 0}
    exposures = {}
    if position and book.mid_ticks is not None:
        exposures["ATHR"] = Decimal(position.quantity_lots) * instrument.lot_size * book.mid_ticks * instrument.tick_size
    second = OrderRequest(
        client_order_id="risk-add",
        symbol="ATHR",
        side="buy",
        order_type="market",
        quantity_lots=1200,
        ledger="live",
    )
    rule, reason = risk.check_order(second, instrument, book.best_ask_ticks, positions, exposures, Decimal("0"))
    blocked, _ = execution.submit(second, book, simulator.session_id, simulator.clock, rule, reason)
    orders.append(blocked)
