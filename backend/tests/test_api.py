"""API tests against an in-process paper market."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from marketstream.api.app import create_app
from marketstream.core.config import Settings


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        warmup_pulses=12,
        q_enabled=False,
        build_demos=False,
        seed=11,
        speed=1,
    )
    return TestClient(create_app(settings))


def test_market_order_and_position_round_trip(tmp_path: Path):
    with _client(tmp_path) as client:
        book = client.get("/api/v1/market/orderbook", params={"symbol": "ATHR"})
        assert book.status_code == 200
        body = book.json()
        assert body["health"]["stale"] is False
        assert body["best_bid"] is not None
        preview = client.post(
            "/api/v1/orders/preview",
            json={
                "client_order_id": "preview-1",
                "symbol": "ATHR",
                "side": "buy",
                "order_type": "market",
                "quantity_lots": 10,
            },
        )
        assert preview.status_code == 200
        assert preview.json()["simulated"] is True
        submitted = client.post(
            "/api/v1/orders",
            json={
                "client_order_id": "order-1",
                "symbol": "ATHR",
                "side": "buy",
                "order_type": "market",
                "quantity_lots": 10,
            },
        )
        assert submitted.status_code == 200
        order = submitted.json()
        assert order["simulated"] is True
        assert order["status"] in {"filled", "cancelled", "rejected"}
        if order["status"] == "rejected":
            assert order["reject_rule"]
        else:
            positions = client.get("/api/v1/positions").json()
            assert positions["simulated"] is True
            assert positions["totals"]["currency"] == "USD"
        candles = client.get("/api/v1/market/candles", params={"symbol": "ATHR", "interval": "5s"})
        assert candles.status_code == 200
        assert candles.json()["candles"]
        system = client.get("/api/v1/system").json()
        names = {item["name"]: item["state"] for item in system["components"]}
        assert names["simulator"] == "live"
        assert names["tickerplant"] == "unavailable"
        assert "not kdb+" in names["analytics"] or names["analytics"] == "python-reference"
        query = client.post("/api/v1/queries/run", json={"query_id": "vwap", "symbol": "ATHR", "interval": "5s"})
        assert query.status_code == 200
        payload = query.json()
        assert payload["engine"] == "python-reference"
        assert payload["executed_unrestricted_q"] is False
        assert payload["rows"]
