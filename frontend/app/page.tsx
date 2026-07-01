import Link from "next/link";
import { Activity, AlertTriangle, BarChart3, ChevronRight, Database, Target } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://backend:8000";

type Stats = {
  total_predictions: number;
  value_predictions: number;
  recent_value_rate: number;
};

type Prediction = {
  id: number;
  fixture_id: number;
  home_team: string | null;
  away_team: string | null;
  league: string | null;
  kickoff: string | null;
  best_pick: string | null;
  best_odds: number | null;
  best_ev: number | null;
  best_kelly: number | null;
  value_score: number | null;
  risk: string | null;
  created_at: string | null;
};

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) {
      return fallback;
    }
    return response.json();
  } catch {
    return fallback;
  }
}

function fmtPercent(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

export default async function DashboardPage() {
  const [stats, predictions] = await Promise.all([
    getJson<Stats>("/v1/stats", {
      total_predictions: 0,
      value_predictions: 0,
      recent_value_rate: 0,
    }),
    getJson<Prediction[]>("/v1/predictions/recent?limit=12", []),
  ]);

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <section className="mb-8 flex flex-col gap-3 border-b border-slate-200 pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">FootballQuant 控制台</h1>
          <p className="mt-1 text-sm text-slate-600">
            Telegram 主流程、赔率快照、价值方向和赛后复盘的只读监控面板
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Link href="/today" className="rounded-md border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-100">
            今日比赛
          </Link>
          <Link href="/stats" className="rounded-md border border-slate-200 px-3 py-2 text-slate-700 hover:bg-slate-100">
            模型统计
          </Link>
          <Activity className="h-4 w-4" />
          Docker MVP
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">总分析</span>
            <Database className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-3 text-3xl font-semibold">{stats.total_predictions}</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">有价值方向</span>
            <Target className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-3 text-3xl font-semibold">{stats.value_predictions}</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">价值方向占比</span>
            <BarChart3 className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-3 text-3xl font-semibold">{fmtPercent(stats.recent_value_rate)}</div>
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-base font-semibold">最近预测</h2>
          <span className="text-xs text-slate-500">{predictions.length} 条</span>
        </div>
        {predictions.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
                <tr>
                  <th className="px-5 py-3">比赛</th>
                  <th className="px-5 py-3">价值方向</th>
                  <th className="px-5 py-3">赔率</th>
                  <th className="px-5 py-3">EV</th>
                  <th className="px-5 py-3">Kelly</th>
                  <th className="px-5 py-3">评分</th>
                  <th className="px-5 py-3">风险</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {predictions.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="px-5 py-4">
                      <div className="font-medium text-slate-950">
                        {item.home_team || "Unknown"} vs {item.away_team || "Unknown"}
                      </div>
                      <div className="text-xs text-slate-500">
                        {item.league || "-"} · {item.kickoff?.slice(0, 16).replace("T", " ") || "-"}
                      </div>
                    </td>
                    <td className="px-5 py-4">{item.best_pick || "观望"}</td>
                    <td className="px-5 py-4">{item.best_odds?.toFixed(2) || "-"}</td>
                    <td className="px-5 py-4">{fmtPercent(item.best_ev)}</td>
                    <td className="px-5 py-4">{item.best_kelly?.toFixed(3) || "-"}</td>
                    <td className="px-5 py-4">{item.value_score ?? 0}</td>
                    <td className="px-5 py-4">{item.risk || "-"}</td>
                    <td className="px-5 py-4">
                      <Link
                        href={`/matches/${item.fixture_id}`}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-100"
                        title="查看详情"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex items-center gap-3 px-5 py-8 text-sm text-slate-500">
            <AlertTriangle className="h-4 w-4" />
            暂无预测记录。通过 Telegram 发送 `/分析 Botafogo SP vs CRB` 后会显示在这里。
          </div>
        )}
      </section>
    </main>
  );
}
