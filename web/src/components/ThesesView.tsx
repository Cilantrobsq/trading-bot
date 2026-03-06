import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Thesis, SignalOverride } from '@/types'

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-500/20 text-green-400',
  invalidated: 'bg-red-500/20 text-red-400',
  expired: 'bg-zinc-500/20 text-zinc-400',
  realized: 'bg-blue-500/20 text-blue-400',
}

const DIRECTION_COLORS: Record<string, string> = {
  bullish: 'text-green-400',
  bearish: 'text-red-400',
  neutral: 'text-zinc-400',
}

interface Props {
  theses?: Thesis[]
  overrides?: SignalOverride[]
  apiBase: string
  onRefresh: () => void
}

export function ThesesView({ theses = [], overrides = [], apiBase, onRefresh }: Props) {
  const [showNewThesis, setShowNewThesis] = useState(false)
  const [showNewOverride, setShowNewOverride] = useState(false)
  const [form, setForm] = useState({
    title: '', direction: 'bullish', confidence: '70', reasoning: '',
    catalysts: '', invalidation_conditions: '', time_horizon: '30',
    affected_tickers: '', affected_themes: ''
  })
  const [overrideForm, setOverrideForm] = useState({
    signal_type: '', ticker_or_market: '', override_type: 'boost',
    strength: '1.5', reason: ''
  })

  const createThesis = async () => {
    if (!apiBase) return
    await fetch(`${apiBase}/api/theses`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: form.title,
        direction: form.direction,
        confidence: parseInt(form.confidence),
        reasoning: form.reasoning,
        catalysts: form.catalysts.split(',').map(s => s.trim()).filter(Boolean),
        invalidation_conditions: form.invalidation_conditions.split(',').map(s => s.trim()).filter(Boolean),
        time_horizon: parseInt(form.time_horizon),
        affected_tickers: form.affected_tickers.split(',').map(s => s.trim()).filter(Boolean),
        affected_themes: form.affected_themes.split(',').map(s => s.trim()).filter(Boolean),
      })
    })
    setShowNewThesis(false)
    setForm({ title: '', direction: 'bullish', confidence: '70', reasoning: '', catalysts: '', invalidation_conditions: '', time_horizon: '30', affected_tickers: '', affected_themes: '' })
    onRefresh()
  }

  const createOverride = async () => {
    if (!apiBase) return
    await fetch(`${apiBase}/api/overrides`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        signal_type: overrideForm.signal_type,
        ticker_or_market: overrideForm.ticker_or_market,
        override_type: overrideForm.override_type,
        strength: parseFloat(overrideForm.strength),
        reason: overrideForm.reason,
      })
    })
    setShowNewOverride(false)
    setOverrideForm({ signal_type: '', ticker_or_market: '', override_type: 'boost', strength: '1.5', reason: '' })
    onRefresh()
  }

  const deleteThesis = async (id: string) => {
    if (!apiBase) return
    await fetch(`${apiBase}/api/theses/${id}`, { method: 'DELETE' })
    onRefresh()
  }

  const deleteOverride = async (id: string) => {
    if (!apiBase) return
    await fetch(`${apiBase}/api/overrides/${id}`, { method: 'DELETE' })
    onRefresh()
  }

  const activeTheses = theses.filter(t => t.status === 'active')
  const inactiveTheses = theses.filter(t => t.status !== 'active')

  return (
    <div className="space-y-4">
      {/* Active Theses */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-sm">Market Theses ({activeTheses.length} active)</CardTitle>
          <Dialog open={showNewThesis} onOpenChange={setShowNewThesis}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline">+ New Thesis</Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>New Market Thesis</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <div>
                  <Label>Title</Label>
                  <Input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="e.g. Fed pivot incoming, risk-on rally" />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <Label>Direction</Label>
                    <Select value={form.direction} onValueChange={v => setForm(f => ({ ...f, direction: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="bullish">Bullish</SelectItem>
                        <SelectItem value="bearish">Bearish</SelectItem>
                        <SelectItem value="neutral">Neutral</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Confidence (%)</Label>
                    <Input type="number" min="0" max="100" value={form.confidence} onChange={e => setForm(f => ({ ...f, confidence: e.target.value }))} />
                  </div>
                  <div>
                    <Label>Time Horizon (days)</Label>
                    <Input type="number" min="1" value={form.time_horizon} onChange={e => setForm(f => ({ ...f, time_horizon: e.target.value }))} />
                  </div>
                </div>
                <div>
                  <Label>Reasoning</Label>
                  <Textarea value={form.reasoning} onChange={e => setForm(f => ({ ...f, reasoning: e.target.value }))} placeholder="Explain your market view..." rows={3} />
                </div>
                <div>
                  <Label>Catalysts (comma-separated)</Label>
                  <Input value={form.catalysts} onChange={e => setForm(f => ({ ...f, catalysts: e.target.value }))} placeholder="e.g. FOMC meeting, CPI print, earnings" />
                </div>
                <div>
                  <Label>Invalidation Conditions (comma-separated)</Label>
                  <Input value={form.invalidation_conditions} onChange={e => setForm(f => ({ ...f, invalidation_conditions: e.target.value }))} placeholder="e.g. VIX above 30, 10Y above 5%" />
                </div>
                <div>
                  <Label>Affected Tickers (comma-separated)</Label>
                  <Input value={form.affected_tickers} onChange={e => setForm(f => ({ ...f, affected_tickers: e.target.value }))} placeholder="e.g. SPY, QQQ, BTC" />
                </div>
                <div>
                  <Label>Affected Themes (comma-separated)</Label>
                  <Input value={form.affected_themes} onChange={e => setForm(f => ({ ...f, affected_themes: e.target.value }))} placeholder="e.g. theme-housing-bonds-war" />
                </div>
                <Button onClick={createThesis} className="w-full">Create Thesis</Button>
              </div>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent>
          {activeTheses.length === 0 ? (
            <div className="text-muted-foreground text-sm">No active theses. Add your market views to guide the bot.</div>
          ) : (
            <div className="space-y-3">
              {activeTheses.map(t => (
                <div key={t.id} className="border border-border rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{t.title}</span>
                      <Badge className={DIRECTION_COLORS[t.direction]}>{t.direction}</Badge>
                      <Badge variant="outline">{t.confidence}% confident</Badge>
                    </div>
                    <Button size="sm" variant="ghost" className="text-red-400" onClick={() => deleteThesis(t.id)}>Remove</Button>
                  </div>
                  <p className="text-sm text-muted-foreground">{t.reasoning}</p>
                  <div className="flex flex-wrap gap-2 text-xs">
                    {t.catalysts.map((c, i) => <Badge key={i} variant="outline" className="text-xs">{c}</Badge>)}
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Horizon: {t.time_horizon}d</span>
                    <span>Tickers: {t.affected_tickers.join(', ') || 'None'}</span>
                    <span>Created: {new Date(t.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Signal Overrides */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-sm">Signal Overrides ({overrides.filter(o => o.active).length} active)</CardTitle>
          <Dialog open={showNewOverride} onOpenChange={setShowNewOverride}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline">+ New Override</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New Signal Override</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <div>
                  <Label>Signal Type</Label>
                  <Input value={overrideForm.signal_type} onChange={e => setOverrideForm(f => ({ ...f, signal_type: e.target.value }))} placeholder="e.g. macro, sentiment, news" />
                </div>
                <div>
                  <Label>Ticker / Market</Label>
                  <Input value={overrideForm.ticker_or_market} onChange={e => setOverrideForm(f => ({ ...f, ticker_or_market: e.target.value }))} placeholder="e.g. ^VIX, BTC, SPY" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Override Type</Label>
                    <Select value={overrideForm.override_type} onValueChange={v => setOverrideForm(f => ({ ...f, override_type: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="boost">Boost (amplify)</SelectItem>
                        <SelectItem value="suppress">Suppress (reduce)</SelectItem>
                        <SelectItem value="invert">Invert (flip)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Strength (0.0 - 2.0)</Label>
                    <Input type="number" min="0" max="2" step="0.1" value={overrideForm.strength} onChange={e => setOverrideForm(f => ({ ...f, strength: e.target.value }))} />
                  </div>
                </div>
                <div>
                  <Label>Reason</Label>
                  <Textarea value={overrideForm.reason} onChange={e => setOverrideForm(f => ({ ...f, reason: e.target.value }))} placeholder="Why are you overriding this signal?" rows={2} />
                </div>
                <Button onClick={createOverride} className="w-full">Create Override</Button>
              </div>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent>
          {overrides.length === 0 ? (
            <div className="text-muted-foreground text-sm">No overrides. Use overrides to boost, suppress, or invert specific signals.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Signal</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Strength</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {overrides.map(o => (
                  <TableRow key={o.id} className={o.active ? '' : 'opacity-50'}>
                    <TableCell>{o.signal_type}</TableCell>
                    <TableCell className="font-mono text-xs">{o.ticker_or_market}</TableCell>
                    <TableCell>
                      <Badge variant={o.override_type === 'boost' ? 'default' : o.override_type === 'suppress' ? 'secondary' : 'destructive'}>
                        {o.override_type}
                      </Badge>
                    </TableCell>
                    <TableCell>{o.strength}x</TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">{o.reason}</TableCell>
                    <TableCell>
                      <Button size="sm" variant="ghost" className="text-red-400" onClick={() => deleteOverride(o.id)}>X</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Thesis History */}
      {inactiveTheses.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Thesis History ({inactiveTheses.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {inactiveTheses.map(t => (
                  <TableRow key={t.id}>
                    <TableCell className="font-medium">{t.title}</TableCell>
                    <TableCell className={DIRECTION_COLORS[t.direction]}>{t.direction}</TableCell>
                    <TableCell>
                      <Badge className={STATUS_COLORS[t.status] || ''}>{t.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{t.outcome || '-'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{new Date(t.created_at).toLocaleDateString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
