import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  Book,
  Candle,
  Instrument,
  Order,
  Portfolio,
  QueryResult,
  QuerySpec,
  ReplayState,
  RiskState,
  SessionInfo,
  SimState,
  Stats,
  SystemState,
  Trade,
  WorkspaceId,
} from "./types";

export type PanelId = "tape" | "depth" | "alerts";

export interface PanelPref {
  weight: number;
  collapsed: boolean;
  pinnedSymbol: string | null;
}

export const DEFAULT_PANELS: Record<PanelId, PanelPref> = {
  tape: { weight: 1.3, collapsed: false, pinnedSymbol: null },
  depth: { weight: 0.9, collapsed: false, pinnedSymbol: null },
  alerts: { weight: 0.8, collapsed: false, pinnedSymbol: null },
};

export const WORKSPACES: { id: WorkspaceId; label: string }[] = [
  { id: "pulse", label: "Pulse" },
  { id: "depth", label: "Depth" },
  { id: "tape", label: "Tape" },
  { id: "execution", label: "Execution" },
  { id: "portfolio", label: "Portfolio" },
  { id: "risk", label: "Risk" },
  { id: "replay", label: "Replay" },
  { id: "query", label: "Query Lab" },
  { id: "systems", label: "Systems" },
];

interface Prefs {
  workspace: WorkspaceId;
  symbol: string;
  density: "compact" | "comfortable" | "expanded";
  dock: boolean;
  palette: boolean;
  reducedMotion: boolean;
  chartMode: "candle" | "line";
  tapePaused: boolean;
  panels: Record<PanelId, PanelPref>;
  expandedPanel: PanelId | null;
  setWorkspace: (workspace: WorkspaceId) => void;
  setSymbol: (symbol: string) => void;
  setDensity: (density: Prefs["density"]) => void;
  setDock: (dock: boolean) => void;
  setPalette: (palette: boolean) => void;
  setReducedMotion: (value: boolean) => void;
  setChartMode: (mode: Prefs["chartMode"]) => void;
  setTapePaused: (value: boolean) => void;
  setPanelWeight: (id: PanelId, weight: number) => void;
  toggleCollapsed: (id: PanelId) => void;
  togglePinned: (id: PanelId, symbol: string) => void;
  setExpandedPanel: (id: PanelId | null) => void;
  resetLayout: () => void;
}

export const usePrefs = create<Prefs>()(
  persist(
    (set) => ({
      workspace: "pulse",
      symbol: "ATHR",
      density: "comfortable",
      dock: true,
      palette: false,
      reducedMotion: false,
      chartMode: "candle",
      tapePaused: false,
      panels: DEFAULT_PANELS,
      expandedPanel: null,
      setWorkspace: (workspace) => set({ workspace }),
      setSymbol: (symbol) => set({ symbol }),
      setDensity: (density) => set({ density }),
      setDock: (dock) => set({ dock }),
      setPalette: (palette) => set({ palette }),
      setReducedMotion: (reducedMotion) => set({ reducedMotion }),
      setChartMode: (chartMode) => set({ chartMode }),
      setTapePaused: (tapePaused) => set({ tapePaused }),
      setPanelWeight: (id, weight) => set((state) => ({ panels: { ...state.panels, [id]: { ...state.panels[id], weight } } })),
      toggleCollapsed: (id) => set((state) => ({ panels: { ...state.panels, [id]: { ...state.panels[id], collapsed: !state.panels[id].collapsed } }, expandedPanel: state.expandedPanel === id ? null : state.expandedPanel })),
      togglePinned: (id, symbol) => set((state) => {
        const current = state.panels[id].pinnedSymbol;
        return { panels: { ...state.panels, [id]: { ...state.panels[id], pinnedSymbol: current === symbol ? null : symbol } } };
      }),
      setExpandedPanel: (expandedPanel) => set({ expandedPanel }),
      resetLayout: () => set({ panels: DEFAULT_PANELS, expandedPanel: null }),
    }),
    { name: "marketstream-prefs", partialize: (state) => ({ workspace: state.workspace, symbol: state.symbol, density: state.density, dock: state.dock, reducedMotion: state.reducedMotion, chartMode: state.chartMode, panels: state.panels, expandedPanel: state.expandedPanel }) },
  ),
);

interface Market {
  connection: "connecting" | "live" | "reconnecting" | "offline";
  instruments: Instrument[];
  stats: Record<string, Stats>;
  books: Record<string, Book>;
  candles: Record<string, Candle[]>;
  trades: Trade[];
  sim: SimState | null;
  system: SystemState | null;
  portfolio: Portfolio | null;
  risk: RiskState | null;
  orders: Order[];
  alerts: RiskState["alerts"];
  queries: QuerySpec[];
  queryResult: QueryResult | null;
  sessions: SessionInfo[];
  replay: ReplayState | null;
  depth: { event_timestamp: string; bids: Book["bids"]; asks: Book["asks"] }[];
  error: string | null;
  setConnection: (connection: Market["connection"]) => void;
  setInstruments: (instruments: Instrument[]) => void;
  apply: (message: Record<string, unknown>) => void;
  setCandles: (symbol: string, candles: Candle[]) => void;
  setTrades: (trades: Trade[]) => void;
  setOrders: (orders: Order[]) => void;
  setQueries: (queries: QuerySpec[]) => void;
  setQueryResult: (queryResult: QueryResult | null) => void;
  setSessions: (sessions: SessionInfo[]) => void;
  setReplay: (replay: ReplayState | null) => void;
  setDepth: (depth: Market["depth"]) => void;
  setError: (error: string | null) => void;
  setPortfolio: (portfolio: Portfolio | null) => void;
}

export const useMarket = create<Market>((set, get) => ({
  connection: "connecting",
  instruments: [],
  stats: {},
  books: {},
  candles: {},
  trades: [],
  sim: null,
  system: null,
  portfolio: null,
  risk: null,
  orders: [],
  alerts: [],
  queries: [],
  queryResult: null,
  sessions: [],
  replay: null,
  depth: [],
  error: null,
  setConnection: (connection) => set({ connection }),
  setInstruments: (instruments) => set({ instruments }),
  setCandles: (symbol, candles) => set({ candles: { ...get().candles, [symbol]: candles } }),
  setTrades: (trades) => set({ trades }),
  setOrders: (orders) => set({ orders }),
  setQueries: (queries) => set({ queries }),
  setQueryResult: (queryResult) => set({ queryResult }),
  setSessions: (sessions) => set({ sessions }),
  setReplay: (replay) => set({ replay }),
  setDepth: (depth) => set({ depth }),
  setError: (error) => set({ error }),
  setPortfolio: (portfolio) => set({ portfolio }),
  apply: (message) => {
    const category = message.category;
    if (category === "quote" && typeof message.symbol === "string") {
      set({ stats: { ...get().stats, [message.symbol]: message as unknown as Stats } });
    } else if (category === "book" && typeof message.symbol === "string") {
      set({ books: { ...get().books, [message.symbol]: message as unknown as Book } });
    } else if (category === "trade") {
      if (get().trades.some((row) => row.event_id === message.event_id)) return;
      const next = [message as unknown as Trade, ...get().trades].slice(0, 400);
      set({ trades: next });
    } else if (category === "ohlc" && typeof message.symbol === "string") {
      const bar = message.bar as Candle;
      const existing = get().candles[message.symbol] ?? [];
      if (!existing.length) return;
      const last = existing[existing.length - 1];
      const candles = last.time === bar.time ? [...existing.slice(0, -1), bar] : [...existing, bar];
      set({ candles: { ...get().candles, [message.symbol]: candles.slice(-400) } });
    } else if (category === "simulation") {
      set({ sim: message as unknown as SimState });
    } else if (category === "system") {
      set({ system: message as unknown as SystemState });
    } else if (category === "position") {
      set({ portfolio: message as unknown as Portfolio });
    } else if (category === "risk") {
      const risk = message as unknown as RiskState;
      set({ risk, alerts: risk.alerts ?? [] });
    } else if (category === "alert") {
      set({ alerts: (message.alerts as RiskState["alerts"]) ?? [] });
    }
  },
}));
