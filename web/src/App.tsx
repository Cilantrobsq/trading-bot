import { useEffect, useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PortfolioView } from '@/components/PortfolioView'
import { SignalsView } from '@/components/SignalsView'
import { OpportunitiesView } from '@/components/OpportunitiesView'
import { ProposalsView } from '@/components/ProposalsView'
import { TradesView } from '@/components/TradesView'
import { ConfigView } from '@/components/ConfigView'
import { BrainView } from '@/components/BrainView'
import { ThesesView } from '@/components/ThesesView'
import { DecisionsView } from '@/components/DecisionsView'
import { NicheView } from '@/components/NicheView'
import { NewsView } from '@/components/NewsView'
import { GlobalView } from '@/components/GlobalView'
import type { DashboardData } from '@/types'

const BASE = import.meta.env.BASE_URL
const API_BASE = import.meta.env.VITE_API_URL || ''

function App() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string>('')
  const [error, setError] = useState<string>('')

  const fetchData = async () => {
    try {
      let res: Response
      if (API_BASE) {
        res = await fetch(`${API_BASE}/api/dashboard?t=${Date.now()}`)
      } else {
        res = await fetch(`${BASE}data/dashboard.json?t=${Date.now()}`)
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
      setLastUpdate(json.exported_at || new Date().toISOString())
      setError('')
    } catch (e) {
      setError(`Failed to load data: ${e}`)
    }
  }

  const toggleKillSwitch = async (active: boolean, reason: string) => {
    if (!API_BASE) return
    try {
      await fetch(`${API_BASE}/api/kill-switch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active, reason })
      })
      fetchData()
    } catch (e) {
      console.error('Kill switch toggle failed:', e)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30_000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="dark min-h-screen bg-background text-foreground">
      <header className="border-b border-border px-3 sm:px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <h1 className="text-lg sm:text-xl font-bold tracking-tight whitespace-nowrap">Trading Bot</h1>
            <span className="text-xs text-muted-foreground px-2 py-0.5 rounded bg-muted shrink-0">
              {data?.portfolio?.mode === 'paper' ? 'PAPER' : 'LIVE'}
            </span>
            {data?.kill_switch?.active && (
              <span className="text-xs px-2 py-0.5 rounded bg-red-900/50 text-red-300 animate-pulse shrink-0">
                KILL SWITCH
              </span>
            )}
            {data?.brain?.market_regime && (
              <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 shrink-0">
                {data.brain.market_regime.replace(/_/g, ' ')}
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
            {lastUpdate && new Date(lastUpdate).toLocaleTimeString()}
          </div>
        </div>
      </header>

      {error && (
        <div className="bg-destructive/10 text-destructive px-4 py-2 text-sm">
          {error}
        </div>
      )}

      <main className="px-3 sm:px-4 py-4 max-w-7xl mx-auto">
        <Tabs defaultValue="brain">
          <div className="overflow-x-auto -mx-3 sm:-mx-4 px-3 sm:px-4 mb-4">
          <TabsList className="inline-flex w-max sm:w-auto">
            <TabsTrigger value="brain">Brain</TabsTrigger>
            <TabsTrigger value="global">Global</TabsTrigger>
            <TabsTrigger value="portfolio">Portfolio</TabsTrigger>
            <TabsTrigger value="signals">Signals</TabsTrigger>
            <TabsTrigger value="theses">Theses</TabsTrigger>
            <TabsTrigger value="proposals">Proposals</TabsTrigger>
            <TabsTrigger value="opportunities">Opportunities</TabsTrigger>
            <TabsTrigger value="niche">Edge</TabsTrigger>
            <TabsTrigger value="news">News</TabsTrigger>
            <TabsTrigger value="decisions">Decisions</TabsTrigger>
            <TabsTrigger value="trades">Trades</TabsTrigger>
            <TabsTrigger value="config">Config</TabsTrigger>
          </TabsList>
          </div>

          <TabsContent value="brain">
            <BrainView data={data?.brain} killSwitch={data?.kill_switch} onToggleKillSwitch={API_BASE ? toggleKillSwitch : undefined} />
          </TabsContent>
          <TabsContent value="global">
            <GlobalView
              globalMarkets={data?.global_markets}
              globalMacro={data?.global_macro}
              timezoneArb={data?.timezone_arb}
              crossCorrelations={data?.cross_correlations}
            />
          </TabsContent>
          <TabsContent value="portfolio">
            <PortfolioView data={data?.portfolio} equityHistory={data?.equity_history} />
          </TabsContent>
          <TabsContent value="signals">
            <SignalsView data={data?.signals} fred={data?.fred} />
          </TabsContent>
          <TabsContent value="theses">
            <ThesesView theses={data?.theses} overrides={data?.overrides} apiBase={API_BASE} onRefresh={fetchData} />
          </TabsContent>
          <TabsContent value="proposals">
            <ProposalsView proposals={data?.proposals} />
          </TabsContent>
          <TabsContent value="opportunities">
            <OpportunitiesView data={data?.opportunities} />
          </TabsContent>
          <TabsContent value="niche">
            <NicheView
              nicheMarkets={data?.niche_markets}
              correlations={data?.correlations}
              circuitBreaker={data?.circuit_breaker}
              regime={data?.regime}
              fred={data?.fred}
              signals={data?.signals}
              brain={data?.brain}
              decisions={data?.decisions}
              snapshot={data?.snapshot}
            />
          </TabsContent>
          <TabsContent value="news">
            <NewsView data={data?.news} />
          </TabsContent>
          <TabsContent value="decisions">
            <DecisionsView data={data?.decisions} />
          </TabsContent>
          <TabsContent value="trades">
            <TradesView data={data?.trades} />
          </TabsContent>
          <TabsContent value="config">
            <ConfigView data={data?.config} />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}

export default App
