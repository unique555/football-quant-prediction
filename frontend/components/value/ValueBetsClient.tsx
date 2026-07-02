"use client";

import { useEffect, useState } from "react";
import { RefreshCw, TrendingUp, AlertCircle } from "lucide-react";
import { getValueToday } from "@/lib/api-client";

interface ValueBet {
  id: number;
  fixture_id: number;
  home_team: string | null;
  away_team: string | null;
  league: string | null;
  kickoff: string | null;
  best_pick: string | null;
  best_odds: number | null;
  best_ev: number | null;
  best_edge: number | null;
  best_kelly: number | null;
  risk: string | null;
  value_score: number | null;
  settled_status: string | null;
}

export function ValueBetsClient() {
  const [bets, setBets] = useState<ValueBet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getValueToday(30);
      setBets(data as ValueBet[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500">
        <RefreshCw className="mr-2 h-5 w-5 animate-spin" />
        加载中...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-500">
        <AlertCircle className="mb-2 h-8 w-8 text-red-400" />
        <p className="text-sm">{error}</p>
        <button
          onClick={load}
          className="mt-4 rounded-md bg-slate-950 px-4 py-2 text-sm text-white hover:bg-slate-800"
        >
          重试
        </button>
      </div>
    );
  }

  if (bets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400">
        <TrendingUp className="mb-2 h-12 w-12" />
        <p className="text-sm">暂无价值投注</p>
        <p className="mt-1 text-xs text-slate-400">
          系统会在每 3 小时自动分析并筛选 edge &gt; 3% 的比赛
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">
          共 <span className="font-semibold text-slate-950">{bets.length}</span> 场价值投注
        </p>
        <button
          onClick={load}
          className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          刷新
        </button>
      </div>

      <div className="grid gap-3">
        {bets.map((bet, idx) => (
          <ValueBetCard key={bet.id || idx} bet={bet} />
        ))}
      </div>
    </div>
  );
}

function ValueBetCard({ bet }: { bet: ValueBet }) {
  const edge = bet.best_edge ?? 0;
  const ev = bet.best_ev ?? 0;
  const kelly = bet.best_kelly ?? 0;
  const riskColor =
    bet.risk === "低"
      ? "bg-green-50 text-green-700"
      : bet.risk === "高"
        ? "bg-red-50 text-red-700"
        : "bg-amber-50 text-amber-700";

  const kickoffStr = bet.kickoff
    ? new Date(bet.kickoff).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "?";

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium">{bet.league || "?"}</span>
            <span>{kickoffStr}</span>
          </div>
          <h3 className="mt-1 text-base font-semibold text-slate-950">
            {bet.home_team || "?"} <span className="text-slate-400">vs</span> {bet.away_team || "?"}
          </h3>
          <p className="mt-0.5 text-sm text-slate-600">
            推荐：<span className="font-medium text-slate-900">{bet.best_pick || "?"}</span>
            <span className="ml-2 text-slate-400">@ {bet.best_odds ?? "?"}</span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${riskColor}`}>
            {bet.risk || "?"}风险
          </span>
          <span className="text-xs text-slate-400">#{bet.fixture_id}</span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2 border-t border-slate-100 pt-3">
        <Metric label="Edge" value={`${(edge * 100).toFixed(1)}%`} positive={edge > 0} />
        <Metric label="EV" value={`${(ev * 100).toFixed(1)}%`} positive={ev > 0} />
        <Metric label="Kelly" value={`${(kelly * 100).toFixed(1)}%`} positive={kelly > 0} />
        <Metric label="价值分" value={`${bet.value_score ?? 0}/100`} positive={(bet.value_score ?? 0) >= 60} />
      </div>
    </div>
  );
}

function Metric({ label, value, positive }: { label: string; value: string; positive: boolean }) {
  return (
    <div className="text-center">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`text-sm font-semibold ${positive ? "text-green-600" : "text-slate-700"}`}>
        {value}
      </p>
    </div>
  );
}
