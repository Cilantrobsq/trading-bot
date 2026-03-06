import { useEffect, useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PortfolioView } from '@/components/PortfolioView'
import { SignalsView } from '@/components/SignalsView'
import { OpportunitiesView } from '@/components/OpportunitiesView'
import { TradesView } from '@/components/TradesView'
import { ConfigView } from '@/components/ConfigView'
import type { DashboardData } from '@/types'

const BASE = import.meta.env.BASE_URL

function App() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string>('')
  const [error, setError] = useState<string>('')

  const fetchData = async () => {
    try {
      const res = await fetch(`${BASE}data/dashboard.json?t=${Date.now()}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
      setLastUpdate(json.exported_at || new Date().toISOString())
      setError('')
    } catch (e) {
      setError(`Failed to load data: ${e}`)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60_000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="dark min-h-screen bg-background text-foreground">
      <header className="border-b border-border px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">Trading Bot</h1>
          <span className="text-xs text-muted-foreground px-2 py-0.5 rounded bg-muted">
            {data?.portfolio?.mode === 'paper' ? 'PAPER' : 'LIVE'}
          </span>
        </div>
        <div className="text-xs text-muted-foreground">
          {lastUpdate && `Updated: ${new Date(lastUpdate).toLocaleString()}`}
        </div>
      </header>

      {error && (
        <div className="bg-destructive/10 text-destructive px-4 py-2 text-sm">
          {error}
        </div>
      )}

      <main className="p-4 max-w-7xl mx-auto">
        <Tabs defaultValue="portfolio">
          <TabsList className="mb-4">
            <TabsTrigger value="portfolio">Portfolio</TabsTrigger>
            <TabsTrigger value="signals">Signals</TabsTrigger>
            <TabsTrigger value="opportunities">Opportunities</TabsTrigger>
            <TabsTrigger value="trades">Trades</TabsTrigger>
            <TabsTrigger value="config">Config</TabsTrigger>
          </TabsList>

          <TabsContent value="portfolio">
            <PortfolioView data={data?.portfolio} />
          </TabsContent>
          <TabsContent value="signals">
            <SignalsView data={data?.signals} />
          </TabsContent>
          <TabsContent value="opportunities">
            <OpportunitiesView data={data?.opportunities} />
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
