"use client";

import Link from "next/link";
import useSWR from "swr";
import { stocksApi, StockRead } from "@/lib/api/stocks";
import { clsx } from "clsx";

const SIGNAL_MAP = {
  bullish: { label: "看多", cls: "bg-[#ef5350]/10 text-[#ef5350]" },
  bearish: { label: "看空", cls: "bg-[#26a69a]/10 text-[#26a69a]" },
  neutral: { label: "中性", cls: "bg-gray-200 text-gray-600" },
};

function SignalBadge({ signal }: { signal: string | null }) {
  const s = SIGNAL_MAP[signal as keyof typeof SIGNAL_MAP] ?? SIGNAL_MAP.neutral;
  return <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", s.cls)}>{s.label}</span>;
}

function StockCard({ stock }: { stock: StockRead }) {
  return (
    <Link
      href={`/stocks/${stock.code}`}
      className="block p-4 rounded-lg bg-[#f6f8fa] border border-gray-200 hover:border-[#58a6ff]/50 transition-colors group"
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <span className="font-semibold text-gray-900 group-hover:text-[#58a6ff] transition-colors">
            {stock.name}
          </span>
          <span className="ml-2 text-xs text-gray-500">{stock.code}</span>
        </div>
        <SignalBadge signal={null} />
      </div>

      <div className="text-xs text-gray-500 mb-2">
        {stock.industry ?? "—"} · {stock.market === "A" ? "A股" : "港股"}
      </div>

      {!stock.data_ready ? (
        <div className="space-y-1">
          <p className="text-xs text-gray-400">数据准备中...</p>
          <div className="h-1 w-full bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-[#58a6ff] w-1/3 animate-pulse rounded-full" />
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-gray-400">数据就绪</span>
          <span className="w-1.5 h-1.5 rounded-full bg-[#26a69a] inline-block" />
        </div>
      )}
    </Link>
  );
}

export function WatchlistDashboard() {
  const { data: stocks, error, isLoading } = useSWR(
    "watchlist",
    stocksApi.watchlist,
    { refreshInterval: 30000 }
  );

  if (isLoading)
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-28 bg-[#f6f8fa] rounded-lg animate-pulse border border-gray-200" />
        ))}
      </div>
    );

  if (error)
    return <div className="text-red-400 text-sm">加载失败，请检查后端服务是否启动</div>;

  if (!stocks?.length)
    return (
      <div className="text-center mt-24">
        <p className="text-4xl mb-4">📈</p>
        <p className="text-gray-600 text-lg mb-2">暂无自选股</p>
        <p className="text-gray-400 text-sm">在上方搜索框中输入股票代码或名称添加自选股</p>
      </div>
    );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-600">
          自选股 <span className="text-gray-400">({stocks.length})</span>
        </h2>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {stocks.map((s) => (
          <StockCard key={s.code} stock={s} />
        ))}
      </div>
    </div>
  );
}
