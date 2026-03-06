export interface PortfolioData {
  balance: number
  initial_balance: number
  total_pnl: number
  total_pnl_pct: number
  positions: Position[]
  mode: string
  last_updated: string | null
}

export interface Position {
  market_id: string
  market_name: string
  side: string
  entry_price: number
  quantity: number
  entry_time: string
  theme_id: string
  current_price: number
  unrealized_pnl?: number
  unrealized_pnl_pct?: number
}

export interface Signal {
  name: string
  ticker: string
  value: number | null
  threshold: number | null
  direction: string
  status: string
  theme: string
}

export interface SignalsData {
  signals: Signal[]
  last_updated: string | null
}

export interface Opportunity {
  market: string
  spread_pct: number
  model_price: number
  market_price: number
  direction: string
  confidence: number
  theme: string
}

export interface OpportunitiesData {
  opportunities: Opportunity[]
  last_updated: string | null
}

export interface Trade {
  market: string
  side: string
  price: number
  quantity: number
  pnl?: number
  timestamp: string
  type: string
}

export interface TradesData {
  trades: Trade[]
  count: number
}

export interface ConfigData {
  strategy: Record<string, unknown>
  themes: Record<string, unknown>
}

// Brain / Bot Thinking
export interface PlannedAction {
  action_type: string
  market: string
  direction: string
  size_pct: number
  reasoning: string
  priority: number
  blocked_by: string | null
}

export interface ThemeAssessment {
  theme_id: string
  conviction: number
  signals_supporting: number
  signals_against: number
}

export interface RiskState {
  daily_pnl: number
  daily_pnl_pct: number
  max_daily_loss_pct: number
  circuit_breaker_active: boolean
  exposure_pct: number
  correlation_warning: boolean
}

export interface BrainData {
  market_regime: string
  regime_confidence: number
  overall_sentiment: number
  active_themes: ThemeAssessment[]
  planned_actions: PlannedAction[]
  risk_state: RiskState
  last_updated: string
}

// Decision Log
export interface DecisionEntry {
  id: string
  timestamp: string
  decision_type: string
  input_data: Record<string, unknown>
  output_data: Record<string, unknown>
  reasoning: string
  confidence: number
  action_taken: string | null
}

// Theses
export interface Thesis {
  id: string
  title: string
  direction: string
  confidence: number
  reasoning: string
  catalysts: string[]
  invalidation_conditions: string[]
  time_horizon: number
  affected_tickers: string[]
  affected_themes: string[]
  status: string
  created_at: string
  updated_at: string
  outcome: string | null
}

// Signal Overrides
export interface SignalOverride {
  id: string
  signal_type: string
  ticker_or_market: string
  override_type: string
  strength: number
  reason: string
  active: boolean
  expires_at: string | null
}

// Kill Switch
export interface KillSwitchStatus {
  active: boolean
  reason: string | null
  activated_at: string | null
}

// Regime
export interface RegimeData {
  regime: string
  risk_multiplier: number
  details: Record<string, unknown>
  last_updated: string
}

// Circuit Breaker
export interface CircuitBreakerData {
  active: boolean
  daily_pnl: number
  hourly_pnl: number
  trades_this_hour: number
  last_trigger: string | null
  reason: string | null
}

// Correlation
export interface CorrelationData {
  diversification_score: number
  high_correlations: Array<{ pair: string[]; correlation: number }>
  warnings: string[]
  suggested_hedges: string[]
}

// Niche Markets
export interface NicheMarket {
  market_id: string
  question: string
  category: string
  volume_usd: number
  unique_traders: number
  current_price: number
  spread: number
  time_to_expiry_days: number
  niche_score: number
  information_advantage_notes: string
}

export interface NewsItem {
  title: string
  link: string
  published: string
  source_feed: string
  matched_themes: string[]
  matched_keywords: string[]
  relevance_score: number
  sentiment_hint: string
}

export interface SnapshotData {
  timestamp: string | null
  regime: string
  regime_confidence: number
  sentiment: number
  portfolio: Record<string, unknown>
  signals_summary: {
    total: number
    bullish: number
    bearish: number
    neutral: number
    errors: number
  }
  news_count: number
  active_theses: number
  planned_actions: number
  circuit_breaker: boolean
}

export interface DashboardData {
  exported_at: string
  portfolio: PortfolioData
  signals: SignalsData
  opportunities: OpportunitiesData
  trades: TradesData
  config: ConfigData
  brain?: BrainData
  decisions?: DecisionEntry[]
  theses?: Thesis[]
  overrides?: SignalOverride[]
  kill_switch?: KillSwitchStatus
  regime?: RegimeData
  circuit_breaker?: CircuitBreakerData
  correlations?: CorrelationData
  niche_markets?: NicheMarket[]
  news?: NewsItem[]
  snapshot?: SnapshotData
}
