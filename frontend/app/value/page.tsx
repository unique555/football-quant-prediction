import { ValueBetsClient } from "@/components/value/ValueBetsClient";

export default function ValuePage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 border-b border-slate-200 pb-5">
        <h1 className="text-2xl font-semibold text-slate-950">价值投注</h1>
        <p className="mt-1 text-sm text-slate-600">
          系统自动筛选的 Edge &gt; 3% 的价值投注，含 Kelly 注额建议
        </p>
      </div>
      <ValueBetsClient />
    </main>
  );
}
