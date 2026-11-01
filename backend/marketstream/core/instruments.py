"""Synthetic instrument catalogue.

Every instrument is fictional. Nothing here is a live exchange listing.
Prices are quoted in the instrument's P&L currency, which is USD for
the starter set, so portfolio totals do not require a cross-rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

AssetClass = Literal["equity", "index", "fx", "etf", "crypto"]


@dataclass(frozen=True)
class Instrument:
    symbol: str
    description: str
    asset_class: AssetClass
    currency: str
    tick_size: Decimal
    lot_size: Decimal
    session: str
    venue: str
    venue_name: str
    reference_price: Decimal
    price_precision: int
    quantity_precision: int
    base_spread_ticks: int
    base_depth_lots: int
    synthetic: bool = True

    def to_public(self) -> dict:
        return {
            "symbol": self.symbol,
            "description": self.description,
            "asset_class": self.asset_class,
            "currency": self.currency,
            "tick_size": f"{self.tick_size:f}",
            "lot_size": f"{self.lot_size:f}",
            "session": self.session,
            "venue": self.venue,
            "venue_name": self.venue_name,
            "reference_price": f"{self.reference_price:.{self.price_precision}f}",
            "price_precision": self.price_precision,
            "quantity_precision": self.quantity_precision,
            "base_spread_ticks": self.base_spread_ticks,
            "base_depth_lots": self.base_depth_lots,
            "synthetic": True,
            "label": "synthetic",
        }


def _equity(
    symbol: str,
    description: str,
    reference: str,
    spread: int,
    depth: int,
    asset_class: AssetClass = "equity",
    tick: str = "0.01",
    precision: int = 2,
    venue: str = "MSX",
    venue_name: str = "Meridian Synthetic Exchange",
    session: str = "synthetic-continuous",
) -> Instrument:
    return Instrument(
        symbol=symbol,
        description=description,
        asset_class=asset_class,
        currency="USD",
        tick_size=Decimal(tick),
        lot_size=Decimal("1"),
        session=session,
        venue=venue,
        venue_name=venue_name,
        reference_price=Decimal(reference),
        price_precision=precision,
        quantity_precision=0,
        base_spread_ticks=spread,
        base_depth_lots=depth,
    )


CATALOGUE: dict[str, Instrument] = {
    inst.symbol: inst
    for inst in (
        _equity(
            "ATHR",
            "Aether Semiconductor — synthetic large-cap equity",
            "186.40",
            spread=2,
            depth=800,
        ),
        _equity(
            "BRDL",
            "Broadleaf Equity Fund — synthetic ETF",
            "54.20",
            spread=1,
            depth=2200,
            asset_class="etf",
        ),
        _equity(
            "NL100",
            "Northline 100 — synthetic equity index future-style print",
            "5125.00",
            spread=1,
            depth=40,
            asset_class="index",
            tick="0.25",
            precision=2,
        ),
        Instrument(
            symbol="HLX",
            description="Helix — synthetic sterling versus US dollar",
            asset_class="fx",
            currency="USD",
            tick_size=Decimal("0.0001"),
            lot_size=Decimal("1000"),
            session="synthetic-continuous",
            venue="MSFX",
            venue_name="Meridian Synthetic FX",
            reference_price=Decimal("1.2740"),
            price_precision=4,
            quantity_precision=0,
            base_spread_ticks=2,
            base_depth_lots=25,
        ),
        Instrument(
            symbol="LUMN",
            description="Lumen Coin — synthetic continuously traded crypto-style instrument",
            asset_class="crypto",
            currency="USD",
            tick_size=Decimal("0.05"),
            lot_size=Decimal("0.01"),
            session="synthetic-continuous",
            venue="MSCX",
            venue_name="Meridian Synthetic Crypto",
            reference_price=Decimal("42.50"),
            price_precision=2,
            quantity_precision=2,
            base_spread_ticks=2,
            base_depth_lots=500,
        ),
    )
}


def get_instrument(symbol: str) -> Instrument:
    try:
        return CATALOGUE[symbol]
    except KeyError as exc:
        raise KeyError(f"unknown instrument {symbol}") from exc


def list_instruments() -> list[Instrument]:
    return [CATALOGUE[symbol] for symbol in ("ATHR", "BRDL", "NL100", "HLX", "LUMN")]
