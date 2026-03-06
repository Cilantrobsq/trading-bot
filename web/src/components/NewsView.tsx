import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { NewsItem } from '@/types'

interface NewsViewProps {
  data?: NewsItem[]
}

export function NewsView({ data }: NewsViewProps) {
  if (!data || data.length === 0) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-muted-foreground">
          No news data available. Run the bot to fetch news feeds.
        </CardContent>
      </Card>
    )
  }

  const sentimentColor = (s: string) => {
    if (s === 'positive') return 'text-green-400'
    if (s === 'negative') return 'text-red-400'
    return 'text-zinc-400'
  }

  const relevanceColor = (score: number) => {
    if (score >= 0.8) return 'bg-green-900/50 text-green-300'
    if (score >= 0.5) return 'bg-yellow-900/50 text-yellow-300'
    return 'bg-zinc-800 text-zinc-400'
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">News Feed ({data.length} articles)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {data.map((item, i) => (
              <div key={i} className="border border-border rounded-lg p-3 hover:bg-muted/50 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <a
                      href={item.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium hover:underline text-foreground block truncate"
                    >
                      {item.title}
                    </a>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className="text-xs text-muted-foreground">
                        {item.published ? new Date(item.published).toLocaleDateString() : 'Unknown date'}
                      </span>
                      <span className={`text-xs ${sentimentColor(item.sentiment_hint)}`}>
                        {item.sentiment_hint}
                      </span>
                      {item.matched_themes.map((theme, j) => (
                        <Badge key={j} variant="outline" className="text-xs py-0">
                          {theme.length > 30 ? theme.slice(0, 30) + '...' : theme}
                        </Badge>
                      ))}
                    </div>
                    {item.matched_keywords.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {item.matched_keywords.slice(0, 5).map((kw, j) => (
                          <span key={j} className="text-xs px-1.5 py-0 rounded bg-zinc-800 text-zinc-400">
                            {kw}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded shrink-0 ${relevanceColor(item.relevance_score)}`}>
                    {(item.relevance_score * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
