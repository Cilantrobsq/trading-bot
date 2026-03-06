import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import type { ConfigData } from '@/types'

export function ConfigView({ data }: { data?: ConfigData }) {
  if (!data) return <div className="text-muted-foreground text-sm">No config data yet.</div>

  const strategy = data.strategy as Record<string, unknown>
  const themes = data.themes as Record<string, unknown>
  const risk = strategy?.risk_management as Record<string, unknown> | undefined
  const paper = strategy?.paper_trading as Record<string, unknown> | undefined
  const themeList = (themes?.themes || []) as Array<Record<string, unknown>>

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Risk Management</CardTitle>
        </CardHeader>
        <CardContent>
          {risk ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {Object.entries(risk).map(([key, val]) => (
                <div key={key} className="flex flex-col">
                  <span className="text-xs text-muted-foreground">{key.replace(/_/g, ' ')}</span>
                  <span className="font-mono text-sm">{String(val)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-muted-foreground text-sm">No risk config.</div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Paper Trading</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4 items-center">
            <Badge variant={paper?.enabled ? 'default' : 'secondary'}>
              {paper?.enabled ? 'ACTIVE' : 'DISABLED'}
            </Badge>
            <span className="text-sm">
              Initial balance: ${Number(paper?.initial_balance_usd || 10000).toLocaleString()}
            </span>
          </div>
        </CardContent>
      </Card>

      <Separator />

      <h2 className="text-lg font-semibold">Themes ({themeList.length})</h2>
      {themeList.map((theme, i) => (
        <Card key={i}>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle className="text-sm">{theme.name as string}</CardTitle>
              <Badge variant={theme.status === 'active' ? 'default' : 'secondary'}>
                {theme.status as string}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground mb-3">{theme.description as string}</p>
            {theme.equities != null && (
              <div className="space-y-2">
                {Object.entries(theme.equities as Record<string, Array<Record<string, unknown>>>).map(([group, tickers]) => (
                  <div key={group}>
                    <span className="text-xs font-medium text-muted-foreground">{group.replace(/_/g, ' ')}: </span>
                    <span className="text-xs font-mono">
                      {tickers.map(t => t.ticker as string).join(', ')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
