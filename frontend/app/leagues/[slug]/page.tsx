import Link from "next/link";

export default function LeagueDetailPage({
  params,
}: {
  params: { slug: string };
}) {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <section className="panel px-5 py-6">
        <h1 className="text-2xl font-semibold text-slate-950">{params.slug}</h1>
        <p className="mt-2 text-sm text-slate-600">
          联赛详情会在后续版本接入赛程、球队画像和联赛维度复盘表现。
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
