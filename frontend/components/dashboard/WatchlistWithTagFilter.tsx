"use client";

import { useMemo, useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { clsx } from "clsx";
import { WatchlistTable } from "@/components/stock/WatchlistTable";
import {
  tagsApi,
  TAG_CATEGORY_COLOR,
  TAG_CATEGORY_LABEL,
  type TagCategory,
  type TagRead,
} from "@/lib/api/tags";

const COLOR_CLS: Record<string, string> = {
  blue: "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30",
  green: "bg-[#26a69a]/10 text-[#26a69a] border-[#26a69a]/30",
  yellow: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  gray: "bg-gray-100 text-gray-600 border-gray-300",
};

const CATEGORIES: TagCategory[] = ["theme", "industry_chain", "attribute"];

export function WatchlistWithTagFilter() {
  const { data: allTags = [], mutate: mutateTags } = useSWR<TagRead[]>(
    "tags:all",
    tagsApi.listAll,
  );
  const [selected, setSelected] = useState<number[]>([]);
  const [editing, setEditing] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [coreOnly, setCoreOnly] = useState(false);

  const handleDelete = async (tag: TagRead) => {
    if (!confirm(`确认删除标签 #${tag.name} ?\n该标签会从所有自选股上解绑,操作不可恢复。`)) {
      return;
    }
    setDeletingId(tag.id);
    try {
      await tagsApi.deleteGlobal(tag.id);
      setSelected((prev) => prev.filter((id) => id !== tag.id));
      await mutateTags();
      // 同步刷新自选股列表(标签已变化)
      globalMutate("watchlist-table");
    } catch (e) {
      alert(`删除失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setDeletingId(null);
    }
  };

  const grouped = useMemo(() => {
    const m: Record<TagCategory, TagRead[]> = {
      theme: [],
      industry_chain: [],
      attribute: [],
    };
    for (const t of allTags) {
      if (CATEGORIES.includes(t.category)) m[t.category].push(t);
    }
    return m;
  }, [allTags]);

  const toggle = (id: number) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
        {allTags.length > 0 && (
          <>
        <span className="text-gray-500 shrink-0">标签筛选：</span>
          {CATEGORIES.map((cat) =>
            grouped[cat].length === 0 ? null : (
              <div
                key={cat}
                className="flex items-center gap-1 flex-wrap"
              >
                <span className="text-[10px] text-gray-400">
                  {TAG_CATEGORY_LABEL[cat]}
                </span>
                {grouped[cat].map((t) => {
                  const active = selected.includes(t.id);
                  const color = TAG_CATEGORY_COLOR[t.category];
                  const isDeleting = deletingId === t.id;
                  return (
                    <span
                      key={t.id}
                      className={clsx(
                        "inline-flex items-center rounded border transition-all overflow-hidden",
                        active
                          ? COLOR_CLS[color]
                          : "bg-transparent text-gray-500 border-gray-300",
                        isDeleting && "opacity-50",
                      )}
                    >
                      <button
                        onClick={() => toggle(t.id)}
                        disabled={isDeleting}
                        className={clsx(
                          "px-2 py-0.5",
                          !active && "hover:text-gray-700",
                        )}
                      >
                        #{t.name}
                      </button>
                      {editing && (
                        <button
                          onClick={() => handleDelete(t)}
                          disabled={isDeleting}
                          title={`删除标签 #${t.name}(从所有自选股上解绑)`}
                          className="px-1.5 border-l border-current/30 text-[#ef5350] hover:bg-[#ef5350]/15"
                        >
                          ×
                        </button>
                      )}
                    </span>
                  );
                })}
              </div>
            ),
          )}
          </>
        )}
        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={() => setCoreOnly((v) => !v)}
            title="只显示标记为核心的自选股"
            className={clsx(
              "transition-colors flex items-center gap-1",
              coreOnly ? "text-yellow-500" : "text-gray-500 hover:text-yellow-400",
            )}
          >
            {coreOnly ? "★" : "☆"} 仅核心
          </button>
          {allTags.length > 0 && (
            <>
              <button
                onClick={() => setEditing((v) => !v)}
                className={clsx(
                  "transition-colors",
                  editing ? "text-[#ef5350]" : "text-gray-500 hover:text-gray-700",
                )}
              >
                {editing ? "完成" : "管理标签"}
              </button>
              {selected.length > 0 && (
                <button
                  onClick={() => setSelected([])}
                  className="text-gray-500 hover:text-gray-700"
                >
                  清除（{selected.length}）
                </button>
              )}
            </>
          )}
        </div>
      </div>
      <WatchlistTable filterTagIds={selected} coreOnly={coreOnly} />
    </div>
  );
}
