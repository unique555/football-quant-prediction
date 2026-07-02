import { fetchClientJson } from "./client-api";

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  return fetchClientJson<T>(endpoint, options);
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

export const getTodayMatches = () =>
  fetchAPI("/v1/matches/today");

export const getMatchDetail = (matchId: string) =>
  fetchAPI(`/v1/matches/${matchId}`);

// --- 赔率 ---
export const getOdds = (matchId: string) =>
  fetchAPI(`/v1/odds/${matchId}`);

// --- 价值投注 ---
export const getValueToday = (limit = 20) =>
  fetchAPI(`/v1/value/today?limit=${limit}`);

// --- 回测 ---
export const runBacktest = (config: Record<string, unknown>) =>
  fetchAPI("/v1/backtest/run", {
    method: "POST",
    body: JSON.stringify(config),
  });

// --- 模型 ---
export const getModels = () =>
  fetchAPI("/v1/models");

// --- 系统 ---
export const getSystemStatus = () =>
  fetchAPI("/v1/system/status");

export const getStats = () =>
  fetchAPI("/v1/stats");

export const getPerformance = () =>
  fetchAPI("/v1/stats/performance");

// --- 预测记录 ---
export const getRecentPredictions = (limit = 20) =>
  fetchAPI(`/v1/predictions/recent?limit=${limit}`);
