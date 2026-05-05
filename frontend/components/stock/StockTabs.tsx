"use client";

import { useState } from "react";
import { clsx } from "clsx";
import useSWR from "swr";
import { klineApi } from "@/lib/api/kline";
import { KlineChart } from "@/components/charts/KlineChart";
import { VolumeChart, MacdChart, RsiChart, KdjChart } from "@/components/charts/IndicatorCharts";
import { ChipChart } from "@/components/charts/ChipChart";
import { FundamentalPanel } from "@/components/stock/FundamentalPanel";
import { ReportPanel } from "@/components/stock/ReportPanel";
import { SupplyChainPanel } from "@/components/stock/SupplyChainPanel";
import { NewsFeed } from "@/components/news/NewsFeed";

const TABS = [
  { key: "kline", label: "K线/技术" },
  { key: "fundamental", label: "基本面" },
  { key: "chip", label: "筹码" },
  { key: "report", label: "AI报告" },
  { key: "supply-chain", label: "供应链" },
  { key: "news", label: "资讯" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

// 副图切换
const SUB_CHARTS = [
  { key: "volume", label: "成交量" },
  { key: "macd", label: "MACD" },
  { key: "rsi", label: "RSI" },
  { key: "kdj", label: "KDJ" },
] as const;

export function StockTabs({ code }: { code: string }) {
  const [activeTab, setActiveTab] = useState<TabKey>("kline");
  const [subChart, setSubChart] = useState<string>("macd");
  const [klineDays] = useState(180);

  const { data: klines } = useSWR(
    activeTab === "kline" ? `kline-${code}-${klineDays}` : null,
    () => klineApi.daily(code, klineDays)
  );
  const { data: indicators } = useSWR(
    activeTab === "kline" ? `indicators-${code}-${klineDays}` : null,
    () => klineApi.indicators(code, klineDays)
  );

  return (
    <div className="flex flex-col h-[calc(100vh-100px)]">
      {/* Tab 导航 */}
      <nav className="flex border-b border-gray-200 px-6 shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={clsx(
              "px-4 py-3 text-sm font-medium border-b-2 transition-colors",
              activeTab === tab.key
                ? "border-[#58a6ff] text-[#58a6ff]"
                : "border-transparent text-gray-600 hover:text-gray-800"
            )}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Tab 内容 */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* ── K线/技术 ───────────────────────────────── */}
        {activeTab === "kline" && (
          <div className="space-y-3">
            <KlineChart code={code} />

            {/* 副图选择 */}
            <div className="flex gap-1 pt-1">
              {SUB_CHARTS.map((s) => (
                <button
                  key={s.key}
                  onClick={() => setSubChart(s.key)}
                  className={clsx(
                    "px-3 py-1 text-xs rounded transition-colors",
                    subChart === s.key
                      ? "bg-[#58a6ff]/20 text-[#58a6ff] border border-[#58a6ff]/40"
                      : "bg-gray-100 text-gray-500 hover:text-gray-700"
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>

            {/* 副图 */}
            {subChart === "volume" && <VolumeChart klines={klines} height={100} />}
            {subChart === "macd" && indicators && (
              <MacdChart indicators={indicators} height={120} />
            )}
            {subChart === "rsi" && indicators && (
              <RsiChart indicators={indicators} height={100} />
            )}
            {subChart === "kdj" && indicators && (
              <KdjChart indicators={indicators} height={100} />
            )}
          </div>
        )}

        {/* ── 基本面 ──────────────────────────────────── */}
        {activeTab === "fundamental" && <FundamentalPanel code={code} />}

        {/* ── 筹码 ────────────────────────────────────── */}
        {activeTab === "chip" && <ChipChart code={code} />}

        {/* ── AI 报告 ─────────────────────────────────── */}
        {activeTab === "report" && <ReportPanel code={code} />}

        {/* ── 供应链 ──────────────────────────────────── */}
        {activeTab === "supply-chain" && <SupplyChainPanel code={code} />}

        {/* ── 资讯 ────────────────────────────────────── */}
        {activeTab === "news" && (
          <div className="max-w-2xl space-y-3">
            <h3 className="text-sm text-gray-600">相关资讯</h3>
            <NewsFeed codes={[code]} />
          </div>
        )}
      </div>
    </div>
  );
}
