import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, clockLabel, csvTrades, tone } from "./lib/api";
import { loadOrders, loadSessions } from "./feed";
import { MarketChart } from "./chart";
import { TradeTape } from "./tape";
import { AnalyticalPanel, PanelGrip } from "./panels";
import { useMarket, usePrefs } from "./state";
import type { Book, Candle, Order, Preview, QueryResult, QuerySpec, ReplayState, RiskState } from "./types";

const NO_CANDLES: Candle[] = [];

export function Pulse() {
  const symbol = usePrefs((state) => state.symbol);
  const stats = useMarket((state) => state.stats[symbol]);
  const sim = useMarket((state) => state.sim);
  const candleBook = useMarket((state) => state.candles);
  const candles = candleBook[symbol] ?? NO_CANDLES;
  const tape = useMarket((state) => state.trades);
  const panels = usePrefs((state) => state.panels);
  const tapeSymbol = panels.tape.pinnedSymbol ?? symbol;
  const depthSymbol = panels.depth.pinnedSymbol ?? symbol;
  const trades = useMemo(() => tape.filter((trade) => trade.symbol === tapeSymbol), [tape, tapeSymbol]);
  const alerts = useMarket((state) => state.alerts);
  const books = useMarket((state) => state.books);
  const book = books[depthSymbol];
  return (
    <section className="pulse">
      <div className="statusline">
        <span>Session <b>{sim?.session_id ?? "—"}</b></span>
        <span>Regime <b>{sim?.regime ?? "—"}</b></span>
        <span>Speed <b>{sim?.speed ?? "—"}×</b></span>
        <span>Pulse <b>{sim?.pulse ?? "—"}</b></span>
        <span>Book <b data-testid="book-state" className={stats?.book_stale ? "neg" : "pos"}>{stats?.book_state ?? "—"}</b></span>
        <span>Seed <b>{sim?.seed ?? "—"}</b></span>
      </div>
      <div className="pulse-main">
        <MarketChart candles={candles} />
        <aside className="rail">
          <div>
            <div className="kicker">{stats?.asset_class ?? "instrument"} · {stats?.venue ?? "MSX"} · synthetic</div>
            <h1 className={stats?.change && Number(stats.change) < 0 ? "flash-down" : "flash-up"}>{stats?.last ?? "—"}</h1>
            <div className={`sub ${tone(stats?.change)}`}>{stats?.change ?? "—"} · {stats?.change_bps ?? "—"} bps vs reference</div>
          </div>
          <div className="quote-split">
            <div><span>Bid</span><strong>{stats?.bid ?? "—"}</strong></div>
            <div className="spread-pill">{stats?.spread ?? "—"}<br />{stats?.spread_bps ?? "—"} bps</div>
            <div style={{ textAlign: "right" }}><span>Ask</span><strong>{stats?.ask ?? "—"}</strong></div>
          </div>
          <dl className="metrics">
            <div><dt>VWAP</dt><dd>{stats?.vwap ?? "—"}</dd></div>
            <div><dt>Mid</dt><dd>{stats?.mid ?? "—"}</dd></div>
            <div><dt>Range</dt><dd>{stats?.low ?? "—"} – {stats?.high ?? "—"}</dd></div>
            <div><dt>Volume</dt><dd>{stats?.volume_lots ?? "—"}</dd></div>
            <div><dt>Volatility</dt><dd>{stats?.volatility ?? "—"}</dd></div>
            <div><dt>Imbalance</dt><dd>{stats?.imbalance ?? "—"}</dd></div>
          </dl>
          <p className="sub">Volatility is the sample standard deviation of log returns over 20 five-second closes. It is not annualised.</p>
        </aside>
      </div>
      <div className="pulse-lower">
        <AnalyticalPanel id="tape" title="Tape" symbol={symbol}>
          <TradeTape rows={trades} />
        </AnalyticalPanel>
        <PanelGrip left="tape" right="depth" />
        <AnalyticalPanel id="depth" title="Depth" symbol={symbol}>
          <MiniBook book={book} />
        </AnalyticalPanel>
        <PanelGrip left="depth" right="alerts" />
        <AnalyticalPanel id="alerts" title="Alerts" symbol={symbol}>
          {alerts.slice(-8).reverse().map((alert) => (
            <div key={alert.id} className="table-row" style={{ display: "block", padding: "8px 12px" }}>
              <b>{alert.kind}</b>
              <div className="sub">{alert.detail}</div>
            </div>
          ))}
          {alerts.length === 0 && <p className="empty-note">No rule has fired.</p>}
        </AnalyticalPanel>
      </div>
    </section>
  );
}

function MiniBook({ book }: { book?: Book }) {
  if (!book) return <p className="empty-note">Waiting for a snapshot.</p>;
  const bids = book.bids.slice(0, 6);
  const asks = book.asks.slice(0, 6);
  const max = Math.max(1, ...bids.map((level) => level.cumulative_lots), ...asks.map((level) => level.cumulative_lots));
  return (
    <div>
      {asks.slice().reverse().map((level) => (
        <div key={`a${level.price}`} className="book-row">
          <span />
          <span />
          <b>{level.price}</b>
          <span>{level.quantity_lots}</span>
          <span className="bar ask" style={{ width: `${(level.cumulative_lots / max) * 46}%` }} />
        </div>
      ))}
      <div className="book-row"><span /><span /><b>{book.mid ?? "—"}</b><span /><span /></div>
      {bids.map((level) => (
        <div key={`b${level.price}`} className="book-row">
          <span className="bar bid" style={{ width: `${(level.cumulative_lots / max) * 46}%` }} />
          <span>{level.quantity_lots}</span>
          <b>{level.price}</b>
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}

export function Depth() {
  const symbol = usePrefs((state) => state.symbol);
  const book = useMarket((state) => state.books[symbol]);
  const depth = useMarket((state) => state.depth);
  const setDepth = useMarket((state) => state.setDepth);
  useEffect(() => {
    let stop = false;
    const pull = () => {
      api<{ history: typeof depth }>(`/api/v1/market/depth?symbol=${symbol}`)
        .then((body) => { if (!stop) setDepth(body.history); })
        .catch(() => undefined);
    };
    pull();
    const timer = window.setInterval(pull, 2000);
    return () => { stop = true; window.clearInterval(timer); };
  }, [setDepth, symbol]);
  return (
    <section className="depth">
      <div className="statusline">
        <span>Book <b className={book?.health.stale ? "neg" : "pos"}>{book?.health.state ?? "—"}</b></span>
        <span>{book?.health.detail || "Sequence is contiguous"}</span>
        <span>Gaps <b>{book?.health.gap_count ?? 0}</b></span>
        <span>Spread <b>{book?.spread_bps ?? "—"} bps</b></span>
      </div>
      <div className="depth-main">
        <div className="ladder"><MiniBook book={book} /></div>
        <div className="heat">
          {depth.length === 0 ? <p className="empty-note">Snapshots have not accumulated yet. History is not invented from the current book.</p> : <Heatmap points={depth} />}
        </div>
      </div>
      <div className="depth-foot">
        <DepthCurve book={book} />
        <div className="scrub">
          <span className="kicker">{depth.length} snapshots</span>
        </div>
      </div>
    </section>
  );
}

function Heatmap({ points }: { points: { bids: { price_ticks: number; quantity_lots: number }[]; asks: { price_ticks: number; quantity_lots: number }[] }[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const width = canvas.clientWidth || 600;
    const height = canvas.clientHeight || 320;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    const prices = new Set<number>();
    for (const point of points) for (const level of [...point.bids, ...point.asks]) prices.add(level.price_ticks);
    const ladder = [...prices].sort((left, right) => right - left);
    const row = height / Math.max(ladder.length, 1);
    const col = width / Math.max(points.length, 1);
    points.forEach((point, x) => {
      for (const level of [...point.bids, ...point.asks]) {
        const y = ladder.indexOf(level.price_ticks) * row;
        const alpha = Math.min(0.9, 0.15 + level.quantity_lots / 1200);
        const bid = point.bids.includes(level);
        context.fillStyle = bid ? `rgba(63,222,198,${alpha})` : `rgba(224,122,104,${alpha})`;
        context.fillRect(x * col, y, Math.max(col - 0.4, 1), Math.max(row - 0.4, 1));
      }
    });
  }, [points]);
  return <canvas ref={ref} />;
}

function DepthCurve({ book }: { book?: Book }) {
  if (!book) return <svg className="curve" />;
  const bids = book.bids.slice(0, 8);
  const asks = book.asks.slice(0, 8);
  const max = Math.max(1, ...bids.map((level) => level.cumulative_lots), ...asks.map((level) => level.cumulative_lots));
  const bidPath = bids.map((level, index) => `${20 + (level.cumulative_lots / max) * 260},${20 + index * 18}`).join(" ");
  const askPath = asks.map((level, index) => `${560 - (level.cumulative_lots / max) * 260},${20 + index * 18}`).join(" ");
  return (
    <svg className="curve" viewBox="0 0 600 180">
      <polyline fill="none" stroke="#3fdec6" strokeWidth="1.4" points={bidPath} />
      <polyline fill="none" stroke="#e07a68" strokeWidth="1.4" points={askPath} />
    </svg>
  );
}

export function TapeWorkspace() {
  const symbol = usePrefs((state) => state.symbol);
  const setSymbol = usePrefs((state) => state.setSymbol);
  const [all, setAll] = useState(true);
  const trades = useMarket((state) => state.trades);
  const rows = all ? trades : trades.filter((trade) => trade.symbol === symbol);
  return (
    <section className="depth">
      <div className="statusline">
        <button onClick={() => setAll((value) => !value)}>{all ? "All instruments" : symbol}</button>
        <button onClick={() => csvTrades(rows)}>Export CSV</button>
        <span>{rows.length} prints in the buffer</span>
      </div>
      <div className="depth-main" style={{ gridTemplateColumns: "1fr" }}>
        <TradeTape rows={rows} />
      </div>
      <div className="statusline">
        {["ATHR", "BRDL", "NL100", "HLX", "LUMN"].map((item) => (
          <button key={item} onClick={() => { setSymbol(item); setAll(false); }}>{item}</button>
        ))}
      </div>
    </section>
  );
}

export function Execution() {
  const symbol = usePrefs((state) => state.symbol);
  const book = useMarket((state) => state.books[symbol]);
  const orders = useMarket((state) => state.orders);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [quantity, setQuantity] = useState("10");
  const [limit, setLimit] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useQuery({ queryKey: ["orders"], queryFn: loadOrders, refetchInterval: 2000 });
  useEffect(() => {
    const handle = window.setTimeout(() => {
      api<Preview>("/api/v1/orders/preview", {
        method: "POST",
        body: JSON.stringify({
          client_order_id: "preview",
          symbol,
          side,
          order_type: orderType,
          quantity_lots: Number(quantity) || 1,
          limit_price: orderType === "limit" ? limit : null,
        }),
      }).then(setPreview).catch((error: Error) => setNotice(error.message));
    }, 180);
    return () => window.clearTimeout(handle);
  }, [limit, orderType, quantity, side, symbol]);
  async function submit() {
    setBusy(true);
    setNotice(null);
    try {
      const order = await api<Order>("/api/v1/orders", {
        method: "POST",
        body: JSON.stringify({
          client_order_id: `web-${crypto.randomUUID()}`,
          symbol,
          side,
          order_type: orderType,
          quantity_lots: Number(quantity),
          limit_price: orderType === "limit" ? limit : null,
        }),
      });
      setNotice(order.status === "rejected" ? `${order.reject_rule}: ${order.reject_reason}` : `${order.status} ${order.filled_lots} lots @ ${order.average_price ?? "—"}`);
      await loadOrders();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The order request failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="split">
      <div className="ticket">
        <div className="banner">Paper simulation. Orders do not leave this process and cannot reach a broker.</div>
        <div className="kicker">{symbol} · queue model {preview?.queue_model ?? "conservative trade-through"}</div>
        <div className="side-switch">
          <button data-side="buy" data-active={side === "buy"} onClick={() => setSide("buy")}>Buy</button>
          <button data-side="sell" data-active={side === "sell"} onClick={() => setSide("sell")}>Sell</button>
        </div>
        <div className="seg">
          <button data-active={orderType === "market"} onClick={() => setOrderType("market")}>Market</button>
          <button data-active={orderType === "limit"} onClick={() => setOrderType("limit")}>Limit</button>
        </div>
        <label className="field">Quantity (lots)<input value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>
        {orderType === "limit" && <label className="field">Limit<input value={limit} onChange={(event) => setLimit(event.target.value)} placeholder={book?.best_bid ?? ""} /></label>}
        <div className="preview-grid">
          <div><span>Estimated price</span>{preview?.average_price ?? "—"}</div>
          <div><span>Notional</span>{preview?.notional ?? "—"}</div>
          <div><span>Fee</span>{preview?.fee ?? "—"}</div>
          <div><span>Displayed lots</span>{preview?.available_lots ?? book?.asks.length ?? "—"}</div>
        </div>
        {preview?.risk_rule && <p className="reject">{preview.risk_rule}: {preview.risk_reason}</p>}
        {preview?.book_stale && <p className="reject">Book is stale. New orders will be rejected until a snapshot recovers it.</p>}
        {notice && <p className={notice.includes(":") && notice.includes("max_") ? "reject" : "sub"}>{notice}</p>}
        <button className="submit" disabled={busy} onClick={() => void submit()}>Simulate {side}</button>
      </div>
      <div className="pane-b">
        <table className="table">
          <thead><tr><th>Order</th><th>Side</th><th>Type</th><th>Status</th><th>Filled</th><th>Avg</th><th></th></tr></thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.order_id}>
                <td>{order.symbol}</td>
                <td className={order.side === "buy" ? "pos" : "neg"}>{order.side}</td>
                <td>{order.order_type}</td>
                <td>{order.status}{order.reject_rule ? ` · ${order.reject_rule}` : ""}</td>
                <td>{order.filled_lots}</td>
                <td>{order.average_price ?? "—"}</td>
                <td>{(order.status === "working" || order.status === "partially_filled") && <button className="link" onClick={() => void api(`/api/v1/orders/${order.order_id}/cancel`, { method: "POST" }).then(() => loadOrders())}>Cancel</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {orders.length === 0 && <p className="empty-note">No paper orders yet.</p>}
      </div>
    </section>
  );
}

export function PortfolioView() {
  const portfolio = useMarket((state) => state.portfolio);
  const setSymbol = usePrefs((state) => state.setSymbol);
  const setWorkspace = usePrefs((state) => state.setWorkspace);
  const positions = portfolio?.positions ?? [];
  const totals = portfolio?.totals;
  return (
    <section className="constellation">
      <div className="sky">
        <svg viewBox="0 0 420 640">
          <circle cx="210" cy="300" r="46" fill="none" stroke="rgba(232,236,244,0.2)" />
          <text x="210" y="304" textAnchor="middle" fill="#e7edf6" fontSize="12">{totals?.net_pnl ?? "0.00"}</text>
          {positions.map((position, index) => {
            const angle = (index / Math.max(positions.length, 1)) * Math.PI * 2 - Math.PI / 2;
            const radius = 18 + Math.min(70, Math.sqrt(Math.abs(Number(position.market_value))) / 12);
            const cx = 210 + Math.cos(angle) * 150;
            const cy = 300 + Math.sin(angle) * 150;
            return (
              <g key={position.symbol} onClick={() => { setSymbol(position.symbol); setWorkspace("pulse"); }} style={{ cursor: "pointer" }}>
                <circle cx={cx} cy={cy} r={radius} fill={Number(position.net_pnl) >= 0 ? "rgba(60,190,139,0.25)" : "rgba(224,122,104,0.25)"} stroke={Number(position.net_pnl) >= 0 ? "#3cbe8b" : "#e07a68"} />
                <text x={cx} y={cy + 4} textAnchor="middle" fill="#e7edf6" fontSize="11">{position.symbol}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <div>
        <div className="totals">
          <div><span>Net P&L</span><b className={tone(totals?.net_pnl)}>{totals?.net_pnl ?? "—"}</b></div>
          <div><span>Realised</span>{totals?.realised_pnl ?? "—"}</div>
          <div><span>Unrealised</span>{totals?.unrealised_pnl ?? "—"}</div>
          <div><span>Fees</span>{totals?.fees ?? "—"}</div>
          <div><span>Cash</span>{totals?.cash ?? "—"}</div>
        </div>
        <table className="table">
          <thead><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>Mark</th><th>Value</th><th>Net</th><th>Fills</th></tr></thead>
          <tbody>
            {positions.map((position) => (
              <tr key={position.symbol} onClick={() => setSymbol(position.symbol)}>
                <td>{position.symbol}</td>
                <td>{position.quantity}</td>
                <td>{position.average_cost}</td>
                <td>{position.mark ?? "—"}</td>
                <td>{position.market_value}</td>
                <td className={tone(position.net_pnl)}>{position.net_pnl}</td>
                <td>{position.execution_ids.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {positions.length === 0 && <p className="empty-note">Flat. P&L appears only after simulated fills.</p>}
        <p className="empty-note">{totals?.fx_note}</p>
      </div>
    </section>
  );
}

export function RiskView() {
  const risk = useMarket((state) => state.risk);
  return (
    <section className="risk">
      <div className="rings">
        {(risk?.utilisation ?? []).map((item) => (
          <Ring key={item.name} item={item} />
        ))}
        <div>
          <div className="kicker">Drawdown</div>
          <div className="neg">{risk?.drawdown.drawdown ?? "0.00"}</div>
        </div>
        <div>
          <div className="kicker">Historical VaR {risk?.var.confidence}</div>
          <div>{risk?.var.var ?? "insufficient history"}</div>
          <p className="sub">{risk?.var.limitations?.[0]}</p>
        </div>
      </div>
      <div className="pane-b">
        <table className="table">
          <thead><tr><th>Shock</th><th>Estimated P&L</th></tr></thead>
          <tbody>
            {(risk?.scenarios ?? []).map((row) => (
              <tr key={row.shock}><td>{row.shock}</td><td className={tone(row.estimated_pnl)}>{row.estimated_pnl}</td></tr>
            ))}
          </tbody>
        </table>
        <table className="table">
          <thead><tr><th>Symbol</th><th>Notional</th><th>Capital</th></tr></thead>
          <tbody>
            {(risk?.concentration ?? []).map((row) => (
              <tr key={row.symbol}><td>{row.symbol}</td><td>{row.notional}</td><td>{row.fraction_of_capital}</td></tr>
            ))}
          </tbody>
        </table>
        <div className="totals">
          <div><span>Gross</span>{risk?.gross_exposure ?? "—"}</div>
          <div><span>Net</span>{risk?.net_exposure ?? "—"}</div>
          <div><span>Long</span>{risk?.long_exposure ?? "—"}</div>
          <div><span>Short</span>{risk?.short_exposure ?? "—"}</div>
        </div>
      </div>
    </section>
  );
}

function Ring({ item }: { item: RiskState["utilisation"][number] }) {
  const ratio = Number(item.ratio);
  const r = 32;
  const c = 2 * Math.PI * r;
  const dash = Math.min(Math.max(ratio, 0), 1) * c;
  return (
    <div className="ring-row">
      <svg viewBox="0 0 92 92" aria-label={`${item.name} ${item.used} of ${item.limit}`}>
        <circle className="ring-track" cx="46" cy="46" r={r} />
        <circle className={ratio > 1 ? "ring-hot" : "ring-value"} cx="46" cy="46" r={r} strokeDasharray={`${dash} ${c}`} />
      </svg>
      <div>
        <div className="kicker">{item.name}</div>
        <b>{item.used}</b>
        <div className="sub">limit {item.limit}</div>
      </div>
    </div>
  );
}

export function ReplayStudio() {
  const symbol = usePrefs((state) => state.symbol);
  const sessions = useMarket((state) => state.sessions);
  const setSessions = useMarket((state) => state.setSessions);
  const replay = useMarket((state) => state.replay);
  const setReplay = useMarket((state) => state.setReplay);
  useEffect(() => {
    loadSessions().then(setSessions).catch(() => undefined);
  }, [setSessions]);
  useEffect(() => {
    if (!replay?.playing) return;
    const timer = window.setInterval(() => {
      api<ReplayState>(`/api/v1/replay/state?symbol=${symbol}`).then(setReplay).catch(() => undefined);
    }, 250);
    return () => window.clearInterval(timer);
  }, [replay?.playing, setReplay, symbol]);
  async function act(path: string, body?: unknown) {
    await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
    setReplay(await api<ReplayState>(`/api/v1/replay/state?symbol=${symbol}`));
  }
  const book = replay?.books?.[symbol];
  return (
    <section className="replay">
      <div className="transport">
        <select
          aria-label="Session"
          key={replay?.session_id ?? "none"}
          defaultValue={replay?.session_id ?? ""}
          onChange={(event) => {
            const sessionId = event.target.value;
            if (sessionId) void act("/api/v1/replay/load", { session_id: sessionId });
          }}
        >
          <option value="">Select a session</option>
          {sessions.map((session) => <option key={session.session_id} value={session.session_id}>{session.title ?? session.session_id}</option>)}
        </select>
        <button onClick={() => void act("/api/v1/replay/seek", { index: 0 })}>Restart</button>
        <button onClick={() => void act("/api/v1/replay/step", { count: -1 })}>Step back</button>
        <button onClick={() => void act(replay?.playing ? "/api/v1/replay/pause" : "/api/v1/replay/play")}>{replay?.playing ? "Pause" : "Play"}</button>
        <button onClick={() => void act("/api/v1/replay/step", { count: 1 })}>Step</button>
        <input aria-label="Timeline" type="range" min={0} max={replay?.event_count ?? 0} value={replay?.cursor ?? 0} onChange={(event) => void act("/api/v1/replay/seek", { index: Number(event.target.value) })} />
        <label className="transport-field">Speed
          <select aria-label="Playback speed" value={String(replay?.speed ?? 8)} onChange={(event) => void act("/api/v1/replay/speed", { speed: Number(event.target.value) })}>
            <option value="1">1×</option>
            <option value="4">4×</option>
            <option value="8">8×</option>
            <option value="16">16×</option>
          </select>
        </label>
        <form className="transport-field" onSubmit={(event) => {
          event.preventDefault();
          const field = new FormData(event.currentTarget).get("when");
          const clock = String(field ?? "").trim();
          if (!clock) return;
          const day = (replay?.event_time ?? "").slice(0, 10);
          const timestamp = clock.length <= 8 && day ? `${day}T${clock}` : clock;
          void act("/api/v1/replay/seek", { timestamp });
        }}>
          <input name="when" aria-label="Jump to time" placeholder="HH:MM:SS" />
          <button type="submit">Jump</button>
        </form>
        <b>{clockLabel(replay?.event_time)}</b>
        <span>{replay?.cursor ?? 0}/{replay?.event_count ?? 0}</span>
      </div>
      <div className="statusline">Replay is isolated from the live position ledger. {replay?.isolated_from_live_ledger ? "Ledger untouched." : ""}</div>
      <div className="replay-main">
        <MarketChart candles={replay?.candles ?? []} />
        <div className="ladder"><MiniBook book={book} /></div>
      </div>
      <div className="replay-lower">
        <div className="heat">
          {(replay?.depth?.length ?? 0) === 0
            ? <p className="empty-note">Depth history appears from reconstructed snapshots. Nothing is drawn before the playhead.</p>
            : <Heatmap points={replay?.depth ?? []} />}
        </div>
        <section className="pane">
          <header className="pane-h"><h2>Playhead risk</h2><span>{replay?.risk?.fills_applied ?? 0} fills</span></header>
          <div className="pane-b">
            <dl className="metrics">
              <div><dt>Net P&L</dt><dd className={tone(replay?.risk?.net_pnl)}>{replay?.risk?.net_pnl ?? "—"}</dd></div>
              <div><dt>Realised</dt><dd>{replay?.risk?.realised_pnl ?? "—"}</dd></div>
              <div><dt>Unrealised</dt><dd>{replay?.risk?.unrealised_pnl ?? "—"}</dd></div>
              <div><dt>Fees</dt><dd>{replay?.risk?.fees ?? "—"}</dd></div>
              <div><dt>Gross exposure</dt><dd>{replay?.risk?.gross_exposure ?? "—"}</dd></div>
              <div><dt>Net exposure</dt><dd>{replay?.risk?.net_exposure ?? "—"}</dd></div>
            </dl>
            <p className="sub">{replay?.risk?.note ?? "Load a session to read its fill file."}</p>
          </div>
        </section>
        <div>
          <div className="markers">
            {(replay?.markers ?? []).map((marker) => (
              <button key={`${marker.kind}-${marker.index}`} onClick={() => void act("/api/v1/replay/seek", { index: marker.index })}>{marker.kind} · {marker.symbol}</button>
            ))}
          </div>
          <TradeTape rows={replay?.trades ?? []} />
        </div>
      </div>
    </section>
  );
}

export function QueryLab() {
  const symbol = usePrefs((state) => state.symbol);
  const catalogue = useQuery({ queryKey: ["queries"], queryFn: () => api<{ queries: QuerySpec[] }>("/api/v1/queries") });
  const [active, setActive] = useState("vwap");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const spec = catalogue.data?.queries.find((item) => item.id === active);
  async function run() {
    setError(null);
    try {
      setResult(await api<QueryResult>("/api/v1/queries/run", { method: "POST", body: JSON.stringify({ query_id: active, symbol, interval: "5s" }) }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "query failed");
    }
  }
  const columns = useMemo(() => Object.keys(result?.rows[0] ?? {}).slice(0, 8), [result]);
  return (
    <section className="lab">
      <div className="q-list">
        {(catalogue.data?.queries ?? []).map((item) => (
          <button key={item.id} data-active={item.id === active} onClick={() => setActive(item.id)}>
            <b>{item.title}</b>
            <div className="sub">{item.summary}</div>
          </button>
        ))}
      </div>
      <div>
        <div className="pane-h">
          <span className="badge">{result?.engine ?? spec?.engine ?? "python-reference"}</span>
          <button onClick={() => void run()}>Run {symbol}</button>
        </div>
        <pre className="q-source">{spec?.q}</pre>
        <p className="empty-note">{result?.explanation ?? spec?.explanation}</p>
        {result && <p className="empty-note">{result.row_count} rows · {result.elapsed_ms} ms · unrestricted q: {String(result.executed_unrestricted_q)}. {result.note}</p>}
        {error && <p className="reject">{error}</p>}
        <table className="table">
          <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
          <tbody>
            {(result?.rows ?? []).slice(0, 40).map((row, index) => (
              <tr key={index}>{columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function Systems() {
  const system = useMarket((state) => state.system);
  if (!system) return <p className="empty-note">Waiting for a measured status frame from the API process.</p>;
  return (
    <section className="systems">
      <div className="metric-band">
        <div><span>Generated</span>{system.generated}</div>
        <div><span>Ingested</span>{system.ingested}</div>
        <div><span>Quarantined</span>{system.quarantined}</div>
        <div><span>Gaps</span>{system.gaps}</div>
        <div><span>Latency p50</span>{system.latency.p50 ?? "—"} ms</div>
        <div><span>p95</span>{system.latency.p95 ?? "—"}</div>
        <div><span>p99</span>{system.latency.p99 ?? "—"}</div>
        <div><span>Sockets</span>{system.websocket_clients}</div>
      </div>
      <div className="pane-b">
        {system.components.map((component) => (
          <div key={component.name} className="component" data-state={component.state}>
            <b>{component.name}</b>
            <strong>{component.state}</strong>
            <span>{component.detail}</span>
          </div>
        ))}
        <p className="empty-note">{system.latency.sample}. These figures are in-process. They are not exchange latency. {system.engine.detail}</p>
      </div>
    </section>
  );
}
