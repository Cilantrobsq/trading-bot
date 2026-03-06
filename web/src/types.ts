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

export interface DashboardData {
  exported_at: string
  portfolio: PortfolioData
  signals: SignalsData
  opportunities: OpportunitiesData
  trades: TradesData
  config: ConfigData
}
