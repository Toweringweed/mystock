"use client";

import { useState } from "react";
import { clsx } from "clsx";
import { settingsApi, TriggerableTask } from "@/lib/api/settings";

interface HeroAction {
  task: TriggerableTask;
  emoji: string;
  title: string;
  desc: string;
  warn?: string;
  cls: string;
}

const HERO_ACTIONS: HeroAction[] = [
  {
    task: "refresh_all_watchlist",
    emoji: "🔄",
    title: "一键回填全部 watchlist",
    desc: "首次配置 / 数据全空时点。包含:日 K + 技术指标 + 基本面 + 一致预期 + 北上资金 + 龙虎榜 + 财报日历 + 业务分部 + 行业景气 + 公告 + 研报 + 事件检测",
    warn: "约 12 个子任务并行,~10-30 分钟跑完",
    cls: "border-[#58a6ff]/40 hover:bg-[#58a6ff]/8 hover:border-[#58a6ff]",
  },
  {
    task: "daily_after_close_routine",
    emoji: "🌅",
    title: "盘后日常更新",
    desc: "每个交易日 16:00 后点(或等 cron)。更新今日:日 K/技术指标 + 行情 + 北上 + 龙虎 + 资讯 + 公告 + 事件",
    warn: "约 7 个子任务,~3-8 分钟",
    cls: "border-[#26a69a]/40 hover:bg-[#26a69a]/8 hover:border-[#26a69a]",
  },
  {
    task: "monthly_universe_refresh",
    emoji: "📊",
    title: "全市场月度同步",
    desc: "每月一次或 schema 升级时点。同步全 A 股代码池 + 历史 K 线扩展 + NVDA/CSP 行业景气 10-Q 抽取",
    warn: "约 3 个子任务,~30 分钟-2 小时",
    cls: "border-purple-500/40 hover:bg-purple-500/8 hover:border-purple-500",
  },
];

export default function HeroActionsPanel() {
  const [pending, setPending] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, { ok: boolean; msg: string }>>({});

  const run = async (task: TriggerableTask) => {
    setPending(task);
    try {
      const r = await settingsApi.triggerTask(task);
      setFeedback((s) => ({
        ...s,
        [task]: { ok: true, msg: `${r.message}(${r.celery_task_id.slice(0, 8)}…)` },
      }));
    } catch (e) {
      setFeedback((s) => ({
        ...s,
        [task]: { ok: false, msg: e instanceof Error ? e.message : "失败" },
      }));
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="bg-[#f6f8fa] rounded-xl border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-1">⚡ 主要操作</h3>
      <p className="text-xs text-gray-400 mb-4">90% 场景用这 3 个就够了</p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {HERO_ACTIONS.map((a) => {
          const fb = feedback[a.task];
          const isPending = pending === a.task;
          return (
            <button
              key={a.task}
              onClick={() => run(a.task)}
              disabled={isPending}
              className={clsx(
                "relative text-left border rounded-lg p-4 transition-colors disabled:opacity-50",
                a.cls,
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-2xl">{a.emoji}</span>
                <span className="font-semibold text-gray-800 text-sm leading-tight">
                  {a.title}
                </span>
              </div>
              <p className="text-xs text-gray-500 leading-relaxed mb-2">{a.desc}</p>
              {a.warn && (
                <p className="text-[11px] text-gray-400 mb-2">⏱ {a.warn}</p>
              )}
              {isPending && (
                <p className="text-xs text-[#58a6ff]">提交中...</p>
              )}
              {fb && (
                <p className={clsx("text-xs", fb.ok ? "text-[#26a69a]" : "text-red-400")}>
                  {fb.ok ? "✓" : "✗"} {fb.msg}
                </p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
