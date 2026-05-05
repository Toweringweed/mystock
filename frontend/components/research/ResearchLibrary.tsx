"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { clsx } from "clsx";
import {
  researchApi,
  ratingColor,
  type GlobalResearchReportRead,
} from "@/lib/api/research";
import { stocksApi, type StockRead } from "@/lib/api/stocks";

const RATING_CLS: Record<string, string> = {
  red: "bg-[#ef5350]/10 text-[#ef5350] border-[#ef5350]/30",
  yellow: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  gray: "bg-gray-100 text-gray-600 border-gray-300",
  blue: "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30",
  green: "bg-[#26a69a]/10 text-[#26a69a] border-[#26a69a]/30",
};

const RATINGS = ["买入", "增持", "中性", "推荐", "强烈推荐", "持有", "减持"];
const DAY_OPTIONS = [
  { value: 7, label: "近 7 天" },
  { value: 30, label: "近 30 天" },
  { value: 90, label: "近 90 天" },
  { value: 180, label: "近半年" },
];

function fmtDate(s: string | null): string {
  return s ? s.slice(0, 10) : "—";
}

function fmt(v: number | null, dp = 2): string {
  return v == null ? "—" : v.toFixed(dp);
}

function SummaryCell({ summary, contentReady }: { summary: string | null; contentReady: boolean }) {
  const [expanded, setExpanded] = useState(false);
  if (!summary) {
    return (
      <span className="text-xs text-gray-400">
        {contentReady ? "（已下载，未生成摘要）" : "（PDF 待解析）"}
      </span>
    );
  }
  const truncated = summary.length > 90 && !expanded;
  return (
    <div className="text-xs text-gray-700 leading-relaxed">
      <span>{truncated ? `${summary.slice(0, 90)}…` : summary}</span>
      {summary.length > 90 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="ml-1 text-[#58a6ff] hover:underline shrink-0"
        >
          {expanded ? "收起" : "展开"}
        </button>
      )}
    </div>
  );
}

export function ResearchLibrary({ initialCode }: { initialCode?: string | null }) {
  const [code, setCode] = useState<string>(initialCode || "");
  const [broker, setBroker] = useState<string>("");
  const [rating, setRating] = useState<string>("");
  const [days, setDays] = useState<number>(30);

  const { data: watchlist } = useSWR<StockRead[]>(
    "watchlist-stocks",
    stocksApi.watchlist,
  );
  const { data: brokers } = useSWR<string[]>(
    "research-brokers",
    () => researchApi.listBrokers(90),
  );

  const swrKey = useMemo(
    () => `research-global:${code}:${broker}:${rating}:${days}`,
    [code, broker, rating, days],
  );
  const { data, isLoading } = useSWR<GlobalResearchReportRead[]>(
    swrKey,
    () => researchApi.listGlobal({ code, broker, rating, days, limit: 200 }),
  );

  return (
    <div className="space-y-4">
      {/* 筛选区 */}
      <div className="bg-[#f6f8fa] border border-gray-200 rounded-xl p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-gray-500">股票：</span>
          <button
            onClick={() => setCode("")}
            className={clsx(
              "px-2 py-0.5 rounded border",
              !code
                ? "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30"
                : "bg-transparent text-gray-500 border-gray-300 hover:text-gray-700",
            )}
          >
            全部
          </button>
          {(watchlist ?? []).map((s) => (
            <button
              key={s.code}
              onClick={() => setCode(s.code)}
              className={clsx(
                "px-2 py-0.5 rounded border",
                code === s.code
                  ? "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30"
                  : "bg-transparent text-gray-500 border-gray-300 hover:text-gray-700",
              )}
            >
              {s.name}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
          <span className="text-gray-500">机构：</span>
          <select
            value={broker}
            onChange={(e) => setBroker(e.target.value)}
            className="bg-white border border-gray-300 rounded px-2 py-0.5 text-gray-800 outline-none"
          >
            <option value="">全部</option>
            {(brokers ?? []).map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>

          <span className="text-gray-500 ml-3">评级：</span>
          {[""].concat(RATINGS).map((r) => (
            <button
              key={r || "all"}
              onClick={() => setRating(r)}
              className={clsx(
                "px-2 py-0.5 rounded border",
                rating === r
                  ? RATING_CLS[ratingColor(r) || "gray"]
                  : "bg-transparent text-gray-500 border-gray-300 hover:text-gray-700",
              )}
            >
              {r || "全部"}
            </button>
          ))}

          <span className="text-gray-500 ml-3">范围：</span>
          {DAY_OPTIONS.map((d) => (
            <button
              key={d.value}
              onClick={() => setDays(d.value)}
              className={clsx(
                "px-2 py-0.5 rounded border",
                days === d.value
                  ? "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30"
                  : "bg-transparent text-gray-500 border-gray-300 hover:text-gray-700",
              )}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {/* 列表 */}
      <div className="bg-[#f6f8fa] border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700">
            研报列表
            <span className="text-xs text-gray-400 font-normal ml-2">
              共 {data?.length ?? 0} 篇
            </span>
          </h2>
        </div>

        {isLoading && <div className="text-xs text-gray-500 py-8 text-center">加载中…</div>}

        {!isLoading && (data?.length ?? 0) === 0 && (
          <div className="text-xs text-gray-400 py-8 text-center">无符合条件的研报</div>
        )}

        {data && data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-200">
                  <th className="text-left font-normal py-2 px-2 w-24">日期</th>
                  <th className="text-left font-normal py-2 px-2 w-28">股票</th>
                  <th className="text-left font-normal py-2 px-2 w-28">机构</th>
                  <th className="text-left font-normal py-2 px-2 w-16">评级</th>
                  <th className="text-left font-normal py-2 px-2 w-72">报告标题</th>
                  <th className="text-left font-normal py-2 px-2">AI 摘要</th>
                  <th className="text-right font-normal py-2 px-2 whitespace-nowrap" colSpan={3}>EPS 预测</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => {
                  const color = ratingColor(r.rating);
                  const broker = r.broker;
                  const cleanTitle = r.title.startsWith(`${broker}：`)
                    ? r.title.slice(broker.length + 1)
                    : r.title;
                  return (
                    <tr key={r.news_id} className="border-b border-gray-200 hover:bg-black/[0.02] align-top">
                      <td className="py-2 px-2 text-gray-500 tabular-nums whitespace-nowrap">
                        {fmtDate(r.published_at)}
                      </td>
                      <td className="py-2 px-2 whitespace-nowrap">
                        <Link
                          href={`/stocks/${r.code}`}
                          className="text-gray-800 hover:text-[#58a6ff] transition-colors"
                        >
                          {r.stock_name}
                        </Link>
                        <div className="text-[10px] text-gray-400 tabular-nums">{r.code}</div>
                      </td>
                      <td className="py-2 px-2 text-gray-700 whitespace-nowrap">{broker}</td>
                      <td className="py-2 px-2">
                        {r.rating ? (
                          <span className={clsx("inline-block px-1.5 py-0.5 rounded border font-medium", RATING_CLS[color])}>
                            {r.rating}
                          </span>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-2 px-2">
                        {r.pdf_url ? (
                          <a
                            href={r.pdf_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-gray-800 hover:text-[#58a6ff]"
                          >
                            {cleanTitle}
                          </a>
                        ) : (
                          <span className="text-gray-800">{cleanTitle}</span>
                        )}
                      </td>
                      <td className="py-2 px-2 max-w-md">
                        <SummaryCell summary={r.summary} contentReady={r.content_ready} />
                      </td>
                      <td className="py-2 px-1 text-right text-gray-700 tabular-nums whitespace-nowrap">{fmt(r.eps_y1)}</td>
                      <td className="py-2 px-1 text-right text-gray-600 tabular-nums whitespace-nowrap">{fmt(r.eps_y2)}</td>
                      <td className="py-2 px-1 text-right text-gray-500 tabular-nums whitespace-nowrap">{fmt(r.eps_y3)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
