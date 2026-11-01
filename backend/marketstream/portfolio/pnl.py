"""Weighted-average position accounting.

Quantity is signed lots: positive long, negative short. Average cost is
the average entry price of the open quantity only.

Unrealised P&L = signed_lots × lot_size × (mark − average_cost)

That identity holds for shorts because the quantity sign carries the
direction. Realised P&L is recognised when an execution reduces or
closes the open quantity, using the average cost of the quantity that
was closed. Fees are stored separately and are not buried inside
realised P&L.

Gross P&L = realised + unrealised
Net P&L = gross − fees

Rebuilding from the fill list is the source of truth. The incremental
updater must match that rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from marketstream.core.instruments import Instrument, get_instrument
from marketstream.core.models import FillRecord
from marketstream.core.money import format_decimal, from_ticks


@dataclass
class Position:
    symbol: str
    currency: str
    quantity_lots: int = 0
    average_cost: Decimal = Decimal("0")
    realised: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    fills: list[str] = field(default_factory=list)

    @property
    def flat(self) -> bool:
        return self.quantity_lots == 0


@dataclass
class Mark:
    price: Decimal | None
    source: str
    stale: bool
    timestamp: datetime | None


class PositionBook:
    def __init__(self, starting_cash: Decimal) -> None:
        self.starting_cash = starting_cash
        self.cash = {"USD": starting_cash}
        self.positions: dict[str, Position] = {}

    def apply_fill(self, fill: FillRecord) -> Position:
        instrument = get_instrument(fill.symbol)
        position = self.positions.get(fill.symbol)
        if position is None:
            position = Position(symbol=fill.symbol, currency=instrument.currency)
            self.positions[fill.symbol] = position
        price = from_ticks(fill.price_ticks, instrument.tick_size)
        fee = Decimal(fill.fee)
        signed = fill.quantity_lots if fill.side == "buy" else -fill.quantity_lots
        self._apply_quantity(position, signed, price)
        position.fees += fee
        position.fills.append(fill.execution_id)
        self._apply_cash(instrument, fill.side, fill.quantity_lots, price, fee)
        return position

    def rebuild(self, fills: list[FillRecord]) -> None:
        cash0 = self.starting_cash
        self.cash = {"USD": cash0}
        self.positions = {}
        for fill in fills:
            self.apply_fill(fill)

    def _apply_quantity(self, position: Position, signed: int, price: Decimal) -> None:
        current = position.quantity_lots
        if current == 0 or (current > 0 and signed > 0) or (current < 0 and signed < 0):
            new_qty = current + signed
            opened = abs(signed)
            previous = abs(current)
            position.average_cost = (
                (Decimal(previous) * position.average_cost + Decimal(opened) * price) / Decimal(abs(new_qty))
            )
            position.quantity_lots = new_qty
            return
        closing = min(abs(current), abs(signed))
        if current > 0:
            position.realised += Decimal(closing) * (price - position.average_cost) * _lot(position.symbol)
        else:
            position.realised += Decimal(closing) * (position.average_cost - price) * _lot(position.symbol)
        leftover_open = abs(signed) - closing
        leftover_position = abs(current) - closing
        if leftover_open > 0:
            position.quantity_lots = leftover_open if signed > 0 else -leftover_open
            position.average_cost = price
        elif leftover_position == 0:
            position.quantity_lots = 0
            position.average_cost = Decimal("0")
        else:
            position.quantity_lots = leftover_position if current > 0 else -leftover_position

    def _apply_cash(self, instrument: Instrument, side: str, lots: int, price: Decimal, fee: Decimal) -> None:
        gross = Decimal(lots) * instrument.lot_size * price
        bucket = self.cash.setdefault(instrument.currency, Decimal("0"))
        if side == "buy":
            self.cash[instrument.currency] = bucket - gross - fee
        else:
            self.cash[instrument.currency] = bucket + gross - fee

    def view(self, symbol: str, mark: Mark, instrument: Instrument) -> dict:
        position = self.positions.get(symbol) or Position(symbol=symbol, currency=instrument.currency)
        unrealised = Decimal("0")
        market_value = Decimal("0")
        if position.quantity_lots and mark.price is not None:
            unrealised = (
                Decimal(position.quantity_lots) * instrument.lot_size * (mark.price - position.average_cost)
            )
            market_value = Decimal(position.quantity_lots) * instrument.lot_size * mark.price
        gross = position.realised + unrealised
        net = gross - position.fees
        return {
            "symbol": symbol,
            "description": instrument.description,
            "asset_class": instrument.asset_class,
            "currency": instrument.currency,
            "quantity_lots": position.quantity_lots,
            "quantity": f"{(Decimal(position.quantity_lots) * instrument.lot_size):.{instrument.quantity_precision}f}",
            "direction": "flat" if position.quantity_lots == 0 else "long" if position.quantity_lots > 0 else "short",
            "average_cost": f"{position.average_cost:.{instrument.price_precision}f}",
            "mark": None if mark.price is None else f"{mark.price:.{instrument.price_precision}f}",
            "mark_source": mark.source,
            "mark_stale": mark.stale,
            "market_value": format_decimal(market_value, 2),
            "realised_pnl": format_decimal(position.realised, 2),
            "unrealised_pnl": format_decimal(unrealised, 2),
            "fees": format_decimal(position.fees, 4),
            "gross_pnl": format_decimal(gross, 2),
            "net_pnl": format_decimal(net, 2),
            "execution_ids": list(position.fills),
            "simulated": True,
        }

    def totals(self, views: list[dict]) -> dict:
        realised = sum((Decimal(row["realised_pnl"]) for row in views), Decimal("0"))
        unrealised = sum((Decimal(row["unrealised_pnl"]) for row in views), Decimal("0"))
        fees = sum((Decimal(row["fees"]) for row in views), Decimal("0"))
        market_value = sum((Decimal(row["market_value"]) for row in views), Decimal("0"))
        gross = realised + unrealised
        net = gross - fees
        cash = self.cash.get("USD", Decimal("0"))
        equity = cash + market_value
        return {
            "currency": "USD",
            "fx_rate": "1",
            "fx_note": "Starter instruments are all priced in USD. No cross-currency conversion is applied.",
            "starting_cash": format_decimal(self.starting_cash, 2),
            "cash": format_decimal(cash, 2),
            "market_value": format_decimal(market_value, 2),
            "equity": format_decimal(equity, 2),
            "realised_pnl": format_decimal(realised, 2),
            "unrealised_pnl": format_decimal(unrealised, 2),
            "fees": format_decimal(fees, 4),
            "gross_pnl": format_decimal(gross, 2),
            "net_pnl": format_decimal(net, 2),
            "simulated": True,
        }


def _lot(symbol: str) -> Decimal:
    return get_instrument(symbol).lot_size
