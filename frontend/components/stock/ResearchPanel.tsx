"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { clsx } from "clsx";
import { researchApi, ratingColor, type ResearchReportRead } from "@/lib/api/research";

const RATING_CLS: Record<string, string> = {
  red: "bg-[#ef5350]/10 text-[#ef5350] border-[#ef5350]/30",
  yellow: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  gray: "bg-gray-100 text-gray-600 border-gray-300",
  blue: "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30",
  green: "bg-[#26a69a]/10 text-[#26a69a] border-[#26a69a]/30",
};

function fmt(v: number | null | undefined, dp = 2): string {
  return v == null ? "—" : v.toFixed(dp);
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  try {
    return s.slice(0, 10);
  } catch {
    return "—";
  }
}

export function ResearchPanel({ code }: { code: string }) {
  const { data, isLoading, mutate } = useSWR<ResearchReportRead[]>(
    `research:${code}`,
    () => researchApi.listForStock(code, 20),
  );
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await researchApi.refresh(code);
      setTimeout(() => {
        mutate();
        setRefreshing(false);
      }, 90_000);
    } catch (e) {
      console.error("research refresh failed", e);
      setRefreshing(false);
    }
  };

  const items = data ?? [];
  const yearBase = items.find((r) => r.forecast_year_base)?.forecast_year_base;

  return (
    <div className="bg-[#f6f8fa] rounded-xl border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <span className="w-1 h-4 bg-[#58a6ff] rounded-full shrink-0" />
          券商研报
          {items.length > 0 && (
            <span className="text-xs text-gray-400 font-normal">
              · 最近 {items.length} 篇
            </span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          <Link
            href={`/research?code=${encodeURIComponent(code)}`}
            className="text-xs px-2 py-1 rounded border bg-gray-100 text-gray-600 border-gray-300 hover:text-gray-800"
          >
            全部研报 →
          </Link>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="text-xs px-2 py-1 rounded border bg-gray-100 text-gray-600 border-gray-300 hover:text-gray-800 disabled:opacity-50"
          >
            {refreshing ? "抓取中…" : "刷新"}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="text-xs text-gray-500 py-4">加载中…</div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="text-xs text-gray-400 py-4">暂无研报数据。点击"刷新"触发抓取（约 1~2 分钟）</div>
      )}

      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-gray-200">
                <th className="text-left font-normal py-1.5 px-2 w-24">日期</th>
                <th className="text-left font-normal py-1.5 px-2 w-28">机构</th>
                <th className="text-left font-normal py-1.5 px-2 w-16">评级</th>
                <th className="text-left font-normal py-1.5 px-2">报告标题</th>
                <th className="text-right font-normal py-1.5 px-2 whitespace-nowrap">
                  目标价
                </th>
                <th
                  className="text-right font-normal py-1.5 px-2 whitespace-nowrap"
                  colSpan={3}
                >
                  EPS 预测{yearBase ? `（${yearBase}~${yearBase + 2}）` : ""}
                </th>
                <th
                  className="text-right font-normal py-1.5 px-2 whitespace-nowrap"
                  colSpan={3}
                >
                  PE 预测
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => {
                const color = ratingColor(r.rating);
                const broker = r.broker;
                // 标题里若以 "{broker}：" 开头，去掉冗余前缀
                const cleanTitle = r.title.startsWith(`${broker}：`)
                  ? r.title.slice(broker.length + 1)
                  : r.title;
                return (
                  <tr
                    key={r.news_id}
                    className="border-b border-gray-200 hover:bg-black/[0.02]"
                  >
                    <td className="py-1.5 px-2 text-gray-500 tabular-nums">
                      {fmtDate(r.published_at)}
                    </td>
                    <td className="py-1.5 px-2 text-gray-700">{broker}</td>
                    <td className="py-1.5 px-2">
                      {r.rating ? (
                        <span
                          className={clsx(
                            "inline-block px-1.5 py-0.5 rounded border font-medium",
                            RATING_CLS[color],
                          )}
                        >
                          {r.rating}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-1.5 px-2 text-gray-800">
                      {r.pdf_url ? (
                        <a
                          href={r.pdf_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-[#58a6ff] transition-colors"
                          title="打开 PDF"
                        >
                          {cleanTitle}
                        </a>
                      ) : (
                        cleanTitle
                      )}
                    </td>
                    <td className="py-1.5 px-2 text-right text-gray-800 tabular-nums font-medium">
                      {r.target_price == null ? "—" : `¥${fmt(r.target_price)}`}
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-700 tabular-nums">
                      {fmt(r.eps_y1)}
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-600 tabular-nums">
                      {fmt(r.eps_y2)}
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-500 tabular-nums">
                      {fmt(r.eps_y3)}
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-700 tabular-nums">
                      {fmt(r.pe_y1, 1)}
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-600 tabular-nums">
                      {fmt(r.pe_y2, 1)}
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-500 tabular-nums">
                      {fmt(r.pe_y3, 1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
