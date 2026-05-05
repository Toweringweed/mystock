"use client";

import useSWR from "swr";
import clsx from "clsx";
import { estimateRevisionsApi, EstimateRevision } from "@/lib/api/earnings";

const fmtPct = (v: string | null): string => {
  if (v == null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
};

const fmtNum = (v: string | null, decimals = 2): string => {
  if (v == null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return n.toFixed(decimals);
};

const dirColor = (d: "up" | "flat" | "down" | null): string => {
  if (d === "up") return "text-[#ef5350]";
  if (d === "down") return "text-[#26a69a]";
  return "text-yellow-400";
};

const dirIcon = (d: "up" | "flat" | "down" | null): string => {
  if (d === "up") return "▲";
  if (d === "down") return "▼";
  if (d === "flat") return "→";
  return "—";
};

export function EstimateRevisionsPanel({ code }: { code: string }) {
  const { data: revisions = [], isLoading } = useSWR<EstimateRevision[]>(
    ["estimate-revisions", code],
    () => estimateRevisionsApi.forStock(code, 2026, 12),
    { revalidateOnFocus: false },
  );

  if (isLoading) return <p className="text-xs text-gray-400">加载共识修正...</p>;

  if (!revisions.length) {
    return (
      <p className="text-xs text-gray-400 leading-relaxed">
        暂无机构共识修正快照。Skill 分析时若发现机构月度上调/下调,会自动写入 estimate_revisions 表。
      </p>
    );
  }

  // 按日期升序绘制趋势(最早的在左)
  const sorted = [...revisions].sort(
    (a, b) => new Date(a.revision_date).getTime() - new Date(b.revision_date).getTime(),
  );

  // 计算 EPS 变化范围 - 用于绘制简化条形图
  const epsValues = sorted.map((r) => Number(r.consensus_eps)).filter((v) => !Number.isNaN(v));
  const minEps = epsValues.length ? Math.min(...epsValues) : 0;
  const maxEps = epsValues.length ? Math.max(...epsValues) : 1;
  const range = maxEps - minEps || 1;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">
          2026E 一致预期 EPS 趋势(<span className="text-gray-600">{sorted.length}</span> 个快照)
        </p>
        {sorted.length >= 2 && (
          <p className="text-xs text-gray-500">
            首末变化:{" "}
            <span className={clsx(
              "font-semibold tabular-nums",
              Number(sorted[sorted.length - 1].consensus_eps) > Number(sorted[0].consensus_eps)
                ? "text-[#ef5350]" : "text-[#26a69a]"
            )}>
              {fmtNum(sorted[0].consensus_eps)} → {fmtNum(sorted[sorted.length - 1].consensus_eps)}
            </span>
          </p>
        )}
      </div>

      {/* 条形图 - 简化 EPS 趋势 */}
      <div className="flex items-end gap-1 h-20 border-b border-gray-200 pb-1">
        {sorted.map((r, i) => {
          const eps = Number(r.consensus_eps);
          const height = epsValues.length && !Number.isNaN(eps)
            ? Math.max(8, ((eps - minEps) / range) * 64 + 8)
            : 8;
          return (
            <div key={r.id} className="flex-1 flex flex-col items-center group" title={`${r.revision_date}: EPS=${fmtNum(r.consensus_eps)}, ${fmtPct(r.eps_revision_pct)}`}>
              <span className="text-[9px] text-gray-400 mb-0.5 group-hover:text-gray-600">
                {fmtNum(r.consensus_eps, 2)}
              </span>
              <div
                style={{ height: `${height}px` }}
                className={clsx(
                  "w-full transition-all rounded-t",
                  r.revision_direction === "up" ? "bg-[#ef5350]/60 group-hover:bg-[#ef5350]"
                    : r.revision_direction === "down" ? "bg-[#26a69a]/60 group-hover:bg-[#26a69a]"
                    : "bg-yellow-400/40 group-hover:bg-yellow-400/70"
                )}
              />
              <span className="text-[9px] text-gray-300 mt-0.5">
                {r.revision_date.slice(5)}
              </span>
            </div>
          );
        })}
      </div>

      {/* 明细表 */}
      <details className="text-xs">
        <summary className="cursor-pointer text-gray-500 hover:text-gray-700 select-none">
          明细(覆盖机构 / 目标价 / EPS / 净利预测 / 月度变化)
        </summary>
        <div className="overflow-x-auto border border-gray-200 rounded mt-2">
          <table className="w-full text-xs">
            <thead className="bg-[#f0f3f6] text-gray-500">
              <tr>
                <th className="px-2 py-1.5 text-left">快照日</th>
                <th className="px-2 py-1.5 text-right">EPS</th>
                <th className="px-2 py-1.5 text-right">净利(亿)</th>
                <th className="px-2 py-1.5 text-right">目标价</th>
                <th className="px-2 py-1.5 text-right">机构数</th>
                <th className="px-2 py-1.5 text-right">EPS 变化</th>
                <th className="px-2 py-1.5 text-right">目标价变化</th>
                <th className="px-2 py-1.5 text-center">方向</th>
              </tr>
            </thead>
            <tbody>
              {[...revisions].map((r) => (
                <tr key={r.id} className="border-t border-gray-200 hover:bg-[#f0f3f6]/40">
                  <td className="px-2 py-1.5 text-gray-600">{r.revision_date}</td>
                  <td className="px-2 py-1.5 text-right text-gray-700 tabular-nums">{fmtNum(r.consensus_eps)}</td>
                  <td className="px-2 py-1.5 text-right text-gray-700 tabular-nums">{fmtNum(r.consensus_net_profit_yi)}</td>
                  <td className="px-2 py-1.5 text-right text-gray-700 tabular-nums">{fmtNum(r.consensus_target_price)}</td>
                  <td className="px-2 py-1.5 text-right text-gray-500 tabular-nums">{r.institution_count ?? "—"}</td>
                  <td className={clsx("px-2 py-1.5 text-right tabular-nums", dirColor(r.revision_direction))}>
                    {fmtPct(r.eps_revision_pct)}
                  </td>
                  <td className={clsx("px-2 py-1.5 text-right tabular-nums", dirColor(r.revision_direction))}>
                    {fmtPct(r.target_price_revision_pct)}
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <span className={clsx("font-bold", dirColor(r.revision_direction))}>
                      {dirIcon(r.revision_direction)} {r.revision_direction ?? "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <p className="text-[10px] text-gray-300 leading-relaxed">
        💡 机构 EPS 共识月度上调 = 业绩超预期或叙事强化的领先信号;连续下调则反之。条形高度=EPS 绝对值,颜色=月度变化方向。
      </p>
    </div>
  );
}
