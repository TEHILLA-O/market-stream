"""Append-only session logs.

Market events are one JSON document per line and can lose the last
unflushed batch if the process is killed. Orders and fills are flushed
on every write so the account ledger survives a restart.
"""

from __future__ import annotations

import json
from pathlib import Path

from marketstream.core.models import FillRecord, MarketEvent, OrderRecord


class JsonlLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("a", encoding="utf-8")
        self._pending = 0

    def write(self, payload: str) -> None:
        self._handle.write(payload)
        self._handle.write("\n")
        self._pending += 1
        if self._pending >= 40:
            self.flush()

    def flush(self) -> None:
        self._handle.flush()
        self._pending = 0

    def close(self) -> None:
        self.flush()
        self._handle.close()


class SessionArchive:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.events: JsonlLog | None = None
        self.session_id: str | None = None

    def open_session(self, session_id: str, meta: dict) -> None:
        self.close()
        folder = self.root / "sessions" / session_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self.events = JsonlLog(folder / "events.jsonl")
        self.session_id = session_id

    def append_event(self, event: MarketEvent) -> None:
        if self.events is not None:
            self.events.write(event.model_dump_json())

    def close(self) -> None:
        if self.events is not None:
            self.events.close()
            self.events = None

    def list_sessions(self) -> list[dict]:
        base = self.root / "sessions"
        if not base.exists():
            return []
        found = []
        for folder in sorted(base.iterdir()):
            meta_path = folder / "meta.json"
            if not meta_path.exists():
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["session_id"] = folder.name
            meta["events_path"] = str(folder / "events.jsonl")
            found.append(meta)
        return found


class AccountLedger:
    def __init__(self, root: Path) -> None:
        folder = root / "ledger"
        folder.mkdir(parents=True, exist_ok=True)
        self.orders = JsonlLog(folder / "orders.jsonl")
        self.fills = JsonlLog(folder / "fills.jsonl")

    def append_order(self, order: OrderRecord) -> None:
        self.orders.write(order.model_dump_json())
        self.orders.flush()

    def append_fill(self, fill: FillRecord) -> None:
        self.fills.write(fill.model_dump_json())
        self.fills.flush()

    def load_fills(self) -> list[FillRecord]:
        return [_load(FillRecord, line) for line in _lines(self.fills.path)]

    def load_orders(self) -> list[OrderRecord]:
        latest: dict[str, OrderRecord] = {}
        for line in _lines(self.orders.path):
            order = _load(OrderRecord, line)
            latest[order.order_id] = order
        return list(latest.values())

    def close(self) -> None:
        self.orders.close()
        self.fills.close()


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load(model, line: str):
    return model.model_validate_json(line)
