"""FastAPI routes. Business rules stay in the platform, not in the handlers."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from marketstream import __version__
from marketstream.core.config import Settings
from marketstream.core.instruments import get_instrument, list_instruments
from marketstream.core.logging import configure_logging, get_logger
from marketstream.core.models import OrderRequest
from marketstream.platform import Platform
from marketstream.queries.catalog import INTERVALS

log = get_logger("api")
_order_hits: dict[str, deque] = defaultdict(deque)


class SpeedBody(BaseModel):
    speed: float = Field(gt=0, le=50)


class RegimeBody(BaseModel):
    regime: str


class SeekBody(BaseModel):
    index: int | None = None
    timestamp: str | None = None


class StepBody(BaseModel):
    count: int = 1


class LoadBody(BaseModel):
    session_id: str


class QueryBody(BaseModel):
    query_id: str
    symbol: str = "ATHR"
    interval: str = "5s"


class LimitBody(BaseModel):
    max_position_lots: int | None = None
    max_gross_exposure: str | None = None
    max_net_exposure: str | None = None
    max_symbol_concentration: str | None = None
    daily_loss: str | None = None
    max_order_notional: str | None = None
    max_order_lots: int | None = None
    drawdown_alert: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.platform = Platform(settings)
        await app.state.platform.startup()
        yield
        await app.state.platform.shutdown()

    app = FastAPI(
        title="MarketStream",
        version=__version__,
        summary="Simulated market-data workstation. Orders are paper trades.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        incoming = request.headers.get("x-request-id") or f"ms-{int(time.time() * 1000)}"
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request_failed", path=request.url.path, request_id=incoming)
            raise
        response.headers["x-request-id"] = incoming
        return response

    def platform(request: Request) -> Platform:
        _authorise(request)
        return request.app.state.platform

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "marketstream", "simulated": True}

    @app.get("/api/v1/instruments")
    def instruments(request: Request):
        platform(request)
        return {"instruments": [item.to_public() for item in list_instruments()]}

    @app.get("/api/v1/instruments/{symbol}")
    def instrument(symbol: str, request: Request):
        platform(request)
        try:
            return get_instrument(symbol.upper()).to_public()
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/v1/market/trades")
    def trades(request: Request, symbol: str | None = None, limit: int = 100):
        return {"trades": platform(request).trades(symbol.upper() if symbol else None, min(limit, 500))}

    @app.get("/api/v1/market/quotes")
    def quotes(request: Request, symbol: str, limit: int = 100):
        _symbol(symbol)
        return {"quotes": platform(request).quotes(symbol.upper(), min(limit, 500))}

    @app.get("/api/v1/market/orderbook")
    def orderbook(request: Request, symbol: str):
        _symbol(symbol)
        return platform(request).order_book(symbol.upper())

    @app.get("/api/v1/market/depth")
    def depth(request: Request, symbol: str):
        _symbol(symbol)
        return {"symbol": symbol.upper(), "history": platform(request).depth_history(symbol.upper())}

    @app.get("/api/v1/market/candles")
    def candles(request: Request, symbol: str, interval: str = "5s", limit: int = 300):
        _symbol(symbol)
        if interval not in INTERVALS:
            raise HTTPException(400, f"interval must be one of {', '.join(INTERVALS)}")
        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "note": "OHLC is built from trades. Buckets without trades are omitted. Floats are for chart rendering.",
            "candles": platform(request).candles(symbol.upper(), interval, min(limit, 1000)),
        }

    @app.get("/api/v1/market/stats")
    def stats(request: Request, symbol: str):
        _symbol(symbol)
        return platform(request).symbol_stats(symbol.upper())

    @app.get("/api/v1/market/history")
    def history(request: Request):
        return {"sessions": platform(request).sessions()}

    @app.get("/api/v1/simulation")
    def simulation(request: Request):
        return platform(request).simulation_state()

    @app.post("/api/v1/simulation/pause")
    def pause(request: Request):
        return platform(request).pause()

    @app.post("/api/v1/simulation/resume")
    def resume(request: Request):
        return platform(request).resume()

    @app.post("/api/v1/simulation/reset")
    def reset(request: Request):
        return platform(request).reset_market()

    @app.post("/api/v1/simulation/speed")
    def speed(body: SpeedBody, request: Request):
        return platform(request).set_speed(body.speed)

    @app.post("/api/v1/simulation/regime")
    def regime(body: RegimeBody, request: Request):
        try:
            return platform(request).set_regime(body.regime)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/simulation/gap")
    def gap(request: Request):
        return platform(request).inject_gap()

    @app.get("/api/v1/replay/sessions")
    def replay_sessions(request: Request):
        return {"sessions": platform(request).sessions()}

    @app.post("/api/v1/replay/load")
    def replay_load(body: LoadBody, request: Request):
        try:
            platform(request).load_replay(body.session_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, f"unknown session {body.session_id}") from exc
        return platform(request).replay_view("ATHR")

    @app.post("/api/v1/replay/play")
    def replay_play(request: Request):
        core = platform(request)
        core.replay.play()
        return core.replay_view("ATHR")

    @app.post("/api/v1/replay/pause")
    def replay_pause(request: Request):
        core = platform(request)
        core.replay.pause()
        return core.replay.status()

    @app.post("/api/v1/replay/step")
    def replay_step(body: StepBody, request: Request):
        core = platform(request)
        core.replay.step(body.count)
        return core.replay.status()

    @app.post("/api/v1/replay/speed")
    def replay_speed(body: SpeedBody, request: Request, symbol: str = "ATHR"):
        _symbol(symbol)
        core = platform(request)
        core.replay.speed = max(0.25, min(body.speed, 50))
        return core.replay_view(symbol.upper())

    @app.post("/api/v1/replay/seek")
    def replay_seek(body: SeekBody, request: Request):
        core = platform(request)
        if body.timestamp:
            core.replay.seek_time(body.timestamp)
        elif body.index is not None:
            core.replay.seek(body.index)
        else:
            raise HTTPException(400, "index or timestamp is required")
        return core.replay.status()

    @app.get("/api/v1/replay/state")
    def replay_state(request: Request, symbol: str = "ATHR"):
        _symbol(symbol)
        return platform(request).replay_view(symbol.upper())

    @app.post("/api/v1/orders/preview")
    def preview(body: OrderRequest, request: Request):
        _symbol(body.symbol)
        body.symbol = body.symbol.upper()
        try:
            return platform(request).preview_order(body)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/orders")
    def submit(body: OrderRequest, request: Request):
        _limit_orders(request)
        _symbol(body.symbol)
        body.symbol = body.symbol.upper()
        try:
            return platform(request).submit_order(body)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/v1/orders")
    def orders(request: Request, ledger: str = "live"):
        return {"orders": platform(request).orders(ledger), "simulated": True}

    @app.post("/api/v1/orders/{order_id}/cancel")
    def cancel(order_id: str, request: Request, ledger: str = "live"):
        try:
            return platform(request).cancel_order(order_id, ledger)
        except KeyError as exc:
            raise HTTPException(404, "unknown order") from exc

    @app.get("/api/v1/executions")
    def executions(request: Request, ledger: str = "live"):
        return {"executions": platform(request).fills(ledger), "simulated": True}

    @app.get("/api/v1/positions")
    def positions(request: Request, ledger: str = "live"):
        return platform(request).portfolio(ledger)

    @app.get("/api/v1/pnl")
    def pnl(request: Request, ledger: str = "live"):
        report = platform(request).portfolio(ledger)
        return report["totals"]

    @app.get("/api/v1/risk")
    def risk(request: Request):
        return platform(request).risk_snapshot()

    @app.get("/api/v1/risk/limits")
    def limits(request: Request):
        return platform(request).risk.limits.to_public()

    @app.put("/api/v1/risk/limits")
    def update_limits(body: LimitBody, request: Request):
        current = platform(request).risk.limits
        data = body.model_dump(exclude_none=True)
        for key, value in data.items():
            existing = getattr(current, key)
            if isinstance(existing, Decimal):
                setattr(current, key, Decimal(str(value)))
            else:
                setattr(current, key, value)
        return current.to_public()

    @app.get("/api/v1/signals")
    def signals(request: Request, symbol: str | None = None):
        if symbol:
            _symbol(symbol)
        return platform(request).signals(symbol.upper() if symbol else None)

    @app.get("/api/v1/queries")
    def queries(request: Request):
        return {"queries": platform(request).list_queries(), "unrestricted_q": False}

    @app.post("/api/v1/queries/run")
    def run_query(body: QueryBody, request: Request):
        _symbol(body.symbol)
        if body.interval not in INTERVALS:
            raise HTTPException(400, "unsupported interval")
        try:
            return platform(request).run_query(body.query_id, body.symbol.upper(), body.interval)
        except KeyError as exc:
            raise HTTPException(404, f"unknown query {body.query_id}") from exc

    @app.get("/api/v1/system")
    def system(request: Request):
        return platform(request).system_status()

    @app.websocket("/ws/v1/market")
    async def market_socket(socket: WebSocket):
        token = settings.api_token
        if token and socket.query_params.get("token") != token:
            await socket.close(code=4401)
            return
        await socket.accept()
        core: Platform = socket.app.state.platform
        try:
            client = core.hub.add(socket)
        except RuntimeError:
            await socket.send_json({"schema_version": 1, "category": "error", "detail": "connection limit reached"})
            await socket.close(code=1013)
            return
        await socket.send_json(core.frame())
        try:
            while True:
                message = await socket.receive_json()
                kind = message.get("type")
                if kind == "subscribe":
                    symbols = {item.upper() for item in message.get("symbols", [])}
                    client.symbols = symbols
                    channels = message.get("channels")
                    if channels:
                        client.channels = set(channels)
                    await socket.send_json(core.frame())
                elif kind == "unsubscribe":
                    for item in message.get("symbols", []):
                        client.symbols.discard(item.upper())
                else:
                    await socket.send_json(
                        {"schema_version": 1, "category": "error", "detail": "unsupported message"}
                    )
        except WebSocketDisconnect:
            core.hub.remove(client)
        except Exception:
            core.hub.remove(client)
            log.exception("websocket_closed")

    return app


def _symbol(symbol: str) -> None:
    try:
        get_instrument(symbol.upper())
    except KeyError as exc:
        raise HTTPException(404, f"unknown instrument {symbol}") from exc


def _authorise(request: Request) -> None:
    token = request.app.state.settings.api_token
    if not token:
        return
    if request.headers.get("authorization") != f"Bearer {token}":
        raise HTTPException(401, "authentication required")


def _limit_orders(request: Request) -> None:
    host = request.client.host if request.client else "local"
    now = time.monotonic()
    bucket = _order_hits[host]
    while bucket and now - bucket[0] > 10:
        bucket.popleft()
    if len(bucket) >= 20:
        raise HTTPException(429, "order rate limit exceeded")
    bucket.append(now)


app = create_app()
