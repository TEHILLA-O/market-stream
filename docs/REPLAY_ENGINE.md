# Replay

Replay is a second order-book engine fed by a recorded `events.jsonl`. Playback time and event time are different clocks. The live fill ledger is not appended to.

## Controls

Load, play, pause, step forward, step back, seek by index, jump to an event time, set playback speed, and restart. The UI polls `/api/v1/replay/state` while `playing` is true. The API loop advances the cursor by the replay speed each frame. Speed is `POST /api/v1/replay/speed`. A clock time is `POST /api/v1/replay/seek` with `timestamp`.

Seek restores the nearest checkpoint at or before the index, then applies events forward. Checkpoints are every 250 events and store each symbol's levels, sequence, and stale flag. Seeking does not recompute from byte zero when a checkpoint exists, and it does not invent state past the cursor.

## What stays in sync

The state payload includes the reconstructed book per symbol, trades in a short window ending at the cursor, and trade OHLC for the focused symbol up to the cursor. Depth samples are taken every 40 events while the checkpoints are built, and the payload only includes samples at or before the cursor. Playhead risk replays the session fill file through the weighted-average account and marks it with the reconstructed mid. Sessions without a fill file report zero fills. Neither path writes the live ledger. Markers call out large prints (at least four times the median size), sequence gaps, and halt or closed status. Choosing a marker seeks to that index.

Demo sessions:

| Id | What it is |
| --- | --- |
| `demo-calm` | Normal regime |
| `demo-shock` | Normal, then `price_shock` |
| `demo-liquidity` | Depth and spread shift into `liquidity_withdrawal` |
| `demo-disruption` | A forced sequence gap, then a recovering snapshot |
| `demo-strategy` | A small mean-reversion paper rule on ATHR, with a sidecar of orders and fills |
| `demo-risk` | 1,200-lot buy, a second buy rejected for concentration, then a shock |

Sidecars (`orders.json`, `fills.json`, `pnl.json`) are descriptions of that recording. They are not merged into the live account.

The same file and the same cursor produce the same book, because the reconstructor is deterministic and the log is not rewritten.
