import Link from "next/link";

export default function AccountPage() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <section className="panel px-5 py-6">
        <h1 className="text-2xl font-semibold text-slate-950">账户管理</h1>
        <p className="mt-2 text-sm text-slate-600">
          当前部署为自用控制台，密钥和服务配置通过服务器 `.env` 管理。网页账户体系暂不开放。
        </p>
        <Link
          href="/"
          className="mt-5 inline-flex rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          返回控制台
        </Link>
      </section>
    </main>
  );
}
