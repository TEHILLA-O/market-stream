"""Feed boundary. Validates simulator output before it reaches storage or the book.

The simulator is trusted to build well-typed events. This handler still
checks the invariants a real feed must enforce: known instruments,
positive prices, non-negative quantities, and schema version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from marketstream.core.instruments import CATALOGUE
from marketstream.core.models import SCHEMA_VERSION, FeedQualityEvent, MarketEvent


@dataclass
class FeedResult:
    accepted: list[MarketEvent] = field(default_factory=list)
    quarantined: list[dict] = field(default_factory=list)


class FeedHandler:
    def __init__(self, source_name: str = "marketstream-feed") -> None:
        self.source_name = source_name
        self.accepted = 0
        self.quarantined = 0
        self.duplicates = 0
        self.gaps = 0
        self.last_sequence: dict[str, int] = {}
        self.connected = True

    def handle_many(self, events: list[MarketEvent], now: datetime | None = None) -> FeedResult:
        result = FeedResult()
        clock = now or datetime.now(timezone.utc)
        for event in events:
            checked = self.handle(event, clock)
            if checked is None:
                continue
            result.accepted.append(checked)
        return result

    def handle(self, event: MarketEvent, now: datetime | None = None) -> MarketEvent | None:
        clock = now or datetime.now(timezone.utc)
        reason = self._reject_reason(event)
        if reason:
            self.quarantined += 1
            return None
        if event.schema_version != SCHEMA_VERSION:
            self.quarantined += 1
            return None
        previous = self.last_sequence.get(event.symbol)
        if previous is not None and event.sequence_number == previous:
            self.duplicates += 1
            return None
        if previous is not None and event.sequence_number < previous:
            self.quarantined += 1
            return None
        if previous is not None and event.sequence_number > previous + 1:
            self.gaps += 1
        self.last_sequence[event.symbol] = event.sequence_number
        stamped = event.model_copy(update={"process_timestamp": clock, "source": event.source or self.source_name})
        self.accepted += 1
        return stamped

    def _reject_reason(self, event: MarketEvent) -> str | None:
        if event.symbol not in CATALOGUE:
            return "unknown instrument"
        if event.sequence_number < 0:
            return "invalid sequence"
        if event.event_type == "trade":
            if event.price_ticks <= 0:
                return "invalid price"
            if event.quantity_lots <= 0:
                return "invalid quantity"
        if event.event_type == "book_delta":
            if event.price_ticks <= 0 or event.quantity_lots < 0:
                return "invalid book delta"
        if event.event_type == "quote":
            if event.bid_ticks is not None and event.bid_ticks <= 0:
                return "invalid bid"
            if event.ask_ticks is not None and event.ask_ticks <= 0:
                return "invalid ask"
        return None

    def quality_event(
        self,
        symbol: str,
        session_id: str,
        venue: str,
        sequence: int,
        kind: str,
        detail: str,
        when: datetime,
    ) -> FeedQualityEvent:
        return FeedQualityEvent(
            event_id=f"{session_id}:{symbol}:fq:{sequence}:{kind}",
            session_id=session_id,
            venue=venue,
            symbol=symbol,
            sequence_number=sequence,
            event_timestamp=when,
            receive_timestamp=when,
            quality=kind,  # type: ignore[arg-type]
            detail=detail,
            related_sequence=sequence,
        )

    def mark_disconnected(self) -> None:
        self.connected = False

    def mark_connected(self) -> None:
        self.connected = True
