import { WatchlistWithTagFilter } from "@/components/dashboard/WatchlistWithTagFilter";
import { NewsFeed } from "@/components/news/NewsFeed";
import { SearchBar } from "@/components/stock/SearchBar";

export default function HomePage() {
  return (
    <main className="min-h-screen">
      <header className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900 tracking-tight">MyStock</h1>
        <div className="flex items-center gap-4">
          <SearchBarWrapper />
          <a href="/research" className="text-xs text-gray-500 hover:text-gray-700 transition-colors px-2 py-1 rounded hover:bg-gray-100">
            研报
          </a>
          <a href="/earnings" className="text-xs text-gray-500 hover:text-gray-700 transition-colors px-2 py-1 rounded hover:bg-gray-100">
            财报
          </a>
          <a href="/backtest" className="text-xs text-gray-500 hover:text-gray-700 transition-colors px-2 py-1 rounded hover:bg-gray-100">
            回测
          </a>
          <a href="/settings" className="text-xs text-gray-500 hover:text-gray-700 transition-colors px-2 py-1 rounded hover:bg-gray-100">
            设置
          </a>
        </div>
      </header>

      <div className="flex h-[calc(100vh-57px)]">
        <div className="flex-1 overflow-y-auto p-6">
          <WatchlistWithTagFilter />
        </div>
        <aside className="w-80 border-l border-gray-200 overflow-y-auto p-4">
          <h2 className="text-sm font-semibold text-gray-600 mb-3">最新资讯</h2>
          <NewsFeed />
        </aside>
      </div>
    </main>
  );
}

// SearchBar 是 Client Component，需要在 Server Page 中包装
function SearchBarWrapper() {
  return <SearchBarClient />;
}

// 动态引入避免 SSR 问题
import dynamic from "next/dynamic";
const SearchBarClient = dynamic(
  () => import("@/components/stock/SearchBar").then((m) => ({ default: m.SearchBar })),
  { ssr: false }
);
