"use client";

import useSWR from "swr";
import { clsx } from "clsx";
import { quarterlyApi, type QuarterlyFinancial } from "@/lib/api/quarterly";

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null) return "—";
  return `${v.toFixed(digits)}%`;
}

function fmtYi(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}亿`;
}

function deltaCell(curr: number | null, prev: number | null): { txt: string; cls: string } {
  if (curr == null || prev == null) return { txt: "—", cls: "text-gray-400" };
  const d = curr - prev;
  if (Math.abs(d) < 0.05) return { txt: "持平", cls: "text-gray-500" };
  const sign = d > 0 ? "+" : "";
  const cls = d > 0 ? "text-[#ef5350]" : "text-[#26a69a]";
  const arrow = d > 0 ? "↑" : "↓";
  return { txt: `${arrow}${sign}${d.toFixed(1)}pct`, cls };
}

function qoqCell(v: number | null | undefined): { txt: string; cls: string } {
  if (v == null) return { txt: "—", cls: "text-gray-400" };
  const sign = v > 0 ? "+" : "";
  const cls = v > 0 ? "text-[#ef5350]" : v < 0 ? "text-[#26a69a]" : "text-gray-500";
  return { txt: `${sign}${v.toFixed(1)}%`, cls };
}

export function MoatChangePanel({ code }: { code: string }) {
  const { data, isLoading, error } = useSWR(
    code ? ["quarterly-financials", code] : null,
    () => quarterlyApi.forStock(code, 4),
  );

  if (isLoading) {
    return <div className="text-xs text-gray-500 py-2">加载季度数据…</div>;
  }
  if (error || !data || data.length === 0) {
    return <div className="text-xs text-gray-500 py-2">暂无季度财务数据</div>;
  }

  const rows = data as QuarterlyFinancial[];
  const reversed = [...rows].reverse();  // 最新在最前

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs tabular-nums">
        <thead className="bg-[#f0f3f6] text-gray-600">
          <tr>
            <th className="px-2 py-1.5 text-left font-medium">季度</th>
            <th className="px-2 py-1.5 text-right font-medium">单季营收</th>
            <th className="px-2 py-1.5 text-right font-medium">营收环比</th>
            <th className="px-2 py-1.5 text-right font-medium">单季扣非净利</th>
            <th className="px-2 py-1.5 text-right font-medium">扣非环比</th>
            <th className="px-2 py-1.5 text-right font-medium">毛利率</th>
            <th className="px-2 py-1.5 text-right font-medium">毛利率Δ</th>
            <th className="px-2 py-1.5 text-right font-medium">ROE</th>
            <th className="px-2 py-1.5 text-right font-medium">ROE Δ</th>
          </tr>
        </thead>
        <tbody>
          {reversed.map((q, i) => {
            const prev = reversed[i + 1];
            const grossDelta = deltaCell(q.gross_margin, prev?.gross_margin ?? null);
            const roeDelta = deltaCell(q.roe, prev?.roe ?? null);
            const revQoQ = qoqCell(q.revenue_qoq);
            const dedQoQ = qoqCell(q.deducted_profit_qoq);
            return (
              <tr key={q.period_end} className="border-t border-gray-200">
                <td className="px-2 py-1.5 text-gray-700 font-medium">{q.period_label}</td>
                <td className="px-2 py-1.5 text-right text-gray-700">{fmtYi(q.single_quarter_revenue_yi)}</td>
                <td className={clsx("px-2 py-1.5 text-right", revQoQ.cls)}>{revQoQ.txt}</td>
                <td className="px-2 py-1.5 text-right text-gray-700">{fmtYi(q.single_quarter_deducted_profit_yi)}</td>
                <td className={clsx("px-2 py-1.5 text-right", dedQoQ.cls)}>{dedQoQ.txt}</td>
                <td className="px-2 py-1.5 text-right text-gray-700">{fmtPct(q.gross_margin)}</td>
                <td className={clsx("px-2 py-1.5 text-right", grossDelta.cls)}>{grossDelta.txt}</td>
                <td className="px-2 py-1.5 text-right text-gray-700">{fmtPct(q.roe)}</td>
                <td className={clsx("px-2 py-1.5 text-right", roeDelta.cls)}>{roeDelta.txt}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
