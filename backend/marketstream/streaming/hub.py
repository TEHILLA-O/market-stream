"""WebSocket fan-out. One JSON batch per client per frame."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import WebSocket


@dataclass
class Subscriber:
    socket: WebSocket
    symbols: set[str] = field(default_factory=set)
    channels: set[str] = field(
        default_factory=lambda: {
            "trades",
            "quotes",
            "book",
            "ohlc",
            "status",
            "positions",
            "risk",
            "orders",
            "alerts",
        }
    )


class StreamHub:
    def __init__(self, max_clients: int) -> None:
        self.max_clients = max_clients
        self.clients: list[Subscriber] = []

    def add(self, socket: WebSocket) -> Subscriber:
        if len(self.clients) >= self.max_clients:
            raise RuntimeError("connection limit reached")
        client = Subscriber(socket=socket)
        self.clients.append(client)
        return client

    def remove(self, client: Subscriber) -> None:
        if client in self.clients:
            self.clients.remove(client)

    async def publish(self, frame: dict) -> None:
        dead: list[Subscriber] = []
        for client in self.clients:
            payload = _filter(frame, client)
            try:
                await client.socket.send_json(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            self.remove(client)


def _filter(frame: dict, client: Subscriber) -> dict:
    messages = []
    for message in frame.get("messages", []):
        category = message.get("category")
        if category in {"heartbeat", "system", "simulation"}:
            messages.append(message)
            continue
        symbol = message.get("symbol")
        if client.symbols and symbol and symbol not in client.symbols:
            continue
        channel = _channel(category)
        if channel and channel not in client.channels:
            continue
        messages.append(message)
    return {"schema_version": 1, "category": "batch", "messages": messages}


def _channel(category: str | None) -> str | None:
    return {
        "trade": "trades",
        "quote": "quotes",
        "book": "book",
        "ohlc": "ohlc",
        "position": "positions",
        "risk": "risk",
        "order": "orders",
        "alert": "alerts",
        "system": "status",
        "heartbeat": "status",
        "simulation": "status",
    }.get(category or "")
