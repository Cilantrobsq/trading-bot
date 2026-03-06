"""
Influencer and key figure tracker.

Monitors what influential market participants are saying via RSS feeds,
blog posts, and public statements. Extracts sentiment and position hints
from their public communications.

Tracks:
- Central bankers (Fed, ECB, BOJ, BOE governors and board members)
- Macro investors (Dalio, Druckenmiller, Ackman, Burry, etc.)
- Crypto leaders (Saylor, CZ, Vitalik, Hayes, etc.)
- Tech/VC voices (a16z, Cathie Wood, Chamath)
- Financial media (Bloomberg, Reuters, FT key columnists)
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore

import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INFLUENCER_DATA_FILE = os.path.join(BASE_DIR, "data", "snapshots", "latest-influencers.json")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] influencer_tracker: {msg}")


# Key figures we track, organized by category
KEY_FIGURES = {
    "central_bankers": {
        "Jerome Powell": {"role": "Fed Chair", "org": "Federal Reserve", "weight": 10},
        "Jay Powell": {"role": "Fed Chair", "org": "Federal Reserve", "weight": 10},
        "Christine Lagarde": {"role": "ECB President", "org": "ECB", "weight": 9},
        "Kazuo Ueda": {"role": "BOJ Governor", "org": "Bank of Japan", "weight": 9},
        "Andrew Bailey": {"role": "BOE Governor", "org": "Bank of England", "weight": 8},
        "Christopher Waller": {"role": "Fed Governor", "org": "Federal Reserve", "weight": 7},
        "Mary Daly": {"role": "SF Fed President", "org": "Federal Reserve", "weight": 6},
        "Neel Kashkari": {"role": "Minneapolis Fed", "org": "Federal Reserve", "weight": 6},
        "Raphael Bostic": {"role": "Atlanta Fed", "org": "Federal Reserve", "weight": 6},
        "Loretta Mester": {"role": "Cleveland Fed", "org": "Federal Reserve", "weight": 6},
        "Philip Lane": {"role": "ECB Chief Economist", "org": "ECB", "weight": 7},
        "Yi Gang": {"role": "PBOC Governor", "org": "PBOC", "weight": 8},
    },
    "macro_investors": {
        "Ray Dalio": {"role": "Bridgewater founder", "org": "Bridgewater", "weight": 9},
        "Stanley Druckenmiller": {"role": "Duquesne founder", "org": "Duquesne", "weight": 9},
        "Bill Ackman": {"role": "Pershing Square CEO", "org": "Pershing Square", "weight": 8},
        "Michael Burry": {"role": "Scion Capital", "org": "Scion", "weight": 8},
        "Howard Marks": {"role": "Oaktree co-chair", "org": "Oaktree", "weight": 8},
        "Carl Icahn": {"role": "Icahn Enterprises", "org": "Icahn", "weight": 7},
        "David Einhorn": {"role": "Greenlight Capital", "org": "Greenlight", "weight": 7},
        "George Soros": {"role": "Soros Fund", "org": "Soros", "weight": 9},
        "Paul Tudor Jones": {"role": "Tudor Investment", "org": "Tudor", "weight": 8},
        "Ken Griffin": {"role": "Citadel CEO", "org": "Citadel", "weight": 8},
        "Jamie Dimon": {"role": "JPMorgan CEO", "org": "JPMorgan", "weight": 9},
        "Larry Fink": {"role": "BlackRock CEO", "org": "BlackRock", "weight": 9},
        "Warren Buffett": {"role": "Berkshire Hathaway", "org": "Berkshire", "weight": 10},
        "Charlie Munger": {"role": "Berkshire Vice Chair", "org": "Berkshire", "weight": 8},
    },
    "crypto_leaders": {
        "Michael Saylor": {"role": "MicroStrategy", "org": "MicroStrategy", "weight": 8},
        "Changpeng Zhao": {"role": "Binance founder", "org": "Binance", "weight": 8},
        "CZ": {"role": "Binance founder", "org": "Binance", "weight": 8},
        "Vitalik Buterin": {"role": "Ethereum co-founder", "org": "Ethereum", "weight": 9},
        "Arthur Hayes": {"role": "BitMEX co-founder", "org": "BitMEX", "weight": 7},
        "Sam Bankman": {"role": "FTX (historical)", "org": "FTX", "weight": 5},
        "Brian Armstrong": {"role": "Coinbase CEO", "org": "Coinbase", "weight": 8},
        "Do Kwon": {"role": "Terra (historical)", "org": "Terra", "weight": 4},
        "Justin Sun": {"role": "Tron founder", "org": "Tron", "weight": 5},
        "Anatoly Yakovenko": {"role": "Solana co-founder", "org": "Solana", "weight": 7},
        "Balaji Srinivasan": {"role": "ex-a16z/Coinbase CTO", "org": "Independent", "weight": 7},
        "Elon Musk": {"role": "Tesla/SpaceX/DOGE", "org": "Tesla", "weight": 9},
    },
    "tech_vc": {
        "Cathie Wood": {"role": "ARK Invest CEO", "org": "ARK", "weight": 7},
        "Marc Andreessen": {"role": "a16z co-founder", "org": "a16z", "weight": 8},
        "Chamath Palihapitiya": {"role": "Social Capital", "org": "Social Capital", "weight": 6},
        "Peter Thiel": {"role": "Founders Fund", "org": "Founders Fund", "weight": 7},
        "Sam Altman": {"role": "OpenAI CEO", "org": "OpenAI", "weight": 8},
        "Jensen Huang": {"role": "NVIDIA CEO", "org": "NVIDIA", "weight": 9},
        "Tim Cook": {"role": "Apple CEO", "org": "Apple", "weight": 8},
        "Satya Nadella": {"role": "Microsoft CEO", "org": "Microsoft", "weight": 8},
        "Mark Zuckerberg": {"role": "Meta CEO", "org": "Meta", "weight": 8},
    },
    "political": {
        "Donald Trump": {"role": "US President", "org": "US Government", "weight": 10},
        "Janet Yellen": {"role": "Treasury Secretary", "org": "US Treasury", "weight": 9},
        "Gary Gensler": {"role": "SEC Chair", "org": "SEC", "weight": 8},
        "Elizabeth Warren": {"role": "US Senator", "org": "US Senate", "weight": 6},
        "Xi Jinping": {"role": "China President", "org": "CPC", "weight": 9},
    },
}

# RSS feeds to monitor for influencer mentions
INFLUENCER_FEEDS = [
    # Central bank official feeds
    "https://news.google.com/rss/search?q=Federal+Reserve+statement+Powell",
    "https://news.google.com/rss/search?q=ECB+Lagarde+monetary+policy",
    "https://news.google.com/rss/search?q=Bank+of+Japan+Ueda+rates",

    # Macro investors
    "https://news.google.com/rss/search?q=Ray+Dalio+economy+markets",
    "https://news.google.com/rss/search?q=Druckenmiller+Ackman+Burry+investing",
    "https://news.google.com/rss/search?q=Warren+Buffett+Berkshire",
    "https://news.google.com/rss/search?q=Jamie+Dimon+JPMorgan+outlook",
    "https://news.google.com/rss/search?q=Larry+Fink+BlackRock",

    # Crypto leaders
    "https://news.google.com/rss/search?q=Michael+Saylor+bitcoin+buy",
    "https://news.google.com/rss/search?q=Vitalik+Buterin+ethereum",
    "https://news.google.com/rss/search?q=Elon+Musk+crypto+dogecoin",
    "https://news.google.com/rss/search?q=CZ+Binance+crypto",
    "https://news.google.com/rss/search?q=Brian+Armstrong+Coinbase",
    "https://news.google.com/rss/search?q=Arthur+Hayes+bitcoin+macro",

    # Tech/VC
    "https://news.google.com/rss/search?q=Cathie+Wood+ARK+invest",
    "https://news.google.com/rss/search?q=Jensen+Huang+NVIDIA+AI",
    "https://news.google.com/rss/search?q=Sam+Altman+OpenAI",

    # Political/regulatory
    "https://news.google.com/rss/search?q=SEC+crypto+regulation+enforcement",
    "https://news.google.com/rss/search?q=Trump+tariffs+economy",
    "https://news.google.com/rss/search?q=Yellen+Treasury+debt",
]

# Sentiment keywords
BULLISH_KEYWORDS = {
    "buy", "bullish", "long", "optimistic", "opportunity", "undervalued",
    "accumulate", "rally", "breakout", "all-time high", "growth", "strong",
    "upside", "recovery", "expansion", "rate cut", "dovish", "stimulus",
    "green light", "buying", "conviction", "loading", "moon",
}

BEARISH_KEYWORDS = {
    "sell", "bearish", "short", "pessimistic", "overvalued", "crash",
    "bubble", "correction", "downturn", "recession", "rate hike", "hawkish",
    "tightening", "risk", "warning", "danger", "collapse", "crisis",
    "exit", "reduce", "dump", "liquidate", "fear", "panic",
}


@dataclass
class InfluencerMention:
    """A detected mention of a key figure in news."""
    figure_name: str
    category: str
    role: str
    org: str
    weight: int
    title: str
    link: str
    published: str
    source_feed: str
    sentiment: str  # "bullish", "bearish", "neutral"
    sentiment_score: float  # -1.0 to 1.0
    key_topics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "figure_name": self.figure_name,
            "category": self.category,
            "role": self.role,
            "org": self.org,
            "weight": self.weight,
            "title": self.title,
            "link": self.link,
            "published": self.published,
            "source_feed": self.source_feed,
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
            "key_topics": self.key_topics,
        }


class InfluencerTracker:
    """
    Tracks what key market figures are saying publicly.

    Monitors RSS feeds, matches headlines to known figures,
    extracts sentiment, and generates position-relevant signals.
    """

    def __init__(self):
        # Build a flat lookup for quick matching
        self.figure_lookup: Dict[str, Dict[str, Any]] = {}
        for category, figures in KEY_FIGURES.items():
            for name, info in figures.items():
                self.figure_lookup[name.lower()] = {
                    "name": name,
                    "category": category,
                    **info,
                }

    def _parse_feed(self, feed_url: str) -> List[Dict[str, Any]]:
        """Parse RSS feed, return raw entries."""
        if feedparser is None:
            return []
        try:
            feed = feedparser.parse(feed_url)
            entries = []
            for entry in feed.entries:
                entries.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", entry.get("updated", "")),
                    "source_feed": feed_url,
                })
            return entries
        except Exception as e:
            _log(f"Feed error: {feed_url} -> {e}")
            return []

    def _match_figures(self, title: str) -> List[Dict[str, Any]]:
        """Find which key figures are mentioned in a headline."""
        title_lower = title.lower()
        matches = []
        seen_names = set()

        for search_name, info in self.figure_lookup.items():
            # Skip if this is a duplicate (e.g., "CZ" and "Changpeng Zhao")
            canonical = info["name"]
            if canonical in seen_names:
                continue

            # Check for name mention
            if search_name in title_lower:
                matches.append(info)
                seen_names.add(canonical)
            # Also check last name for multi-word names
            elif " " in search_name:
                parts = search_name.split()
                last_name = parts[-1]
                if len(last_name) > 3 and last_name in title_lower:
                    matches.append(info)
                    seen_names.add(canonical)

        return matches

    def _analyze_sentiment(self, title: str) -> tuple:
        """Analyze headline sentiment. Returns (sentiment_str, score, topics)."""
        title_lower = title.lower()

        bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in title_lower)
        bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in title_lower)

        if bull_count > bear_count:
            sentiment = "bullish"
            score = min(1.0, (bull_count - bear_count) * 0.25)
        elif bear_count > bull_count:
            sentiment = "bearish"
            score = max(-1.0, -(bear_count - bull_count) * 0.25)
        else:
            sentiment = "neutral"
            score = 0.0

        # Extract key topics
        topics = []
        topic_keywords = {
            "bitcoin": "Bitcoin", "btc": "Bitcoin", "ethereum": "Ethereum", "eth": "Ethereum",
            "crypto": "Crypto", "ai": "AI", "artificial intelligence": "AI",
            "rate": "Interest Rates", "inflation": "Inflation", "recession": "Recession",
            "tariff": "Trade/Tariffs", "china": "China", "regulation": "Regulation",
            "earning": "Earnings", "profit": "Profits", "tech": "Technology",
            "oil": "Oil/Energy", "gold": "Gold", "housing": "Housing",
            "bond": "Bonds", "treasury": "Treasuries", "stock": "Equities",
            "semiconductor": "Semiconductors", "chip": "Semiconductors",
            "bank": "Banking", "dollar": "USD", "yen": "JPY",
        }
        for kw, topic in topic_keywords.items():
            if kw in title_lower and topic not in topics:
                topics.append(topic)

        return sentiment, score, topics

    def scan_feeds(self) -> List[InfluencerMention]:
        """Scan all feeds and extract influencer mentions with sentiment."""
        _log(f"Scanning {len(INFLUENCER_FEEDS)} feeds for influencer mentions...")
        all_mentions = []
        seen_titles: Set[str] = set()

        for feed_url in INFLUENCER_FEEDS:
            entries = self._parse_feed(feed_url)
            for entry in entries:
                title = entry.get("title", "")
                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                figures = self._match_figures(title)
                if not figures:
                    continue

                sentiment, score, topics = self._analyze_sentiment(title)

                for fig in figures:
                    mention = InfluencerMention(
                        figure_name=fig["name"],
                        category=fig["category"],
                        role=fig["role"],
                        org=fig["org"],
                        weight=fig["weight"],
                        title=title,
                        link=entry.get("link", ""),
                        published=entry.get("published", ""),
                        source_feed=entry.get("source_feed", ""),
                        sentiment=sentiment,
                        sentiment_score=score,
                        key_topics=topics,
                    )
                    all_mentions.append(mention)

        # Sort by weight (most influential first), then by sentiment strength
        all_mentions.sort(key=lambda m: (m.weight, abs(m.sentiment_score)), reverse=True)
        _log(f"Found {len(all_mentions)} influencer mentions across {len(seen_titles)} unique headlines")
        return all_mentions

    def generate_signals(self, mentions: List[InfluencerMention]) -> List[Dict[str, Any]]:
        """Generate trading signals from influencer activity."""
        signals = []

        # Aggregate sentiment by category
        cat_sentiments: Dict[str, List[float]] = {}
        for m in mentions:
            if m.category not in cat_sentiments:
                cat_sentiments[m.category] = []
            cat_sentiments[m.category].append(m.sentiment_score * m.weight)

        for cat, scores in cat_sentiments.items():
            if not scores:
                continue
            avg_score = sum(scores) / len(scores)
            if abs(avg_score) > 2.0:  # weighted sentiment threshold
                direction = "bullish" if avg_score > 0 else "bearish"
                signals.append({
                    "signal": f"influencer_{cat}_consensus",
                    "direction": direction,
                    "strength": min(1.0, abs(avg_score) / 10),
                    "description": f"{cat.replace('_', ' ').title()} figures trending {direction} "
                                   f"(weighted sentiment: {avg_score:+.1f}, {len(scores)} mentions)",
                    "mention_count": len(scores),
                })

        # High-weight individual signals (weight >= 9 with clear sentiment)
        for m in mentions:
            if m.weight >= 9 and abs(m.sentiment_score) >= 0.5:
                signals.append({
                    "signal": f"key_figure_{m.figure_name.replace(' ', '_').lower()}",
                    "direction": m.sentiment,
                    "strength": min(1.0, abs(m.sentiment_score) * m.weight / 10),
                    "description": f"{m.figure_name} ({m.role}): \"{m.title[:100]}\"",
                    "topics": m.key_topics,
                })

        return signals

    def compute_summary(self, mentions: List[InfluencerMention]) -> Dict[str, Any]:
        """Compute summary statistics from mentions."""
        if not mentions:
            return {"total": 0, "categories": {}, "top_figures": [], "sentiment_balance": 0}

        # By category
        categories: Dict[str, Dict] = {}
        for m in mentions:
            if m.category not in categories:
                categories[m.category] = {"count": 0, "bullish": 0, "bearish": 0, "neutral": 0}
            categories[m.category]["count"] += 1
            categories[m.category][m.sentiment] += 1

        # Top mentioned figures
        figure_counts: Dict[str, int] = {}
        for m in mentions:
            figure_counts[m.figure_name] = figure_counts.get(m.figure_name, 0) + 1
        top_figures = sorted(figure_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Overall sentiment balance
        bull = sum(1 for m in mentions if m.sentiment == "bullish")
        bear = sum(1 for m in mentions if m.sentiment == "bearish")
        total = len(mentions)

        return {
            "total": total,
            "categories": categories,
            "top_figures": [{"name": name, "mentions": count} for name, count in top_figures],
            "sentiment_balance": {
                "bullish": bull,
                "bearish": bear,
                "neutral": total - bull - bear,
                "ratio": round(bull / max(bear, 1), 2),
            },
        }

    def full_scan(self) -> Dict[str, Any]:
        """Run complete influencer scan."""
        _log("=== Starting full influencer scan ===")

        mentions = self.scan_feeds()
        signals = self.generate_signals(mentions)
        summary = self.compute_summary(mentions)

        result = {
            "mentions": [m.to_dict() for m in mentions],
            "signals": signals,
            "summary": summary,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "mention_count": len(mentions),
            "signal_count": len(signals),
            "feeds_scanned": len(INFLUENCER_FEEDS),
        }

        # Save to disk
        os.makedirs(os.path.dirname(INFLUENCER_DATA_FILE), exist_ok=True)
        with open(INFLUENCER_DATA_FILE, "w") as f:
            json.dump(result, f, indent=2)

        _log(f"=== Influencer scan complete: {len(mentions)} mentions, {len(signals)} signals ===")
        return result


if __name__ == "__main__":
    tracker = InfluencerTracker()
    result = tracker.full_scan()
    print(json.dumps(result, indent=2)[:3000])
