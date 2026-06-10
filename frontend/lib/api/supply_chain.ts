import { api } from "./client";

export interface SupplyChainNode {
  id: number;
  relation_type: "upstream" | "downstream" | "competitor";
  company_name: string;
  company_code: string | null;
  product_desc: string | null;
  percentage: number | null;
  importance: "high" | "medium" | "low";
  is_listed: boolean;
  recent_event_count: number;
  urgent_event_count: number;
  latest_event_title: string | null;
  latest_news_id: number | null;
}

export interface SupplyChainEventSummary {
  news_id: number;
  stock_code: string;
  stock_name: string;
  company_name: string;
  company_code: string | null;
  title: string;
  published_at: string | null;
  urgency: "urgent" | "important" | "info" | null;
  importance_score: number | null;
  relevance: number;
  impact_direction: "bullish" | "bearish" | "neutral" | null;
  impact_summary: string | null;
}

export interface SupplyChain {
  code: string;
  name: string;
  upstream: SupplyChainNode[];
  downstream: SupplyChainNode[];
  competitors: SupplyChainNode[];
  updated_at: string | null;
  recent_events: SupplyChainEventSummary[];
}

// 全局供应链图(聚簇分组)
export interface SupplyChainStockMeta {
  code: string;
  name: string;
  industry: string | null;
  market: string;  // A / H / EXT
  recent_event_count: number;
  urgent_event_count: number;
  latest_event_title: string | null;
  latest_news_id: number | null;
}

export interface SupplyChainEdge {
  from_code: string;
  to_code: string;
  from_name: string;
  to_name: string;
  product_desc: string | null;
  importance: "high" | "medium" | "low";
  relation_type: "upstream" | "downstream";
  both_listed: boolean;
  recent_event_count: number;
  urgent_event_count: number;
  latest_event_title: string | null;
  latest_news_id: number | null;
}

export interface GlobalSupplyChain {
  watchlist_stocks: SupplyChainStockMeta[];
  external_companies: SupplyChainStockMeta[];
  edges: SupplyChainEdge[];
  recent_events: SupplyChainEventSummary[];
  industry_groups: Record<string, string[]>;
  stats: {
    watchlist_count: number;
    external_count: number;
    edge_count: number;
    industry_count: number;
    cross_watchlist_edges: number;
    highlighted_edges: number;
    recent_event_count: number;
  };
}

export const supplyChainApi = {
  get: (code: string) => api.get<SupplyChain>(`/supply-chain/${code}`),
  refresh: (code: string) => api.post(`/supply-chain/${code}/refresh`, {}),
  global: () => api.get<GlobalSupplyChain>("/supply-chain/global"),
  coverage: () => api.get<{
    items: Array<{
      code: string;
      name: string;
      upstream_count: number;
      downstream_count: number;
      competitor_count: number;
      total_count: number;
      status: "complete" | "partial" | "missing";
    }>;
    stats: Record<string, number>;
  }>("/supply-chain/global/coverage"),
  fillGaps: (limit = 10, force = false) =>
    api.post(`/supply-chain/global/fill-gaps?limit=${limit}&force=${force}`, {}),
  refreshIntelligence: (days = 14) =>
    api.post(`/supply-chain/global/refresh-intelligence?days=${days}`, {}),
};
