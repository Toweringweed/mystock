import { api } from "./client";

export interface EarningsSurprise {
  id: number;
  stock_id: number;
  period_type: "quarterly" | "annual";
  period: string;
  release_date: string;
  expected_release_date: string | null;

  expected_revenue_yi: string | null;
  expected_net_profit_yi: string | null;
  expected_eps: string | null;
  expected_yoy_growth: string | null;
  expected_source: string | null;

  actual_revenue_yi: string | null;
  actual_net_profit_yi: string | null;
  actual_eps: string | null;
  actual_yoy_growth: string | null;
  actual_qoq_growth: string | null;

  surprise_revenue_pct: string | null;
  surprise_net_profit_pct: string | null;
  surprise_direction: "beat" | "meet" | "miss" | null;

  price_at_release: string | null;
  pre_release_5d_return: string | null;
  pre_release_20d_return: string | null;
  post_release_1d_return: string | null;
  post_release_5d_return: string | null;
  post_release_30d_return: string | null;

  forward_eps_revision_pct: string | null;
  data_source: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface UpcomingEarnings {
  stock_id: number;
  code: string;
  name: string;
  expected_release_date: string;
  days_to_release: number;
  period_hint: string | null;
  last_surprise_direction: "beat" | "meet" | "miss" | null;
  last_surprise_pct: string | null;
}

export const earningsApi = {
  forStock: (code: string, limit = 8) =>
    api.get<EarningsSurprise[]>(`/stocks/${code}/earnings-surprises?limit=${limit}`),
  upcoming: (days = 60, onlyWatchlist = true) =>
    api.get<UpcomingEarnings[]>(
      `/earnings-surprises/upcoming?days=${days}&only_watchlist=${onlyWatchlist}`,
    ),
  recent: (days = 60, direction?: "beat" | "meet" | "miss", limit = 50) => {
    const params = new URLSearchParams({ days: String(days), limit: String(limit) });
    if (direction) params.set("direction", direction);
    return api.get<EarningsSurprise[]>(`/earnings-surprises/recent?${params}`);
  },
};

// ─── 共识修正 ────────────────────────────────
export interface EstimateRevision {
  id: number;
  stock_id: number;
  revision_date: string;
  forecast_year: number;
  consensus_eps: string | null;
  consensus_net_profit_yi: string | null;
  consensus_revenue_yi: string | null;
  consensus_target_price: string | null;
  institution_count: number | null;
  eps_revision_pct: string | null;
  net_profit_revision_pct: string | null;
  target_price_revision_pct: string | null;
  revision_direction: "up" | "flat" | "down" | null;
  source: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export const estimateRevisionsApi = {
  forStock: (code: string, forecastYear?: number, limit = 24) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (forecastYear) params.set("forecast_year", String(forecastYear));
    return api.get<EstimateRevision[]>(`/stocks/${code}/estimate-revisions?${params}`);
  },
};
