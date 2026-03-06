import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { PortfolioData } from '@/types'

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function PortfolioView({ data }: { data?: PortfolioData }) {
  if (!data) return <div className="text-muted-foreground text-sm">No portfolio data yet.</div>

  const pnlColor = data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Balance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${fmt(data.balance)}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Initial Capital</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${fmt(data.initial_balance)}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Total P&L</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${pnlColor}`}>
              {data.total_pnl >= 0 ? '+' : ''}${fmt(data.total_pnl)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">P&L %</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${pnlColor}`}>
              {data.total_pnl_pct >= 0 ? '+' : ''}{fmt(data.total_pnl_pct)}%
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Open Positions ({data.positions.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {data.positions.length === 0 ? (
            <div className="text-muted-foreground text-sm">No open positions.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Market</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Entry</TableHead>
                  <TableHead>Current</TableHead>
                  <TableHead>Qty</TableHead>
                  <TableHead>P&L</TableHead>
                  <TableHead>Theme</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.positions.map((p, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium">{p.market_name || p.market_id}</TableCell>
                    <TableCell>
                      <Badge variant={p.side === 'YES' ? 'default' : 'secondary'}>{p.side}</Badge>
                    </TableCell>
                    <TableCell>${fmt(p.entry_price, 4)}</TableCell>
                    <TableCell>${fmt(p.current_price, 4)}</TableCell>
                    <TableCell>{fmt(p.quantity, 0)}</TableCell>
                    <TableCell className={p.unrealized_pnl && p.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                      {p.unrealized_pnl !== undefined ? `${p.unrealized_pnl >= 0 ? '+' : ''}$${fmt(p.unrealized_pnl)}` : '-'}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">{p.theme_id}</TableCell>
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
