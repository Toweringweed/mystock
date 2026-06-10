"use client";

import useSWR from "swr";
import { useState } from "react";
import Link from "next/link";
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
} from "reactflow";
import "reactflow/dist/style.css";
import { supplyChainApi, SupplyChainEventSummary, SupplyChainNode } from "@/lib/api/supply_chain";
import { clsx } from "clsx";

interface Props {
  code: string;
}

// 节点颜色
const NODE_COLORS = {
  center: { bg: "#1f3a5f", border: "#58a6ff", text: "#58a6ff" },
  upstream_listed: { bg: "#1a3a2a", border: "#26a69a", text: "#26a69a" },
  upstream_unlisted: { bg: "#1e2939", border: "#4a5568", text: "#8b949e" },
  downstream_listed: { bg: "#3a1f1f", border: "#ef5350", text: "#ef5350" },
  downstream_unlisted: { bg: "#1e2939", border: "#4a5568", text: "#8b949e" },
};

function buildGraph(
  code: string,
  name: string,
  upstream: SupplyChainNode[],
  downstream: SupplyChainNode[]
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // 中心节点
  nodes.push({
    id: "center",
    data: { label: `${name}\n${code}` },
    position: { x: 400, y: 300 },
    style: {
      background: NODE_COLORS.center.bg,
      border: `2px solid ${NODE_COLORS.center.border}`,
      color: NODE_COLORS.center.text,
      borderRadius: 8,
      padding: "10px 16px",
      fontSize: 13,
      fontWeight: 600,
      minWidth: 120,
      textAlign: "center",
    },
  });

  const UP_X = 80;
  const DOWN_X = 720;
  const GAP = 90;

  // 上游节点
  upstream.slice(0, 6).forEach((node, i) => {
    const id = `up-${node.id}`;
    const colorKey = node.is_listed ? "upstream_listed" : "upstream_unlisted";
    const c = NODE_COLORS[colorKey];
    const y = 300 - ((upstream.slice(0, 6).length - 1) / 2) * GAP + i * GAP;

    const hasEvent = node.recent_event_count > 0;
    const eventBorder = node.urgent_event_count > 0 ? "#ef5350" : hasEvent ? "#f59e0b" : c.border;

    nodes.push({
      id,
      data: {
        label: `${node.company_name}${node.percentage ? `\n${node.percentage}%` : ""}${
          hasEvent ? `\n动态 ${node.recent_event_count}` : ""
        }`,
      },
      position: { x: UP_X, y },
      style: {
        background: node.urgent_event_count > 0 ? "#3a1f1f" : hasEvent ? "#332b16" : c.bg,
        border: `1.5px solid ${eventBorder}`,
        color: node.urgent_event_count > 0 ? "#ef5350" : hasEvent ? "#f59e0b" : c.text,
        borderRadius: 6,
        padding: "6px 12px",
        fontSize: 11,
        maxWidth: 140,
        textAlign: "center",
      },
    });

    edges.push({
      id: `e-up-${node.id}`,
      source: id,
      target: "center",
      animated: node.importance === "high" || hasEvent,
      style: {
        stroke: eventBorder,
        strokeWidth: hasEvent ? 2.5 : node.importance === "high" ? 2 : 1,
        opacity: 0.7,
      },
      label: node.product_desc?.slice(0, 10),
      labelStyle: { fontSize: 10, fill: "#8b949e" },
      labelBgStyle: { fill: "#0d1117" },
    });
  });

  // 下游节点
  downstream.slice(0, 6).forEach((node, i) => {
    const id = `down-${node.id}`;
    const colorKey = node.is_listed ? "downstream_listed" : "downstream_unlisted";
    const c = NODE_COLORS[colorKey];
    const y = 300 - ((downstream.slice(0, 6).length - 1) / 2) * GAP + i * GAP;

    const hasEvent = node.recent_event_count > 0;
    const eventBorder = node.urgent_event_count > 0 ? "#ef5350" : hasEvent ? "#f59e0b" : c.border;

    nodes.push({
      id,
      data: {
        label: `${node.company_name}${node.percentage ? `\n${node.percentage}%` : ""}${
          hasEvent ? `\n动态 ${node.recent_event_count}` : ""
        }`,
      },
      position: { x: DOWN_X, y },
      style: {
        background: node.urgent_event_count > 0 ? "#3a1f1f" : hasEvent ? "#332b16" : c.bg,
        border: `1.5px solid ${eventBorder}`,
        color: node.urgent_event_count > 0 ? "#ef5350" : hasEvent ? "#f59e0b" : c.text,
        borderRadius: 6,
        padding: "6px 12px",
        fontSize: 11,
        maxWidth: 140,
        textAlign: "center",
      },
    });

    edges.push({
      id: `e-down-${node.id}`,
      source: "center",
      target: id,
      animated: node.importance === "high" || hasEvent,
      style: {
        stroke: eventBorder,
        strokeWidth: hasEvent ? 2.5 : node.importance === "high" ? 2 : 1,
        opacity: 0.7,
      },
      label: node.product_desc?.slice(0, 10),
      labelStyle: { fontSize: 10, fill: "#8b949e" },
      labelBgStyle: { fill: "#0d1117" },
    });
  });

  return { nodes, edges };
}

export function SupplyChainPanel({ code }: Props) {
  const { data, isLoading, mutate } = useSWR(`supply-chain-${code}`, () =>
    supplyChainApi.get(code)
  );

  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    await supplyChainApi.refresh(code);
    setTimeout(() => {
      mutate();
      setRefreshing(false);
    }, 5000);
  };

  if (isLoading) return <div className="text-xs text-gray-500 py-10 text-center">加载中...</div>;

  const hasData =
    data && (data.upstream.length > 0 || data.downstream.length > 0);

  return (
    <div className="space-y-4">
      {/* 控制栏 */}
      <div className="flex items-center justify-between">
        <div className="flex gap-4 text-xs">
          <LegendItem color="#26a69a" label="上游供应商（上市）" />
          <LegendItem color="#4a5568" label="上游供应商（未上市）" />
          <LegendItem color="#ef5350" label="下游客户（上市）" />
        </div>
        <div className="flex items-center gap-3">
          {data?.updated_at && (
            <span className="text-xs text-gray-400">更新于 {data.updated_at.slice(0, 10)}</span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="text-xs px-3 py-1.5 bg-gray-100 text-gray-600 rounded hover:text-gray-800 disabled:opacity-50"
          >
            {refreshing ? "提取中..." : "重新提取"}
          </button>
        </div>
      </div>

      {!hasData ? (
        <div className="py-16 text-center">
          <p className="text-gray-500 text-sm mb-4">暂无供应链数据</p>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="px-4 py-2 bg-[#58a6ff] text-gray-900 text-sm rounded hover:bg-[#58a6ff]/80 disabled:opacity-50"
          >
            {refreshing ? "从年报提取中..." : "从年报提取供应链"}
          </button>
        </div>
      ) : (
        <>
          {data.recent_events.length > 0 && (
            <SupplyChainEvents events={data.recent_events} />
          )}

          {/* 图谱 */}
          <SupplyChainGraph
            code={code}
            name={data.name}
            upstream={data.upstream}
            downstream={data.downstream}
          />

          {/* 文字说明 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {data.upstream.length > 0 && (
              <NodeList title="上游供应商" nodes={data.upstream} color="text-[#26a69a]" />
            )}
            {data.downstream.length > 0 && (
              <NodeList title="下游客户" nodes={data.downstream} color="text-[#ef5350]" />
            )}
          </div>
        </>
      )}
    </div>
  );
}

function SupplyChainEvents({ events }: { events: SupplyChainEventSummary[] }) {
  return (
    <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-orange-800">供应链动态</h4>
        <span className="text-xs text-orange-700">近 14 天 · {events.length} 条</span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        {events.slice(0, 6).map((ev) => (
          <Link
            key={`${ev.news_id}-${ev.company_name}-${ev.stock_code}`}
            href={`/news/${ev.news_id}`}
            className="block rounded-md border border-orange-200 bg-white px-3 py-2 hover:border-orange-300 hover:bg-orange-50"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-orange-800 truncate">{ev.company_name}</span>
              <span
                className={clsx(
                  "shrink-0 rounded px-1.5 py-0.5 text-[10px]",
                  ev.urgency === "urgent"
                    ? "bg-[#ef5350]/15 text-[#ef5350]"
                    : "bg-amber-100 text-amber-700"
                )}
              >
                {ev.urgency === "urgent" ? "紧急" : "重要"}
              </span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs leading-snug text-gray-700">{ev.title}</p>
            {ev.impact_summary && (
              <p className="mt-1 line-clamp-1 text-[11px] text-gray-500">{ev.impact_summary}</p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}

function SupplyChainGraph({
  code,
  name,
  upstream,
  downstream,
}: {
  code: string;
  name: string;
  upstream: SupplyChainNode[];
  downstream: SupplyChainNode[];
}) {
  const { nodes: initNodes, edges: initEdges } = buildGraph(
    code,
    name,
    upstream,
    downstream
  );
  const [nodes, , onNodesChange] = useNodesState(initNodes);
  const [edges, , onEdgesChange] = useEdgesState(initEdges);

  return (
    <div className="h-[420px] rounded-lg overflow-hidden border border-gray-200">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        attributionPosition="bottom-right"
        style={{ background: "#0d1117" }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#21262d"
        />
        <Controls
          style={{
            background: "#161b22",
            border: "1px solid #30363d",
            borderRadius: 6,
          }}
        />
      </ReactFlow>
    </div>
  );
}

function NodeList({
  title,
  nodes,
  color,
}: {
  title: string;
  nodes: SupplyChainNode[];
  color: string;
}) {
  return (
    <div className="bg-[#f6f8fa] rounded-lg p-4">
      <h4 className={clsx("text-sm font-semibold mb-3", color)}>{title}</h4>
      <ul className="space-y-2">
        {nodes.map((n) => (
          <li key={n.id} className="flex items-start gap-2">
            <span
              className={clsx(
                "text-xs px-1.5 py-0.5 rounded shrink-0 mt-0.5",
                n.importance === "high"
                  ? "bg-[#ef5350]/20 text-[#ef5350]"
                  : n.importance === "medium"
                  ? "bg-[#ff9800]/20 text-[#ff9800]"
                  : "bg-gray-200 text-gray-600"
              )}
            >
              {n.importance === "high" ? "核心" : n.importance === "medium" ? "重要" : "一般"}
            </span>
            <div>
              <p className="text-sm text-gray-800">
                {n.company_name}
                {n.is_listed && n.company_code && (
                  <span className="ml-1 text-xs text-[#58a6ff]">{n.company_code}</span>
                )}
                {n.percentage && (
                  <span className="ml-1 text-xs text-gray-500">{n.percentage}%</span>
                )}
              </p>
              {n.product_desc && (
                <p className="text-xs text-gray-500">{n.product_desc}</p>
              )}
              {n.recent_event_count > 0 && n.latest_news_id && (
                <Link
                  href={`/news/${n.latest_news_id}`}
                  className="mt-1 inline-block text-xs text-orange-600 hover:underline"
                >
                  近期动态：{n.latest_event_title || `${n.recent_event_count} 条相关资讯`}
                </Link>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="w-3 h-3 rounded-sm border inline-block"
        style={{ borderColor: color, backgroundColor: color + "33" }}
      />
      <span className="text-gray-500">{label}</span>
    </span>
  );
}

