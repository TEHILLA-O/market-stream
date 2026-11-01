# MarketStream

MarketStream is a simulated trading workstation. It turns a deterministic stream of synthetic trades, quotes, and order-book updates into a reconstructable book, a paper account, and a set of risk and analytics views.

Nothing in the default process is a live exchange feed, and nothing in the order ticket is a real order. The instruments are fictional: Aether Semiconductor (`ATHR`), Broadleaf (`BRDL`), Northline 100 (`NL100`), Helix FX (`HLX`), and Lumen Coin (`LUMN`).

## What is actually running

On this machine there is no kdb+ / KDB-X runtime. KDB-X Community Edition needs a licence key from the KX Developer Center and, on Windows, a WSL2 Linux distro. Native Windows is not a supported KDB-X platform.

Until that runtime is installed and listening, MarketStream runs in **Python reference mode**:

- The simulator, feedhandler, order book, paper fills, positions, risk checks, and REST/WebSocket API are real and tested.
- The q scripts under `q/` are real source, including `q/tests/runtests.q`. They have **not** been executed here, because `q` is not on `PATH`.
- The ribbon and Systems workspace say `PYTHON REF`. Query Lab shows the q expression and the Python result, and it records `executed_unrestricted_q: false`. The Python result is not a kdb+ result.

If a q process is later started on `127.0.0.1:5001` with the project scripts loaded, the bridge attempts an unlicensed PyKX IPC connection. Embedded q inside Python still requires a licence. See [docs/KDB_ENGINE.md](docs/KDB_ENGINE.md).

## Architecture

```
simulator → feedhandler → session log
                       ↘ in-memory book, trades, quotes
                       ↘ optional q IPC
paper orders → reconstructed book → fills → weighted-average positions
WebSocket / REST → React workstation
```

The live account ledger is append-only JSONL. Replay uses a separate book and does not write that ledger.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

Requirements: Python 3.12 and Node 22 (Node 20 also worked in the check below). Docker and q are optional.

```bash
python -m venv .venv
.venv/bin/pip install -e "./backend[dev]"
.venv/bin/python -m marketstream        # API on 127.0.0.1:8000
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev                             # workstation on 127.0.0.1:5173
```

On Windows use `.venv\Scripts\python` instead of `.venv/bin/python`. `scripts/dev.sh` and `scripts/dev.ps1` start both processes. The `Makefile` targets use Windows paths (`.venv/Scripts`), so on Linux or macOS run the commands above directly.

If port 8000 is taken, set `MARKETSTREAM_PORT` for the API and `MARKETSTREAM_API` (for example `http://127.0.0.1:8765`) for Vite.

The first launch writes six demo sessions into `data/sessions/` and warms the live book before serving. `data/` is not committed.

## Real output

From a fresh clone on Linux on 1 November 2026, with no q runtime:

```bash
curl -s 127.0.0.1:8000/healthz
```

```json
{"status":"ok","service":"marketstream","simulated":true}
```

A paper market order:

```bash
curl -s -X POST 127.0.0.1:8000/api/v1/orders -H 'content-type: application/json' \
  -d '{"client_order_id":"doc-check-1","symbol":"ATHR","side":"buy","order_type":"market","quantity_lots":10}'
```

```json
{"order_id":"live-00000001","symbol":"ATHR","side":"buy","order_type":"market","quantity_lots":10,"status":"filled","filled_lots":10,"leaves_lots":0,"average_price":"186.10","simulated":true,"queue_model":"conservative_trade_through", ...}
```

Timestamps in responses come from the simulated market clock, not the wall clock. Prices will differ between runs started at different moments because the live simulator keeps moving.

## Walkthrough

The steps in [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) are the ones the UI and API actually implement: live book, paper order, positions, risk, a regime shock, replay, an allowlisted query, and measured feed counters.

## Workstation

These frames are from a local Python-reference session. The ribbon says `PYTHON REF` because no q process was listening.

![Pulse](docs/screenshots/pulse.png)

![Depth](docs/screenshots/depth.png)

![Execution](docs/screenshots/execution.png)

![Query Lab](docs/screenshots/query.png)

## Tests

```bash
.venv/bin/pytest backend/tests -q
cd frontend && npm run build && npm run test:e2e
```

Domain tests check VWAP, OHLC, book gaps, deterministic seeds, market order walks, the trade through rule, weighted average P&L, cash reconciliation and limit rejects. They assert numbers, not just that a field exists.

q tests, when a runtime exists: `cd q && q tests/runtests.q`.

| Check | Result on 1 November 2026 |
| --- | --- |
| `pytest backend/tests -q` | 16 passed |
| `npm ci && npm run build` (frontend) | Pass |
| API start, `/healthz`, order book, paper order | Worked as shown above |
| Playwright e2e | Not run in this check (CI runs it) |
| q scripts and q tests | Not run, no q runtime |
| Linting | No linter is configured |

GitHub Actions runs the backend tests, the frontend build and Playwright on every push. The latest run on `main` passed.

## Benchmarks

`benchmarks/run_benchmark.py` times the simulator, feedhandler and book applier in one process. These are in process rates, not exchange latencies. kdb+ was not timed because it is not installed. Full method in [docs/PERFORMANCE.md](docs/PERFORMANCE.md).

| events | machine | generate evt/s | feed evt/s | book apply evt/s |
| ---: | --- | ---: | ---: | ---: |
| 10,000 | i7-9750H laptop, Windows | 25,188 | 38,837 | 153,336 |
| 100,000 | i7-9750H laptop, Windows | 18,325 | 27,755 | 142,429 |
| 1,000,000 | i7-9750H laptop, Windows | 22,320 | 29,324 | 343,309 |
| 10,000 | 8 vCPU Xeon cloud VM, Linux | 197,944 | 233,432 | 1,706,759 |
| 100,000 | 8 vCPU Xeon cloud VM, Linux | 192,109 | 171,654 | 1,353,057 |
| 1,000,000 | 8 vCPU Xeon cloud VM, Linux | 137,472 | 139,154 | 1,604,447 |

Each block is one run, both on 1 November 2026. The gap between the two machines is large and has not been investigated, so treat these as rough orders of magnitude rather than a comparison.

## Design

There is no left navigation sidebar. Workspaces sit in the top ribbon: Pulse, Depth, Tape, Execution, Portfolio, Risk, Replay, Query Lab, Systems. `Ctrl+K` opens the command palette. Number keys `1` to `9` switch workspaces when focus is not in a field.

The visual system is documented in [docs/UI_DESIGN_SYSTEM.md](docs/UI_DESIGN_SYSTEM.md).

## Project structure

```
backend/marketstream/
  api/app.py          FastAPI REST and WebSocket routes
  simulation/         Deterministic synthetic market and demo sessions
  feed/               Feedhandler
  market/             Order book and analytics (VWAP, OHLC)
  execution/          Paper order engine
  portfolio/          Positions and P&L
  risk/               Pre trade and portfolio risk checks
  replay/             Session replay on a separate book
  queries/            Allowlisted Query Lab catalogue
  store/              Tick store, history and the optional q bridge
backend/tests/        API and domain tests
frontend/             React + Vite workstation, Playwright test
q/                    tickerplant, rdb, hdb, order book, analytics and tests in q
benchmarks/           Python benchmark and a q comparison script
docs/                 Design notes and screenshots
```

## Configuration

Copy `.env.example` to `.env`. Values used by the backend:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MARKETSTREAM_HOST`, `MARKETSTREAM_PORT` | `127.0.0.1`, `8000` | API bind address |
| `MARKETSTREAM_SEED` | `42` | Simulator seed |
| `MARKETSTREAM_SPEED` | `4` | Simulation speed |
| `MARKETSTREAM_WARMUP_PULSES` | `240` | Pulses run before serving |
| `MARKETSTREAM_STARTING_CASH` | `1000000` | Paper account cash |
| `MARKETSTREAM_Q_ENABLED`, `MARKETSTREAM_Q_HOST`, `MARKETSTREAM_Q_PORT` | `true`, `127.0.0.1`, `5001` | Optional q IPC bridge |
| `MARKETSTREAM_API_TOKEN` | empty | Optional API token. Empty means no auth |

Never commit a KX licence key.

## Limitations and known issues

- All market data is synthetic and every order is a paper order.
- The q code has never been executed in this project, so its correctness is unverified.
- With `MARKETSTREAM_API_TOKEN` empty the API has no authentication. Keep it on localhost.
- The `Makefile` only works on Windows paths.
- No linter or type checker is configured for the backend.

## Status

Working prototype in Python reference mode. Tests, build and the API run from a clean clone. The kdb+ path is written but untested.

## Further reading

- [Market-data model](docs/MARKET_DATA_MODEL.md)
- [Order book](docs/ORDER_BOOK.md)
- [Paper execution](docs/EXECUTION_SIMULATION.md)
- [P&L](docs/PNL_ACCOUNTING.md)
- [Risk](docs/RISK_MODELS.md)
- [Replay](docs/REPLAY_ENGINE.md)

## Licence

Project code is MIT. The KDB-X runtime is not included and remains under KX terms.

## Author

Tehilla Obanor. Portfolio: https://cv.omnitest.dev/
