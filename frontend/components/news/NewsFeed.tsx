"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api/client";
import { clsx } from "clsx";

interface NewsItem {
  id: number;
  title: string;
  summary: string | null;
  source: string;
  sentiment: "positive" | "negative" | "neutral" | null;
  published_at: string;
  catalyst_type?: string | null;
  original_title?: string | null;
}

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

const sentimentStyle = {
  positive: "border-l-[#ef5350]",
  negative: "border-l-[#26a69a]",
  neutral: "border-l-gray-700",
};

const TZ = "Asia/Shanghai";

function bjDateKey(d: Date): string {
  // YYYY-MM-DD in Beijing time, used to determine "is today"
  return d.toLocaleDateString("en-CA", { timeZone: TZ });
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const isToday = bjDateKey(d) === bjDateKey(new Date());
  const time = d.toLocaleTimeString("zh-CN", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  if (isToday) return time;
  const date = d.toLocaleDateString("zh-CN", {
    timeZone: TZ,
    month: "2-digit",
    day: "2-digit",
  });
  return `${date} ${time}`;
}

export function NewsFeed({ codes }: { codes?: string[] }) {
  const query = codes?.length ? `?codes=${codes.join(",")}` : "";
  const { data, isLoading, mutate } = useSWR(
    `news-feed${query}`,
    () => api.get<NewsItem[]>(`/news/feed${query}`),
    { refreshInterval: 5 * 60 * 1000 }
  );

  const [deletingIds, setDeletingIds] = useState<Set<number>>(new Set());

  const handleDelete = async (id: number) => {
    setDeletingIds((prev) => new Set(prev).add(id));
    try {
      await api.delete(`/news/${id}`);
      mutate((items) => items?.filter((item) => item.id !== id), false);
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  if (isLoading) return <div className="text-xs text-gray-400">加载中...</div>;

  return (
    <div className="space-y-2">
      {data?.map((item) => (
        <div
          key={item.id}
          className={clsx(
            "border-l-2 pl-3 py-1 pr-1 group relative",
            sentimentStyle[item.sentiment ?? "neutral"]
          )}
        >
          <Link
            href={`/news/${item.id}`}
            className="text-xs text-gray-800 leading-snug pr-5 hover:text-[#58a6ff] transition-colors block"
          >
            {item.title}
          </Link>
          {item.summary && (
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{item.summary}</p>
          )}
          <p className="text-xs text-gray-400 mt-1 flex items-center gap-2 flex-wrap">
            <span>{item.source} · {formatDate(item.published_at)}</span>
            {item.catalyst_type && item.catalyst_type !== "other" && (
              <span
                className={clsx(
                  "inline-block px-1.5 py-0 rounded border text-[10px]",
                  CATALYST_COLOR[item.catalyst_type] ?? CATALYST_COLOR.other,
                )}
              >
                {CATALYST_LABEL[item.catalyst_type] ?? item.catalyst_type}
              </span>
            )}
          </p>
          <button
            onClick={() => handleDelete(item.id)}
            disabled={deletingIds.has(item.id)}
            className="absolute top-1 right-0 opacity-0 group-hover:opacity-60 hover:!opacity-100 text-gray-500 hover:text-red-400 transition-all text-xs px-1 py-0.5 disabled:opacity-30"
            title="删除此资讯"
          >
            ✕
          </button>
        </div>
      ))}
      {!data?.length && <p className="text-xs text-gray-400">暂无资讯</p>}
    </div>
  );
}
