import { useEffect } from "react";
import { api } from "./lib/api";
import { useMarket, usePrefs } from "./state";
import type { Book, Candle, Instrument, Order, Portfolio, SessionInfo, Trade } from "./types";

export function useSession() {
  const symbol = usePrefs((state) => state.symbol);
  const setConnection = useMarket((state) => state.setConnection);
  const setInstruments = useMarket((state) => state.setInstruments);
  const setCandles = useMarket((state) => state.setCandles);
  const setTrades = useMarket((state) => state.setTrades);
  const apply = useMarket((state) => state.apply);
  const setError = useMarket((state) => state.setError);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let stopped = false;
    let timer = 0;
    const connect = () => {
      if (stopped) return;
      setConnection("connecting");
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${window.location.host}/ws/v1/market`);
      socket.onopen = () => setConnection("live");
      socket.onmessage = (event) => {
        const frame = JSON.parse(event.data) as { category?: string; messages?: Record<string, unknown>[] };
        if (frame.category === "batch") {
          for (const message of frame.messages ?? []) apply(message);
        }
      };
      socket.onerror = () => setError("WebSocket connection failed");
      socket.onclose = () => {
        if (stopped) return;
        setConnection("reconnecting");
        timer = window.setTimeout(connect, 900);
      };
    };
    connect();
    api<{ instruments: Instrument[] }>("/api/v1/instruments")
      .then((body) => setInstruments(body.instruments))
      .catch((error: Error) => setError(error.message));
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [apply, setConnection, setError, setInstruments]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api<{ candles: Candle[] }>(`/api/v1/market/candles?symbol=${symbol}&interval=5s&limit=300`),
      api<{ trades: Trade[] }>("/api/v1/market/trades?limit=120"),
      api<Book>(`/api/v1/market/orderbook?symbol=${symbol}`),
    ])
      .then(([candles, trades, book]) => {
        if (cancelled) return;
        setCandles(symbol, candles.candles);
        setTrades(trades.trades);
        apply({ category: "book", ...book });
      })
      .catch((error: Error) => setError(error.message));
    return () => {
      cancelled = true;
    };
  }, [apply, setCandles, setError, setTrades, symbol]);
}

export function loadOrders() {
  return Promise.all([
    api<{ orders: Order[] }>("/api/v1/orders"),
    api<Portfolio>("/api/v1/positions"),
  ]).then(([orders, portfolio]) => {
    useMarket.getState().setOrders(orders.orders);
    useMarket.getState().setPortfolio(portfolio);
  });
}

export function loadSessions() {
  return api<{ sessions: SessionInfo[] }>("/api/v1/replay/sessions").then((body) => {
    useMarket.getState().setSessions(body.sessions);
    return body.sessions;
  });
}
