import { api } from "./client";

export interface StockRead {
  id: number;
  code: string;
  market: "A" | "HK";
  name: string;
  industry: string | null;
  is_watchlist: boolean;
  is_core: boolean;
  data_ready: boolean;
  sync_status: string;
  sync_task_id: string | null;
  sync_error: string | null;
  sync_started_at: string | null;
  sync_completed_at: string | null;
}

export interface StockSearch {
  code: string;
  name: string;
  market: "A" | "HK";
  industry: string | null;
}

export const stocksApi = {
  search: (q: string) => api.get<StockSearch[]>(`/stocks/search?q=${encodeURIComponent(q)}`),
  watchlist: () => api.get<StockRead[]>("/stocks/watchlist"),
  add: (code: string, market: string, name?: string) =>
    api.post<StockRead>("/stocks/watchlist", { code, market, name }),
  remove: (code: string) => api.delete(`/stocks/watchlist/${code}`),
  setCore: (code: string, is_core: boolean) =>
    api.patch<StockRead>(`/stocks/watchlist/${code}/core`, { is_core }),
  get: (code: string) => api.get<StockRead>(`/stocks/${code}`),
};
