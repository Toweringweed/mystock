"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ResearchLibrary } from "@/components/research/ResearchLibrary";

function ResearchPageInner() {
  const params = useSearchParams();
  const code = params.get("code");

  return (
    <main className="min-h-screen">
      <header className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            ← 返回
          </Link>
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">券商研报库</h1>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/" className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100">
            自选股
          </Link>
          <Link href="/settings" className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100">
            设置
          </Link>
        </div>
      </header>
      <div className="p-6">
        <ResearchLibrary initialCode={code} />
      </div>
    </main>
  );
}

export default function ResearchPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-500 text-sm">加载中…</div>}>
      <ResearchPageInner />
    </Suspense>
  );
}
