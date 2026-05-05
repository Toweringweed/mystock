"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import useSWR from "swr";
import clsx from "clsx";
import { backtestApi, BacktestItem, BacktestMode, BacktestSummary } from "@/lib/api/backtest";

// echarts 在客户端动态加载，避免 SSR 问题
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const HORIZONS = [7, 14, 30, 60, 90];
const MODES: { v: BacktestMode; label: string; hint: string }[] = [
  { v: "lookback", label: "事后印证", hint: "评分前 N 天涨幅,样本量足时使用" },
  { v: "prediction", label: "预测验证", hint: "评分后 N 天涨幅,需历史评分(等待样本积累)" },
];

export default function BacktestPage() {
  const [horizon, setHorizon] = useState<number>(30);
  const [mode, setMode] = useState<BacktestMode>("lookback");

  const { data: items = [], isLoading: loadingItems } = useSWR<BacktestItem[]>(
    ["backtest-scores", horizon, mode],
    () => backtestApi.scores(horizon, mode),
    { revalidateOnFocus: false },
  );
  const { data: summary, isLoading: loadingSummary } = useSWR<BacktestSummary>(
    ["backtest-summary", horizon, mode],
    () => backtestApi.summary(horizon, mode),
    { revalidateOnFocus: false },
  );

  // 散点图配置
  const scatterOption = useMemo(() => {
    const normal = items.filter((i) => !i.veto_triggered);
    const veto = items.filter((i) => i.veto_triggered);
    return {
      backgroundColor: "transparent",
      grid: { top: 50, right: 30, bottom: 50, left: 60 },
      tooltip: {
        backgroundColor: "#1c2333",
        borderColor: "#4a5568",
        textStyle: { color: "#e5e7eb" },
        formatter: (p: { data: number[]; seriesName: string; value: number[]; }) => {
          const item = items.find(
            (i) => i.claude_overall_score === p.value[0] && i.return_pct === p.value[1],
          );
          if (!item) return "";
          return `<div style="font-size:12px">
            <b>${item.name} (${item.code})</b><br/>
            综合分: ${item.claude_overall_score}<br/>
            ${horizon}日涨幅: <b style="color:${item.return_pct >= 0 ? "#ef5350" : "#26a69a"}">${item.return_pct.toFixed(2)}%</b><br/>
            标签: ${item.claude_overall_label ?? "—"}<br/>
            ${item.veto_triggered ? `<span style="color:#ef5350">⚠ Veto: ${item.veto_reason ?? "—"}</span><br/>` : ""}
            评分日: ${item.score_date} | 基准: ¥${item.base_price.toFixed(2)} → 目标: ¥${item.target_price.toFixed(2)}
          </div>`;
        },
      },
      xAxis: {
        name: "Claude 8D 综合分",
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: "#9ca3af" },
        type: "value",
        min: 0, max: 10,
        axisLabel: { color: "#9ca3af" },
        splitLine: { lineStyle: { color: "#374151", type: "dashed" } },
      },
      yAxis: {
        name: `${mode === "lookback" ? "评分前" : "评分后"} ${horizon} 日涨幅 (%)`,
        nameLocation: "middle",
        nameGap: 45,
        nameTextStyle: { color: "#9ca3af" },
        type: "value",
        axisLabel: { color: "#9ca3af", formatter: "{value}%" },
        splitLine: { lineStyle: { color: "#374151", type: "dashed" } },
      },
      series: [
        {
          name: "正常",
          type: "scatter",
          symbolSize: 14,
          data: normal.map((i) => [i.claude_overall_score, i.return_pct]),
          itemStyle: { color: "#58a6ff", opacity: 0.85 },
        },
        {
          name: "Veto",
          type: "scatter",
          symbolSize: 18,
          symbol: "diamond",
          data: veto.map((i) => [i.claude_overall_score, i.return_pct]),
          itemStyle: { color: "#ef5350", borderColor: "#fff", borderWidth: 1 },
        },
        {
          name: "判定阈值 6.5",
          type: "line",
          markLine: {
            silent: true,
            symbol: "none",
            label: { color: "#9ca3af" },
            lineStyle: { color: "#4a5568", type: "dashed" },
            data: [
              { xAxis: 6.5, label: { formatter: "看好阈值 6.5" } },
              { xAxis: 5.0, label: { formatter: "中性 5.0" } },
              { xAxis: 4.0, label: { formatter: "Veto 上限 4.0" } },
              { yAxis: 0, label: { formatter: "0%" } },
            ],
          },
          data: [],
        },
      ],
      legend: {
        data: ["正常", "Veto"],
        textStyle: { color: "#9ca3af" },
        top: 10,
      },
    };
  }, [items, horizon, mode]);

  return (
    <div className="min-h-screen bg-white text-gray-800 p-6">
      <div className="max-w-6xl mx-auto">
        {/* 顶栏 */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <Link href="/" className="text-sm text-gray-500 hover:text-gray-700 mb-1 inline-block">← 返回首页</Link>
            <h1 className="text-2xl font-bold text-gray-900">回测验证 · Claude 8D 评分有效性</h1>
            <p className="text-xs text-gray-500 mt-1">
              评估新框架综合分与实际股价表现的相关性 · Spearman 秩相关 / Top-Bottom Alpha / Veto 命中率
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* 时间窗口选择 */}
            <div className="flex items-center gap-1 text-xs">
              <span className="text-gray-500 mr-1">N 日:</span>
              {HORIZONS.map((h) => (
                <button
                  key={h}
                  onClick={() => setHorizon(h)}
                  className={clsx(
                    "px-2 py-1 rounded transition-colors",
                    horizon === h
                      ? "bg-[#58a6ff] text-gray-900"
                      : "bg-gray-100 text-gray-600 hover:text-gray-800"
                  )}
                >
                  {h}d
                </button>
              ))}
            </div>
            {/* mode 切换 */}
            <div className="flex items-center gap-1 text-xs">
              {MODES.map((m) => (
                <button
                  key={m.v}
                  onClick={() => setMode(m.v)}
                  title={m.hint}
                  className={clsx(
                    "px-2 py-1 rounded transition-colors",
                    mode === m.v
                      ? "bg-[#26a69a] text-gray-900"
                      : "bg-gray-100 text-gray-600 hover:text-gray-800"
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 汇总指标卡 */}
        {summary && summary.sample_size > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <MetricCard
              label="样本量"
              value={summary.sample_size}
              hint={`${horizon} 日 · ${MODES.find((m) => m.v === mode)?.label}`}
            />
            <MetricCard
              label="Spearman 秩相关"
              value={summary.spearman_rank_correlation?.toFixed(3) ?? "—"}
              hint={
                summary.spearman_rank_correlation == null
                  ? "样本不足"
                  : summary.spearman_rank_correlation > 0.7
                  ? "强正相关 ✓"
                  : summary.spearman_rank_correlation > 0.4
                  ? "中等相关"
                  : "弱相关"
              }
              valueColor={
                (summary.spearman_rank_correlation ?? 0) > 0.7
                  ? "text-[#ef5350]"
                  : (summary.spearman_rank_correlation ?? 0) > 0.4
                  ? "text-yellow-400"
                  : "text-[#26a69a]"
              }
            />
            <MetricCard
              label="Top-Bottom Alpha"
              value={
                summary.alpha_top_minus_bottom_pct != null
                  ? `${summary.alpha_top_minus_bottom_pct >= 0 ? "+" : ""}${summary.alpha_top_minus_bottom_pct.toFixed(2)}%`
                  : "—"
              }
              hint={
                summary.top_third_avg_return_pct != null && summary.bottom_third_avg_return_pct != null
                  ? `Top1/3 ${summary.top_third_avg_return_pct.toFixed(1)}% vs Bot1/3 ${summary.bottom_third_avg_return_pct.toFixed(1)}%`
                  : "高分股 vs 低分股平均收益差"
              }
              valueColor={(summary.alpha_top_minus_bottom_pct ?? 0) > 0 ? "text-[#ef5350]" : "text-[#26a69a]"}
            />
            <MetricCard
              label="Veto 命中"
              value={
                summary.veto_sample_count > 0 && summary.veto_avg_return_pct != null
                  ? `${summary.veto_avg_return_pct >= 0 ? "+" : ""}${summary.veto_avg_return_pct.toFixed(2)}%`
                  : `${summary.veto_sample_count} / ${summary.veto_sample_count + summary.non_veto_sample_count}`
              }
              hint={
                summary.non_veto_avg_return_pct != null
                  ? `Veto 组 vs 非 Veto 组 ${summary.non_veto_avg_return_pct.toFixed(1)}%`
                  : "Veto 触发样本数"
              }
              valueColor={
                summary.veto_avg_return_pct != null && summary.non_veto_avg_return_pct != null &&
                  summary.veto_avg_return_pct < summary.non_veto_avg_return_pct
                  ? "text-[#26a69a]"
                  : "text-gray-700"
              }
            />
          </div>
        )}

        {/* 散点图 */}
        <div className="bg-[#f6f8fa] border border-gray-200 rounded-lg p-4 mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            评分 vs 涨幅散点图
            <span className="text-xs text-gray-500 ml-2">理想:右上密集(高分→高涨幅)/ 左下密集(低分→低涨幅)</span>
          </h2>
          {loadingItems ? (
            <p className="text-gray-500 text-sm py-12 text-center">加载中...</p>
          ) : items.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-gray-500 text-sm mb-2">⚠ 当前模式样本量为 0</p>
              <p className="text-xs text-gray-400">
                {mode === "prediction"
                  ? "预测模式需要历史评分(评分日 + N 日 ≤ 今天),建议:切换到事后印证模式 / 等待评分老化"
                  : "事后印证需要评分日前 N 日的 K 线,可能数据不足"}
              </p>
            </div>
          ) : (
            <ReactECharts option={scatterOption} style={{ height: 480 }} theme="dark" />
          )}
        </div>

        {/* 数据明细表 */}
        {items.length > 0 && (
          <div className="bg-[#f6f8fa] border border-gray-200 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 flex justify-between items-center">
              <h2 className="text-sm font-semibold text-gray-700">数据明细</h2>
              <span className="text-xs text-gray-500">{items.length} 条</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#f0f3f6] text-gray-500 text-xs">
                  <tr>
                    <th className="px-3 py-2 text-left">代码</th>
                    <th className="px-3 py-2 text-left">名称</th>
                    <th className="px-3 py-2 text-right">综合分</th>
                    <th className="px-3 py-2 text-left">标签</th>
                    <th className="px-3 py-2 text-right">基准价</th>
                    <th className="px-3 py-2 text-right">目标价</th>
                    <th className="px-3 py-2 text-right">{horizon}日涨幅</th>
                    <th className="px-3 py-2 text-left">D1-D8</th>
                    <th className="px-3 py-2 text-left">评分日</th>
                  </tr>
                </thead>
                <tbody>
                  {items
                    .slice()
                    .sort((a, b) => b.claude_overall_score - a.claude_overall_score)
                    .map((it) => (
                      <tr
                        key={it.report_id}
                        className={clsx(
                          "border-t border-gray-200 hover:bg-[#f0f3f6]/50",
                          it.veto_triggered && "bg-red-50",
                        )}
                      >
                        <td className="px-3 py-2 font-mono text-xs">
                          <Link href={`/stocks/${it.code}`} className="text-[#58a6ff] hover:underline">
                            {it.code}
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-gray-700">
                          {it.name}
                          {it.veto_triggered && <span className="text-red-400 text-xs ml-1" title={it.veto_reason ?? ""}>⚠</span>}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums font-bold text-base">
                          <span className={clsx(
                            it.claude_overall_score >= 6.5 ? "text-[#ef5350]"
                              : it.claude_overall_score >= 5 ? "text-yellow-400"
                              : "text-[#26a69a]"
                          )}>
                            {it.claude_overall_score.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-600">{it.claude_overall_label ?? "—"}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-gray-600">¥{it.base_price.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-gray-600">¥{it.target_price.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right tabular-nums font-medium">
                          <span className={it.return_pct >= 0 ? "text-[#ef5350]" : "text-[#26a69a]"}>
                            {it.return_pct >= 0 ? "+" : ""}{it.return_pct.toFixed(2)}%
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-500 tabular-nums whitespace-nowrap">
                          {[
                            it.industry_score, it.disruption_score, it.moat_score, it.valuation_score,
                            it.performance_score, it.narrative_score, it.financial_score, it.governance_score,
                          ].map((s, i) => (
                            <span key={i} className={clsx("inline-block w-5 text-center", s == null ? "text-gray-300" : "text-gray-600")}>
                              {s ?? "—"}
                            </span>
                          ))}
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-500">{it.score_date}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <p className="text-xs text-gray-400 mt-4">
          ⚠ 事后印证用于在样本量不足时验证框架"识别度";严格预测验证需要积累历史评分(等待 30+ 天 + 多只股票)。
        </p>
      </div>
    </div>
  );
}

function MetricCard({
  label, value, hint, valueColor = "text-gray-800",
}: {
  label: string; value: string | number; hint?: string; valueColor?: string;
}) {
  return (
    <div className="bg-[#f6f8fa] border border-gray-200 rounded-lg p-3">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={clsx("text-2xl font-bold tabular-nums", valueColor)}>{value}</p>
      {hint && <p className="text-xs text-gray-400 mt-1 leading-tight">{hint}</p>}
    </div>
  );
}
