"""Exact tick and decimal helpers.

Prices are stored as integer ticks. A tick is the instrument's minimum
price increment. Equality of prices is equality of those integers.
Quantities are stored as integer lots. A lot is the instrument's
minimum quantity increment.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from marketstream.core.instruments import Instrument


def to_ticks(price: Decimal, tick_size: Decimal) -> int:
    if tick_size <= 0:
        raise ValueError("tick size must be positive")
    quotient = price / tick_size
    integral = quotient.to_integral_value(rounding=ROUND_HALF_EVEN)
    if quotient != integral:
        raise ValueError(f"price {price} is not aligned to tick {tick_size}")
    return int(integral)


def from_ticks(ticks: int, tick_size: Decimal) -> Decimal:
    return Decimal(ticks) * tick_size


def format_price(ticks: int, tick_size: Decimal, precision: int) -> str:
    return f"{from_ticks(ticks, tick_size):.{precision}f}"


def format_decimal(value: Decimal, places: int) -> str:
    quantised = value.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_EVEN)
    return f"{quantised:.{places}f}"


def units_for(lots: int, instrument: Instrument) -> Decimal:
    return Decimal(lots) * instrument.lot_size


def notional(lots: int, price_ticks: int, instrument: Instrument) -> Decimal:
    price = from_ticks(price_ticks, instrument.tick_size)
    return units_for(lots, instrument) * price


def format_qty(lots: int, instrument: Instrument) -> str:
    units = units_for(lots, instrument)
    return format_decimal(units, instrument.quantity_precision)
