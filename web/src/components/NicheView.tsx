import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { NicheMarket, CorrelationData, CircuitBreakerData, RegimeData } from '@/types'

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

interface Props {
  nicheMarkets?: NicheMarket[]
  correlations?: CorrelationData
  circuitBreaker?: CircuitBreakerData
  regime?: RegimeData
}

export function NicheView({ nicheMarkets = [], correlations, circuitBreaker, regime }: Props) {
  return (
    <div className="space-y-4">
      {/* Top row: Regime + Circuit Breaker + Diversification */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {regime && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground">Market Regime</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-lg font-bold">{regime.regime.replace(/_/g, ' ')}</div>
              <div className="text-xs text-muted-foreground mt-1">
                Risk multiplier: {fmt(regime.risk_multiplier)}x
              </div>
              <Progress value={regime.risk_multiplier * 100} className="mt-2 h-1.5" />
            </CardContent>
          </Card>
        )}

        {circuitBreaker && (
          <Card className={circuitBreaker.active ? 'border-red-700' : ''}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground">Circuit Breaker</CardTitle>
            </CardHeader>
            <CardContent>
              <Badge variant={circuitBreaker.active ? 'destructive' : 'default'} className="text-sm">
                {circuitBreaker.active ? 'TRIGGERED' : 'Normal'}
              </Badge>
              <div className="mt-2 space-y-1 text-xs">
                <div className="flex justify-between">
                  <span>Daily P&L</span>
                  <span className={circuitBreaker.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    ${fmt(circuitBreaker.daily_pnl)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Trades/hr</span>
                  <span>{circuitBreaker.trades_this_hour}</span>
                </div>
              </div>
              {circuitBreaker.reason && (
                <div className="text-xs text-red-400 mt-2">{circuitBreaker.reason}</div>
              )}
            </CardContent>
          </Card>
        )}

        {correlations && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground">Diversification</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{correlations.diversification_score}/100</div>
              <Progress value={correlations.diversification_score} className="mt-2 h-1.5" />
              {correlations.warnings.length > 0 && (
                <div className="mt-2 space-y-1">
                  {correlations.warnings.map((w, i) => (
                    <div key={i} className="text-xs text-yellow-400">{w}</div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* High Correlations */}
      {correlations && correlations.high_correlations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">High Correlations (risk of concentrated bets)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {correlations.high_correlations.map((c, i) => (
                <Badge key={i} variant="destructive" className="text-xs">
                  {c.ticker_a} / {c.ticker_b} = {fmt(c.correlation)}
                </Badge>
              ))}
            </div>
            {correlations.suggested_hedges.length > 0 && (
              <div className="mt-3">
                <div className="text-xs text-muted-foreground mb-1">Suggested hedges:</div>
                {correlations.suggested_hedges.map((h, i) => (
                  <Badge key={i} variant="outline" className="text-xs mr-1 mb-1">{h.ticker} ({h.hedge_effectiveness})</Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Niche Markets */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            Niche Market Opportunities ({nicheMarkets.length})
            <span className="text-xs text-muted-foreground ml-2">Low-competition markets where big bots don't operate</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {nicheMarkets.length === 0 ? (
            <div className="text-muted-foreground text-sm">No niche markets found. Run the scanner to discover opportunities.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Question</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead>Volume</TableHead>
                  <TableHead>Spread</TableHead>
                  <TableHead>Expiry</TableHead>
                  <TableHead>Niche Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {nicheMarkets
                  .sort((a, b) => b.niche_score - a.niche_score)
                  .map((m, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium max-w-[300px] truncate">{m.question}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs">{m.category}</Badge>
                      </TableCell>
                      <TableCell>{fmt(m.current_price, 2)}c</TableCell>
                      <TableCell className="text-xs">${m.volume_usd < 1000 ? fmt(m.volume_usd, 0) : `${fmt(m.volume_usd / 1000, 1)}K`}</TableCell>
                      <TableCell>{fmt(m.spread, 1)}c</TableCell>
                      <TableCell className="text-xs">{m.time_to_expiry_days}d</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={m.niche_score * 100} className="h-1.5 w-16" />
                          <span className="text-xs">{fmt(m.niche_score * 100, 0)}%</span>
                        </div>
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
