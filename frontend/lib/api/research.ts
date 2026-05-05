import { api } from "./client";

export interface ResearchReportRead {
  news_id: number;
  title: string;
  broker: string;
  rating: string | null;
  published_at: string | null;
  pdf_url: string | null;
  forecast_year_base: number | null;
  eps_y1: number | null;
  eps_y2: number | null;
  eps_y3: number | null;
  pe_y1: number | null;
  pe_y2: number | null;
  pe_y3: number | null;
  summary: string | null;
  content_ready: boolean;
}

export interface GlobalResearchReportRead extends ResearchReportRead {
  code: string;
  stock_name: string;
}

export interface ResearchListParams {
  code?: string;
  broker?: string;
  rating?: string;
  days?: number;
  limit?: number;
}

function qs(params: ResearchListParams): string {
  const u = new URLSearchParams();
  if (params.code) u.set("code", params.code);
  if (params.broker) u.set("broker", params.broker);
  if (params.rating) u.set("rating", params.rating);
  if (params.days) u.set("days", String(params.days));
  if (params.limit) u.set("limit", String(params.limit));
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const researchApi = {
  listForStock: (code: string, limit = 20) =>
    api.get<ResearchReportRead[]>(
      `/stocks/${encodeURIComponent(code)}/research?limit=${limit}`,
    ),
  refresh: (code: string) =>
    api.post<{ message: string }>(
      `/stocks/${encodeURIComponent(code)}/research/refresh`,
      {},
    ),
  listGlobal: (params: ResearchListParams = {}) =>
    api.get<GlobalResearchReportRead[]>(`/research${qs(params)}`),
  listBrokers: (days = 90) =>
    api.get<string[]>(`/research/brokers?days=${days}`),
};

// 评级 → 颜色映射
export function ratingColor(rating: string | null | undefined): string {
  if (!rating) return "gray";
  const r = rating.trim();
  if (/(强烈)?(推荐|买入)/.test(r)) return "red";       // 涨色
  if (/(增持|跑赢)/.test(r)) return "yellow";
  if (/(中性|持有|跑平|观望)/.test(r)) return "gray";
  if (/(减持|跑输|谨慎)/.test(r)) return "blue";
  if (/卖出/.test(r)) return "green";                  // 跌色
  return "gray";
}
