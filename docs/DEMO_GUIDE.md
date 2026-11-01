# Demonstration

Start the API and the Vite dev server as in the README. The live session is already warm, so Pulse is not an empty chart.

1. Confirm the ribbon says `PYTHON REF` unless you have connected q, and that the health lamp matches the socket (`live`, `paused`, `stale`, or `offline`).
2. The virtual clock in the ribbon advances while the simulation is running. Pause it from the palette (`Ctrl+K`, “Pause simulation”). The lamp goes to paused. Resume the same way.
3. Search `Helix` or type in the dock to select `HLX`. The rail, chart, and book follow that symbol. Candles are trade OHLC at 5 seconds. Buckets with no trades are absent. The caption on the chart says so.
4. Open Depth. The ladder is the reconstructed book. If you inject a sequence gap from the palette, the health line becomes stale and new paper orders are rejected until the next snapshot. The heatmap only grows when snapshots have been stored.
5. Open Tape. Pause freezes the rows you are reading. Export CSV writes the buffer, not a hidden server extract.
6. Open Execution. The banner says the order cannot reach a broker. Choose Buy, Market, 10 lots. The preview shows an estimated price, fee, and any risk rule. Simulate buy. The blotter status comes from the API. A rejection shows `reject_rule`. Cancelling a resting limit uses the cancel route.
7. Open Portfolio. Net, realised, unrealised, fees, and cash are the position engine’s numbers. A row’s fill count is the execution ids that built it. Flat accounts say they are flat.
8. Open Risk. Utilisation, drawdown, concentration, and the shock table are from the current paper book. VaR stays empty until 20 return samples exist, and the limitation text stays visible when a number does appear.
9. From the palette, inject a price shock. Spreads and the mark move because the regime changes depth, spread, and the mid, not because a label changed. Portfolio marks follow the new mid.
10. Open Replay. The first visit can spend a few seconds writing demo logs if `data/sessions` is empty. Load `demo-shock` or `demo-disruption`. Play, step, and drag the range. The book at the cursor is rebuilt from the log. The live blotter does not gain fills from this.
11. Open Query Lab. Run VWAP or OHLC. You should see the q expression, `python-reference` (or a clearly worded IPC note), a row count, and `executed_unrestricted_q: false`.
12. Open Systems. Generated, ingested, quarantined, gaps, and the latency percentiles are counters from this process. The tickerplant row is `unavailable` until q answers. A disconnected API does not stay on `live`.

Demo files, once written:

- `demo-calm`, `demo-shock`, `demo-liquidity`, `demo-disruption`
- `demo-strategy` includes a sidecar of mean-reversion paper fills
- `demo-risk` includes the concentration reject

Seeds are fixed in `backend/marketstream/simulation/demos.py`.
