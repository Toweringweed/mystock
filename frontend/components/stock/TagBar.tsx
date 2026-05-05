"use client";

import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { clsx } from "clsx";
import {
  tagsApi,
  TAG_CATEGORY_COLOR,
  TAG_CATEGORY_LABEL,
  type StockTagRead,
  type TagCategory,
  type TagRead,
} from "@/lib/api/tags";

const COLOR_CLS: Record<string, string> = {
  blue: "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30",
  green: "bg-[#26a69a]/10 text-[#26a69a] border-[#26a69a]/30",
  yellow: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
  red: "bg-[#ef5350]/10 text-[#ef5350] border-[#ef5350]/30",
  gray: "bg-gray-100 text-gray-600 border-gray-300",
};

export function TagChip({
  tag,
  removable = false,
  onRemove,
}: {
  tag: TagRead | StockTagRead;
  removable?: boolean;
  onRemove?: () => void;
}) {
  const color = TAG_CATEGORY_COLOR[tag.category] ?? "gray";
  const isAi = "source" in tag && tag.source === "ai";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border font-medium",
        COLOR_CLS[color],
      )}
      title={`${TAG_CATEGORY_LABEL[tag.category]}${isAi ? " · AI" : ""}`}
    >
      <span>#{tag.name}</span>
      {removable && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove?.();
          }}
          className="opacity-50 hover:opacity-100 transition-opacity"
          aria-label="remove tag"
        >
          ×
        </button>
      )}
    </span>
  );
}

export function TagBar({ code }: { code: string }) {
  const { data: tags = [], isLoading } = useSWR<StockTagRead[]>(
    `tags:${code}`,
    () => tagsApi.listForStock(code),
  );
  const { data: allTags = [] } = useSWR<TagRead[]>("tags:all", tagsApi.listAll);

  const [editing, setEditing] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCat, setNewCat] = useState<TagCategory>("theme");
  const [refreshing, setRefreshing] = useState(false);

  const refreshAll = () => {
    globalMutate(`tags:${code}`);
    globalMutate("tags:all");
    globalMutate("watchlist-table");
  };

  const handleAdd = async (name: string, category: TagCategory) => {
    const trimmed = name.trim().replace(/^#+/, "");
    if (!trimmed) return;
    try {
      await tagsApi.attach(code, trimmed, category);
      setNewName("");
      refreshAll();
    } catch (e) {
      console.error("attach tag failed", e);
    }
  };

  const handleRemove = async (tagId: number) => {
    try {
      await tagsApi.detach(code, tagId);
      refreshAll();
    } catch (e) {
      console.error("detach tag failed", e);
    }
  };

  const handleAiRefresh = async () => {
    setRefreshing(true);
    try {
      await tagsApi.refresh(code);
      // 后端异步生成，等几秒后重新拉
      setTimeout(refreshAll, 8000);
    } catch (e) {
      console.error("refresh tags failed", e);
    } finally {
      setTimeout(() => setRefreshing(false), 8000);
    }
  };

  // 候选：未挂在当前股票上的已存在标签
  const usedIds = new Set(tags.map((t) => t.id));
  const suggestions = allTags
    .filter((t) => !usedIds.has(t.id))
    .filter((t) => !newName || t.name.includes(newName))
    .slice(0, 12);

  return (
    <div className="flex items-start gap-2 flex-wrap">
      <div className="flex items-center gap-1.5 flex-wrap flex-1 min-w-0">
        {isLoading && (
          <span className="text-xs text-gray-500">加载标签中…</span>
        )}
        {!isLoading && tags.length === 0 && !editing && (
          <span className="text-xs text-gray-400">暂无标签</span>
        )}
        {tags.map((t) => (
          <TagChip
            key={t.id}
            tag={t}
            removable={editing}
            onRemove={() => handleRemove(t.id)}
          />
        ))}
        {editing && (
          <div className="inline-flex items-center gap-1 bg-white border border-gray-300 rounded px-2 py-0.5 text-xs">
            <select
              value={newCat}
              onChange={(e) => setNewCat(e.target.value as TagCategory)}
              className="bg-transparent text-gray-700 outline-none cursor-pointer"
            >
              <option value="theme">主题</option>
              <option value="industry_chain">产业链</option>
              <option value="attribute">属性</option>
            </select>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAdd(newName, newCat);
              }}
              placeholder="标签名"
              className="bg-transparent text-gray-800 outline-none w-20 placeholder-gray-600"
              maxLength={16}
            />
            <button
              onClick={() => handleAdd(newName, newCat)}
              className="text-[#58a6ff] hover:text-[#79b8ff]"
            >
              +
            </button>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={() => setEditing((v) => !v)}
          className={clsx(
            "text-xs px-2 py-0.5 rounded border transition-colors",
            editing
              ? "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30"
              : "bg-gray-100 text-gray-600 border-gray-300 hover:text-gray-800",
          )}
        >
          {editing ? "完成" : "编辑"}
        </button>
        <button
          onClick={handleAiRefresh}
          disabled={refreshing}
          className="text-xs px-2 py-0.5 rounded border bg-gray-100 text-gray-600 border-gray-300 hover:text-gray-800 disabled:opacity-50"
          title="AI 试生成（覆盖 ai 来源标签，保留手动标签；准确率有限）"
        >
          {refreshing ? "生成中…" : "AI 试生成"}
        </button>
      </div>
      {editing && suggestions.length > 0 && (
        <div className="w-full mt-1 flex flex-wrap gap-1">
          <span className="text-[10px] text-gray-400 self-center">已有：</span>
          {suggestions.map((t) => (
            <button
              key={t.id}
              onClick={() => handleAdd(t.name, t.category)}
              className={clsx(
                "text-xs px-2 py-0.5 rounded border opacity-60 hover:opacity-100",
                COLOR_CLS[TAG_CATEGORY_COLOR[t.category]] ?? COLOR_CLS.gray,
              )}
            >
              +#{t.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
