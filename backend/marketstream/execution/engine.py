"""Paper execution against the reconstructed book.

This is not an exchange. Market-by-price data has no order identity and
no queue position, so resting limits use a conservative trade-through
rule:

- Aggressive quantity walks displayed opposing liquidity and may fill
  immediately, up to the limit price for limit orders.
- Unfilled market quantity is cancelled. Market orders do not rest.
- Resting limits do not fill just because the touch reaches them.
  They fill only when a later trade prints strictly through the limit
  (a buy limit fills only if a trade prints below it; a sell limit
  fills only if a trade prints above it). At-touch prints are assumed
  to belong to orders already in a queue we cannot see.
- Paper fills do not remove liquidity from the public simulated book.

Fees are commission plus an optional flat tax, both in basis points of
notional. Walking the book is the slippage model. There is no second
hidden slippage number added on top.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from marketstream.core.instruments import Instrument, get_instrument
from marketstream.core.models import FillRecord, LifecycleStep, OrderRecord, OrderRequest, TradeEvent
from marketstream.core.money import format_decimal, from_ticks, notional, to_ticks
from marketstream.market.book import BookView


class ExecutionEngine:
    def __init__(self, commission_bps: Decimal = Decimal("1.0"), tax_bps: Decimal = Decimal("0")) -> None:
        self.commission_bps = commission_bps
        self.tax_bps = tax_bps
        self.orders: dict[str, OrderRecord] = {}
        self.by_client: dict[tuple[str, str], str] = {}
        self.fills: list[FillRecord] = []
        self._avg: dict[str, Decimal] = {}
        self._seq = 0
        self.assumptions = (
            "simulated; conservative trade-through queue; "
            "market orders are immediate-or-cancel; book liquidity is not consumed"
        )

    def preview(
        self,
        request: OrderRequest,
        book: BookView,
        risk_rule: str | None,
        risk_reason: str | None,
    ) -> dict:
        instrument = get_instrument(request.symbol)
        limit_ticks = self._limit_ticks(request, instrument)
        estimate = self._walk(request.side, request.order_type, request.quantity_lots, limit_ticks, book)
        fee = self._fee(estimate["notional"])
        return {
            "simulated": True,
            "symbol": request.symbol,
            "side": request.side,
            "order_type": request.order_type,
            "quantity_lots": request.quantity_lots,
            "filled_lots_estimate": estimate["filled"],
            "leaves_lots_estimate": request.quantity_lots - estimate["filled"],
            "average_price": estimate["average"],
            "notional": format_decimal(estimate["notional"], 2),
            "fee": format_decimal(fee, 4),
            "fee_currency": instrument.currency,
            "available_lots": estimate["available"],
            "risk_rule": risk_rule,
            "risk_reason": risk_reason,
            "accepted": risk_rule is None and request.quantity_lots > 0,
            "queue_model": "conservative_trade_through",
            "book_stale": book.health.stale,
        }

    def submit(
        self,
        request: OrderRequest,
        book: BookView,
        session_id: str,
        now: datetime,
        risk_rule: str | None,
        risk_reason: str | None,
    ) -> tuple[OrderRecord, list[FillRecord]]:
        key = (request.ledger, request.client_order_id)
        existing = self.by_client.get(key)
        if existing:
            return self.orders[existing], []
        instrument = get_instrument(request.symbol)
        limit_ticks = self._limit_ticks(request, instrument)
        order = self._new_order(request, instrument, session_id, now, limit_ticks)
        self.orders[order.order_id] = order
        self.by_client[key] = order.order_id
        if risk_rule:
            return self._reject(order, now, risk_rule, risk_reason or risk_rule), []
        if book.health.stale:
            return self._reject(order, now, "stale_book", "order book is stale or waiting for a snapshot"), []
        if book.health.state == "crossed":
            return self._reject(order, now, "crossed_book", "book is crossed; paper execution is paused"), []
        order.lifecycle.append(LifecycleStep(status="accepted", timestamp=now, reason="paper order accepted"))
        fills = self._aggress(order, book, instrument, now)
        if order.order_type == "market":
            if order.leaves_lots > 0 and order.filled_lots > 0:
                self._transition(order, "partially_filled", now, "partial market fill")
                self._transition(order, "cancelled", now, "unfilled market quantity cancelled")
            elif order.leaves_lots > 0:
                self._reject(order, now, "no_liquidity", "no opposing liquidity at the touch")
            else:
                self._transition(order, "filled", now, "market order filled")
        else:
            if order.leaves_lots == 0:
                self._transition(order, "filled", now, "limit order filled on entry")
            elif order.filled_lots > 0:
                self._transition(order, "partially_filled", now, "remainder resting")
            else:
                self._transition(order, "working", now, "resting at the back of an unseen queue")
        return order, fills

    def cancel(self, order_id: str, now: datetime, ledger: str = "live") -> OrderRecord:
        order = self.orders.get(order_id)
        if order is None or ledger not in order.order_id:
            raise KeyError(order_id)
        if order.status in {"filled", "cancelled", "rejected", "expired"}:
            return order
        self._transition(order, "cancelled", now, "cancelled by user")
        return order

    def on_trade(self, trade: TradeEvent, now: datetime, ledger: str) -> list[FillRecord]:
        fills: list[FillRecord] = []
        for order in list(self.orders.values()):
            if ledger not in order.order_id:
                continue
            if order.symbol != trade.symbol:
                continue
            if order.status not in {"working", "partially_filled"}:
                continue
            if order.order_type != "limit" or order.limit_ticks is None:
                continue
            through = (
                order.side == "buy" and trade.price_ticks < order.limit_ticks
            ) or (
                order.side == "sell" and trade.price_ticks > order.limit_ticks
            )
            if not through:
                continue
            lots = min(order.leaves_lots, trade.quantity_lots)
            if lots <= 0:
                continue
            fills.append(self._fill(order, lots, trade.price_ticks, now, "resting"))
            if order.leaves_lots == 0:
                self._transition(order, "filled", now, "filled on trade-through")
            else:
                self._transition(order, "partially_filled", now, "partial fill on trade-through")
        return fills

    def expire_working(self, now: datetime, ledger: str) -> None:
        for order in self.orders.values():
            if ledger not in order.order_id:
                continue
            if order.status in {"working", "partially_filled"}:
                self._transition(order, "expired", now, "session ended")

    def list_orders(self, ledger: str) -> list[OrderRecord]:
        return [order for order in self.orders.values() if order.order_id.startswith(f"{ledger}-")]

    def list_fills(self, ledger: str) -> list[FillRecord]:
        return [fill for fill in self.fills if fill.order_id.startswith(f"{ledger}-")]

    def restore(self, orders: list[OrderRecord], fills: list[FillRecord]) -> None:
        """Rebuild the blotter from the durable ledger. The latest row for an id wins."""

        for order in orders:
            self.orders[order.order_id] = order
            ledger = order.order_id.split("-", 1)[0]
            self.by_client[(ledger, order.client_order_id)] = order.order_id
            if order.avg_price is not None:
                self._avg[order.order_id] = Decimal(order.avg_price)
            suffix = order.order_id.rsplit("-", 1)[-1]
            if suffix.isdigit():
                self._seq = max(self._seq, int(suffix))
        self.fills.extend(fills)

    def _limit_ticks(self, request: OrderRequest, instrument: Instrument) -> int | None:
        if request.order_type == "market":
            return None
        if not request.limit_price:
            raise ValueError("limit orders require limit_price")
        return to_ticks(Decimal(request.limit_price), instrument.tick_size)

    def _new_order(
        self,
        request: OrderRequest,
        instrument: Instrument,
        session_id: str,
        now: datetime,
        limit_ticks: int | None,
    ) -> OrderRecord:
        self._seq += 1
        order_id = f"{request.ledger}-{self._seq:08d}"
        order = OrderRecord(
            order_id=order_id,
            client_order_id=request.client_order_id,
            session_id=session_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity_lots=request.quantity_lots,
            limit_ticks=limit_ticks,
            status="accepted",
            filled_lots=0,
            leaves_lots=request.quantity_lots,
            venue=instrument.venue,
            created_at=now,
            updated_at=now,
            lifecycle=[],
        )
        return order

    def _reject(self, order: OrderRecord, now: datetime, rule: str, reason: str) -> OrderRecord:
        order.status = "rejected"
        order.reject_rule = rule
        order.reject_reason = reason
        order.leaves_lots = 0
        order.updated_at = now
        order.lifecycle.append(LifecycleStep(status="rejected", timestamp=now, reason=reason))
        return order

    def _aggress(self, order: OrderRecord, book: BookView, instrument: Instrument, now: datetime) -> list[FillRecord]:
        levels = book.asks if order.side == "buy" else book.bids
        fills = []
        for level in levels:
            if order.leaves_lots <= 0:
                break
            price = level["price_ticks"]
            if order.limit_ticks is not None:
                if order.side == "buy" and price > order.limit_ticks:
                    break
                if order.side == "sell" and price < order.limit_ticks:
                    break
            lots = min(order.leaves_lots, level["quantity_lots"])
            if lots <= 0:
                continue
            fills.append(self._fill(order, lots, price, now, "take"))
        return fills

    def _fill(
        self,
        order: OrderRecord,
        lots: int,
        price_ticks: int,
        now: datetime,
        liquidity: str,
    ) -> FillRecord:
        instrument = get_instrument(order.symbol)
        self._seq += 1
        gross = notional(lots, price_ticks, instrument)
        fee = self._fee(gross)
        price = from_ticks(price_ticks, instrument.tick_size)
        previous_units = Decimal(order.filled_lots) * instrument.lot_size
        new_units = Decimal(lots) * instrument.lot_size
        previous_avg = self._avg.get(order.order_id, Decimal("0"))
        average = (previous_avg * previous_units + price * new_units) / (previous_units + new_units)
        self._avg[order.order_id] = average
        order.avg_price = f"{average:.{instrument.price_precision}f}"
        order.filled_lots += lots
        order.leaves_lots -= lots
        order.updated_at = now
        fill = FillRecord(
            execution_id=f"EX-{self._seq:08d}",
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            session_id=order.session_id,
            symbol=order.symbol,
            side=order.side,
            quantity_lots=lots,
            price_ticks=price_ticks,
            fee=format_decimal(fee, 4),
            fee_currency=instrument.currency,
            timestamp=now,
            liquidity=liquidity,  # type: ignore[arg-type]
            assumptions=self.assumptions,
        )
        self.fills.append(fill)
        return fill

    def _fee(self, gross: Decimal) -> Decimal:
        bps = self.commission_bps + self.tax_bps
        return (gross * bps) / Decimal(10000)

    def _transition(self, order: OrderRecord, status: str, now: datetime, reason: str) -> None:
        order.status = status  # type: ignore[assignment]
        order.updated_at = now
        if status in {"cancelled", "rejected", "expired", "filled"}:
            order.leaves_lots = 0 if status != "filled" else 0
        order.lifecycle.append(LifecycleStep(status=status, timestamp=now, reason=reason))  # type: ignore[arg-type]

    def _walk(self, side: str, order_type: str, quantity: int, limit_ticks: int | None, book: BookView) -> dict:
        instrument = get_instrument(book.symbol)
        levels = book.asks if side == "buy" else book.bids
        available = sum(level["quantity_lots"] for level in levels)
        remaining = quantity
        notion = Decimal(0)
        filled = 0
        for level in levels:
            if remaining <= 0:
                break
            price = level["price_ticks"]
            if order_type == "limit" and limit_ticks is not None:
                if side == "buy" and price > limit_ticks:
                    break
                if side == "sell" and price < limit_ticks:
                    break
            lots = min(remaining, level["quantity_lots"])
            notion += notional(lots, price, instrument)
            filled += lots
            remaining -= lots
        average = None
        if filled:
            average_px = notion / (Decimal(filled) * instrument.lot_size)
            average = f"{average_px:.{instrument.price_precision}f}"
        return {"filled": filled, "notional": notion, "available": available, "average": average}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
