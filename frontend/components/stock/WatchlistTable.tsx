"use client";

import Link from "next/link";
import { useState, useRef, useCallback } from "react";
import useSWR, { mutate } from "swr";
import { tableApi, WatchlistTableRow } from "@/lib/api/table";
import { stocksApi } from "@/lib/api/stocks";
import { TagChip } from "@/components/stock/TagBar";
import { tagsApi, type TagCategory } from "@/lib/api/tags";
import { clsx } from "clsx";

// ─── 行内添加标签入口 ─────────────────────────────────────────────────────────

function InlineTagAdder({ code, onDone }: { code: string; onDone: () => void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState<TagCategory>("theme");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const open = () => {
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await tagsApi.attach(code, trimmed, category);
      setName("");
      setEditing(false);
      onDone();
    } catch {
      // 忽略错误,UI 保留输入状态由用户重试
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1 mt-0.5">
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value as TagCategory)}
          className="text-[10px] bg-[#f0f3f6] border border-gray-300 rounded px-1 py-0.5 text-gray-700 outline-none"
          disabled={saving}
        >
          <option value="theme">主题</option>
          <option value="industry_chain">产业链</option>
          <option value="attribute">属性</option>
        </select>
        <input
          ref={inputRef}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") setEditing(false);
          }}
          onBlur={submit}
          placeholder="标签名"
          disabled={saving}
          className="w-20 text-[10px] bg-[#f0f3f6] border border-[#58a6ff]/40 rounded px-1.5 py-0.5 text-gray-900 outline-none placeholder-gray-600"
        />
      </div>
    );
  }

  return (
    <button
      onClick={open}
      className="inline-flex items-center text-[10px] text-gray-500 hover:text-[#58a6ff] transition-colors mt-0.5"
      title="添加标签"
    >
      + 添加
    </button>
  );
}

// ─── 可编辑单元格 ─────────────────────────────────────────────────────────────

interface EditableCellProps {
  value: string | number | null;
  onSave: (val: string) => Promise<void>;
  placeholder?: string;
  className?: string;
  numeric?: boolean;
}

function EditableCell({ value, onSave, placeholder = "—", className, numeric }: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const startEdit = () => {
    setDraft(value !== null && value !== undefined ? String(value) : "");
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const cancel = () => setEditing(false);

  const commit = async () => {
    if (draft === String(value ?? "")) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(draft);
    } finally {
      setSaving(false);
      setEditing(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") commit();
    if (e.key === "Escape") cancel();
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={onKeyDown}
        className={clsx(
          "w-full bg-[#f0f3f6] border border-[#58a6ff] rounded px-1.5 py-0.5 text-sm text-gray-900 outline-none",
          numeric && "text-right",
          className
        )}
        disabled={saving}
      />
    );
  }

  return (
    <div
      onClick={startEdit}
      title="点击编辑"
      className={clsx(
        "cursor-text rounded px-1.5 py-0.5 min-h-[24px] hover:bg-black/5 transition-colors group relative",
        className
      )}
    >
      {value !== null && value !== undefined && value !== "" ? (
        <span className={clsx(numeric && "tabular-nums")}>{value}</span>
      ) : (
        <span className="text-gray-400">{placeholder}</span>
      )}
      <span className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-40 text-xs text-gray-600 pointer-events-none">
        ✎
      </span>
    </div>
  );
}

// ─── PE 标签颜色 ──────────────────────────────────────────────────────────────

function PEBadge({ pe }: { pe: number | null }) {
  if (pe === null) return <span className="text-gray-400">—</span>;
  const cls =
    pe <= 20 ? "text-[#ef5350]" :
    pe <= 35 ? "text-yellow-400" :
    "text-gray-600";
  return <span className={clsx("tabular-nums font-medium", cls)}>{pe}</span>;
}

// ─── 涨跌幅颜色 ───────────────────────────────────────────────────────────────

function ChangeCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-gray-400">—</span>;
  const positive = value >= 0;
  return (
    <span className={clsx("tabular-nums font-medium", positive ? "text-[#ef5350]" : "text-[#26a69a]")}>
      {positive ? "+" : ""}{value.toFixed(2)}%
    </span>
  );
}

// ─── 6 维度结论文字 ───────────────────────────────────────────────────────────

type Tone = "bull" | "bear" | "neutral" | "warn";
const toneCls = (t: Tone): string =>
  t === "bull" ? "text-[#ef5350]" : t === "bear" ? "text-[#26a69a]" : t === "warn" ? "text-yellow-400" : "text-gray-600";

// Claude 6 维度单分徽章（显示在每个维度的数据右侧）
function ScoreBadge({ score, dim }: { score: number | null | undefined; dim?: string }) {
  if (score == null) return null;
  const tone: Tone =
    score >= 7 ? "bull" : score >= 5 ? "neutral" : score >= 3 ? "warn" : "bear";
  const bgCls =
    tone === "bull" ? "bg-[#ef5350]/15 text-[#ef5350] border-[#ef5350]/40"
    : tone === "warn" ? "bg-yellow-400/15 text-yellow-400 border-yellow-400/40"
    : tone === "bear" ? "bg-[#26a69a]/15 text-[#26a69a] border-[#26a69a]/40"
    : "bg-gray-200 text-gray-600 border-gray-300";
  return (
    <span
      title={`Claude 维度 ${dim ?? ""} 评分: ${score}/10`}
      className={clsx(
        "inline-flex items-center justify-center text-[10px] font-semibold tabular-nums px-1 py-0 rounded border min-w-[18px] h-[16px]",
        bgCls
      )}
    >
      {dim ? <span className="opacity-60 mr-0.5">{dim}</span> : null}
      {score}
    </span>
  );
}

function moatJudgment(gm: number | null, roe: number | null, nm: number | null): { text: string; tone: Tone } {
  if (gm == null && roe == null) return { text: "数据不足", tone: "neutral" };
  if ((gm ?? 0) > 40 && (roe ?? 0) > 20) return { text: "护城河强（高毛利+高ROE）", tone: "bull" };
  if ((gm ?? 0) > 30 && (roe ?? 0) > 15) return { text: "护城河稳固", tone: "bull" };
  if ((gm ?? 100) < 15) return { text: "毛利偏弱，承压", tone: "bear" };
  if ((roe ?? 100) < 5 && roe != null) return { text: "ROE 偏低，资本回报差", tone: "bear" };
  if ((nm ?? 0) > 15) return { text: "净利率优良", tone: "bull" };
  return { text: "护城河中等", tone: "neutral" };
}

function valuationJudgment(peTtm: number | null, fwd26: number | null, fwd27: number | null): { text: string; tone: Tone } {
  if (fwd26 == null && peTtm == null) return { text: "数据不足", tone: "neutral" };
  if (fwd26 != null && fwd26 > 35) return { text: `26远期PE ${fwd26}x · 高于NVDA锚`, tone: "warn" };
  if (fwd26 != null && fwd26 < 20) return { text: `26远期PE ${fwd26}x · 估值便宜`, tone: "bull" };
  if (fwd26 != null && fwd26 < 30) return { text: `26远期PE ${fwd26}x · 合理区间`, tone: "bull" };
  if (peTtm != null && peTtm > 60) return { text: `PE-TTM ${peTtm.toFixed(0)}x · 静态偏高`, tone: "warn" };
  if (fwd27 != null && fwd27 < 25) return { text: `27远期PE ${fwd27}x · 中期可消化`, tone: "bull" };
  return { text: "估值已被定价", tone: "neutral" };
}

function performanceJudgment(profitYoy: number | null, revYoy: number | null): { text: string; tone: Tone } {
  if (profitYoy == null && revYoy == null) return { text: "数据不足", tone: "neutral" };
  if (profitYoy != null && profitYoy > 100) return { text: `净利+${profitYoy.toFixed(0)}% 业绩爆发`, tone: "bull" };
  if (profitYoy != null && profitYoy > 50) return { text: `净利+${profitYoy.toFixed(0)}% 高增长`, tone: "bull" };
  if (profitYoy != null && profitYoy > 20) return { text: `净利+${profitYoy.toFixed(0)}% 稳健`, tone: "bull" };
  if (profitYoy != null && profitYoy < 0) return { text: `净利${profitYoy.toFixed(0)}% 业绩下滑`, tone: "bear" };
  if (revYoy != null && revYoy < 0) return { text: `营收${revYoy.toFixed(0)}% 需求转弱`, tone: "bear" };
  return { text: "业绩兑现一般", tone: "neutral" };
}

// ─── 删除按钮 ─────────────────────────────────────────────────────────────────

function RemoveButton({ code }: { code: string }) {
  const [removing, setRemoving] = useState(false);

  const remove = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (!confirm(`确定从自选股移除 ${code}？`)) return;
    setRemoving(true);
    try {
      await stocksApi.remove(code);
      mutate("watchlist-table");
    } finally {
      setRemoving(false);
    }
  };

  return (
    <button
      onClick={remove}
      disabled={removing}
      className="opacity-0 group-hover/row:opacity-60 hover:!opacity-100 text-gray-500 hover:text-red-400 transition-all text-xs px-1"
      title="移除自选股"
    >
      ✕
    </button>
  );
}

// ─── 表格主体 ─────────────────────────────────────────────────────────────────

// `groupStart` = true 表示该列是一个新分组的起点，渲染时左侧加细分隔线
// 表格采用 2 行块布局：第一行硬指标，第二行 narrative（AI 结论 + 拐点 + 颠覆 + 操作建议）横跨多列
type HeaderDef = {
  label: string;
  align: "left" | "right" | "center";
  width: string;
  groupStart?: boolean;
};

const HEADERS: HeaderDef[] = [
  { label: "公司", align: "left", width: "w-28" },
  { label: "现价 / 年内", align: "right", width: "w-24", groupStart: true },
  { label: "🎯 目标价\n上行空间", align: "center", width: "w-36", groupStart: true },
  { label: "③ 护城河\n毛利率·ROE", align: "left", width: "w-40", groupStart: true },
  { label: "估值·远期PE\n26E/27E 利润", align: "left", width: "w-44", groupStart: true },
  { label: "⑤ 业绩·财务\n营收/利润 YoY", align: "left", width: "w-48", groupStart: true },
  { label: "①② 行业·拐点·颠覆\nD1+D2", align: "left", width: "w-48", groupStart: true },
  { label: "", align: "center", width: "w-8" },
];

function TableRow({ row, onRefresh }: { row: WatchlistTableRow; onRefresh: () => void }) {
  const saveRecommendation = useCallback(
    async (val: string) => {
      await tableApi.updateRecommendation(row.code, val);
      onRefresh();
    },
    [row.code, onRefresh]
  );

  const savePersonalNote = useCallback(
    async (val: string) => {
      await tableApi.updatePersonalNote(row.code, val);
      onRefresh();
    },
    [row.code, onRefresh]
  );

  const moat = moatJudgment(row.gross_margin, row.roe, row.net_margin);
  const valuation = valuationJudgment(row.pe_ttm, row.forward_pe_2026, row.forward_pe_2027);
  const performance = performanceJudgment(row.profit_yoy, row.revenue_yoy);

  // 操作建议优先取用户编辑值,没有则取 AI 默认
  const userRec = row.recommendation;
  const aiRec = row.ai_action_suggestion;
  const recDisplay = userRec ?? aiRec ?? null;
  const isAiDefault = !userRec && !!aiRec;

  // 分组分隔线
  const groupBorder = "border-l border-gray-200";

  return (
    <>
      {/* ── 数据行（硬指标） ─────────────────────────────────────────── */}
      <tr className="hover:bg-black/[0.03] peer/data align-top transition-colors group/row">
        {/* 公司(含标签竖排 + 添加入口) */}
        <td className="pt-3 pb-1.5 px-3">
          <Link
            href={`/stocks/${row.code}`}
            className="font-medium text-gray-900 hover:text-[#58a6ff] transition-colors"
          >
            {row.name}
          </Link>
          <div className="text-[11px] text-gray-400 mt-0.5 tabular-nums">{row.code}</div>

          {/* 标签竖排 + 添加按钮 */}
          <div className="flex flex-col items-start gap-1 mt-2">
            {row.tags?.map((t) => (
              <TagChip
                key={t.id}
                tag={t}
                removable
                onRemove={async () => {
                  await tagsApi.detach(row.code, t.id);
                  onRefresh();
                }}
              />
            ))}
            <InlineTagAdder code={row.code} onDone={onRefresh} />
          </div>
        </td>

        {/* 现价 / 年内涨幅 — 合并列 */}
        <td className={clsx("pt-3 pb-1.5 px-2 text-right", groupBorder)}>
          <div className="text-sm font-semibold tabular-nums text-gray-800 leading-tight">
            {row.current_price != null ? row.current_price.toFixed(2) : <span className="text-gray-300">—</span>}
          </div>
          <div className="mt-0.5 text-[11px]">
            <ChangeCell value={row.ytd_change} />
          </div>
        </td>

        {/* 🎯 目标价上行空间 — v5 主决策信号 */}
        <td className={clsx("pt-3 pb-1.5 px-2 text-center", groupBorder)}>
          {row.v5_upside_pct != null ? (
            <div
              className={clsx(
                "inline-flex flex-col items-center justify-center px-2 py-1.5 rounded-lg border relative min-w-[100px]",
                row.v5_veto_triggered
                  ? "bg-red-100 border-red-500"
                  : row.v5_upside_pct >= 15
                  ? "bg-[#ef5350]/15 border-[#ef5350]/50"
                  : row.v5_upside_pct >= 5
                  ? "bg-[#ef5350]/10 border-[#ef5350]/30"
                  : row.v5_upside_pct >= -5
                  ? "bg-gray-200 border-gray-300"
                  : "bg-[#26a69a]/10 border-[#26a69a]/40"
              )}
              title={
                `v5 上行空间 ${row.v5_upside_pct.toFixed(2)}%` +
                (row.v5_avg_target_weighted ? ` · 加权目标 ¥${row.v5_avg_target_weighted.toFixed(2)}` : "") +
                (row.v5_research_count_90d != null ? ` · 90d 研报 ${row.v5_research_count_90d}` : "") +
                (row.v5_freshness_status ? ` · ${row.v5_freshness_status}` : "") +
                (row.v5_has_consensus ? " · consensus" : "") +
                (row.v5_upgrade_count_30d && row.v5_upgrade_count_30d >= 3 ? ` · upgrade×${row.v5_upgrade_count_30d}` : "") +
                (row.v5_veto_reason ? ` · Veto:${row.v5_veto_reason}` : "")
              }
            >
              {row.v5_veto_triggered && (
                <span className="absolute -top-1.5 -right-1.5 text-[10px] bg-red-600 text-white rounded-full px-1.5 leading-tight" title="Veto 触发">⚠</span>
              )}
              {/* 大号上行空间 % */}
              <span className={clsx(
                "text-xl font-bold tabular-nums leading-none",
                row.v5_veto_triggered ? "text-red-700"
                  : row.v5_upside_pct >= 5 ? "text-[#ef5350]"
                  : row.v5_upside_pct >= -5 ? "text-gray-700"
                  : "text-[#26a69a]"
              )}>
                {row.v5_upside_pct >= 0 ? "+" : ""}{row.v5_upside_pct.toFixed(1)}%
              </span>
              {/* score + 加权目标价 */}
              <div className="flex items-center gap-1.5 mt-1 text-[10px] tabular-nums text-gray-600">
                {row.v5_final_score != null && (
                  <span className="font-semibold">分 {row.v5_final_score.toFixed(1)}</span>
                )}
                {row.v5_avg_target_weighted != null && (
                  <>
                    <span className="text-gray-400">·</span>
                    <span>¥{row.v5_avg_target_weighted.toFixed(0)}</span>
                  </>
                )}
              </div>
              {/* 鲜度 + bonus 徽章 */}
              <div className="flex items-center gap-1 mt-1">
                {row.v5_freshness_status && (
                  <span className={clsx(
                    "text-[9px] px-1 rounded",
                    row.v5_freshness_status === "fresh" ? "bg-[#26a69a]/20 text-[#26a69a]"
                      : row.v5_freshness_status === "recent" ? "bg-blue-500/20 text-blue-400"
                      : row.v5_freshness_status === "aging" ? "bg-yellow-500/20 text-yellow-400"
                      : "bg-red-500/20 text-red-400"
                  )}>
                    {row.v5_freshness_status}
                  </span>
                )}
                {row.v5_has_consensus && (
                  <span className="text-[9px] text-[#26a69a]" title="一致预期">✓</span>
                )}
                {row.v5_upgrade_count_30d != null && row.v5_upgrade_count_30d >= 3 && (
                  <span className="text-[9px] text-[#ef5350]" title={`30d 内 ${row.v5_upgrade_count_30d} 家上调`}>↑{row.v5_upgrade_count_30d}</span>
                )}
              </div>
            </div>
          ) : (
            <div className="text-gray-300 text-xs">
              {row.v5_freshness_status === "stale" ? (
                <span title="30d 无新研报">stale</span>
              ) : (
                <span>—</span>
              )}
            </div>
          )}

          {/* 重要消息预告 + 警示徽章组(财报临近 + 上次 surprise) */}
          {(row.days_to_earnings != null && row.days_to_earnings <= 30) || row.last_earnings_surprise_direction ? (
            <div className="flex flex-col items-center gap-1 mt-2">
              {row.days_to_earnings != null && row.days_to_earnings <= 30 && (
                <div
                  className={clsx(
                    "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border",
                    row.days_to_earnings <= 7
                      ? "bg-orange-500/15 border-orange-500/40 text-orange-400 animate-pulse"
                      : "bg-yellow-500/10 border-yellow-500/30 text-yellow-500"
                  )}
                  title={`财报披露日 ${row.upcoming_earnings_date},距今 ${row.days_to_earnings} 天`}
                >
                  ⏰ 财报 {row.days_to_earnings}d
                </div>
              )}
              {row.last_earnings_surprise_direction && (
                <div
                  className={clsx(
                    "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold border",
                    row.last_earnings_surprise_direction === "beat"
                      ? "bg-[#ef5350]/10 border-[#ef5350]/40 text-[#ef5350]"
                      : row.last_earnings_surprise_direction === "miss"
                      ? "bg-[#26a69a]/10 border-[#26a69a]/40 text-[#26a69a]"
                      : "bg-yellow-400/10 border-yellow-400/30 text-yellow-400"
                  )}
                  title={`上次 surprise: ${row.last_earnings_surprise_pct?.toFixed(2) ?? "—"}%`}
                >
                  {row.last_earnings_surprise_direction === "beat" && "▲"}
                  {row.last_earnings_surprise_direction === "miss" && "▼"}
                  {row.last_earnings_surprise_direction === "meet" && "≈"}
                  {row.last_earnings_surprise_pct != null
                    ? `${row.last_earnings_surprise_pct >= 0 ? "+" : ""}${row.last_earnings_surprise_pct.toFixed(0)}%`
                    : ""}
                </div>
              )}
            </div>
          ) : null}
        </td>

        {/* ③ 护城河 */}
        <td className={clsx("pt-3 pb-1.5 px-3", groupBorder)}>
          <div className="flex items-baseline gap-2 text-xs tabular-nums">
            <span className="text-gray-500">毛利</span>
            <span className={clsx("font-medium", row.gross_margin != null && row.gross_margin > 40 ? "text-[#ef5350]" : "text-gray-800")}>
              {row.gross_margin != null ? `${row.gross_margin.toFixed(1)}%` : <span className="text-gray-300">—</span>}
            </span>
            <span className="text-gray-300">·</span>
            <span className="text-gray-500">ROE</span>
            <span className={clsx("font-medium", row.roe != null ? (row.roe > 20 ? "text-[#ef5350]" : row.roe < 5 ? "text-[#26a69a]" : "text-gray-800") : "text-gray-300")}>
              {row.roe != null ? `${row.roe.toFixed(1)}%` : "—"}
            </span>
            <ScoreBadge score={row.claude_moat_score} dim="③" />
          </div>
          <div className={clsx("text-xs mt-1 leading-snug", toneCls(moat.tone))}>{moat.text}</div>
        </td>

        {/* 估值 · 远期PE(原 D4 动态赔率维度已并入主决策依据,本列仅作信息展示不计分) */}
        <td className={clsx("pt-3 pb-1.5 px-3", groupBorder)}>
          <div className="flex items-baseline gap-2 text-xs tabular-nums">
            <span className="text-gray-500">PE</span>
            <span className="text-gray-800 font-medium">{row.pe_ttm != null ? row.pe_ttm.toFixed(1) : <span className="text-gray-300">—</span>}</span>
            <span className="text-gray-300">·</span>
            <span className="text-gray-500">26/27</span>
            <span><PEBadge pe={row.forward_pe_2026} /></span>
            <span className="text-gray-300">/</span>
            <span><PEBadge pe={row.forward_pe_2027} /></span>
          </div>
          <div className={clsx("text-xs mt-1 leading-snug", toneCls(valuation.tone))}>{valuation.text}</div>
          {/* 26E/27E 利润预测(只读小号字,编辑请去详情页) */}
          {(row.forecast_2026 != null || row.forecast_2027 != null) && (
            <div className="text-[10px] text-gray-400 mt-1.5 tabular-nums">
              {row.forecast_2026 != null && <span>26E <span className="text-gray-600">{row.forecast_2026.toFixed(1)}</span>亿</span>}
              {row.forecast_2026 != null && row.forecast_2027 != null && <span className="mx-1.5 text-gray-300">/</span>}
              {row.forecast_2027 != null && <span>27E <span className="text-gray-600">{row.forecast_2027.toFixed(1)}</span>亿</span>}
            </div>
          )}
        </td>

        {/* ⑤ 业绩·财务 — 营收/利润 YoY + Claude 评分(对应详情页 D3 护城河 evidence) */}
        <td className={clsx("pt-3 pb-1.5 px-3", groupBorder)}>
          <div className="flex items-baseline gap-2 text-xs tabular-nums flex-wrap">
            <span className="text-gray-500">营收</span>
            <span className={clsx("font-medium", row.revenue_yoy != null ? (row.revenue_yoy > 0 ? "text-[#ef5350]" : "text-[#26a69a]") : "text-gray-300")}>
              {row.revenue_yoy != null ? `${row.revenue_yoy > 0 ? "+" : ""}${row.revenue_yoy.toFixed(1)}%` : "—"}
            </span>
            <span className="text-gray-300">·</span>
            <span className="text-gray-500">利润</span>
            <span className={clsx("font-medium", row.profit_yoy != null ? (row.profit_yoy > 0 ? "text-[#ef5350]" : "text-[#26a69a]") : "text-gray-300")}>
              {row.profit_yoy != null ? `${row.profit_yoy > 0 ? "+" : ""}${row.profit_yoy.toFixed(1)}%` : "—"}
            </span>
            <ScoreBadge score={row.claude_performance_score} dim="⑤" />
          </div>
          <div className={clsx("text-xs mt-1 leading-snug", toneCls(performance.tone))}>{performance.text}</div>
        </td>

        {/* ①② 行业景气 · 拐点 · 颠覆 — D1 + D2 + 拐点/颠覆文字 */}
        <td className={clsx("pt-3 pb-1.5 px-3", groupBorder)}>
          <div className="flex items-center gap-2 text-xs">
            {row.claude_industry_score != null ? (
              <span className="inline-flex items-baseline gap-1">
                <span className="text-[10px] text-[#58a6ff] font-semibold">拐点</span>
                <ScoreBadge score={row.claude_industry_score} dim="①" />
              </span>
            ) : null}
            {row.claude_disruption_score != null ? (
              <span className="inline-flex items-baseline gap-1">
                <span className="text-[10px] text-yellow-500/80 font-semibold">颠覆</span>
                <ScoreBadge score={row.claude_disruption_score} dim="②" />
              </span>
            ) : null}
            {row.claude_industry_score == null && row.claude_disruption_score == null && (
              <span className="text-gray-300">—</span>
            )}
          </div>
          {/* 拐点 + 颠覆 文字(各自一行) */}
          {row.industry_inflection && (
            <div className="text-[11px] mt-1.5 leading-snug text-gray-600">
              <span className="text-[#58a6ff] font-semibold mr-1">拐点</span>
              {row.industry_inflection}
            </div>
          )}
          {row.external_disruption && (
            <div className="text-[11px] mt-1 leading-snug text-gray-600">
              <span className="text-yellow-500/80 font-semibold mr-1">颠覆</span>
              {row.external_disruption}
            </div>
          )}
        </td>

        {/* 删除 */}
        <td className="pt-3 pb-1.5 px-1 text-center">
          <RemoveButton code={row.code} />
        </td>
      </tr>

      {/* ── Narrative 行(标签 + AI 结论 + 治理/Veto + 操作建议)─────────── */}
      {/* 跨列布局:col 1 留空(公司),cols 2-7 整体左移到现价/年内列起,col 8 留空(×) */}
      <tr className="border-b border-gray-200 bg-black/[0.015] peer-hover/data:bg-black/[0.03] hover:bg-black/[0.03] transition-colors group/row">
        <td className="pt-0 pb-2.5 px-3"></td>
        <td colSpan={6} className={clsx("pt-1 pb-2.5 px-3", groupBorder)}>
          <div className="space-y-1.5">
            {/* ⑧ 治理 + Veto 警告(标签已迁移到公司列) */}
            {(row.claude_governance_score != null || row.claude_veto_triggered) && (
              <div className="flex flex-wrap items-center gap-1">
                {row.claude_governance_score != null && (
                  <span className="inline-flex items-baseline gap-1">
                    <span className="text-[10px] text-purple-400 font-semibold">治理</span>
                    <ScoreBadge score={row.claude_governance_score} dim="⑧" />
                  </span>
                )}
                {row.claude_veto_triggered && (
                  <span
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-100 border border-red-500 text-[10px] text-red-700 font-semibold"
                    title={row.claude_veto_reason ?? "Veto 触发"}
                  >
                    ⚠ Veto
                  </span>
                )}
              </div>
            )}

            {/* AI 一句话结论 */}
            {row.ai_conclusion && (
              <div className="text-xs text-gray-700 leading-relaxed">
                <span className="text-gray-400 mr-1.5 text-[10px] font-semibold tracking-wide">AI</span>
                {row.ai_conclusion}
              </div>
            )}

            {/* 技术分析(只读) */}
            {row.technical_analysis && (
              <div className="flex items-start gap-2 text-xs">
                <span className="text-[#58a6ff] font-semibold shrink-0 mt-0.5 text-[11px]">技术</span>
                <div className="flex-1 min-w-0 text-gray-600 leading-relaxed whitespace-pre-wrap">
                  {row.technical_analysis}
                </div>
              </div>
            )}

            {/* 操作建议(可编辑) */}
            <div className="flex items-start gap-2 text-xs">
              <span className="text-[#26a69a] font-semibold shrink-0 mt-1">建议</span>
              <div className="flex-1 min-w-0">
                <EditableCell
                  value={recDisplay}
                  placeholder="点击输入操作建议"
                  onSave={saveRecommendation}
                  className={clsx(
                    "leading-relaxed whitespace-normal",
                    isAiDefault && "text-gray-600 italic"
                  )}
                />
                {isAiDefault && (
                  <div className="text-[10px] text-gray-300 mt-0.5">AI 默认建议 · 点击编辑可覆盖</div>
                )}
              </div>
            </div>

            {/* 个人笔记(可编辑) */}
            <div className="flex items-start gap-2 text-xs">
              <span className="text-yellow-500/80 font-semibold shrink-0 mt-1">笔记</span>
              <div className="flex-1 min-w-0">
                <EditableCell
                  value={row.personal_note}
                  placeholder="点击输入个人笔记(投资逻辑/观察点/复盘记录)"
                  onSave={savePersonalNote}
                  className="leading-relaxed whitespace-normal text-gray-700"
                />
              </div>
            </div>
          </div>
        </td>
        {/* 右侧 1 列留空对齐:× */}
        <td className="pt-0 pb-2.5"></td>
      </tr>
    </>
  );
}

// ─── 骨架屏 ───────────────────────────────────────────────────────────────────

function SkeletonRows() {
  return (
    <>
      {[...Array(5)].map((_, i) => (
        <tr key={i} className="border-b border-gray-200">
          {HEADERS.map((h, j) => (
            <td key={j} className="py-3 px-3">
              <div className="h-4 bg-gray-100 rounded animate-pulse" style={{ width: j === 2 ? "80%" : "60%" }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

// ─── 主组件 ───────────────────────────────────────────────────────────────────

// 排序选项 — 核心(v5 上行空间) + 6D + 技术 + 年内涨幅(2026-05 6D 精简版)
type SortKey =
  | "default"
  | "v5_score" | "v5_upside"
  | "overall"
  | "industry" | "disruption" | "moat"
  | "performance" | "governance" | "tech"
  | "ytd_change";

const SORT_OPTIONS: { key: SortKey; label: string; field: (r: WatchlistTableRow) => number | null }[] = [
  { key: "default", label: "默认(添加顺序)", field: () => null },
  // 核心(v5 主决策)
  { key: "v5_score", label: "🎯 核心 v5 综合分(目标价主导)↓", field: (r) => r.v5_final_score },
  { key: "v5_upside", label: "🎯 核心 上行空间 % ↓", field: (r) => r.v5_upside_pct },
  // 6D + 技术 综合
  { key: "overall", label: "6D 综合分(辅助)↓", field: (r) => r.claude_overall_score },
  // 6 维度
  { key: "moat", label: "③ 护城河 ↓", field: (r) => r.claude_moat_score },
  { key: "performance", label: "⑤ 业绩+财务 ↓", field: (r) => r.claude_performance_score },
  { key: "industry", label: "① 行业拐点+叙事 ↓", field: (r) => r.claude_industry_score },
  { key: "disruption", label: "② 外部颠覆 ↓", field: (r) => r.claude_disruption_score },
  { key: "governance", label: "⑧ 治理 ↓", field: (r) => r.claude_governance_score },
  // 技术段
  { key: "tech", label: "📊 技术评估 ↓", field: (r) => r.claude_tech_score },
  // 行情
  { key: "ytd_change", label: "年内涨幅 ↓", field: (r) => r.ytd_change },
];

export function WatchlistTable({ filterTagIds = [] }: { filterTagIds?: number[] }) {
  const { data, error, isLoading, mutate: revalidate } = useSWR(
    "watchlist-table",
    tableApi.getWatchlist,
    { refreshInterval: 30000 }
  );

  const [sortKey, setSortKey] = useState<SortKey>("v5_score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const onRefresh = useCallback(() => revalidate(), [revalidate]);

  const tagFiltered = filterTagIds.length === 0
    ? data
    : data?.filter((row) =>
        filterTagIds.every((id) => (row.tags ?? []).some((t) => t.id === id)),
      );

  // 应用排序
  const filtered = (() => {
    if (!tagFiltered || sortKey === "default") return tagFiltered;
    const opt = SORT_OPTIONS.find((o) => o.key === sortKey);
    if (!opt) return tagFiltered;
    const sorted = [...tagFiltered].sort((a, b) => {
      const va = opt.field(a);
      const vb = opt.field(b);
      // null 一律排到最后
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return sortDir === "desc" ? vb - va : va - vb;
    });
    return sorted;
  })();

  if (error)
    return (
      <div className="text-red-400 text-sm py-4">
        加载失败，请检查后端服务是否启动
      </div>
    );

  if (!isLoading && !data?.length)
    return (
      <div className="text-center mt-24">
        <p className="text-4xl mb-4">📈</p>
        <p className="text-gray-600 text-lg mb-2">暂无自选股</p>
        <p className="text-gray-400 text-sm">在上方搜索框中输入股票代码或名称添加自选股</p>
      </div>
    );

  return (
    <div className="overflow-x-auto">
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h2 className="text-sm font-semibold text-gray-600">
          自选股 <span className="text-gray-400">
            ({filtered?.length ?? 0}{filterTagIds.length > 0 && data ? ` / ${data.length}` : ""})
          </span>
          <span className="text-xs text-gray-400 ml-2 font-normal">· 🎯 目标价上行空间主导 + 8D 维度</span>
        </h2>
        <div className="flex items-center gap-2 ml-auto">
          <Link
            href="/supply-chain"
            className="text-xs px-2.5 py-1 bg-[#58a6ff]/10 text-[#58a6ff] border border-[#58a6ff]/30 rounded hover:bg-[#58a6ff]/20 transition-colors"
          >
            📊 全局供应链图
          </Link>
          {/* 排序控件 */}
          <span className="text-xs text-gray-400 ml-1">排序:</span>
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="text-xs bg-[#f0f3f6] border border-gray-300 rounded px-2 py-1 text-gray-700 outline-none hover:border-gray-600"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
          {sortKey !== "default" && (
            <button
              onClick={() => setSortDir(sortDir === "desc" ? "asc" : "desc")}
              title={sortDir === "desc" ? "切换升序" : "切换降序"}
              className="text-xs px-2 py-1 bg-[#f0f3f6] border border-gray-300 rounded text-gray-700 hover:border-gray-600"
            >
              {sortDir === "desc" ? "↓" : "↑"}
            </button>
          )}
        </div>
      </div>

      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 z-20">
          <tr className="border-b-2 border-gray-300 shadow-sm">
            {HEADERS.map((h, i) => (
              <th
                key={i}
                className={clsx(
                  "py-2.5 px-3 text-[11px] font-semibold text-gray-700 whitespace-pre-line uppercase tracking-wide bg-[#eef4fc]",
                  h.align === "right" && "text-right",
                  h.align === "center" && "text-center",
                  h.align === "left" && "text-left",
                  h.width,
                  h.groupStart && "border-l border-gray-200"
                )}
              >
                {h.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <SkeletonRows />
          ) : (
            filtered?.map((row) => (
              <TableRow key={row.code} row={row} onRefresh={onRefresh} />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
