import Link from "next/link";

export default function BacktestPage() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <section className="panel px-5 py-6">
        <h1 className="text-2xl font-semibold text-slate-950">回测系统</h1>
        <p className="mt-2 text-sm text-slate-600">
          当前版本优先开放预测控制台和复盘统计。历史回测能力保留在后端任务与脚本中，
          后续会接入可视化配置和报告页面。
        </p>
        <Link
          href="/stats"
          className="mt-5 inline-flex rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          查看复盘统计
        </Link>
      </section>
    </main>
  );
}
