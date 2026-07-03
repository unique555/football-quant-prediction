export type HealthStatus = {
  status: string;
  version: string;
};

export type StatsSummary = {
  total_predictions: number;
  value_predictions: number;
  settled_predictions?: number;
  recent_value_rate: number;
};

export type PredictionRow = {
  id: number;
  fixture_id: number;
  home_team: string | null;
  away_team: string | null;
  league: string | null;
  kickoff: string | null;
  best_pick: string | null;
  best_market?: string | null;
  best_odds: number | null;
  best_ev: number | null;
  best_kelly: number | null;
  best_edge?: number | null;
  best_bookmaker?: string | null;
  market_prob?: number | null;
  value_score: number | null;
  risk: string | null;
  settled_status?: string | null;
  profit_units?: number | null;
  created_at: string | null;
};

export type TodayMatch = {
  fixture_id: number;
  home_team: string;
  away_team: string;
  league: string | null;
  kickoff: string | null;
  status: string | null;
  analyzed: boolean;
  best_pick: string | null;
  value_score: number | null;
  risk: string | null;
  review_status: string | null;
  score: string | null;
};

export type PerformanceBucket = {
  count: number;
  hit_rate: number;
  profit_units: number;
};

export type PerformanceSummary = {
  overall: PerformanceBucket;
  by_market: Record<string, PerformanceBucket>;
  by_bookmaker_count: Record<string, PerformanceBucket>;
  by_consensus: Record<string, PerformanceBucket>;
  by_disagreement: Record<string, PerformanceBucket>;
  recommendations: string[];
};

export type SystemStatus = {
  status: string;
  environment: string;
  database: string;
  api_football: string;
  telegram_bot: string;
  mlflow: string;
};
