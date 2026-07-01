import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://backend:8000";

type TodayMatch = {
  fixture_id: number;
  home_team: string;
  away_team: string;
  league: string | null;
  kickoff: string | null;
  analyzed: boolean;
  best_pick: string | null;
  value_score: number | null;
  risk: string | null;
  review_status: string | null;
  score: string | null;
};

async function getToday(): Promise<TodayMatch[]> {
  try {
    const response = await fetch(`${API_BASE}/v1/matches/today`, { cache: "no-store" });
    if (!response.ok) return [];
    return response.json();
  } catch {
    return [];
  }
}

export default async function TodayPage() {
  const matches = await getToday();
  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6 flex items-end justify-between border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-2xl font-semibold">今日比赛</h1>
          <p className="mt-1 text-sm text-slate-500">今日已入库比赛、分析状态和复盘状态</p>
        </div>
        <Link href="/" className="text-sm text-slate-600 hover:text-slate-950">返回控制台</Link>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3">比赛</th>
              <th className="px-5 py-3">开赛时间</th>
              <th className="px-5 py-3">已分析</th>
              <th className="px-5 py-3">最优方向</th>
              <th className="px-5 py-3">评分</th>
              <th className="px-5 py-3">风险</th>
              <th className="px-5 py-3">复盘</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {matches.map((item) => (
              <tr key={item.fixture_id} className="hover:bg-slate-50">
                <td className="px-5 py-4">
                  <Link href={`/matches/${item.fixture_id}`} className="font-medium text-slate-950">
                    {item.home_team} vs {item.away_team}
                  </Link>
                  <div className="text-xs text-slate-500">{item.league || "-"}</div>
                </td>
                <td className="px-5 py-4">{item.kickoff?.slice(0, 16).replace("T", " ") || "-"}</td>
                <td className="px-5 py-4">{item.analyzed ? "是" : "否"}</td>
                <td className="px-5 py-4">{item.best_pick || "观望/未分析"}</td>
                <td className="px-5 py-4">{item.value_score ?? "-"}</td>
                <td className="px-5 py-4">{item.risk || "-"}</td>
                <td className="px-5 py-4">{item.review_status || "pending"}</td>
              </tr>
            ))}
            {!matches.length && (
              <tr>
                <td className="px-5 py-8 text-slate-500" colSpan={7}>暂无今日比赛记录。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
