import { api } from "./client";

export interface SettingItem {
  key: string;
  value: string;
  has_value: boolean;
  description: string;
  is_secret: boolean;
  group: string; // ai / data / notifications / ...（后端可扩展）
  source: "env" | "db";
}

export interface LLMTestResult {
  openrouter: { status: "ok" | "error" | "not_configured"; model?: string; reply?: string; error?: string };
  openai: { status: "ok" | "error" | "not_configured"; model?: string; reply?: string; error?: string };
  anthropic: { status: "ok" | "error" | "not_configured"; model?: string; reply?: string; error?: string };
}

export type TriggerableTask =
  | "refresh_all_watchlist"
  | "daily_after_close_routine"
  | "monthly_universe_refresh"
  | "sync_stock_universe"
  | "refresh_watchlist_data"
  | "crawl_research_reports"
  | "update_realtime_quotes"
  | "update_all_fundamentals"
  | "crawl_all_sources"
  | "crawl_disclosures_only"
  | "calc_all_indicators"
  | "process_pending_news"
  | "run_event_detection"
  | "generate_daily_summaries"
  | "generate_reports_for_events"
  | "dispatch_event_queue"
  | "dispatch_daily_summary"
  | "update_capital_flows"
  | "update_lhb"
  | "sync_calendar_events"
  | "update_industry_metrics"
  | "update_profit_forecasts"
  | "extract_segments_for_all";

export interface TriggerTaskResult {
  message: string;
  task_name: TriggerableTask;
  celery_task_id: string;
}

export interface DataStatusItem {
  group: string;
  table: string;
  rows: number;
  stocks: number | null;
  latest: string | null;
  stale_hours: number | null;
  expected_max_hours?: number | null;
  /** healthy / stale / empty / not_implemented */
  status?: "healthy" | "stale" | "empty" | "not_implemented";
  trigger_task?: string | null;
  hint: string;
}

export const settingsApi = {
  getAll: () => api.get<SettingItem[]>("/settings"),
  update: (key: string, value: string) =>
    api.put<{ message: string }>("/settings", { key, value }),
  testLLM: () => api.post<LLMTestResult>("/settings/test-llm", {}),

  triggerTask: (task_name: TriggerableTask) =>
    api.post<TriggerTaskResult>("/settings/trigger-task", { task_name }),
  testNotify: () => api.post<{ message: string }>("/settings/test-notify", {}),
  refreshKeywords: () => api.post<{ message: string }>("/settings/refresh-keywords", {}),
  dataStatus: () => api.get<DataStatusItem[]>("/settings/data-status"),
};
