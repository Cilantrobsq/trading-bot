import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { DecisionEntry } from '@/types'

const TYPE_COLORS: Record<string, string> = {
  signal_eval: 'bg-blue-500/20 text-blue-400',
  position_size: 'bg-purple-500/20 text-purple-400',
  trade: 'bg-green-500/20 text-green-400',
  risk_check: 'bg-orange-500/20 text-orange-400',
  override: 'bg-yellow-500/20 text-yellow-400',
  thesis_update: 'bg-cyan-500/20 text-cyan-400',
}

export function DecisionsView({ data = [] }: { data?: DecisionEntry[] }) {
  if (!data || data.length === 0) {
    return <div className="text-muted-foreground text-sm">No decision log entries yet. The bot logs every decision it makes here.</div>
  }

  const typeCounts = data.reduce<Record<string, number>>((acc, d) => {
    acc[d.decision_type] = (acc[d.decision_type] || 0) + 1
    return acc
  }, {})

  const avgConfidence = data.length > 0
    ? Math.round(data.reduce((sum, d) => sum + d.confidence, 0) / data.length)
    : 0

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Total Decisions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Avg Confidence</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{avgConfidence}%</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Trades Executed</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{typeCounts['trade'] || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Risk Checks</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{typeCounts['risk_check'] || 0}</div>
          </CardContent>
        </Card>
      </div>

      {/* Decision Log Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Decision Audit Trail (newest first)</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Reasoning</TableHead>
                <TableHead>Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data
                .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
                .slice(0, 50)
                .map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(d.timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <Badge className={TYPE_COLORS[d.decision_type] || 'bg-zinc-500/20 text-zinc-400'}>
                        {d.decision_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className={d.confidence >= 70 ? 'text-green-400' : d.confidence >= 40 ? 'text-yellow-400' : 'text-red-400'}>
                        {d.confidence}%
                      </span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[400px]">
                      <details>
                        <summary className="cursor-pointer truncate">{d.reasoning.slice(0, 80)}{d.reasoning.length > 80 ? '...' : ''}</summary>
                        <div className="mt-2 whitespace-pre-wrap text-xs bg-zinc-900 p-2 rounded">{d.reasoning}</div>
                      </details>
                    </TableCell>
                    <TableCell className="text-xs">
                      {d.action_taken || <span className="text-muted-foreground">No action</span>}
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
