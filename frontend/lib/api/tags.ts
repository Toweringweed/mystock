import { api } from "./client";
import type { StockRead } from "./stocks";

export type TagCategory = "theme" | "industry_chain" | "attribute";

export interface TagRead {
  id: number;
  name: string;
  category: TagCategory;
  description?: string | null;
}

export interface StockTagRead extends TagRead {
  source: "ai" | "manual";
  confidence?: number | null;
}

export const tagsApi = {
  listAll: () => api.get<TagRead[]>("/tags"),
  listForStock: (code: string) =>
    api.get<StockTagRead[]>(`/stocks/${encodeURIComponent(code)}/tags`),
  attach: (code: string, name: string, category: TagCategory = "theme") =>
    api.post<TagRead>(`/stocks/${encodeURIComponent(code)}/tags`, {
      name,
      category,
    }),
  detach: (code: string, tagId: number) =>
    api.delete(`/stocks/${encodeURIComponent(code)}/tags/${tagId}`),
  refresh: (code: string) =>
    api.post<{ message: string }>(
      `/stocks/${encodeURIComponent(code)}/tags/refresh`,
      {},
    ),
  stocksByTag: (tagId: number) =>
    api.get<StockRead[]>(`/tags/${tagId}/stocks`),
  deleteGlobal: (tagId: number) => api.delete(`/tags/${tagId}`),
};

// 颜色映射（按 category）
export const TAG_CATEGORY_COLOR: Record<TagCategory, string> = {
  theme: "blue",
  industry_chain: "yellow",
  attribute: "green",
};

export const TAG_CATEGORY_LABEL: Record<TagCategory, string> = {
  theme: "主题",
  industry_chain: "产业链",
  attribute: "属性",
};
