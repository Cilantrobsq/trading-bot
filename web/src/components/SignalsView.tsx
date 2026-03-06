import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { SignalsData } from '@/types'

export function SignalsView({ data }: { data?: SignalsData }) {
  if (!data) return <div className="text-muted-foreground text-sm">No signal data yet.</div>

  const grouped = data.signals.reduce<Record<string, typeof data.signals>>((acc, s) => {
    const theme = s.theme || 'Other'
    if (!acc[theme]) acc[theme] = []
    acc[theme].push(s)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      {data.last_updated && (
        <div className="text-xs text-muted-foreground">
          Last scan: {new Date(data.last_updated).toLocaleString()}
        </div>
      )}

      {Object.entries(grouped).map(([theme, signals]) => (
        <Card key={theme}>
          <CardHeader>
            <CardTitle className="text-sm">{theme}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Signal</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Threshold</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Direction</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {signals.map((s, i) => {
                  const isAlert = s.value != null && s.threshold != null && s.value >= s.threshold
                  return (
                    <TableRow key={i} className={isAlert ? 'bg-destructive/10' : ''}>
                      <TableCell className="font-medium">{s.name}</TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">{s.ticker}</TableCell>
                      <TableCell className={isAlert ? 'text-red-400 font-bold' : ''}>
                        {s.value != null ? s.value.toFixed(2) : '-'}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {s.threshold !== null ? s.threshold : '-'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={s.status === 'alert' ? 'destructive' : s.status === 'normal' ? 'default' : 'secondary'}>
                          {s.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
                        {s.direction}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
