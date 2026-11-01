# Risk

Figures are paper exposures in USD. They are not a desk limit framework.

## Measures

- Gross exposure: sum of absolute market values
- Net exposure: sum of signed market values
- Long and short buckets from the sign of market value
- Exposure by instrument and by asset class
- Concentration: absolute instrument notional divided by starting capital (default 1,000,000), not by current gross. A single position would otherwise always be 100% of gross.
- Drawdown: peak-to-trough of the sampled equity curve (cash plus market value)
- Rolling volatility on each symbol: sample standard deviation of log mid returns, not annualised
- Scenario shocks: parallel ±1%, ±5%, ±10% of current notionals, linear in price

## Limits and the rule that fires

| Rule | Default |
| --- | --- |
| `max_order_quantity` | 2,000 lots |
| `max_order_notional` | 250,000 USD |
| `max_position_size` | 5,000 lots absolute, after the order |
| `max_gross_exposure` | 2,000,000 |
| `max_net_exposure` | 1,500,000 absolute |
| `max_symbol_concentration` | 40% of capital |
| `daily_loss_threshold` | net P&L below −25,000 blocks new orders |
| `buying_power` | buy notional plus fee must fit in cash |
| `stale_book` | no new orders while recovery is pending |
| `crossed_book` | no new orders |
| `stale_mark` | no reference price for the notional check |
| `no_liquidity` | market order, empty opposite side |

The order's `reject_rule` is that id, and `reject_reason` includes the numbers. Demo session `demo-risk` buys 1,200 ATHR and then rejects a second 1,200 because projected concentration is about 44.6% against a 40% capital limit.

Alerts for drawdown, concentration, stale books, and wide spreads (more than 2.5× that symbol's reference spread) are raised from those same measurements. A repeated detail is not appended again.

## Historical simulation VaR

Once 20 overlapping mid-return samples exist, VaR is the empirical lower-tail quantile of `sum(notional × historical simple return)` at the requested confidence, default 95%. The window is whatever the current process has stored, capped near 300 pulses. Frequency is one simulator pulse.

This is not a regulatory VaR. The path is synthetic, the map from price to P&L is linear, there is no decay or liquidity horizon, and a short window is dominated by the current regime. The API returns those limitations next to the number. An empty result stays null rather than a decorative zero presented as a calculation.
