import Link from "next/link";
import { BarChart3, TrendingUp, Zap } from "lucide-react";

export default function HomePage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-16">
      {/* Hero */}
      <section className="text-center mb-16">
        <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
          足球量化预测
        </h1>
        <p className="mt-4 text-lg text-slate-600 max-w-2xl mx-auto">
          基于泊松模型、蒙特卡洛模拟与 Stacking 集成学习的
          <br />
          概率化足球比赛预测引擎
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <Link
            href="/predict"
            className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-6 py-3 text-white font-medium hover:bg-primary-700 transition-colors"
          >
            <Zap className="h-5 w-5" />
            立即预测
          </Link>
          <Link
            href="/backtest"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-6 py-3 font-medium text-slate-700 hover:bg-slate-50 transition-colors"
          >
            <BarChart3 className="h-5 w-5" />
            查看回测
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="grid gap-8 md:grid-cols-3">
        {features.map(({ icon: Icon, title, desc }) => (
          <div key={title} className="card text-center">
            <Icon className="mx-auto h-10 w-10 text-primary-600" />
            <h3 className="mt-4 text-lg font-semibold">{title}</h3>
            <p className="mt-2 text-sm text-slate-600">{desc}</p>
          </div>
        ))}
      </section>

      {/* Today's Picks — 待实现 */}
      <section className="mt-16">
        <h2 className="text-2xl font-bold mb-6">今日高置信度推荐</h2>
        <p className="text-slate-500">— 数据同步后将自动展示 —</p>
      </section>
    </div>
  );
}

const features = [
  {
    icon: BarChart3,
    title: "双轨预测引擎",
    desc: "泊松统计模型 + Stacking ML 模型，Bayesian 融合",
  },
  {
    icon: TrendingUp,
    title: "13 个预测市场",
    desc: "胜负平、大小球、双方进球、半场、零封全覆盖",
  },
  {
    icon: Zap,
    title: "蒙特卡洛模拟",
    desc: "10,000 次模拟 + 环境因子修正，量化不确定性",
  },
];
