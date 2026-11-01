# P&L accounting

Cost basis is weighted average. Quantity is signed lots: positive long, negative short. Average cost is the average entry price of the open quantity only, in the instrument's quote currency.

## Identities

For any open signed quantity `q`, lot size `L`, mark `m`, and average cost `a`:

```
unrealised = q × L × (m − a)
```

The sign of `q` makes the short case work. A short of 10 lots at 100, marked at 90, with `L = 1`, is `-10 × (90 − 100) = 100`.

Realised P&L is booked only when a fill reduces or flips the open quantity, on the closed lots:

- Closing a long: `closed_lots × L × (fill − average)`
- Closing a short: `closed_lots × L × (average − fill)`

A flip closes the old quantity and opens the excess at the fill price. Fees are not folded into realised P&L.

```
gross = realised + unrealised
net   = gross − fees
```

## Cash

```
buy:  cash -= notional + fee
sell: cash += notional − fee
```

When the position is flat, the change in cash equals net P&L. The tests cover a long that is scaled in and partially sold, a short that is partially covered, a rebuild of the same fills, and a flat round trip where cash ends at `1,000,098` after a 100 point gain on 10 shares minus 2 of fees.

## Marks

The mark is the reconstructed mid when the book is live. A stale or one-sided book keeps the previous mid and is flagged stale. Unrealised P&L on a stale mark is labelled, not treated as fresh.

## Currency

The starter instruments are all USD-quoted. Totals use FX rate 1 and say so. A non-USD book would have to carry the rate used for the conversion; this version does not invent one.

## Source of truth

`PositionBook.rebuild` replays the fill ledger from the starting cash. Incremental `apply_fill` is required to match that replay. The browser never owns the position.
