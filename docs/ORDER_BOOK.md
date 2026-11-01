# Order book

The book is market-by-price. It does not invent order ids or a FIFO queue.

## Rules

1. The book is uninitialised until a valid snapshot. Uninitialised is reported as stale.
2. Deltas apply only when the sequence is exactly `last + 1` and the book is not stale.
3. Quantities are absolute. A delta replaces the size at that price. It does not add to it.
4. Quantity zero or action `delete` removes the level.
5. Bids sort high to low. Asks sort low to high.
6. A sequence jump sets `stale`, increments the gap count, and quarantines that delta. `last_seq` stays put, so later deltas stay quarantined too.
7. A later snapshot replaces both sides, clears stale, and sets `last_seq` to the snapshot sequence.
8. Duplicate sequences are counted and ignored.
9. A negative quantity or a non-positive price quarantines the update and marks the book stale.
10. Trades and quotes do not change levels. A quote whose touch disagrees with the book sets a mismatch detail. It does not overwrite the book.

A crossed book (`bid > ask`) and a locked book (`bid == ask`) are explicit health states. The simulator keeps at least one tick of half-spread, so a normal pulse is not locked. Execution refuses a crossed book.

## Derived fields

- Mid is the average of the best bid and ask, in ticks, and may be a half tick.
- Spread in basis points is `spread / mid * 10000`.
- Imbalance is `(bid_depth - ask_depth) / (bid_depth + ask_depth)` across all displayed levels. Top-five imbalance uses the first five levels on each side.
- Microprice is `(ask * bid_size + bid * ask_size) / (bid_size + ask_size)` at the touch. It is omitted when either side is missing.
- Concentration is the touch size divided by that side's displayed depth.

Empty and one-sided books leave mid, spread, and microprice empty. The UI prints the health state next to the price. Stale is not shown as live.

## Depth history

Each applied snapshot is kept, up to 180 per symbol. The heatmap draws those snapshots. It does not interpolate a history from the latest image. Cumulative curves use the current reconstructed levels only.

## Tests

`test_book_reconstructs_snapshot_and_absolute_deltas` builds a known book and checks spread, cumulative size, and microprice. `test_gap_stales_the_book_until_a_snapshot` checks that a jumped delta does not change the size and that the next snapshot does. The q analogue is in `q/tests/runtests.q` and has not been executed here.
