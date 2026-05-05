"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import useSWR from "swr";
import clsx from "clsx";
import { earningsApi, EarningsSurprise, UpcomingEarnings } from "@/lib/api/earnings";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const fmtPct = (v: string | number | null, withSign = true): string => {
  if (v == null) return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (Number.isNaN(n)) return "—";
  return `${n > 0 && withSign ? "+" : ""}${n.toFixed(2)}%`;
};

const directionStyle = (d: "beat" | "meet" | "miss" | null | undefined) => {
  if (d === "beat") return { label: "超预期", cls: "bg-[#ef5350]/15 text-[#ef5350] border-[#ef5350]/40", icon: "▲" };
  if (d === "miss") return { label: "低预期", cls: "bg-[#26a69a]/15 text-[#26a69a] border-[#26a69a]/40", icon: "▼" };
  if (d === "meet") return { label: "符合预期", cls: "bg-yellow-400/15 text-yellow-400 border-yellow-400/40", icon: "≈" };
  return { label: "—", cls: "bg-gray-200 text-gray-500 border-gray-300", icon: "—" };
};

const returnColor = (v: string | number | null): string => {
  if (v == null) return "text-gray-500";
  const n = typeof v === "string" ? Number(v) : v;
  if (n > 0) return "text-[#ef5350]";
  if (n < 0) return "text-[#26a69a]";
  return "text-gray-700";
};

export default function EarningsPage() {
  const [filterDirection, setFilterDirection] = useState<"all" | "beat" | "meet" | "miss">("all");
  const [days, setDays] = useState<number>(60);

  const { data: upcoming = [] } = useSWR<UpcomingEarnings[]>(
    ["earnings-upcoming", 60],
    () => earningsApi.upcoming(60, false),
    { revalidateOnFocus: false },
  );

  const { data: recent = [] } = useSWR<EarningsSurprise[]>(
    ["earnings-recent", days, filterDirection],
    () => earningsApi.recent(days, filterDirection === "all" ? undefined : filterDirection),
    { revalidateOnFocus: false },
  );

  // 散点图:Surprise % vs 后 5 日涨幅
  const scatterOption = useMemo(() => {
    const beat = recent.filter((r) => r.surprise_direction === "beat" && r.post_release_5d_return != null && r.surprise_net_profit_pct != null);
    const meet = recent.filter((r) => r.surprise_direction === "meet" && r.post_release_5d_return != null && r.surprise_net_profit_pct != null);
    const miss = recent.filter((r) => r.surprise_direction === "miss" && r.post_release_5d_return != null && r.surprise_net_profit_pct != null);
    const toData = (arr: EarningsSurprise[]) =>
      arr.map((r) => [Number(r.surprise_net_profit_pct), Number(r.post_release_5d_return), r]);

    return {
      backgroundColor: "transparent",
      grid: { top: 50, right: 30, bottom: 50, left: 60 },
      tooltip: {
        backgroundColor: "#1c2333",
        borderColor: "#4a5568",
        textStyle: { color: "#e5e7eb" },
        formatter: (p: { value: [number, number, EarningsSurprise] }) => {
          const r = p.value[2];
          return `<div style="font-size:12px">
            <b>${r.period}</b> · stock_id=${r.stock_id}<br/>
            披露日: ${r.release_date}<br/>
            一致预期净利: ${r.expected_net_profit_yi ?? "—"} 亿<br/>
            实际净利: ${r.actual_net_profit_yi ?? "—"} 亿<br/>
            <b>Surprise: ${fmtPct(r.surprise_net_profit_pct)}</b><br/>
            披露后 5 日涨幅: <span style="color:${Number(r.post_release_5d_return) >= 0 ? "#ef5350" : "#26a69a"}">${fmtPct(r.post_release_5d_return)}</span><br/>
            披露后 30 日涨幅: ${fmtPct(r.post_release_30d_return)}
          </div>`;
        },
      },
      xAxis: {
        name: "Surprise %(净利)",
        nameLocation: "middle", nameGap: 30,
        nameTextStyle: { color: "#9ca3af" },
        type: "value",
        axisLabel: { color: "#9ca3af", formatter: "{value}%" },
        splitLine: { lineStyle: { color: "#374151", type: "dashed" } },
      },
      yAxis: {
        name: "披露后 5 日涨幅 %",
        nameLocation: "middle", nameGap: 45,
        nameTextStyle: { color: "#9ca3af" },
        type: "value",
        axisLabel: { color: "#9ca3af", formatter: "{value}%" },
        splitLine: { lineStyle: { color: "#374151", type: "dashed" } },
      },
      series: [
        { name: "超预期 (▲)", type: "scatter", symbolSize: 14, data: toData(beat), itemStyle: { color: "#ef5350", opacity: 0.85 } },
        { name: "符合 (≈)", type: "scatter", symbolSize: 12, data: toData(meet), itemStyle: { color: "#facc15", opacity: 0.7 } },
        { name: "低预期 (▼)", type: "scatter", symbolSize: 14, data: toData(miss), itemStyle: { color: "#26a69a", opacity: 0.85 } },
        {
          name: "参考线",
          type: "line",
          markLine: {
            silent: true, symbol: "none",
            label: { color: "#9ca3af" },
            lineStyle: { color: "#4a5568", type: "dashed" },
            data: [
              { xAxis: 5, label: { formatter: "+5% beat 阈值" } },
              { xAxis: -5, label: { formatter: "-5% miss 阈值" } },
              { yAxis: 0, label: { formatter: "0% (持平)" } },
            ],
          },
          data: [],
        },
      ],
      legend: { data: ["超预期 (▲)", "符合 (≈)", "低预期 (▼)"], textStyle: { color: "#9ca3af" }, top: 10 },
    };
  }, [recent]);

  // 统计
  const stats = useMemo(() => {
    const beats = recent.filter((r) => r.surprise_direction === "beat");
    const misses = recent.filter((r) => r.surprise_direction === "miss");
    const meets = recent.filter((r) => r.surprise_direction === "meet");
    const avgPost5d = (arr: EarningsSurprise[]) => {
      const valid = arr.map((r) => r.post_release_5d_return).filter((v): v is string => v != null).map(Number);
      return valid.length ? +(valid.reduce((a, b) => a + b, 0) / valid.length).toFixed(2) : null;
    };
    return {
      total: recent.length,
      beats: beats.length,
      misses: misses.length,
      meets: meets.length,
      avg_beat_post5d: avgPost5d(beats),
      avg_miss_post5d: avgPost5d(misses),
    };
  }, [recent]);

  return (
    <div className="min-h-screen bg-white text-gray-800 p-6">
      <div className="max-w-6xl mx-auto">
        {/* 顶栏 */}
        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <Link href="/" className="text-sm text-gray-500 hover:text-gray-700 mb-1 inline-block">← 返回首页</Link>
            <h1 className="text-2xl font-bold text-gray-900">财报预期差中心</h1>
            <p className="text-xs text-gray-500 mt-1">
              一致预期 vs 实际 vs 股价反应 · 量化"超预期 → 跳涨 / 低预期 → 跳水"alpha
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="text-xs bg-[#f0f3f6] border border-gray-300 rounded px-2 py-1 text-gray-700"
            >
              <option value={30}>近 30 天</option>
              <option value={60}>近 60 天</option>
              <option value={90}>近 90 天</option>
              <option value={180}>近 180 天</option>
            </select>
            {(["all", "beat", "meet", "miss"] as const).map((d) => (
              <button
                key={d}
                onClick={() => setFilterDirection(d)}
                className={clsx(
                  "text-xs px-2 py-1 rounded",
                  filterDirection === d ? "bg-[#58a6ff] text-gray-900" : "bg-gray-100 text-gray-600 hover:text-gray-800"
                )}
              >
                {d === "all" ? "全部" : d === "beat" ? "▲ 超" : d === "miss" ? "▼ 低" : "≈ 符"}
              </button>
            ))}
          </div>
        </div>

        {/* 统计卡 */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatCard label="样本量" value={stats.total} hint={`近 ${days} 天披露`} />
          <StatCard
            label="超预期 / 符合 / 低预期"
            value={`${stats.beats} / ${stats.meets} / ${stats.misses}`}
            hint="数量分布"
          />
          <StatCard
            label="超预期组 后 5 日涨幅"
            value={stats.avg_beat_post5d != null ? `${stats.avg_beat_post5d >= 0 ? "+" : ""}${stats.avg_beat_post5d}%` : "—"}
            hint="平均收益"
            valueColor={stats.avg_beat_post5d != null && stats.avg_beat_post5d > 0 ? "text-[#ef5350]" : ""}
          />
          <StatCard
            label="低预期组 后 5 日涨幅"
            value={stats.avg_miss_post5d != null ? `${stats.avg_miss_post5d >= 0 ? "+" : ""}${stats.avg_miss_post5d}%` : "—"}
            hint="平均收益"
            valueColor={stats.avg_miss_post5d != null && stats.avg_miss_post5d < 0 ? "text-[#26a69a]" : ""}
          />
        </div>

        {/* 即将披露日历 */}
        <div className="bg-[#f6f8fa] border border-gray-200 rounded-lg p-4 mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            ⏰ 即将披露日历({upcoming.length})
            <span className="text-xs text-gray-500 ml-2 font-normal">未来 60 天</span>
          </h2>
          {upcoming.length === 0 ? (
            <p className="text-xs text-gray-500">暂无未来披露安排(可在管理后台添加 calendar_events)</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {upcoming.slice(0, 12).map((u) => (
                <Link
                  key={u.stock_id}
                  href={`/stocks/${u.code}`}
                  className={clsx(
                    "flex items-center justify-between gap-2 p-2 border rounded hover:bg-[#f0f3f6]/50 transition-colors",
                    u.days_to_release <= 7
                      ? "bg-orange-500/5 border-orange-500/30"
                      : "border-gray-200"
                  )}
                >
                  <div>
                    <p className="text-sm text-gray-800 font-medium">{u.name}</p>
                    <p className="text-xs text-gray-500 tabular-nums">{u.code} · {u.expected_release_date}</p>
                  </div>
                  <div className="text-right">
                    <p className={clsx(
                      "text-base font-bold tabular-nums",
                      u.days_to_release <= 7 ? "text-orange-400" : "text-gray-700"
                    )}>
                      {u.days_to_release}d
                    </p>
                    {u.last_surprise_direction && (
                      <p className="text-[10px] text-gray-500">
                        上次 {directionStyle(u.last_surprise_direction).icon} {fmtPct(u.last_surprise_pct)}
                      </p>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* 散点图 */}
        <div className="bg-[#f6f8fa] border border-gray-200 rounded-lg p-4 mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Surprise % vs 后 5 日涨幅
            <span className="text-xs text-gray-500 ml-2 font-normal">
              理想:右上(超预期+涨)/ 左下(低预期+跌)集中
            </span>
          </h2>
          {recent.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-gray-500 text-sm mb-2">当前筛选条件下无样本</p>
              <p className="text-xs text-gray-400 leading-relaxed max-w-lg mx-auto">
                💡 想增加样本量?三种方式:<br />
                ① <Link href="/" className="text-[#58a6ff] hover:underline">在首页对自选股做 Skill 分析</Link>(自动写入)<br />
                ② 等待 Celery 后台任务每日扫描 <code className="text-[#58a6ff]">stock_fundamentals</code> 自动套填<br />
                ③ 手动 POST <code className="text-[#58a6ff]">/api/v1/stocks/&#123;code&#125;/earnings-surprises</code>(详见 Skill Step 2.7)
              </p>
            </div>
          ) : (
            <ReactECharts option={scatterOption} style={{ height: 420 }} theme="dark" />
          )}
        </div>

        {/* 明细表 */}
        {recent.length > 0 && (
          <div className="bg-[#f6f8fa] border border-gray-200 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-700">明细 · {recent.length} 条</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-[#f0f3f6] text-gray-500">
                  <tr>
                    <th className="px-3 py-2 text-left">股票</th>
                    <th className="px-3 py-2 text-left">期间</th>
                    <th className="px-3 py-2 text-left">披露日</th>
                    <th className="px-3 py-2 text-right">预期净利</th>
                    <th className="px-3 py-2 text-right">实际净利</th>
                    <th className="px-3 py-2 text-right">Surprise</th>
                    <th className="px-3 py-2 text-center">方向</th>
                    <th className="px-3 py-2 text-right">前 5d</th>
                    <th className="px-3 py-2 text-right">后 5d</th>
                    <th className="px-3 py-2 text-right">后 30d</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((r) => {
                    const ds = directionStyle(r.surprise_direction);
                    return (
                      <tr key={r.id} className="border-t border-gray-200 hover:bg-[#f0f3f6]/40">
                        <td className="px-3 py-2 text-gray-700 tabular-nums">{r.stock_id}</td>
                        <td className="px-3 py-2 font-medium text-gray-700">{r.period}</td>
                        <td className="px-3 py-2 text-gray-500">{r.release_date}</td>
                        <td className="px-3 py-2 text-right text-gray-600 tabular-nums">{r.expected_net_profit_yi ?? "—"}</td>
                        <td className="px-3 py-2 text-right text-gray-700 tabular-nums font-medium">{r.actual_net_profit_yi ?? "—"}</td>
                        <td className={clsx("px-3 py-2 text-right tabular-nums font-bold", returnColor(r.surprise_net_profit_pct))}>
                          {fmtPct(r.surprise_net_profit_pct)}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <span className={clsx("text-[10px] px-1.5 py-0.5 rounded border", ds.cls)}>
                            {ds.icon} {ds.label}
                          </span>
                        </td>
                        <td className={clsx("px-3 py-2 text-right tabular-nums", returnColor(r.pre_release_5d_return))}>
                          {fmtPct(r.pre_release_5d_return)}
                        </td>
                        <td className={clsx("px-3 py-2 text-right tabular-nums font-medium", returnColor(r.post_release_5d_return))}>
                          {fmtPct(r.post_release_5d_return)}
                        </td>
                        <td className={clsx("px-3 py-2 text-right tabular-nums", returnColor(r.post_release_30d_return))}>
                          {fmtPct(r.post_release_30d_return)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <p className="text-[10px] text-gray-300 mt-4 leading-relaxed">
          💡 财报披露前后是估值修正的关键节点。市场已 price-in 一致预期,实际 vs 预期的差(Surprise %)直接驱动股价跳动。
          理想模式:超预期组 后 5 日平均涨 +5-15%,低预期组 后 5 日平均跌 -5-20%。
        </p>
      </div>
    </div>
  );
}

function StatCard({ label, value, hint, valueColor = "text-gray-800" }: {
  label: string; value: string | number; hint?: string; valueColor?: string;
}) {
  return (
    <div className="bg-[#f6f8fa] border border-gray-200 rounded-lg p-3">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={clsx("text-2xl font-bold tabular-nums", valueColor)}>{value}</p>
      {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
    </div>
  );
}
