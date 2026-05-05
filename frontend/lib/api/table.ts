import { api } from "./client";
import type { TagRead } from "./tags";

export interface WatchlistTableRow {
  code: string;
  name: string;
  market: "A" | "HK";
  // 维度 3 · 护城河
  gross_margin: number | null;
  net_margin: number | null;
  roe: number | null;
  // 维度 4 · 动态赔率
  pe_ttm: number | null;
  forward_pe_2026: number | null;
  forward_pe_2027: number | null;
  forecast_2026: number | null;
  forecast_2027: number | null;
  // 维度 5 · 业绩兑现
  revenue_yoy: number | null;
  profit_yoy: number | null;
  // 维度 6 · 叙事窗口
  overall_signal: "bullish" | "bearish" | "neutral" | null;
  ai_conclusion: string | null;
  technical_score: number | null;
  fundamental_score: number | null;
  technical_analysis: string | null;
  industry_inflection: string | null;
  external_disruption: string | null;
  ai_action_suggestion: string | null;
  // 行情与备注
  current_price: number | null;
  ytd_change: number | null;
  recommendation: string | null;
  personal_note: string | null;
  market_cap: number | null;
  forecast_source: string | null;
  tags: TagRead[];
  // Claude「核心 + 6D + 技术」评分(2026-05 精简版,由 stock-analysis skill 写入)
  claude_overall_score: number | null;        // Tier 加权综合分(不含核心段)
  claude_industry_score: number | null;       // D1 行业拐点 + 上游 + 叙事(原 D1+D6 合并)
  claude_disruption_score: number | null;     // D2 外部颠覆
  claude_moat_score: number | null;           // D3 护城河
  claude_valuation_score: number | null;      // D4 动态赔率
  claude_performance_score: number | null;    // D5 业绩兑现 + 财务质量(原 D5+D7 合并)
  claude_governance_score: number | null;     // D8 治理
  claude_tech_score: number | null;           // 技术评估(K 线 + 筹码 + 动量)— 新增
  claude_veto_triggered: boolean | null;
  claude_veto_reason: string | null;
  claude_overall_label: string | null;
  claude_score_at: string | null;

  // 财报临近预警(2026-05 新增)
  upcoming_earnings_date: string | null;        // 最近一次财报披露日(未来,YYYY-MM-DD)
  days_to_earnings: number | null;              // 距披露还剩天数
  last_earnings_surprise_direction: "beat" | "meet" | "miss" | null;
  last_earnings_surprise_pct: number | null;

  // v5 框架 — 实时目标价上行空间(2026-05 新增,主决策因子)
  v5_final_score: number | null;                // 最终评分(经一致性/上调奖金 + 鲜度衰减后)
  v5_base_score: number | null;                 // 基于上行空间的原始 1-10 分
  v5_upside_pct: number | null;                 // 加权目标价 / 当前价 - 1, 百分比
  v5_avg_target_weighted: number | null;        // 机构权重加权目标价
  v5_avg_target_simple: number | null;          // 简单平均目标价
  v5_freshness_status: "fresh" | "recent" | "aging" | "stale" | "none" | null;
  v5_research_count_30d: number | null;
  v5_research_count_90d: number | null;
  v5_has_consensus: boolean | null;             // ≥3 家研报方向一致 → +20% 奖金
  v5_upgrade_count_30d: number | null;          // ≥3 家上调 → +40% 奖金
  v5_veto_triggered: boolean | null;
  v5_veto_reason: string | null;
  v5_updated_at: string | null;
}

export const tableApi = {
  getWatchlist: () => api.get<WatchlistTableRow[]>("/stocks/watchlist/table"),

  updateForecast: (code: string, year: number, net_profit: number) =>
    api.put(`/analysis/${code}/forecast`, { year, net_profit }),

  generateLLMForecast: (code: string) =>
    api.post(`/analysis/${code}/forecast/llm`, {}),

  updateRecommendation: (code: string, recommendation: string) =>
    api.put(`/analysis/${code}/recommendation`, { recommendation }),

  updatePersonalNote: (code: string, personal_note: string) =>
    api.put(`/analysis/${code}/note`, { personal_note }),
};
