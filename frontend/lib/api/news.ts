import { api } from "./client";

export interface NewsRelatedStock {
  code: string;
  name: string;
  relevance: number;
}

export interface NewsDetail {
  id: number;
  title: string;
  summary: string | null;
  content: string | null;
  source: string;
  source_url: string | null;
  sentiment: "positive" | "negative" | "neutral" | null;
  published_at: string | null;
  crawled_at: string;
  category: string | null;
  direction: "bullish" | "bearish" | "neutral" | null;
  urgency: "urgent" | "important" | "info" | null;
  importance_score: number | null;
  rule_score: number | null;
  llm_score: number | null;
  source_authority: number | null;

  // P0 升级字段
  catalyst_type: string | null;
  catalyst_summary: string | null;
  key_risks: string | null;
  original_title: string | null;
  original_lang: string | null;

  related_stocks: NewsRelatedStock[];
}

export const newsApi = {
  getDetail: (id: number) => api.get<NewsDetail>(`/news/detail/${id}`),
};
