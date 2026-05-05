import { api } from "./client";

export interface BacktestItem {
  report_id: number;
  score_at: string;
  score_date: string;
  code: string;
  name: string;
  claude_overall_score: number;
  claude_overall_label: string | null;
  veto_triggered: boolean;
  veto_reason: string | null;
  industry_score: number | null;
  disruption_score: number | null;
  moat_score: number | null;
  valuation_score: number | null;
  performance_score: number | null;
  narrative_score: number | null;
  financial_score: number | null;
  governance_score: number | null;
  base_date: string;
  base_price: number;
  target_date: string;
  target_price: number;
  return_pct: number;
  actual_horizon_days: number;
}

export interface BacktestSummary {
  sample_size: number;
  horizon_days: number;
  min_history_days: number;
  mode: string;
  spearman_rank_correlation: number | null;
  top_third_avg_return_pct: number | null;
  bottom_third_avg_return_pct: number | null;
  alpha_top_minus_bottom_pct: number | null;
  veto_sample_count: number;
  non_veto_sample_count: number;
  veto_avg_return_pct: number | null;
  non_veto_avg_return_pct: number | null;
  message?: string;
}

export type BacktestMode = "prediction" | "lookback";

export const backtestApi = {
  scores: (horizon: number, mode: BacktestMode = "lookback", minHistory = 0) =>
    api.get<BacktestItem[]>(
      `/backtest/scores?horizon_days=${horizon}&mode=${mode}&min_history_days=${minHistory}`,
    ),
  summary: (horizon: number, mode: BacktestMode = "lookback", minHistory = 0) =>
    api.get<BacktestSummary>(
      `/backtest/summary?horizon_days=${horizon}&mode=${mode}&min_history_days=${minHistory}`,
    ),
};
