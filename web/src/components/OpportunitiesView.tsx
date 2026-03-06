import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { OpportunitiesData } from '@/types'

export function OpportunitiesView({ data }: { data?: OpportunitiesData }) {
  if (!data) return <div className="text-muted-foreground text-sm">No opportunity data yet.</div>

  return (
    <div className="space-y-4">
      {data.last_updated && (
        <div className="text-xs text-muted-foreground">
          Last scan: {new Date(data.last_updated).toLocaleString()}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Active Opportunities ({data.opportunities.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {data.opportunities.length === 0 ? (
            <div className="text-muted-foreground text-sm">No opportunities detected. Scanner runs periodically.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Market</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Market Price</TableHead>
                  <TableHead>Model Price</TableHead>
                  <TableHead>Spread</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Theme</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.opportunities.map((o, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium">{o.market}</TableCell>
                    <TableCell>
                      <Badge variant={o.direction === 'BUY' ? 'default' : 'secondary'}>
                        {o.direction}
                      </Badge>
                    </TableCell>
                    <TableCell>${o.market_price?.toFixed(4)}</TableCell>
                    <TableCell>${o.model_price?.toFixed(4)}</TableCell>
                    <TableCell className="text-green-400 font-bold">{o.spread_pct?.toFixed(2)}%</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-2 rounded bg-muted overflow-hidden">
                          <div
                            className="h-full bg-primary rounded"
                            style={{ width: `${(o.confidence || 0) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs">{((o.confidence || 0) * 100).toFixed(0)}%</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{o.theme}</TableCell>
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
