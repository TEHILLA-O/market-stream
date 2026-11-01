# Paper execution

Orders are simulated. The public book is not reduced when a paper order fills. The simulator is not an exchange, and this engine is not claiming a place in its queue.

## States

`accepted` is recorded only after risk, staleness, and crossed-book checks pass. Otherwise the final status is `rejected` and `reject_rule` names the check.

From there:

- A market order walks the opposite side. Anything left is cancelled. Status ends `filled`, or `partially_filled` then `cancelled` when the book runs out. A market order with nothing to hit is `rejected` / `no_liquidity`.
- A limit order takes displayed size at prices no worse than the limit. The remainder rests as `working`, or `partially_filled` if some size already traded.
- Cancel moves `working` or `partially_filled` to `cancelled`.
- A market reset expires resting live orders so they cannot fill on a new path.

`client_order_id` is idempotent per ledger. A retry returns the original order and does not fill again.

## Queue assumption

Market-by-price data has no order identity. Resting limits use a conservative trade-through rule:

- A buy limit fills from later trades only when the print is strictly below the limit.
- A sell limit fills only when the print is strictly above the limit.
- A print at the limit is assumed to belong to size already queued, which we cannot see, so it does not fill us.

That will miss fills a real book might have given, and it can still fill more than a back-of-queue order would. It is a teaching model. The order record stores `queue_model = conservative_trade_through`.

Aggressive size is different: if the limit is marketable, it takes displayed liquidity immediately, because that order is the aggressor.

## Fees

Commission defaults to 1 basis point of notional. Tax defaults to 0. Walking the book is the slippage. There is no second hidden slippage added on top. Each fill stores the fee, the currency, the session, and the assumption text.

## Buying power

Buys must fit in simulated cash, including the fee, using the limit price or the opposite touch. Sells and shorts are not passed through a margin model. They still face position, notional, and concentration limits. Starting cash is 1,000,000 USD of paper buying power.
