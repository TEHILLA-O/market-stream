# KDB-X engine

## What the official distribution allows

KDB-X is the current q runtime from KX. Community Edition is free for personal and commercial use inside published limits: 16 GB RAM for q, one physical or virtual instance, 4 secondary threads, a small connection cap, and 24 cores across instances. Native Windows is not supported. Windows uses WSL2. macOS and Linux are supported directly.

Installation is a licence-bearing command from the KX Developer Center, not a file this repository can vendor. The Community key arrives as base64 `kc.lic`. Keep it in the environment or in `~/.kx`, never in git. `.env.example` has a commented placeholder only.

PyKX (the KDB-X Python library) can talk IPC without a local licence. Embedded q, local `pykx.q` evaluation, and loading a database inside the Python process need a licence. This project therefore treats q as a separate process.

## Layout

```
q/schemas/market.q       table definitions
q/tickerplant/tick.q     append-only log and publish
q/rdb/rdb.q              in-memory session tables and replay of the log
q/hdb/hdb.q              one directory per date
q/analytics/analytics.q  OHLC, VWAP, spread, as-of join, rolling dev
q/orderbook/book.q       absolute book, gap → stale
q/queries/examples.q     names the API is allowed to call
q/tests/runtests.q       assertions, exit code is the failure count
```

Load paths assume the working directory is `q/`.

Prices in q are longs: integer ticks. Quantities are longs: lots. Time is a timestamp. Instrument identifiers are symbols. The grouped attribute `` `g# `` on `sym` is applied after a replay or bulk load, not on every tickerplant insert.

The tickerplant `upd` logs, inserts, and publishes. It does not compute VWAP.

## Worked example

Three trades, one symbol, one minute:

| price (ticks) | qty |
| ---: | ---: |
| 1000 | 100 |
| 1200 | 50 |
| 1100 | 50 |

VWAP = (1000×100 + 1200×50 + 1100×50) / 200 = 1075 ticks.

```q
vwap:{[t;s] exec qty wavg price from t where sym=s}
ohlc:{[t;s;bucket]
  select open:first price, high:max price, low:min price, close:last price,
         volume:sum qty, vwap:qty wavg price
    by time:bucket xbar time from select time, price, qty from t where sym=s
 }
```

`q/tests/runtests.q` asserts that example and a small book: snapshot, absolute upsert, delete, then a gap that quarantines the next delta. Those tests were not run in this workspace.

## Python reference mode

`QBridge.probe` opens a short TCP connection to `MARKETSTREAM_Q_HOST:MARKETSTREAM_Q_PORT`. If nothing listens, mode stays `python` and the detail string says this is not kdb+. If the port accepts TCP, the process tries `pykx.SyncQConnection` with `PYKX_UNLICENSED=true`. A failed import or a failed `tables[]` call also stays in Python mode.

Query Lab never evaluates client-supplied q text. It dispatches a query id. In Python mode the id runs the matching Python function and returns the q source beside the rows. Even if IPC is connected, this build still returns the Python rows and says so, because an unrestricted remote eval is not exposed.

## Suggested WSL2 setup

1. Install Ubuntu on WSL2.
2. Sign in at the KX Developer Center and copy the Community install command.
3. Run that command inside Ubuntu. Confirm with `q` and the Community banner.
4. From `q/`: `q tickerplant/tick.q -p 5001`
5. In another shell, load `rdb/rdb.q` and subscribe, or call the `.ms.q.*` functions once the tables exist.
6. Point MarketStream at `127.0.0.1:5001` with `MARKETSTREAM_Q_ENABLED=true` and install `pykx` into the same virtualenv (`pip install -e "./backend[q]"`).

Do not publish a Docker image that contains the q binary. `docker-compose.yml` runs the API with q disabled.
