import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://backend:8000";

type Bucket = { count: number; hit_rate: number; profit_units: number };
type Performance = {
  overall: Bucket;
  by_market: Record<string, Bucket>;
  by_bookmaker_count: Record<string, Bucket>;
  by_consensus: Record<string, Bucket>;
  by_disagreement: Record<string, Bucket>;
  recommendations: string[];
};

async function getPerformance(): Promise<Performance> {
  const empty = {
    overall: { count: 0, hit_rate: 0, profit_units: 0 },
    by_market: {},
    by_bookmaker_count: {},
    by_consensus: {},
    by_disagreement: {},
    recommendations: [],
  };
  try {
    const response = await fetch(`${API_BASE}/v1/stats/performance`, { cache: "no-store" });
    if (!response.ok) return empty;
    return response.json();
  } catch {
    return empty;
  }
}

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function Table({ title, data }: { title: string; data: Record<string, Bucket> }) {
  const rows = Object.entries(data);
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-5 py-4 font-semibold">{title}</div>
      <div className="divide-y divide-slate-100">
        {rows.length ? rows.map(([key, item]) => (
          <div key={key} className="grid grid-cols-4 gap-4 px-5 py-3 text-sm">
            <span className="font-medium">{key}</span>
            <span>{item.count} 场</span>
            <span>命中 {pct(item.hit_rate)}</span>
            <span>收益 {item.profit_units.toFixed(2)}</span>
          </div>
        )) : <div className="px-5 py-6 text-sm text-slate-500">暂无复盘样本。</div>}
      </div>
    </section>
  );
}

export default async function StatsPage() {
  const perf = await getPerformance();
  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6 flex items-end justify-between border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-2xl font-semibold">模型统计</h1>
          <p className="mt-1 text-sm text-slate-500">命中率、盘口表现和复盘建议</p>
        </div>
        <Link href="/" className="text-sm text-slate-600 hover:text-slate-950">返回控制台</Link>
      </div>

      <section className="mb-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="text-sm text-slate-500">已复盘推荐</div>
          <div className="mt-2 text-3xl font-semibold">{perf.overall.count}</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="text-sm text-slate-500">总命中率</div>
          <div className="mt-2 text-3xl font-semibold">{pct(perf.overall.hit_rate)}</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="text-sm text-slate-500">单位收益</div>
          <div className="mt-2 text-3xl font-semibold">{perf.overall.profit_units.toFixed(2)}</div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Table title="盘口表现" data={perf.by_market} />
        <Table title="机构数表现" data={perf.by_bookmaker_count} />
        <Table title="一致性评分表现" data={perf.by_consensus} />
        <Table title="赔率分歧表现" data={perf.by_disagreement} />
      </div>

      <section className="mt-6 rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-5 py-4 font-semibold">复盘建议</div>
        <div className="space-y-2 px-5 py-4 text-sm text-slate-700">
          {perf.recommendations.length ? perf.recommendations.map((item, idx) => (
            <p key={idx}>{idx + 1}. {item}</p>
          )) : <p>暂无建议。</p>}
        </div>
      </section>
    </main>
  );
}
