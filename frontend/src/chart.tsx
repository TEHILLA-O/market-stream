import { useEffect, useRef } from "react";
import { CandlestickSeries, ColorType, HistogramSeries, LineSeries, createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import { useMarket, usePrefs } from "./state";
import type { Candle } from "./types";

export function MarketChart({ candles }: { candles: Candle[] }) {
  const mode = usePrefs((state) => state.chartMode);
  const setMode = usePrefs((state) => state.setChartMode);
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const price = useRef<ISeriesApi<"Candlestick"> | ISeriesApi<"Line"> | null>(null);
  const volume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const fit = useRef("");

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const next = createChart(element, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8b95a6", fontFamily: "IBM Plex Sans" },
      grid: { vertLines: { color: "rgba(232,236,244,0.04)" }, horzLines: { color: "rgba(232,236,244,0.04)" } },
      rightPriceScale: { borderColor: "rgba(232,236,244,0.08)" },
      timeScale: { borderColor: "rgba(232,236,244,0.08)", timeVisible: true, secondsVisible: true, rightOffset: 3, shiftVisibleRangeOnNewBar: true },
      crosshair: { vertLine: { color: "rgba(63,222,198,0.35)" }, horzLine: { color: "rgba(63,222,198,0.35)" } },
    });
    chart.current = next;
    return () => {
      next.remove();
      chart.current = null;
      price.current = null;
      volume.current = null;
    };
  }, []);

  useEffect(() => {
    const current = chart.current;
    if (!current) return;
    if (price.current) current.removeSeries(price.current);
    if (volume.current) current.removeSeries(volume.current);
    price.current = mode === "line"
      ? current.addSeries(LineSeries, { color: "#3fdec6", lineWidth: 2 })
      : current.addSeries(CandlestickSeries, {
          upColor: "#3cbe8b",
          downColor: "#e07a68",
          borderVisible: false,
          wickUpColor: "#3cbe8b",
          wickDownColor: "#e07a68",
        });
    volume.current = current.addSeries(HistogramSeries, { priceScaleId: "volume", priceFormat: { type: "volume" } });
    current.priceScale("volume").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
  }, [mode]);

  useEffect(() => {
    if (!price.current || !volume.current || !candles.length) return;
    if (mode === "line") {
      price.current.setData(candles.map((bar) => ({ time: bar.time as UTCTimestamp, value: bar.close })));
    } else {
      price.current.setData(candles.map((bar) => ({ time: bar.time as UTCTimestamp, open: bar.open, high: bar.high, low: bar.low, close: bar.close })));
    }
    volume.current.setData(candles.map((bar) => ({ time: bar.time as UTCTimestamp, value: bar.volume, color: bar.close >= bar.open ? "rgba(60,190,139,0.35)" : "rgba(224,122,104,0.35)" })));
    const fitKey = `${mode}:${candles[0]?.time ?? ""}`;
    if (fitKey !== fit.current) {
      fit.current = fitKey;
      const fitNow = () => chart.current?.timeScale().fitContent();
      fitNow();
      window.setTimeout(fitNow, 120);
    }
  }, [candles, mode]);

  const symbol = usePrefs((state) => state.symbol);
  const ready = useMarket((state) => state.candles[symbol]?.length ?? 0);
  return (
    <div className="chart-wrap">
      <div className="chart-tools">
        <button data-active={mode === "candle"} onClick={() => setMode("candle")}>Candles</button>
        <button data-active={mode === "line"} onClick={() => setMode("line")}>Line</button>
        <span className="kicker">{ready ? "trade OHLC · 5s · empty buckets omitted" : "waiting for trades"}</span>
      </div>
      <div className="chart" ref={host} />
    </div>
  );
}
