"use client";

import { useState } from "react";
import useSWR from "swr";
import { analysisApi, Report } from "@/lib/api/analysis";
import { clsx } from "clsx";

interface Props {
  code: string;
}

const SIGNAL_MAP = {
  bullish: { label: "看多", icon: "📈", cls: "bg-[#ef5350]/10 text-[#ef5350] border-[#ef5350]/30" },
  bearish: { label: "看空", icon: "📉", cls: "bg-[#26a69a]/10 text-[#26a69a] border-[#26a69a]/30" },
  neutral: { label: "中性", icon: "⚖️", cls: "bg-gray-200/50 text-gray-600 border-gray-600" },
};

export function ReportPanel({ code }: Props) {
  const [refreshing, setRefreshing] = useState(false);

  const { data: report, isLoading, mutate } = useSWR(
    `report-latest-${code}`,
    () => analysisApi.latestReport(code)
  );

  const handleRefresh = async () => {
    setRefreshing(true);
    await analysisApi.refreshReport(code);
    setTimeout(() => {
      mutate();
      setRefreshing(false);
    }, 3000);
  };

  if (isLoading)
    return <div className="text-xs text-gray-500 py-10 text-center">加载中...</div>;

  if (!report)
    return (
      <div className="py-10 text-center">
        <p className="text-gray-500 text-sm mb-4">暂无分析报告</p>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="px-4 py-2 bg-[#58a6ff] text-gray-900 text-sm rounded hover:bg-[#58a6ff]/80 disabled:opacity-50"
        >
          {refreshing ? "生成中..." : "立即生成"}
        </button>
      </div>
    );

  const signal = SIGNAL_MAP[report.overall_signal ?? "neutral"];
  const full = report.full_report;

  return (
    <div className="space-y-5">
      {/* 报告头 */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className={clsx("text-sm font-bold px-3 py-1 rounded border", signal.cls)}>
              {signal.icon} {signal.label}
            </span>
            <span className="text-gray-700 font-medium">{report.conclusion}</span>
          </div>
          <p className="text-xs text-gray-500">
            {report.report_date} · {report.model_used}
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="text-xs px-3 py-1.5 bg-gray-100 text-gray-600 rounded hover:text-gray-800 disabled:opacity-50 transition-colors"
        >
          {refreshing ? "生成中..." : "刷新报告"}
        </button>
      </div>

      {/* 三联结论卡片：行业拐点 / 外部颠覆 / AI 操作建议 */}
      {(report.industry_inflection || report.external_disruption || report.action_suggestion) && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <ConclusionCard
            icon="📊"
            label="行业需求拐点"
            tone="info"
            content={report.industry_inflection}
          />
          <ConclusionCard
            icon="⚡"
            label="外部颠覆力量"
            tone="warn"
            content={report.external_disruption}
          />
          <ConclusionCard
            icon="🎯"
            label="AI 操作建议"
            tone="action"
            content={report.action_suggestion}
          />
        </div>
      )}

      {/* 评分 */}
      <div className="grid grid-cols-2 gap-3">
        <ScoreCard label="技术面评分" score={report.technical_score} />
        <ScoreCard label="基本面评分" score={report.fundamental_score} />
      </div>

      {/* Claude 4D + 技术 评分(2026-05 精简版:D4 已并入主决策依据,D5 业绩兑现已并入 D3 护城河;⑤ 评分作为 D3 evidence 仍展示;仅当 source='claude_chat' 时显示) */}
      {full.source === "claude_chat" && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <ScoreCard label="① 行业+叙事" score={full.claude_industry_score ?? null} />
          <ScoreCard label="② 外部颠覆" score={full.claude_disruption_score ?? null} />
          <ScoreCard label="③ 护城河" score={full.claude_moat_score ?? null} />
          <ScoreCard label="⑤ 业绩+财务" score={full.claude_performance_score ?? null} />
          <ScoreCard label="⑧ 治理" score={full.claude_governance_score ?? null} />
          <ScoreCard label="📊 技术" score={full.claude_tech_score ?? null} />
        </div>
      )}

      {/* 详细分析 */}
      {full.technical_analysis && (
        <ReportSection title="技术面分析" content={full.technical_analysis} />
      )}
      {full.fundamental_analysis && (
        <ReportSection title="基本面分析" content={full.fundamental_analysis} />
      )}

      {/* 催化剂与风险 */}
      {(full.catalysts?.length || full.risks?.length) ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {full.catalysts?.length ? (
            <div className="bg-[#ef5350]/5 border border-[#ef5350]/20 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-[#ef5350] mb-2">近期催化剂</h4>
              <ul className="space-y-1">
                {full.catalysts.map((c, i) => (
                  <li key={i} className="text-xs text-gray-700 flex gap-2">
                    <span className="text-[#ef5350] shrink-0">•</span>
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {full.risks?.length ? (
            <div className="bg-[#26a69a]/5 border border-[#26a69a]/20 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-[#26a69a] mb-2">主要风险</h4>
              <ul className="space-y-1">
                {full.risks.map((r, i) => (
                  <li key={i} className="text-xs text-gray-700 flex gap-2">
                    <span className="text-[#26a69a] shrink-0">•</span>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* 支撑/压力 + 操作建议 */}
      {(full.support_level || full.resistance_level) && (
        <div className="bg-[#f6f8fa] rounded-lg p-4">
          <div className="flex gap-6 mb-3">
            {full.support_level && (
              <div>
                <p className="text-xs text-gray-500">支撑位</p>
                <p className="text-[#26a69a] font-bold">¥{full.support_level.toFixed(2)}</p>
              </div>
            )}
            {full.resistance_level && (
              <div>
                <p className="text-xs text-gray-500">压力位</p>
                <p className="text-[#ef5350] font-bold">¥{full.resistance_level.toFixed(2)}</p>
              </div>
            )}
          </div>
          {full.suggestion && (
            <p className="text-sm text-gray-700 leading-relaxed">{full.suggestion}</p>
          )}
        </div>
      )}

      {/* 免责声明 */}
      <p className="text-xs text-gray-400 border-t border-gray-200 pt-3">
        ⚠️ 以上为 AI 辅助分析，不构成投资建议，股市有风险，投资需谨慎。
      </p>
    </div>
  );
}

function ScoreCard({ label, score }: { label: string; score: number | null }) {
  const pct = score != null ? score * 10 : 0;
  const color =
    score != null
      ? score >= 7
        ? "#ef5350"
        : score >= 4
        ? "#ff9800"
        : "#26a69a"
      : "#555";

  return (
    <div className="bg-[#f6f8fa] rounded-lg p-3">
      <div className="flex justify-between items-center mb-2">
        <p className="text-xs text-gray-500">{label}</p>
        <p className="text-sm font-bold" style={{ color }}>
          {score ?? "—"}/10
        </p>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function ReportSection({ title, content }: { title: string; content: string }) {
  return (
    <div className="bg-[#f6f8fa] rounded-lg p-4">
      <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
        <span className="w-1 h-3.5 bg-[#58a6ff] rounded-full inline-block" />
        {title}
      </h4>
      <p className="text-sm text-gray-700 leading-relaxed">{content}</p>
    </div>
  );
}

function ConclusionCard({
  icon,
  label,
  tone,
  content,
}: {
  icon: string;
  label: string;
  tone: "info" | "warn" | "action";
  content: string | null;
}) {
  const palette = {
    info: {
      border: "border-[#58a6ff]/30",
      bg: "bg-[#58a6ff]/5",
      label: "text-[#58a6ff]",
    },
    warn: {
      border: "border-yellow-500/30",
      bg: "bg-yellow-500/5",
      label: "text-yellow-400",
    },
    action: {
      border: "border-[#26a69a]/30",
      bg: "bg-[#26a69a]/5",
      label: "text-[#26a69a]",
    },
  }[tone];

  return (
    <div className={clsx("rounded-lg border p-3", palette.border, palette.bg)}>
      <div className={clsx("text-xs font-semibold flex items-center gap-1.5 mb-1.5", palette.label)}>
        <span>{icon}</span>
        <span>{label}</span>
      </div>
      <p className="text-sm text-gray-800 leading-relaxed">
        {content ?? <span className="text-gray-400 italic">暂无（下次刷新报告后生成）</span>}
      </p>
    </div>
  );
}
