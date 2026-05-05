import { api } from "./client";

export interface Report {
  id: number;
  report_date: string;
  report_type: string;
  conclusion: string | null;
  overall_signal: "bullish" | "bearish" | "neutral" | null;
  technical_score: number | null;
  fundamental_score: number | null;
  industry_inflection: string | null;
  external_disruption: string | null;
  action_suggestion: string | null;
  full_report: {
    technical_analysis?: string;
    fundamental_analysis?: string;
    catalysts?: string[];
    risks?: string[];
    support_level?: number;
    resistance_level?: number;
    suggestion?: string;
    // Claude 对话评分扩展字段（source='claude_chat' 时存在）
    source?: string;
    framework_version?: string;  // "6d_tech_v1" 标识 6D 精简版 / 旧 "8d_tier_weighted_v1"
    // 6D + 技术(2026-05 精简版)— 旧 D6/D7 已并入 D1/D5
    claude_industry_score?: number;     // D1 行业拐点 + 叙事(原 D1+D6 合并)
    claude_disruption_score?: number;   // D2 外部颠覆
    claude_moat_score?: number;         // D3 护城河
    claude_valuation_score?: number;    // D4 动态赔率
    claude_performance_score?: number;  // D5 业绩 + 财务(原 D5+D7 合并)
    claude_governance_score?: number;   // D8 治理
    claude_tech_score?: number;         // 技术评估(K 线 + 筹码 + 动量)— 新增
    // 嵌套结构(2026-05 6D 精简版,详情页消费)
    core?: { upside_pct?: number | null; score?: number | null; freshness?: string | null; text: string; conclusion: string };
    dims?: {
      d1?: { score: number; text: string; conclusion: string };
      d2?: { score: number; text: string; conclusion: string };
      d3?: { score: number; text: string; conclusion: string };
      d4?: { score: number; text: string; conclusion: string };
      d5?: { score: number; text: string; conclusion: string };
      d8?: { score: number; text: string; conclusion: string };
    };
    tech?: { score: number; text: string; conclusion: string };
    // Veto 状态（2026-05 新增）
    veto_triggered?: boolean;
    veto_reason?: string | null;
    // 综合分
    claude_overall_score?: number;
    claude_overall_label?: string;
    summary?: string;
    // 五档价位（前瞻字段,Skill 后续可能补充结构化数据)
    price_levels?: {
      heavy_buy?: number | null;       // 重仓买入价
      mid_buy?: number | null;          // 中线买入价
      hold_low?: number | null;         // 持有区间下沿
      hold_high?: number | null;        // 持有区间上沿
      reduce?: number | null;           // 减仓价
      exit?: number | null;             // 清仓价
    };
    intrinsic_value?: {
      optimistic?: number | null;
      base?: number | null;
      pessimistic?: number | null;
    };
  };
  model_used: string | null;
  generated_at: string;
}

export interface Fundamental {
  code: string;
  name: string;
  pe_ttm: number | null;
  pb: number | null;
  roe: number | null;
  gross_margin: number | null;
  net_margin: number | null;
  debt_ratio: number | null;
  current_ratio: number | null;
  cash_flow_ratio: number | null;
  revenue_yoy: number | null;
  profit_yoy: number | null;
  net_profit_ttm: number | null;   // 亿元
  market_cap: number | null;       // 亿元
  industry_pe_median: number | null;
  pe_percentile: number | null;
  forecasts: {
    forecast_year: number;
    eps_forecast: number | null;
    net_profit_forecast: number | null;
    forward_pe: number | null;
    analyst_count: number | null;
    source: string;
  }[];
}

export interface ChipData {
  calc_date: string;
  price_ranges: { price_low: number; price_high: number; chip_pct: number }[];
  profit_ratio: number | null;
  avg_cost: number | null;
  concentration: number | null;
}

export interface DivergenceSignal {
  id: number;
  detected_date: string;
  signal_type: string;
  price_point1: number | null;
  price_point2: number | null;
  confidence: number | null;
  is_confirmed: boolean;
}

export interface ChipHistoryItem {
  calc_date: string;
  profit_ratio: number | null;
  avg_cost: number | null;
  concentration: number | null;
}

export const analysisApi = {
  latestReport: (code: string) => api.get<Report>(`/analysis/${code}/report/latest`),
  reportHistory: (code: string, limit = 30) =>
    api.get<Report[]>(`/analysis/${code}/report/history?limit=${limit}`),
  refreshReport: (code: string) =>
    api.post(`/analysis/${code}/report/refresh`, {}),
  fundamental: (code: string) => api.get<Fundamental>(`/analysis/${code}/fundamental`),
  chip: (code: string) => api.get<ChipData>(`/analysis/${code}/chip`),
  divergence: (code: string, days = 60) =>
    api.get<DivergenceSignal[]>(`/analysis/${code}/divergence?days=${days}`),
  chipHistory: (code: string, days = 7) =>
    api.get<ChipHistoryItem[]>(`/analysis/${code}/chip/history?days=${days}`),
};
