import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { BrainData, KillSwitchStatus } from '@/types'

const REGIME_COLORS: Record<string, string> = {
  BULL_QUIET: 'bg-green-500/20 text-green-400',
  BULL_VOLATILE: 'bg-yellow-500/20 text-yellow-400',
  BEAR_QUIET: 'bg-orange-500/20 text-orange-400',
  BEAR_VOLATILE: 'bg-red-500/20 text-red-400',
  SIDEWAYS: 'bg-zinc-500/20 text-zinc-400',
  CRISIS: 'bg-red-700/30 text-red-300',
  unknown: 'bg-zinc-500/20 text-zinc-400',
}

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

interface Props {
  data?: BrainData
  killSwitch?: KillSwitchStatus
  onToggleKillSwitch?: (active: boolean, reason: string) => void
}

export function BrainView({ data, killSwitch, onToggleKillSwitch }: Props) {
  if (!data) return <div className="text-muted-foreground text-sm">No brain state data yet. Run the bot to generate state.</div>

  const sentimentColor = data.overall_sentiment >= 0.2 ? 'text-green-400' : data.overall_sentiment <= -0.2 ? 'text-red-400' : 'text-zinc-400'
  const sentimentLabel = data.overall_sentiment >= 0.3 ? 'Bullish' : data.overall_sentiment <= -0.3 ? 'Bearish' : 'Neutral'

  return (
    <div className="space-y-4">
      {/* Kill Switch Banner */}
      {killSwitch?.active && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg p-4 flex items-center justify-between">
          <div>
            <span className="text-red-300 font-bold text-lg">KILL SWITCH ACTIVE</span>
            {killSwitch.reason && <span className="text-red-400 ml-3 text-sm">{killSwitch.reason}</span>}
          </div>
          {onToggleKillSwitch && (
            <button
              onClick={() => onToggleKillSwitch(false, '')}
              className="px-4 py-2 bg-green-700 text-white rounded hover:bg-green-600 text-sm"
            >
              Deactivate
            </button>
          )}
        </div>
      )}

      {/* Top Cards: Regime + Sentiment + Risk */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Market Regime</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-xl font-bold px-3 py-1 rounded inline-block ${REGIME_COLORS[data.market_regime] || REGIME_COLORS.unknown}`}>
              {data.market_regime.replace(/_/g, ' ')}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              Confidence: {data.regime_confidence}%
            </div>
            <Progress value={data.regime_confidence} className="mt-1 h-1.5" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Overall Sentiment</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${sentimentColor}`}>
              {data.overall_sentiment >= 0 ? '+' : ''}{fmt(data.overall_sentiment)}
            </div>
            <div className="text-xs text-muted-foreground mt-1">{sentimentLabel}</div>
            <div className="mt-2 w-full bg-zinc-800 rounded-full h-2 relative">
              <div
                className="absolute top-0 h-2 rounded-full bg-gradient-to-r from-red-500 via-zinc-500 to-green-500"
                style={{ width: '100%' }}
              />
              <div
                className="absolute top-[-2px] w-3 h-3 bg-white rounded-full border-2 border-zinc-900"
                style={{ left: `${((data.overall_sentiment + 1) / 2) * 100}%`, transform: 'translateX(-50%)' }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Risk State</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Daily P&L</span>
                <span className={data.risk_state.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {data.risk_state.daily_pnl >= 0 ? '+' : ''}${fmt(data.risk_state.daily_pnl)}
                  ({fmt(data.risk_state.daily_pnl_pct)}%)
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Exposure</span>
                <span>{fmt(data.risk_state.exposure_pct)}%</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Max Daily Loss</span>
                <span className="text-muted-foreground">{fmt(data.risk_state.max_daily_loss_pct)}%</span>
              </div>
              {data.risk_state.circuit_breaker_active && (
                <Badge variant="destructive" className="mt-1">Circuit Breaker Active</Badge>
              )}
              {data.risk_state.correlation_warning && (
                <Badge variant="destructive" className="mt-1">Correlation Warning</Badge>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Kill Switch Button (when not active) */}
      {!killSwitch?.active && onToggleKillSwitch && (
        <div className="flex justify-end">
          <button
            onClick={() => {
              const reason = prompt('Reason for activating kill switch:')
              if (reason !== null) onToggleKillSwitch(true, reason || 'Manual activation')
            }}
            className="px-4 py-2 bg-red-800 text-red-200 rounded hover:bg-red-700 text-sm border border-red-700"
          >
            Activate Kill Switch
          </button>
        </div>
      )}

      {/* Theme Assessments */}
      {data.active_themes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Theme Conviction</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {data.active_themes.map((t) => (
                <div key={t.theme_id} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{t.theme_id}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-green-400 text-xs">{t.signals_supporting} supporting</span>
                      <span className="text-red-400 text-xs">{t.signals_against} against</span>
                      <span className="font-mono">{t.conviction}%</span>
                    </div>
                  </div>
                  <Progress value={t.conviction} className="h-1.5" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Planned Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Planned Actions ({data.planned_actions.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {data.planned_actions.length === 0 ? (
            <div className="text-muted-foreground text-sm">No planned actions. Bot is observing.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Priority</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Market</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Reasoning</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.planned_actions
                  .sort((a, b) => a.priority - b.priority)
                  .map((a, i) => (
                    <TableRow key={i}>
                      <TableCell>
                        <Badge variant={a.priority <= 2 ? 'destructive' : a.priority <= 5 ? 'default' : 'secondary'}>
                          P{a.priority}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium">{a.action_type}</TableCell>
                      <TableCell className="max-w-[200px] truncate">{a.market}</TableCell>
                      <TableCell>
                        <Badge variant={a.direction.includes('BUY') ? 'default' : 'secondary'}>
                          {a.direction}
                        </Badge>
                      </TableCell>
                      <TableCell>{fmt(a.size_pct)}%</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[300px] truncate">
                        {a.reasoning}
                      </TableCell>
                      <TableCell>
                        {a.blocked_by ? (
                          <Badge variant="destructive">Blocked: {a.blocked_by}</Badge>
                        ) : (
                          <Badge variant="default">Ready</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
