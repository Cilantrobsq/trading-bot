import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts'

interface PredictionsViewProps {
  data: any
}

const COLORS = {
  green: '#22c55e',
  red: '#ef4444',
  amber: '#f59e0b',
  blue: '#3b82f6',
  purple: '#a855f7',
  cyan: '#06b6d4',
  zinc: '#71717a',
  pink: '#ec4899',
}

const CATEGORY_COLORS: Record<string, string> = {
  crypto: COLORS.amber,
  geopolitics: COLORS.red,
  markets: COLORS.blue,
  economics: COLORS.green,
  tech: COLORS.purple,
  energy: COLORS.cyan,
  other: COLORS.zinc,
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

function fmtPrice(n: number): string {
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
  return `$${n.toFixed(2)}`
}

function fmtVol(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return `${n}`
}

// Kalshi distribution bar chart
function DistributionChart({ buckets, asset }: { buckets: any[]; asset: string }) {
  if (!buckets || buckets.length === 0) return null

  // Filter to buckets with probability > 0
  const data = buckets
    .filter((b: any) => b.midpoint_prob > 0.005)
    .map((b: any) => ({
      label: b.label?.replace(/\$/g, '').replace(/,/g, '').substring(0, 15) || '?',
      prob: b.midpoint_prob * 100,
      volume: b.volume,
      fullLabel: b.label,
    }))

  const assetColor = asset === 'btc' ? COLORS.amber : asset === 'eth' ? COLORS.purple : COLORS.blue

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
        <XAxis dataKey="label" tick={{ fontSize: 9, fill: '#a1a1aa' }} interval={Math.max(0, Math.floor(data.length / 8))} />
        <YAxis tick={{ fontSize: 10, fill: '#a1a1aa' }} tickFormatter={(v) => `${v}%`} width={40} />
        <Tooltip
          contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 12 }}
          formatter={(v: any, _: any, props: any) => [`${Number(v).toFixed(1)}%`, props?.payload?.fullLabel]}
        />
        <Bar dataKey="prob" radius={[2, 2, 0, 0]}>
          {data.map((_: any, i: number) => (
            <Cell key={i} fill={assetColor} fillOpacity={0.8} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// Edge signal card
function EdgeCard({ signal }: { signal: any }) {
  const edge = signal.edge_pct || 0
  const isPositive = edge > 0
  const conf = signal.confidence || 'low'
  const confColor = conf === 'high' ? COLORS.green : conf === 'medium' ? COLORS.amber : COLORS.zinc

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-3">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 shrink-0">
            {signal.platform}
          </span>
          <span className="text-sm font-medium truncate">{signal.question}</span>
        </div>
        <span className={`text-sm font-bold shrink-0 ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
          {edge > 0 ? '+' : ''}{edge.toFixed(1)}%
        </span>
      </div>

      <div className="grid grid-cols-4 gap-2 text-xs">
        <div>
          <div className="text-muted-foreground">Market</div>
          <div className="font-mono">{fmtPct(signal.yes_price)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Model</div>
          <div className="font-mono">{fmtPct(signal.model_probability)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Direction</div>
          <div className={isPositive ? 'text-green-400' : 'text-red-400'}>
            {signal.direction}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">Confidence</div>
          <div style={{ color: confColor }}>{conf}</div>
        </div>
      </div>

      {signal.underlying && (
        <div className="mt-2 text-xs text-muted-foreground">
          {signal.underlying}: {fmtPrice(signal.current_price || 0)} / target: {fmtPrice(signal.target_price || 0)}
        </div>
      )}

      {/* Edge bar */}
      <div className="mt-2 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.min(Math.abs(edge) * 3, 100)}%`,
            backgroundColor: isPositive ? COLORS.green : COLORS.red,
          }}
        />
      </div>
    </div>
  )
}

// Market signal row
function MarketRow({ signal }: { signal: any }) {
  const catColor = CATEGORY_COLORS[signal.category] || COLORS.zinc

  return (
    <div className="flex items-center gap-3 py-2 border-b border-zinc-800/50 last:border-0">
      <span
        className="text-xs px-1.5 py-0.5 rounded shrink-0"
        style={{ backgroundColor: `${catColor}20`, color: catColor }}
      >
        {signal.category}
      </span>
      <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 shrink-0">
        {signal.platform}
      </span>
      <span className="text-sm truncate flex-1 min-w-0">{signal.question}</span>
      <div className="flex items-center gap-3 shrink-0">
        <span className="text-sm font-mono text-green-400">{fmtPct(signal.yes_price)}</span>
        <span className="text-xs text-muted-foreground">{fmtVol(signal.volume)}</span>
      </div>
    </div>
  )
}

export function PredictionsView({ data }: PredictionsViewProps) {
  if (!data) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          <p className="text-lg mb-2">No prediction market data yet</p>
          <p className="text-sm">Run the bot to scan Kalshi and Polymarket for live market data,
            implied probability distributions, and model-vs-market edge signals.</p>
        </CardContent>
      </Card>
    )
  }

  const edgeSignals = data.edge_signals || []
  const marketSignals = data.market_signals || []
  const distributions = data.kalshi?.distributions || []
  const arbitrage = data.arbitrage || []
  const summary = data.summary || {}
  const polyCategories = data.polymarket?.categories || {}

  // Category pie data for Polymarket
  const pieData = Object.entries(polyCategories)
    .filter(([cat]) => cat !== 'other')
    .map(([cat, count]) => ({
      name: cat,
      value: count as number,
      fill: CATEGORY_COLORS[cat] || COLORS.zinc,
    }))

  return (
    <div className="space-y-4">
      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <Card>
          <CardContent className="py-3 text-center">
            <div className="text-2xl font-bold">{summary.total_signals || 0}</div>
            <div className="text-xs text-muted-foreground">Total Signals</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <div className="text-2xl font-bold text-amber-400">{summary.edge_signals || 0}</div>
            <div className="text-xs text-muted-foreground">Edge Signals</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <div className="text-2xl font-bold text-purple-400">{summary.arbitrage_opportunities || 0}</div>
            <div className="text-xs text-muted-foreground">Arbitrage</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <div className="text-2xl font-bold text-blue-400">{summary.kalshi_distributions || 0}</div>
            <div className="text-xs text-muted-foreground">Kalshi Dists</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <div className="text-2xl font-bold text-cyan-400">{summary.polymarket_finance_markets || 0}</div>
            <div className="text-xs text-muted-foreground">Polymarket Finance</div>
          </CardContent>
        </Card>
      </div>

      {/* Kalshi price distributions */}
      {distributions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Kalshi Implied Price Distributions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {distributions.map((dist: any, i: number) => (
                <div key={i} className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium">{(dist.asset || '').toUpperCase()}</span>
                    {dist.expected_price && (
                      <span className="text-sm font-mono text-amber-400">
                        E[P] = {fmtPrice(dist.expected_price)}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground mb-2">
                    {dist.title} / vol: {fmtVol(dist.total_volume || 0)}
                  </div>
                  <DistributionChart buckets={dist.buckets || []} asset={dist.asset || ''} />
                  {dist.prob_above_levels && Object.keys(dist.prob_above_levels).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {Object.entries(dist.prob_above_levels).map(([level, prob]) => (
                        <span key={level} className="text-xs px-2 py-0.5 rounded bg-zinc-800">
                          P({level}): <span className="font-mono text-amber-400">{fmtPct(prob as number)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Edge signals - model vs market */}
      {edgeSignals.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Model vs Market Edge ({edgeSignals.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {edgeSignals.map((s: any, i: number) => (
                <EdgeCard key={i} signal={s} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Arbitrage opportunities */}
      {arbitrage.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-purple-400">
              Cross-Platform Arbitrage ({arbitrage.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {arbitrage.map((a: any, i: number) => (
                <div key={i} className="bg-purple-950/20 border border-purple-800/50 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-bold text-purple-400">
                      {a.spread_pct?.toFixed(1)}% spread
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <div className="text-muted-foreground">Kalshi</div>
                      <div className="truncate">{a.kalshi_question}</div>
                      <div className="font-mono text-green-400">{fmtPct(a.kalshi_price)}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Polymarket</div>
                      <div className="truncate">{a.polymarket_question}</div>
                      <div className="font-mono text-blue-400">{fmtPct(a.polymarket_price)}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Polymarket categories + market signals */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Category breakdown */}
        {pieData.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Polymarket Categories</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {pieData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 12 }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap gap-2 mt-2 justify-center">
                {pieData.map((d, i) => (
                  <span key={i} className="text-xs flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: d.fill }} />
                    {d.name}: {d.value}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Market signals list */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Market Signals ({marketSignals.length})</CardTitle>
          </CardHeader>
          <CardContent className="max-h-96 overflow-y-auto">
            {marketSignals.length === 0 ? (
              <div className="text-sm text-muted-foreground py-4 text-center">No market signals available</div>
            ) : (
              marketSignals.map((s: any, i: number) => (
                <MarketRow key={i} signal={s} />
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Timestamp */}
      {data.timestamp && (
        <div className="text-xs text-muted-foreground text-center">
          Last scan: {new Date(data.timestamp).toLocaleString()}
        </div>
      )}
    </div>
  )
}
