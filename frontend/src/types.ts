export type WorkspaceId =
  | "pulse"
  | "depth"
  | "tape"
  | "execution"
  | "portfolio"
  | "risk"
  | "replay"
  | "query"
  | "systems";

export interface Instrument {
  symbol: string;
  description: string;
  asset_class: string;
  currency: string;
  venue: string;
  tick_size: string;
  reference_price: string;
}

export interface Stats {
  symbol: string;
  description?: string;
  asset_class?: string;
  venue?: string;
  last: string | null;
  change: string | null;
  change_bps: string | null;
  bid: string | null;
  ask: string | null;
  spread: string | null;
  spread_bps: string | null;
  mid: string | null;
  microprice: string | null;
  vwap: string | null;
  volume_lots: number;
  trade_count: number;
  high: string | null;
  low: string | null;
  volatility: string | null;
  imbalance: string | null;
  bid_depth_lots: number;
  ask_depth_lots: number;
  book_state: string;
  book_stale: boolean;
  book_detail?: string;
  mark?: string | null;
  mark_stale?: boolean;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  close_text?: string;
}

export interface Trade {
  event_id: string;
  symbol: string;
  venue: string;
  event_timestamp: string;
  price: string;
  quantity: string;
  quantity_lots: number;
  notional: string;
  aggressor_side: string;
}

export interface BookLevel {
  price: string;
  price_ticks: number;
  quantity_lots: number;
  cumulative_lots: number;
}

export interface Book {
  symbol: string;
  bids: BookLevel[];
  asks: BookLevel[];
  best_bid: string | null;
  best_ask: string | null;
  spread: string | null;
  spread_bps: string | null;
  mid: string | null;
  imbalance: string | null;
  health: { state: string; stale: boolean; detail: string; gap_count: number };
}

export interface SimState {
  session_id: string;
  running: boolean;
  paused: boolean;
  regime: string;
  regimes: string[];
  speed: number;
  virtual_time: string;
  pulse: number;
  seed: number;
  stalled: boolean;
  engine: { mode: string; detail: string; engine: string };
}

export interface SystemState {
  components: { name: string; state: string; detail: string }[];
  generated: number;
  ingested: number;
  quarantined: number;
  gaps: number;
  duplicates: number;
  latency: { p50: number | null; p95: number | null; p99: number | null; unit: string; sample: string };
  websocket_clients: number;
  freshness_seconds: number | null;
  engine: { mode: string; detail: string };
  errors: { time: string; detail: string }[];
}

export interface Position {
  symbol: string;
  asset_class: string;
  direction: string;
  quantity: string;
  quantity_lots: number;
  average_cost: string;
  mark: string | null;
  market_value: string;
  realised_pnl: string;
  unrealised_pnl: string;
  fees: string;
  net_pnl: string;
  execution_ids: string[];
}

export interface Portfolio {
  positions: Position[];
  totals: Record<string, string>;
}

export interface RiskState {
  gross_exposure: string;
  net_exposure: string;
  long_exposure: string;
  short_exposure: string;
  by_asset_class: Record<string, string>;
  utilisation: { name: string; used: string; limit: string; ratio: string }[];
  drawdown: { drawdown: string; peak: string | null };
  var: { var: string | null; confidence: string; window: number; limitations: string[] };
  scenarios: { shock: string; estimated_pnl: string }[];
  alerts: { id: string; kind: string; detail: string; timestamp: string; symbol: string | null }[];
  concentration: { symbol: string; notional: string; fraction_of_capital: string }[];
}

export interface Order {
  order_id: string;
  client_order_id: string;
  symbol: string;
  side: string;
  order_type: string;
  quantity: string;
  limit_price: string | null;
  status: string;
  filled_lots: number;
  leaves_lots: number;
  average_price: string | null;
  reject_rule: string | null;
  reject_reason: string | null;
  simulated: boolean;
  lifecycle: { status: string; timestamp: string; reason: string }[];
}

export interface Fill {
  execution_id: string;
  order_id: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  fee: string;
  timestamp: string;
  liquidity: string;
}

export interface Preview {
  average_price: string | null;
  notional: string;
  fee: string;
  filled_lots_estimate: number;
  available_lots: number;
  risk_rule: string | null;
  risk_reason: string | null;
  book_stale: boolean;
  queue_model: string;
}

export interface QuerySpec {
  id: string;
  title: string;
  summary: string;
  q: string;
  explanation: string;
  engine: string;
}

export interface QueryResult {
  id: string;
  title: string;
  q: string;
  explanation: string;
  engine: string;
  note: string;
  elapsed_ms: number;
  row_count: number;
  rows: Record<string, unknown>[];
  executed_unrestricted_q: boolean;
}

export interface ReplayState {
  session_id: string | null;
  event_count: number;
  cursor: number;
  playing: boolean;
  speed: number;
  event_time: string | null;
  markers: { index: number; kind: string; symbol: string; time: string; detail: string }[];
  books?: Record<string, Book>;
  trades?: Trade[];
  candles?: Candle[];
  depth?: { index: number; bids: { price_ticks: number; quantity_lots: number }[]; asks: { price_ticks: number; quantity_lots: number }[] }[];
  risk?: {
    fills_applied: number;
    gross_exposure: string;
    net_exposure: string;
    net_pnl: string;
    realised_pnl: string;
    unrealised_pnl: string;
    fees: string;
    note: string;
  };
  session_ledger?: { orders?: Order[]; fills?: Fill[]; pnl?: unknown };
  isolated_from_live_ledger: boolean;
}

export interface SessionInfo {
  session_id: string;
  title?: string;
  summary?: string;
  kind?: string;
  seed?: number;
}
