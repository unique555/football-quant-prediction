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
  home_team_zh?: string | null;
  away_team_zh?: string | null;
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
  home_team_zh?: string | null;
  away_team_zh?: string | null;
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

export type MatchListItem = {
  id: number;
  fixture_id: number;
  home_team: string | null;
  away_team: string | null;
  home_team_zh?: string | null;
  away_team_zh?: string | null;
  league: string | null;
  kickoff: string | null;
  status: string | null;
  score: string | null;
};

export type MarketOutcome = {
  label: string;
  probability: number | null;
  tone: "positive" | "warning" | "negative" | "neutral" | string;
};

export type MarketMetric = {
  label: string;
  value: string;
};

export type MarketCard = {
  market: "1x2" | "asian_handicap" | "over_under" | "corners" | string;
  title: string;
  subtitle: string;
  status: "ready" | "empty" | string;
  outcomes: MarketOutcome[];
  metrics: MarketMetric[];
  action: string;
};

export type AnalysisReport = {
  title: string;
  sections: Array<{
    title: string;
    items: string[];
  }>;
  raw_report: string;
  primary_market: string | null;
};

export type MatchDetail = {
  fixture_id: number;
  home_team: string | null;
  away_team: string | null;
  home_team_zh?: string | null;
  away_team_zh?: string | null;
  league: string | null;
  kickoff: string | null;
  status: string | null;
  market_cards?: MarketCard[];
  analysis_report?: AnalysisReport;
  result: {
    home_goals: number | null;
    away_goals: number | null;
    status: string | null;
  } | null;
  predictions: Array<{
    best_pick: string | null;
    best_market?: string | null;
    best_odds?: number | null;
    best_ev?: number | null;
    best_kelly?: number | null;
    best_edge?: number | null;
    home_win_prob?: number | null;
    draw_prob?: number | null;
    away_win_prob?: number | null;
    value_score: number | null;
    risk: string | null;
    settled_status: string | null;
    profit_units: number | null;
    settlement_note: string | null;
    created_at: string | null;
    report_text: string | null;
  }>;
  value_candidates: Array<{
    market: string;
    pick: string;
    display_pick?: string | null;
    line: number | null;
    odds: number | null;
    prob: number | null;
    market_prob: number | null;
    ev: number | null;
    kelly: number | null;
    edge: number | null;
    bookmaker_count: number | null;
    consensus_score: number | null;
    disagreement_index: number | null;
    risk: string | null;
    value_score: number | null;
    selected: boolean | null;
    settled_status: string | null;
    settlement_note: string | null;
  }>;
  odds_snapshots: Array<{
    market: string;
    bookmaker: string | null;
    home_odds: number | null;
    draw_odds: number | null;
    away_odds: number | null;
    ah_line: number | null;
    ah_home_odds: number | null;
    ah_away_odds: number | null;
    ou_line: number | null;
    over_odds: number | null;
    under_odds: number | null;
    snapshot_type: string | null;
    captured_at: string | null;
  }>;
};
