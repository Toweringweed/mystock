"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import useSWR from "swr";
import { klineApi, KlineBar, Indicator } from "@/lib/api/kline";
import { analysisApi, DivergenceSignal } from "@/lib/api/analysis";
import { clsx } from "clsx";

// A股/港股涨红跌绿
const UP_COLOR = "#ef5350";
const DOWN_COLOR = "#26a69a";
const CHART_BG = "#0d1117";
const GRID_COLOR = "#21262d";
const TEXT_COLOR = "#8b949e";

const PERIODS = [
  { label: "3月", days: 90 },
  { label: "6月", days: 180 },
  { label: "1年", days: 365 },
  { label: "全部", days: 1000 },
] as const;

type IndicatorToggle = {
  ma: boolean;
  boll: boolean;
};

interface Props {
  code: string;
}

export function KlineChart({ code }: Props) {
  const [days, setDays] = useState(180);
  const [indicators, setIndicators] = useState<IndicatorToggle>({
    ma: true,
    boll: false,
  });

  const { data: klines } = useSWR(
    `kline-${code}-${days}`,
    () => klineApi.daily(code, days)
  );
  const { data: indData } = useSWR(
    `indicators-${code}-${days}`,
    () => klineApi.indicators(code, days)
  );
  const { data: divergences } = useSWR(
    `divergence-${code}`,
    () => analysisApi.divergence(code, 60)
  );

  const chartRef = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candleSeries = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volSeries = useRef<ISeriesApi<"Histogram"> | null>(null);
  const maSeries = useRef<Record<string, ISeriesApi<"Line">>>({});
  const bollSeries = useRef<Record<string, ISeriesApi<"Line">>>({});

  // 初始化图表
  useEffect(() => {
    if (!chartRef.current) return;

    chart.current = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_BG },
        textColor: TEXT_COLOR,
        fontSize: 12,
      },
      grid: {
        vertLines: { color: GRID_COLOR },
        horzLines: { color: GRID_COLOR },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: GRID_COLOR },
      timeScale: {
        borderColor: GRID_COLOR,
        timeVisible: true,
      },
      width: chartRef.current.clientWidth,
      height: 380,
    });

    candleSeries.current = chart.current.addSeries(CandlestickSeries, {
      upColor: UP_COLOR,
      downColor: DOWN_COLOR,
      borderVisible: false,
      wickUpColor: UP_COLOR,
      wickDownColor: DOWN_COLOR,
    });

    // 响应式宽度
    const ro = new ResizeObserver(() => {
      if (chartRef.current && chart.current) {
        chart.current.applyOptions({ width: chartRef.current.clientWidth });
      }
    });
    ro.observe(chartRef.current);

    return () => {
      ro.disconnect();
      chart.current?.remove();
      chart.current = null;
      candleSeries.current = null;
      maSeries.current = {};
      bollSeries.current = {};
    };
  }, []);

  // 更新 K 线数据
  useEffect(() => {
    if (!klines || !candleSeries.current) return;
    const data = klines.map((k) => ({
      time: k.trade_date as any,
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
    }));
    candleSeries.current.setData(data);
    chart.current?.timeScale().fitContent();
  }, [klines]);

  // MA 线
  useEffect(() => {
    if (!chart.current || !indData) return;

    // 清除旧 MA 线
    Object.values(maSeries.current).forEach((s) => chart.current!.removeSeries(s));
    maSeries.current = {};

    if (!indicators.ma) return;

    const MA_CONFIGS = [
      { key: "ma5", color: "#ff9800", width: 1 },
      { key: "ma10", color: "#2196f3", width: 1 },
      { key: "ma20", color: "#9c27b0", width: 1 },
      { key: "ma60", color: "#f44336", width: 2 },
    ];

    for (const cfg of MA_CONFIGS) {
      const series = chart.current.addSeries(LineSeries, {
        color: cfg.color,
        lineWidth: cfg.width as 1 | 2 | 3 | 4,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const data = indData
        .filter((d) => d[cfg.key as keyof Indicator] != null)
        .map((d) => ({
          time: d.trade_date as any,
          value: d[cfg.key as keyof Indicator] as number,
        }));
      series.setData(data);
      maSeries.current[cfg.key] = series;
    }
  }, [indData, indicators.ma]);

  // 布林带
  useEffect(() => {
    if (!chart.current || !indData) return;
    Object.values(bollSeries.current).forEach((s) => chart.current!.removeSeries(s));
    bollSeries.current = {};

    if (!indicators.boll) return;

    const BOLL_CONFIGS = [
      { key: "bb_upper", color: "#607d8b", dash: [4, 2] },
      { key: "bb_middle", color: "#78909c", dash: [] },
      { key: "bb_lower", color: "#607d8b", dash: [4, 2] },
    ];

    for (const cfg of BOLL_CONFIGS) {
      const series = chart.current.addSeries(LineSeries, {
        color: cfg.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        lineStyle: cfg.dash.length ? 1 : 0, // 0=Solid, 1=Dotted
      });
      const data = indData
        .filter((d) => d[cfg.key as keyof Indicator] != null)
        .map((d) => ({
          time: d.trade_date as any,
          value: d[cfg.key as keyof Indicator] as number,
        }));
      series.setData(data);
      bollSeries.current[cfg.key] = series;
    }
  }, [indData, indicators.boll]);

  return (
    <div className="space-y-2">
      {/* 控制栏 */}
      <div className="flex items-center gap-4">
        {/* 时间周期 */}
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              onClick={() => setDays(p.days)}
              className={clsx(
                "px-3 py-1 text-xs rounded transition-colors",
                days === p.days
                  ? "bg-[#58a6ff] text-gray-900"
                  : "bg-gray-100 text-gray-600 hover:text-gray-900"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="h-4 w-px bg-gray-200" />

        {/* 指标切换 */}
        {(
          [
            { key: "ma", label: "均线" },
            { key: "boll", label: "BOLL" },
          ] as const
        ).map((item) => (
          <button
            key={item.key}
            onClick={() =>
              setIndicators((prev) => ({ ...prev, [item.key]: !prev[item.key] }))
            }
            className={clsx(
              "px-3 py-1 text-xs rounded border transition-colors",
              indicators[item.key]
                ? "border-[#58a6ff] text-[#58a6ff]"
                : "border-gray-300 text-gray-500 hover:text-gray-700"
            )}
          >
            {item.label}
          </button>
        ))}

        {/* 均线图例 */}
        {indicators.ma && (
          <div className="flex items-center gap-3 text-xs">
            {[
              { label: "MA5", color: "#ff9800" },
              { label: "MA10", color: "#2196f3" },
              { label: "MA20", color: "#9c27b0" },
              { label: "MA60", color: "#f44336" },
            ].map((m) => (
              <span key={m.label} className="flex items-center gap-1">
                <span
                  className="inline-block w-4 h-0.5"
                  style={{ backgroundColor: m.color }}
                />
                <span className="text-gray-600">{m.label}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 背离信号提示 */}
      {divergences && divergences.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {divergences.slice(0, 3).map((d) => (
            <DivergenceBadge key={d.id} signal={d} />
          ))}
        </div>
      )}

      {/* K 线图容器 */}
      <div ref={chartRef} className="w-full rounded-lg overflow-hidden" />
    </div>
  );
}

function DivergenceBadge({ signal }: { signal: DivergenceSignal }) {
  const isBull = signal.signal_type.endsWith("BULL");
  const prefix = signal.signal_type.startsWith("MACD") ? "MACD" : "RSI";
  return (
    <span
      className={clsx(
        "text-xs px-2 py-0.5 rounded border",
        isBull
          ? "border-[#ef5350] text-[#ef5350] bg-[#ef5350]/10"
          : "border-[#26a69a] text-[#26a69a] bg-[#26a69a]/10"
      )}
      title={`置信度: ${((signal.confidence ?? 0) * 100).toFixed(0)}%`}
    >
      {prefix} {isBull ? "↑底背离" : "↓顶背离"} {signal.detected_date}
    </span>
  );
}
