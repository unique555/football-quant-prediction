"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  ClipboardList,
  Loader2,
  RefreshCw,
  Search,
  Send,
  Shield,
  Star,
} from "lucide-react";
import {
  getMatchDetail,
  getMatches,
  getPerformance,
  getStats,
  getSystemStatus,
  predictMatch,
} from "@/lib/api-client";
import type {
  AnalysisReport,
  MatchDetail,
  MatchListItem,
  MarketCard,
  PerformanceSummary,
  StatsSummary,
  SystemStatus,
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

function formatDate(value?: string | null) {
  if (!value) return "-";
  return value.slice(0, 16).replace("T", " ");
}

function displayHome(item?: MatchListItem | MatchDetail | null) {
  return item?.home_team_zh || item?.home_team || "主队";
}

function displayAway(item?: MatchListItem | MatchDetail | null) {
  return item?.away_team_zh || item?.away_team || "客队";
}

function englishLine(item?: MatchListItem | MatchDetail | null) {
  const home = item?.home_team || "";
  const away = item?.away_team || "";
  if (!home && !away) return "";
  return `${home} vs ${away}`;
}

function riskClass(risk?: string | null) {
  if (risk === "低") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (risk === "高") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function outcomeColor(tone?: string) {
  if (tone === "positive") return "bg-emerald-500";
  if (tone === "warning") return "bg-amber-500";
  if (tone === "negative") return "bg-rose-500";
  return "bg-blue-500";
}

function actionClass(action?: string) {
  if (action === "推送") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (action === "人工复核") return "border-amber-200 bg-amber-50 text-amber-700";
  if (action === "待采集") return "border-slate-200 bg-slate-50 text-slate-500";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function MarketCardView({ card }: { card: MarketCard }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-950">{card.title}</h3>
          <p className="mt-0.5 text-xs text-slate-500">{card.subtitle}</p>
        </div>
        <span className={`status-pill ${actionClass(card.action)}`}>{card.action}</span>
      </div>
      <div className="space-y-3 p-4">
        {card.outcomes.map((item) => {
          const width = item.probability ? Math.max(3, Math.min(100, item.probability * 100)) : 3;
          return (
            <div key={item.label} className="grid grid-cols-[5.5rem_1fr_3.75rem] items-center gap-3 text-sm">
              <span className="text-slate-700">{item.label}</span>
              <div className="h-2.5 overflow-hidden rounded-full bg-slate-200">
                <div className={`h-full rounded-full ${outcomeColor(item.tone)}`} style={{ width: `${width}%` }} />
              </div>
              <span className="text-right font-semibold text-slate-950">{pct(item.probability)}</span>
            </div>
          );
        })}
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {card.metrics.map((metric) => (
            <div key={`${card.market}-${metric.label}`} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
              <div className="text-[11px] text-slate-500">{metric.label}</div>
              <div className="mt-1 truncate text-sm font-semibold text-slate-950">{metric.value}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ReportModal({
  report,
  onClose,
}: {
  report: AnalysisReport;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[80] bg-slate-950/40 p-4 backdrop-blur-sm">
      <div className="mx-auto flex max-h-[92vh] max-w-6xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">{report.title}</h2>
            <p className="mt-1 text-xs text-slate-500">结构化报告模板</p>
          </div>
          <button className="rounded-md border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="grid min-h-0 gap-4 overflow-auto p-5 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="space-y-3">
            {report.sections.map((section) => (
              <section key={section.title} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <h3 className="text-sm font-semibold text-slate-950">{section.title}</h3>
                <ul className="mt-2 space-y-1.5 text-sm leading-6 text-slate-700">
                  {section.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          <pre className="min-h-[28rem] overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-4 text-sm leading-6 text-blue-50">
            {report.raw_report || "暂无原始引擎报告。运行分析后会在这里展示完整输出。"}
          </pre>
        </div>
      </div>
    </div>
  );
}

export function AnalysisWorkbenchClient() {
  const [matches, setMatches] = useState<MatchListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<MatchDetail | null>(null);
  const [stats, setStats] = useState<StatsSummary>(emptyStats);
  const [performance, setPerformance] = useState<PerformanceSummary>(emptyPerformance);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"48h" | "today" | "value" | "watch">("48h");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);

  const loadInitial = async () => {
    setLoading(true);
    setError(null);
    try {
      const [matchRows, statsData, perfData, systemData] = await Promise.all([
        getMatches({ limit: "80" }) as Promise<MatchListItem[]>,
        getStats() as Promise<StatsSummary>,
        getPerformance() as Promise<PerformanceSummary>,
        getSystemStatus() as Promise<SystemStatus>,
      ]);
      setMatches(matchRows);
      setStats(statsData);
      setPerformance(perfData);
      setSystem(systemData);
      if (matchRows[0]?.fixture_id) {
        setSelectedId(matchRows[0].fixture_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (fixtureId: number) => {
    setDetailLoading(true);
    setError(null);
    try {
      const data = (await getMatchDetail(String(fixtureId))) as MatchDetail;
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "比赛详情加载失败");
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    loadInitial();
  }, []);

  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
    }
  }, [selectedId]);

  const filteredMatches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return matches.filter((item) => {
      const text = [
        item.home_team,
        item.away_team,
        item.home_team_zh,
        item.away_team_zh,
        item.league,
        item.fixture_id,
      ]
        .join(" ")
        .toLowerCase();
      if (q && !text.includes(q)) return false;
      if (tab === "today") return item.kickoff?.slice(0, 10) === new Date().toISOString().slice(0, 10);
      if (tab === "value") return true;
      if (tab === "watch") return item.status === "scheduled";
      return true;
    });
  }, [matches, query, tab]);

  const latestPrediction = detail?.predictions?.[0];
  const selectedCandidate =
    detail?.value_candidates?.find((item) => item.selected) || detail?.value_candidates?.[0];
  const marketCards = detail?.market_cards || [];
  const score =
    detail?.result && detail.result.home_goals !== null
      ? `${detail.result.home_goals}:${detail.result.away_goals}`
      : "-";

  const handleRunAnalysis = async () => {
    if (!detail?.home_team || !detail.away_team) return;
    setRunning(true);
    setError(null);
    try {
      await predictMatch(detail.home_team, detail.away_team);
      await loadDetail(detail.fixture_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行分析失败");
    } finally {
      setRunning(false);
    }
  };

  return (
    <main className="mx-auto max-w-[1520px] px-4 py-5">
      <section className="mb-4 flex flex-col gap-3 border-b border-slate-200 pb-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">专业分析工作台</h1>
          <p className="mt-1 text-sm text-slate-600">
            中文队名、四大市场、手动选赛、结构化报告和 Telegram 输出集中在一个工作台。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="status-pill border-emerald-200 bg-emerald-50 text-emerald-700">
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            API {system?.status || "unknown"}
          </span>
          <button onClick={loadInitial} className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm hover:bg-slate-50">
            <RefreshCw className="h-4 w-4" />
            刷新
          </button>
        </div>
      </section>

      {error ? (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      <section className="grid overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm xl:grid-cols-[320px_minmax(0,1fr)_340px]">
        <aside className="border-b border-slate-200 bg-slate-50 p-4 xl:border-b-0 xl:border-r">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-9 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-blue-400"
              placeholder="搜索中文队名 / 英文名 / fixture_id"
            />
          </div>
          <div className="mt-3 grid grid-cols-4 gap-1">
            {[
              ["48h", "48h"],
              ["today", "今日"],
              ["value", "价值"],
              ["watch", "关注"],
            ].map(([value, label]) => (
              <button
                key={value}
                onClick={() => setTab(value as typeof tab)}
                className={`rounded-md px-2 py-2 text-xs font-medium ${
                  tab === value ? "bg-slate-950 text-white" : "border border-slate-200 bg-white text-slate-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
            <div className="rounded-md border border-slate-200 bg-white px-2 py-2">联赛：全部</div>
            <div className="rounded-md border border-slate-200 bg-white px-2 py-2">状态：可分析</div>
            <div className="rounded-md border border-slate-200 bg-white px-2 py-2">赔率：≥3家</div>
            <div className="rounded-md border border-slate-200 bg-white px-2 py-2">排序：时间</div>
          </div>

          <div className="mt-3 max-h-[720px] space-y-2 overflow-auto pr-1">
            {loading ? (
              <div className="flex items-center gap-2 px-2 py-6 text-sm text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                加载比赛中...
              </div>
            ) : null}
            {filteredMatches.map((item) => (
              <button
                key={item.fixture_id}
                onClick={() => setSelectedId(item.fixture_id)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  selectedId === item.fixture_id
                    ? "border-blue-500 bg-blue-50 shadow-sm"
                    : "border-slate-200 bg-white hover:border-blue-200"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-slate-950">
                      {displayHome(item)} vs {displayAway(item)}
                    </div>
                    <div className="mt-0.5 truncate text-[11px] text-slate-500">{englishLine(item)}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {item.league || "-"} · {formatDate(item.kickoff)}
                    </div>
                  </div>
                  <span className="status-pill border-blue-200 bg-blue-50 text-blue-700">#{item.fixture_id}</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
                  <div className="h-full rounded-full bg-blue-600" style={{ width: item.score ? "88%" : "54%" }} />
                </div>
              </button>
            ))}
            {!loading && !filteredMatches.length ? (
              <div className="rounded-lg border border-dashed border-slate-300 px-3 py-8 text-sm text-slate-500">
                没有匹配的比赛。
              </div>
            ) : null}
          </div>
        </aside>

        <section className="min-w-0 bg-white p-4">
          {detailLoading ? (
            <div className="flex min-h-[480px] items-center justify-center text-sm text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              加载分析详情...
            </div>
          ) : detail ? (
            <>
              <div className="mb-4 flex flex-col gap-3 border-b border-slate-200 pb-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <h2 className="truncate text-2xl font-semibold text-slate-950">
                    {displayHome(detail)} vs {displayAway(detail)}
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {englishLine(detail)} · {detail.league || "-"} · {formatDate(detail.kickoff)} · fixture #{detail.fixture_id}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={handleRunAnalysis}
                    disabled={running}
                    className="inline-flex items-center gap-1.5 rounded-md bg-slate-950 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  >
                    {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />}
                    运行分析
                  </button>
                  <button
                    onClick={() => setReportOpen(true)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-semibold hover:bg-slate-50"
                  >
                    <ClipboardList className="h-4 w-4" />
                    查看分析报告
                  </button>
                </div>
              </div>

              <div className="mb-4 grid gap-3 md:grid-cols-5">
                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="text-xs text-slate-500">首选方向</div>
                  <div className="mt-2 text-lg font-semibold text-slate-950">{latestPrediction?.best_pick || "观望"}</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="text-xs text-slate-500">价值分</div>
                  <div className="mt-2 text-lg font-semibold text-slate-950">{latestPrediction?.value_score ?? selectedCandidate?.value_score ?? 0}</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="text-xs text-slate-500">最高 Edge</div>
                  <div className="mt-2 text-lg font-semibold text-emerald-700">{pct(latestPrediction?.best_edge ?? selectedCandidate?.edge)}</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="text-xs text-slate-500">最高 EV</div>
                  <div className="mt-2 text-lg font-semibold text-emerald-700">{pct(latestPrediction?.best_ev ?? selectedCandidate?.ev)}</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="text-xs text-slate-500">Kelly</div>
                  <div className="mt-2 text-lg font-semibold text-slate-950">{pct(latestPrediction?.best_kelly ?? selectedCandidate?.kelly)}</div>
                </div>
              </div>

              <div className="grid gap-3 2xl:grid-cols-2">
                {marketCards.map((card) => (
                  <MarketCardView key={card.market} card={card} />
                ))}
              </div>

              <section className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                <h3 className="text-sm font-semibold text-emerald-950">核心结论</h3>
                <p className="mt-1 text-sm leading-6 text-emerald-800">
                  胜平负作为首选输出；亚盘、大小球、角球统一展示给用户。数据不足或风险偏高的市场进入观察或人工复核，不默认推送。
                </p>
              </section>

              <section className="mt-4 grid gap-3 xl:grid-cols-[0.9fr_1.1fr]">
                <div className="rounded-lg border border-slate-200 bg-white">
                  <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                    <h3 className="text-sm font-semibold text-slate-950">11 维分析模块</h3>
                    <span className="status-pill border-blue-200 bg-blue-50 text-blue-700">已完成</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 p-4 text-sm">
                    {["基本面", "战术", "战意", "盘口", "进球", "角球", "半全场", "风险"].map((item) => (
                      <div key={item} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                        <div className="font-semibold text-slate-950">{item}</div>
                        <div className="mt-1 text-xs text-slate-500">已纳入综合判断</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white">
                  <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                    <h3 className="text-sm font-semibold text-slate-950">市场排序</h3>
                    <span className="text-xs text-slate-500">价值优先</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <tbody className="divide-y divide-slate-100">
                        {marketCards.map((card) => (
                          <tr key={`rank-${card.market}`} className="hover:bg-slate-50">
                            <td className="px-4 py-3 font-medium text-slate-950">{card.title}</td>
                            <td className="px-4 py-3 text-slate-600">{card.subtitle}</td>
                            <td className="px-4 py-3">
                              <span className={`status-pill ${actionClass(card.action)}`}>{card.action}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </section>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                    <RefreshCw className="h-4 w-4 text-slate-400" />
                    自动闭环
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">fixtures 6h · odds 5min · analyze 3h · settle 30min</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                    <BarChart3 className="h-4 w-4 text-slate-400" />
                    模型状态
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">Stacking latest · trust_weight 0.3 · MLflow 可选</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                    <Star className="h-4 w-4 text-slate-400" />
                    复盘摘要
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    {performance.overall.count} 条样本 · 命中 {pct(performance.overall.hit_rate)} · 收益 {num(performance.overall.profit_units)}u
                  </p>
                </div>
              </div>
            </>
          ) : (
            <div className="flex min-h-[520px] flex-col items-center justify-center text-center text-slate-500">
              <AlertTriangle className="mb-3 h-8 w-8 text-slate-400" />
              <p className="text-sm">请选择一场比赛。</p>
            </div>
          )}
        </section>

        <aside className="border-t border-slate-200 bg-slate-50 p-4 xl:border-l xl:border-t-0">
          <section className="rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h3 className="text-sm font-semibold text-slate-950">赔率盘口</h3>
              <span className="status-pill border-emerald-200 bg-emerald-50 text-emerald-700">
                {detail?.odds_snapshots?.length || 0} 条
              </span>
            </div>
            <div className="max-h-[270px] overflow-auto p-3">
              <table className="min-w-full text-sm">
                <tbody className="divide-y divide-slate-100">
                  {(detail?.odds_snapshots || []).slice(0, 12).map((item, index) => (
                    <tr key={`${item.bookmaker}-${item.market}-${index}`}>
                      <td className="py-2 pr-2 font-medium text-slate-950">{item.bookmaker || "-"}</td>
                      <td className="py-2 pr-2 text-slate-500">{item.market}</td>
                      <td className="py-2 text-right text-slate-700">
                        {item.market === "1x2"
                          ? `${num(item.home_odds)} / ${num(item.draw_odds)} / ${num(item.away_odds)}`
                          : item.market === "asian_handicap"
                            ? `${item.ah_line ?? "-"} · ${num(item.ah_home_odds)} / ${num(item.ah_away_odds)}`
                            : `${item.ou_line ?? "-"} · ${num(item.over_odds)} / ${num(item.under_odds)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!detail?.odds_snapshots?.length ? (
                <div className="px-2 py-8 text-sm text-slate-500">暂无赔率快照。</div>
              ) : null}
            </div>
          </section>

          <section className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-amber-950">
              <Shield className="h-4 w-4" />
              风控提示
            </div>
            <p className="mt-2 text-sm leading-6 text-amber-800">
              风险等级：
              <span className={`status-pill ml-1 ${riskClass(latestPrediction?.risk || selectedCandidate?.risk)}`}>
                {latestPrediction?.risk || selectedCandidate?.risk || "中"}
              </span>
              。亚盘、大小球、角球默认展示，不自动推送高风险方向。
            </p>
          </section>

          <section className="mt-3 rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h3 className="text-sm font-semibold text-slate-950">操作台</h3>
              <span className="status-pill border-amber-200 bg-amber-50 text-amber-700">
                {latestPrediction?.settled_status || "pending"}
              </span>
            </div>
            <div className="space-y-2 p-4">
              <button className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-slate-950 px-3 py-2 text-sm font-semibold text-white">
                <Send className="h-4 w-4" />
                推送 Telegram
              </button>
              <button className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-semibold hover:bg-slate-50">
                加入关注列表
              </button>
              <button className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-semibold hover:bg-slate-50">
                标记人工复核
              </button>
            </div>
          </section>

          <div className="mt-3 rounded-lg bg-slate-950 p-4 font-mono text-xs leading-5 text-blue-50">
            auto_analyze.run
            <br />
            fixture: {detail?.fixture_id || "-"}
            <br />
            markets: 1x2 / AH / OU / Corners
            <br />
            report saved: {latestPrediction?.report_text ? "yes" : "no"}
            <br />
            telegram: not sent
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-xs text-slate-500">总分析</div>
              <div className="mt-1 text-lg font-semibold">{stats.total_predictions}</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-xs text-slate-500">价值方向</div>
              <div className="mt-1 text-lg font-semibold">{stats.value_predictions}</div>
            </div>
          </div>
        </aside>
      </section>

      {reportOpen && detail?.analysis_report ? (
        <ReportModal report={detail.analysis_report} onClose={() => setReportOpen(false)} />
      ) : null}
    </main>
  );
}
