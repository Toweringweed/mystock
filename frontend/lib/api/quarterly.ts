import { api } from "./client";

export interface QuarterlyFinancial {
  period_end: string;
  period_label: string;
  gross_margin: number | null;
  roe: number | null;
  net_margin: number | null;
  debt_ratio: number | null;
  revenue_yoy: number | null;
  profit_yoy: number | null;
  profit_qoq: number | null;
  // 2026-05 新增 — 后端推算的单季 + 单季环比
  single_quarter_revenue_yi: number | null;       // 单季营收(亿元)
  revenue_qoq: number | null;                     // 单季营收环比(%)
  single_quarter_deducted_profit_yi: number | null; // 单季扣非净利(亿元)
  deducted_profit_qoq: number | null;             // 单季扣非环比(%)
}

export const quarterlyApi = {
  forStock: (code: string, limit = 8) =>
    api.get<QuarterlyFinancial[]>(`/analysis/${encodeURIComponent(code)}/quarterly-financials?limit=${limit}`),
};
