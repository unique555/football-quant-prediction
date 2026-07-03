import Link from "next/link";
import { ArrowLeft, BarChart3, Clock, Shield, Target } from "lucide-react";
import { fetchServerJson } from "@/lib/server-api";

type MatchDetail = {
  fixture_id: number;
  home_team: string;
  away_team: string;
  league: string;
  kickoff: string;
  status: string;
  result: {
    home_goals: number | null;
    away_goals: number | null;
    status: string | null;
  } | null;
  predictions: Array<{
    best_pick: string | null;
    value_score: number | null;
    risk: string | null;
    settled_status: string | null;
    profit_units: number | null;
    settlement_note: string | null;
    created_at: string | null;
    report_text: string | null;
  }>;
  value_candidates: Array<{
    market: string;
    pick: string;
    line: number | null;
    odds: number | null;
    prob: number | null;
    market_prob: number | null;
    ev: number | null;
    kelly: number | null;
    edge: number | null;
    bookmaker_count: number | null;
    consensus_score: number | null;
    disagreement_index: number | null;
    risk: string | null;
    value_score: number | null;
    selected: boolean | null;
    settled_status: string | null;
    settlement_note: string | null;
  }>;
  odds_snapshots: Array<{
    market: string;
    bookmaker: string | null;
    home_odds: number | null;
    draw_odds: number | null;
    away_odds: number | null;
    ah_line: number | null;
    ah_home_odds: number | null;
    ah_away_odds: number | null;
    ou_line: number | null;
    over_odds: number | null;
    under_odds: number | null;
    snapshot_type: string | null;
    captured_at: string | null;
  }>;
};

function pct(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function num(value?: number | null, digits = 2) {
  if (value === null || value === undefined) return "-";
  return value.toFixed(digits);
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return value.slice(0, 16).replace("T", " ");
}

function riskClass(risk?: string | null) {
  if (risk === "低") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (risk === "高") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function oddsText(item: MatchDetail["odds_snapshots"][number]) {
  if (item.market === "1x2") {
    return `${num(item.home_odds)} / ${num(item.draw_odds)} / ${num(item.away_odds)}`;
  }
  if (item.market === "asian_handicap") {
    return `AH ${item.ah_line ?? "-"} · ${num(item.ah_home_odds)} / ${num(item.ah_away_odds)}`;
  }
  if (item.market === "over_under") {
    return `OU ${item.ou_line ?? "-"} · ${num(item.over_odds)} / ${num(item.under_odds)}`;
  }
  return "-";
}

export default async function MatchDetailPage({
  params,
}: {
  params: { fixture_id: string };
}) {
  const detail = await fetchServerJson<MatchDetail | null>(
    `/v1/matches/${params.fixture_id}`,
    null
  );

  if (!detail) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-sm text-slate-600">
          <ArrowLeft className="h-4 w-4" />
          返回控制台
        </Link>
        <div className="panel px-5 py-8 text-sm text-slate-500">未找到比赛记录。</div>
      </main>
    );
  }

  const latest = detail.predictions[0];
  const selected = detail.value_candidates.find((item) => item.selected) || detail.value_candidates[0];
  const score =
    detail.result && detail.result.home_goals !== null
      ? `${detail.result.home_goals}:${detail.result.away_goals}`
      : "-";

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <Link href="/" className="mb-5 inline-flex items-center gap-2 text-sm text-slate-600 hover:text-slate-950">
        <ArrowLeft className="h-4 w-4" />
        返回控制台
      </Link>

      <section className="mb-6 border-b border-slate-200 pb-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">
              {detail.home_team} vs {detail.away_team}
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              {detail.league || "-"} · {formatDate(detail.kickoff)} · fixture {detail.fixture_id}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="status-pill border-slate-200 bg-white text-slate-700">
              {detail.status || "-"}
            </span>
            <span className="status-pill border-slate-200 bg-white text-slate-700">
              比分 {score}
            </span>
          </div>
        </div>
      </section>

      <section className="mb-6 grid gap-4 md:grid-cols-4">
        <div className="card">
          <div className="flex items-center justify-between text-sm text-slate-500">
            最优方向
            <Target className="h-4 w-4" />
          </div>
          <div className="mt-3 text-lg font-semibold text-slate-950">
            {latest?.best_pick || "观望"}
          </div>
        </div>
        <div className="card">
          <div className="flex items-center justify-between text-sm text-slate-500">
            价值评分
            <BarChart3 className="h-4 w-4" />
          </div>
          <div className="mt-3 text-lg font-semibold text-slate-950">
            {latest?.value_score ?? selected?.value_score ?? "-"}
          </div>
        </div>
        <div className="card">
          <div className="flex items-center justify-between text-sm text-slate-500">
            风险
            <Shield className="h-4 w-4" />
          </div>
          <div className="mt-3">
            <span className={`status-pill ${riskClass(latest?.risk || selected?.risk)}`}>
              {latest?.risk || selected?.risk || "-"}
            </span>
          </div>
        </div>
        <div className="card">
          <div className="flex items-center justify-between text-sm text-slate-500">
            复盘
            <Clock className="h-4 w-4" />
          </div>
          <div className="mt-3 text-lg font-semibold text-slate-950">
            {latest?.settled_status || "pending"}
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <section className="panel overflow-hidden">
            <div className="panel-header">
              <h2 className="text-base font-semibold">价值候选</h2>
              <span className="text-xs text-slate-500">{detail.value_candidates.length} 条</span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
                  <tr>
                    <th className="px-5 py-3">方向</th>
                    <th className="px-5 py-3">赔率</th>
                    <th className="px-5 py-3">概率/市场</th>
                    <th className="px-5 py-3">EV</th>
                    <th className="px-5 py-3">Kelly</th>
                    <th className="px-5 py-3">评分</th>
                    <th className="px-5 py-3">状态</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {detail.value_candidates.map((item, index) => (
                    <tr key={`${item.market}-${item.pick}-${index}`} className="hover:bg-slate-50">
                      <td className="px-5 py-4">
                        <div className="font-medium text-slate-950">{item.pick || "-"}</div>
                        <div className="mt-1 text-xs text-slate-500">{item.market}</div>
                      </td>
                      <td className="px-5 py-4">{num(item.odds)}</td>
                      <td className="px-5 py-4">
                        {pct(item.prob)} / {pct(item.market_prob)}
                      </td>
                      <td className="px-5 py-4 text-emerald-700">{pct(item.ev)}</td>
                      <td className="px-5 py-4">{num(item.kelly, 3)}</td>
                      <td className="px-5 py-4">{item.value_score ?? 0}</td>
                      <td className="px-5 py-4">
                        <span className={`status-pill ${riskClass(item.risk)}`}>
                          {item.selected ? "入选" : item.risk || "-"}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {!detail.value_candidates.length && (
                    <tr>
                      <td className="px-5 py-8 text-slate-500" colSpan={7}>
                        暂无价值候选。
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {detail.predictions.filter(p => p.report_text).length > 0 && (
            <section className="panel">
              <div className="panel-header">
                <h2 className="text-base font-semibold">引擎报告</h2>
                <span className="text-xs text-slate-500">{detail.predictions.filter(p => p.report_text).length} 条</span>
              </div>
              <div className="divide-y divide-slate-100">
                {detail.predictions.map((pred, idx) => (
                  <div key={idx} className="px-5 py-4">
                    <div className="mb-1 text-xs text-slate-500">
                      {formatDate(pred.created_at)} · {pred.best_pick || "-"}
                    </div>
                    {pred.report_text && (
                      <details className="mt-3">
                        <summary className="cursor-pointer text-sm font-medium text-primary-700 hover:text-primary-900">📊 查看完整分析报告</summary>
                        <pre className="mt-2 max-h-[500px] overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-4 text-xs leading-relaxed text-slate-700">
                          {pred.report_text.slice(0, 10000)}
                        </pre>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        <section className="panel overflow-hidden">
          <div className="panel-header">
            <h2 className="text-base font-semibold">赔率快照</h2>
            <span className="text-xs text-slate-500">{detail.odds_snapshots.length} 条</span>
          </div>
          <div className="max-h-[760px] overflow-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="sticky top-0 bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
                <tr>
                  <th className="px-5 py-3">公司</th>
                  <th className="px-5 py-3">市场</th>
                  <th className="px-5 py-3">赔率</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {detail.odds_snapshots.map((item, index) => (
                  <tr key={`${item.bookmaker}-${item.market}-${index}`} className="hover:bg-slate-50">
                    <td className="px-5 py-4">
                      <div className="font-medium text-slate-950">{item.bookmaker || "-"}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        {item.snapshot_type || "latest"} · {formatDate(item.captured_at)}
                      </div>
                    </td>
                    <td className="px-5 py-4">{item.market}</td>
                    <td className="px-5 py-4">{oddsText(item)}</td>
                  </tr>
                ))}
                {!detail.odds_snapshots.length && (
                  <tr>
                    <td className="px-5 py-8 text-slate-500" colSpan={3}>
                      暂无赔率快照。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}
