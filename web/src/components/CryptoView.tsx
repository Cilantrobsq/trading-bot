import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface CryptoViewProps {
  data: any
}

const COLORS = {
  green: '#22c55e',
  red: '#ef4444',
  amber: '#f59e0b',
  blue: '#3b82f6',
  purple: '#a855f7',
  pink: '#ec4899',
  cyan: '#06b6d4',
  zinc: '#71717a',
}

const SECTOR_COLORS: Record<string, string> = {
  'L1': COLORS.blue,
  'L2': COLORS.purple,
  'DeFi': COLORS.green,
  'AI': COLORS.cyan,
  'Meme': COLORS.pink,
  'Store of Value': COLORS.amber,
  'Infrastructure': COLORS.zinc,
}

function fmtNum(n: number, decimals = 2): string {
  if (n >= 1e12) return `$${(n / 1e12).toFixed(decimals)}T`
  if (n >= 1e9) return `$${(n / 1e9).toFixed(decimals)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(decimals)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(decimals)}K`
  return `$${n.toFixed(decimals)}`
}

function FearGreedGauge({ value, classification }: { value: number | null; classification: string }) {
  if (value === null || value === undefined) {
    return <div className="text-muted-foreground text-sm">No data</div>
  }
  const pct = value / 100
  const color = value <= 25 ? COLORS.red : value <= 45 ? '#f97316' : value <= 55 ? COLORS.amber : value <= 75 ? '#84cc16' : COLORS.green
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 120 120" className="w-full h-full">
          <circle cx="60" cy="60" r="50" fill="none" stroke="#27272a" strokeWidth="12" />
          <circle
            cx="60" cy="60" r="50" fill="none"
            stroke={color} strokeWidth="12"
            strokeDasharray={`${pct * 314} 314`}
            strokeLinecap="round"
            transform="rotate(-90 60 60)"
          />
          <text x="60" y="55" textAnchor="middle" fill="white" fontSize="28" fontWeight="bold">{value}</text>
          <text x="60" y="75" textAnchor="middle" fill="#a1a1aa" fontSize="10">{classification}</text>
        </svg>
      </div>
    </div>
  )
}

export function CryptoView({ data }: CryptoViewProps) {
  if (!data) {
    return (
      <Card><CardContent className="py-8 text-center text-muted-foreground">
        No crypto data yet. Run the bot to scan crypto markets.
      </CardContent></Card>
    )
  }

  const coins = data.coins || []
  const overview = data.overview || {}
  const fearGreed = data.fear_greed || {}
  const sectors = data.sectors || []
  const anomalies = data.anomalies || []
  const signals = data.signals || []

  // Top movers chart data
  const movers = [...coins]
    .sort((a: any, b: any) => Math.abs(b.change_24h_pct || 0) - Math.abs(a.change_24h_pct || 0))
    .slice(0, 15)
    .map((c: any) => ({
      name: c.symbol,
      change: c.change_24h_pct || 0,
      price: c.price,
    }))

  // Sector chart data
  const sectorData = sectors.map((s: any) => ({
    name: s.sector,
    change24h: s.avg_change_24h_pct || 0,
    change7d: s.avg_change_7d_pct || 0,
    mcap: s.total_market_cap || 0,
  }))

  // 7d performance chart
  const weekChart = [...coins]
    .filter((c: any) => c.change_7d_pct !== undefined)
    .sort((a: any, b: any) => (b.change_7d_pct || 0) - (a.change_7d_pct || 0))
    .slice(0, 12)
    .map((c: any) => ({
      name: c.symbol,
      change: c.change_7d_pct || 0,
    }))

  return (
    <div className="space-y-4">
      {/* Row 1: Overview gauges */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card>
          <CardHeader className="pb-1 pt-3 px-3"><CardTitle className="text-xs text-muted-foreground">Fear & Greed</CardTitle></CardHeader>
          <CardContent className="flex justify-center pb-3 px-3">
            <FearGreedGauge value={fearGreed.value} classification={fearGreed.classification || ''} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 pt-3 px-3"><CardTitle className="text-xs text-muted-foreground">Total Market Cap</CardTitle></CardHeader>
          <CardContent className="pb-3 px-3">
            <div className="text-2xl font-bold">{fmtNum(overview.total_market_cap_usd || 0)}</div>
            <div className={`text-sm ${(overview.market_cap_change_24h_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {(overview.market_cap_change_24h_pct || 0) >= 0 ? '+' : ''}{overview.market_cap_change_24h_pct?.toFixed(2) || 0}% (24h)
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 pt-3 px-3"><CardTitle className="text-xs text-muted-foreground">BTC Dominance</CardTitle></CardHeader>
          <CardContent className="pb-3 px-3">
            <div className="text-2xl font-bold">{overview.btc_dominance?.toFixed(1) || '?'}%</div>
            <div className="text-sm text-muted-foreground">ETH: {overview.eth_dominance?.toFixed(1) || '?'}%</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 pt-3 px-3"><CardTitle className="text-xs text-muted-foreground">24h Volume</CardTitle></CardHeader>
          <CardContent className="pb-3 px-3">
            <div className="text-2xl font-bold">{fmtNum(overview.total_volume_24h_usd || 0)}</div>
            <div className="text-sm text-muted-foreground">{overview.active_cryptocurrencies || 0} active coins</div>
          </CardContent>
        </Card>
      </div>

      {/* Row 2: Top Movers + Sector Performance */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Top Movers (24h)</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={movers} layout="vertical" margin={{ left: 10, right: 10 }}>
                <XAxis type="number" tick={{ fill: '#71717a', fontSize: 11 }} tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`} />
                <YAxis type="category" dataKey="name" tick={{ fill: '#d4d4d8', fontSize: 11 }} width={55} />
                <Tooltip
                  contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 6 }}
                  formatter={(v: any, _name: any, props: any) => [`${v > 0 ? '+' : ''}${v.toFixed(2)}% ($${props.payload.price?.toLocaleString()})`, '24h Change']}
                />
                <Bar dataKey="change" radius={[0, 4, 4, 0]}>
                  {movers.map((m: any, i: number) => (
                    <Cell key={i} fill={m.change >= 0 ? COLORS.green : COLORS.red} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Sector Performance (24h)</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={sectorData} margin={{ left: 0, right: 10 }}>
                <XAxis dataKey="name" tick={{ fill: '#d4d4d8', fontSize: 10 }} angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fill: '#71717a', fontSize: 11 }} tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`} />
                <Tooltip
                  contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 6 }}
                  formatter={(v: any) => [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, '24h Avg']}
                />
                <Bar dataKey="change24h" radius={[4, 4, 0, 0]}>
                  {sectorData.map((s: any, i: number) => (
                    <Cell key={i} fill={SECTOR_COLORS[s.name] || COLORS.zinc} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Row 3: 7d Performance */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">7-Day Performance (Top 12)</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={weekChart} margin={{ left: 0, right: 10 }}>
              <XAxis dataKey="name" tick={{ fill: '#d4d4d8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#71717a', fontSize: 11 }} tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`} />
              <Tooltip
                contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 6 }}
                formatter={(v: any) => [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, '7d Change']}
              />
              <Bar dataKey="change" radius={[4, 4, 0, 0]}>
                {weekChart.map((c: any, i: number) => (
                  <Cell key={i} fill={c.change >= 0 ? COLORS.green : COLORS.red} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Row 4: Signals + Anomalies */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {signals.length > 0 && (
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Crypto Signals ({signals.length})</CardTitle></CardHeader>
            <CardContent className="space-y-2 max-h-80 overflow-y-auto">
              {signals.map((sig: any, i: number) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-zinc-900/50">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    sig.direction === 'bullish' ? 'bg-green-900/50 text-green-300' :
                    sig.direction === 'bearish' ? 'bg-red-900/50 text-red-300' :
                    'bg-zinc-800 text-zinc-400'
                  }`}>
                    {sig.direction?.toUpperCase() || 'NEUTRAL'}
                  </span>
                  <div className="text-xs text-zinc-300 flex-1">{sig.description}</div>
                  <div className="text-[10px] text-muted-foreground whitespace-nowrap">
                    str: {((sig.strength || 0) * 100).toFixed(0)}%
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {anomalies.length > 0 && (
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Anomalies ({anomalies.length})</CardTitle></CardHeader>
            <CardContent className="space-y-2 max-h-80 overflow-y-auto">
              {anomalies.map((a: any, i: number) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-zinc-900/50">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    a.severity === 'high' ? 'bg-red-900/50 text-red-300' :
                    a.severity === 'medium' ? 'bg-amber-900/50 text-amber-300' :
                    'bg-zinc-800 text-zinc-400'
                  }`}>
                    {a.severity?.toUpperCase()}
                  </span>
                  <div className="text-xs text-zinc-300 flex-1">{a.description}</div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Row 5: Coin Table */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">All Coins ({coins.length})</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800 text-muted-foreground">
                  <th className="text-left py-2 px-1">#</th>
                  <th className="text-left py-2 px-1">Coin</th>
                  <th className="text-right py-2 px-1">Price</th>
                  <th className="text-right py-2 px-1">1h</th>
                  <th className="text-right py-2 px-1">24h</th>
                  <th className="text-right py-2 px-1">7d</th>
                  <th className="text-right py-2 px-1">30d</th>
                  <th className="text-right py-2 px-1">MCap</th>
                  <th className="text-right py-2 px-1">Vol/MCap</th>
                  <th className="text-right py-2 px-1">ATH %</th>
                </tr>
              </thead>
              <tbody>
                {coins.sort((a: any, b: any) => (a.market_cap_rank || 999) - (b.market_cap_rank || 999)).map((c: any, i: number) => (
                  <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50">
                    <td className="py-1.5 px-1 text-muted-foreground">{c.market_cap_rank || '-'}</td>
                    <td className="py-1.5 px-1 font-medium">{c.symbol} <span className="text-muted-foreground font-normal">{c.name}</span></td>
                    <td className="py-1.5 px-1 text-right font-mono">${c.price?.toLocaleString(undefined, { maximumFractionDigits: c.price < 1 ? 4 : 2 })}</td>
                    <td className={`py-1.5 px-1 text-right ${(c.change_1h_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(c.change_1h_pct || 0) >= 0 ? '+' : ''}{c.change_1h_pct?.toFixed(1)}%
                    </td>
                    <td className={`py-1.5 px-1 text-right ${(c.change_24h_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(c.change_24h_pct || 0) >= 0 ? '+' : ''}{c.change_24h_pct?.toFixed(1)}%
                    </td>
                    <td className={`py-1.5 px-1 text-right ${(c.change_7d_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(c.change_7d_pct || 0) >= 0 ? '+' : ''}{c.change_7d_pct?.toFixed(1)}%
                    </td>
                    <td className={`py-1.5 px-1 text-right ${(c.change_30d_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(c.change_30d_pct || 0) >= 0 ? '+' : ''}{c.change_30d_pct?.toFixed(1)}%
                    </td>
                    <td className="py-1.5 px-1 text-right">{fmtNum(c.market_cap || 0, 1)}</td>
                    <td className="py-1.5 px-1 text-right">{((c.volume_to_mcap || 0) * 100).toFixed(1)}%</td>
                    <td className={`py-1.5 px-1 text-right ${(c.ath_change_pct || 0) > -10 ? 'text-green-400' : 'text-muted-foreground'}`}>
                      {c.ath_change_pct?.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
