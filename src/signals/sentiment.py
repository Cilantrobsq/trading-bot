"""
Social sentiment analysis using the Finnhub API.

Fetches social sentiment (Reddit/Twitter mention counts and sentiment)
and market news for tracked tickers. Aggregates into a normalized
sentiment score from -1 (extremely bearish) to +1 (extremely bullish).
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from src.core.config import Config


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] sentiment: {msg}")


DEFAULT_TICKERS = ["AAPL", "TSLA", "SPY"]
DEFAULT_CRYPTO = ["BTC", "ETH"]

# Finnhub free tier: 60 API calls/minute
RATE_LIMIT_DELAY = 1.1  # seconds between calls to stay safe


@dataclass
class SentimentSignal:
    ticker: str
    source: str             # "finnhub_social", "finnhub_news"
    positive_mentions: int
    negative_mentions: int
    sentiment_score: float  # -1.0 to 1.0
    volume_change_pct: Optional[float]
    timestamp: str
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "source": self.source,
            "positive_mentions": self.positive_mentions,
            "negative_mentions": self.negative_mentions,
            "sentiment_score": self.sentiment_score,
            "volume_change_pct": self.volume_change_pct,
            "timestamp": self.timestamp,
            "error": self.error,
            "details": self.details,
        }


class SentimentFetcher:
    """
    Fetches social sentiment data from Finnhub for tracked tickers.

    Usage:
        cfg = Config()
        fetcher = SentimentFetcher(cfg)
        signals = fetcher.fetch_all()
    """

    def __init__(self, config: Config):
        self.config = config
        self._api_key = self._resolve_api_key()
        self._base_url = "https://finnhub.io/api/v1"

        # Load tracked tickers from config or use defaults
        finnhub_cfg = config._raw_strategy.get("finnhub", {})
        self.tickers = finnhub_cfg.get("tickers", DEFAULT_TICKERS)
        self.crypto_symbols = finnhub_cfg.get("crypto_symbols", DEFAULT_CRYPTO)

        if self._api_key:
            _log(f"initialized with {len(self.tickers)} tickers, {len(self.crypto_symbols)} crypto")
        else:
            _log("WARNING: no Finnhub API key found (set FINNHUB_API_KEY), signals will be empty")

    def _resolve_api_key(self) -> Optional[str]:
        key = os.environ.get("FINNHUB_API_KEY")
        if key:
            return key

        finnhub_cfg = self.config._raw_strategy.get("finnhub", {})
        key = finnhub_cfg.get("api_key")
        if key:
            return key

        # Try secrets file
        secrets_path = os.path.join(self.config.project_root, "secrets", "finnhub.json")
        if os.path.isfile(secrets_path):
            try:
                with open(secrets_path) as f:
                    data = json.load(f)
                return data.get("api_key") or data.get("key")
            except Exception:
                pass
        return None

    def _request(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Any:
        if not self._api_key:
            return None

        url = f"{self._base_url}{endpoint}"
        query_parts = [f"token={self._api_key}"]
        if params:
            for k, v in params.items():
                query_parts.append(f"{k}={v}")
        url += "?" + "&".join(query_parts)

        req = Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "TradingBot/1.0")

        try:
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:200]
            except Exception:
                pass
            _log(f"HTTP {e.code} for {endpoint}: {body}")
            return None
        except (URLError, Exception) as e:
            _log(f"request error for {endpoint}: {e}")
            return None

    def _fetch_social_sentiment(self, ticker: str) -> Optional[SentimentSignal]:
        """Fetch social sentiment (Reddit + Twitter) for a stock ticker."""
        data = self._request("/stock/social-sentiment", {"symbol": ticker})
        time.sleep(RATE_LIMIT_DELAY)

        now_str = datetime.now(timezone.utc).isoformat()

        if data is None:
            return SentimentSignal(
                ticker=ticker, source="finnhub_social",
                positive_mentions=0, negative_mentions=0,
                sentiment_score=0.0, volume_change_pct=None,
                timestamp=now_str, error="API request failed",
            )

        # Aggregate across reddit and twitter
        total_positive = 0
        total_negative = 0
        total_mentions = 0

        for platform in ("reddit", "twitter"):
            entries = data.get(platform, [])
            if not entries:
                continue
            for entry in entries:
                pos = entry.get("positiveMention", 0)
                neg = entry.get("negativeMention", 0)
                total_positive += pos
                total_negative += neg
                total_mentions += entry.get("mention", 0)

        # Compute sentiment score: (pos - neg) / (pos + neg), clamped to [-1, 1]
        total = total_positive + total_negative
        if total > 0:
            score = round((total_positive - total_negative) / total, 4)
        else:
            score = 0.0

        return SentimentSignal(
            ticker=ticker,
            source="finnhub_social",
            positive_mentions=total_positive,
            negative_mentions=total_negative,
            sentiment_score=max(-1.0, min(1.0, score)),
            volume_change_pct=None,
            timestamp=now_str,
            details={"total_mentions": total_mentions},
        )

    def _fetch_news_sentiment(self) -> List[SentimentSignal]:
        """Fetch general market news and derive per-ticker sentiment."""
        data = self._request("/news", {"category": "general"})
        time.sleep(RATE_LIMIT_DELAY)

        now_str = datetime.now(timezone.utc).isoformat()
        if not data or not isinstance(data, list):
            return []

        # Count headline sentiment per related ticker
        ticker_sentiment: Dict[str, Dict[str, int]] = {}
        all_tickers = set(self.tickers + self.crypto_symbols)

        for article in data:
            headline = (article.get("headline") or "").lower()
            summary = (article.get("summary") or "").lower()
            text = headline + " " + summary
            related = article.get("related", "").split(",")

            # Match tickers mentioned in related field or headline
            matched_tickers = set()
            for t in related:
                t = t.strip().upper()
                if t in all_tickers:
                    matched_tickers.add(t)
            for t in all_tickers:
                if t.lower() in text:
                    matched_tickers.add(t)

            if not matched_tickers:
                continue

            # Simple keyword sentiment
            neg_words = {"crash", "loss", "decline", "drop", "risk", "fear", "selloff", "bearish", "warning"}
            pos_words = {"rally", "surge", "growth", "bullish", "record", "profit", "gain", "rebound"}
            neg_count = sum(1 for w in neg_words if w in text)
            pos_count = sum(1 for w in pos_words if w in text)

            for t in matched_tickers:
                if t not in ticker_sentiment:
                    ticker_sentiment[t] = {"positive": 0, "negative": 0}
                ticker_sentiment[t]["positive"] += pos_count
                ticker_sentiment[t]["negative"] += neg_count

        signals = []
        for ticker, counts in ticker_sentiment.items():
            total = counts["positive"] + counts["negative"]
            score = 0.0
            if total > 0:
                score = round((counts["positive"] - counts["negative"]) / total, 4)

            signals.append(SentimentSignal(
                ticker=ticker,
                source="finnhub_news",
                positive_mentions=counts["positive"],
                negative_mentions=counts["negative"],
                sentiment_score=max(-1.0, min(1.0, score)),
                volume_change_pct=None,
                timestamp=now_str,
            ))

        return signals

    def fetch_all(self) -> List[SentimentSignal]:
        if not self._api_key:
            _log("skipping fetch: no Finnhub API key")
            return []

        _log(f"fetching sentiment for {len(self.tickers)} tickers...")
        signals: List[SentimentSignal] = []

        # Social sentiment per ticker
        for ticker in self.tickers:
            sig = self._fetch_social_sentiment(ticker)
            if sig:
                signals.append(sig)
                _log(f"  {ticker:<8} social  score={sig.sentiment_score:+.4f}  pos={sig.positive_mentions}  neg={sig.negative_mentions}")

        # News-based sentiment
        news_signals = self._fetch_news_sentiment()
        for sig in news_signals:
            signals.append(sig)
            _log(f"  {sig.ticker:<8} news    score={sig.sentiment_score:+.4f}  pos={sig.positive_mentions}  neg={sig.negative_mentions}")

        _log(f"summary: {len(signals)} sentiment signals")
        return signals

    def signals_to_json(self, signals: List[SentimentSignal]) -> str:
        return json.dumps([s.to_dict() for s in signals], indent=2)


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    fetcher = SentimentFetcher(cfg)

    if fetcher._api_key:
        signals = fetcher.fetch_all()
        print(f"\nFetched {len(signals)} sentiment signals")
    else:
        print("Finnhub API key not found. Set FINNHUB_API_KEY env var.")
