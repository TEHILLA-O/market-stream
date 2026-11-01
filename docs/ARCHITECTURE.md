# Architecture

MarketStream is one Python process plus a React workstation. q is an optional second process. There is no Kafka, Redis, or extra broker.

## Processes

| Piece | Role |
| --- | --- |
| Simulator | Deterministic pulses on a virtual clock |
| Feedhandler | Schema, instrument, price, quantity, and sequence checks |
| Session log | Append-only `events.jsonl` per session |
| Book service | Snapshot and absolute-delta reconstruction |
| Tick store | Bounded in-memory trades and quotes for the current session |
| Execution engine | Paper orders against the reconstructed book |
| Position book | Weighted-average lots, cash, fees |
| Risk and decisions | Pre-trade checks, exposures, rule records |
| Replay studio | A second book driven by a log, isolated from the live ledger |
| Q bridge | TCP probe, then PyKX IPC if a q process answers |
| FastAPI | REST and `/ws/v1/market` |
| React | Workstation. The browser is not the source of fills or positions |

## Startup and shutdown

`Platform.startup` opens a new live session id, warms `MARKETSTREAM_WARMUP_PULSES` virtual seconds, then starts the async loop. Fills already on disk are rebuilt into positions before the loop. Working orders from a previous process are not restored: a new market path must not fill old resting orders. The fill ledger itself is kept.

On shutdown the session log and the account ledger are flushed and closed.

A market reset expires resting live orders, closes the session file, and starts a new seeded session. Cash and positions stay. That split is deliberate: the account is not the market session.

## Clock

Each pulse moves the virtual clock by one second. Wall-clock speed only changes how often `pulse()` is called. Reconnecting a browser does not reseed the generator.

## Recovery

| Failure | What comes back | What does not |
| --- | --- | --- |
| API restart | Fills, positions, cash, closed session logs | The in-memory book and working orders |
| WebSocket drop | Client reconnects, receives a fresh frame, refetches candles | Missed frames are not replayed tick-by-tick to that socket |
| Sequence gap | Book is marked stale and deltas are quarantined until a snapshot | The UI does not keep a green book through the gap |
| q down | Python reference mode | No pretend kdb+ answers |

The session log flushes every 40 events. A crash can lose that tail.

## WebSocket

Clients send `subscribe` / `unsubscribe` with symbols and channels. The server sends a `batch` of versioned messages about ten times a second: heartbeat, simulation, system, per-symbol quote stats, top of book, the latest 5-second bar, new trades, positions, and risk. An empty symbol set means all instruments. The hub drops a client that can no longer accept writes. The connection cap defaults to 32.

Order posts are limited to 20 per 10 seconds per client address. If `MARKETSTREAM_API_TOKEN` is set, REST calls need `Authorization: Bearer`, and the socket needs `?token=`.
