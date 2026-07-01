import Link from "next/link";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  Database,
  type LucideIcon,
  ShieldAlert,
  Target,
} from "lucide-react";
import { fetchServerJson } from "@/lib/server-api";
import type {
  HealthStatus,
  PerformanceSummary,
  PredictionRow,
  StatsSummary,
  TodayMatch,
} from "@/lib/types";

const emptyStats: StatsSummary = {
  total_predictions: 0,
  value_predictions: 0,
  settled_predictions: 0,
  recent_value_rate: 0,
};

const emptyPerformance: PerformanceSummary = {
  overall: { count: 0, hit_rate: 0, profit_units: 0 },
  by_market: {},
  by_bookmaker_count: {},
  by_consensus: {},
  by_disagreement: {},
  recommendations: [],
};

function pct(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function num(value?: number | null, digits = 2) {
  if (value === null || value === undefined) return "-";
  return value.toFixed(digits);
}

function riskClass(risk?: string | null) {
  if (risk === "低") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (risk === "高") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function statusClass(status?: string | null) {
  if (status === "ok" || status === "online") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return value.slice(0, 16).replace("T", " ");
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
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-slate-500">{label}</span>
        <Icon className="h-4 w-4 text-slate-400" />
      </div>
      <div className="mt-3 text-2xl font-semibold tracking-normal text-slate-950">
        {value}
      </div>
      <div className="mt-1 text-xs text-slate-500">{detail}</div>
    </div>
  );
}

export default async function DashboardPage() {
  const [health, stats, predictions, today, perf] = await Promise.all([
    fetchServerJson<HealthStatus>("/health", { status: "offline", version: "-" }),
    fetchServerJson<StatsSummary>("/v1/stats", emptyStats),
    fetchServerJson<PredictionRow[]>("/v1/predictions/recent?limit=12", []),
    fetchServerJson<TodayMatch[]>("/v1/matches/today", []),
    fetchServerJson<PerformanceSummary>("/v1/stats/performance", emptyPerformance),
  ]);

  const analyzedToday = today.filter((item) => item.analyzed).length;
  const valueRows = predictions
    .filter((item) => (item.best_ev || 0) > 0 || item.best_pick)
    .slice(0, 5);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <section className="mb-6 flex flex-col gap-3 border-b border-slate-200 pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">控制台</h1>
          <p className="mt-1 text-sm text-slate-600">
            API-Football 赔率、引擎判断、价值候选、Telegram 输出和复盘结果
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`status-pill ${statusClass(health.status)}`}>
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            API {health.status}
          </span>
          <Link
            href="/predict"
            className="inline-flex items-center gap-1.5 rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            单场预测
            <ArrowUpRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="今日比赛"
          value={today.length}
          detail={`${analyzedToday} 场已生成分析`}
          icon={Database}
        />
        <StatCard
          label="总分析"
          value={stats.total_predictions}
          detail={`${stats.value_predictions} 条有价值方向`}
          icon={Activity}
        />
        <StatCard
          label="价值方向占比"
          value={pct(stats.recent_value_rate)}
          detail={`${stats.settled_predictions || 0} 条已复盘`}
          icon={Target}
        />
        <StatCard
          label="复盘收益"
          value={`${perf.overall.profit_units >= 0 ? "+" : ""}${num(
            perf.overall.profit_units
          )}u`}
          detail={`命中 ${pct(perf.overall.hit_rate)} / ${perf.overall.count} 条样本`}
          icon={BarChart3}
        />
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
        <div className="panel overflow-hidden">
          <div className="panel-header">
            <div>
              <h2 className="text-base font-semibold">核心输出</h2>
              <p className="mt-1 text-xs text-slate-500">按最近生成的价值方向展示</p>
            </div>
            <Link href="/today" className="text-sm text-primary-700 hover:text-primary-900">
              今日比赛
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
                <tr>
                  <th className="px-5 py-3">比赛</th>
                  <th className="px-5 py-3">方向</th>
                  <th className="px-5 py-3">赔率</th>
                  <th className="px-5 py-3">EV</th>
                  <th className="px-5 py-3">Kelly</th>
                  <th className="px-5 py-3">风险</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {valueRows.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="px-5 py-4">
                      <Link
                        href={`/matches/${item.fixture_id}`}
                        className="font-medium text-slate-950 hover:text-primary-700"
                      >
                        {item.home_team || "Unknown"} vs {item.away_team || "Unknown"}
                      </Link>
                      <div className="mt-1 text-xs text-slate-500">
                        {item.league || "-"} · {formatDate(item.kickoff)}
                      </div>
                    </td>
                    <td className="px-5 py-4">{item.best_pick || "观望"}</td>
                    <td className="px-5 py-4">
                      {num(item.best_odds)}
                      {item.best_bookmaker ? (
                        <div className="mt-1 text-xs text-slate-500">{item.best_bookmaker}</div>
                      ) : null}
                    </td>
                    <td className="px-5 py-4 text-emerald-700">{pct(item.best_ev)}</td>
                    <td className="px-5 py-4">{num(item.best_kelly, 3)}</td>
                    <td className="px-5 py-4">
                      <span className={`status-pill ${riskClass(item.risk)}`}>
                        {item.risk || "中"}
                      </span>
                    </td>
                  </tr>
                ))}
                {!valueRows.length && (
                  <tr>
                    <td className="px-5 py-8 text-slate-500" colSpan={6}>
                      暂无价值输出。可以从单场预测页或 Telegram 发起分析。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-6">
          <section className="panel">
            <div className="panel-header">
              <h2 className="text-base font-semibold">今日状态</h2>
              <span className="text-xs text-slate-500">{today.length} 场</span>
            </div>
            <div className="divide-y divide-slate-100">
              {today.slice(0, 5).map((item) => (
                <Link
                  key={item.fixture_id}
                  href={`/matches/${item.fixture_id}`}
                  className="block px-5 py-3 hover:bg-slate-50"
                >
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-medium text-slate-950">
                      {item.home_team} vs {item.away_team}
                    </span>
                    <span className="text-xs text-slate-500">{item.analyzed ? "已分析" : "待分析"}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {item.league || "-"} · {formatDate(item.kickoff)}
                  </div>
                </Link>
              ))}
              {!today.length && (
                <div className="flex items-center gap-2 px-5 py-6 text-sm text-slate-500">
                  <ShieldAlert className="h-4 w-4" />
                  今日暂无入库比赛。
                </div>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2 className="text-base font-semibold">系统建议</h2>
            </div>
            <div className="space-y-2 px-5 py-4 text-sm text-slate-700">
              {(perf.recommendations.length
                ? perf.recommendations
                : ["样本量不足，先积累分析与复盘数据。"]
              ).map((item, index) => (
                <p key={index}>{item}</p>
              ))}
            </div>
          </section>
        </div>
      </section>

      <section className="panel mt-6 overflow-hidden">
        <div className="panel-header">
          <h2 className="text-base font-semibold">最近预测</h2>
          <span className="text-xs text-slate-500">{predictions.length} 条</span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
              <tr>
                <th className="px-5 py-3">比赛</th>
                <th className="px-5 py-3">市场</th>
                <th className="px-5 py-3">方向</th>
                <th className="px-5 py-3">评分</th>
                <th className="px-5 py-3">复盘</th>
                <th className="px-5 py-3">生成时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {predictions.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50">
                  <td className="px-5 py-4">
                    <Link
                      href={`/matches/${item.fixture_id}`}
                      className="font-medium text-slate-950 hover:text-primary-700"
                    >
                      {item.home_team || "Unknown"} vs {item.away_team || "Unknown"}
                    </Link>
                  </td>
                  <td className="px-5 py-4">{item.best_market || "-"}</td>
                  <td className="px-5 py-4">{item.best_pick || "观望"}</td>
                  <td className="px-5 py-4">{item.value_score ?? 0}</td>
                  <td className="px-5 py-4">{item.settled_status || "pending"}</td>
                  <td className="px-5 py-4">{formatDate(item.created_at)}</td>
                </tr>
              ))}
              {!predictions.length && (
                <tr>
                  <td className="px-5 py-8 text-slate-500" colSpan={6}>
                    暂无预测记录。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
