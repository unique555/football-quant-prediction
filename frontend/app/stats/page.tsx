import { BarChart3, type LucideIcon, Sigma, Target, Trophy } from "lucide-react";
import { fetchServerJson } from "@/lib/server-api";
import type { PerformanceBucket, PerformanceSummary } from "@/lib/types";

const emptyPerformance: PerformanceSummary = {
  overall: { count: 0, hit_rate: 0, profit_units: 0 },
  by_market: {},
  by_bookmaker_count: {},
  by_consensus: {},
  by_disagreement: {},
  recommendations: [],
};

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function StatCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: LucideIcon;
}) {
  return (
    <div className="card">
      <div className="flex items-center justify-between text-sm text-slate-500">
        {label}
        <Icon className="h-4 w-4" />
      </div>
      <div className="mt-3 text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{detail}</div>
    </div>
  );
}

function BucketTable({
  title,
  description,
  data,
}: {
  title: string;
  description: string;
  data: Record<string, PerformanceBucket>;
}) {
  const rows = Object.entries(data);
  return (
    <section className="panel overflow-hidden">
      <div className="panel-header">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-xs text-slate-500">{description}</p>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3">分组</th>
              <th className="px-5 py-3">样本</th>
              <th className="px-5 py-3">命中率</th>
              <th className="px-5 py-3">收益</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map(([key, item]) => (
              <tr key={key} className="hover:bg-slate-50">
                <td className="px-5 py-4 font-medium text-slate-950">{key}</td>
                <td className="px-5 py-4">{item.count}</td>
                <td className="px-5 py-4">{pct(item.hit_rate)}</td>
                <td
                  className={
                    item.profit_units >= 0
                      ? "px-5 py-4 text-emerald-700"
                      : "px-5 py-4 text-rose-700"
                  }
                >
                  {item.profit_units >= 0 ? "+" : ""}
                  {item.profit_units.toFixed(2)}u
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td className="px-5 py-7 text-slate-500" colSpan={4}>
                  暂无复盘样本。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default async function StatsPage() {
  const perf = await fetchServerJson<PerformanceSummary>(
    "/v1/stats/performance",
    emptyPerformance
  );

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 border-b border-slate-200 pb-5">
        <h1 className="text-2xl font-semibold text-slate-950">统计</h1>
        <p className="mt-1 text-sm text-slate-600">
          复盘样本、盘口表现、机构一致性和收益曲线摘要
        </p>
      </div>

      <section className="mb-6 grid gap-4 md:grid-cols-3">
        <StatCard
          label="已复盘推荐"
          value={perf.overall.count}
          detail="仅统计已结算价值候选"
          icon={Sigma}
        />
        <StatCard
          label="总命中率"
          value={pct(perf.overall.hit_rate)}
          detail="win / half_win 计入命中"
          icon={Target}
        />
        <StatCard
          label="单位收益"
          value={`${perf.overall.profit_units >= 0 ? "+" : ""}${perf.overall.profit_units.toFixed(2)}u`}
          detail="按候选记录 profit_units 汇总"
          icon={Trophy}
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <BucketTable
          title="盘口表现"
          description="按 market 聚合"
          data={perf.by_market}
        />
        <BucketTable
          title="机构数表现"
          description="按可用 bookmaker 数聚合"
          data={perf.by_bookmaker_count}
        />
        <BucketTable
          title="一致性表现"
          description="按 consensus_score 分桶"
          data={perf.by_consensus}
        />
        <BucketTable
          title="分歧度表现"
          description="按 disagreement_index 分桶"
          data={perf.by_disagreement}
        />
      </div>

      <section className="panel mt-6">
        <div className="panel-header">
          <h2 className="text-base font-semibold">复盘建议</h2>
        </div>
        <div className="space-y-2 px-5 py-4 text-sm text-slate-700">
          {(perf.recommendations.length
            ? perf.recommendations
            : ["暂无建议，等待更多结算样本。"]
          ).map((item, index) => (
            <p key={index}>{item}</p>
          ))}
        </div>
      </section>
    </main>
  );
}
