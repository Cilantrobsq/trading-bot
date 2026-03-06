"""
LLM-powered news headline analyzer using Claude.

Takes raw news headlines and uses Claude claude-haiku-4-5-20251001 to analyze sentiment,
market impact, affected themes/tickers, and confidence. Results are cached
to avoid re-analyzing identical headlines. Falls back to keyword-based
scoring when the API key is unavailable.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.config import Config

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] llm_analyzer: {msg}")


# Keyword sets for fallback scoring
_BEARISH_KEYWORDS = {
    "crash", "collapse", "plunge", "selloff", "crisis", "default", "recession",
    "downgrade", "fear", "warning", "decline", "slump", "panic", "bearish",
    "invasion", "war", "sanctions", "ban", "restrict",
}
_BULLISH_KEYWORDS = {
    "rally", "surge", "boom", "recovery", "growth", "bullish", "ceasefire",
    "peace", "deal", "stimulus", "rebound", "expansion", "upgrade",
    "profit", "record", "breakthrough",
}

MAX_HEADLINES_PER_BATCH = 20
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class LLMAnalysis:
    headline: str
    sentiment_score: float          # -1.0 to 1.0
    market_impact: str              # "high", "medium", "low", "none"
    affected_themes: List[str]
    affected_tickers: List[str]
    reasoning: str
    confidence: float               # 0.0 to 1.0
    timestamp: str
    source: str = "llm"             # "llm" or "keyword_fallback"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "headline": self.headline,
            "sentiment_score": self.sentiment_score,
            "market_impact": self.market_impact,
            "affected_themes": self.affected_themes,
            "affected_tickers": self.affected_tickers,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "source": self.source,
            "error": self.error,
        }


class LLMNewsAnalyzer:
    """
    Analyzes news headlines using Claude claude-haiku-4-5-20251001 for sentiment, market
    impact, and theme relevance. Caches results by headline hash.

    Falls back to keyword-based scoring when the Anthropic API key
    is not available.

    Usage:
        cfg = Config()
        analyzer = LLMNewsAnalyzer(cfg)
        results = analyzer.analyze(["Fed raises rates by 25bps", "Tesla reports record earnings"])
    """

    def __init__(self, config: Config):
        self.config = config
        self._client: Optional[Any] = None
        self._cache: Dict[str, LLMAnalysis] = {}

        llm_cfg = config._raw_strategy.get("llm_analysis", {})
        self.model = llm_cfg.get("model", DEFAULT_MODEL)
        self.max_batch_size = llm_cfg.get("max_batch_size", MAX_HEADLINES_PER_BATCH)
        self.max_daily_calls = llm_cfg.get("max_daily_calls", 100)
        self._calls_today = 0

        # Resolve API key
        api_key = os.environ.get("ANTHROPIC_API_KEY") or llm_cfg.get("api_key")
        if api_key and anthropic is not None:
            self._client = anthropic.Anthropic(api_key=api_key)
            _log(f"initialized with model={self.model}")
        elif anthropic is None:
            _log("WARNING: anthropic SDK not installed, using keyword fallback")
        else:
            _log("WARNING: no ANTHROPIC_API_KEY found, using keyword fallback")

    @staticmethod
    def _headline_hash(headline: str) -> str:
        return hashlib.sha256(headline.strip().lower().encode()).hexdigest()[:16]

    def _keyword_fallback(self, headline: str) -> LLMAnalysis:
        """Simple keyword-based scoring when LLM is unavailable."""
        now_str = datetime.now(timezone.utc).isoformat()
        h_lower = headline.lower()

        neg = sum(1 for w in _BEARISH_KEYWORDS if w in h_lower)
        pos = sum(1 for w in _BULLISH_KEYWORDS if w in h_lower)
        total = neg + pos

        if total > 0:
            score = round((pos - neg) / total, 2)
        else:
            score = 0.0

        if total >= 3:
            impact = "high"
        elif total >= 1:
            impact = "medium"
        else:
            impact = "none"

        return LLMAnalysis(
            headline=headline,
            sentiment_score=score,
            market_impact=impact,
            affected_themes=[],
            affected_tickers=[],
            reasoning="keyword-based fallback analysis",
            confidence=0.3 if total > 0 else 0.1,
            timestamp=now_str,
            source="keyword_fallback",
        )

    def _build_prompt(self, headlines: List[str]) -> str:
        numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
        return f"""Analyze these news headlines for market/trading relevance.
For each headline, provide:
- sentiment_score: float from -1.0 (very bearish) to 1.0 (very bullish)
- market_impact: "high", "medium", "low", or "none"
- affected_themes: list of relevant themes (e.g. "housing", "crypto", "geopolitics", "tech", "energy")
- affected_tickers: list of stock/crypto tickers likely affected (e.g. ["TSLA", "BTC"])
- reasoning: one sentence explaining your assessment
- confidence: float from 0.0 to 1.0

Headlines:
{numbered}

Respond with valid JSON only. Format: {{"analyses": [{{"index": 1, "sentiment_score": ..., "market_impact": ..., "affected_themes": [...], "affected_tickers": [...], "reasoning": "...", "confidence": ...}}, ...]}}"""

    def _parse_llm_response(self, response_text: str, headlines: List[str]) -> List[LLMAnalysis]:
        now_str = datetime.now(timezone.utc).isoformat()

        # Extract JSON from response (may be wrapped in markdown code blocks)
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            _log("failed to parse LLM response as JSON")
            return [self._keyword_fallback(h) for h in headlines]

        analyses_raw = data.get("analyses", [])
        results = []

        for i, headline in enumerate(headlines):
            # Find matching analysis by index
            analysis = None
            for a in analyses_raw:
                if a.get("index") == i + 1:
                    analysis = a
                    break

            if analysis is None:
                results.append(self._keyword_fallback(headline))
                continue

            results.append(LLMAnalysis(
                headline=headline,
                sentiment_score=max(-1.0, min(1.0, float(analysis.get("sentiment_score", 0)))),
                market_impact=analysis.get("market_impact", "none"),
                affected_themes=analysis.get("affected_themes", []),
                affected_tickers=analysis.get("affected_tickers", []),
                reasoning=analysis.get("reasoning", ""),
                confidence=max(0.0, min(1.0, float(analysis.get("confidence", 0.5)))),
                timestamp=now_str,
                source="llm",
            ))

        return results

    def _analyze_batch_llm(self, headlines: List[str]) -> List[LLMAnalysis]:
        """Send a batch of headlines to Claude for analysis."""
        if self._calls_today >= self.max_daily_calls:
            _log(f"daily call limit reached ({self.max_daily_calls}), using fallback")
            return [self._keyword_fallback(h) for h in headlines]

        prompt = self._build_prompt(headlines)

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            self._calls_today += 1
            response_text = response.content[0].text
            return self._parse_llm_response(response_text, headlines)

        except Exception as e:
            _log(f"LLM API error: {e}")
            return [self._keyword_fallback(h) for h in headlines]

    def analyze(self, headlines: List[str]) -> List[LLMAnalysis]:
        """
        Analyze a list of headlines. Uses cache for previously seen headlines.
        Batches uncached headlines into groups of max_batch_size for LLM calls.
        """
        if not headlines:
            return []

        results: List[LLMAnalysis] = []
        uncached: List[str] = []
        uncached_indices: List[int] = []

        # Check cache first
        for i, h in enumerate(headlines):
            h_hash = self._headline_hash(h)
            if h_hash in self._cache:
                results.append(self._cache[h_hash])
            else:
                results.append(None)  # type: ignore
                uncached.append(h)
                uncached_indices.append(i)

        if not uncached:
            _log(f"all {len(headlines)} headlines served from cache")
            return results

        _log(f"analyzing {len(uncached)} uncached headlines ({len(headlines) - len(uncached)} cached)")

        # Analyze uncached in batches
        analyzed: List[LLMAnalysis] = []
        for batch_start in range(0, len(uncached), self.max_batch_size):
            batch = uncached[batch_start:batch_start + self.max_batch_size]

            if self._client is not None:
                batch_results = self._analyze_batch_llm(batch)
            else:
                batch_results = [self._keyword_fallback(h) for h in batch]

            analyzed.extend(batch_results)

        # Merge results and populate cache
        for j, idx in enumerate(uncached_indices):
            analysis = analyzed[j]
            results[idx] = analysis
            h_hash = self._headline_hash(analysis.headline)
            self._cache[h_hash] = analysis

        # Summary
        llm_count = sum(1 for r in results if r.source == "llm")
        fallback_count = sum(1 for r in results if r.source == "keyword_fallback")
        _log(f"summary: {llm_count} LLM-analyzed, {fallback_count} keyword-fallback, {len(self._cache)} cached total")

        return results

    def clear_cache(self) -> None:
        count = len(self._cache)
        self._cache.clear()
        _log(f"cleared {count} cached analyses")

    def analyses_to_json(self, analyses: List[LLMAnalysis]) -> str:
        return json.dumps([a.to_dict() for a in analyses], indent=2)


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    analyzer = LLMNewsAnalyzer(cfg)

    test_headlines = [
        "Fed raises interest rates by 25 basis points amid inflation concerns",
        "Tesla reports record Q4 earnings, stock surges 8%",
        "Bitcoin crashes below $50,000 as market panic spreads",
        "Ukraine ceasefire talks show progress, defense stocks decline",
        "Apple announces new AI chip partnership with NVIDIA",
    ]

    results = analyzer.analyze(test_headlines)
    for r in results:
        print(f"  [{r.source:>16}] {r.sentiment_score:+.2f} | {r.market_impact:>6} | {r.headline[:50]}")
        if r.affected_tickers:
            print(f"                     tickers: {', '.join(r.affected_tickers)}")
