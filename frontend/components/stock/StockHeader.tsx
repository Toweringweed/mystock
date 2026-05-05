"use client";

import useSWR from "swr";
import { stocksApi } from "@/lib/api/stocks";

export function StockHeader({ code }: { code: string }) {
  const { data } = useSWR(`stock-${code}`, () => stocksApi.get(code));

  return (
    <header className="border-b border-gray-200 px-6 py-4">
      <a href="/" className="text-sm text-gray-500 hover:text-gray-700 mb-2 inline-block">
        ← 返回
      </a>
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold text-gray-900">{data?.name ?? code}</h1>
        <span className="text-gray-500 text-sm">{code}</span>
        <span className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">
          {data?.market === "A" ? "A股" : "港股"}
        </span>
      </div>
      {data?.industry && (
        <p className="text-sm text-gray-500 mt-1">{data.industry}</p>
      )}
    </header>
  );
}
