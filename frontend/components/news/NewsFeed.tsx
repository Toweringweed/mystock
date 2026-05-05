"use client";

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
}

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
          <p className="text-xs text-gray-800 leading-snug pr-5">{item.title}</p>
          {item.summary && (
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{item.summary}</p>
          )}
          <p className="text-xs text-gray-400 mt-1">
            {item.source} · {formatDate(item.published_at)}
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
