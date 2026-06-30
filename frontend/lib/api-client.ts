/**
 * API 客户端 — 后端通信层
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API Error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// --- 预测 ---
export const predictMatch = (home: string, away: string) =>
  fetchAPI("/v1/predict", {
    method: "POST",
    body: JSON.stringify({ home_team: home, away_team: away }),
  });

// --- 联赛 ---
export const getLeagues = () =>
  fetchAPI("/v1/leagues");

// --- 比赛 ---
export const getMatches = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return fetchAPI(`/v1/matches${qs}`);
};

// --- 赔率 ---
export const getOdds = (matchId: string) =>
  fetchAPI(`/v1/odds/${matchId}`);

// --- 回测 ---
export const runBacktest = (config: Record<string, unknown>) =>
  fetchAPI("/v1/backtest/run", {
    method: "POST",
    body: JSON.stringify(config),
  });

// --- 模型 ---
export const getModels = () =>
  fetchAPI("/v1/models");
