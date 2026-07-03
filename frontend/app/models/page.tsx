import Link from "next/link";

export default function ModelsPage() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <section className="panel px-5 py-6">
        <h1 className="text-2xl font-semibold text-slate-950">模型中心</h1>
        <p className="mt-2 text-sm text-slate-600">
          模型训练和 MLflow 已纳入全功能部署，网页端先展示预测输出、价值候选和复盘表现。
          模型版本详情后续会从 MLflow 与训练任务中同步到这里。
        </p>
        <Link
          href="/system"
          className="mt-5 inline-flex rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          查看系统状态
        </Link>
      </section>
    </main>
  );
}
