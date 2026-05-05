import { api } from "./client";

export interface StockRead {
  id: number;
  code: string;
  market: "A" | "HK";
  name: string;
  industry: string | null;
  is_watchlist: boolean;
  data_ready: boolean;
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
  get: (code: string) => api.get<StockRead>(`/stocks/${code}`),
};
