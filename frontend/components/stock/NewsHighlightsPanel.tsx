"use client";

import Link from "next/link";
import useSWR from "swr";
import { clsx } from "clsx";
import { api } from "@/lib/api/client";

interface NewsHighlight {
  id: number;
  title: string;
  summary: string | null;
  source: string;
  published_at: string | null;
  importance_score: number | null;
  urgency: "urgent" | "important" | "info" | null;
  catalyst_type: string | null;
  catalyst_summary: string | null;
  key_risks: string | null;
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

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
  });
}

export function NewsHighlightsPanel({ code }: { code: string }) {
  // 拉该股近 14 天 importance 排序前 10 条 — 复用 GET /news/{code}
  const { data, isLoading } = useSWR<NewsHighlight[]>(
    `news-highlights-${code}`,
    () => api.get<NewsHighlight[]>(`/news/${code}?limit=15`),
  );

  if (isLoading) {
    return <p className="text-xs text-gray-400">加载中...</p>;
  }

  // 优先显示有 catalyst_summary 或 key_risks 的(L1.5 已分析过)+ 重要度排序
  const highlights = (data ?? [])
    .filter((n) => n.catalyst_summary || n.key_risks || (n.importance_score ?? 0) >= 0.4)
    .slice(0, 6);

  // 按催化剂类型聚合 — 给每类显示最近一条
  const byCatalyst = new Map<string, NewsHighlight>();
  for (const n of highlights) {
    const ct = n.catalyst_type ?? "other";
    if (!byCatalyst.has(ct)) byCatalyst.set(ct, n);
  }

  // 关键风险聚合(从所有 key_risks 字段拆分,去重,取前 5)
  const riskSet = new Set<string>();
  for (const n of data ?? []) {
    if (!n.key_risks) continue;
    for (const r of n.key_risks.split(/\s*\/\s*/)) {
      const t = r.trim();
      if (t && t !== "暂无明显风险" && riskSet.size < 5) riskSet.add(t);
    }
  }
  const risks = Array.from(riskSet);

  if (highlights.length === 0 && risks.length === 0) {
    return <p className="text-xs text-gray-400">近期无重要催化剂资讯</p>;
  }

  return (
    <div className="space-y-3 text-xs">
      {/* 催化剂分组 */}
      {byCatalyst.size > 0 && (
        <div className="space-y-2">
          <div className="text-gray-500 font-medium flex items-center gap-1.5">
            🎯 近期催化剂
            <span className="text-[10px] text-gray-400 font-normal">
              · {byCatalyst.size} 类 / 近 14 天
            </span>
          </div>
          <div className="space-y-1.5">
            {Array.from(byCatalyst.entries()).map(([ct, n]) => {
              const label = CATALYST_LABEL[ct] ?? ct;
              const color = CATALYST_COLOR[ct] ?? CATALYST_COLOR.other;
              return (
                <div
                  key={ct}
                  className="border-l-2 border-gray-200 hover:border-[#58a6ff] pl-2 py-1 group transition-colors"
                >
                  <div className="flex items-start gap-1.5 mb-0.5">
                    <span className={clsx("inline-block px-1.5 py-0 rounded border text-[10px] shrink-0", color)}>
                      {label}
                    </span>
                    <span className="text-[10px] text-gray-400 shrink-0">{fmtDate(n.published_at)}</span>
                    {(n.urgency === "urgent" || n.urgency === "important") && (
                      <span className={clsx(
                        "text-[10px] shrink-0",
                        n.urgency === "urgent" ? "text-red-500" : "text-orange-500"
                      )}>
                        {n.urgency === "urgent" ? "🚨" : "⚡"}
                      </span>
                    )}
                  </div>
                  <Link
                    href={`/news/${n.id}`}
                    className="text-gray-800 hover:text-[#58a6ff] leading-snug line-clamp-2 block"
                  >
                    {n.title}
                  </Link>
                  {n.catalyst_summary && (
                    <p className="text-gray-600 mt-1 leading-relaxed line-clamp-2">
                      {n.catalyst_summary}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 关键风险聚合 */}
      {risks.length > 0 && (
        <div className="space-y-1.5 pt-2 border-t border-gray-200">
          <div className="text-gray-500 font-medium flex items-center gap-1.5">
            ⚠️ 关键风险
            <span className="text-[10px] text-gray-400 font-normal">
              · {risks.length} 条 / 资讯聚合
            </span>
          </div>
          <ul className="space-y-1 list-none">
            {risks.map((r, i) => (
              <li
                key={i}
                className="text-gray-700 leading-relaxed pl-3 relative before:content-['•'] before:absolute before:left-0 before:text-[#ef5350]"
              >
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
