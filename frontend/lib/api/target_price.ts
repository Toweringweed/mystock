import { api } from "./client";

export interface InstitutionBreakdownItem {
  institution: string;
  weight: number;
  is_foreign: boolean;
  report_date: string;
  rating: string | null;
  target_price: number;
  target_derived: boolean;
  eps_y1: number | null;
  pe_y1: number | null;
  freshness_days: number;
}

export interface TargetPriceRealtime {
  stock_id: number;
  current_price: string | null;
  avg_target_simple: string | null;
  avg_target_weighted: string | null;
  highest_target: string | null;
  lowest_target: string | null;
  target_dispersion_cv: string | null;
  upside_pct: string | null;
  base_score: string | null;
  final_score: string | null;
  has_consensus: boolean;
  bonus_consensus_pct: string | null;
  upgrade_count_30d: number;
  bonus_revisions_pct: string | null;
  total_bonus_pct: string | null;
  research_count_30d: number;
  research_count_90d: number;
  days_since_latest: number | null;
  freshness_status: "fresh" | "recent" | "aging" | "stale" | "none" | null;
  freshness_factor: string | null;
  veto_triggered: boolean;
  veto_reason: string | null;
  institution_breakdown: {
    items: InstitutionBreakdownItem[];
    weighted_avg: number;
    simple_avg: number;
  } | null;
  updated_at: string;
}

export const targetPriceApi = {
  forStock: (code: string, recompute = false) =>
    api.get<TargetPriceRealtime>(
      `/stocks/${code}/target-price-realtime${recompute ? "?recompute=true" : ""}`
    ),
  recomputeAll: () =>
    api.post<{ total: number; computed: number; no_target: number; veto: number }>(
      "/target-price/recompute-all", {}
    ),
  ranking: (limit = 50, onlyActionable = false) =>
    api.get<TargetPriceRealtime[]>(
      `/target-price/ranking?limit=${limit}&only_actionable=${onlyActionable}`
    ),
};
