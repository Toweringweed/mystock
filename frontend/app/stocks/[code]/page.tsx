import { StockDetailView } from "@/components/stock/StockDetailView";

interface Props {
  params: { code: string };
}

export default function StockDetailPage({ params }: Props) {
  return (
    <main className="min-h-screen px-6 py-4">
      <StockDetailView code={params.code} />
    </main>
  );
}
