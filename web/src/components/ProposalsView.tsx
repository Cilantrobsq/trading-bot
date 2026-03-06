import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, ReferenceLine
} from 'recharts'
import type { TradeProposal } from '@/types'

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function formatCountdown(totalSeconds: number): string {
  if (totalSeconds <= 0) return 'EXPIRED'
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function categoryLabel(cat: string): string {
  const labels: Record<string, string> = {
    momentum: 'Momentum',
    macro: 'Macro',
    mean_reversion: 'Mean Reversion',
    timezone_arb: 'TZ Arbitrage',
    correlation_arb: 'Correlation Arb',
    thesis: 'Thesis',
  }
  return labels[cat] || cat
}

function categoryColor(cat: string): string {
  const colors: Record<string, string> = {
    momentum: 'bg-blue-900/50 text-blue-300',
    macro: 'bg-purple-900/50 text-purple-300',
    mean_reversion: 'bg-amber-900/50 text-amber-300',
    timezone_arb: 'bg-cyan-900/50 text-cyan-300',
    correlation_arb: 'bg-pink-900/50 text-pink-300',
    thesis: 'bg-green-900/50 text-green-300',
  }
  return colors[cat] || 'bg-zinc-800 text-zinc-300'
}

function ProposalCard({ proposal, countdown }: { proposal: TradeProposal; countdown: number }) {
  const isLong = proposal.direction === 'long'
  const pctToTarget = isLong
    ? ((proposal.target_price - proposal.entry_price) / proposal.entry_price * 100)
    : ((proposal.entry_price - proposal.target_price) / proposal.entry_price * 100)
  const pctToStop = isLong
    ? ((proposal.entry_price - proposal.stop_price) / proposal.entry_price * 100)
    : ((proposal.stop_price - proposal.entry_price) / proposal.entry_price * 100)

  // R:R visual bar data
  const rrData = [
    { name: 'Risk', value: -pctToStop, fill: '#ef4444' },
    { name: 'Reward', value: pctToTarget, fill: '#22c55e' },
  ]

  const timerPct = proposal.seconds_remaining > 0
    ? Math.min(100, (countdown / proposal.seconds_remaining) * 100)
    : 0
  const isUrgent = countdown < 1800 && countdown > 0 // less than 30 min

  return (
    <Card className={`border ${proposal.urgency === 'high' ? 'border-red-700/50' : 'border-border'} relative overflow-hidden`}>
      {/* Timer bar at top */}
      <div className="h-1 w-full bg-zinc-800">
        <div
          className={`h-full transition-all duration-1000 ${isUrgent ? 'bg-red-500 animate-pulse' : countdown > 7200 ? 'bg-green-500' : 'bg-amber-500'}`}
          style={{ width: `${timerPct}%` }}
        />
      </div>

      <CardHeader className="pb-2 pt-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono font-bold text-sm">{proposal.ticker}</span>
              <Badge variant={isLong ? 'default' : 'secondary'} className="text-xs">
                {isLong ? 'LONG' : 'SHORT'}
              </Badge>
              <Badge className={`text-xs ${categoryColor(proposal.category)}`}>
                {categoryLabel(proposal.category)}
              </Badge>
              {proposal.urgency === 'high' && (
                <Badge className="text-xs bg-red-900/50 text-red-300">URGENT</Badge>
              )}
            </div>
            <div className="text-xs text-muted-foreground mt-1 truncate">{proposal.name}</div>
          </div>
          <div className="text-right shrink-0">
            <div className={`font-mono text-sm font-bold ${isUrgent ? 'text-red-400' : 'text-muted-foreground'}`}>
              {formatCountdown(countdown)}
            </div>
            <div className="text-xs text-muted-foreground">remaining</div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3 pt-0">
        {/* Price levels */}
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-red-950/30 rounded p-2">
            <div className="text-xs text-red-400">Stop Loss</div>
            <div className="font-mono text-sm font-bold text-red-300">${fmt(proposal.stop_price, 2)}</div>
            <div className="text-xs text-red-400/70">-{fmt(pctToStop, 1)}%</div>
          </div>
          <div className="bg-zinc-800/50 rounded p-2 ring-1 ring-zinc-600">
            <div className="text-xs text-zinc-400">Entry</div>
            <div className="font-mono text-sm font-bold">${fmt(proposal.entry_price, 2)}</div>
            <div className="text-xs text-zinc-500">now</div>
          </div>
          <div className="bg-green-950/30 rounded p-2">
            <div className="text-xs text-green-400">Target</div>
            <div className="font-mono text-sm font-bold text-green-300">${fmt(proposal.target_price, 2)}</div>
            <div className="text-xs text-green-400/70">+{fmt(pctToTarget, 1)}%</div>
          </div>
        </div>

        {/* R:R visual bar */}
        <div className="h-10">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rrData} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 50 }}>
              <XAxis type="number" hide domain={[-Math.max(pctToStop, pctToTarget) * 1.1, Math.max(pctToStop, pctToTarget) * 1.1]} />
              <YAxis type="category" dataKey="name" width={45} tick={{ fontSize: 10, fill: '#a1a1aa' }} />
              <ReferenceLine x={0} stroke="#52525b" />
              <Bar dataKey="value" radius={[2, 2, 2, 2]}>
                {rrData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Key metrics row */}
        <div className="grid grid-cols-4 gap-1.5 text-center text-xs">
          <div className="bg-zinc-800/50 rounded px-2 py-1.5">
            <div className="text-muted-foreground">R:R</div>
            <div className={`font-bold font-mono ${proposal.risk_reward >= 3 ? 'text-green-400' : proposal.risk_reward >= 2 ? 'text-amber-400' : 'text-zinc-300'}`}>
              {fmt(proposal.risk_reward, 1)}:1
            </div>
          </div>
          <div className="bg-zinc-800/50 rounded px-2 py-1.5">
            <div className="text-muted-foreground">Confidence</div>
            <div className="font-bold font-mono">{proposal.confidence}%</div>
          </div>
          <div className="bg-zinc-800/50 rounded px-2 py-1.5">
            <div className="text-muted-foreground">Size</div>
            <div className="font-bold font-mono">${fmt(proposal.position_size_usd, 0)}</div>
          </div>
          <div className="bg-zinc-800/50 rounded px-2 py-1.5">
            <div className="text-muted-foreground">Max Loss</div>
            <div className="font-bold font-mono text-red-400">-${fmt(proposal.max_loss_usd, 0)}</div>
          </div>
        </div>

        {/* Confidence bar */}
        <div className="space-y-1">
          <Progress value={proposal.confidence} className="h-1.5" />
        </div>

        {/* Reasoning */}
        <div className="text-xs text-muted-foreground leading-relaxed">
          {proposal.reasoning}
        </div>

        {/* Supporting / Opposing signals */}
        {(proposal.supporting_signals.length > 0 || proposal.opposing_signals.length > 0) && (
          <div className="grid grid-cols-2 gap-2 text-xs">
            {proposal.supporting_signals.length > 0 && (
              <div>
                <div className="text-green-400/70 mb-1">Supporting</div>
                {proposal.supporting_signals.map((s, i) => (
                  <div key={i} className="text-muted-foreground truncate">+ {s}</div>
                ))}
              </div>
            )}
            {proposal.opposing_signals.length > 0 && (
              <div>
                <div className="text-red-400/70 mb-1">Risks</div>
                {proposal.opposing_signals.map((s, i) => (
                  <div key={i} className="text-muted-foreground truncate">- {s}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}


export function ProposalsView({ proposals }: { proposals?: TradeProposal[] }) {
  const [countdowns, setCountdowns] = useState<Record<string, number>>({})

  // Initialize countdowns from proposal data
  useEffect(() => {
    if (!proposals) return
    const initial: Record<string, number> = {}
    for (const p of proposals) {
      initial[p.id] = p.seconds_remaining
    }
    setCountdowns(initial)
  }, [proposals])

  // Tick every second
  useEffect(() => {
    const interval = setInterval(() => {
      setCountdowns(prev => {
        const next = { ...prev }
        for (const id of Object.keys(next)) {
          if (next[id] > 0) next[id]--
        }
        return next
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  if (!proposals || proposals.length === 0) {
    return (
      <div className="py-12 text-center space-y-3">
        <div className="text-4xl">📋</div>
        <div className="text-muted-foreground text-sm">No active trade proposals.</div>
        <div className="text-muted-foreground text-xs max-w-md mx-auto">
          The bot generates proposals every 30 minutes by analyzing signals from
          yfinance, FRED, global markets, timezone arbitrage, correlations, and active theses.
          Proposals require a minimum 1.5:1 risk/reward ratio.
        </div>
      </div>
    )
  }

  // Summary stats
  const totalProposals = proposals.length
  const longCount = proposals.filter(p => p.direction === 'long').length
  const shortCount = proposals.filter(p => p.direction === 'short').length
  const avgRR = proposals.reduce((sum, p) => sum + p.risk_reward, 0) / totalProposals
  const avgConf = proposals.reduce((sum, p) => sum + p.confidence, 0) / totalProposals
  const highUrgency = proposals.filter(p => p.urgency === 'high').length
  const categories = [...new Set(proposals.map(p => p.category))]
  const totalExposure = proposals.reduce((sum, p) => sum + p.position_size_usd, 0)

  // Category distribution for chart
  const catData = categories.map(cat => ({
    name: categoryLabel(cat),
    count: proposals.filter(p => p.category === cat).length,
    fill: {
      momentum: '#3b82f6',
      macro: '#a855f7',
      mean_reversion: '#f59e0b',
      timezone_arb: '#06b6d4',
      correlation_arb: '#ec4899',
      thesis: '#22c55e',
    }[cat] || '#71717a',
  }))

  // R:R distribution for chart
  const rrBuckets = [
    { range: '1.5-2x', min: 1.5, max: 2 },
    { range: '2-3x', min: 2, max: 3 },
    { range: '3-5x', min: 3, max: 5 },
    { range: '5x+', min: 5, max: 100 },
  ]
  const rrData = rrBuckets.map(b => ({
    name: b.range,
    count: proposals.filter(p => p.risk_reward >= b.min && p.risk_reward < b.max).length,
  }))

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
        <Card className="p-3 text-center">
          <div className="text-xs text-muted-foreground">Active</div>
          <div className="text-xl font-bold font-mono">{totalProposals}</div>
        </Card>
        <Card className="p-3 text-center">
          <div className="text-xs text-muted-foreground">Long / Short</div>
          <div className="text-sm font-bold font-mono">
            <span className="text-green-400">{longCount}</span>
            {' / '}
            <span className="text-red-400">{shortCount}</span>
          </div>
        </Card>
        <Card className="p-3 text-center">
          <div className="text-xs text-muted-foreground">Avg R:R</div>
          <div className={`text-xl font-bold font-mono ${avgRR >= 3 ? 'text-green-400' : avgRR >= 2 ? 'text-amber-400' : ''}`}>
            {fmt(avgRR, 1)}:1
          </div>
        </Card>
        <Card className="p-3 text-center">
          <div className="text-xs text-muted-foreground">Avg Confidence</div>
          <div className="text-xl font-bold font-mono">{fmt(avgConf, 0)}%</div>
        </Card>
        <Card className="p-3 text-center">
          <div className="text-xs text-muted-foreground">Urgent</div>
          <div className={`text-xl font-bold font-mono ${highUrgency > 0 ? 'text-red-400' : ''}`}>
            {highUrgency}
          </div>
        </Card>
        <Card className="p-3 text-center">
          <div className="text-xs text-muted-foreground">Categories</div>
          <div className="text-xl font-bold font-mono">{categories.length}</div>
        </Card>
        <Card className="p-3 text-center">
          <div className="text-xs text-muted-foreground">Total Size</div>
          <div className="text-sm font-bold font-mono">${fmt(totalExposure, 0)}</div>
        </Card>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">By Category</CardTitle>
          </CardHeader>
          <CardContent className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={catData} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#a1a1aa' }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: '#a1a1aa' }} width={20} />
                <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                  {catData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Risk/Reward Distribution</CardTitle>
          </CardHeader>
          <CardContent className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rrData} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#a1a1aa' }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: '#a1a1aa' }} width={20} />
                <Bar dataKey="count" fill="#22c55e" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Proposal cards grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {proposals
          .sort((a, b) => {
            // Urgent first, then by confidence, then by R:R
            if (a.urgency === 'high' && b.urgency !== 'high') return -1
            if (b.urgency === 'high' && a.urgency !== 'high') return 1
            if (b.confidence !== a.confidence) return b.confidence - a.confidence
            return b.risk_reward - a.risk_reward
          })
          .map(p => (
            <ProposalCard
              key={p.id}
              proposal={p}
              countdown={countdowns[p.id] ?? p.seconds_remaining}
            />
          ))
        }
      </div>
    </div>
  )
}
