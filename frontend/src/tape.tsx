import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { usePrefs } from "./state";
import type { Trade } from "./types";

export function TradeTape({ rows }: { rows: Trade[] }) {
  const paused = usePrefs((state) => state.tapePaused);
  const setPaused = usePrefs((state) => state.setTapePaused);
  const parent = useRef<HTMLDivElement>(null);
  const snapshot = useRef<Trade[]>(rows);
  if (!paused) snapshot.current = rows;
  const shown = paused ? snapshot.current : rows;
  const virtualizer = useVirtualizer({
    count: shown.length,
    getScrollElement: () => parent.current,
    estimateSize: () => 28,
  });
  return (
    <section className="pane">
      <header className="pane-h">
        <h2>Tape</h2>
        <button onClick={() => setPaused(!paused)}>{paused ? "Resume" : "Pause"}</button>
      </header>
      <div className="pane-b" ref={parent}>
        <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {virtualizer.getVirtualItems().map((item) => {
            const trade = shown[item.index];
            const large = Number(trade.notional) >= 25000;
            return (
              <div
                key={trade.event_id}
                className="tape-row"
                data-large={large}
                style={{ position: "absolute", top: 0, transform: `translateY(${item.start}px)`, width: "100%" }}
              >
                <span>{trade.event_timestamp.slice(11, 19)}</span>
                <span>{trade.symbol}</span>
                <span className={trade.aggressor_side === "buy" ? "pos" : trade.aggressor_side === "sell" ? "neg" : ""}>{trade.price}</span>
                <span>{trade.quantity}</span>
                <span>{trade.notional}</span>
                <span>{trade.aggressor_side === "buy" ? "B" : trade.aggressor_side === "sell" ? "S" : "·"}</span>
              </div>
            );
          })}
        </div>
        {shown.length === 0 && <p className="empty-note">No trades in view.</p>}
      </div>
    </section>
  );
}
