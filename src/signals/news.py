"""
News feed monitor using feedparser.

Parses RSS feeds from strategy.json config, extracts headlines,
and scores relevance to active trading themes using keyword matching.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore

from src.core.config import Config, Theme


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] news: {msg}")


@dataclass
class NewsItem:
    """A single parsed news article with relevance scoring."""
    title: str
    link: str
    published: str
    source_feed: str
    matched_themes: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    sentiment_hint: str = "neutral"  # "positive", "negative", "neutral"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "link": self.link,
            "published": self.published,
            "source_feed": self.source_feed,
            "matched_themes": self.matched_themes,
            "matched_keywords": self.matched_keywords,
            "relevance_score": self.relevance_score,
            "sentiment_hint": self.sentiment_hint,
        }


# Keywords that suggest negative/bearish sentiment
NEGATIVE_KEYWORDS = {
    "crash", "collapse", "plunge", "selloff", "sell-off", "crisis",
    "default", "recession", "downgrade", "risk", "fear", "warning",
    "decline", "drop", "slump", "bust", "panic", "losses", "bearish",
    "invasion", "escalation", "sanctions", "war", "missile", "nuclear",
    "ban", "restrict", "freeze", "moratorium",
}

# Keywords that suggest positive/bullish sentiment
POSITIVE_KEYWORDS = {
    "rally", "surge", "boom", "recovery", "growth", "bullish",
    "ceasefire", "peace", "deal", "agreement", "stimulus",
    "rebound", "expansion", "upgrade", "opportunity", "profit",
    "record", "high", "breakthrough",
}


class NewsFeedMonitor:
    """
    Monitors RSS news feeds and scores headlines for relevance
    to active trading themes.

    Uses keyword matching against theme-specific terms (geopolitical
    keywords, regulation keywords, ticker names, theme descriptions)
    to produce a relevance score per headline.

    Usage:
        cfg = Config()
        monitor = NewsFeedMonitor(cfg)
        articles = monitor.fetch_all()
        relevant = monitor.filter_relevant(articles, min_score=0.3)
    """

    def __init__(self, config: Config):
        self.config = config
        self.feeds = config.news_feeds
        self._build_theme_keywords()
        _log(f"initialized with {len(self.feeds)} feeds, {len(self.theme_keywords)} theme keyword sets")

    def _build_theme_keywords(self) -> None:
        """
        Build keyword sets for each active theme from config data.
        Pulls from: signal_logic keywords, regulation_watch keywords,
        ticker names, theme description words.
        """
        self.theme_keywords: Dict[str, Set[str]] = {}

        for theme in self.config.active_themes():
            keywords: Set[str] = set()

            # From signal_logic (geopolitical keywords, property watch, etc.)
            sl = theme.signal_logic
            for key, val in sl.items():
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, str):
                            # Add multi-word phrases as-is (lowercased)
                            keywords.add(item.lower())
                elif isinstance(val, str):
                    # Extract meaningful terms from logic expressions
                    pass

            # From regulation_watch
            rw = theme.regulation_watch
            for section_key, section in rw.items():
                if isinstance(section, dict):
                    for sk_key in ("signal_keywords", "monitor"):
                        sk = section.get(sk_key, [])
                        if isinstance(sk, list):
                            for kw in sk:
                                keywords.add(kw.lower())
                        elif isinstance(sk, str):
                            keywords.add(sk.lower())

            # Theme name words
            for word in theme.name.lower().split():
                if len(word) > 3:
                    keywords.add(word)

            # Ticker symbols (useful for matching "LEN" or "Melia" in headlines)
            for category, items in theme.equities.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            name = item.get("name", "")
                            if name:
                                # Add company name (first word if multi-word)
                                words = name.split()
                                if words:
                                    keywords.add(words[0].lower())
                                if len(words) > 1:
                                    keywords.add(name.lower())

            # Key concepts from description
            desc_keywords = {
                "housing", "bond", "yield", "treasury", "mortgage", "geopolitical",
                "defense", "reit", "homebuilder", "mallorca", "balearic", "tourism",
                "airbnb", "rental", "hotel", "spain", "spanish",
                "polymarket", "prediction", "prediction market",
            }
            for dk in desc_keywords:
                if dk in theme.description.lower():
                    keywords.add(dk)

            self.theme_keywords[theme.id] = keywords

    def _parse_feed(self, feed_url: str) -> List[NewsItem]:
        """Parse a single RSS feed and return NewsItem objects."""
        if feedparser is None:
            _log(f"feedparser not installed, skipping {feed_url}")
            return []

        try:
            feed = feedparser.parse(feed_url)
            items = []
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                published = entry.get("published", entry.get("updated", ""))

                if not title:
                    continue

                items.append(NewsItem(
                    title=title,
                    link=link,
                    published=published,
                    source_feed=feed_url,
                ))
            _log(f"parsed {len(items)} articles from {feed_url.split('?')[0]}...")
            return items

        except Exception as e:
            _log(f"error parsing {feed_url}: {e}")
            return []

    def _score_article(self, article: NewsItem) -> None:
        """
        Score a single article for relevance against all active themes.
        Mutates the article in place, setting matched_themes,
        matched_keywords, relevance_score, and sentiment_hint.
        """
        title_lower = article.title.lower()
        total_score = 0.0

        for theme_id, keywords in self.theme_keywords.items():
            theme_matches = []
            for kw in keywords:
                # For multi-word keywords, do substring match
                if " " in kw:
                    if kw in title_lower:
                        theme_matches.append(kw)
                else:
                    # Word boundary match for single words
                    pattern = r'\b' + re.escape(kw) + r'\b'
                    if re.search(pattern, title_lower):
                        theme_matches.append(kw)

            if theme_matches:
                article.matched_themes.append(theme_id)
                article.matched_keywords.extend(theme_matches)
                # Score: more keyword matches = higher relevance
                # Diminishing returns after 3 matches
                match_score = min(len(theme_matches), 5) / 5.0
                total_score += match_score

        article.relevance_score = round(min(total_score, 1.0), 3)

        # Simple sentiment from keyword presence
        neg_count = sum(1 for nk in NEGATIVE_KEYWORDS if nk in title_lower)
        pos_count = sum(1 for pk in POSITIVE_KEYWORDS if pk in title_lower)
        if neg_count > pos_count:
            article.sentiment_hint = "negative"
        elif pos_count > neg_count:
            article.sentiment_hint = "positive"
        else:
            article.sentiment_hint = "neutral"

    def fetch_all(self) -> List[NewsItem]:
        """
        Fetch and score all articles from configured RSS feeds.
        Returns articles sorted by relevance score (highest first).
        """
        _log(f"fetching {len(self.feeds)} feeds...")
        all_articles: List[NewsItem] = []

        for feed_url in self.feeds:
            articles = self._parse_feed(feed_url)
            all_articles.extend(articles)

        # Deduplicate by title
        seen_titles: Set[str] = set()
        unique: List[NewsItem] = []
        for a in all_articles:
            title_key = a.title.lower().strip()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique.append(a)

        _log(f"total: {len(all_articles)} raw, {len(unique)} unique articles")

        # Score all articles
        for article in unique:
            self._score_article(article)

        # Sort by relevance
        unique.sort(key=lambda a: a.relevance_score, reverse=True)

        relevant_count = sum(1 for a in unique if a.relevance_score > 0)
        _log(f"scored: {relevant_count} relevant, {len(unique) - relevant_count} unrelated")

        return unique

    def filter_relevant(
        self, articles: List[NewsItem], min_score: float = 0.2
    ) -> List[NewsItem]:
        """Filter articles to those above a minimum relevance score."""
        return [a for a in articles if a.relevance_score >= min_score]

    def articles_by_theme(
        self, articles: List[NewsItem]
    ) -> Dict[str, List[NewsItem]]:
        """Group relevant articles by theme ID."""
        by_theme: Dict[str, List[NewsItem]] = {}
        for a in articles:
            for tid in a.matched_themes:
                if tid not in by_theme:
                    by_theme[tid] = []
                by_theme[tid].append(a)
        return by_theme

    def articles_to_json(self, articles: List[NewsItem]) -> str:
        """Serialize articles to JSON."""
        return json.dumps([a.to_dict() for a in articles], indent=2)

    def print_summary(self, articles: List[NewsItem], max_items: int = 20) -> None:
        """Print a formatted news summary."""
        relevant = self.filter_relevant(articles, min_score=0.1)
        print(f"\n--- News Summary ({len(relevant)} relevant of {len(articles)} total) ---")
        for a in relevant[:max_items]:
            themes_str = ", ".join(a.matched_themes) if a.matched_themes else "none"
            sent = {"positive": "+", "negative": "-", "neutral": " "}[a.sentiment_hint]
            print(
                f"  [{sent}] ({a.relevance_score:.2f}) {a.title[:80]}"
            )
            if a.matched_keywords:
                print(f"       keywords: {', '.join(a.matched_keywords[:5])}")
        if len(relevant) > max_items:
            print(f"  ... and {len(relevant) - max_items} more")
        print("---")


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    monitor = NewsFeedMonitor(cfg)

    print(f"Theme keyword sets:")
    for tid, kws in monitor.theme_keywords.items():
        print(f"  {tid}: {len(kws)} keywords")
        for kw in sorted(kws)[:10]:
            print(f"    - {kw}")

    if feedparser is not None:
        articles = monitor.fetch_all()
        monitor.print_summary(articles)
    else:
        print("\nfeedparser not installed -- skipping live fetch")
