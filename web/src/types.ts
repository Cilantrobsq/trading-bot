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
  ticker: string
  name: string
  price: number | null
  prev_close: number | null
  change_pct: number | null
  threshold: number | null
  threshold_breached: boolean
  signal: string
  source: string
  error: string | null
}

export interface SignalsData {
  signals: Signal[]
  fetched_at?: string | null
  last_updated?: string | null
}

export interface FredSignal {
  series_id: string
  name: string
  value: number | null
  prev_value: number | null
  change_pct: number | null
  threshold: number | null
  breached: boolean
  direction: string
  last_updated: string
  error: string | null
}

export interface FredData {
  signals: FredSignal[]
  fetched_at?: string | null
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
  high_correlations: Array<{ ticker_a: string; ticker_b: string; correlation: number; risk: string }>
  warnings: string[]
  suggested_hedges: Array<{ ticker: string; name: string; correlation_to_portfolio: number; hedge_effectiveness: string }>
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

export interface EquityPoint {
  timestamp: string
  value: number
  pnl: number
  pnl_pct: number
  positions: number
}

// Global Markets
export interface GlobalMarketPoint {
  ticker: string
  name: string
  region: string
  price: number | null
  prev_close: number | null
  change_pct: number | null
  week_change_pct: number | null
  month_change_pct: number | null
  volume: number | null
  volume_ratio: number | null
  pct_from_52w_high: number | null
  ma_50d: number | null
  ma_200d: number | null
  above_50d: boolean | null
  above_200d: boolean | null
  error: string | null
  extra?: Record<string, unknown>
}

export interface SessionSummary {
  session: string
  label: string
  markets_up: number
  markets_down: number
  markets_flat: number
  avg_change_pct: number
  strongest: string | null
  strongest_pct: number | null
  weakest: string | null
  weakest_pct: number | null
  breadth: number
}

export interface GapSignal {
  from_session: string
  to_session: string
  from_avg_change: number
  to_avg_change: number
  gap_magnitude: number
  divergent: boolean
  description: string
}

export interface GlobalMarketsData {
  indices: Record<string, GlobalMarketPoint[]>
  forex: GlobalMarketPoint[]
  commodities: GlobalMarketPoint[]
  crypto: GlobalMarketPoint[]
  bonds: GlobalMarketPoint[]
  sessions: Record<string, SessionSummary>
  gaps: GapSignal[]
  global_breadth: number
  total_markets: number
  fetched_at: string
}

// Global Macro
export interface GlobalMacroSignal {
  series_id: string
  name: string
  country: string
  category: string
  value: number | null
  prev_value: number | null
  change_pct: number | null
  threshold: number | null
  breached: boolean
  direction: string
  last_updated: string
  error: string | null
}

export interface RateDifferential {
  high_rate_country: string
  low_rate_country: string
  high_rate: number
  low_rate: number
  differential: number
  direction: string
  description: string
}

export interface GlobalMacroData {
  signals: GlobalMacroSignal[]
  by_category: Record<string, GlobalMacroSignal[]>
  by_country: Record<string, GlobalMacroSignal[]>
  rate_differentials: RateDifferential[]
  breaches: GlobalMacroSignal[]
  total_series: number
  fetched_ok: number
  total_breaches: number
  analyzed_at: string
}

// Timezone Arbitrage
export interface LeadLagResult {
  leader: string
  follower: string
  pair_name: string
  label: string
  correlation: number | null
  same_direction_pct: number | null
  sharp_follow_rate: number | null
  sample_size: number
  signal: string
  confidence: number
  description: string
}

export interface TimezoneSignal {
  signal_type: string
  direction: string
  strength: number
  target_market: string
  source_market: string
  description: string
  supporting_data: Record<string, unknown>
}

export interface TimezoneArbData {
  lead_lag: LeadLagResult[]
  realtime_signals: TimezoneSignal[]
  analyzed_at: string
}

// Cross Correlations
export interface CrossCorrelationData {
  matrix: {
    tickers: string[]
    names: string[]
    matrix_30d: (number | null)[][]
    matrix_90d: (number | null)[][]
    avg_correlation_30d: number
    avg_correlation_90d: number
    systemic_risk_score: number
  }
  anomalies: Array<{
    ticker_a: string
    name_a: string
    ticker_b: string
    name_b: string
    correlation_30d: number | null
    correlation_90d: number | null
    correlation_change: number | null
    is_breakdown: boolean
    is_unusual: boolean
    is_concentrated: boolean
    signal: string
    description: string
  }>
  top_correlated: Array<{ pair: string; correlation: number }>
  best_hedges: Array<{ pair: string; correlation: number }>
  systemic_risk_score: number
  analyzed_at: string
}

// Trade Proposals
export interface TradeProposal {
  id: string
  ticker: string
  name: string
  direction: string
  entry_price: number
  target_price: number
  stop_price: number
  risk_reward: number
  position_size_pct: number
  position_size_usd: number
  confidence: number
  max_loss_usd: number
  max_gain_usd: number
  category: string
  reasoning: string
  supporting_signals: string[]
  opposing_signals: string[]
  created_at: string
  expires_at: string
  status: string
  urgency: string
  seconds_remaining: number
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
  fred?: FredData
  equity_history?: EquityPoint[]
  global_markets?: GlobalMarketsData
  global_macro?: GlobalMacroData
  timezone_arb?: TimezoneArbData
  cross_correlations?: CrossCorrelationData
  proposals?: TradeProposal[]
}
