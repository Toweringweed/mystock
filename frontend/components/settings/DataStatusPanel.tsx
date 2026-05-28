"use client";

import { useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { settingsApi, DataStatusItem, TriggerableTask } from "@/lib/api/settings";

const GROUP_EMOJI: Record<string, string> = {
  "行情": "📈",
  "财务": "💰",
  "资金": "💵",
  "事件": "🔔",
  "资讯": "📰",
  "AI": "🤖",
  "行业景气": "🌐",
};

const STATUS_BADGE = {
  healthy: { label: "✓ 健康", cls: "bg-green-500/15 text-green-500 border-green-500/30" },
  stale: { label: "⚠ 滞后", cls: "bg-yellow-500/15 text-yellow-500 border-yellow-500/30" },
  empty: { label: "✗ 空", cls: "bg-red-500/15 text-red-400 border-red-500/30" },
  not_implemented: { label: "未实现", cls: "bg-gray-200 text-gray-500 border-gray-300" },
} as const;

export default function DataStatusPanel() {
  const { data, mutate, isLoading } = useSWR("data-status", settingsApi.dataStatus, {
    refreshInterval: 60_000,
  });
  const [triggering, setTriggering] = useState<string | null>(null);

  const handleTrigger = async (task: string) => {
    setTriggering(task);
    try {
      await settingsApi.triggerTask(task as TriggerableTask);
      // 30 秒后自动刷一次,看 task 跑完没
      setTimeout(() => mutate(), 30_000);
    } catch (e) {
      alert(`触发失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setTriggering(null);
    }
  };

  const grouped = (data ?? []).reduce<Record<string, DataStatusItem[]>>((acc, item) => {
    (acc[item.group] ??= []).push(item);
    return acc;
  }, {});

  // 总览数字 — 用后端 status 字段
  const total = data ?? [];
  const healthy = total.filter((t) => t.status === "healthy").length;
  const stale = total.filter((t) => t.status === "stale").length;
  const empty = total.filter((t) => t.status === "empty").length;
  const notImpl = total.filter((t) => t.status === "not_implemented").length;

  return (
    <div className="bg-[#f6f8fa] rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-gray-700">数据状态</h3>
        <button
          onClick={() => mutate()}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          ↻ 刷新
        </button>
      </div>
      <p className="text-xs text-gray-400 mb-4">
        {isLoading ? (
          "加载中…"
        ) : (
          <>
            共 {total.length} 张表 ·{" "}
            <span className="text-green-500">✓ {healthy}</span>{" · "}
            <span className="text-yellow-500">⚠ {stale}</span>{" · "}
            <span className="text-red-400">✗ {empty}</span>
            {notImpl > 0 && <> · <span className="text-gray-500">— {notImpl} 未实现</span></>}
          </>
        )}
      </p>

      <div className="space-y-4">
        {Object.entries(grouped).map(([group, items]) => (
          <div key={group}>
            <h4 className="text-xs font-medium text-gray-500 mb-2">
              <span className="mr-1.5">{GROUP_EMOJI[group] ?? "·"}</span>
              {group}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {items.map((item) => {
                const status = item.status ?? "healthy";
                const badge = STATUS_BADGE[status];
                const canTrigger = item.trigger_task && status !== "not_implemented" && status !== "healthy";
                const isTriggering = triggering === item.trigger_task;
                return (
                  <div
                    key={item.table}
                    className={clsx(
                      "border rounded-lg p-2.5 bg-black/50 transition-colors",
                      status === "empty" && "border-red-500/30",
                      status === "stale" && "border-yellow-500/30",
                      status === "healthy" && "border-gray-200 hover:border-gray-300",
                      status === "not_implemented" && "border-gray-300 opacity-70",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <code className="text-xs text-gray-600 font-mono truncate">
                        {item.table}
                      </code>
                      <span className={clsx("text-[10px] px-1.5 py-0.5 border rounded", badge.cls)}>
                        {badge.label}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 leading-tight">{item.hint}</div>
                    <div className="text-xs mt-1.5 text-gray-700 font-mono flex items-center justify-between gap-2">
                      <span>
                        {item.rows.toLocaleString()} 行
                        {item.stocks !== null && (
                          <span className="text-gray-400"> · {item.stocks} 股</span>
                        )}
                        {item.latest && (
                          <span className="text-gray-400">
                            {" · "}{String(item.latest).slice(0, 10)}
                          </span>
                        )}
                      </span>
                      {canTrigger && (
                        <button
                          onClick={() => handleTrigger(item.trigger_task!)}
                          disabled={isTriggering}
                          title={`重触发 ${item.trigger_task}`}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-[#58a6ff]/10 text-[#58a6ff] border border-[#58a6ff]/30 hover:bg-[#58a6ff]/20 disabled:opacity-50"
                        >
                          {isTriggering ? "…" : "↻ 重拉"}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
