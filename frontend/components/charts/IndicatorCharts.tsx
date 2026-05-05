"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  IChartApi,
  HistogramSeries,
  LineSeries,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import { Indicator, KlineBar } from "@/lib/api/kline";

const CHART_BG = "#0d1117";
const GRID_COLOR = "#21262d";
const TEXT_COLOR = "#8b949e";
const UP_COLOR = "#ef5350";
const DOWN_COLOR = "#26a69a";

interface BaseProps {
  indicators: Indicator[];
  klines?: KlineBar[];
  height?: number;
}

function useIndicatorChart(
  containerRef: React.RefObject<HTMLDivElement | null>,
  height: number
) {
  const chart = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    chart.current = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_BG },
        textColor: TEXT_COLOR,
        fontSize: 11,
      },
      grid: {
        vertLines: { color: GRID_COLOR },
        horzLines: { color: GRID_COLOR },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: GRID_COLOR, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor: GRID_COLOR, timeVisible: true },
      width: containerRef.current.clientWidth,
      height,
    });

    const ro = new ResizeObserver(() => {
      if (containerRef.current && chart.current) {
        chart.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.current?.remove();
    };
  }, []);

  return chart;
}

// ── 成交量图 ───────────────────────────────────────────────────────

export function VolumeChart({ klines = [], height = 100 }: { klines?: KlineBar[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useIndicatorChart(ref, height);

  useEffect(() => {
    if (!chart.current || !klines.length) return;
    const series = chart.current.addSeries(HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
    });
    chart.current.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.7, bottom: 0 },
    });
    series.setData(
      klines.map((k) => ({
        time: k.trade_date as any,
        value: k.volume,
        color: k.change_pct >= 0 ? UP_COLOR + "99" : DOWN_COLOR + "99",
      }))
    );
  }, [klines]);

  return (
    <div>
      <p className="text-xs text-gray-500 px-1 mb-1">成交量</p>
      <div ref={ref} className="w-full rounded overflow-hidden" />
    </div>
  );
}

// ── MACD 图 ────────────────────────────────────────────────────────

export function MacdChart({ indicators, height = 120 }: BaseProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useIndicatorChart(ref, height);

  useEffect(() => {
    if (!chart.current || !indicators.length) return;

    const histSeries = chart.current.addSeries(HistogramSeries, {
      color: UP_COLOR,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    histSeries.setData(
      indicators
        .filter((d) => d.macd_hist != null)
        .map((d) => ({
          time: d.trade_date as any,
          value: d.macd_hist!,
          color: d.macd_hist! >= 0 ? UP_COLOR + "cc" : DOWN_COLOR + "cc",
        }))
    );

    const macdLine = chart.current.addSeries(LineSeries, {
      color: "#ff9800",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    macdLine.setData(
      indicators
        .filter((d) => d.macd != null)
        .map((d) => ({ time: d.trade_date as any, value: d.macd! }))
    );

    const signalLine = chart.current.addSeries(LineSeries, {
      color: "#e040fb",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    signalLine.setData(
      indicators
        .filter((d) => d.macd_signal != null)
        .map((d) => ({ time: d.trade_date as any, value: d.macd_signal! }))
    );
  }, [indicators]);

  return (
    <div>
      <div className="flex items-center gap-3 px-1 mb-1">
        <p className="text-xs text-gray-500">MACD(12,26,9)</p>
        <span className="flex items-center gap-1 text-xs">
          <span className="w-3 h-0.5 bg-[#ff9800] inline-block" />
          <span className="text-gray-500">DIF</span>
        </span>
        <span className="flex items-center gap-1 text-xs">
          <span className="w-3 h-0.5 bg-[#e040fb] inline-block" />
          <span className="text-gray-500">DEA</span>
        </span>
      </div>
      <div ref={ref} className="w-full rounded overflow-hidden" />
    </div>
  );
}

// ── RSI 图 ─────────────────────────────────────────────────────────

export function RsiChart({ indicators, height = 100 }: BaseProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useIndicatorChart(ref, height);

  useEffect(() => {
    if (!chart.current || !indicators.length) return;

    const configs = [
      { key: "rsi_6" as const, color: "#ff9800" },
      { key: "rsi_14" as const, color: "#2196f3" },
      { key: "rsi_24" as const, color: "#9c27b0" },
    ];

    for (const cfg of configs) {
      const series = chart.current.addSeries(LineSeries, {
        color: cfg.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      series.setData(
        indicators
          .filter((d) => d[cfg.key] != null)
          .map((d) => ({ time: d.trade_date as any, value: d[cfg.key]! }))
      );
    }

    // 超买/超卖参考线
    for (const level of [30, 70]) {
      const line = chart.current.addSeries(LineSeries, {
        color: "#555",
        lineWidth: 1,
        lineStyle: 1, // dotted
        priceLineVisible: false,
        lastValueVisible: false,
      });
      if (indicators.length) {
        line.setData([
          { time: indicators[0].trade_date as any, value: level },
          { time: indicators[indicators.length - 1].trade_date as any, value: level },
        ]);
      }
    }
  }, [indicators]);

  return (
    <div>
      <div className="flex items-center gap-3 px-1 mb-1">
        <p className="text-xs text-gray-500">RSI</p>
        {[
          { label: "6", color: "#ff9800" },
          { label: "14", color: "#2196f3" },
          { label: "24", color: "#9c27b0" },
        ].map((m) => (
          <span key={m.label} className="flex items-center gap-1 text-xs">
            <span className="w-3 h-0.5 inline-block" style={{ backgroundColor: m.color }} />
            <span className="text-gray-500">RSI{m.label}</span>
          </span>
        ))}
      </div>
      <div ref={ref} className="w-full rounded overflow-hidden" />
    </div>
  );
}

// ── KDJ 图 ─────────────────────────────────────────────────────────

export function KdjChart({ indicators, height = 100 }: BaseProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useIndicatorChart(ref, height);

  useEffect(() => {
    if (!chart.current || !indicators.length) return;

    const configs = [
      { key: "kdj_k" as const, color: "#ff9800", label: "K" },
      { key: "kdj_d" as const, color: "#2196f3", label: "D" },
      { key: "kdj_j" as const, color: "#f44336", label: "J" },
    ];

    for (const cfg of configs) {
      const series = chart.current.addSeries(LineSeries, {
        color: cfg.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      series.setData(
        indicators
          .filter((d) => d[cfg.key] != null)
          .map((d) => ({ time: d.trade_date as any, value: d[cfg.key]! }))
      );
    }
  }, [indicators]);

  return (
    <div>
      <div className="flex items-center gap-3 px-1 mb-1">
        <p className="text-xs text-gray-500">KDJ(9,3,3)</p>
        {[
          { label: "K", color: "#ff9800" },
          { label: "D", color: "#2196f3" },
          { label: "J", color: "#f44336" },
        ].map((m) => (
          <span key={m.label} className="flex items-center gap-1 text-xs">
            <span className="w-3 h-0.5 inline-block" style={{ backgroundColor: m.color }} />
            <span className="text-gray-500">{m.label}</span>
          </span>
        ))}
      </div>
      <div ref={ref} className="w-full rounded overflow-hidden" />
    </div>
  );
}
