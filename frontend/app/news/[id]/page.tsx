"use client";

import Link from "next/link";
import useSWR from "swr";
import { clsx } from "clsx";
import { newsApi, type NewsDetail } from "@/lib/api/news";

const CATALYST_LABEL: Record<string, string> = {
  merger: "并购",
  earnings: "业绩",
  regulatory: "监管",
  contract: "合同",
  sanction: "制裁",
  research: "研报",
  capacity: "产能",
  other: "其他",
};

const CATALYST_COLOR: Record<string, string> = {
  sanction: "bg-red-500/15 text-red-500 border-red-500/30",
  regulatory: "bg-orange-500/15 text-orange-500 border-orange-500/30",
  merger: "bg-purple-500/15 text-purple-500 border-purple-500/30",
  earnings: "bg-[#ef5350]/15 text-[#ef5350] border-[#ef5350]/30",
  contract: "bg-[#26a69a]/15 text-[#26a69a] border-[#26a69a]/30",
  capacity: "bg-blue-500/15 text-blue-500 border-blue-500/30",
  research: "bg-[#58a6ff]/15 text-[#58a6ff] border-[#58a6ff]/30",
  other: "bg-gray-200 text-gray-600 border-gray-300",
};

const URGENCY_COLOR: Record<string, string> = {
  urgent: "bg-red-500/15 text-red-500",
  important: "bg-orange-500/15 text-orange-500",
  info: "bg-gray-200 text-gray-600",
};

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function NewsDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const newsId = Number(params.id);
  const { data, error, isLoading } = useSWR<NewsDetail>(
    `news-detail-${newsId}`,
    () => newsApi.getDetail(newsId),
  );

  if (isLoading) {
    return <div className="p-6 text-gray-500 text-sm">加载中...</div>;
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <Link href="/" className="text-sm text-[#58a6ff] hover:underline">
          ← 返回主页
        </Link>
        <div className="mt-4 text-red-500">
          {error instanceof Error ? error.message : "加载失败"}
        </div>
      </div>
    );
  }

  const catalystKey = data.catalyst_type ?? "other";
  const catalystLabel = CATALYST_LABEL[catalystKey] ?? catalystKey;
  const risks = (data.key_risks ?? "")
    .split(/\s*\/\s*/)
    .map((r) => r.trim())
    .filter(Boolean);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <Link href="/" className="text-sm text-[#58a6ff] hover:underline">
        ← 返回主页
      </Link>

      {/* 标题 + 右上角催化剂/风险 */}
      <div className="mt-4 flex items-start justify-between gap-6">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-semibold text-gray-900 leading-snug">
            {data.title}
          </h1>
          {data.original_title && data.original_title !== data.title && (
            <p className="text-sm text-gray-500 mt-2 italic">
              原文: {data.original_title}
            </p>
          )}
          <div className="flex items-center gap-3 mt-3 text-xs text-gray-500 flex-wrap">
            <span>{data.source}</span>
            <span>·</span>
            <span>{formatTime(data.published_at)}</span>
            {data.urgency && (
              <span
                className={clsx(
                  "px-1.5 py-0.5 rounded text-[11px]",
                  URGENCY_COLOR[data.urgency],
                )}
              >
                {data.urgency === "urgent"
                  ? "紧急"
                  : data.urgency === "important"
                    ? "重要"
                    : "一般"}
              </span>
            )}
            {typeof data.importance_score === "number" && (
              <span>重要度 {data.importance_score.toFixed(2)}</span>
            )}
            {data.source_url && (
              <a
                href={data.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-[#58a6ff] hover:underline"
              >
                查看原文 ↗
              </a>
            )}
          </div>
        </div>

        {/* 右上角催化剂/风险卡 */}
        <aside className="w-72 shrink-0 border border-gray-200 rounded-md p-3 bg-gray-50/40 text-xs space-y-2">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-gray-500">催化剂</span>
              <span
                className={clsx(
                  "inline-block px-1.5 py-0 rounded border text-[11px]",
                  CATALYST_COLOR[catalystKey] ?? CATALYST_COLOR.other,
                )}
              >
                {catalystLabel}
              </span>
            </div>
            {data.catalyst_summary ? (
              <p className="text-gray-700 leading-relaxed">{data.catalyst_summary}</p>
            ) : (
              <p className="text-gray-400">—</p>
            )}
          </div>
          <div className="border-t border-gray-200 pt-2">
            <div className="text-gray-500 mb-1">关键风险</div>
            {risks.length > 0 ? (
              <ul className="text-gray-700 leading-relaxed space-y-0.5 list-disc list-inside">
                {risks.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            ) : (
              <p className="text-gray-400">—</p>
            )}
          </div>
        </aside>
      </div>

      {/* 关联股票 */}
      {data.related_stocks.length > 0 && (
        <div className="mt-6 flex items-center gap-2 flex-wrap text-xs">
          <span className="text-gray-500">关联股票:</span>
          {data.related_stocks.map((s) => (
            <Link
              key={s.code}
              href={`/stocks/${s.code}`}
              className="px-2 py-0.5 border border-gray-300 rounded hover:border-[#58a6ff] hover:text-[#58a6ff] transition-colors"
            >
              {s.name} <span className="text-gray-400">{s.code}</span>
            </Link>
          ))}
        </div>
      )}

      {/* 摘要 */}
      {data.summary && (
        <div className="mt-6 border-l-2 border-[#58a6ff]/40 pl-4 py-2 bg-[#58a6ff]/5">
          <div className="text-xs text-gray-500 mb-1">摘要</div>
          <p className="text-sm text-gray-800 leading-relaxed">{data.summary}</p>
        </div>
      )}

      {/* 正文 */}
      <div className="mt-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">正文</h2>
        {data.content ? (
          <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
            {data.content}
          </div>
        ) : (
          <p className="text-gray-400 text-sm">暂无正文(可点击"查看原文"链接到原始来源)</p>
        )}
      </div>
    </div>
  );
}
