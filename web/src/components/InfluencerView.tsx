import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts'

interface InfluencerViewProps {
  data: any
}

const COLORS = {
  green: '#22c55e',
  red: '#ef4444',
  amber: '#f59e0b',
  blue: '#3b82f6',
  purple: '#a855f7',
  zinc: '#71717a',
}

const CATEGORY_COLORS: Record<string, string> = {
  'central_bankers': '#3b82f6',
  'macro_investors': '#22c55e',
  'crypto_leaders': '#f59e0b',
  'tech_vc': '#a855f7',
  'political': '#ef4444',
}

const CATEGORY_LABELS: Record<string, string> = {
  'central_bankers': 'Central Bankers',
  'macro_investors': 'Macro Investors',
  'crypto_leaders': 'Crypto Leaders',
  'tech_vc': 'Tech / VC',
  'political': 'Political',
}

export function InfluencerView({ data }: InfluencerViewProps) {
  if (!data) {
    return (
      <Card><CardContent className="py-8 text-center text-muted-foreground">
        No influencer data yet. Run the bot to scan key figure activity.
      </CardContent></Card>
    )
  }

  const mentions = data.mentions || []
  const signals = data.signals || []
  const summary = data.summary || {}
  const categories = summary.categories || {}
  const topFigures = summary.top_figures || []
  const sentimentBalance = summary.sentiment_balance || {}

  // Category distribution chart
  const catData = Object.entries(categories).map(([key, val]: [string, any]) => ({
    name: CATEGORY_LABELS[key] || key,
    count: val.count || 0,
    bullish: val.bullish || 0,
    bearish: val.bearish || 0,
    neutral: val.neutral || 0,
    color: CATEGORY_COLORS[key] || COLORS.zinc,
  }))

  // Top figures chart
  const figureData = topFigures.slice(0, 10).map((f: any) => {
    // Find this figure's sentiment from mentions
    const figureMentions = mentions.filter((m: any) => m.figure_name === f.name)
    const bullish = figureMentions.filter((m: any) => m.sentiment === 'bullish').length
    const bearish = figureMentions.filter((m: any) => m.sentiment === 'bearish').length
    return {
      name: f.name.split(' ').pop(),
      fullName: f.name,
      mentions: f.mentions,
      bullish,
      bearish,
      neutral: f.mentions - bullish - bearish,
    }
  })

  // Sentiment pie
  const sentPie = [
    { name: 'Bullish', value: sentimentBalance.bullish || 0, color: COLORS.green },
    { name: 'Bearish', value: sentimentBalance.bearish || 0, color: COLORS.red },
    { name: 'Neutral', value: sentimentBalance.neutral || 0, color: COLORS.zinc },
  ]

  // (catSentiment reserved for future stacked chart)

  return (
    <div className="space-y-4">
      {/* Row 1: Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card>
          <CardHeader className="pb-1 pt-3 px-3"><CardTitle className="text-xs text-muted-foreground">Total Mentions</CardTitle></CardHeader>
          <CardContent className="pb-3 px-3">
            <div className="text-2xl font-bold">{summary.total || 0}</div>
            <div className="text-sm text-muted-foreground">{data.feeds_scanned || 0} feeds scanned</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 pt-3 px-3"><CardTitle className="text-xs text-muted-foreground">Sentiment</CardTitle></CardHeader>
          <CardContent className="pb-3 px-3">
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-bold text-green-400">{sentimentBalance.bullish || 0}</span>
              <span className="text-muted-foreground">/</span>
              <span className="text-lg font-bold text-red-400">{sentimentBalance.bearish || 0}</span>
            </div>
            <div className="text-sm text-muted-foreground">
              Bull/Bear ratio: {sentimentBalance.ratio?.toFixed(2) || '?'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 pt-3 px-3"><CardTitle className="text-xs text-muted-foreground">Trading Signals</CardTitle></CardHeader>
          <CardContent className="pb-3 px-3">
            <div className="text-2xl font-bold">{signals.length}</div>
            <div className="text-sm text-muted-foreground">from key figure activity</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1 pt-3 px-3"><CardTitle className="text-xs text-muted-foreground">Most Active</CardTitle></CardHeader>
          <CardContent className="pb-3 px-3">
            <div className="text-lg font-bold">{topFigures[0]?.name || 'N/A'}</div>
            <div className="text-sm text-muted-foreground">{topFigures[0]?.mentions || 0} mentions</div>
          </CardContent>
        </Card>
      </div>

      {/* Row 2: Top Figures + Sentiment Distribution */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Top Mentioned Figures</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={figureData} layout="vertical" margin={{ left: 10, right: 10 }}>
                <XAxis type="number" tick={{ fill: '#71717a', fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fill: '#d4d4d8', fontSize: 11 }} width={90} />
                <Tooltip
                  contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 6 }}
                  formatter={(v: any, name: any) => [v, name]}
                  labelFormatter={(label: any, payload: any) => payload?.[0]?.payload?.fullName || label}
                />
                <Bar dataKey="bullish" stackId="s" fill={COLORS.green} name="Bullish" />
                <Bar dataKey="neutral" stackId="s" fill={COLORS.zinc} name="Neutral" />
                <Bar dataKey="bearish" stackId="s" fill={COLORS.red} name="Bearish" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Category Breakdown</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <ResponsiveContainer width="50%" height={280}>
                <PieChart>
                  <Pie
                    data={sentPie}
                    cx="50%" cy="50%"
                    innerRadius={55} outerRadius={85}
                    paddingAngle={3}
                    dataKey="value"
                    label={({ name, value }: any) => value > 0 ? `${name}: ${value}` : ''}
                    labelLine={false}
                  >
                    {sentPie.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 6 }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2">
                {catData.map((cat, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ background: cat.color }} />
                    <div className="text-xs flex-1">{cat.name}</div>
                    <div className="text-xs font-mono text-muted-foreground">{cat.count}</div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Row 3: Signals */}
      {signals.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Influencer Trading Signals ({signals.length})</CardTitle></CardHeader>
          <CardContent className="space-y-2 max-h-96 overflow-y-auto">
            {signals.map((sig: any, i: number) => (
              <div key={i} className="flex items-start gap-2 p-2 rounded bg-zinc-900/50">
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${
                  sig.direction === 'bullish' ? 'bg-green-900/50 text-green-300' :
                  sig.direction === 'bearish' ? 'bg-red-900/50 text-red-300' :
                  'bg-zinc-800 text-zinc-400'
                }`}>
                  {sig.direction?.toUpperCase() || '?'}
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

      {/* Row 4: Recent Mentions */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Recent Mentions (Top 50)</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-1.5 max-h-96 overflow-y-auto">
            {mentions.slice(0, 50).map((m: any, i: number) => (
              <div key={i} className="flex items-start gap-2 py-1.5 border-b border-zinc-800/50">
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${
                  m.sentiment === 'bullish' ? 'bg-green-900/50 text-green-300' :
                  m.sentiment === 'bearish' ? 'bg-red-900/50 text-red-300' :
                  'bg-zinc-800 text-zinc-400'
                }`}>
                  {m.sentiment === 'bullish' ? '+' : m.sentiment === 'bearish' ? '-' : '='}
                </span>
                <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-300 shrink-0">
                  {m.figure_name}
                </span>
                <a
                  href={m.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-zinc-300 hover:text-blue-400 flex-1 line-clamp-1"
                >
                  {m.title}
                </a>
                <span className="text-[10px] text-muted-foreground shrink-0">
                  w:{m.weight}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
