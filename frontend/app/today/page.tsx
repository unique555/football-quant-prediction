import Link from "next/link";
import { CalendarDays, CheckCircle2, Clock, Search } from "lucide-react";
import { fetchServerJson } from "@/lib/server-api";
import type { TodayMatch } from "@/lib/types";

function formatDate(value?: string | null) {
  if (!value) return "-";
  return value.slice(0, 16).replace("T", " ");
}

function riskClass(risk?: string | null) {
  if (risk === "低") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (risk === "高") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

export default async function TodayPage() {
  const matches = await fetchServerJson<TodayMatch[]>("/v1/matches/today", []);
  const analyzed = matches.filter((item) => item.analyzed).length;
  const pending = matches.length - analyzed;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 flex flex-col gap-3 border-b border-slate-200 pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">今日比赛</h1>
          <p className="mt-1 text-sm text-slate-600">
            当日入库赛程、预测状态、价值方向和赛后复盘状态
          </p>
        </div>
        <Link
          href="/predict"
          className="inline-flex items-center gap-1.5 rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          <Search className="h-4 w-4" />
          单场预测
        </Link>
      </div>

      <section className="mb-6 grid gap-4 md:grid-cols-3">
        <div className="card">
          <div className="flex items-center justify-between text-sm text-slate-500">
            今日总场次
            <CalendarDays className="h-4 w-4" />
          </div>
          <div className="mt-3 text-2xl font-semibold">{matches.length}</div>
        </div>
        <div className="card">
          <div className="flex items-center justify-between text-sm text-slate-500">
            已分析
            <CheckCircle2 className="h-4 w-4" />
          </div>
          <div className="mt-3 text-2xl font-semibold">{analyzed}</div>
        </div>
        <div className="card">
          <div className="flex items-center justify-between text-sm text-slate-500">
            待分析
            <Clock className="h-4 w-4" />
          </div>
          <div className="mt-3 text-2xl font-semibold">{pending}</div>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="panel-header">
          <h2 className="text-base font-semibold">赛程列表</h2>
          <span className="text-xs text-slate-500">{matches.length} 场</span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
              <tr>
                <th className="px-5 py-3">比赛</th>
                <th className="px-5 py-3">开赛时间</th>
                <th className="px-5 py-3">状态</th>
                <th className="px-5 py-3">最优方向</th>
                <th className="px-5 py-3">评分</th>
                <th className="px-5 py-3">风险</th>
                <th className="px-5 py-3">复盘</th>
                <th className="px-5 py-3">比分</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {matches.map((item) => (
                <tr key={item.fixture_id} className="hover:bg-slate-50">
                  <td className="px-5 py-4">
                    <Link
                      href={`/matches/${item.fixture_id}`}
                      className="font-medium text-slate-950 hover:text-primary-700"
                    >
                      {item.home_team} vs {item.away_team}
                    </Link>
                    <div className="mt-1 text-xs text-slate-500">{item.league || "-"}</div>
                  </td>
                  <td className="px-5 py-4">{formatDate(item.kickoff)}</td>
                  <td className="px-5 py-4">
                    <span
                      className={
                        item.analyzed
                          ? "status-pill border-emerald-200 bg-emerald-50 text-emerald-700"
                          : "status-pill border-slate-200 bg-slate-50 text-slate-600"
                      }
                    >
                      {item.analyzed ? "已分析" : "待分析"}
                    </span>
                  </td>
                  <td className="px-5 py-4">{item.best_pick || "观望/未分析"}</td>
                  <td className="px-5 py-4">{item.value_score ?? "-"}</td>
                  <td className="px-5 py-4">
                    <span className={`status-pill ${riskClass(item.risk)}`}>
                      {item.risk || "-"}
                    </span>
                  </td>
                  <td className="px-5 py-4">{item.review_status || "pending"}</td>
                  <td className="px-5 py-4">{item.score || "-"}</td>
                </tr>
              ))}
              {!matches.length && (
                <tr>
                  <td className="px-5 py-8 text-slate-500" colSpan={8}>
                    暂无今日比赛记录。
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
