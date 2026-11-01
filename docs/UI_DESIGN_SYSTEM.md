# Interface

The workstation is a single surface. Navigation is the ribbon across the top, not a sidebar of pages. The active workspace is a short underline, not a filled pill. The bottom dock is a strip of pinned symbols and can be hidden. It is not a second menu.

## Colour

Graphite foundation (`#0b0d11`) with hairline borders instead of stacked cards. Cyan is live state and the active workspace. Violet is query text. Emerald and coral are reserved for up/down and buy/sell. Amber is a warning, including the paper-trading banner and the Python-reference badge. Muted grey is secondary. Health is never green while the book is stale or the socket is down, and the q tickerplant is `unavailable` rather than a healthy lamp when no q process is connected.

## Type

IBM Plex Sans for labels, IBM Plex Mono for prices, sizes, clocks, and P&L. Those faces are bundled with `@fontsource`, so the layout does not depend on a network font. Tabular figures are on for the root.

Density is `compact`, `comfortable`, or `expanded`, stored locally, and it changes row height and type size. Hit targets on the ribbon and the ticket stay larger than the densest tape row.

## Motion

Price changes can flash once. Workspace changes fade in about 160 ms. `prefers-reduced-motion` and the local reduce toggle remove the flash. Values are not animated toward a number; the text is the current value.

## Workspaces

Pulse is the chart, the selected instrument, a virtualised tape, a short ladder, and alerts. Depth is the ladder, a canvas of stored snapshots, and cumulative curves. Tape adds filters and CSV. Execution is a ticket plus a blotter, with the paper banner above the button. Portfolio is a constellation sized from market value and a table of the same numbers. Risk is utilisation rings plus the shock table; the rings are not the only place the figures exist. Replay is a transport bar. Query Lab prints q and the engine name. Systems lists measured counters.

`Ctrl+K` or `⌘K` opens the palette. Keys `1` through `9` change workspace when the focus is not in a field.

Charts use Lightweight Charts. Floats in the series are for drawing. The text in the rail and the blotter is the decimal string from the API.
