"use client";

import useSWR from "swr";
import clsx from "clsx";
import { earningsApi, EarningsSurprise } from "@/lib/api/earnings";

const fmtPct = (v: string | null, withSign = true): string => {
  if (v == null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  const sign = n > 0 && withSign ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
};

const fmtNum = (v: string | null, decimals = 2): string => {
  if (v == null) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return n.toFixed(decimals);
};

const directionStyle = (
  d: "beat" | "meet" | "miss" | null | undefined,
): { label: string; cls: string; icon: string } => {
  if (d === "beat") return { label: "超预期", cls: "bg-[#ef5350]/15 text-[#ef5350] border-[#ef5350]/40", icon: "▲" };
  if (d === "miss") return { label: "低预期", cls: "bg-[#26a69a]/15 text-[#26a69a] border-[#26a69a]/40", icon: "▼" };
  if (d === "meet") return { label: "符合预期", cls: "bg-yellow-400/15 text-yellow-400 border-yellow-400/40", icon: "≈" };
  return { label: "未评估", cls: "bg-gray-200 text-gray-500 border-gray-300", icon: "—" };
};

const returnColor = (v: string | null): string => {
  if (v == null) return "text-gray-500";
  const n = Number(v);
  if (n > 0) return "text-[#ef5350]";
  if (n < 0) return "text-[#26a69a]";
  return "text-gray-700";
};

export function EarningsTrackPanel({ code }: { code: string }) {
  const { data: surprises = [], isLoading } = useSWR<EarningsSurprise[]>(
    ["earnings-surprises", code],
    () => earningsApi.forStock(code, 8),
    { revalidateOnFocus: false },
  );

  if (isLoading) {
    return <p className="text-xs text-gray-400">加载财报追踪...</p>;
  }
  if (!surprises.length) {
    return (
      <p className="text-xs text-gray-400 leading-relaxed">
        暂无财报预期差记录。下次 Skill 分析披露季报时会自动写入(详见 SKILL.md Step 2.7)。
      </p>
    );
  }

  // 最新一期
  const latest = surprises[0];
  const dirStyle = directionStyle(latest.surprise_direction);

  return (
    <div className="space-y-3">
      {/* 最新一期亮点卡 */}
      <div className={clsx(
        "border rounded-lg p-3 flex items-stretch gap-4",
        latest.surprise_direction === "beat" ? "bg-[#ef5350]/5 border-[#ef5350]/30"
          : latest.surprise_direction === "miss" ? "bg-[#26a69a]/5 border-[#26a69a]/30"
          : "bg-yellow-400/5 border-yellow-400/30"
      )}>
        <div className="flex flex-col items-center justify-center px-3 border-r border-gray-200">
          <span className={clsx("text-xs uppercase tracking-wide", dirStyle.cls.split(" ").slice(1, 2))}>
            {latest.period}
          </span>
          <span className={clsx("text-2xl font-bold tabular-nums mt-1", dirStyle.cls.split(" ").slice(1, 2))}>
            {dirStyle.icon} {fmtPct(latest.surprise_net_profit_pct)}
          </span>
          <span className={clsx("text-xs mt-1 px-2 py-0.5 rounded border", dirStyle.cls)}>
            {dirStyle.label}
          </span>
        </div>

        <div className="flex-1 grid grid-cols-3 gap-3 text-xs">
          <div>
            <p className="text-gray-500 mb-0.5">一致预期 / 实际(净利)</p>
            <p className="text-gray-800 tabular-nums">
              {fmtNum(latest.expected_net_profit_yi)} 亿 → <span className="font-semibold">{fmtNum(latest.actual_net_profit_yi)} 亿</span>
            </p>
            {latest.expected_source && <p className="text-[10px] text-gray-400 mt-0.5">{latest.expected_source}</p>}
          </div>
          <div>
            <p className="text-gray-500 mb-0.5">同比 / 环比</p>
            <p className="text-gray-800 tabular-nums">
              <span className={returnColor(latest.actual_yoy_growth)}>{fmtPct(latest.actual_yoy_growth)}</span>
              {latest.actual_qoq_growth != null && <span className="text-gray-400 ml-2">环比 <span className={returnColor(latest.actual_qoq_growth)}>{fmtPct(latest.actual_qoq_growth)}</span></span>}
            </p>
            <p className="text-[10px] text-gray-400 mt-0.5">披露日 {latest.release_date}</p>
          </div>
          <div>
            <p className="text-gray-500 mb-0.5">披露后涨幅</p>
            <p className="text-gray-800 tabular-nums leading-tight">
              <span className="text-[10px] text-gray-400">5日 </span>
              <span className={returnColor(latest.post_release_5d_return)}>{fmtPct(latest.post_release_5d_return)}</span>
              <span className="text-gray-300 mx-1">·</span>
              <span className="text-[10px] text-gray-400">30日 </span>
              <span className={returnColor(latest.post_release_30d_return)}>{fmtPct(latest.post_release_30d_return)}</span>
            </p>
            {latest.pre_release_5d_return != null && (
              <p className="text-[10px] text-gray-400 mt-0.5">
                披露前 5日 <span className={returnColor(latest.pre_release_5d_return)}>{fmtPct(latest.pre_release_5d_return)}</span>(预期定价)
              </p>
            )}
          </div>
        </div>
      </div>

      {latest.notes && (
        <p className="text-xs text-gray-600 leading-relaxed border-l-2 border-gray-200 pl-2 italic">
          {latest.notes}
        </p>
      )}

      {/* 历史预期差表格 */}
      {surprises.length > 1 && (
        <details className="text-xs" open={surprises.length <= 4}>
          <summary className="cursor-pointer text-gray-500 hover:text-gray-700 mb-2 select-none">
            历史预期差({surprises.length} 期)
          </summary>
          <div className="overflow-x-auto border border-gray-200 rounded">
            <table className="w-full text-xs">
              <thead className="bg-[#f0f3f6] text-gray-500">
                <tr>
                  <th className="px-2 py-1.5 text-left">期间</th>
                  <th className="px-2 py-1.5 text-left">披露日</th>
                  <th className="px-2 py-1.5 text-right">预期净利</th>
                  <th className="px-2 py-1.5 text-right">实际</th>
                  <th className="px-2 py-1.5 text-right">Surprise</th>
                  <th className="px-2 py-1.5 text-center">方向</th>
                  <th className="px-2 py-1.5 text-right">前 5d</th>
                  <th className="px-2 py-1.5 text-right">后 5d</th>
                  <th className="px-2 py-1.5 text-right">后 30d</th>
                </tr>
              </thead>
              <tbody>
                {surprises.map((s) => {
                  const ds = directionStyle(s.surprise_direction);
                  return (
                    <tr key={s.id} className="border-t border-gray-200 hover:bg-[#f0f3f6]/40">
                      <td className="px-2 py-1.5 font-medium text-gray-700">{s.period}</td>
                      <td className="px-2 py-1.5 text-gray-500">{s.release_date}</td>
                      <td className="px-2 py-1.5 text-right text-gray-600 tabular-nums">{fmtNum(s.expected_net_profit_yi)}</td>
                      <td className="px-2 py-1.5 text-right text-gray-700 tabular-nums font-medium">{fmtNum(s.actual_net_profit_yi)}</td>
                      <td className={clsx("px-2 py-1.5 text-right tabular-nums", returnColor(s.surprise_net_profit_pct))}>
                        {fmtPct(s.surprise_net_profit_pct)}
                      </td>
                      <td className="px-2 py-1.5 text-center">
                        <span className={clsx("text-[10px] px-1.5 py-0.5 rounded border", ds.cls)}>
                          {ds.icon} {ds.label}
                        </span>
                      </td>
                      <td className={clsx("px-2 py-1.5 text-right tabular-nums", returnColor(s.pre_release_5d_return))}>
                        {fmtPct(s.pre_release_5d_return)}
                      </td>
                      <td className={clsx("px-2 py-1.5 text-right tabular-nums font-medium", returnColor(s.post_release_5d_return))}>
                        {fmtPct(s.post_release_5d_return)}
                      </td>
                      <td className={clsx("px-2 py-1.5 text-right tabular-nums", returnColor(s.post_release_30d_return))}>
                        {fmtPct(s.post_release_30d_return)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <p className="text-[10px] text-gray-300 leading-relaxed">
        💡 财报披露前后是估值修正关键节点。Beat 通常带来 +5-15% 跳涨,Miss 带来 -5-20% 下杀。前 5d/20d 涨幅反映市场"预期定价",后 5d/30d 涨幅反映"实际兑现 vs 预期差"。
      </p>
    </div>
  );
}
