"use client";

import { useState } from "react";
import { clsx } from "clsx";
import { settingsApi, TriggerableTask } from "@/lib/api/settings";

type ActionKind = "trigger" | "test_notify" | "refresh_keywords";

interface ActionDef {
  kind: ActionKind;
  task?: TriggerableTask;
  label: string;
  hint: string;
}

const SECTIONS: { title: string; emoji: string; actions: ActionDef[] }[] = [
  {
    emoji: "📥",
    title: "数据采集",
    actions: [
      { kind: "trigger", task: "sync_stock_universe",     label: "同步股票池",     hint: "全量 A股+港股代码同步（默认每周日）" },
      { kind: "trigger", task: "refresh_watchlist_data",  label: "更新自选股数据", hint: "日 K 入库 + 技术指标 + 基本面 + 盈利预测 + v5 信号" },
      { kind: "trigger", task: "update_realtime_quotes",  label: "拉取实时快照",   hint: "强制刷新东方财富 spot 最新价，盘前/盘后也可用" },
      { kind: "trigger", task: "update_all_fundamentals", label: "更新基本面",     hint: "PE/PB/PS/ROE 全自选股刷新（限速 0.5s/股）" },
      { kind: "trigger", task: "crawl_all_sources",       label: "抓取资讯",       hint: "wsj/财联社/东财 4 个源" },
      { kind: "trigger", task: "crawl_disclosures_only",  label: "抓取财报公告",   hint: "业绩预告/快报专项" },
      { kind: "trigger", task: "update_capital_flows",    label: "拉取北上资金",   hint: "个股日度净流入 + 持股比例（A 股）" },
      { kind: "trigger", task: "update_lhb",              label: "拉取龙虎榜",     hint: "当日龙虎榜全表，过滤自选股入榜" },
      { kind: "trigger", task: "sync_calendar_events",    label: "同步披露/解禁日历", hint: "财报披露日 + 解禁日（未来 90 天窗口）" },
      { kind: "trigger", task: "update_industry_metrics", label: "提取行业景气",   hint: "NVDA + 4 大 CSP 最新 10-Q AI 提取（含 SEC 网络访问）" },
      { kind: "trigger", task: "extract_segments_for_all", label: "提取业务分部",   hint: "对所有自选股从年报「分部信息」章节做 SOTP 拆解" },
      { kind: "trigger", task: "update_profit_forecasts",  label: "刷新盈利预测",   hint: "同花顺机构一致预期(EPS/净利/分析师覆盖数)，无覆盖时降级 LLM" },
    ],
  },
  {
    emoji: "📊",
    title: "计算",
    actions: [
      { kind: "trigger", task: "calc_all_indicators",  label: "计算技术指标", hint: "MA/MACD/RSI/KDJ/BOLL + 背离 + 筹码" },
      { kind: "trigger", task: "process_pending_news", label: "处理待打分资讯", hint: "去重 + 实体匹配 + 规则打分 + LLM 评分" },
    ],
  },
  {
    emoji: "🤖",
    title: "AI 分析",
    actions: [
      { kind: "trigger", task: "run_event_detection",         label: "运行事件检测",     hint: "技术 + 估值 + 资讯 → stock_events 表" },
      { kind: "trigger", task: "generate_daily_summaries",    label: "生成 L1 每日摘要", hint: "Haiku 批量打标签（含 signal_flip 检测）" },
      { kind: "trigger", task: "generate_reports_for_events", label: "生成 L2 事件报告", hint: "Sonnet 4.6 仅给当日有事件的股" },
    ],
  },
  {
    emoji: "📢",
    title: "推送",
    actions: [
      { kind: "trigger",          task: "dispatch_event_queue",   label: "聚合推送队列", hint: "把 Redis 中堆积的 medium 事件推出去" },
      { kind: "trigger",          task: "dispatch_daily_summary", label: "推送每日摘要", hint: "汇总昨日 important+info 资讯" },
      { kind: "test_notify",                                       label: "测试推送",     hint: "构造一条假卡片，验证 webhook 配置" },
    ],
  },
  {
    emoji: "🛠️",
    title: "工具",
    actions: [
      { kind: "refresh_keywords", label: "刷新关键词缓存", hint: "自选股/别名/供应链变更后调用" },
    ],
  },
];

interface FeedbackState {
  kind: "success" | "error";
  message: string;
  ts: number;
}

export default function ManualActionsPanel() {
  const [pending, setPending] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, FeedbackState>>({});

  const actionKey = (a: ActionDef) =>
    a.kind === "trigger" ? `trigger:${a.task}` : a.kind;

  const run = async (a: ActionDef) => {
    const key = actionKey(a);
    setPending(key);
    try {
      let msg = "";
      if (a.kind === "trigger" && a.task) {
        const r = await settingsApi.triggerTask(a.task);
        msg = `${r.message}（task_id=${r.celery_task_id.slice(0, 8)}…）`;
      } else if (a.kind === "test_notify") {
        const r = await settingsApi.testNotify();
        msg = r.message;
      } else if (a.kind === "refresh_keywords") {
        const r = await settingsApi.refreshKeywords();
        msg = r.message;
      }
      setFeedback((s) => ({ ...s, [key]: { kind: "success", message: msg, ts: Date.now() } }));
    } catch (e: any) {
      setFeedback((s) => ({
        ...s,
        [key]: { kind: "error", message: e?.message ?? "操作失败", ts: Date.now() },
      }));
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="bg-[#f6f8fa] rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-gray-700">手工操作</h3>
        <span className="text-xs text-gray-400">点击立即提交，结果显示在按钮下方</span>
      </div>
      <p className="text-xs text-gray-400 mb-4">
        所有任务都是 fire-and-forget；提交后由 Celery worker 异步执行，可在后端日志查看进度
      </p>

      <div className="space-y-5">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <h4 className="text-xs font-medium text-gray-500 mb-2">
              <span className="mr-1.5">{section.emoji}</span>
              {section.title}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {section.actions.map((a) => {
                const key = actionKey(a);
                const isLoading = pending === key;
                const fb = feedback[key];
                return (
                  <div
                    key={key}
                    className="border border-gray-200 rounded-lg p-3 bg-black/50 hover:border-gray-300 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-sm text-gray-800 font-medium">{a.label}</span>
                      <button
                        onClick={() => run(a)}
                        disabled={isLoading || pending !== null}
                        className={clsx(
                          "text-xs px-2.5 py-1 rounded transition-colors shrink-0",
                          isLoading
                            ? "bg-[#58a6ff]/20 text-[#58a6ff]"
                            : "bg-[#58a6ff] text-gray-900 hover:bg-[#58a6ff]/80 disabled:opacity-30 disabled:hover:bg-[#58a6ff]"
                        )}
                      >
                        {isLoading ? "提交中…" : "运行"}
                      </button>
                    </div>
                    <p className="text-xs text-gray-400 leading-tight">{a.hint}</p>
                    {fb && (
                      <p
                        className={clsx(
                          "text-xs mt-2 break-words",
                          fb.kind === "success" ? "text-green-400" : "text-red-400"
                        )}
                      >
                        {fb.kind === "success" ? "✓ " : "✗ "}
                        {fb.message}
                      </p>
                    )}
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
