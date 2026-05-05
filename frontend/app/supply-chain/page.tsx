"use client";

import Link from "next/link";
import { GlobalSupplyChainView } from "@/components/supply-chain/GlobalSupplyChainView";

export default function SupplyChainPage() {
  return (
    <main className="min-h-screen flex flex-col">
      <header className="border-b border-gray-200 px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            ← 返回
          </Link>
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">📊 全局供应链图</h1>
          <span className="text-xs text-gray-500">自选股按行业聚簇 · 上下游关联</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/" className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100">
            自选股
          </Link>
          <Link href="/research" className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100">
            研报库
          </Link>
          <Link href="/settings" className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100">
            设置
          </Link>
        </div>
      </header>
      <div className="flex-1 min-h-0">
        <GlobalSupplyChainView />
      </div>
    </main>
  );
}
