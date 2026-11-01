"""Versioned market-event and trading contracts.

Schema version 1. Prices are integer ticks. Quantities are integer lots.
Event time is the virtual market clock. Receive and process times are
wall-clock timestamps on the machine running the feedhandler.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

EventType = Literal[
    "trade",
    "quote",
    "book_snapshot",
    "book_delta",
    "market_status",
    "heartbeat",
    "feed_quality",
]
Side = Literal["buy", "sell"]
BookSide = Literal["bid", "ask"]
Aggressor = Literal["buy", "sell", "unknown"]
UpdateAction = Literal["upsert", "delete"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal[
    "accepted",
    "rejected",
    "working",
    "partially_filled",
    "filled",
    "cancelled",
    "expired",
]
MarketPhase = Literal["open", "halt", "closed", "preopen"]
FeedQualityKind = Literal[
    "gap",
    "duplicate",
    "quarantine",
    "stale",
    "recovered",
    "disconnect",
    "mismatch",
]


class EventBase(BaseModel):
    schema_version: int = SCHEMA_VERSION
    event_id: str
    session_id: str
    event_type: EventType
    source: str = "simulator"
    venue: str
    symbol: str
    sequence_number: int
    event_timestamp: datetime
    receive_timestamp: datetime
    process_timestamp: datetime | None = None


class TradeEvent(EventBase):
    event_type: Literal["trade"] = "trade"
    trade_id: str
    price_ticks: int
    quantity_lots: int
    aggressor_side: Aggressor
    trade_conditions: list[str] = Field(default_factory=list)


class QuoteEvent(EventBase):
    event_type: Literal["quote"] = "quote"
    bid_ticks: int | None = None
    ask_ticks: int | None = None
    bid_quantity_lots: int = 0
    ask_quantity_lots: int = 0


class BookLevel(BaseModel):
    side: BookSide
    price_ticks: int
    quantity_lots: int
    order_count: int | None = None


class BookSnapshotEvent(EventBase):
    event_type: Literal["book_snapshot"] = "book_snapshot"
    levels: list[BookLevel]
    depth: int


class BookDeltaEvent(EventBase):
    event_type: Literal["book_delta"] = "book_delta"
    side: BookSide
    price_ticks: int
    quantity_lots: int
    update_action: UpdateAction
    order_count: int | None = None
    semantics: Literal["absolute"] = "absolute"


class MarketStatusEvent(EventBase):
    event_type: Literal["market_status"] = "market_status"
    status: MarketPhase
    reason: str
    regime: str


class HeartbeatEvent(EventBase):
    event_type: Literal["heartbeat"] = "heartbeat"
    last_sequence: int


class FeedQualityEvent(EventBase):
    event_type: Literal["feed_quality"] = "feed_quality"
    quality: FeedQualityKind
    detail: str
    related_sequence: int | None = None


MarketEvent = Annotated[
    Union[
        TradeEvent,
        QuoteEvent,
        BookSnapshotEvent,
        BookDeltaEvent,
        MarketStatusEvent,
        HeartbeatEvent,
        FeedQualityEvent,
    ],
    Field(discriminator="event_type"),
]


class LifecycleStep(BaseModel):
    status: OrderStatus
    timestamp: datetime
    reason: str = ""


class OrderRecord(BaseModel):
    order_id: str
    client_order_id: str
    session_id: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity_lots: int
    limit_ticks: int | None = None
    status: OrderStatus
    filled_lots: int = 0
    leaves_lots: int = 0
    avg_price: str | None = None
    venue: str
    created_at: datetime
    updated_at: datetime
    reject_rule: str | None = None
    reject_reason: str | None = None
    simulated: bool = True
    queue_model: str = "conservative_trade_through"
    lifecycle: list[LifecycleStep] = Field(default_factory=list)


class FillRecord(BaseModel):
    execution_id: str
    order_id: str
    client_order_id: str
    session_id: str
    symbol: str
    side: Side
    quantity_lots: int
    price_ticks: int
    fee: str
    fee_currency: str
    timestamp: datetime
    simulated: bool = True
    liquidity: Literal["take", "resting"]
    assumptions: str


class OrderRequest(BaseModel):
    client_order_id: str = Field(min_length=1, max_length=80)
    symbol: str
    side: Side
    order_type: OrderType
    quantity_lots: int = Field(gt=0)
    limit_price: str | None = None
    ledger: Literal["live", "replay"] = "live"
