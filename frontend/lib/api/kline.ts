import { api } from "./client";

export interface KlineBar {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  turnover: number;
  change_pct: number;
}

export interface Indicator {
  trade_date: string;
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  rsi_6: number | null;
  rsi_14: number | null;
  rsi_24: number | null;
  kdj_k: number | null;
  kdj_d: number | null;
  kdj_j: number | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  obv: number | null;
  chip_profit_ratio: number | null;
  chip_concentration: number | null;
  chip_avg_cost: number | null;
}

export const klineApi = {
  daily: (code: string, days = 90) =>
    api.get<KlineBar[]>(`/kline/${code}/daily?days=${days}`),
  indicators: (code: string, days = 90) =>
    api.get<Indicator[]>(`/kline/${code}/indicators?days=${days}`),
  recalc: (code: string) =>
    api.post<{ message: string; klines_saved: number; indicators_saved: number }>(
      `/kline/${code}/recalc`,
      {}
    ),
};
