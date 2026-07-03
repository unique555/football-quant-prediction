"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { AlertCircle, ArrowUpRight, Loader2, Play } from "lucide-react";
import { fetchClientJson } from "@/lib/client-api";

type PredictResult = {
  status: string;
  message: string;
  fixture_id: number | null;
  payload?: {
    match?: {
      fixture_id?: number;
      home_team?: string;
      away_team?: string;
      league?: string;
      kickoff?: string;
    };
    engine?: {
      final_home_prob?: number;
      final_draw_prob?: number;
      final_away_prob?: number;
      recommended_direction?: string | null;
      final_verdict?: string;
      confidence_score?: number;
      warnings?: string[];
      summary?: string;
    };
    value_candidates?: Array<{
      market?: string;
      pick?: string;
      display_pick?: string;
      odds?: number;
      ev?: number;
      kelly?: number;
      edge?: number;
      risk?: string;
      value_score?: number;
    }>;
  };
};

const examples = [
  "Botafogo SP vs CRB",
  "France W vs Sweden W",
  "VPS Vaasa vs Inter Turku",
];

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

export function PredictionForm() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<PredictResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const candidates = useMemo(
    () => result?.payload?.value_candidates?.slice(0, 8) || [],
    [result]
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setResult(null);
    const clean = query.trim();
    if (!clean) {
      setError("请输入比赛名称，例如 Botafogo SP vs CRB。");
      return;
    }
    setLoading(true);
    try {
      const data = await fetchClientJson<PredictResult>("/v1/predict", {
        method: "POST",
        body: JSON.stringify({ query: clean }),
      });
      setResult(data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "预测请求失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <section className="panel">
        <div className="panel-header">
          <h2 className="text-base font-semibold">发起分析</h2>
        </div>
        <form className="space-y-4 px-5 py-5" onSubmit={submit}>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">比赛</span>
            <input
              className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="主队 vs 客队"
            />
          </label>

          <div className="flex flex-wrap gap-2">
            {examples.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setQuery(item)}
                className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              >
                {item}
              </button>
            ))}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-slate-950 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            生成分析
          </button>

          {error ? (
            <div className="flex gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}
        </form>
      </section>

      <section className="panel min-h-[420px]">
        <div className="panel-header">
          <h2 className="text-base font-semibold">分析结果</h2>
          {result?.fixture_id ? (
            <Link
              href={`/matches/${result.fixture_id}`}
              className="inline-flex items-center gap-1 text-sm text-primary-700 hover:text-primary-900"
            >
              比赛详情
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          ) : null}
        </div>

        {!result ? (
          <div className="flex h-[340px] items-center justify-center px-6 text-center text-sm text-slate-500">
            输入比赛后，这里会展示引擎概率、推荐方向、价值候选和原始 Telegram 报告。
          </div>
        ) : (
          <div className="space-y-5 px-5 py-5">
            <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm text-slate-500">{result.payload?.match?.league || "-"}</div>
                  <div className="mt-1 text-lg font-semibold text-slate-950">
                    {result.payload?.match?.home_team || "Home"} vs{" "}
                    {result.payload?.match?.away_team || "Away"}
                  </div>
                </div>
                <span className="status-pill border-slate-200 bg-white text-slate-700">
                  {result.status}
                </span>
              </div>
            </div>

            {result.payload?.engine ? (
              <div className="grid gap-3 md:grid-cols-4">
                <div className="rounded-md border border-slate-200 p-3">
                  <div className="text-xs text-slate-500">主胜</div>
                  <div className="mt-1 text-xl font-semibold">{pct(result.payload.engine.final_home_prob)}</div>
                </div>
                <div className="rounded-md border border-slate-200 p-3">
                  <div className="text-xs text-slate-500">平局</div>
                  <div className="mt-1 text-xl font-semibold">{pct(result.payload.engine.final_draw_prob)}</div>
                </div>
                <div className="rounded-md border border-slate-200 p-3">
                  <div className="text-xs text-slate-500">客胜</div>
                  <div className="mt-1 text-xl font-semibold">{pct(result.payload.engine.final_away_prob)}</div>
                </div>
                <div className="rounded-md border border-slate-200 p-3">
                  <div className="text-xs text-slate-500">信心</div>
                  <div className="mt-1 text-xl font-semibold">{pct(result.payload.engine.confidence_score)}</div>
                </div>
              </div>
            ) : null}

            {candidates.length ? (
              <div className="overflow-hidden rounded-md border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
                    <tr>
                      <th className="px-4 py-3">方向</th>
                      <th className="px-4 py-3">赔率</th>
                      <th className="px-4 py-3">EV</th>
                      <th className="px-4 py-3">Kelly</th>
                      <th className="px-4 py-3">风险</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {candidates.map((item, index) => (
                      <tr key={`${item.market}-${item.pick}-${index}`}>
                        <td className="px-4 py-3">{item.display_pick || item.pick || "-"}</td>
                        <td className="px-4 py-3">{num(item.odds)}</td>
                        <td className="px-4 py-3 text-emerald-700">{pct(item.ev)}</td>
                        <td className="px-4 py-3">{num(item.kelly, 3)}</td>
                        <td className="px-4 py-3">
                          <span className={`status-pill ${riskClass(item.risk)}`}>
                            {item.risk || "中"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-800">
              {result.message}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}
