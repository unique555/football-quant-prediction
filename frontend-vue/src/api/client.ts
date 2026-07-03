import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || ''

const api = axios.create({ baseURL: API_BASE, timeout: 30000 })

export async function get<T>(path: string): Promise<T> {
  const { data } = await api.get<T>(path)
  return data
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const { data } = await api.post<T>(path, body)
  return data
}

// --- 价值投注 ---
export const getValueToday = (limit = 20) => get<any[]>(`/v1/value/today?limit=${limit}`)

// --- 比赛 ---
export const getTodayMatches = () => get<any[]>('/v1/matches/today')
export const getMatchDetail = (id: string) => get<any>(`/v1/matches/${id}`)

// --- 预测 ---
export const predictMatch = (query: string) => post('/v1/predict', { query })

// --- 统计 ---
export const getStats = () => get<any>('/v1/stats')
export const getPerformance = () => get<any>('/v1/stats/performance')
export const getProfitCurve = () => get<any[]>('/v1/stats/profit-curve')

// --- 系统 ---
export const getSystemStatus = () => get<any>('/v1/system/status')

// --- 预测记录 ---
export const getRecentPredictions = (limit = 20) => get<any[]>(`/v1/predictions/recent?limit=${limit}`)
