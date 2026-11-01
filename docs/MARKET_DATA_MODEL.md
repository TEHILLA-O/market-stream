# Market-data model

Schema version is `1`.

Every event carries `event_id`, `session_id`, `event_type`, `source`, `venue`, `symbol`, `sequence_number`, `event_timestamp`, `receive_timestamp`, and `process_timestamp`.

`event_timestamp` is the virtual market clock. `receive_timestamp` and `process_timestamp` are wall-clock times inside the feedhandler. The difference is an in-process measurement. It is not a wire latency to an exchange.

## Types

Prices are integer ticks. A tick is the instrument's `tick_size`. `ATHR` at 186.40 is 18640 ticks of 0.01. Equality is integer equality.

Quantities are integer lots. A lot is `lot_size` units. Helix is 1000 units per lot. Lumen is 0.01 units per lot. Notional is `lots × lot_size × price`.

Off-tick limit prices are rejected. Negative prices and negative quantities are quarantined and do not enter the book or the tape.

## Events

| Type | Meaning |
| --- | --- |
| `trade` | A print. `aggressor_side` is the simulated aggressor. Condition `synthetic` is always set. |
| `quote` | Best bid and ask after the book updates in that pulse. |
| `book_snapshot` | Full absolute depth. Replaces both sides. |
| `book_delta` | One price level. `semantics` is `absolute`. Zero quantity or `delete` removes the level. |
| `market_status` | `open`, `halt`, `closed`, or `preopen`, plus the regime name. |
| `heartbeat` | Clock pulse when a symbol is closed or halted and is not publishing a book. |
| `feed_quality` | Gap, duplicate, quarantine, stale, recovered, disconnect, or quote/book mismatch. |

Sequence numbers are per symbol and shared by every event type for that symbol. A quote occupies a sequence slot. The book treats a missing slot as a gap even if the missing message was not itself a delta, because the feed is one sequence.

## Simulator

One `random.Random` per session, symbols in a fixed list, virtual time advanced only inside `pulse()`. The same seed and the same number of pulses produce the same JSON events.

Each open pulse:

1. Steps the mid in tick space with `round(mid * exp(drift + vol * gaussian + shock))`.
2. Builds a new absolute depth around that mid. Spread multiplier and depth multiplier come from the regime, so a low-liquidity regime is wider and thinner, not just a label.
3. Emits a snapshot every 20 pulses, otherwise absolute deltas for levels that changed.
4. Emits the quote, then a trade at the touch with probability `trade_p`.

The trade does not mutate the book by itself. Only a later delta or snapshot does. Closing and halt regimes stop prints and emit heartbeats.

A gap injection skips sequence numbers on one pulse and suppresses snapshots on that pulse. The following pulse forces a snapshot, which is the recovery.

Regimes: `normal`, `low_liquidity`, `high_volatility`, `uptrend`, `downtrend`, `sideways`, `liquidity_withdrawal`, `price_shock`, `opening`, `closing`.

## Instruments

All five are priced in USD, so the starter book does not convert currencies. `currency` on the instrument is the P&L currency. Descriptions say synthetic. Venues are Meridian Synthetic Exchange (`MSX`), Meridian Synthetic FX (`MSFX`), and Meridian Synthetic Crypto (`MSCX`).

Sessions are `synthetic-continuous`. The demo does not follow a real exchange calendar. The closing regime is what stops a symbol.
