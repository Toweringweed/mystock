"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { clsx } from "clsx";
import { settingsApi, SettingItem, LLMTestResult } from "@/lib/api/settings";
import ManualActionsPanel from "@/components/settings/ManualActionsPanel";
import DataStatusPanel from "@/components/settings/DataStatusPanel";
import HeroActionsPanel from "@/components/settings/HeroActionsPanel";

const GROUP_LABELS: Record<string, string> = {
  ai: "AI 模型配置",
  data: "数据源配置",
  notifications: "通知配置",
};
const GROUP_ORDER = ["ai", "data", "notifications"];

// ─── 单个设置项 ────────────────────────────────────────────────────────────────

function SettingRow({ item, onSaved }: { item: SettingItem; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const startEdit = () => {
    setDraft("");  // always start empty for secrets so user types new value
    setEditing(true);
    setError("");
  };

  const cancel = () => { setEditing(false); setError(""); };

  const save = async () => {
    if (!draft.trim()) { setError("值不能为空"); return; }
    setSaving(true);
    try {
      await settingsApi.update(item.key, draft.trim());
      setEditing(false);
      onSaved();
    } catch (e: any) {
      setError(e.message ?? "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border-b border-gray-200 py-4 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-medium text-gray-800">{item.description}</span>
            <span className="text-xs text-gray-400 font-mono">{item.key}</span>
            {item.source === "db" && (
              <span className="text-xs px-1.5 py-0.5 bg-[#58a6ff]/10 text-[#58a6ff] rounded border border-[#58a6ff]/20">
                已覆盖
              </span>
            )}
          </div>
          {!editing ? (
            <div className="flex items-center gap-3">
              <span className={clsx(
                "text-sm font-mono",
                item.has_value ? "text-gray-600" : "text-gray-400 italic"
              )}>
                {item.has_value ? (item.is_secret ? item.value || "••••" : item.value) : "未配置"}
              </span>
              {item.has_value && (
                <span className={clsx(
                  "text-xs px-1.5 py-0.5 rounded",
                  item.source === "db" ? "bg-green-500/10 text-green-400" : "bg-gray-200 text-gray-500"
                )}>
                  {item.source === "db" ? "DB覆盖" : "来自.env"}
                </span>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 mt-1">
              <input
                autoFocus
                type={item.is_secret ? "password" : "text"}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") cancel(); }}
                placeholder={item.is_secret ? "输入新值（不修改请取消）" : item.value || "输入值"}
                className="flex-1 bg-[#f0f3f6] border border-[#58a6ff] rounded px-3 py-1.5 text-sm text-gray-900 outline-none font-mono placeholder-gray-600"
              />
              <button onClick={save} disabled={saving}
                className="px-3 py-1.5 bg-[#58a6ff] text-gray-900 text-sm rounded hover:bg-[#58a6ff]/80 disabled:opacity-50">
                {saving ? "保存…" : "保存"}
              </button>
              <button onClick={cancel} className="px-3 py-1.5 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-600">
                取消
              </button>
            </div>
          )}
          {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
        </div>
        {!editing && (
          <button onClick={startEdit}
            className="text-xs px-3 py-1.5 bg-gray-100 text-gray-600 rounded hover:text-gray-800 hover:bg-gray-200 transition-colors shrink-0">
            {item.has_value ? "修改" : "配置"}
          </button>
        )}
      </div>
    </div>
  );
}

// ─── LLM 连通性测试 ────────────────────────────────────────────────────────────

function LLMTestPanel() {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<LLMTestResult | null>(null);

  const runTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      const r = await settingsApi.testLLM();
      setResult(r);
    } catch (e: any) {
      alert("测试失败: " + e.message);
    } finally {
      setTesting(false);
    }
  };

  const StatusBadge = ({ status }: { status: string }) => {
    const cls = status === "ok" ? "bg-green-500/10 text-green-400 border-green-500/30"
      : status === "error" ? "bg-red-500/10 text-red-400 border-red-500/30"
      : "bg-gray-200 text-gray-500 border-gray-600";
    const label = status === "ok" ? "✓ 可用" : status === "error" ? "✗ 失败" : "未配置";
    return <span className={clsx("text-xs px-2 py-1 rounded border font-medium", cls)}>{label}</span>;
  };

  return (
    <div className="bg-[#f6f8fa] rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-700">LLM 连通性测试</h3>
        <button onClick={runTest} disabled={testing}
          className="px-4 py-1.5 bg-[#58a6ff] text-gray-900 text-sm rounded hover:bg-[#58a6ff]/80 disabled:opacity-50 transition-colors">
          {testing ? "测试中…" : "开始测试"}
        </button>
      </div>
      {result ? (
        <div className="space-y-3">
          {(["openrouter", "openai", "anthropic"] as const).map((provider) => {
            const r = result[provider];
            return (
              <div key={provider} className="flex items-center gap-3 text-sm">
                <span className="text-gray-600 w-24 font-mono text-xs">{provider}</span>
                <StatusBadge status={r.status} />
                {r.status !== "not_configured" && (
                  <span className="text-gray-500 text-xs font-mono">{r.model}</span>
                )}
                {r.status === "ok" && r.reply && (
                  <span className="text-green-400 text-xs">回复: {r.reply}</span>
                )}
                {r.status === "error" && r.error && (
                  <span className="text-red-400 text-xs truncate max-w-xs" title={r.error}>{r.error}</span>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-gray-400">点击"开始测试"检查各 LLM provider 的连通性和 API Key 有效性</p>
      )}
    </div>
  );
}

// ─── 主页面 ───────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { data: settings, mutate, isLoading } = useSWR("settings", settingsApi.getAll);

  const grouped = (settings ?? []).reduce<Record<string, SettingItem[]>>((acc, s) => {
    (acc[s.group] ??= []).push(s);
    return acc;
  }, {});

  return (
    <main className="min-h-screen">
      <header className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700 transition-colors">← 返回</Link>
          <h1 className="text-xl font-bold text-gray-900">设置</h1>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">

        {/* 主要操作 — 3 个一键按钮 */}
        <HeroActionsPanel />

        {/* 数据状态 — 16 张表健康度 + 单点重拉 */}
        <DataStatusPanel />

        {/* 高级:17 个原始 task,默认折叠 */}
        <details className="bg-[#f6f8fa] rounded-xl border border-gray-200">
          <summary className="cursor-pointer px-5 py-3 text-sm font-semibold text-gray-700 hover:text-gray-900 select-none">
            🔧 高级 — 单个原始任务触发
            <span className="ml-2 text-xs text-gray-400 font-normal">(默认不需要,数据健康面板上的"重拉"按钮已覆盖大多数场景)</span>
          </summary>
          <div className="px-5 pb-5">
            <ManualActionsPanel />
          </div>
        </details>

        {/* LLM 连通性测试 */}
        <LLMTestPanel />

        {/* 配置项分组（按预定义顺序，未声明的 group 排最后） */}
        {isLoading ? (
          <div className="text-sm text-gray-500 py-10 text-center">加载中…</div>
        ) : (
          Object.entries(grouped)
            .sort(([a], [b]) => {
              const ai = GROUP_ORDER.indexOf(a);
              const bi = GROUP_ORDER.indexOf(b);
              return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
            })
            .map(([group, items]) => (
              <div key={group} className="bg-[#f6f8fa] rounded-xl border border-gray-200 p-5">
                <h2 className="text-sm font-semibold text-gray-600 mb-4 flex items-center gap-2">
                  <span className="w-1 h-4 bg-[#58a6ff] rounded-full inline-block" />
                  {GROUP_LABELS[group] ?? group}
                </h2>
                {items.map((item) => (
                  <SettingRow key={item.key} item={item} onSaved={() => mutate()} />
                ))}
              </div>
            ))
        )}

        {/* 说明 */}
        <div className="bg-[#f6f8fa] rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-600 mb-3 flex items-center gap-2">
            <span className="w-1 h-4 bg-yellow-500 rounded-full inline-block" />
            说明
          </h2>
          <ul className="space-y-2 text-sm text-gray-500">
            <li>• 在此页面保存的配置会覆盖 <code className="bg-gray-100 px-1 rounded text-xs">.env</code> 文件中的同名变量，并<strong className="text-gray-600">立即生效</strong>（无需重启）</li>
            <li>• AI 模型优先级：OpenRouter &gt; OpenAI &gt; Anthropic Claude</li>
            <li>• Secret 类型的值（API Key）保存后不会明文显示，只显示脱敏版本</li>
            <li>• 如需恢复 .env 默认值，将字段留空后保存即可（或直接修改 .env 并重启服务）</li>
          </ul>
        </div>
      </div>
    </main>
  );
}
