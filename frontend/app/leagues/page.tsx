import Link from "next/link";

export default function LeaguesPage() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <section className="panel px-5 py-6">
        <h1 className="text-2xl font-semibold text-slate-950">联赛中心</h1>
        <p className="mt-2 text-sm text-slate-600">
          当前核心入口是今日比赛和单场预测。联赛聚合页后续会接入赛程、球队画像和盘口表现分布。
        </p>
        <Link
          href="/today"
          className="mt-5 inline-flex rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          查看今日比赛
        </Link>
      </section>
    </main>
  );
}
