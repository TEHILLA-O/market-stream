"""Composition root for the simulated market, account, and replay studio."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from marketstream.core.config import Settings, project_root
from marketstream.core.instruments import get_instrument, list_instruments
from marketstream.core.logging import get_logger
from marketstream.core.models import FillRecord, MarketEvent, OrderRecord, OrderRequest
from marketstream.core.money import format_decimal, format_price, from_ticks, notional
from marketstream.core.present import book_view, candle_view, fill_view, order_view, price_float, price_text, trade_view
from marketstream.decision_engine.rules import DecisionEngine
from marketstream.execution.engine import ExecutionEngine
from marketstream.feed.handler import FeedHandler
from marketstream.market.analytics import asof_quote, ohlc, rolling_volatility, session_high_low, spread_series, trade_returns, vwap_ticks
from marketstream.market.book import BookService
from marketstream.portfolio.pnl import Mark, PositionBook
from marketstream.queries.catalog import INTERVALS, QUERIES, list_queries as query_catalogue
from marketstream.replay.engine import ReplayStudio, read_meta
from marketstream.risk.engine import RiskEngine, RiskLimits
from marketstream.simulation.engine import REGIMES, Simulator
from marketstream.store.history import AccountLedger, SessionArchive
from marketstream.store.qbridge import QBridge
from marketstream.store.tickstore import TickStore
from marketstream.streaming.hub import StreamHub

log = get_logger("platform")


class Metrics:
    def __init__(self) -> None:
        self.started = datetime.now(timezone.utc)
        self.generated = 0
        self.ingested = 0
        self.quarantined = 0
        self.gaps = 0
        self.duplicates = 0
        self.latencies_ms: deque[float] = deque(maxlen=4000)
        self.last_event_wall: datetime | None = None
        self.errors: deque[dict] = deque(maxlen=50)

    def observe(self, latency_ms: float) -> None:
        self.latencies_ms.append(latency_ms)

    def percentile(self, p: float) -> float | None:
        if not self.latencies_ms:
            return None
        ordered = sorted(self.latencies_ms)
        index = min(len(ordered) - 1, max(0, int(round((p / 100) * (len(ordered) - 1)))))
        return ordered[index]


class Platform:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        root = project_root()
        self.data_dir = settings.data_dir if settings.data_dir.is_absolute() else root / settings.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.metrics = Metrics()
        self.archive = SessionArchive(self.data_dir)
        self.ledger = AccountLedger(self.data_dir)
        self.store = TickStore()
        self.books = BookService()
        self.feed = FeedHandler()
        self.execution = ExecutionEngine()
        cash = Decimal(settings.starting_cash)
        self.positions = PositionBook(cash)
        self.replay_positions = PositionBook(cash)
        self.risk = RiskEngine(limits=RiskLimits(capital_base=cash))
        self.decisions = DecisionEngine()
        self.replay = ReplayStudio()
        self.hub = StreamHub(settings.ws_max_clients)
        self.qbridge = QBridge(settings.q_host, settings.q_port, settings.q_enabled)
        self.speed = settings.speed
        self.session_id = ""
        self.sim: Simulator | None = None
        self._task: asyncio.Task | None = None
        self._stop = False
        self._accumulator = 0.0
        self._pending_trades: list[MarketEvent] = []
        self._stats_cache: dict[str, dict] = {}
        self._candle_cache: dict[tuple[str, str], list] = {}
        self._last_decision_pulse = 0
        self._order_clock = 0
        self._demo_lock = threading.Lock()
        self.alerts: deque[dict] = deque(maxlen=100)
        self._recover_account()

    async def startup(self) -> None:
        self.open_session(warmup=True)
        self._task = asyncio.create_task(self.run())
        if self.settings.build_demos:
            await asyncio.to_thread(self.ensure_demos)
        log.info("platform_started", session=self.session_id, engine=self.qbridge.mode)

    async def shutdown(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.archive.close()
        self.ledger.close()

    def open_session(self, warmup: bool) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.session_id = f"live-{self.settings.seed}-{stamp}"
        self.sim = Simulator(self.session_id, self.settings.symbols, self.settings.seed)
        self.store.clear()
        self.books = BookService()
        self.feed = FeedHandler()
        self._stats_cache.clear()
        self._candle_cache.clear()
        self.archive.open_session(
            self.session_id,
            {
                "kind": "live",
                "seed": self.settings.seed,
                "symbols": self.settings.symbols,
                "started": datetime.now(timezone.utc).isoformat(),
                "synthetic": True,
            },
        )
        if warmup and self.settings.warmup_pulses:
            self.run_pulses(self.settings.warmup_pulses)

    def reset_market(self) -> dict:
        now = self.now()
        for order in self.execution.list_orders("live"):
            if order.status in {"working", "partially_filled"}:
                self.execution.expire_working(now, "live")
                break
        for order in self.execution.list_orders("live"):
            if order.status == "expired":
                self.ledger.append_order(order)
        self.open_session(warmup=True)
        return self.simulation_state()

    def run_pulses(self, count: int) -> None:
        assert self.sim is not None
        for _ in range(count):
            self.ingest(self.sim.pulse())

    def ingest(self, events: list[MarketEvent]) -> None:
        if not events:
            return
        self.metrics.generated += len(events)
        started = time.perf_counter()
        wall = datetime.now(timezone.utc)
        accepted = self.feed.handle_many(events, wall).accepted
        elapsed = (time.perf_counter() - started) * 1000
        if events:
            self.metrics.observe(elapsed / len(events))
        for event in accepted:
            self.metrics.ingested += 1
            self.metrics.last_event_wall = wall
            self.store.add(event)
            outcome = self.books.on_event(event)
            if outcome == "duplicate":
                self.metrics.duplicates += 1
            if outcome == "quarantine":
                self.metrics.quarantined += 1
            self.archive.append_event(event)
            self.qbridge.publish(event)
            if event.event_type == "trade":
                self._pending_trades.append(event)
                fills = self.execution.on_trade(event, event.event_timestamp, "live")
                for fill in fills:
                    self._apply_fill(fill)
        self.metrics.gaps = self.feed.gaps
        self._refresh_analytics()

    async def run(self) -> None:
        last = time.perf_counter()
        while not self._stop:
            now = time.perf_counter()
            delta = now - last
            last = now
            assert self.sim is not None
            if self.sim.running and not self.sim.paused:
                self._accumulator += delta * self.speed
                produced = 0
                # A gap and its recovering snapshot must be published on
                # different frames, or the workstation never shows the book as stale.
                recovering = self.sim.pending_gap or self.sim.pulses_until_recovery
                pulse_budget = 1 if recovering else 5
                while self._accumulator >= self.sim.pulse_seconds and produced < pulse_budget:
                    self.ingest(self.sim.pulse())
                    self._accumulator -= self.sim.pulse_seconds
                    produced += 1
                if self.sim.pulse_index - self._last_decision_pulse >= 5:
                    self._evaluate_decisions()
                    self._last_decision_pulse = self.sim.pulse_index
            if self.replay.playing:
                step = max(1, int(self.replay.speed))
                self.replay.tick(step)
            try:
                await self.hub.publish(self.frame())
            except Exception as exc:  # noqa: BLE001
                self.metrics.errors.append({"time": datetime.now(timezone.utc).isoformat(), "detail": str(exc)})
            self._pending_trades.clear()
            await asyncio.sleep(0.1)

    def frame(self) -> dict:
        assert self.sim is not None
        messages: list[dict] = [
            {
                "category": "heartbeat",
                "schema_version": 1,
                "virtual_time": self.sim.clock.isoformat(),
                "wall_time": datetime.now(timezone.utc).isoformat(),
            },
            {"category": "simulation", **self.simulation_state()},
            {"category": "system", **self.system_status()},
        ]
        for symbol in self.settings.symbols:
            stats = self.symbol_stats(symbol)
            messages.append({"category": "quote", "symbol": symbol, **stats})
            messages.append({"category": "book", "symbol": symbol, **self.order_book(symbol)})
            candles = self.candles(symbol, "5s", limit=2)
            if candles:
                messages.append({"category": "ohlc", "symbol": symbol, "interval": "5s", "bar": candles[-1]})
        for trade in self._pending_trades[-40:]:
            messages.append(trade_view(trade, get_instrument(trade.symbol)))
        if self.alerts:
            messages.append({"category": "alert", "alerts": list(self.alerts)[-8:]})
        messages.append({"category": "position", **self.portfolio()})
        messages.append({"category": "risk", **self.risk_snapshot()})
        return {"schema_version": 1, "category": "batch", "messages": messages}

    def now(self) -> datetime:
        assert self.sim is not None
        return self.sim.clock

    def simulation_state(self) -> dict:
        assert self.sim is not None
        freshness = None
        if self.metrics.last_event_wall is not None:
            freshness = (datetime.now(timezone.utc) - self.metrics.last_event_wall).total_seconds()
        stalled = bool(self.sim.running and not self.sim.paused and freshness is not None and freshness > 3)
        return {
            "session_id": self.session_id,
            "running": self.sim.running,
            "paused": self.sim.paused,
            "regime": self.sim.regime,
            "regimes": list(REGIMES),
            "speed": self.speed,
            "virtual_time": self.sim.clock.isoformat(),
            "pulse": self.sim.pulse_index,
            "seed": self.settings.seed,
            "symbols": self.settings.symbols,
            "synthetic": True,
            "stalled": stalled,
            "engine": self.qbridge.status(),
        }

    def set_speed(self, speed: float) -> dict:
        self.speed = max(0.25, min(speed, 50))
        self._accumulator = 0
        return self.simulation_state()

    def set_regime(self, regime: str) -> dict:
        assert self.sim is not None
        self.sim.set_regime(regime)
        self.alerts.append(
            {
                "id": f"regime-{self.sim.pulse_index}",
                "kind": "regime",
                "symbol": None,
                "detail": f"Regime set to {regime}",
                "timestamp": self.now().isoformat(),
                "simulated": True,
            }
        )
        return self.simulation_state()

    def pause(self) -> dict:
        assert self.sim is not None
        self.sim.paused = True
        return self.simulation_state()

    def resume(self) -> dict:
        assert self.sim is not None
        self.sim.paused = False
        self.sim.running = True
        return self.simulation_state()

    def inject_gap(self) -> dict:
        assert self.sim is not None
        self.sim.inject_gap(5)
        return self.simulation_state()

    def symbol_stats(self, symbol: str) -> dict:
        cached = self._stats_cache.get(symbol)
        if cached:
            return cached
        return self._compute_stats(symbol)

    def _refresh_analytics(self) -> None:
        for symbol in self.settings.symbols:
            self._stats_cache[symbol] = self._compute_stats(symbol)
            self._candle_cache.pop((symbol, "5s"), None)
        if self.sim is not None:
            equity = Decimal(self.portfolio()["totals"]["equity"])
            self.risk.sample_equity(equity, self.now())

    def _compute_stats(self, symbol: str) -> dict:
        instrument = get_instrument(symbol)
        trades = list(self.store.trades.get(symbol, []))
        book = self.books.view(symbol)
        last = trades[-1] if trades else None
        high, low = session_high_low(trades)
        weighted = vwap_ticks(trades)
        bars = ohlc(trades, 5) if trades else []
        closes = [bar["close_ticks"] for bar in bars]
        vol = rolling_volatility(closes, 20)
        short = _return_bps(closes, 5)
        long = _return_bps(closes, 20)
        reference = from_ticks(int(instrument.reference_price / instrument.tick_size), instrument.tick_size)
        last_px = from_ticks(last.price_ticks, instrument.tick_size) if last else None
        change = (last_px - reference) if last_px is not None else None
        mid = None if book.mid_ticks is None else book.mid_ticks * instrument.tick_size
        if book.health.stale or mid is None:
            mark = Mark(price=self.risk.last_mid.get(symbol), source="previous", stale=True, timestamp=book.health.last_event_timestamp)
        else:
            mark_price = mid
            self.risk.sample_return(symbol, mark_price)
            mark = Mark(price=mark_price, source="mid", stale=False, timestamp=book.health.last_event_timestamp)
        return {
            "symbol": symbol,
            "description": instrument.description,
            "asset_class": instrument.asset_class,
            "currency": instrument.currency,
            "venue": instrument.venue,
            "last": None if last_px is None else f"{last_px:.{instrument.price_precision}f}",
            "last_size": None if last is None else last.quantity_lots,
            "change": None if change is None else f"{change:.{instrument.price_precision}f}",
            "change_bps": None if change is None or reference == 0 else f"{(change / reference) * Decimal(10000):.2f}",
            "bid": price_text(book.best_bid_ticks, instrument),
            "ask": price_text(book.best_ask_ticks, instrument),
            "spread": price_text(book.spread_ticks, instrument),
            "spread_bps": None if book.spread_bps is None else f"{book.spread_bps:.2f}",
            "mid": None if mid is None else f"{mid:.{instrument.price_precision}f}",
            "microprice": None if book.microprice_ticks is None else f"{(book.microprice_ticks * instrument.tick_size):.{instrument.price_precision}f}",
            "vwap": None if weighted is None else f"{(weighted * instrument.tick_size):.{instrument.price_precision}f}",
            "volume_lots": sum(trade.quantity_lots for trade in trades),
            "trade_count": len(trades),
            "high": price_text(high, instrument),
            "low": price_text(low, instrument),
            "volatility": None if vol is None else f"{vol:.6f}",
            "return_short_bps": None if short is None else f"{short:.2f}",
            "return_long_bps": None if long is None else f"{long:.2f}",
            "imbalance": None if book.imbalance is None else f"{book.imbalance:.4f}",
            "bid_depth_lots": book.bid_depth_lots,
            "ask_depth_lots": book.ask_depth_lots,
            "book_state": book.health.state,
            "book_stale": book.health.stale,
            "book_detail": book.health.detail,
            "mark": None if mark.price is None else f"{mark.price:.{instrument.price_precision}f}",
            "mark_stale": mark.stale,
            "simulated": True,
        }

    def candles(self, symbol: str, interval: str, limit: int = 300) -> list[dict]:
        seconds = INTERVALS.get(interval)
        if seconds is None:
            raise ValueError(f"unsupported interval {interval}")
        key = (symbol, interval)
        if key not in self._candle_cache or interval != "5s":
            instrument = get_instrument(symbol)
            bars = ohlc(list(self.store.trades.get(symbol, [])), seconds)
            self._candle_cache[key] = [candle_view(bar, instrument) for bar in bars]
        return self._candle_cache[key][-limit:]

    def trades(self, symbol: str | None, limit: int) -> list[dict]:
        if symbol:
            rows = list(self.store.trades.get(symbol, []))
        else:
            rows = list(self.store.tape)
        return [trade_view(trade, get_instrument(trade.symbol)) for trade in rows[-limit:]]

    def quotes(self, symbol: str, limit: int) -> list[dict]:
        instrument = get_instrument(symbol)
        rows = []
        for quote in list(self.store.quotes.get(symbol, []))[-limit:]:
            rows.append(
                {
                    "symbol": symbol,
                    "sequence": quote.sequence_number,
                    "event_timestamp": quote.event_timestamp.isoformat(),
                    "bid": price_text(quote.bid_ticks, instrument),
                    "ask": price_text(quote.ask_ticks, instrument),
                    "bid_quantity_lots": quote.bid_quantity_lots,
                    "ask_quantity_lots": quote.ask_quantity_lots,
                    "simulated": True,
                }
            )
        return rows

    def order_book(self, symbol: str) -> dict:
        return book_view(self.books.view(symbol), get_instrument(symbol))

    def depth_history(self, symbol: str) -> list[dict]:
        instrument = get_instrument(symbol)
        history = []
        for row in self.books.depth_history(symbol):
            history.append(
                {
                    **row,
                    "bids": [
                        {**level, "price": price_text(level["price_ticks"], instrument)} for level in row["bids"]
                    ],
                    "asks": [
                        {**level, "price": price_text(level["price_ticks"], instrument)} for level in row["asks"]
                    ],
                }
            )
        return history

    def submit_order(self, request: OrderRequest) -> dict:
        instrument = get_instrument(request.symbol)
        book = self.books.view(request.symbol) if request.ledger == "live" else self.replay.books.view(request.symbol)
        account = self.positions if request.ledger == "live" else self.replay_positions
        rule, reason = self._pretrade(request, instrument, book, account)
        repeat = (request.ledger, request.client_order_id) in self.execution.by_client
        order, fills = self.execution.submit(request, book, self.session_id, self.now(), rule, reason)
        for fill in fills:
            if request.ledger == "live":
                self._apply_fill(fill)
            else:
                account.apply_fill(fill)
        if request.ledger == "live" and not repeat:
            self.ledger.append_order(order)
        self._order_clock += 1
        return order_view(order, instrument)

    def preview_order(self, request: OrderRequest) -> dict:
        instrument = get_instrument(request.symbol)
        book = self.books.view(request.symbol)
        account = self.positions
        rule, reason = self._pretrade(request, instrument, book, account)
        return self.execution.preview(request, book, rule, reason)

    def cancel_order(self, order_id: str, ledger: str = "live") -> dict:
        order = self.execution.cancel(order_id, self.now(), ledger)
        if ledger == "live":
            self.ledger.append_order(order)
        return order_view(order, get_instrument(order.symbol))

    def orders(self, ledger: str = "live") -> list[dict]:
        return [order_view(order, get_instrument(order.symbol)) for order in self.execution.list_orders(ledger)]

    def fills(self, ledger: str = "live") -> list[dict]:
        return [fill_view(fill, get_instrument(fill.symbol)) for fill in self.execution.list_fills(ledger)]

    def portfolio(self, ledger: str = "live") -> dict:
        account = self.positions if ledger == "live" else self.replay_positions
        views = []
        for instrument in list_instruments():
            stats = self.symbol_stats(instrument.symbol) if ledger == "live" else {}
            if ledger == "live":
                mark = Mark(
                    price=Decimal(stats["mark"]) if stats.get("mark") else None,
                    source="mid" if not stats.get("mark_stale") else "previous",
                    stale=bool(stats.get("mark_stale")),
                    timestamp=None,
                )
            else:
                replay_book = self.replay.books.view(instrument.symbol)
                price = None if replay_book.mid_ticks is None else replay_book.mid_ticks * instrument.tick_size
                mark = Mark(price=price, source="replay-mid", stale=replay_book.health.stale, timestamp=None)
            view = account.view(instrument.symbol, mark, instrument)
            if view["quantity_lots"] or Decimal(view["fees"]) or Decimal(view["realised_pnl"]):
                views.append(view)
        totals = account.totals(views)
        return {"positions": views, "totals": totals, "ledger": ledger, "simulated": True}

    def risk_snapshot(self) -> dict:
        portfolio = self.portfolio()
        notionals: dict[str, Decimal] = {}
        by_class: dict[str, Decimal] = {}
        long_exposure = Decimal("0")
        short_exposure = Decimal("0")
        for row in portfolio["positions"]:
            value = Decimal(row["market_value"])
            notionals[row["symbol"]] = value
            by_class[row["asset_class"]] = by_class.get(row["asset_class"], Decimal("0")) + value
            if value >= 0:
                long_exposure += value
            else:
                short_exposure += value
        gross = sum((abs(value) for value in notionals.values()), Decimal("0"))
        net = sum(notionals.values(), Decimal("0"))
        capital = self.risk.limits.capital_base or Decimal("1")
        utilisations = []
        concentration = []
        for symbol, value in notionals.items():
            ratio = abs(value) / capital
            concentration.append({"symbol": symbol, "notional": format_decimal(value, 2), "fraction_of_capital": f"{ratio:.4f}"})
            if ratio > self.risk.limits.max_symbol_concentration:
                self._alert("concentration", f"{symbol} concentration {ratio:.1%} exceeds the capital limit", symbol)
        drawdown = self.risk.drawdown()
        if Decimal(drawdown["drawdown"]) > self.risk.limits.drawdown_alert:
            self._alert("drawdown", f"Peak-to-trough drawdown is {drawdown['drawdown']}", None)
        net_pnl = Decimal(portfolio["totals"]["net_pnl"])
        if net_pnl < -self.risk.limits.daily_loss:
            self._alert("daily_loss", f"Net P&L {net_pnl:.2f} breached the daily loss threshold", None)
        for symbol in self.settings.symbols:
            stats = self.symbol_stats(symbol)
            if stats.get("book_stale"):
                self._alert("stale_book", f"{symbol} order book is stale. {stats.get('book_detail') or ''}".strip(), symbol)
            spread = stats.get("spread_bps")
            normal = _normal_spread_bps(symbol)
            if spread is not None and normal is not None and Decimal(spread) > normal * Decimal("2.5"):
                self._alert("wide_spread", f"{symbol} spread is {spread} bps versus a normal {normal:.2f} bps", symbol)
        utilisations.extend(
            [
                _util("gross exposure", gross, self.risk.limits.max_gross_exposure),
                _util("net exposure", abs(net), self.risk.limits.max_net_exposure),
                _util("daily loss", max(Decimal("0"), -net_pnl), self.risk.limits.daily_loss),
            ]
        )
        return {
            "simulated": True,
            "gross_exposure": format_decimal(gross, 2),
            "net_exposure": format_decimal(net, 2),
            "long_exposure": format_decimal(long_exposure, 2),
            "short_exposure": format_decimal(short_exposure, 2),
            "by_asset_class": {key: format_decimal(value, 2) for key, value in by_class.items()},
            "by_instrument": {key: format_decimal(value, 2) for key, value in notionals.items()},
            "concentration": concentration,
            "limits": self.risk.limits.to_public(),
            "utilisation": utilisations,
            "drawdown": drawdown,
            "equity_curve": list(self.risk.equity_curve)[-180:],
            "var": self.risk.historical_var(notionals),
            "scenarios": self.risk.scenario(notionals),
            "alerts": list(self.alerts)[-30:],
            "currency": "USD",
        }

    def signals(self, symbol: str | None = None) -> dict:
        return self.decisions.summarise(symbol)

    def run_query(self, query_id: str, symbol: str, interval: str) -> dict:
        spec = QUERIES.get(query_id)
        if spec is None:
            raise KeyError(query_id)
        started = time.perf_counter()
        engine = "python-reference"
        note = self.qbridge.detail
        rows: list[dict]
        if query_id == "latest":
            rows = [self.symbol_stats(item.symbol) for item in list_instruments()]
        elif query_id == "ohlc":
            rows = self.candles(symbol, interval, limit=200)
        elif query_id == "vwap":
            rows = []
            for item in list_instruments():
                stats = self.symbol_stats(item.symbol)
                rows.append({"symbol": item.symbol, "vwap": stats["vwap"], "volume_lots": stats["volume_lots"], "trade_count": stats["trade_count"]})
        elif query_id == "volatility":
            rows = [
                {
                    "symbol": item.symbol,
                    "volatility": self.symbol_stats(item.symbol)["volatility"],
                    "window_bars": 20,
                    "annualised": False,
                }
                for item in list_instruments()
            ]
        elif query_id == "asof":
            instrument = get_instrument(symbol)
            joined = asof_quote(
                list(self.store.trades.get(symbol, []))[-20:],
                list(self.store.quotes.get(symbol, [])),
            )
            rows = [
                {
                    "trade_id": row["trade_id"],
                    "price": price_text(row["price_ticks"], instrument),
                    "bid": price_text(row["bid_ticks"], instrument),
                    "ask": price_text(row["ask_ticks"], instrument),
                }
                for row in joined
            ]
        elif query_id == "spread":
            instrument = get_instrument(symbol)
            series = spread_series(list(self.store.quotes.get(symbol, []))[-80:])
            rows = [
                {
                    "time": row["time"].isoformat(),
                    "spread_ticks": row["spread_ticks"],
                    "spread": price_text(row["spread_ticks"], instrument),
                    "spread_bps": None if row["spread_bps"] is None else f"{row['spread_bps']:.2f}",
                }
                for row in series
            ]
        else:
            rows = []
        if self.qbridge.connected:
            engine = "kdb"
            note = "Query id was served by the Python reference. IPC is connected, but only allowlisted q functions defined in the RDB are executed, and this build returns the verified Python result alongside the q source."
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "id": query_id,
            "title": spec["title"],
            "q": spec["q"],
            "explanation": spec["explanation"],
            "engine": engine,
            "note": note,
            "symbol": symbol,
            "interval": interval,
            "elapsed_ms": round(elapsed_ms, 3),
            "row_count": len(rows),
            "rows": rows,
            "executed_unrestricted_q": False,
        }

    def list_queries(self) -> list[dict]:
        return query_catalogue(self.qbridge.mode)

    def system_status(self) -> dict:
        q = self.qbridge.status()
        latency = {
            "unit": "milliseconds",
            "sample": "in-process feedhandler batch, per event",
            "p50": _round(self.metrics.percentile(50)),
            "p95": _round(self.metrics.percentile(95)),
            "p99": _round(self.metrics.percentile(99)),
            "not_exchange_latency": True,
        }
        sessions = self.archive.list_sessions()
        components = [
            _component("simulator", "live" if self.sim and self.sim.running and not self.sim.paused else "paused", "Synthetic event generator"),
            _component("feedhandler", "live" if self.feed.connected else "down", f"accepted {self.feed.accepted}, quarantined {self.feed.quarantined}"),
            _component(
                "tickerplant",
                "live" if q["connected"] else "unavailable",
                q["detail"],
            ),
            _component("rdb", "live", f"in-memory session store, {self.store.count} events"),
            _component("hdb", "live" if sessions else "empty", f"{len(sessions)} session logs on disk"),
            _component(
                "analytics",
                "live" if q["connected"] else "python-reference",
                "q process" if q["connected"] else "Python reference implementation, not kdb+",
            ),
            _component("api", "live", "FastAPI process"),
            _component("websocket", "live", f"{len(self.hub.clients)} subscribers"),
        ]
        return {
            "components": components,
            "generated": self.metrics.generated,
            "ingested": self.metrics.ingested,
            "quarantined": self.metrics.quarantined,
            "gaps": self.metrics.gaps,
            "duplicates": self.metrics.duplicates,
            "latency": latency,
            "websocket_clients": len(self.hub.clients),
            "freshness_seconds": _freshness(self.metrics.last_event_wall),
            "queue_backlog": 0,
            "engine": q,
            "errors": list(self.metrics.errors),
            "started": self.metrics.started.isoformat(),
            "simulated": True,
        }

    def sessions(self) -> list[dict]:
        self.ensure_demos()
        return self.archive.list_sessions()

    def ensure_demos(self) -> None:
        from marketstream.simulation.demos import DEMO_SPECS, write_demo

        with self._demo_lock:
            for spec in DEMO_SPECS:
                folder = self.data_dir / "sessions" / spec["session_id"]
                if not (folder / "events.jsonl").exists():
                    write_demo(self.data_dir, spec)

    def load_replay(self, session_id: str) -> dict:
        path = self.data_dir / "sessions" / session_id / "events.jsonl"
        if not path.exists():
            self.ensure_demos()
        if not path.exists():
            raise FileNotFoundError(session_id)
        return self.replay.load_file(path, read_meta(path))

    def replay_view(self, symbol: str) -> dict:
        status = self.replay.status()
        books = {
            item.symbol: book_view(self.replay.books.view(item.symbol), item) for item in list_instruments()
        }
        trades = []
        window = self.replay.events[max(0, self.replay.cursor - 40) : self.replay.cursor]
        for event in window:
            if event.event_type == "trade":
                trades.append(trade_view(event, get_instrument(event.symbol)))
        symbol_trades = [
            event
            for event in self.replay.events[: self.replay.cursor]
            if event.event_type == "trade" and event.symbol == symbol
        ]
        instrument = get_instrument(symbol)
        candles = [candle_view(bar, instrument) for bar in ohlc(symbol_trades, 5)]
        depth = [
            row
            for row in self.replay.depth_samples.get(symbol, [])
            if row["index"] <= self.replay.cursor
        ]
        folder = self.data_dir / "sessions" / (self.replay.session_id or "")
        ledger = {}
        for name in ("orders.json", "fills.json", "pnl.json"):
            sidecar = folder / name
            if sidecar.exists():
                ledger[name.removesuffix(".json")] = json.loads(sidecar.read_text(encoding="utf-8"))
        return {
            **status,
            "books": books,
            "trades": trades[-30:],
            "candles": candles[-240:],
            "depth": depth[-60:],
            "risk": self._replay_risk(ledger.get("fills") or [], status.get("event_time")),
            "focus": symbol,
            "session_ledger": ledger,
            "isolated_from_live_ledger": True,
        }

    def _replay_risk(self, fills: list, event_time: str | None) -> dict:
        """P&L from this session's fill file, cut at the playhead. The live ledger is not read."""

        as_of = None
        if event_time:
            as_of = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        account = PositionBook(Decimal(self.settings.starting_cash))
        applied = 0
        for row in fills:
            fill = FillRecord.model_validate(row)
            if as_of is not None and fill.timestamp > as_of:
                continue
            account.apply_fill(fill)
            applied += 1
        views = []
        for instrument in list_instruments():
            replay_book = self.replay.books.view(instrument.symbol)
            price = None if replay_book.mid_ticks is None else replay_book.mid_ticks * instrument.tick_size
            mark = Mark(price=price, source="replay-mid", stale=replay_book.health.stale, timestamp=as_of)
            view = account.view(instrument.symbol, mark, instrument)
            if view["quantity_lots"] or Decimal(view["fees"]) or Decimal(view["realised_pnl"]):
                views.append(view)
        totals = account.totals(views)
        gross = sum((abs(Decimal(row["market_value"])) for row in views), Decimal("0"))
        net = sum((Decimal(row["market_value"]) for row in views), Decimal("0"))
        note = (
            "No paper fills are stored for this session."
            if not fills
            else "Recomputed from the session fill file up to the playhead. This does not change the live account."
        )
        return {
            "fills_applied": applied,
            "gross_exposure": format_decimal(gross, 2),
            "net_exposure": format_decimal(net, 2),
            "net_pnl": totals["net_pnl"],
            "realised_pnl": totals["realised_pnl"],
            "unrealised_pnl": totals["unrealised_pnl"],
            "fees": totals["fees"],
            "note": note,
            "simulated": True,
        }

    def _pretrade(self, request: OrderRequest, instrument, book, account: PositionBook):
        reference = book.best_ask_ticks if request.side == "buy" else book.best_bid_ticks
        if request.order_type == "limit" and request.limit_price:
            from marketstream.core.money import to_ticks

            reference = to_ticks(Decimal(request.limit_price), instrument.tick_size)
        positions = {symbol: position.quantity_lots for symbol, position in account.positions.items()}
        exposures = {}
        for symbol, position in account.positions.items():
            mark_text = self.symbol_stats(symbol).get("mark") if request.ledger == "live" else None
            if mark_text:
                exposures[symbol] = Decimal(position.quantity_lots) * get_instrument(symbol).lot_size * Decimal(mark_text)
        totals = self.portfolio(request.ledger)["totals"]
        rule, reason = self.risk.check_order(
            request,
            instrument,
            reference,
            positions,
            exposures,
            Decimal(totals["net_pnl"]),
        )
        if rule:
            return rule, reason
        if request.side == "buy" and reference is not None:
            required = notional(request.quantity_lots, reference, instrument)
            required += required * (self.execution.commission_bps + self.execution.tax_bps) / Decimal(10000)
            cash = account.cash.get(instrument.currency, Decimal("0"))
            if cash < required:
                return "buying_power", f"required {required:.2f} {instrument.currency} exceeds cash {cash:.2f}"
        return None, None

    def _apply_fill(self, fill: FillRecord) -> None:
        self.positions.apply_fill(fill)
        self.ledger.append_fill(fill)

    def _recover_account(self) -> None:
        try:
            fills = self.ledger.load_fills()
            orders = self.ledger.load_orders()
        except Exception as exc:  # noqa: BLE001
            self.metrics.errors.append({"time": datetime.now(timezone.utc).isoformat(), "detail": f"ledger read failed: {exc}"})
            return
        if orders or fills:
            self.execution.restore(orders, fills)
        if fills:
            self.positions.rebuild(fills)
            log.info("ledger_recovered", fills=len(fills), orders=len(orders))

    def _evaluate_decisions(self) -> None:
        now = self.now()
        for symbol in self.settings.symbols:
            for decision in self.decisions.evaluate(symbol, self.symbol_stats(symbol), now):
                if decision.result == "trigger":
                    self._alert(decision.rule_id, decision.explanation, symbol)

    def _alert(self, kind: str, detail: str, symbol: str | None) -> None:
        alert = self.risk.raise_alert(kind, detail, self.now(), symbol)
        if alert is not None:
            self.alerts.append(alert)


def _return_bps(closes: list[int], window: int) -> Decimal | None:
    if len(closes) <= window:
        return None
    returns = trade_returns(closes[-(window + 1) :])
    if not returns:
        return None
    return Decimal(str(sum(returns))) * Decimal(10000)


def _component(name: str, state: str, detail: str) -> dict:
    return {"name": name, "state": state, "detail": detail}


def _util(name: str, used: Decimal, limit: Decimal) -> dict:
    ratio = Decimal("0") if limit == 0 else used / limit
    return {
        "name": name,
        "used": format_decimal(used, 2),
        "limit": format_decimal(limit, 2),
        "ratio": f"{ratio:.4f}",
    }


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _normal_spread_bps(symbol: str) -> Decimal | None:
    instrument = get_instrument(symbol)
    reference_ticks = instrument.reference_price / instrument.tick_size
    if reference_ticks <= 0:
        return None
    return (Decimal(instrument.base_spread_ticks) / reference_ticks) * Decimal(10000)


def _freshness(last: datetime | None) -> float | None:
    if last is None:
        return None
    return round((datetime.now(timezone.utc) - last).total_seconds(), 3)


def new_client_order_id() -> str:
    return uuid4().hex[:16]
