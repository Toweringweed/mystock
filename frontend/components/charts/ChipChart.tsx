"use client";

import ReactECharts from "echarts-for-react";
import useSWR from "swr";
import { analysisApi } from "@/lib/api/analysis";

interface Props {
  code: string;
  currentPrice?: number;
}

export function ChipChart({ code, currentPrice }: Props) {
  const { data, isLoading } = useSWR(`chip-${code}`, () => analysisApi.chip(code));

  if (isLoading) return <div className="text-xs text-gray-500 py-10 text-center">计算中...</div>;
  if (!data || !data.price_ranges?.length)
    return <div className="text-xs text-gray-500 py-10 text-center">暂无筹码数据</div>;

  const price = currentPrice ?? data.avg_cost ?? 0;

  // 构建 ECharts 数据
  const barData = data.price_ranges.map((r) => ({
    value: [r.chip_pct * 100, (r.price_low + r.price_high) / 2],
    price_low: r.price_low,
    price_high: r.price_high,
    chip_pct: r.chip_pct,
  }));

  const option = {
    backgroundColor: "#0d1117",
    grid: { left: 60, right: 20, top: 10, bottom: 30 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: any) => {
        const d = params[0];
        const item = barData[d.dataIndex];
        return `价格: ${item.price_low.toFixed(2)} ~ ${item.price_high.toFixed(2)}<br/>占比: ${(item.chip_pct * 100).toFixed(3)}%`;
      },
      backgroundColor: "#161b22",
      borderColor: "#30363d",
      textStyle: { color: "#e6edf3", fontSize: 12 },
    },
    xAxis: {
      type: "value",
      name: "占比%",
      nameTextStyle: { color: "#8b949e", fontSize: 11 },
      axisLine: { lineStyle: { color: "#21262d" } },
      splitLine: { lineStyle: { color: "#21262d" } },
      axisLabel: { color: "#8b949e", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      name: "价格",
      nameTextStyle: { color: "#8b949e", fontSize: 11 },
      axisLine: { lineStyle: { color: "#21262d" } },
      splitLine: { lineStyle: { color: "#21262d" } },
      axisLabel: { color: "#8b949e", fontSize: 10 },
    },
    series: [
      {
        type: "bar",
        data: barData.map((d) => ({
          value: [d.chip_pct * 100, d.value[1]],
          itemStyle: {
            color:
              d.value[1] < price
                ? "rgba(38, 166, 154, 0.6)"  // 获利盘 绿
                : "rgba(239, 83, 80, 0.6)",   // 套牢盘 红
          },
        })),
        barWidth: "80%",
        barCategoryGap: "0%",
      },
    ],
    // 当前价格标线
    markLine: price
      ? {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#f0f6fc", width: 1, type: "dashed" },
          data: [{ yAxis: price, label: { formatter: `当前价 ${price.toFixed(2)}`, color: "#f0f6fc", fontSize: 11 } }],
        }
      : undefined,
  };

  return (
    <div className="space-y-4">
      {/* 统计指标 */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard
          label="获利盘"
          value={data.profit_ratio != null ? `${(data.profit_ratio * 100).toFixed(1)}%` : "—"}
          color={data.profit_ratio != null && data.profit_ratio > 0.5 ? "text-[#ef5350]" : "text-[#26a69a]"}
        />
        <StatCard
          label="平均成本"
          value={data.avg_cost != null ? `¥${data.avg_cost.toFixed(2)}` : "—"}
        />
        <StatCard
          label="筹码集中度"
          value={
            data.concentration != null
              ? data.concentration < 0.1
                ? "高度集中"
                : data.concentration < 0.2
                ? "较为集中"
                : "较为分散"
              : "—"
          }
          color={
            data.concentration != null && data.concentration < 0.1
              ? "text-[#ef5350]"
              : "text-gray-700"
          }
        />
      </div>

      {/* 筹码分布图 */}
      <ReactECharts
        option={option}
        style={{ height: 320 }}
        theme="dark"
        notMerge
      />

      <p className="text-xs text-gray-400">
        数据截止: {data.calc_date} · 回看250个交易日 · GSY模型估算，仅供参考
      </p>
    </div>
  );
}

function StatCard({
  label,
  value,
  color = "text-gray-800",
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="bg-[#f6f8fa] rounded-lg p-3">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-semibold ${color}`}>{value}</p>
    </div>
  );
}
