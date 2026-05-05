"use client";

import { useState, useRef, useEffect } from "react";
import { stocksApi, StockSearch } from "@/lib/api/stocks";

export function SearchBar({ onAdded }: { onAdded?: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StockSearch[]>([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 点击外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleInput = (v: string) => {
    setQuery(v);
    if (!v.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await stocksApi.search(v.trim());
        setResults(data);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  };

  const handleAdd = async (stock: StockSearch) => {
    setAdding(stock.code);
    try {
      await stocksApi.add(stock.code, stock.market, stock.name);
      setQuery("");
      setResults([]);
      setOpen(false);
      onAdded?.();
    } catch (e) {
      console.error(e);
    } finally {
      setAdding(null);
    }
  };

  return (
    <div ref={ref} className="relative">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          placeholder="搜索股票代码或名称..."
          className="w-64 pl-3 pr-8 py-1.5 rounded bg-[#f6f8fa] border border-gray-300 text-sm text-gray-800 placeholder-gray-500 focus:outline-none focus:border-[#58a6ff] transition-colors"
        />
        {loading && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 text-xs animate-spin">
            ⟳
          </span>
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute top-full mt-1 w-80 bg-[#f6f8fa] border border-gray-300 rounded-lg shadow-xl z-50 overflow-hidden">
          {results.map((stock) => (
            <button
              key={stock.code}
              onClick={() => handleAdd(stock)}
              disabled={adding === stock.code}
              className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-gray-100 transition-colors text-left disabled:opacity-50"
            >
              <div>
                <span className="text-sm text-gray-800 font-medium">{stock.name}</span>
                <span className="ml-2 text-xs text-gray-500">{stock.code}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs bg-gray-200 px-1.5 py-0.5 rounded text-gray-600">
                  {stock.market === "A" ? "A股" : "港股"}
                </span>
                {adding === stock.code ? (
                  <span className="text-xs text-[#58a6ff]">添加中...</span>
                ) : (
                  <span className="text-xs text-gray-400 group-hover:text-[#58a6ff]">+添加</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {open && !loading && results.length === 0 && query.trim() && (
        <div className="absolute top-full mt-1 w-80 bg-[#f6f8fa] border border-gray-300 rounded-lg shadow-xl z-50 px-4 py-3 text-xs text-gray-500">
          未找到匹配的股票
        </div>
      )}
    </div>
  );
}
