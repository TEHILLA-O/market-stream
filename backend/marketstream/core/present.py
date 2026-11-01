"""Public JSON for prices, orders, and books.

Chart floats are for rendering only. Text fields are the audited values.
"""

from __future__ import annotations

from decimal import Decimal

from marketstream.core.instruments import Instrument
from marketstream.core.models import FillRecord, OrderRecord, TradeEvent
from marketstream.core.money import format_decimal, format_price, format_qty, from_ticks, notional
from marketstream.market.book import BookView


def price_text(ticks: int | None, instrument: Instrument) -> str | None:
    if ticks is None:
        return None
    return format_price(ticks, instrument.tick_size, instrument.price_precision)


def price_float(ticks: int | Decimal | None, instrument: Instrument) -> float | None:
    if ticks is None:
        return None
    return float(Decimal(ticks) * instrument.tick_size)


def trade_view(trade: TradeEvent, instrument: Instrument) -> dict:
    gross = notional(trade.quantity_lots, trade.price_ticks, instrument)
    return {
        "category": "trade",
        "schema_version": trade.schema_version,
        "event_id": trade.event_id,
        "symbol": trade.symbol,
        "venue": trade.venue,
        "sequence": trade.sequence_number,
        "event_timestamp": trade.event_timestamp.isoformat(),
        "price": price_text(trade.price_ticks, instrument),
        "price_ticks": trade.price_ticks,
        "quantity_lots": trade.quantity_lots,
        "quantity": format_qty(trade.quantity_lots, instrument),
        "notional": format_decimal(gross, 2),
        "aggressor_side": trade.aggressor_side,
        "conditions": trade.trade_conditions,
        "simulated": True,
    }


def order_view(order: OrderRecord, instrument: Instrument) -> dict:
    return {
        "order_id": order.order_id,
        "client_order_id": order.client_order_id,
        "session_id": order.session_id,
        "symbol": order.symbol,
        "side": order.side,
        "order_type": order.order_type,
        "quantity_lots": order.quantity_lots,
        "quantity": format_qty(order.quantity_lots, instrument),
        "limit_price": price_text(order.limit_ticks, instrument),
        "status": order.status,
        "filled_lots": order.filled_lots,
        "leaves_lots": order.leaves_lots,
        "average_price": order.avg_price,
        "reject_rule": order.reject_rule,
        "reject_reason": order.reject_reason,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "simulated": True,
        "queue_model": order.queue_model,
        "lifecycle": [
            {"status": step.status, "timestamp": step.timestamp.isoformat(), "reason": step.reason}
            for step in order.lifecycle
        ],
    }


def fill_view(fill: FillRecord, instrument: Instrument) -> dict:
    return {
        "execution_id": fill.execution_id,
        "order_id": fill.order_id,
        "symbol": fill.symbol,
        "side": fill.side,
        "quantity_lots": fill.quantity_lots,
        "quantity": format_qty(fill.quantity_lots, instrument),
        "price": price_text(fill.price_ticks, instrument),
        "fee": fill.fee,
        "fee_currency": fill.fee_currency,
        "timestamp": fill.timestamp.isoformat(),
        "liquidity": fill.liquidity,
        "assumptions": fill.assumptions,
        "session_id": fill.session_id,
        "simulated": True,
    }


def book_view(view: BookView, instrument: Instrument) -> dict:
    return view.to_public(instrument, price_text, format_qty)


def candle_view(bar: dict, instrument: Instrument) -> dict:
    return {
        "time": int(bar["time"].timestamp()),
        "open": price_float(bar["open_ticks"], instrument),
        "high": price_float(bar["high_ticks"], instrument),
        "low": price_float(bar["low_ticks"], instrument),
        "close": price_float(bar["close_ticks"], instrument),
        "volume": bar["volume_lots"],
        "trade_count": bar["trade_count"],
        "open_text": price_text(bar["open_ticks"], instrument),
        "high_text": price_text(bar["high_ticks"], instrument),
        "low_text": price_text(bar["low_ticks"], instrument),
        "close_text": price_text(bar["close_ticks"], instrument),
        "vwap": None
        if bar["vwap_ticks"] is None
        else f"{(bar['vwap_ticks'] * instrument.tick_size):.{instrument.price_precision}f}",
    }


def signed(value: Decimal) -> str:
    return format_decimal(value, 2)
