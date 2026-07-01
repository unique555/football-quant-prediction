import { PredictionForm } from "@/components/predict/PredictionForm";

export default function PredictPage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 border-b border-slate-200 pb-5">
        <h1 className="text-2xl font-semibold text-slate-950">单场预测</h1>
        <p className="mt-1 text-sm text-slate-600">
          输入比赛后调用统一预测管线，返回引擎判断、价值候选和可追踪 fixture
        </p>
      </div>
      <PredictionForm />
    </main>
  );
}
