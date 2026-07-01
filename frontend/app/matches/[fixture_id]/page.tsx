import Link from "next/link";
import { ArrowLeft } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://backend:8000";

type MatchDetail = {
  fixture_id: number;
  home_team: string;
  away_team: string;
  league: string;
  kickoff: string;
  status: string;
  predictions: Array<{
    best_pick: string | null;
    value_score: number | null;
    risk: string | null;
    created_at: string | null;
    report_text: string | null;
  }>;
  value_candidates: Array<{
    market: string;
    pick: string;
    ev: number | null;
    kelly: number | null;
    edge: number | null;
    value_score: number | null;
    selected: boolean | null;
  }>;
  odds_snapshots: Array<{
    market: string;
    bookmaker: string | null;
    home_odds: number | null;
    draw_odds: number | null;
    away_odds: number | null;
    ah_line: number | null;
    ou_line: number | null;
    captured_at: string | null;
  }>;
};

async function getDetail(fixtureId: string): Promise<MatchDetail | null> {
  try {
    const response = await fetch(`${API_BASE}/v1/matches/${fixtureId}`, { cache: "no-store" });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

function fmt(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

export default async function MatchDetailPage({
  params,
}: {
  params: { fixture_id: string };
}) {
  const detail = await getDetail(params.fixture_id);

  if (!detail) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 text-sm text-slate-600">
          <ArrowLeft className="h-4 w-4" />
          返回
        </Link>
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">
          未找到比赛记录。
        </div>
      </main>
    );
  }

  const latest = detail.predictions[0];

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <Link href="/" className="mb-6 inline-flex items-center gap-2 text-sm text-slate-600">
        <ArrowLeft className="h-4 w-4" />
        返回控制台
      </Link>

      <section className="border-b border-slate-200 pb-6">
        <h1 className="text-2xl font-semibold">
          {detail.home_team} vs {detail.away_team}
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          {detail.league} · {detail.kickoff?.slice(0, 16).replace("T", " ")} · {detail.status}
        </p>
      </section>

      {latest?.report_text && (
        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="mb-3 text-base font-semibold">Telegram 输出</h2>
          <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-800">{latest.report_text}</pre>
        </section>
      )}

      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-5 py-4 text-base font-semibold">价值候选</div>
          <div className="divide-y divide-slate-100">
            {detail.value_candidates.length ? (
              detail.value_candidates.map((item, index) => (
                <div key={`${item.market}-${index}`} className="px-5 py-4 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{item.pick}</span>
                    <span>{item.selected ? "入选" : "未入选"}</span>
                  </div>
                  <div className="mt-2 text-slate-500">
                    EV {fmt(item.ev)} · Kelly {item.kelly?.toFixed(3) || "-"} · Edge {fmt(item.edge)} · 评分{" "}
                    {item.value_score ?? 0}
                  </div>
                </div>
              ))
            ) : (
              <div className="px-5 py-6 text-sm text-slate-500">暂无候选。</div>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-5 py-4 text-base font-semibold">赔率快照</div>
          <div className="max-h-[520px] divide-y divide-slate-100 overflow-auto">
            {detail.odds_snapshots.length ? (
              detail.odds_snapshots.map((item, index) => (
                <div key={`${item.bookmaker}-${index}`} className="px-5 py-4 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{item.bookmaker || "-"}</span>
                    <span className="text-xs text-slate-500">{item.market}</span>
                  </div>
                  <div className="mt-2 text-slate-500">
                    {item.market === "1x2"
                      ? `${item.home_odds ?? "-"} / ${item.draw_odds ?? "-"} / ${item.away_odds ?? "-"}`
                      : item.ah_line !== null
                        ? `AH ${item.ah_line}`
                        : item.ou_line !== null
                          ? `OU ${item.ou_line}`
                          : "-"}
                  </div>
                </div>
              ))
            ) : (
              <div className="px-5 py-6 text-sm text-slate-500">暂无赔率快照。</div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
