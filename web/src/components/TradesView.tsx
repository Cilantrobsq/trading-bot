import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { TradesData } from '@/types'

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function TradesView({ data }: { data?: TradesData }) {
  if (!data) return <div className="text-muted-foreground text-sm">No trade data yet.</div>

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Trade History ({data.count} trades)</CardTitle>
      </CardHeader>
      <CardContent>
        {data.trades.length === 0 ? (
          <div className="text-muted-foreground text-sm">No trades recorded yet. Paper trading is active.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Market</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Side</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Qty</TableHead>
                <TableHead>P&L</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.trades.map((t, i) => (
                <TableRow key={i}>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {t.timestamp ? new Date(t.timestamp).toLocaleString() : '-'}
                  </TableCell>
                  <TableCell className="font-medium">{t.market}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{t.type || 'paper'}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={t.side === 'BUY' || t.side === 'YES' ? 'default' : 'secondary'}>
                      {t.side}
                    </Badge>
                  </TableCell>
                  <TableCell>${fmt(t.price, 4)}</TableCell>
                  <TableCell>{fmt(t.quantity, 0)}</TableCell>
                  <TableCell className={t.pnl !== undefined ? (t.pnl >= 0 ? 'text-green-400' : 'text-red-400') : ''}>
                    {t.pnl !== undefined ? `${t.pnl >= 0 ? '+' : ''}$${fmt(t.pnl)}` : '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
