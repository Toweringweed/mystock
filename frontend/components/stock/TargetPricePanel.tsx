"use client";

import useSWR from "swr";
import clsx from "clsx";
import { targetPriceApi, TargetPriceRealtime } from "@/lib/api/target_price";

const fmt = (v: string | number | null | undefined, decimals = 2): string => {
  if (v == null) return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (Number.isNaN(n)) return "—";
  return n.toFixed(decimals);
};

const fmtPct = (v: string | number | null, withSign = true): string => {
  if (v == null) return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (Number.isNaN(n)) return "—";
  return `${n > 0 && withSign ? "+" : ""}${n.toFixed(2)}%`;
};

const FRESHNESS_BADGE = {
  fresh:  { color: "bg-[#26a69a]/15 text-[#26a69a] border-[#26a69a]/40", icon: "🟢", label: "Fresh" },
  recent: { color: "bg-yellow-500/10 text-yellow-500 border-yellow-500/30", icon: "🟡", label: "Recent" },
  aging:  { color: "bg-orange-500/15 text-orange-400 border-orange-500/40", icon: "🟠", label: "Aging" },
  stale:  { color: "bg-red-700/20 text-red-400 border-red-600/40", icon: "🔴", label: "Stale" },
  none:   { color: "bg-gray-200 text-gray-500 border-gray-300", icon: "⚪", label: "无覆盖" },
} as const;

export function TargetPricePanel({ code }: { code: string }) {
  const { data, isLoading, error, mutate } = useSWR<TargetPriceRealtime>(
    ["target-price-realtime", code],
    () => targetPriceApi.forStock(code),
    { revalidateOnFocus: false }
  );

  if (isLoading) return <p className="text-xs text-gray-400">加载中...</p>;
  if (error || !data) return <p className="text-xs text-gray-400">暂无数据</p>;

  const upside = data.upside_pct ? Number(data.upside_pct) : null;
  const finalScore = data.final_score ? Number(data.final_score) : null;
  const totalBonus = data.total_bonus_pct ? Number(data.total_bonus_pct) : 0;
  const fresh = FRESHNESS_BADGE[data.freshness_status ?? "none"];
  const items = data.institution_breakdown?.items ?? [];

  // 主信号颜色(基于上行空间)
  const upsideColor = upside == null ? "text-gray-600"
    : upside > 15 ? "text-[#ef5350]"
    : upside > 5 ? "text-[#ef5350]/80"
    : upside > -5 ? "text-yellow-400"
    : "text-[#26a69a]";

  // 目标价
  const tpWeighted = data.avg_target_weighted ? Number(data.avg_target_weighted) : null;
  const currentPrice = data.current_price ? Number(data.current_price) : null;

  // 没有覆盖时
  if (data.freshness_status === "none" || items.length === 0) {
    return (
      <div className="rounded-lg border border-gray-300 bg-gray-100/30 p-4">
        <p className="text-sm text-gray-600">⚪ 暂无机构目标价覆盖</p>
        <p className="text-xs text-gray-400 mt-1">不建议仅基于辅助维度做决策,等待机构覆盖</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ━━━━━━━━━━ 顶部摘要(主决策信号)━━━━━━━━━━ */}
      <div className={clsx(
        "rounded-lg border p-4 flex items-stretch gap-4",
        upside != null && upside > 5 ? "bg-[#ef5350]/5 border-[#ef5350]/30"
        : upside != null && upside < -5 ? "bg-[#26a69a]/5 border-[#26a69a]/30"
        : "bg-gray-100/30 border-gray-300"
      )}>
        {/* 左:大字上行空间 */}
        <div className="flex flex-col items-center justify-center px-3 border-r border-gray-300 min-w-[120px]">
          <span className="text-xs text-gray-500 uppercase tracking-wide">上行空间</span>
          <span className={clsx("text-3xl font-bold tabular-nums", upsideColor)}>
            {fmtPct(upside)}
          </span>
          <span className={clsx("text-[10px] mt-1 px-2 py-0.5 rounded border", fresh.color)}>
            {fresh.icon} {fresh.label}
            {data.days_since_latest != null && ` (${data.days_since_latest}d)`}
          </span>
        </div>

        {/* 中:加权目标 vs 当前 */}
        <div className="flex-1 grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs text-gray-500 mb-0.5">当前价</p>
            <p className="text-xl font-bold text-gray-800 tabular-nums">¥{fmt(currentPrice)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-0.5">加权目标价</p>
            <p className="text-xl font-bold text-gray-800 tabular-nums">¥{fmt(tpWeighted)}</p>
            <p className="text-[10px] text-gray-400">
              {data.institution_breakdown?.reports_in_weight_window ?? data.research_count_30d}{" "}
              家加权 · {data.institution_breakdown?.weight_window_days ?? 30}d
              <span className="ml-1">
                (近 30d {data.research_count_30d} / 90d {data.research_count_90d} 家)
              </span>
            </p>
          </div>
        </div>

        {/* 右:综合分 + 加成徽章 */}
        <div className="flex flex-col items-center justify-center px-3 border-l border-gray-300 min-w-[120px]">
          {data.veto_triggered ? (
            <>
              <span className="text-2xl font-bold text-red-400">⚠ VETO</span>
              <span className="text-[10px] text-red-400 mt-1">{data.veto_reason}</span>
            </>
          ) : (
            <>
              <span className="text-xs text-gray-500 uppercase tracking-wide">综合分</span>
              <span className={clsx("text-3xl font-bold tabular-nums", upsideColor)}>
                {fmt(finalScore, 1)}
              </span>
              <div className="flex flex-wrap gap-1 mt-1 justify-center">
                {data.has_consensus && (
                  <span className="text-[10px] bg-[#58a6ff]/10 border border-[#58a6ff]/30 text-[#58a6ff] px-1.5 py-0.5 rounded">
                    +20% 一致
                  </span>
                )}
                {data.upgrade_count_30d >= 3 && (
                  <span className="text-[10px] bg-[#ef5350]/10 border border-[#ef5350]/30 text-[#ef5350] px-1.5 py-0.5 rounded">
                    +40% {data.upgrade_count_30d}家上修
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 时效提示 — 2026-05 调优:不再做乘法衰减,stale 直接置空主信号 */}
      {data.freshness_status === "stale" && (
        <div className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-700">
          🔴 最新研报距今 {data.days_since_latest} 天 — 30d 内无新研报,主决策信号置空。建议等待新研报发布或谨慎参考。
        </div>
      )}
      {data.freshness_status === "aging" && (
        <div className="rounded border border-orange-500/40 bg-orange-500/10 px-3 py-2 text-xs text-orange-700">
          ⚠️ 最新研报距今 {data.days_since_latest} 天 — 信号有效但仍建议关注新研报。
        </div>
      )}

      {/* ━━━━━━━━━━ 各机构具体预测(透明展示)━━━━━━━━━━ */}
      <div className="bg-[#f6f8fa] border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-4 py-2 border-b border-gray-200 flex items-center justify-between">
          <h4 className="text-xs font-semibold text-gray-700">各机构预测明细 ({items.length})</h4>
          <button
            onClick={() => targetPriceApi.forStock(code, true).then(() => mutate())}
            className="text-[10px] text-gray-500 hover:text-gray-700 transition-colors"
          >
            🔄 重算
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-[#f0f3f6] text-gray-500">
              <tr>
                <th className="px-2 py-1.5 text-left">机构</th>
                <th className="px-2 py-1.5 text-center">权重</th>
                <th className="px-2 py-1.5 text-left">日期</th>
                <th className="px-2 py-1.5 text-center">评级</th>
                <th className="px-2 py-1.5 text-right">目标价</th>
                <th className="px-2 py-1.5 text-right">EPS 26</th>
                <th className="px-2 py-1.5 text-right">PE 26</th>
                <th className="px-2 py-1.5 text-right">EPS 27</th>
                <th className="px-2 py-1.5 text-right">PE 27</th>
                <th className="px-2 py-1.5 text-center">时效</th>
                <th className="px-2 py-1.5 text-center">原文</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, idx) => {
                const isHighWeight = it.weight >= 1.4;
                const ratingColor =
                  it.rating?.includes("买入") || it.rating?.includes("增持") || it.rating?.includes("推荐")
                    ? "text-[#ef5350]"
                    : it.rating?.includes("减持") || it.rating?.includes("卖出")
                    ? "text-[#26a69a]"
                    : "text-gray-600";
                const freshIcon = it.freshness_days <= 7 ? "🟢" : it.freshness_days <= 15 ? "🟡" : it.freshness_days <= 30 ? "🟠" : "🔴";
                return (
                  <tr key={idx} className={clsx(
                    "border-t border-gray-200 hover:bg-[#f0f3f6]/40",
                    isHighWeight && "bg-[#58a6ff]/5"
                  )}>
                    <td className="px-2 py-1.5">
                      <span className={clsx("font-medium", isHighWeight && "text-[#58a6ff]")}>
                        {it.institution}
                      </span>
                      {it.is_foreign && (
                        <span className="ml-1 text-[9px] text-purple-400">外资</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <span className={clsx(
                        "tabular-nums",
                        isHighWeight ? "font-bold text-[#58a6ff]" : "text-gray-600"
                      )}>
                        {it.weight.toFixed(2)}
                        {isHighWeight && <span className="ml-0.5">⭐</span>}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-gray-500">{it.report_date}</td>
                    <td className={clsx("px-2 py-1.5 text-center", ratingColor)}>
                      {it.rating ?? "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums font-medium text-gray-800">
                      ¥{it.target_price.toFixed(2)}
                      {it.target_derived && (
                        <span className="ml-1 text-[9px] text-gray-400" title="EPS×PE 推算">📐</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-gray-600">
                      {it.eps_y1?.toFixed(2) ?? "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-gray-600">
                      {it.pe_y1 != null && it.pe_y1 > 1.5 ? it.pe_y1.toFixed(1) : "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-gray-600">
                      {it.eps_y2?.toFixed(2) ?? "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-gray-600">
                      {it.pe_y2?.toFixed(1) ?? "—"}
                    </td>
                    <td className="px-2 py-1.5 text-center text-[10px]">
                      {freshIcon} {it.freshness_days}d
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      {it.source_url ? (
                        <a
                          href={it.source_url}
                          target="_blank"
                          rel="noreferrer"
                          title="查看研报原文"
                          className="text-[#58a6ff] hover:text-[#79b8ff] transition-colors"
                        >
                          🔗
                        </a>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-[10px] text-gray-300 leading-relaxed">
        💡 v5 框架核心信号 · 加权目标价 = Σ(目标价 × 机构权重) / Σ(权重) ·
        <strong className="text-gray-500"> 自适应窗口:30 天内 ≥2 篇用 30d,否则用 60d</strong>(同机构同日 dedup);
        摩根士丹利/JPM/Citi 1.20 · 高盛 0.80 · 中金 1.00;加成:一致预期 +20%,3 家上修 +40%。
      </p>
    </div>
  );
}
