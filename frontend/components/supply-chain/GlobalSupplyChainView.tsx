"use client";

import useSWR from "swr";
import { useMemo, useState } from "react";
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  MarkerType,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import Link from "next/link";
import { clsx } from "clsx";
import {
  supplyChainApi,
  GlobalSupplyChain,
  SupplyChainStockMeta,
  SupplyChainEdge,
} from "@/lib/api/supply_chain";

// ── 布局常量 ───────────────────────────────────────────────────────────────────
const CLUSTER_PADDING = 40;             // 行业聚簇内边距
const CLUSTER_GAP_X = 120;              // 聚簇间横向间距
const CLUSTER_GAP_Y = 80;               // 聚簇间纵向间距
const NODE_W = 150;
const NODE_H = 56;
const NODE_GAP_X = 40;
const NODE_GAP_Y = 24;
const COLS_PER_CLUSTER = 3;             // 聚簇内每行最多 3 个自选股节点

const EXTERNAL_LANE_OFFSET = 600;       // 外部公司列起点 x 偏移(基于聚簇区右侧)
const EXTERNAL_LANE_WIDTH = 280;
const EXTERNAL_NODE_GAP_Y = 70;

// ── 工具:按重要度配色 ─────────────────────────────────────────────────────────
const importanceColor = (imp: SupplyChainEdge["importance"]) =>
  imp === "high" ? "#ef5350" : imp === "medium" ? "#f59e0b" : "#9ca3af";

// ── 布局计算:行业聚簇 + 外部公司分列 ───────────────────────────────────────────
function buildLayout(data: GlobalSupplyChain, focusCode: string | null): {
  nodes: Node[];
  edges: Edge[];
} {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // 1) 排序行业(自选股数量倒序),计算每个聚簇的盒子尺寸
  const industries = Object.entries(data.industry_groups)
    .sort(([, a], [, b]) => b.length - a.length);

  // 计算聚簇区总布局(左侧主区域)
  let cursorY = 0;
  const clusterMaxX = 0;

  // 用 code → {x, y} 索引方便后续连边
  const codePos: Record<string, { x: number; y: number; w: number; h: number }> = {};

  for (const [industry, codes] of industries) {
    const rows = Math.ceil(codes.length / COLS_PER_CLUSTER);
    const clusterW = CLUSTER_PADDING * 2 + COLS_PER_CLUSTER * NODE_W + (COLS_PER_CLUSTER - 1) * NODE_GAP_X;
    const clusterH = CLUSTER_PADDING * 2 + 30 + rows * NODE_H + (rows - 1) * NODE_GAP_Y; // +30 给 cluster header

    // 聚簇容器(group node)
    const groupId = `group::${industry}`;
    nodes.push({
      id: groupId,
      type: "group",
      position: { x: 0, y: cursorY },
      data: { label: industry },
      style: {
        width: clusterW,
        height: clusterH,
        backgroundColor: "rgba(88, 166, 255, 0.04)",
        border: "1px dashed rgba(88, 166, 255, 0.5)",
        borderRadius: 12,
      },
    });
    // header 文本节点(只读 label)
    nodes.push({
      id: `${groupId}::header`,
      parentNode: groupId,
      extent: "parent",
      position: { x: CLUSTER_PADDING, y: 8 },
      data: { label: `🏷 ${industry} · ${codes.length} 只` },
      style: {
        background: "transparent",
        border: "none",
        color: "#374151",
        fontSize: 12,
        fontWeight: 600,
        width: clusterW - CLUSTER_PADDING * 2,
        padding: 0,
        boxShadow: "none",
      },
      draggable: false,
      selectable: false,
    });

    // 聚簇内的自选股节点
    codes.forEach((code, idx) => {
      const meta = data.watchlist_stocks.find((s) => s.code === code);
      if (!meta) return;
      const col = idx % COLS_PER_CLUSTER;
      const row = Math.floor(idx / COLS_PER_CLUSTER);
      const x = CLUSTER_PADDING + col * (NODE_W + NODE_GAP_X);
      const y = CLUSTER_PADDING + 30 + row + row * NODE_GAP_Y + row * NODE_H;
      const isFocus = focusCode === code;
      nodes.push({
        id: code,
        parentNode: groupId,
        extent: "parent",
        position: { x, y },
        data: {
          label: (
            <Link
              href={`/stocks/${code}`}
              className="block text-center hover:opacity-80"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="text-[13px] font-semibold leading-tight">{meta.name}</div>
              <div className="text-[10px] text-gray-500 mt-0.5">{meta.code}</div>
            </Link>
          ),
        },
        style: {
          background: isFocus ? "#fff7ed" : "#f0f7ff",
          border: `2px solid ${isFocus ? "#f59e0b" : "#58a6ff"}`,
          color: "#1f2937",
          borderRadius: 8,
          width: NODE_W,
          height: NODE_H,
          padding: 6,
          fontSize: 12,
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      });
      // 记录绝对坐标(group offset + 内坐标),用于连边参考
      codePos[code] = { x: 0 + x, y: cursorY + y, w: NODE_W, h: NODE_H };
    });

    cursorY += clusterH + CLUSTER_GAP_Y;
  }

  const totalClusterHeight = Math.max(cursorY, 600);

  // 2) 外部公司:分两列(左 = 上游、右 = 下游),纵向排列
  const upstreamExt: SupplyChainStockMeta[] = [];
  const downstreamExt: SupplyChainStockMeta[] = [];
  const extDirection: Record<string, "upstream" | "downstream" | "both"> = {};

  for (const ext of data.external_companies) {
    extDirection[ext.code] = "both"; // 先标 both,后面覆盖
  }
  for (const e of data.edges) {
    const partnerCode = data.watchlist_stocks.find((s) => s.code === e.from_code)
      ? e.to_code
      : data.watchlist_stocks.find((s) => s.code === e.to_code)
      ? e.from_code
      : null;
    if (!partnerCode || !extDirection[partnerCode]) continue;
    const isUpstream = e.relation_type === "upstream";
    const cur = extDirection[partnerCode];
    if (cur === "both") {
      extDirection[partnerCode] = isUpstream ? "upstream" : "downstream";
    } else if (cur === "upstream" && !isUpstream) {
      extDirection[partnerCode] = "both";
    } else if (cur === "downstream" && isUpstream) {
      extDirection[partnerCode] = "both";
    }
  }
  for (const ext of data.external_companies) {
    const dir = extDirection[ext.code];
    if (dir === "downstream") downstreamExt.push(ext);
    else upstreamExt.push(ext);  // upstream 或 both 都放上游列
  }

  // 上游外部列在聚簇区左侧
  const upstreamX = -EXTERNAL_LANE_OFFSET - EXTERNAL_LANE_WIDTH;
  const downstreamX = clusterMaxX + 700;  // 聚簇右侧

  upstreamExt.forEach((ext, idx) => {
    const x = upstreamX;
    const y = idx * EXTERNAL_NODE_GAP_Y;
    nodes.push({
      id: ext.code,
      position: { x, y },
      data: { label: ext.name.length > 22 ? ext.name.slice(0, 22) + "…" : ext.name },
      style: {
        background: "#f9fafb",
        border: "1px solid #d1d5db",
        color: "#6b7280",
        borderRadius: 6,
        width: EXTERNAL_LANE_WIDTH,
        fontSize: 11,
        padding: 6,
        textAlign: "center" as const,
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Right,
      draggable: true,
    });
    codePos[ext.code] = { x, y, w: EXTERNAL_LANE_WIDTH, h: 32 };
  });

  downstreamExt.forEach((ext, idx) => {
    const x = downstreamX;
    const y = idx * EXTERNAL_NODE_GAP_Y;
    nodes.push({
      id: ext.code,
      position: { x, y },
      data: { label: ext.name.length > 22 ? ext.name.slice(0, 22) + "…" : ext.name },
      style: {
        background: "#fef2f2",
        border: "1px solid #fecaca",
        color: "#7f1d1d",
        borderRadius: 6,
        width: EXTERNAL_LANE_WIDTH,
        fontSize: 11,
        padding: 6,
        textAlign: "center" as const,
      },
      sourcePosition: Position.Left,
      targetPosition: Position.Left,
      draggable: true,
    });
    codePos[ext.code] = { x, y, w: EXTERNAL_LANE_WIDTH, h: 32 };
  });

  // 3) 边
  for (const e of data.edges) {
    const fromExists = codePos[e.from_code];
    const toExists = codePos[e.to_code];
    if (!fromExists || !toExists) continue;

    const isFocusEdge = focusCode && (e.from_code === focusCode || e.to_code === focusCode);
    const stroke = importanceColor(e.importance);
    edges.push({
      id: `${e.from_code}->${e.to_code}::${e.product_desc?.slice(0, 8) || ""}`,
      source: e.from_code,
      target: e.to_code,
      animated: isFocusEdge || e.both_listed,
      label: e.product_desc ? (e.product_desc.length > 14 ? e.product_desc.slice(0, 14) + "…" : e.product_desc) : "",
      labelStyle: { fontSize: 10, fill: "#4b5563" },
      labelBgStyle: { fill: "rgba(255, 255, 255, 0.85)", fillOpacity: 0.85 },
      style: {
        stroke,
        strokeWidth: e.both_listed ? 2 : 1,
        opacity: focusCode && !isFocusEdge ? 0.15 : 0.85,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: stroke,
        width: 14,
        height: 14,
      },
    });
  }

  // 调整外部上游列起点 y,使其垂直居中于聚簇区
  const upY = Math.max(0, (totalClusterHeight - upstreamExt.length * EXTERNAL_NODE_GAP_Y) / 2);
  upstreamExt.forEach((ext, idx) => {
    const node = nodes.find((n) => n.id === ext.code);
    if (node) node.position.y = upY + idx * EXTERNAL_NODE_GAP_Y;
    if (codePos[ext.code]) codePos[ext.code].y = upY + idx * EXTERNAL_NODE_GAP_Y;
  });
  const dnY = Math.max(0, (totalClusterHeight - downstreamExt.length * EXTERNAL_NODE_GAP_Y) / 2);
  downstreamExt.forEach((ext, idx) => {
    const node = nodes.find((n) => n.id === ext.code);
    if (node) node.position.y = dnY + idx * EXTERNAL_NODE_GAP_Y;
    if (codePos[ext.code]) codePos[ext.code].y = dnY + idx * EXTERNAL_NODE_GAP_Y;
  });

  return { nodes, edges };
}

// ── 主组件 ─────────────────────────────────────────────────────────────────────
export function GlobalSupplyChainView() {
  const { data, error, isLoading } = useSWR<GlobalSupplyChain>(
    "global-supply-chain",
    () => supplyChainApi.global(),
    { revalidateOnFocus: false }
  );
  const [focusCode, setFocusCode] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "watchlist-only" | "high-only">("all");

  const filteredData = useMemo(() => {
    if (!data) return null;
    if (filter === "all") return data;
    if (filter === "watchlist-only") {
      return {
        ...data,
        external_companies: [],
        edges: data.edges.filter((e) => e.both_listed),
      };
    }
    // high-only
    return {
      ...data,
      edges: data.edges.filter((e) => e.importance === "high"),
    };
  }, [data, filter]);

  const layout = useMemo(
    () => (filteredData ? buildLayout(filteredData, focusCode) : { nodes: [], edges: [] }),
    [filteredData, focusCode]
  );

  if (isLoading) {
    return <div className="p-8 text-gray-500 text-sm">加载全局供应链…</div>;
  }
  if (error || !data) {
    return <div className="p-8 text-red-500 text-sm">加载失败,请稍后重试</div>;
  }

  return (
    <div className="flex h-full">
      {/* 左侧:节点列表 + 过滤器 */}
      <aside className="w-64 shrink-0 border-r border-gray-200 overflow-y-auto p-4 space-y-4">
        <div>
          <h3 className="text-xs font-semibold text-gray-700 mb-2">📊 网络统计</h3>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <Stat label="自选股" value={data.stats.watchlist_count} color="text-[#58a6ff]" />
            <Stat label="外部伙伴" value={data.stats.external_count} color="text-gray-600" />
            <Stat label="关联边" value={data.stats.edge_count} color="text-gray-700" />
            <Stat label="自选股互联" value={data.stats.cross_watchlist_edges} color="text-[#ef5350]" />
            <Stat label="行业聚簇" value={data.stats.industry_count} color="text-[#26a69a]" />
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold text-gray-700 mb-2">🔍 视图过滤</h3>
          <div className="space-y-1">
            {([
              { v: "all", label: "全部(默认)" },
              { v: "watchlist-only", label: "仅自选股互联" },
              { v: "high-only", label: "仅核心关系" },
            ] as const).map((f) => (
              <button
                key={f.v}
                onClick={() => setFilter(f.v)}
                className={clsx(
                  "block w-full text-left text-xs px-2 py-1.5 rounded transition-colors",
                  filter === f.v
                    ? "bg-[#58a6ff]/15 text-[#58a6ff] font-medium"
                    : "text-gray-600 hover:bg-gray-100"
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold text-gray-700 mb-2">🎯 焦点高亮</h3>
          <button
            onClick={() => setFocusCode(null)}
            className={clsx(
              "block w-full text-left text-xs px-2 py-1.5 rounded mb-1",
              !focusCode ? "bg-gray-100 font-medium" : "text-gray-600 hover:bg-gray-100"
            )}
          >
            清除焦点
          </button>
          <div className="max-h-[40vh] overflow-y-auto space-y-0.5">
            {data.watchlist_stocks
              .slice()
              .sort((a, b) => a.code.localeCompare(b.code))
              .map((s) => (
                <button
                  key={s.code}
                  onClick={() => setFocusCode(s.code === focusCode ? null : s.code)}
                  className={clsx(
                    "block w-full text-left text-xs px-2 py-1 rounded transition-colors",
                    focusCode === s.code
                      ? "bg-orange-100 text-orange-700 font-medium"
                      : "text-gray-600 hover:bg-gray-100"
                  )}
                >
                  <span className="font-medium">{s.name}</span>
                  <span className="text-gray-400 ml-1">{s.code}</span>
                </button>
              ))}
          </div>
        </div>

        <div className="text-[10px] text-gray-400 leading-relaxed border-t border-gray-200 pt-3">
          <p className="mb-1">· 自选股按 <span className="text-[#58a6ff]">行业</span> 聚簇分组</p>
          <p className="mb-1">· 外部公司按上游(左)/下游(右)分列</p>
          <p className="mb-1">· 边色:🔴 核心 · 🟡 重要 · ⚪ 一般</p>
          <p>· 点击节点跳转个股页;点击焦点高亮关联边</p>
        </div>
      </aside>

      {/* 右侧:ReactFlow 画布 */}
      <div className="flex-1 min-h-0 bg-[#fafbfc]">
        <ReactFlow
          nodes={layout.nodes}
          edges={layout.edges}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.2}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e5e7eb" />
          <Controls position="bottom-right" />
          <MiniMap
            position="top-right"
            nodeColor={(n) => {
              if (n.type === "group") return "rgba(88, 166, 255, 0.1)";
              if (n.id.startsWith("_ext::")) return "#e5e7eb";
              return "#58a6ff";
            }}
            pannable
            zoomable
          />
        </ReactFlow>
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded px-2 py-1.5">
      <p className="text-[10px] text-gray-500 mb-0.5">{label}</p>
      <p className={clsx("text-base font-bold tabular-nums", color)}>{value}</p>
    </div>
  );
}
