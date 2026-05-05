"use client";

import useSWR from "swr";
import { clsx } from "clsx";
import { settingsApi, DataStatusItem } from "@/lib/api/settings";

const GROUP_EMOJI: Record<string, string> = {
  "行情": "📈",
  "财务": "💰",
  "资金": "💵",
  "事件": "🔔",
  "资讯": "📰",
  "AI": "🤖",
  "行业景气": "🌐",
};

// 各表的"过期"阈值（小时）。超过即标黄；超过 3 倍标红。
const STALE_HOURS_THRESHOLD: Record<string, number> = {
  // 行情类应每日更新
  stock_daily_kline: 24 * 3,           // 周末 + 假期容忍
  stock_technical_indicators: 24 * 3,
  divergence_signals: 24 * 7,          // 新增背离不一定每天有
  // 财务/估值更新慢
  stock_fundamentals: 24 * 7,
  profit_forecasts: 24 * 14,
  business_segments: 24 * 365,         // 年报数据
  supply_chains: 24 * 365,
  // 资金应日度
  stock_capital_flows: 24 * 5,
  stock_lhb: 24 * 7,
  insider_trades: 24 * 30,
  // 事件 / 日历
  stock_events: 24 * 30,
  calendar_events: 24 * 90,
  // 资讯
  industry_news: 24 * 1,               // 新闻应每小时刷
  news_stock_relations: 24 * 1,
  // AI
  daily_summaries: 24 * 3,             // 工作日盘后更新
  analysis_reports: 24 * 7,
  // 行业景气季度
  industry_metrics: 24 * 100,
};


function FreshnessBadge({ item }: { item: DataStatusItem }) {
  if (item.rows === 0) {
    return (
      <span className="text-xs px-1.5 py-0.5 bg-gray-200 text-gray-500 rounded">空</span>
    );
  }
  const stale = item.stale_hours ?? null;
  if (stale === null) {
    return null;
  }

  // 未来事件（如 calendar_events 的财报日/解禁日）：stale_hours 是负数
  if (stale < 0) {
    const daysAhead = Math.abs(Math.round(stale / 24));
    return (
      <span className="text-xs px-1.5 py-0.5 bg-blue-500/15 text-blue-400 border border-blue-500/30 rounded">
        未来 {daysAhead}d
      </span>
    );
  }

  const threshold = STALE_HOURS_THRESHOLD[item.table] ?? 24 * 3;
  if (stale > threshold * 3) {
    return (
      <span className="text-xs px-1.5 py-0.5 bg-red-500/15 text-red-400 border border-red-500/30 rounded">
        过期 {Math.round(stale / 24)}d
      </span>
    );
  }
  if (stale > threshold) {
    return (
      <span className="text-xs px-1.5 py-0.5 bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 rounded">
        滞后 {stale < 48 ? `${Math.round(stale)}h` : `${Math.round(stale / 24)}d`}
      </span>
    );
  }
  return (
    <span className="text-xs px-1.5 py-0.5 bg-green-500/15 text-green-400 border border-green-500/30 rounded">
      新鲜
    </span>
  );
}


export default function DataStatusPanel() {
  const { data, mutate, isLoading } = useSWR("data-status", settingsApi.dataStatus, {
    refreshInterval: 60_000,  // 1 分钟自动刷
  });

  const grouped = (data ?? []).reduce<Record<string, DataStatusItem[]>>((acc, item) => {
    (acc[item.group] ??= []).push(item);
    return acc;
  }, {});

  // 总览数字
  const total = data ?? [];
  const empty = total.filter((t) => t.rows === 0).length;
  const stale = total.filter((t) => {
    const thr = STALE_HOURS_THRESHOLD[t.table] ?? 24 * 3;
    return t.stale_hours !== null && t.stale_hours > thr;
  }).length;
  const healthy = total.length - empty - stale;

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
            <span className="text-green-400">{healthy} 健康</span>{" · "}
            <span className="text-yellow-400">{stale} 滞后</span>{" · "}
            <span className="text-red-400">{empty} 空</span>
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
              {items.map((item) => (
                <div
                  key={item.table}
                  className={clsx(
                    "border rounded-lg p-2.5 bg-black/50 transition-colors",
                    item.rows === 0
                      ? "border-gray-200/80"
                      : "border-gray-200 hover:border-gray-300"
                  )}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <code className="text-xs text-gray-600 font-mono truncate">
                      {item.table}
                    </code>
                    <FreshnessBadge item={item} />
                  </div>
                  <div className="text-xs text-gray-500 leading-tight">
                    {item.hint}
                  </div>
                  <div className="text-xs mt-1.5 text-gray-700 font-mono">
                    {item.rows.toLocaleString()} 行
                    {item.stocks !== null && (
                      <span className="text-gray-400"> · {item.stocks} 股</span>
                    )}
                    {item.latest && (
                      <span className="text-gray-400">
                        {" · "}
                        {String(item.latest).slice(0, 10)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
