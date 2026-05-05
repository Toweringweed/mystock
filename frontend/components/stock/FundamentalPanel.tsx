"use client";

import useSWR from "swr";
import { analysisApi, Fundamental } from "@/lib/api/analysis";
import { clsx } from "clsx";

interface Props {
  code: string;
}

export function FundamentalPanel({ code }: Props) {
  const { data, isLoading } = useSWR(`fundamental-${code}`, () =>
    analysisApi.fundamental(code)
  );

  if (isLoading) return <div className="text-xs text-gray-500 py-10 text-center">加载中...</div>;
  if (!data) return <div className="text-xs text-gray-500 py-10 text-center">暂无基本面数据</div>;

  return (
    <div className="space-y-6">
      {/* 估值指标 */}
      <Section title="估值水平">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard label="PE-TTM" value={fmt(data.pe_ttm, "x")} note={peNote(data.pe_ttm)} />
          <MetricCard label="PB" value={fmt(data.pb, "x")} />
          <MetricCard label="ROE" value={fmt(data.roe, "%")} />
          <MetricCard
            label="PE 历史分位"
            value={data.pe_percentile != null ? `${data.pe_percentile.toFixed(0)}%` : "—"}
            note={pePercentileNote(data.pe_percentile)}
            noteColor={pePercentileColor(data.pe_percentile)}
          />
        </div>
        {data.industry_pe_median != null && (
          <p className="text-xs text-gray-500 mt-2">
            行业 PE 中位数：{data.industry_pe_median.toFixed(1)}x
            {data.pe_ttm != null && (
              <span className={clsx("ml-2", data.pe_ttm < data.industry_pe_median ? "text-[#26a69a]" : "text-[#ef5350]")}>
                {data.pe_ttm < data.industry_pe_median ? "低于行业均值" : "高于行业均值"}
              </span>
            )}
          </p>
        )}
      </Section>

      {/* 盈利能力 */}
      <Section title="盈利能力">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard label="毛利率" value={fmt(data.gross_margin, "%")} />
          <MetricCard label="净利率" value={fmt(data.net_margin, "%")} />
          <MetricCard
            label="营收同比"
            value={fmt(data.revenue_yoy, "%")}
            valueColor={growthColor(data.revenue_yoy)}
          />
          <MetricCard
            label="净利润同比"
            value={fmt(data.profit_yoy, "%")}
            valueColor={growthColor(data.profit_yoy)}
          />
        </div>
      </Section>

      {/* 财务健康 */}
      <Section title="财务健康">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <MetricCard
            label="资产负债率"
            value={fmt(data.debt_ratio, "%")}
            noteColor={data.debt_ratio != null && data.debt_ratio > 70 ? "text-[#ef5350]" : undefined}
            note={data.debt_ratio != null && data.debt_ratio > 70 ? "偏高" : undefined}
          />
        </div>
      </Section>

      {/* 盈利预测 */}
      {data.forecasts.length > 0 && (
        <Section title="机构盈利预测">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-gray-200">
                  <th className="text-left py-2">年度</th>
                  <th className="text-right py-2">预测净利润</th>
                  <th className="text-right py-2">预测 EPS</th>
                  <th className="text-right py-2">远期 PE</th>
                  <th className="text-right py-2">分析师数</th>
                </tr>
              </thead>
              <tbody>
                {data.forecasts.map((f) => (
                  <tr
                    key={`${f.forecast_year}-${f.source}`}
                    className="border-b border-gray-200/50 hover:bg-gray-100/30"
                  >
                    <td className="py-2 text-gray-800 font-medium">{f.forecast_year}E</td>
                    <td className="py-2 text-right text-gray-700">
                      {f.net_profit_forecast != null
                        ? `${(f.net_profit_forecast / 1e8).toFixed(2)} 亿`
                        : "—"}
                    </td>
                    <td className="py-2 text-right text-gray-700">
                      {f.eps_forecast != null ? `¥${f.eps_forecast.toFixed(2)}` : "—"}
                    </td>
                    <td className="py-2 text-right">
                      {f.forward_pe != null ? (
                        <span
                          className={clsx(
                            "font-semibold",
                            f.forward_pe < 15
                              ? "text-[#26a69a]"
                              : f.forward_pe > 30
                              ? "text-[#ef5350]"
                              : "text-gray-800"
                          )}
                        >
                          {f.forward_pe.toFixed(1)}x
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2 text-right text-gray-500 text-xs">
                      {f.analyst_count ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            数据来源：机构一致预期（{data.forecasts[0]?.source}）· 仅供参考
          </p>
        </Section>
      )}
    </div>
  );
}

// ── 辅助组件 ──────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-600 mb-3 flex items-center gap-2">
        <span className="w-1 h-4 bg-[#58a6ff] rounded-full inline-block" />
        {title}
      </h3>
      {children}
    </div>
  );
}

function MetricCard({
  label,
  value,
  note,
  noteColor,
  valueColor,
}: {
  label: string;
  value: string;
  note?: string;
  noteColor?: string;
  valueColor?: string;
}) {
  return (
    <div className="bg-[#f6f8fa] rounded-lg p-3">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={clsx("text-lg font-semibold", valueColor ?? "text-gray-800")}>{value}</p>
      {note && <p className={clsx("text-xs mt-0.5", noteColor ?? "text-gray-500")}>{note}</p>}
    </div>
  );
}

// ── 辅助函数 ──────────────────────────────────────────────────────

function fmt(v: number | null | undefined, suffix: string): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}${suffix}`;
}

function peNote(pe: number | null | undefined): string | undefined {
  if (pe == null) return undefined;
  if (pe < 10) return "低估值";
  if (pe < 20) return "合理";
  if (pe < 35) return "偏高";
  return "高估值";
}

function pePercentileNote(p: number | null | undefined): string | undefined {
  if (p == null) return undefined;
  if (p < 20) return "历史低位";
  if (p > 80) return "历史高位";
  return "中等水平";
}

function pePercentileColor(p: number | null | undefined): string | undefined {
  if (p == null) return undefined;
  if (p < 20) return "text-[#26a69a]";
  if (p > 80) return "text-[#ef5350]";
  return undefined;
}

function growthColor(v: number | null | undefined): string | undefined {
  if (v == null) return undefined;
  return v > 0 ? "text-[#ef5350]" : "text-[#26a69a]";
}
