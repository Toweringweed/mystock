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
}

export interface SupplyChain {
  code: string;
  name: string;
  upstream: SupplyChainNode[];
  downstream: SupplyChainNode[];
  competitors: SupplyChainNode[];
  updated_at: string | null;
}

// 全局供应链图(聚簇分组)
export interface SupplyChainStockMeta {
  code: string;
  name: string;
  industry: string | null;
  market: string;  // A / H / EXT
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
}

export interface GlobalSupplyChain {
  watchlist_stocks: SupplyChainStockMeta[];
  external_companies: SupplyChainStockMeta[];
  edges: SupplyChainEdge[];
  industry_groups: Record<string, string[]>;
  stats: {
    watchlist_count: number;
    external_count: number;
    edge_count: number;
    industry_count: number;
    cross_watchlist_edges: number;
  };
}

export const supplyChainApi = {
  get: (code: string) => api.get<SupplyChain>(`/supply-chain/${code}`),
  refresh: (code: string) => api.post(`/supply-chain/${code}/refresh`, {}),
  global: () => api.get<GlobalSupplyChain>("/supply-chain/global"),
};
