"use client";

import { useState, useCallback } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import Link from "next/link";
import { clsx } from "clsx";
import { analysisApi } from "@/lib/api/analysis";
import { klineApi, Indicator, KlineBar } from "@/lib/api/kline";
import { stocksApi } from "@/lib/api/stocks";
import { NewsFeed } from "@/components/news/NewsFeed";
import { tableApi } from "@/lib/api/table";
import { TagBar } from "@/components/stock/TagBar";
import { NewsHighlightsPanel } from "@/components/stock/NewsHighlightsPanel";
import { targetPriceApi } from "@/lib/api/target_price";
import { EarningsTrackPanel } from "@/components/stock/EarningsTrackPanel";
import { EstimateRevisionsPanel } from "@/components/stock/EstimateRevisionsPanel";
import { MoatChangePanel } from "@/components/stock/MoatChangePanel";
import { TargetPricePanel } from "@/components/stock/TargetPricePanel";

// ─── 通用 UI ──────────────────────────────────────────────────────────────────

function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
        <span className="w-1 h-4 bg-[#58a6ff] rounded-full shrink-0" />
        {children}
      </h2>
      {action}
    </div>
  );
}

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx("bg-[#f6f8fa] rounded-xl border border-gray-200 p-4", className)}>
      {children}
    </div>
  );
}

function MetricItem({ label, value, sub, valueClass }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; valueClass?: string;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500 mb-0.5">{label}</p>
      <p className={clsx("text-base font-semibold leading-snug", valueClass ?? "text-gray-800")}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function Tag({ children, color = "gray" }: {
  children: React.ReactNode;
  color?: "red" | "green" | "blue" | "yellow" | "gray";
}) {
  const cls = { red: "bg-[#ef5350]/10 text-[#ef5350] border-[#ef5350]/30", green: "bg-[#26a69a]/10 text-[#26a69a] border-[#26a69a]/30", blue: "bg-[#58a6ff]/10 text-[#58a6ff] border-[#58a6ff]/30", yellow: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30", gray: "bg-gray-100 text-gray-600 border-gray-300" }[color];
  return <span className={clsx("text-xs px-2 py-0.5 rounded border font-medium", cls)}>{children}</span>;
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

const fmt = (v: number | null | undefined, suffix = "", dp = 2): string =>
  v == null ? "—" : `${v.toFixed(dp)}${suffix}`;
const growthClass = (v: number | null | undefined) =>
  v == null ? undefined : v > 0 ? "text-[#ef5350]" : "text-[#26a69a]";
const peColor = (pe: number | null | undefined) =>
  pe == null ? undefined : pe <= 20 ? "text-[#26a69a]" : pe <= 35 ? "text-yellow-400" : "text-[#ef5350]";

// ─── 技术分析计算 ──────────────────────────────────────────────────────────────

function buildTechConclusion(indicators: Indicator[], klines: KlineBar[]) {
  if (!indicators.length) return null;
  const latest = indicators[indicators.length - 1];
  const prev = indicators.length > 1 ? indicators[indicators.length - 2] : null;
  const ma5 = latest.ma5 ?? 0, ma10 = latest.ma10 ?? 0, ma20 = latest.ma20 ?? 0, ma60 = latest.ma60 ?? 0;

  let trend = "震荡排列", trendColor: "red" | "green" | "gray" = "gray";
  if (ma5 > 0 && ma60 > 0) {
    if (ma5 > ma10 && ma10 > ma20 && ma20 > ma60) { trend = "多头排列（MA5>MA10>MA20>MA60）"; trendColor = "red"; }
    else if (ma5 < ma10 && ma10 < ma20 && ma20 < ma60) { trend = "空头排列（MA5<MA10<MA20<MA60）"; trendColor = "green"; }
    else if (ma5 > ma20) { trend = "短期偏多，中期震荡"; trendColor = "red"; }
    else { trend = "短期偏空，关注支撑"; trendColor = "green"; }
  }

  const hist = latest.macd_hist ?? 0, prevHist = prev?.macd_hist ?? hist;
  let macd = "MACD 数据不足", macdColor: "red" | "green" | "gray" = "gray";
  if (hist > 0 && prevHist <= 0) { macd = "MACD 金叉（红柱转正）"; macdColor = "red"; }
  else if (hist < 0 && prevHist >= 0) { macd = "MACD 死叉（绿柱转负）"; macdColor = "green"; }
  else if (hist > 0 && hist > prevHist) { macd = `MACD 红柱扩张（${hist.toFixed(3)}）`; macdColor = "red"; }
  else if (hist > 0) { macd = `MACD 红柱收缩（${hist.toFixed(3)}）`; macdColor = "gray"; }
  else if (hist < 0 && Math.abs(hist) < Math.abs(prevHist)) { macd = `MACD 绿柱收缩（${hist.toFixed(3)}）`; macdColor = "gray"; }
  else if (hist < 0) { macd = `MACD 绿柱扩张（${hist.toFixed(3)}）`; macdColor = "green"; }

  const rsi = latest.rsi_14 ?? 50;
  let rsiText = `RSI=${rsi.toFixed(1)} 中性`, rsiColor: "red" | "green" | "yellow" | "gray" = "gray";
  if (rsi < 25) { rsiText = `RSI=${rsi.toFixed(1)} 深度超卖`; rsiColor = "green"; }
  else if (rsi < 35) { rsiText = `RSI=${rsi.toFixed(1)} 超卖区`; rsiColor = "green"; }
  else if (rsi > 75) { rsiText = `RSI=${rsi.toFixed(1)} 深度超买`; rsiColor = "red"; }
  else if (rsi > 65) { rsiText = `RSI=${rsi.toFixed(1)} 超买高位`; rsiColor = "yellow"; }
  else if (rsi > 55) { rsiText = `RSI=${rsi.toFixed(1)} 多头偏强`; rsiColor = "red"; }

  const k = latest.kdj_k ?? 50, d = latest.kdj_d ?? 50, prevK = prev?.kdj_k ?? k, prevD = prev?.kdj_d ?? d;
  let kdj = `KDJ K${k.toFixed(0)}/D${d.toFixed(0)}`, kdjColor: "red" | "green" | "gray" = "gray";
  if (k > d && prevK <= prevD) { kdj = `KDJ 金叉（K=${k.toFixed(1)}>D=${d.toFixed(1)}）`; kdjColor = "red"; }
  else if (k < d && prevK >= prevD) { kdj = `KDJ 死叉（K=${k.toFixed(1)}<D=${d.toFixed(1)}）`; kdjColor = "green"; }
  else if (k > d && k > 80) { kdj = `KDJ 高位钝化（K=${k.toFixed(1)}）`; kdjColor = "gray"; }
  else if (k < d && k < 20) { kdj = `KDJ 低位超卖（K=${k.toFixed(1)}）`; kdjColor = "green"; }
  else if (k > d) { kdj = `KDJ 多头格局（K=${k.toFixed(1)}>D=${d.toFixed(1)}）`; kdjColor = "red"; }
  else { kdj = `KDJ 空头格局（K=${k.toFixed(1)}<D=${d.toFixed(1)}）`; kdjColor = "green"; }

  const close = klines.length ? klines[klines.length - 1].close : 0;
  const bbU = latest.bb_upper ?? 0, bbM = latest.bb_middle ?? 0, bbL = latest.bb_lower ?? 0;
  const bbWidth = bbU && bbL && bbM ? (bbU - bbL) / bbM * 100 : 0;
  let bb = "布林带中轨运行", bbColor: "red" | "green" | "gray" = "gray";
  if (close > 0 && bbU > 0) {
    if (close > bbU) { bb = `突破上轨 ¥${bbU.toFixed(2)}，关注回调`; bbColor = "red"; }
    else if (close < bbL) { bb = `跌破下轨 ¥${bbL.toFixed(2)}，关注企稳`; bbColor = "green"; }
    else if (bbWidth < 5) { bb = "布林带收口，等待方向选择"; }
    else if (close > bbM) { bb = `上轨区间（¥${bbM.toFixed(2)}～¥${bbU.toFixed(2)}）`; }
    else { bb = `下轨区间（¥${bbL.toFixed(2)}～¥${bbM.toFixed(2)}）`; }
  }

  let volume = "";
  if (klines.length >= 5) {
    const avg5 = klines.slice(-5, -1).reduce((s, k) => s + k.volume, 0) / 4;
    const todayVol = klines[klines.length - 1].volume;
    const ratio = todayVol / (avg5 || 1);
    if (ratio > 2) volume = `放量 ${ratio.toFixed(1)}x（${klines[klines.length - 1].change_pct > 0 ? "放量上涨" : "放量下跌"}）`;
    else if (ratio < 0.5) volume = `缩量 ${ratio.toFixed(1)}x（整理）`;
    else volume = "量能正常";
  }

  const bullish = [trendColor === "red", macdColor === "red", rsiColor === "green" || rsiColor === "red", kdjColor === "red"].filter(Boolean).length;
  let summary = "技术面中性，震荡整理", summaryColor: "red" | "green" | "gray" = "gray";
  if (trendColor === "red" && macdColor === "red" && kdjColor === "red") { summary = "技术面强势多头，持仓偏积极"; summaryColor = "red"; }
  else if (trendColor === "green" && macdColor === "green") { summary = "技术面偏弱，空头格局压制"; summaryColor = "green"; }
  else if (rsiColor === "green" && kdjColor === "green") { summary = "超卖区域，关注技术性反弹机会"; summaryColor = "green"; }
  else if (bullish >= 3) { summary = "多项指标偏多，短期偏乐观"; summaryColor = "red"; }

  return { trend, trendColor, macd, macdColor, rsi: rsiText, rsiColor, kdj, kdjColor, bb, bbColor, volume, summary, summaryColor };
}

function buildDailyRows(indicators: Indicator[], klines: KlineBar[]) {
  const klineMap = new Map(klines.map((k) => [k.trade_date, k]));
  const sorted = indicators.slice(-7);
  return sorted.map((ind, idx) => {
    const bar = klineMap.get(ind.trade_date);
    const k = ind.kdj_k ?? 50, d = ind.kdj_d ?? 50;
    const hist = ind.macd_hist, rsi = ind.rsi_14;
    const bull = [hist != null && hist > 0, rsi != null && rsi > 50, k > d].filter(Boolean).length;
    const signal: "up" | "down" | "flat" = bull >= 2 ? "up" : bull <= 0 ? "down" : "flat";
    let conclusion = "震荡";
    if (hist != null && hist > 0 && k > d && rsi != null && rsi > 55) conclusion = "偏多";
    else if (hist != null && hist < 0 && k < d && rsi != null && rsi < 45) conclusion = "偏空";
    else if (rsi != null && rsi < 30) conclusion = "超卖";
    else if (rsi != null && rsi > 70) conclusion = "超买";
    // 筹码集中度变化（与前一日对比）
    const prevInd = idx > 0 ? sorted[idx - 1] : null;
    const concChange = (ind.chip_concentration != null && prevInd?.chip_concentration != null)
      ? ind.chip_concentration - prevInd.chip_concentration : null;
    return {
      date: ind.trade_date,
      close: bar?.close ?? 0,
      changePct: bar?.change_pct ?? 0,
      macdHist: hist,
      rsi14: rsi,
      kdj: `K${k.toFixed(0)}/D${d.toFixed(0)}`,
      conclusion,
      signal,
      chipProfitRatio: ind.chip_profit_ratio,
      chipConcentration: ind.chip_concentration,
      chipAvgCost: ind.chip_avg_cost,
      chipConcChange: concChange,
    };
  }).reverse();
}

// ─── 6 维度故事健康度评分 ──────────────────────────────────────────────────────

type DimColor = "red" | "green" | "gray" | "yellow";
interface DimScore {
  score: number | null;
  judgment: string;            // 短结论(≤30 字),从 dims.{d}.conclusion 或 hardcoded fallback 获取
  color: DimColor;
  evidence: string[];          // 短证据 bullets
  longText?: string;           // 100-300 字富文本分析,从 dims.{d}.text 取(可选)
}

const clamp10 = (n: number) => Math.max(1, Math.min(10, Math.round(n)));
const colorByScore = (s: number | null): DimColor =>
  s == null ? "gray" : s >= 7 ? "red" : s >= 5 ? "yellow" : "green";
const dimBorder = (c: DimColor) =>
  c === "red" ? "border-l-[#ef5350]" : c === "green" ? "border-l-[#26a69a]" : c === "yellow" ? "border-l-yellow-400" : "border-l-gray-700";
const dimText = (c: DimColor) =>
  c === "red" ? "text-[#ef5350]" : c === "green" ? "text-[#26a69a]" : c === "yellow" ? "text-yellow-400" : "text-gray-600";

interface FundLike {
  pe_ttm?: number | null; pb?: number | null; pe_percentile?: number | null;
  industry_pe_median?: number | null; gross_margin?: number | null;
  net_margin?: number | null; roe?: number | null; revenue_yoy?: number | null;
  profit_yoy?: number | null; cash_flow_ratio?: number | null;
  debt_ratio?: number | null;
}

// 纯财务公式计算护城河分（不依赖 Claude，用于「首页公式分」对比行）
function dim3FormulaScore(fund: FundLike | null | undefined): number | null {
  if (!fund || (fund.gross_margin == null && fund.roe == null)) return null;
  const gm = fund.gross_margin ?? 0;
  const roe = fund.roe ?? 0;
  const nm = fund.net_margin ?? 0;
  let s = 5;
  if (gm > 40) s += 2;
  else if (gm > 25) s += 1;
  else if (gm > 0 && gm < 15) s -= 1;
  if (roe > 20) s += 2;
  else if (roe > 12) s += 1;
  else if (roe > 0 && roe < 5) s -= 1;
  if (nm > 15) s += 1;
  if (fund.debt_ratio != null && fund.debt_ratio > 70) s -= 1;
  return clamp10(s);
}

function buildDim3Moat(
  fund: FundLike | null | undefined,
  report: { full_report?: Record<string, unknown> | null } | null | undefined,
): DimScore {
  const claude = claudeScoreFromReport(report, "claude_moat_score");
  const { text: longText, conclusion } = dimRichText(report, "d3");

  // 优先使用 Claude 评分（与 dim1/dim2/dim8/tech 保持一致）
  if (claude != null) {
    let j = conclusion ?? "护城河中等";
    if (!conclusion) {
      if (claude >= 8) j = "护城河稳固，毛利率 + ROE 双优";
      else if (claude >= 6) j = "护城河良好，盈利质量稳健";
      else if (claude <= 3) j = "护城河承压，需关注盈利质量恶化";
    }
    return { score: claude, judgment: j, color: colorByScore(claude), evidence: longText ? [] : ["来源: Claude 6D 评分"], longText: longText ?? undefined };
  }

  // Fallback：财务指标公式
  if (!fund || (fund.gross_margin == null && fund.roe == null)) {
    return { score: null, judgment: "财务数据不足，护城河暂无法评估", color: "gray", evidence: [] };
  }
  const gm = fund.gross_margin ?? 0;
  const roe = fund.roe ?? 0;
  const nm = fund.net_margin ?? 0;
  let s = 5;
  const ev: string[] = [];
  if (gm > 40) { s += 2; ev.push(`毛利率 ${gm.toFixed(1)}% 处于高毛利区间（>40%）`); }
  else if (gm > 25) { s += 1; ev.push(`毛利率 ${gm.toFixed(1)}% 中等水平`); }
  else if (gm > 0 && gm < 15) { s -= 1; ev.push(`毛利率仅 ${gm.toFixed(1)}%，溢价能力偏弱`); }
  if (roe > 20) { s += 2; ev.push(`ROE ${roe.toFixed(1)}% 显著高于平均（>20%）`); }
  else if (roe > 12) { s += 1; ev.push(`ROE ${roe.toFixed(1)}% 良好`); }
  else if (roe > 0 && roe < 5) { s -= 1; ev.push(`ROE 仅 ${roe.toFixed(1)}%，资本回报偏低`); }
  if (nm > 15) { s += 1; ev.push(`净利率 ${nm.toFixed(1)}% 高于一般水平`); }
  if (fund.debt_ratio != null) {
    if (fund.debt_ratio > 70) { s -= 1; ev.push(`资产负债率 ${fund.debt_ratio.toFixed(1)}% 偏高,需关注偿债压力`); }
    else if (fund.debt_ratio < 40) { ev.push(`资产负债率 ${fund.debt_ratio.toFixed(1)}% 稳健`); }
    else { ev.push(`资产负债率 ${fund.debt_ratio.toFixed(1)}% 中等`); }
  }
  s = clamp10(s);
  let j = "护城河中等";
  if (s >= 8) j = "护城河稳固，毛利率 + ROE 双优";
  else if (s >= 6) j = "护城河良好，盈利质量稳健";
  else if (s <= 3) j = "护城河承压，需关注盈利质量恶化";
  return { score: s, judgment: j, color: colorByScore(s), evidence: ev };
}

// buildDim4Odds 已删除(2026-05):D4 动态赔率不再独立成段,远期 PE/PEG/PE 历史分位等
// 所有估值指标已并入"主决策依据·估值赔率"段。
// buildDim5Performance 已删除(2026-05):业绩兑现节奏并入 D3 护城河,
// 财报预期差追踪面板搬至 D3 section,YoY/现金流/负债率等指标继续作为 buildDim3Moat evidence。

interface ReportLike {
  overall_signal?: string | null;
  technical_score?: number | null;
  fundamental_score?: number | null;
  conclusion?: string | null;
  full_report?: { catalysts?: string[]; risks?: string[]; suggestion?: string } | null;
}

// 通用：从 Claude full_report 取出某维度分（若有,优先使用）
function claudeScoreFromReport(
  report: { full_report?: Record<string, unknown> | null } | null | undefined,
  field: string,
): number | null {
  const v = (report?.full_report as Record<string, unknown> | undefined)?.[field];
  return typeof v === "number" ? v : null;
}

// 从 full_report.dims.{key} 嵌套结构读取 6D 富文本(2026-05 6D 框架升级)
// 若内容是占位符 "[6D 迁移占位]" 则返回 null,让上层 fallback 到 hardcoded judgment
function dimRichText(
  report: { full_report?: Record<string, unknown> | null } | null | undefined,
  key: "d1" | "d2" | "d3" | "d4" | "d5" | "d8",
): { text: string | null; conclusion: string | null } {
  const dims = (report?.full_report as Record<string, unknown> | undefined)?.["dims"] as
    | Record<string, { text?: string; conclusion?: string }>
    | undefined;
  const d = dims?.[key];
  if (!d) return { text: null, conclusion: null };
  const text = typeof d.text === "string" && !d.text.startsWith("[6D 迁移占位]") ? d.text : null;
  const conclusion = typeof d.conclusion === "string" && !d.conclusion.startsWith("需 6D") && d.conclusion !== "需 Claude 6D 框架补充" ? d.conclusion : null;
  return { text, conclusion };
}

// 维度 1 行业拐点+叙事:优先读 dims.d1 富文本,fallback 到 hardcoded
function buildDim1Industry(report: ReportLike | null | undefined): DimScore {
  const claude = claudeScoreFromReport(report, "claude_industry_score");
  const { text: longText, conclusion } = dimRichText(report, "d1");

  if (claude == null) {
    return {
      score: null,
      judgment: "需结合上游 capex / 行业月度数据综合判断（暂无 Claude 评分）",
      color: "gray",
      evidence: [
        "建议查询 industry_metrics（NVDA / GOOGL / META / MSFT / AMZN capex 与 datacenter 收入）",
        "或在 Claude 对话中按 6D 框架打分",
      ],
    };
  }
  let j = conclusion ?? "行业景气中性";
  if (!conclusion) {
    if (claude >= 8) j = "行业需求加速,上行明确";
    else if (claude >= 6) j = "行业景气向好,但加速度不明显";
    else if (claude <= 3) j = "行业景气走弱,警惕拐点";
  }
  return {
    score: claude,
    judgment: j,
    color: colorByScore(claude),
    evidence: longText ? [] : ["来源: Claude 6D 评分"],
    longText: longText ?? undefined,
  };
}

function buildDim2Disruption(report: ReportLike | null | undefined): DimScore {
  const claude = claudeScoreFromReport(report, "claude_disruption_score");
  const { text: longText, conclusion } = dimRichText(report, "d2");

  if (claude == null) {
    return {
      score: null,
      judgment: "需识别政策/地缘/颠覆性技术信号（暂无 Claude 评分）",
      color: "gray",
      evidence: ["参考右侧『催化剂』与『关键风险』,或在 Claude 对话中按 6D 框架打分"],
    };
  }
  let j = conclusion ?? "外部环境中性";
  if (!conclusion) {
    if (claude >= 8) j = "重大政策利好,公司核心受益";
    else if (claude >= 6) j = "政策环境改善,间接受益";
    else if (claude <= 3) j = "出口管制/关税/技术替代构成结构性压力";
  }
  return {
    score: claude,
    judgment: j,
    color: colorByScore(claude),
    evidence: longText ? [] : ["来源: Claude 6D 评分"],
    longText: longText ?? undefined,
  };
}

// 注意:旧 D5/D7 已并入 D3 护城河(2026-05);claude_performance_score 仍由 Claude 6D 框架产出,
// 在自选股表格 ⑤ 业绩·财务列与 ReportPanel 显示,仅作为护城河可持续性的 evidence 信号。

// 维度 8 治理:无本地公式,仅用 Claude 数据
function buildDim8Governance(report: ReportLike | null | undefined): DimScore {
  const claude = claudeScoreFromReport(report, "claude_governance_score");
  if (claude == null) {
    return {
      score: null,
      judgment: "需识别大股东行为/分红/关联交易（暂无 Claude 评分）",
      color: "gray",
      evidence: ["参考 insider_trades 表与公告,或在 Claude 对话中按 6D 框架打分"],
    };
  }
  let j = "治理稳健";
  if (claude >= 8) j = "大股东增持 + 高分红 + 无关联交易黑历史";
  else if (claude <= 3) j = "高位减持 / 频繁关联交易 / 商誉爆雷历史";
  return { score: claude, judgment: j, color: colorByScore(claude), evidence: ["来源: Claude 6D 评分"] };
}

// 注意:旧 D6 叙事时间窗口已并入 D1(行业拐点+叙事合并),buildDim1Industry 直接读 claude_industry_score 即可

// 技术评估段(2026-05 新增):优先用 Claude 评分,否则用 report.technical_score 推算
function buildDimTech(report: ReportLike | null | undefined): DimScore {
  const claude = claudeScoreFromReport(report, "claude_tech_score");
  if (claude != null) {
    let j = "技术面中性";
    if (claude >= 8) j = "趋势向上 + 量能配合 + 筹码偏低位";
    else if (claude <= 3) j = "破位 + 量能萎缩 + 高位获利盘套牢";
    return { score: claude, judgment: j, color: colorByScore(claude), evidence: ["来源: Claude 6D 评分"] };
  }
  if (!report?.technical_score) {
    return {
      score: null,
      judgment: "需识别 K 线 / 筹码 / 60-90d 动量(暂无 Claude 评分)",
      color: "gray",
      evidence: ["参考左侧 K 线 + 筹码图,或在 Claude 对话中按 6D 框架打分"],
    };
  }
  const s = clamp10(report.technical_score);
  let j = "技术面中性";
  if (s >= 8) j = "趋势向上 + 量能配合";
  else if (s <= 3) j = "破位 + 杀跌";
  return { score: s, judgment: j, color: colorByScore(s), evidence: [`技术评分 ${s}/10(来自 AI 报告)`] };
}

// ─── 维度卡片 ─────────────────────────────────────────────────────────────────

// 内联 markdown 渲染:支持 **粗体** 标记,其他文本原样输出 + 保留换行
function renderMarkdownInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /\*\*([^*]+?)\*\*/g;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIdx) {
      nodes.push(text.slice(lastIdx, m.index));
    }
    nodes.push(
      <strong key={`b${key++}`} className="font-semibold text-gray-900">
        {m[1]}
      </strong>,
    );
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < text.length) nodes.push(text.slice(lastIdx));
  return nodes;
}

function DimensionHeader({ index, title, tier, dim }: {
  index: number; title: string; tier?: 1 | 2 | 3; dim: DimScore;
}) {
  const circled = ["①", "②", "③", "④", "⑤", "⑥"][index - 1];
  return (
    <Card className={clsx("border-l-2", dimBorder(dim.color))}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-base font-bold text-gray-800">{circled}</span>
          <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
          {tier === 1 && <Tag color="red">Tier 1</Tag>}
          {tier === 2 && <Tag color="yellow">Tier 2</Tag>}
        </div>
        {dim.score != null ? (
          <span className={clsx("text-lg font-bold tabular-nums shrink-0", dimText(dim.color))}>
            {dim.score}<span className="text-xs text-gray-500">/10</span>
          </span>
        ) : (
          <span className="text-xs text-gray-400 shrink-0">— / 10</span>
        )}
      </div>
      <p className={clsx("text-sm leading-snug font-medium", dimText(dim.color))}>{dim.judgment}</p>
      {dim.longText && (
        <p className="mt-2 text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
          {renderMarkdownInline(dim.longText)}
        </p>
      )}
      {dim.evidence.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {dim.evidence.map((e, i) => (
            <li key={i} className="text-xs text-gray-500">· {e}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ─── 可编辑值 ─────────────────────────────────────────────────────────────────

function EditableValue({ label, value, unit, onSave }: {
  label: string; value: number | null; unit?: string; onSave: (v: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const start = () => { setDraft(value != null ? String(value) : ""); setEditing(true); };
  const commit = async () => {
    const n = parseFloat(draft);
    if (!isNaN(n) && n !== value) { setSaving(true); try { await onSave(draft); } finally { setSaving(false); } }
    setEditing(false);
  };
  return (
    <div>
      <p className="text-xs text-gray-500 mb-0.5">{label}</p>
      {editing ? (
        <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)}
          onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(false); }}
          className="w-full bg-[#f0f3f6] border border-[#58a6ff] rounded px-2 py-1 text-sm text-gray-900 outline-none" disabled={saving} />
      ) : (
        <div onClick={start} className="flex items-center gap-1 cursor-text group">
          <p className="text-base font-semibold text-gray-800">
            {value != null ? value : <span className="text-gray-400">—</span>}
            {value != null && unit && <span className="text-xs text-gray-500 ml-1">{unit}</span>}
          </p>
          <span className="opacity-0 group-hover:opacity-40 text-xs text-gray-600">✎</span>
        </div>
      )}
    </div>
  );
}

// ─── 指标卡片 ─────────────────────────────────────────────────────────────────

function IndicatorItem({ icon, label, text, color }: {
  icon: string; label: string; text: string; color: "red" | "green" | "gray" | "yellow";
}) {
  const border = { red: "border-l-[#ef5350]", green: "border-l-[#26a69a]", yellow: "border-l-yellow-400", gray: "border-l-gray-700" }[color];
  const textCls = { red: "text-[#ef5350]", green: "text-[#26a69a]", yellow: "text-yellow-400", gray: "text-gray-600" }[color];
  return (
    <div className={clsx("bg-[#f6f8fa] rounded-lg p-3 border-l-2", border)}>
      <p className="text-xs text-gray-500 mb-1">{icon} {label}</p>
      <p className={clsx("text-sm font-medium leading-snug", textCls)}>{text}</p>
    </div>
  );
}

function ScoreBar({ label, score }: { label: string; score: number | null }) {
  const pct = score != null ? score * 10 : 0;
  const color = score != null ? (score >= 7 ? "#ef5350" : score >= 4 ? "#ff9800" : "#26a69a") : "#555";
  return (
    <div className="text-center min-w-[60px]">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-lg font-bold" style={{ color }}>{score ?? "—"}</p>
      <div className="h-1 bg-gray-100 rounded-full overflow-hidden mt-1">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

// ─── 主组件 ───────────────────────────────────────────────────────────────────

export function StockDetailView({ code }: { code: string }) {
  const { data: stock } = useSWR(`stock-${code}`, () => stocksApi.get(code));
  const { data: fund } = useSWR(`fundamental-${code}`, () => analysisApi.fundamental(code));
  const { data: report, mutate: mutateReport } = useSWR(`report-latest-${code}`, () =>
    analysisApi.latestReport(code).catch(() => null));
  const { data: chip } = useSWR(`chip-${code}`, () => analysisApi.chip(code).catch(() => null));
  const { data: divergences } = useSWR(`divergence-${code}`, () =>
    analysisApi.divergence(code, 60).catch(() => []));
  const { data: indicators } = useSWR(`indicators-${code}-30`, () => klineApi.indicators(code, 30));
  const { data: klines } = useSWR(`kline-${code}-30`, () => klineApi.daily(code, 30));
  const { data: targetPrice } = useSWR(`target-price-realtime-${code}`, () =>
    targetPriceApi.forStock(code).catch(() => null));

  const [refreshing, setRefreshing] = useState(false);
  const [llmLoading, setLlmLoading] = useState(false);
  const [recalcLoading, setRecalcLoading] = useState(false);
  const [recalcMsg, setRecalcMsg] = useState<string | null>(null);

  const handleRefreshReport = async () => {
    setRefreshing(true);
    await analysisApi.refreshReport(code);
    setTimeout(() => { mutateReport(); setRefreshing(false); }, 3000);
  };

  const handleRecalc = async () => {
    setRecalcLoading(true);
    setRecalcMsg(null);
    try {
      const res = await klineApi.recalc(code);
      setRecalcMsg(`完成：K线+${res.klines_saved}条，指标+${res.indicators_saved}条`);
      // 重新拉取指标和K线
      globalMutate(`indicators-${code}-30`);
      globalMutate(`kline-${code}-30`);
      globalMutate(`chip-${code}`);
      setTimeout(() => setRecalcMsg(null), 5000);
    } catch {
      setRecalcMsg("重算失败，请查看后端日志");
    } finally {
      setRecalcLoading(false);
    }
  };

  const handleLLMForecast = async () => {
    setLlmLoading(true);
    try {
      await tableApi.generateLLMForecast(code);
      globalMutate("watchlist-table");
      globalMutate(`fundamental-${code}`);
    } finally { setLlmLoading(false); }
  };

  const saveForecast = useCallback(async (year: number, val: string) => {
    const n = parseFloat(val);
    if (isNaN(n) || n <= 0) return;
    await tableApi.updateForecast(code, year, n);
    globalMutate("watchlist-table");
    globalMutate(`fundamental-${code}`);
  }, [code]);

  // 计算派生值
  const techConclusion = indicators && klines ? buildTechConclusion(indicators, klines) : null;
  const dailyRows = indicators && klines ? buildDailyRows(indicators, klines) : [];
  const signal = report?.overall_signal ?? "neutral";
  const signalMap = { bullish: { label: "看多", color: "red" as const }, bearish: { label: "看空", color: "green" as const }, neutral: { label: "中性", color: "gray" as const } };
  const signalInfo = signalMap[signal];

  const f26 = fund?.forecasts.find((f) => f.forecast_year === 2026);
  const f27 = fund?.forecasts.find((f) => f.forecast_year === 2027);
  const np26 = f26?.net_profit_forecast != null ? f26.net_profit_forecast / 1e8 : null;
  const np27 = f27?.net_profit_forecast != null ? f27.net_profit_forecast / 1e8 : null;
  const mktCap = fund?.market_cap ?? null;
  // 远期 PE 双轨:研报反算 + 同花顺一致预期(profit_forecasts.forward_pe)— 都展示让用户对比
  const researchPE26 = targetPrice?.institution_breakdown?.weighted_forward_pe_y1 ?? null;
  const researchPE27 = targetPrice?.institution_breakdown?.weighted_forward_pe_y2 ?? null;
  const thsPE26 = f26?.forward_pe ?? (mktCap && np26 && np26 > 0 ? mktCap / np26 : null);
  const thsPE27 = f27?.forward_pe ?? (mktCap && np27 && np27 > 0 ? mktCap / np27 : null);
  // 兼容旧用法(取一个主值给 peColor 着色) — 研报优先, fallback 共识
  const fwdPE26 = researchPE26 != null ? Math.round(researchPE26) :
                  thsPE26 != null ? Math.round(thsPE26) : null;
  const fwdPE27 = researchPE27 != null ? Math.round(researchPE27) :
                  thsPE27 != null ? Math.round(thsPE27) : null;
  const peg = fund?.pe_ttm && fund?.profit_yoy && fund.profit_yoy > 0 ? +(fund.pe_ttm / fund.profit_yoy).toFixed(2) : null;
  const latestClose = klines?.length ? klines[klines.length - 1].close : null;
  const high30 = klines?.length ? Math.max(...klines.map((k) => k.high)) : null;
  const low30 = klines?.length ? Math.min(...klines.map((k) => k.low)) : null;

  const chipSummary = (() => {
    if (!chip) return null;
    const pr = chip.profit_ratio ?? 0, conc = chip.concentration ?? 0, avg = chip.avg_cost ?? 0, cur = latestClose ?? 0;
    const parts: string[] = [];
    if (pr > 75) parts.push(`获利盘 ${(pr * 100).toFixed(0)}%，上方压力较大`);
    else if (pr < 30) parts.push(`获利盘仅 ${(pr * 100).toFixed(0)}%，套牢盘沉重`);
    else parts.push(`获利盘 ${(pr * 100).toFixed(0)}%，结构尚可`);
    if (conc > 70) parts.push("筹码高度集中");
    else if (conc < 40) parts.push("筹码分散充分");
    if (avg > 0 && cur > 0) {
      const diff = ((cur - avg) / avg * 100).toFixed(1);
      parts.push(`均匀成本 ¥${avg.toFixed(2)}，${+diff > 0 ? "溢价" : "折价"} ${Math.abs(+diff)}%`);
    }
    return parts.join("；");
  })();

  // ── 4D + 技术评分(2026-05 精简版:Tier 加权 + Veto 否决,D4 动态赔率已并入主决策依据,D5 业绩兑现已并入 D3 护城河) ──
  const reportLike = report as ReportLike | null | undefined;
  const dim1 = buildDim1Industry(reportLike);            // D1' 行业拐点 + 叙事(合并)
  const dim2 = buildDim2Disruption(reportLike);
  const dim3 = buildDim3Moat(fund as FundLike | null | undefined, reportLike);
  const dim8 = buildDim8Governance(reportLike);
  const dimTech = buildDimTech(reportLike);              // 技术评估

  // 首页公式分：始终用纯财务指标（用于"公式分 vs Claude 6D"对比行）
  const formulaScore = dim3FormulaScore(fund as FundLike | null | undefined);
  const hasClaudeScore =
    report?.full_report?.claude_overall_score != null;

  // Tier 加权综合分(D4/D5 已移除)
  // raw = 0.55 × D3 + 0.30 × mean(D1', D2) + 0.05 × D8 + 0.10 × tech
  const meanOf = (...nums: (number | null)[]): number | null => {
    const xs = nums.filter((v): v is number => v != null);
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
  };
  const coreAvg = dim3.score;
  const industryAvg = meanOf(dim1.score, dim2.score);
  const governanceScore = dim8.score;
  const techScore = dimTech.score;
  let weightedSum = 0;
  let weightTotal = 0;
  if (coreAvg != null) { weightedSum += 0.55 * coreAvg; weightTotal += 0.55; }
  if (industryAvg != null) { weightedSum += 0.30 * industryAvg; weightTotal += 0.30; }
  if (governanceScore != null) { weightedSum += 0.05 * governanceScore; weightTotal += 0.05; }
  if (techScore != null) { weightedSum += 0.10 * techScore; weightTotal += 0.10; }
  let overallScore: number | null = weightTotal > 0 ? weightedSum / weightTotal : null;

  // Veto 否决:Tier 1 基本面(D3 护城河) ≤ 2,综合分压低至 ≤ 4.0
  const vetoFromClaude = report?.full_report?.veto_triggered === true;
  const vetoLocal = dim3.score != null && dim3.score <= 2;
  const vetoTriggered = vetoFromClaude || vetoLocal;
  const vetoReason =
    report?.full_report?.veto_reason ||
    (vetoLocal ? "本地检测: D3 护城河 ≤ 2" : null);
  if (vetoTriggered && overallScore != null) {
    overallScore = Math.min(overallScore, 4.0);
  }
  if (overallScore != null) overallScore = +overallScore.toFixed(1);

  // Prefer the exact overall_score Claude wrote during analysis (Step 7 write-back)
  const claudeOverallScore = hasClaudeScore
    ? +(report!.full_report!.claude_overall_score as number).toFixed(1)
    : null;
  const claudeOverallLabel =
    (report?.full_report?.claude_overall_label as string | null | undefined) ?? null;
  if (claudeOverallScore != null) overallScore = claudeOverallScore;

  const validDimCount =
    [dim1, dim2, dim3, dim8, dimTech].filter((d) => d.score != null).length;
  // 2026-05 阈值偏移升级:≥7.5 强烈看好 / 6.5-7.4 看好 / 5.5-6.4 中性 / 3.5-5.4 看淡 / <3.5 强烈看淡
  const overallJudgment = claudeOverallLabel ?? (
    overallScore == null ? "—"
      : overallScore >= 7.5 ? "强烈看好"
      : overallScore >= 6.5 ? "看好"
      : overallScore >= 5.5 ? "中性"
      : overallScore >= 3.5 ? "看淡"
      : "强烈看淡"
  );
  const overallColorCls =
    overallScore == null ? "text-gray-600"
      : overallScore >= 6.5 ? "text-[#ef5350]"
      : overallScore >= 5.5 ? "text-yellow-400"
      : "text-[#26a69a]";

  return (
    <div className="flex h-[calc(100vh-32px)]">
      {/* ── 左侧主内容 ─────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto pr-6 min-w-0">

        {/* 顶栏 */}
        <div className="sticky top-0 z-10 bg-white border-b border-gray-200 py-3 mb-5 -mx-1 px-1">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <Link href="/" className="text-sm text-gray-500 hover:text-gray-700 transition-colors">← 返回</Link>
                <h1 className="text-xl font-bold text-gray-900">{stock?.name ?? code}</h1>
                <span className="text-gray-500 text-sm">{code}</span>
                <Tag color="blue">{stock?.market === "A" ? "A股" : "港股"}</Tag>
                {stock?.industry && <Tag>{stock.industry}</Tag>}
              </div>
              <div className="flex items-center gap-4">
                {latestClose && <span className="text-2xl font-bold text-gray-900">¥{latestClose.toFixed(2)}</span>}
                {klines && klines.length > 0 && (
                  <span className={clsx("text-sm font-medium", klines[klines.length - 1].change_pct >= 0 ? "text-[#ef5350]" : "text-[#26a69a]")}>
                    {klines[klines.length - 1].change_pct >= 0 ? "+" : ""}{klines[klines.length - 1].change_pct.toFixed(2)}%
                  </span>
                )}
                {mktCap && <span className="text-sm text-gray-500">市值 {mktCap.toFixed(0)}亿</span>}
                {report && <Tag color={signalInfo.color}>{signalInfo.label}</Tag>}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button onClick={handleRecalc} disabled={recalcLoading}
                className="text-xs px-3 py-1.5 bg-gray-100 text-gray-600 rounded hover:text-gray-800 disabled:opacity-50 transition-colors">
                {recalcLoading ? "重算中…" : "重算技术指标"}
              </button>
              <button onClick={handleRefreshReport} disabled={refreshing}
                className="text-xs px-3 py-1.5 bg-gray-100 text-gray-600 rounded hover:text-gray-800 disabled:opacity-50 transition-colors">
                {refreshing ? "生成中…" : "刷新AI报告"}
              </button>
            </div>
          </div>
          <div className="mt-2.5">
            <TagBar code={code} />
          </div>
          {recalcMsg && (
            <p className="text-xs mt-2 text-[#58a6ff]">{recalcMsg}</p>
          )}
        </div>

        {/* AI 综合结论(从 sticky 顶栏移出,避免滚动时遮挡其他段落) */}
        {report && (
          <section className="mb-5">
            <Card>
              <div className="flex items-center gap-4">
                <p className="text-sm text-gray-700 flex-1 leading-relaxed">
                  {report.conclusion}
                  {report.full_report?.suggestion && <span className="text-gray-500 ml-2 text-xs">{report.full_report.suggestion}</span>}
                </p>
                <div className="flex gap-3 shrink-0">
                  <ScoreBar label="技术" score={report.technical_score} />
                  <ScoreBar label="基本面" score={report.fundamental_score} />
                </div>
              </div>
            </Card>
          </section>
        )}

        {/* ━━━━━━━━━━━ 🎯 v5 主决策区:目标价上行空间 + 估值快照(原 D4 内容并入) ━━━━━━━━━━━ */}
        <section className="mb-6">
          <SectionTitle>🎯 主决策依据 · 机构目标价上行空间 + 估值赔率</SectionTitle>
          <TargetPricePanel code={code} />

          {/* 估值快照(从 D4 动态赔率合并:远期 PE / PEG 等同样源自机构研报) */}
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs tabular-nums px-3 py-2 bg-[#f6f8fa] border border-gray-200 rounded">
            <span className="text-xs font-semibold text-gray-700 mr-1">估值赔率</span>
            {[
              { label: "PE-TTM", value: fmt(fund?.pe_ttm, "x"), cls: peColor(fund?.pe_ttm) },
              { label: "PB", value: fmt(fund?.pb, "x"), cls: undefined },
              { label: "PEG", value: peg != null ? fmt(peg) : "—", cls: peg != null ? (peg < 1 ? "text-[#26a69a]" : peg > 1.5 ? "text-[#ef5350]" : "text-gray-700") : undefined },
              { label: "PE历史分位", value: fund?.pe_percentile != null ? `${fund.pe_percentile.toFixed(0)}%` : "—", cls: fund?.pe_percentile != null ? (fund.pe_percentile < 30 ? "text-[#26a69a]" : fund.pe_percentile > 70 ? "text-[#ef5350]" : "text-gray-700") : undefined },
              { label: "ROE", value: fmt(fund?.roe, "%"), cls: fund?.roe != null && fund.roe > 20 ? "text-[#ef5350]" : "text-gray-700" },
              { label: "市值", value: mktCap ? `${mktCap.toFixed(0)}亿` : "—", cls: "text-gray-700" },
            ].map((m) => (
              <span key={m.label} className="inline-flex items-baseline gap-1">
                <span className="text-gray-500">{m.label}</span>
                <span className={clsx("font-medium", m.cls)}>{m.value}</span>
              </span>
            ))}
            {/* 26 远期 PE — 双轨展示:研报反算 / 同花顺共识 */}
            <span className="inline-flex items-baseline gap-1">
              <span className="text-gray-500">26远期PE</span>
              {researchPE26 != null ? (
                <span title="研报 EPS 加权反算" className={clsx("font-medium", peColor(researchPE26))}>
                  研 {Math.round(researchPE26)}x
                </span>
              ) : null}
              {researchPE26 != null && thsPE26 != null && <span className="text-gray-300 mx-0.5">/</span>}
              {thsPE26 != null ? (
                <span title={`同花顺一致预期${f26?.analyst_count ? ` · ${f26.analyst_count} 家分析师` : ""}`} className={clsx("font-medium", peColor(thsPE26))}>
                  共 {Math.round(thsPE26)}x
                </span>
              ) : null}
              {researchPE26 == null && thsPE26 == null && <span className="text-gray-400">—</span>}
            </span>
            {/* 27 远期 PE — 双轨 */}
            <span className="inline-flex items-baseline gap-1">
              <span className="text-gray-500">27远期PE</span>
              {researchPE27 != null ? (
                <span title="研报 EPS 加权反算" className={clsx("font-medium", peColor(researchPE27))}>
                  研 {Math.round(researchPE27)}x
                </span>
              ) : null}
              {researchPE27 != null && thsPE27 != null && <span className="text-gray-300 mx-0.5">/</span>}
              {thsPE27 != null ? (
                <span title={`同花顺一致预期${f27?.analyst_count ? ` · ${f27.analyst_count} 家分析师` : ""}`} className={clsx("font-medium", peColor(thsPE27))}>
                  共 {Math.round(thsPE27)}x
                </span>
              ) : null}
              {researchPE27 == null && thsPE27 == null && <span className="text-gray-400">—</span>}
            </span>
          </div>

          {/* 价格区间 */}
          {high30 && low30 && latestClose && (
            <div className="mt-2 flex items-center gap-3 text-xs text-gray-500">
              <span className="text-[#26a69a] shrink-0">¥{low30.toFixed(2)}</span>
              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-[#26a69a] to-[#ef5350] rounded-full"
                  style={{ width: `${Math.min(100, Math.max(3, ((latestClose - low30) / (high30 - low30)) * 100))}%` }} />
              </div>
              <span className="text-[#ef5350] shrink-0">¥{high30.toFixed(2)}</span>
              <span className="text-gray-400">现价 ¥{latestClose.toFixed(2)} · 30日区间 {(((latestClose - low30) / (high30 - low30)) * 100).toFixed(0)}% 位</span>
            </div>
          )}
          {fund?.industry_pe_median != null && (
            <p className="text-xs text-gray-400 mt-2">
              行业PE中位 {fund.industry_pe_median.toFixed(1)}x
              {fund.pe_ttm != null && <span className={clsx("ml-1", fund.pe_ttm < fund.industry_pe_median ? "text-[#26a69a]" : "text-[#ef5350]")}>· {fund.pe_ttm < fund.industry_pe_median ? "低于" : "高于"}行业均值</span>}
              <span className="mx-2 text-gray-300">·</span>
              <span>英伟达 26 远期 PE 锚 ≈ 25-30x · PEG &gt; 1.5 应回避</span>
            </p>
          )}

          {/* 📈 机构共识修正趋势(从 D4 合并) */}
          <div className="mt-3 p-3 bg-[#f6f8fa] border border-gray-200 rounded-lg">
            <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-2">
              <span>📈 机构共识修正趋势</span>
              <span className="text-[10px] text-gray-400 font-normal">(月度 EPS / 净利 / 目标价 共识变化)</span>
            </h4>
            <EstimateRevisionsPanel code={code} />
          </div>
        </section>

        {/* ── Veto 警示带（基本面破坏/审计预警） ───────────── */}
        {vetoTriggered && (
          <div className="mb-5 px-4 py-3 bg-red-50 border border-red-400 rounded-lg">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-red-700 font-bold text-sm">⚠ Veto 触发</span>
              <span className="text-red-600 text-xs">
                {vetoReason || "基本面破坏,综合分已强制压低至 ≤ 4.0"}
              </span>
            </div>
          </div>
        )}

        {/* ── 故事健康度 · 4D + 技术评分总览(D4 动态赔率并入主决策依据,D5 业绩兑现并入 D3 护城河) ─────── */}
        <section className="mb-7">
          <SectionTitle>故事健康度 · 4D + 技术评分总览（Tier 加权 + Veto）</SectionTitle>
          <Card>
            <div className="grid grid-cols-3 sm:grid-cols-5 gap-3">
              <ScoreBar label="① 行业+叙事" score={dim1.score} />
              <ScoreBar label="② 外部力量" score={dim2.score} />
              <ScoreBar label="③ 护城河" score={dim3.score} />
              <ScoreBar label="⑧ 治理" score={dim8.score} />
              <ScoreBar label="📊 技术" score={dimTech.score} />
            </div>
            {overallScore != null && (
              <div className="border-t border-gray-200 mt-4 pt-3 flex items-center justify-between">
                <p className="text-xs text-gray-500">
                  综合评分({validDimCount} / 5 段)· Tier1 基本面(D3)55% + 行业(D1/D2)30% + 治理 5% + 技术 10%
                  {vetoTriggered && <span className="text-red-400 ml-2">· Veto 已应用</span>}
                </p>
                <p className={clsx("text-2xl font-bold tabular-nums", overallColorCls)}>
                  {overallScore.toFixed(1)}
                  <span className="text-sm text-gray-500 ml-2 font-medium">{overallJudgment}</span>
                </p>
              </div>
            )}

            {/* 历史评分对比:首页公式分 vs Claude 6D 综合分（提升评分透明度） */}
            {formulaScore != null && overallScore != null && hasClaudeScore && (
              <div className="border-t border-gray-200 mt-3 pt-3">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <p className="text-xs text-gray-500 mb-1">📊 评分对比</p>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="text-gray-600">
                        首页公式分 <span className="text-gray-700 font-medium tabular-nums">{formulaScore.toFixed(1)}</span>
                      </span>
                      <span className="text-gray-400">→</span>
                      <span className={clsx(overallColorCls, "font-medium")}>
                        Claude 6D <span className="font-bold tabular-nums">{overallScore.toFixed(1)}</span>
                      </span>
                      {Math.abs(overallScore - formulaScore) >= 0.5 && (
                        <span className={clsx(
                          "text-xs px-2 py-0.5 rounded",
                          overallScore > formulaScore ? "bg-[#ef5350]/15 text-[#ef5350]" : "bg-[#26a69a]/15 text-[#26a69a]"
                        )}>
                          {overallScore > formulaScore ? "+" : ""}{(overallScore - formulaScore).toFixed(1)}
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-gray-400 max-w-md leading-relaxed">
                    首页公式仅看 TTM 静态数据;Claude 6D 综合 web search 最新动态(季报/研报/治理)+ Tier 加权 + Veto。
                    {Math.abs(overallScore - formulaScore) >= 0.5 && " 显著差异提示边际信息尚未反映到 TTM 字段。"}
                  </p>
                </div>
              </div>
            )}
          </Card>
        </section>

        {/* ── 维度 1：行业需求拐点 + 上游价格弹性 ───────────── */}
        <section className="mb-5">
          <DimensionHeader index={1} title="行业需求拐点 + 上游价格弹性" tier={1} dim={dim1} />
          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            评估行业需求是否处于上行加速期、上游原材料价格弹性、需求是结构性还是周期性。
            建议关注：北美 CSP 资本开支指引、三星/海力士月度合约价、行业月度数据。
          </p>
        </section>

        {/* ── 维度 2：外部颠覆力量 ─────────────────────────── */}
        <section className="mb-5">
          <DimensionHeader index={2} title="外部颠覆力量（政策 / 地缘 / 技术）" dim={dim2} />
          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            评估重大政策利好/利空、出口管制、产业补贴、地缘政治、颠覆性新技术对公司的影响。
          </p>
        </section>

        {/* ── 维度 3：护城河变化 ───────────────────────────── */}
        <section className="mb-5">
          <DimensionHeader index={3} title="护城河变化（毛利率 · ROE · 客户结构）" tier={1} dim={dim3} />

          {/* 🛡️ 护城河变动子卡 — 季度毛利率/ROE 环比走势 */}
          <div className="mt-3 mb-3 p-3 bg-[#f6f8fa] border border-gray-200 rounded-lg">
            <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-2">
              <span>🛡️ 护城河变动追踪</span>
              <span className="text-[10px] text-gray-400 font-normal">(季度毛利率/ROE 环比走势)</span>
            </h4>
            <MoatChangePanel code={code} />
          </div>

          {/* 📅 财报预期差追踪(2026-05 并入护城河:验证盈利可持续性) */}
          <div className="mt-3 mb-3 p-3 bg-[#f6f8fa] border border-gray-200 rounded-lg">
            <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-2">
              <span>📅 财报预期差追踪</span>
              <span className="text-[10px] text-gray-400 font-normal">(一致预期 vs 实际 vs 股价反应)</span>
            </h4>
            <EarningsTrackPanel code={code} />
          </div>

          {/* 上下游供应商已迁移至独立的全局供应链页面(/supply-chain),便于跨自选股关联 */}
          <p className="text-xs text-gray-400 mt-3 leading-relaxed">
            上下游供应商关系已迁移至 <Link href="/supply-chain" className="text-[#58a6ff] hover:underline">📊 全局供应链图</Link>,
            可查看自选股按行业聚簇的整体上下游链路。
          </p>
        </section>

        {/* ── 维度 4 动态赔率已并入"主决策依据·估值赔率"段(2026-05) ── */}

        {/* ── 维度 5 业绩兑现节奏已删除(2026-05):财报预期差追踪并入 D3 护城河;其余 YoY/现金流指标已通过 buildDim3Moat evidence 输出 ── */}

        {/* ── 维度 8：治理与资本配置（调整项） ───────────── */}
        <section className="mb-5">
          <DimensionHeader index={8} title="治理与资本配置（大股东行为 · 分红回购 · 关联交易）" dim={dim8} />
          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            子项加权:大股东行为 40% · 回购分红 30% · 关联交易 20% · 信披透明度 10%
            {dim8.score == null && " · 当前无 Claude 评分,可在对话中按 6D 框架打分"}
          </p>
        </section>

        {/* ── 技术形态 · 择时辅助(2026-05 整合:原 6D 末"技术评估"段已并入此处,score+判断显示在标题右侧) ── */}
        <section className="mb-7" data-section="tech-form">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <span className="w-1 h-4 bg-[#58a6ff] rounded-full shrink-0" />
              📊 技术形态 · 择时辅助
              <span className="ml-1 text-xs text-yellow-400/80">Tier 2</span>
              <span className="ml-2 text-[10px] text-gray-400 font-normal">
                (K 线 + 筹码 + 60-90d 动量 · 子项加权 MACD/KDJ/RSI 25% · 均线 20% · 筹码 20% · 60d 动量 25% · 量能 10%)
              </span>
            </h2>
            <div className="flex items-center gap-2 shrink-0">
              {dimTech.score != null ? (
                <span className={clsx("text-base font-bold tabular-nums", dimText(dimTech.color))}>
                  {dimTech.score}<span className="text-xs text-gray-500">/10</span>
                </span>
              ) : (
                <span className="text-xs text-gray-400">— / 10</span>
              )}
              <span className={clsx("text-xs font-medium", dimText(dimTech.color))}>{dimTech.judgment}</span>
            </div>
          </div>
          {techConclusion ? (
            <div className="space-y-3">
              <Card className="border-l-2 border-l-[#58a6ff]">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-gray-900 mb-1">{techConclusion.summary}</p>
                    {report?.full_report?.technical_analysis && (
                      <p className="text-sm text-gray-600 leading-relaxed">{report.full_report.technical_analysis}</p>
                    )}
                  </div>
                  {(report?.full_report?.support_level || report?.full_report?.resistance_level) && (
                    <div className="shrink-0 text-right space-y-2">
                      {report.full_report.resistance_level && <div><p className="text-xs text-gray-500">压力位</p><p className="text-sm font-bold text-[#ef5350]">¥{Number(report.full_report.resistance_level).toFixed(2)}</p></div>}
                      {report.full_report.support_level && <div><p className="text-xs text-gray-500">支撑位</p><p className="text-sm font-bold text-[#26a69a]">¥{Number(report.full_report.support_level).toFixed(2)}</p></div>}
                    </div>
                  )}
                </div>
              </Card>

              <div className="grid grid-cols-2 xl:grid-cols-3 gap-2">
                <IndicatorItem icon="📈" label="趋势（均线）" text={techConclusion.trend} color={techConclusion.trendColor} />
                <IndicatorItem icon="⚡" label="动能（MACD）" text={techConclusion.macd} color={techConclusion.macdColor} />
                <IndicatorItem icon="🌡" label="超买超卖（RSI）" text={techConclusion.rsi} color={techConclusion.rsiColor as "red" | "green" | "gray"} />
                <IndicatorItem icon="🔄" label="随机指标（KDJ）" text={techConclusion.kdj} color={techConclusion.kdjColor} />
                <IndicatorItem icon="📊" label="波动（布林带）" text={techConclusion.bb} color={techConclusion.bbColor} />
                {techConclusion.volume && <IndicatorItem icon="💧" label="成交量" text={techConclusion.volume} color="gray" />}
              </div>

              {/* 近7日日报 */}
              {dailyRows.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1.5">近期日度快照</p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-gray-200 text-gray-500">
                          {["日期","收盘","涨跌","MACD柱","RSI14","KDJ","获利盘","集中度","结论"].map(h => (
                            <th key={h} className={clsx("py-1.5 px-2 font-normal", h === "日期" ? "text-left" : "text-right", h === "结论" && "text-center")}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {dailyRows.map((row) => (
                          <tr key={row.date} className="border-b border-gray-200 hover:bg-black/[0.02]">
                            <td className="py-1.5 px-2 text-gray-500">{row.date.slice(5)}</td>
                            <td className="py-1.5 px-2 text-right text-gray-700 tabular-nums">{row.close > 0 ? row.close.toFixed(2) : "—"}</td>
                            <td className={clsx("py-1.5 px-2 text-right tabular-nums", row.changePct >= 0 ? "text-[#ef5350]" : "text-[#26a69a]")}>
                              {row.changePct >= 0 ? "+" : ""}{row.changePct.toFixed(2)}%
                            </td>
                            <td className={clsx("py-1.5 px-2 text-right tabular-nums", row.macdHist != null && row.macdHist > 0 ? "text-[#ef5350]" : "text-[#26a69a]")}>
                              {row.macdHist != null ? row.macdHist.toFixed(3) : "—"}
                            </td>
                            <td className={clsx("py-1.5 px-2 text-right tabular-nums", row.rsi14 != null && row.rsi14 < 30 ? "text-[#26a69a]" : row.rsi14 != null && row.rsi14 > 70 ? "text-[#ef5350]" : "text-gray-600")}>{row.rsi14 != null ? row.rsi14.toFixed(1) : "—"}</td>
                            <td className="py-1.5 px-2 text-right text-gray-500">{row.kdj}</td>
                            {/* 获利盘 */}
                            <td className={clsx("py-1.5 px-2 text-right tabular-nums", row.chipProfitRatio != null && row.chipProfitRatio > 0.7 ? "text-[#ef5350]" : row.chipProfitRatio != null && row.chipProfitRatio < 0.3 ? "text-[#26a69a]" : "text-gray-600")}>
                              {row.chipProfitRatio != null ? `${(row.chipProfitRatio * 100).toFixed(0)}%` : "—"}
                            </td>
                            {/* 筹码集中度（附变化箭头） */}
                            <td className="py-1.5 px-2 text-right tabular-nums text-gray-600">
                              {row.chipConcentration != null ? (
                                <span>
                                  {row.chipConcentration.toFixed(1)}%
                                  {row.chipConcChange != null && (
                                    <span className={clsx("ml-1 text-[10px]", row.chipConcChange > 0.2 ? "text-[#ef5350]" : row.chipConcChange < -0.2 ? "text-[#26a69a]" : "text-gray-400")}>
                                      {row.chipConcChange > 0 ? "↑" : "↓"}
                                    </span>
                                  )}
                                </span>
                              ) : "—"}
                            </td>
                            <td className="py-1.5 px-2 text-center">
                              <span className={clsx("px-1.5 py-0.5 rounded text-xs", row.signal === "up" ? "bg-[#ef5350]/10 text-[#ef5350]" : row.signal === "down" ? "bg-[#26a69a]/10 text-[#26a69a]" : "bg-gray-100 text-gray-600")}>{row.conclusion}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* 背离信号 */}
              {divergences && divergences.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1.5">背离信号（近60日）</p>
                  <div className="space-y-1.5">
                    {divergences.slice(0, 4).map((d) => (
                      <div key={d.id} className={clsx("flex items-center gap-3 text-xs px-3 py-2 rounded-lg", d.signal_type.includes("BULL") ? "bg-[#ef5350]/5 border border-[#ef5350]/20" : "bg-[#26a69a]/5 border border-[#26a69a]/20")}>
                        <span className={d.signal_type.includes("BULL") ? "text-[#ef5350]" : "text-[#26a69a]"}>
                          {d.signal_type.includes("BULL") ? "底背离" : "顶背离"}{d.signal_type.includes("MACD") ? "（MACD）" : "（RSI）"}
                        </span>
                        <span className="text-gray-500">{d.detected_date}</span>
                        {d.confidence != null && <span className="text-gray-500">置信度 {(d.confidence * 100).toFixed(0)}%</span>}
                        {d.is_confirmed && <Tag color="yellow">已确认</Tag>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-3 py-3">
              <p className="text-sm text-gray-500">暂无技术指标数据</p>
              <button onClick={handleRecalc} disabled={recalcLoading}
                className="text-xs px-3 py-1.5 border border-[#58a6ff]/40 text-[#58a6ff] rounded hover:bg-[#58a6ff]/10 disabled:opacity-50 transition-colors">
                {recalcLoading ? "重算中…" : "立即重算"}
              </button>
            </div>
          )}
        </section>
        {/* ── 筹码结构（属于动态赔率 · 已并入 6D 末端"技术评估"段) ──── */}
        <section className="mb-7" data-section="chip-form">
          <SectionTitle>筹码结构 · 资金压力 <span className="ml-1 text-xs text-yellow-400/80">Tier 2</span></SectionTitle>
          {chip ? (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <Card><MetricItem label="获利盘" value={chip.profit_ratio != null ? `${(chip.profit_ratio * 100).toFixed(1)}%` : "—"} valueClass={chip.profit_ratio != null ? (chip.profit_ratio > 0.75 ? "text-[#ef5350]" : chip.profit_ratio < 0.3 ? "text-[#26a69a]" : undefined) : undefined} /></Card>
                <Card><MetricItem label="均匀成本" value={chip.avg_cost != null ? `¥${chip.avg_cost.toFixed(2)}` : "—"} /></Card>
                <Card><MetricItem label="集中度（90%筹码区间/价格）" value={chip.concentration != null ? `${chip.concentration.toFixed(1)}%` : "—"} sub={chip.concentration != null ? (chip.concentration > 70 ? "高度集中" : chip.concentration < 40 ? "分散" : "适中") : undefined} /></Card>
              </div>

              {chipSummary && (
                <Card>
                  <p className="text-sm text-gray-600 leading-relaxed">{chipSummary}</p>
                </Card>
              )}

            </div>
          ) : <p className="text-sm text-gray-500">暂无筹码数据</p>}
        </section>

        {/* ── 五档价位与安全边际（若 Claude 写入） ─────────── */}
        {report?.full_report?.price_levels && Object.values(report.full_report.price_levels).some((v) => v != null) && (
          <section className="mb-5">
            <SectionTitle>五档操作价位 · 安全边际</SectionTitle>
            <Card>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                {[
                  { label: "重仓买入", v: report.full_report.price_levels.heavy_buy, color: "text-[#26a69a]" },
                  { label: "中线买入", v: report.full_report.price_levels.mid_buy, color: "text-[#26a69a]" },
                  { label: "持有低位", v: report.full_report.price_levels.hold_low, color: "text-yellow-400" },
                  { label: "减仓", v: report.full_report.price_levels.reduce, color: "text-orange-400" },
                  { label: "清仓", v: report.full_report.price_levels.exit, color: "text-[#ef5350]" },
                ].map((it) => (
                  <div key={it.label} className="text-center py-2">
                    <p className="text-xs text-gray-500 mb-1">{it.label}</p>
                    <p className={clsx("text-lg font-bold tabular-nums", it.color)}>
                      {it.v != null ? "¥" + Number(it.v).toFixed(2) : "—"}
                    </p>
                  </div>
                ))}
              </div>
              {report.full_report.intrinsic_value && (
                <div className="border-t border-gray-200 mt-3 pt-2 text-xs text-gray-500 flex items-center gap-4 flex-wrap">
                  <span>内在价值:</span>
                  {report.full_report.intrinsic_value.optimistic != null && <span>乐观 ¥{Number(report.full_report.intrinsic_value.optimistic).toFixed(0)}</span>}
                  {report.full_report.intrinsic_value.base != null && <span>基准 ¥{Number(report.full_report.intrinsic_value.base).toFixed(0)}</span>}
                  {report.full_report.intrinsic_value.pessimistic != null && <span>悲观 ¥{Number(report.full_report.intrinsic_value.pessimistic).toFixed(0)}</span>}
                </div>
              )}
            </Card>
          </section>
        )}

        <p className="text-xs text-gray-300 pb-6">⚠ 以上数据由 AI 辅助生成，仅供参考，不构成投资建议。</p>
      </div>

      {/* ── 右侧边栏 ───────────────────────────────────────── */}
      <aside className="w-80 shrink-0 border-l border-gray-200 overflow-y-auto pl-5">

        {/* 催化剂 */}
        {report?.full_report?.catalysts?.length ? (
          <div className="mb-6">
            <SectionTitle>近期催化剂</SectionTitle>
            <ul className="space-y-2">
              {report.full_report.catalysts.map((c, i) => (
                <li key={i} className="flex gap-2 text-sm text-gray-700 bg-[#ef5350]/5 border border-[#ef5350]/15 rounded-lg px-3 py-2">
                  <span className="text-[#ef5350] shrink-0 mt-0.5">▸</span>{c}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* 关键风险 */}
        {report?.full_report?.risks?.length ? (
          <div className="mb-6">
            <SectionTitle>关键风险</SectionTitle>
            <ul className="space-y-2">
              {report.full_report.risks.map((r, i) => (
                <li key={i} className="flex gap-2 text-sm text-gray-700 bg-[#26a69a]/5 border border-[#26a69a]/15 rounded-lg px-3 py-2">
                  <span className="text-[#26a69a] shrink-0 mt-0.5">▸</span>{r}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* 近期催化剂 + 风险(替代原券商研报列表;研报原文链接已并入下方目标价表格"原文"列) */}
        <div>
          <SectionTitle>近期催化剂 · 风险</SectionTitle>
          <NewsHighlightsPanel code={code} />
        </div>

        {/* 近期资讯 */}
        <div>
          <SectionTitle>近期资讯</SectionTitle>
          <NewsFeed codes={[code]} />
        </div>
      </aside>
    </div>
  );
}
