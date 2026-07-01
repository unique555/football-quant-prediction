import {
  Activity,
  Bot,
  Database,
  FlaskConical,
  KeyRound,
  type LucideIcon,
  Server,
} from "lucide-react";
import { fetchServerJson } from "@/lib/server-api";
import type { HealthStatus, SystemStatus } from "@/lib/types";

const emptyStatus: SystemStatus = {
  status: "offline",
  environment: "-",
  database: "missing",
  api_football: "missing",
  telegram_bot: "missing",
  mlflow: "missing",
};

function statusClass(value: string) {
  if (["online", "ok", "configured"].includes(value)) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function StatusItem({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
}) {
  return (
    <div className="card">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm text-slate-500">{label}</div>
          <div className="mt-2 text-lg font-semibold text-slate-950">{value}</div>
        </div>
        <Icon className="h-5 w-5 text-slate-400" />
      </div>
      <span className={`status-pill mt-4 ${statusClass(value)}`}>{value}</span>
    </div>
  );
}

export default async function SystemPage() {
  const [health, status] = await Promise.all([
    fetchServerJson<HealthStatus>("/health", { status: "offline", version: "-" }),
    fetchServerJson<SystemStatus>("/v1/system/status", emptyStatus),
  ]);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-6 border-b border-slate-200 pb-5">
        <h1 className="text-2xl font-semibold text-slate-950">系统</h1>
        <p className="mt-1 text-sm text-slate-600">
          后端健康、运行环境、外部 API、Telegram 和 MLflow 配置状态
        </p>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <StatusItem label="FastAPI" value={health.status} icon={Server} />
        <StatusItem label="运行环境" value={status.environment} icon={Activity} />
        <StatusItem label="PostgreSQL" value={status.database} icon={Database} />
        <StatusItem label="API-Football" value={status.api_football} icon={KeyRound} />
        <StatusItem label="Telegram Bot" value={status.telegram_bot} icon={Bot} />
        <StatusItem label="MLflow" value={status.mlflow} icon={FlaskConical} />
      </section>

      <section className="panel mt-6">
        <div className="panel-header">
          <h2 className="text-base font-semibold">运行信息</h2>
        </div>
        <div className="grid gap-4 px-5 py-5 text-sm md:grid-cols-3">
          <div>
            <div className="text-slate-500">后端版本</div>
            <div className="mt-1 font-medium text-slate-950">{health.version}</div>
          </div>
          <div>
            <div className="text-slate-500">公开入口</div>
            <div className="mt-1 font-medium text-slate-950">Nginx / Docker Compose</div>
          </div>
          <div>
            <div className="text-slate-500">部署模式</div>
            <div className="mt-1 font-medium text-slate-950">Full profile</div>
          </div>
        </div>
      </section>
    </main>
  );
}
