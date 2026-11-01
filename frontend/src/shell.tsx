import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "./lib/api";
import { WORKSPACES, useMarket, usePrefs } from "./state";
import type { Instrument, WorkspaceId } from "./types";

export function Ribbon() {
  const workspace = usePrefs((state) => state.workspace);
  const setWorkspace = usePrefs((state) => state.setWorkspace);
  const setPalette = usePrefs((state) => state.setPalette);
  const symbol = usePrefs((state) => state.symbol);
  const setSymbol = usePrefs((state) => state.setSymbol);
  const sim = useMarket((state) => state.sim);
  const connection = useMarket((state) => state.connection);
  const instruments = useMarket((state) => state.instruments);
  const stats = useMarket((state) => state.stats[symbol]);
  const [query, setQuery] = useState("");
  const matches = instruments.filter((item) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return false;
    return item.symbol.toLowerCase().includes(needle) || item.description.toLowerCase().includes(needle);
  });
  const health = !sim ? connection : sim.paused ? "paused" : stats?.book_stale || sim.stalled ? "stale" : connection === "live" ? "live" : connection;
  const engine = sim?.engine.engine === "kdb" ? "KDB-X" : "PYTHON REF";
  return (
    <header className="ribbon">
      <div className="brand">
        <Mark />
        <div>
          <div className="brand-name">Market<span>Stream</span></div>
          <small>Synthetic workstation</small>
        </div>
      </div>
      <nav className="switcher" aria-label="Workspaces">
        {WORKSPACES.map((item) => (
          <button key={item.id} data-active={workspace === item.id} onClick={() => setWorkspace(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>
      <div className="ribbon-tools">
        <div style={{ position: "relative" }}>
          <input className="search" aria-label="Search instruments" placeholder="Symbol" value={query} onChange={(event) => setQuery(event.target.value)} />
          {matches.length > 0 && (
            <div className="search-pop" role="listbox">
              {matches.map((item) => (
                <button key={item.symbol} onClick={() => { setSymbol(item.symbol); setQuery(""); }}>
                  <b>{item.symbol}</b>
                  <small>{item.asset_class}</small>
                </button>
              ))}
            </div>
          )}
        </div>
        <span className="engine" title={sim?.engine.detail}>{engine}</span>
        <span className="health" data-state={health}><i />{health}</span>
        <span className="clock">{sim ? sim.virtual_time.slice(11, 19) : "--:--:--"}</span>
        <button className="icon-btn" onClick={() => setPalette(true)}>Ctrl K</button>
      </div>
    </header>
  );
}

export function Dock() {
  const open = usePrefs((state) => state.dock);
  const symbol = usePrefs((state) => state.symbol);
  const setSymbol = usePrefs((state) => state.setSymbol);
  const stats = useMarket((state) => state.stats);
  const instruments = useMarket((state) => state.instruments);
  if (!open) return null;
  const rows = instruments.length ? instruments : [{ symbol: "ATHR", description: "", asset_class: "", currency: "USD", venue: "", tick_size: "0.01", reference_price: "" } satisfies Instrument];
  return (
    <footer className="dock" aria-label="Pinned instruments">
      {rows.map((item) => {
        const quote = stats[item.symbol];
        return (
          <button key={item.symbol} className="pin" data-active={symbol === item.symbol} onClick={() => setSymbol(item.symbol)}>
            {item.symbol}
            <span className={quote?.change_bps && Number(quote.change_bps) < 0 ? "neg" : "pos"}>{quote?.last ?? "—"}</span>
          </button>
        );
      })}
    </footer>
  );
}

export function Palette() {
  const open = usePrefs((state) => state.palette);
  const setPalette = usePrefs((state) => state.setPalette);
  const setWorkspace = usePrefs((state) => state.setWorkspace);
  const setSymbol = usePrefs((state) => state.setSymbol);
  const setDensity = usePrefs((state) => state.setDensity);
  const setDock = usePrefs((state) => state.setDock);
  const dock = usePrefs((state) => state.dock);
  const resetLayout = usePrefs((state) => state.resetLayout);
  const instruments = useMarket((state) => state.instruments);
  const [text, setText] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const commands = useMemo(() => buildCommands({ setWorkspace, setSymbol, setDensity, setDock, dock, instruments, resetLayout, close: () => setPalette(false) }), [dock, instruments, resetLayout, setDensity, setDock, setPalette, setSymbol, setWorkspace]);
  const filtered = commands.filter((item) => item.label.toLowerCase().includes(text.toLowerCase()));
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div className="palette-backdrop" onClick={() => setPalette(false)}>
      <motion.div className="palette" role="dialog" aria-label="Command palette" onClick={(event) => event.stopPropagation()} initial={{ y: 8, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <input
          ref={input}
          placeholder="Instruments, workspaces, simulation"
          value={text}
          onChange={(event) => { setText(event.target.value); setIndex(0); }}
          onKeyDown={(event) => {
            if (event.key === "Escape") setPalette(false);
            if (event.key === "ArrowDown") setIndex((value) => Math.min(filtered.length - 1, value + 1));
            if (event.key === "ArrowUp") setIndex((value) => Math.max(0, value - 1));
            if (event.key === "Enter" && filtered[index]) filtered[index].run();
          }}
        />
        <ul>
          {filtered.map((item, itemIndex) => (
            <li key={item.label}>
              <button data-active={itemIndex === index} onClick={item.run}>
                {item.label}
                <small>{item.hint}</small>
              </button>
            </li>
          ))}
        </ul>
      </motion.div>
    </div>
  );
}

function buildCommands(args: {
  setWorkspace: (workspace: WorkspaceId) => void;
  setSymbol: (symbol: string) => void;
  setDensity: (density: "compact" | "comfortable" | "expanded") => void;
  setDock: (dock: boolean) => void;
  dock: boolean;
  instruments: Instrument[];
  resetLayout: () => void;
  close: () => void;
}) {
  const items = [
    ...WORKSPACES.map((item) => ({ label: `Open ${item.label}`, hint: "workspace", run: () => { args.setWorkspace(item.id); args.close(); } })),
    ...args.instruments.map((item) => ({ label: `Select ${item.symbol}`, hint: item.asset_class, run: () => { args.setSymbol(item.symbol); args.close(); } })),
    { label: "Pause simulation", hint: "market", run: () => { void api("/api/v1/simulation/pause", { method: "POST" }); args.close(); } },
    { label: "Resume simulation", hint: "market", run: () => { void api("/api/v1/simulation/resume", { method: "POST" }); args.close(); } },
    { label: "Inject price shock", hint: "regime", run: () => { void api("/api/v1/simulation/regime", { method: "POST", body: JSON.stringify({ regime: "price_shock" }) }); args.close(); } },
    { label: "Withdraw liquidity", hint: "regime", run: () => { void api("/api/v1/simulation/regime", { method: "POST", body: JSON.stringify({ regime: "liquidity_withdrawal" }) }); args.close(); } },
    { label: "Return to normal regime", hint: "regime", run: () => { void api("/api/v1/simulation/regime", { method: "POST", body: JSON.stringify({ regime: "normal" }) }); args.close(); } },
    { label: "Inject sequence gap", hint: "feed", run: () => { void api("/api/v1/simulation/gap", { method: "POST" }); args.close(); } },
    { label: "Density compact", hint: "view", run: () => { args.setDensity("compact"); args.close(); } },
    { label: "Density comfortable", hint: "view", run: () => { args.setDensity("comfortable"); args.close(); } },
    { label: "Density expanded", hint: "view", run: () => { args.setDensity("expanded"); args.close(); } },
    { label: args.dock ? "Hide dock" : "Show dock", hint: "view", run: () => { args.setDock(!args.dock); args.close(); } },
    { label: "Reset panel layout", hint: "view", run: () => { args.resetLayout(); args.close(); } },
    { label: "Open execution ticket", hint: "trade", run: () => { args.setWorkspace("execution"); args.close(); } },
  ];
  return items;
}

export function Stage({ children }: { children: ReactNode }) {
  const reduced = usePrefs((state) => state.reducedMotion);
  const workspace = usePrefs((state) => state.workspace);
  return (
    <main className="stage">
      <AnimatePresence mode="wait">
        <motion.div key={workspace} className="stage-pane" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : 0.16 }}>
          {children}
        </motion.div>
      </AnimatePresence>
    </main>
  );
}

function Mark() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <path d="M4 20 L10 8" stroke="#3fdec6" strokeWidth="1.6" />
      <path d="M10 20 L16 6" stroke="#a394ff" strokeWidth="1.6" />
      <path d="M16 20 L24 10" stroke="#e7edf6" strokeWidth="1.6" />
    </svg>
  );
}
