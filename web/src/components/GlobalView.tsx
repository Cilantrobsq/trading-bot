import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  RadialBarChart, RadialBar,
} from 'recharts'
import type {
  GlobalMarketsData, GlobalMacroData, TimezoneArbData,
  CrossCorrelationData, GlobalMarketPoint, SessionSummary,
} from '@/types'

interface Props {
  globalMarkets?: GlobalMarketsData
  globalMacro?: GlobalMacroData
  timezoneArb?: TimezoneArbData
  crossCorrelations?: CrossCorrelationData
}

const REGION_COLORS: Record<string, string> = {
  asia: '#f59e0b',
  europe: '#3b82f6',
  americas: '#10b981',
}

const REGION_LABELS: Record<string, string> = {
  asia: 'Asia-Pacific',
  europe: 'Europe',
  americas: 'Americas',
}

function formatNum(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '-'
  return n.toFixed(decimals)
}

function changeColor(pct: number | null | undefined): string {
  if (pct == null) return 'text-muted-foreground'
  if (pct > 0.1) return 'text-green-400'
  if (pct < -0.1) return 'text-red-400'
  return 'text-muted-foreground'
}

function barColor(v: number): string {
  if (v > 1) return '#22c55e'
  if (v > 0) return '#4ade80'
  if (v > -1) return '#f87171'
  return '#ef4444'
}

// -- Session Summary Cards --
function SessionCards({ sessions }: { sessions: Record<string, SessionSummary> }) {
  const order = ['asia', 'europe', 'americas']
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {order.map(key => {
        const s = sessions[key]
        if (!s) return null
        const color = REGION_COLORS[key] || '#888'
        return (
          <Card key={key} className="border-l-4" style={{ borderLeftColor: color }}>
            <CardHeader className="pb-2 pt-3 px-3">
              <CardTitle className="text-sm font-medium" style={{ color }}>{s.label}</CardTitle>
            </CardHeader>
            <CardContent className="px-3 pb-3 space-y-1">
              <div className="flex justify-between text-xs">
                <span>Avg Change</span>
                <span className={changeColor(s.avg_change_pct)}>{formatNum(s.avg_change_pct)}%</span>
              </div>
              <div className="flex justify-between text-xs">
                <span>Breadth</span>
                <span className={s.breadth > 60 ? 'text-green-400' : s.breadth < 40 ? 'text-red-400' : 'text-muted-foreground'}>
                  {formatNum(s.breadth, 0)}% positive
                </span>
              </div>
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{s.markets_up} up / {s.markets_down} down / {s.markets_flat} flat</span>
              </div>
              {s.strongest && (
                <div className="text-xs text-green-400/80 truncate">Best: {s.strongest} ({formatNum(s.strongest_pct)}%)</div>
              )}
              {s.weakest && (
                <div className="text-xs text-red-400/80 truncate">Worst: {s.weakest} ({formatNum(s.weakest_pct)}%)</div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}

// -- Indices Bar Chart --
function IndicesChart({ indices }: { indices: Record<string, GlobalMarketPoint[]> }) {
  const data: Array<{ name: string; change: number; region: string }> = []
  for (const [region, pts] of Object.entries(indices)) {
    for (const p of pts) {
      if (p.change_pct != null) {
        data.push({ name: p.name, change: p.change_pct, region })
      }
    }
  }
  data.sort((a, b) => b.change - a.change)

  return (
    <Card>
      <CardHeader className="pb-2 pt-3 px-3">
        <CardTitle className="text-sm font-medium">Global Indices (Daily Change %)</CardTitle>
      </CardHeader>
      <CardContent className="px-1 pb-2">
        <ResponsiveContainer width="100%" height={Math.max(300, data.length * 22)}>
          <BarChart data={data} layout="vertical" margin={{ left: 100, right: 10, top: 5, bottom: 5 }}>
            <XAxis type="number" tick={{ fill: '#888', fontSize: 10 }} />
            <YAxis type="category" dataKey="name" tick={{ fill: '#ccc', fontSize: 10 }} width={95} />
            <Tooltip
              contentStyle={{ background: '#1a1a2e', border: '1px solid #333', borderRadius: 6, fontSize: 12 }}
              formatter={(v: any, _: any, entry: any) => [`${Number(v).toFixed(2)}%`, REGION_LABELS[entry.payload.region] || entry.payload.region]}
            />
            <Bar dataKey="change" radius={[0, 3, 3, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={REGION_COLORS[d.region] || '#888'} opacity={d.change >= 0 ? 1 : 0.7} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}

// -- Forex, Commodities, Crypto, Bonds Table --
function AssetTable({ title, data, showExtra }: { title: string; data: GlobalMarketPoint[]; showExtra?: string }) {
  return (
    <Card>
      <CardHeader className="pb-1 pt-3 px-3">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent className="px-2 pb-2 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground border-b border-border">
              <th className="text-left py-1 px-1">Name</th>
              <th className="text-right py-1 px-1">Price</th>
              <th className="text-right py-1 px-1">Day</th>
              <th className="text-right py-1 px-1">Week</th>
              <th className="text-right py-1 px-1">Month</th>
              {showExtra && <th className="text-right py-1 px-1">{showExtra}</th>}
            </tr>
          </thead>
          <tbody>
            {data.map((d, i) => (
              <tr key={i} className="border-b border-border/30">
                <td className="py-1 px-1 font-medium">{d.name}</td>
                <td className="text-right py-1 px-1 tabular-nums">{d.price != null ? d.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '-'}</td>
                <td className={`text-right py-1 px-1 tabular-nums ${changeColor(d.change_pct)}`}>{formatNum(d.change_pct)}%</td>
                <td className={`text-right py-1 px-1 tabular-nums ${changeColor(d.week_change_pct)}`}>{formatNum(d.week_change_pct)}%</td>
                <td className={`text-right py-1 px-1 tabular-nums ${changeColor(d.month_change_pct)}`}>{formatNum(d.month_change_pct)}%</td>
                {showExtra === 'Vol Ratio' && (
                  <td className="text-right py-1 px-1 tabular-nums">{d.volume_ratio != null ? `${d.volume_ratio.toFixed(1)}x` : '-'}</td>
                )}
                {showExtra === 'Country' && (
                  <td className="text-right py-1 px-1">{(d.extra as any)?.country || '-'}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

// -- Gap Signals --
function GapSignals({ gaps }: { gaps: Array<{ description: string; divergent: boolean; gap_magnitude: number }> }) {
  if (!gaps || gaps.length === 0) return null
  return (
    <Card>
      <CardHeader className="pb-1 pt-3 px-3">
        <CardTitle className="text-sm font-medium">Session Gap Analysis</CardTitle>
      </CardHeader>
      <CardContent className="px-3 pb-3 space-y-2">
        {gaps.map((g, i) => (
          <div key={i} className={`text-xs p-2 rounded border ${g.divergent ? 'border-amber-500/40 bg-amber-500/5' : 'border-border bg-muted/20'}`}>
            {g.divergent && <span className="text-amber-400 font-medium mr-1">DIVERGENCE</span>}
            {g.description}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// -- Global Macro Breaches --
function MacroBreaches({ globalMacro }: { globalMacro: GlobalMacroData }) {
  const breaches = globalMacro.breaches || []
  const rds = globalMacro.rate_differentials || []

  return (
    <div className="space-y-3">
      {breaches.length > 0 && (
        <Card>
          <CardHeader className="pb-1 pt-3 px-3">
            <CardTitle className="text-sm font-medium text-red-400">Threshold Breaches ({breaches.length})</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 space-y-1">
            {breaches.map((b, i) => (
              <div key={i} className="text-xs flex justify-between border-b border-border/30 py-1">
                <span>{b.country} / {b.name}</span>
                <span className="text-red-400 tabular-nums">{formatNum(b.value, 2)} (threshold: {formatNum(b.threshold, 2)})</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {rds.length > 0 && (
        <Card>
          <CardHeader className="pb-1 pt-3 px-3">
            <CardTitle className="text-sm font-medium">Interest Rate Differentials (Carry Trade Signals)</CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-2 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground border-b border-border">
                  <th className="text-left py-1 px-1">High Rate</th>
                  <th className="text-left py-1 px-1">Low Rate</th>
                  <th className="text-right py-1 px-1">Spread</th>
                  <th className="text-left py-1 px-1">Signal</th>
                </tr>
              </thead>
              <tbody>
                {rds.map((r, i) => (
                  <tr key={i} className="border-b border-border/30">
                    <td className="py-1 px-1">{r.high_rate_country} ({r.high_rate}%)</td>
                    <td className="py-1 px-1">{r.low_rate_country} ({r.low_rate}%)</td>
                    <td className={`text-right py-1 px-1 tabular-nums ${r.differential > 3 ? 'text-amber-400' : ''}`}>{r.differential}pp</td>
                    <td className="py-1 px-1 text-muted-foreground">{r.direction.replace(/_/g, ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// -- Global Macro by Category Chart --
function MacroByCategoryChart({ globalMacro }: { globalMacro: GlobalMacroData }) {
  const signals = (globalMacro.signals || []).filter(s => s.value != null && s.change_pct != null)
  if (signals.length === 0) return null

  const data = signals.map(s => ({
    name: `${s.country}/${s.name.split(' ').slice(0, 2).join(' ')}`,
    change: s.change_pct!,
    breached: s.breached,
  })).sort((a, b) => Math.abs(b.change) - Math.abs(a.change)).slice(0, 20)

  return (
    <Card>
      <CardHeader className="pb-2 pt-3 px-3">
        <CardTitle className="text-sm font-medium">Global Macro Indicators (30d Change %)</CardTitle>
      </CardHeader>
      <CardContent className="px-1 pb-2">
        <ResponsiveContainer width="100%" height={Math.max(250, data.length * 20)}>
          <BarChart data={data} layout="vertical" margin={{ left: 130, right: 10, top: 5, bottom: 5 }}>
            <XAxis type="number" tick={{ fill: '#888', fontSize: 10 }} />
            <YAxis type="category" dataKey="name" tick={{ fill: '#ccc', fontSize: 10 }} width={125} />
            <Tooltip
              contentStyle={{ background: '#1a1a2e', border: '1px solid #333', borderRadius: 6, fontSize: 12 }}
              formatter={(v: any) => [`${Number(v).toFixed(2)}%`, '30d Change']}
            />
            <Bar dataKey="change" radius={[0, 3, 3, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.breached ? '#ef4444' : barColor(d.change)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}

// -- Timezone Arb Signals --
function TzArbSection({ tzArb }: { tzArb: TimezoneArbData }) {
  const leadLag = tzArb.lead_lag || []
  const rtSignals = tzArb.realtime_signals || []

  return (
    <div className="space-y-3">
      {rtSignals.length > 0 && (
        <Card>
          <CardHeader className="pb-1 pt-3 px-3">
            <CardTitle className="text-sm font-medium">Live Timezone Signals</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 space-y-2">
            {rtSignals.map((s, i) => (
              <div key={i} className={`text-xs p-2 rounded border ${
                s.direction === 'bullish' ? 'border-green-500/40 bg-green-500/5' :
                s.direction === 'bearish' ? 'border-red-500/40 bg-red-500/5' :
                'border-border bg-muted/20'
              }`}>
                <div className="flex justify-between mb-1">
                  <span className="font-medium">{s.signal_type.replace(/_/g, ' ').toUpperCase()}</span>
                  <span className={s.direction === 'bullish' ? 'text-green-400' : s.direction === 'bearish' ? 'text-red-400' : 'text-muted-foreground'}>
                    {s.direction.toUpperCase()} ({(s.strength * 100).toFixed(0)}%)
                  </span>
                </div>
                <div className="text-muted-foreground">{s.description}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-1 pt-3 px-3">
          <CardTitle className="text-sm font-medium">Lead-Lag Analysis (Historical Patterns)</CardTitle>
        </CardHeader>
        <CardContent className="px-2 pb-2 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted-foreground border-b border-border">
                <th className="text-left py-1 px-1">Pair</th>
                <th className="text-right py-1 px-1">Corr</th>
                <th className="text-right py-1 px-1">Same Dir</th>
                <th className="text-right py-1 px-1">Sharp Follow</th>
                <th className="text-center py-1 px-1">Signal</th>
                <th className="text-right py-1 px-1">Conf</th>
              </tr>
            </thead>
            <tbody>
              {leadLag.map((ll, i) => (
                <tr key={i} className="border-b border-border/30">
                  <td className="py-1 px-1 font-medium">{ll.label}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{ll.correlation != null ? ll.correlation.toFixed(3) : '-'}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{ll.same_direction_pct != null ? `${ll.same_direction_pct}%` : '-'}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{ll.sharp_follow_rate != null ? `${ll.sharp_follow_rate}%` : '-'}</td>
                  <td className={`text-center py-1 px-1 font-medium ${
                    ll.signal === 'follow' ? 'text-green-400' :
                    ll.signal === 'fade' ? 'text-red-400' : 'text-muted-foreground'
                  }`}>{ll.signal.toUpperCase()}</td>
                  <td className="text-right py-1 px-1 tabular-nums">{formatNum(ll.confidence, 0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

// -- Correlation Anomalies --
function CorrelationSection({ crossCorr }: { crossCorr: CrossCorrelationData }) {
  const anomalies = crossCorr.anomalies || []
  const topCorr = crossCorr.top_correlated || []
  const hedges = crossCorr.best_hedges || []
  const systemic = crossCorr.systemic_risk_score || 0

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card>
          <CardContent className="p-3 text-center">
            <div className={`text-2xl font-bold tabular-nums ${systemic > 60 ? 'text-red-400' : systemic > 40 ? 'text-amber-400' : 'text-green-400'}`}>
              {systemic.toFixed(0)}
            </div>
            <div className="text-xs text-muted-foreground">Systemic Risk</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold tabular-nums">{crossCorr.matrix?.avg_correlation_30d?.toFixed(2) || '-'}</div>
            <div className="text-xs text-muted-foreground">Avg Corr (30d)</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold tabular-nums">{anomalies.length}</div>
            <div className="text-xs text-muted-foreground">Anomalies</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold tabular-nums">{crossCorr.matrix?.tickers?.length || 0}</div>
            <div className="text-xs text-muted-foreground">Assets Tracked</div>
          </CardContent>
        </Card>
      </div>

      {anomalies.length > 0 && (
        <Card>
          <CardHeader className="pb-1 pt-3 px-3">
            <CardTitle className="text-sm font-medium">Correlation Anomalies</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 space-y-2">
            {anomalies.slice(0, 10).map((a, i) => (
              <div key={i} className={`text-xs p-2 rounded border ${
                a.is_breakdown ? 'border-amber-500/40 bg-amber-500/5' :
                a.is_unusual ? 'border-purple-500/40 bg-purple-500/5' :
                'border-red-500/40 bg-red-500/5'
              }`}>
                <div className="flex justify-between mb-1">
                  <span className="font-medium">{a.name_a} / {a.name_b}</span>
                  <span className={
                    a.is_breakdown ? 'text-amber-400' :
                    a.is_unusual ? 'text-purple-400' : 'text-red-400'
                  }>{a.signal.replace(/_/g, ' ').toUpperCase()}</span>
                </div>
                <div className="text-muted-foreground">{a.description}</div>
                <div className="mt-1 text-muted-foreground">
                  30d: {a.correlation_30d?.toFixed(3)} | 90d: {a.correlation_90d?.toFixed(3)} | Change: {a.correlation_change?.toFixed(3)}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Card>
          <CardHeader className="pb-1 pt-3 px-3">
            <CardTitle className="text-sm font-medium">Most Correlated (Risk)</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            {topCorr.slice(0, 8).map((c, i) => (
              <div key={i} className="flex justify-between text-xs py-1 border-b border-border/30">
                <span>{c.pair}</span>
                <span className={`tabular-nums ${c.correlation > 0.8 ? 'text-red-400' : ''}`}>{c.correlation.toFixed(3)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 pt-3 px-3">
            <CardTitle className="text-sm font-medium">Best Hedges (Negative Correlation)</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            {hedges.slice(0, 8).map((c, i) => (
              <div key={i} className="flex justify-between text-xs py-1 border-b border-border/30">
                <span>{c.pair}</span>
                <span className={`tabular-nums ${c.correlation < -0.3 ? 'text-green-400' : ''}`}>{c.correlation.toFixed(3)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// -- Breadth Gauge --
function BreadthGauge({ breadth }: { breadth: number }) {
  const data = [{ name: 'breadth', value: breadth, fill: breadth > 60 ? '#22c55e' : breadth > 40 ? '#f59e0b' : '#ef4444' }]
  return (
    <Card>
      <CardContent className="p-3 flex flex-col items-center">
        <ResponsiveContainer width={120} height={100}>
          <RadialBarChart innerRadius="60%" outerRadius="100%" data={data} startAngle={180} endAngle={0}>
            <RadialBar background dataKey="value" cornerRadius={5} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="text-lg font-bold tabular-nums -mt-4">{breadth.toFixed(0)}%</div>
        <div className="text-xs text-muted-foreground">Global Breadth</div>
      </CardContent>
    </Card>
  )
}

export function GlobalView({ globalMarkets, globalMacro, timezoneArb, crossCorrelations }: Props) {
  if (!globalMarkets && !globalMacro && !timezoneArb && !crossCorrelations) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-muted-foreground">
          <p className="text-lg mb-2">Global Markets</p>
          <p className="text-sm">No global market data yet. Run the bot to fetch data from 22+ indices across Asia, Europe, and the Americas, plus forex, commodities, crypto, bonds, and 25+ macro indicators.</p>
          <p className="text-sm mt-2">The bot fetches this data every 30 minutes during market hours.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Row 1: Session summaries + breadth gauge */}
      {globalMarkets && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div className="sm:col-span-3">
              <SessionCards sessions={globalMarkets.sessions} />
            </div>
            <BreadthGauge breadth={globalMarkets.global_breadth} />
          </div>

          {/* Row 2: Indices chart */}
          <IndicesChart indices={globalMarkets.indices} />

          {/* Row 3: Gap signals */}
          <GapSignals gaps={globalMarkets.gaps} />

          {/* Row 4: Forex, Commodities, Crypto, Bonds */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <AssetTable title="Forex" data={globalMarkets.forex} />
            <AssetTable title="Commodities" data={globalMarkets.commodities} showExtra="Vol Ratio" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <AssetTable title="Crypto" data={globalMarkets.crypto} />
            <AssetTable title="Global Bonds" data={globalMarkets.bonds} showExtra="Country" />
          </div>
        </>
      )}

      {/* Row 5: Global Macro */}
      {globalMacro && (
        <>
          <MacroByCategoryChart globalMacro={globalMacro} />
          <MacroBreaches globalMacro={globalMacro} />
        </>
      )}

      {/* Row 6: Timezone Arbitrage */}
      {timezoneArb && (
        <TzArbSection tzArb={timezoneArb} />
      )}

      {/* Row 7: Cross Correlations */}
      {crossCorrelations && (
        <CorrelationSection crossCorr={crossCorrelations} />
      )}

      {/* Footer: data freshness */}
      <div className="text-xs text-muted-foreground text-center">
        {globalMarkets?.fetched_at && `Markets: ${new Date(globalMarkets.fetched_at).toLocaleString()}`}
        {globalMacro?.analyzed_at && ` | Macro: ${new Date(globalMacro.analyzed_at).toLocaleString()}`}
        {timezoneArb?.analyzed_at && ` | TZ Arb: ${new Date(timezoneArb.analyzed_at).toLocaleString()}`}
        {crossCorrelations?.analyzed_at && ` | Correlations: ${new Date(crossCorrelations.analyzed_at).toLocaleString()}`}
      </div>
    </div>
  )
}
