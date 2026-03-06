"""
Cross-platform prediction market aggregator.

Aggregates market data from Polymarket (via existing client), Manifold Markets,
and Metaculus. Detects cross-platform arbitrage opportunities where the same
question has meaningfully different prices across platforms.
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from src.core.config import Config
from src.execution.polymarket_client import PolymarketClient


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] prediction_markets: {msg}")


CATEGORIES = ["elections", "crypto", "economics", "geopolitics", "ai", "tech", "science"]


@dataclass
class PredictionMarketSignal:
    question: str
    platform_prices: Dict[str, float]     # platform_name -> probability
    avg_probability: float
    spread_pct: float                     # max - min across platforms
    arbitrage_opportunity: bool
    category: str
    volume: Optional[float] = None
    platforms_count: int = 1
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "platform_prices": self.platform_prices,
            "avg_probability": self.avg_probability,
            "spread_pct": self.spread_pct,
            "arbitrage_opportunity": self.arbitrage_opportunity,
            "category": self.category,
            "volume": self.volume,
            "platforms_count": self.platforms_count,
            "error": self.error,
        }


def _http_get(url: str, timeout: float = 15.0) -> Any:
    """Simple HTTP GET returning parsed JSON, or None on failure."""
    req = Request(url)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "TradingBot/1.0")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, Exception) as e:
        _log(f"HTTP error for {url[:80]}: {e}")
        return None


def _classify_category(text: str) -> str:
    """Classify a market question into one of the tracked categories."""
    text_lower = text.lower()
    category_keywords = {
        "elections": ["election", "president", "vote", "ballot", "governor", "senate", "congress", "mayor", "primary"],
        "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol", "token", "blockchain"],
        "economics": ["gdp", "inflation", "recession", "fed", "interest rate", "unemployment", "cpi", "stock", "s&p", "nasdaq"],
        "geopolitics": ["war", "conflict", "russia", "ukraine", "china", "taiwan", "nato", "sanctions", "missile", "ceasefire"],
        "ai": ["ai ", "artificial intelligence", "openai", "chatgpt", "gpt", "llm", "machine learning", "agi"],
        "tech": ["apple", "google", "meta", "microsoft", "tesla", "spacex", "launch"],
        "science": ["climate", "vaccine", "pandemic", "nasa", "space"],
    }
    for cat, keywords in category_keywords.items():
        for kw in keywords:
            if kw in text_lower:
                return cat
    return "other"


class PredictionMarketAggregator:
    """
    Aggregates prediction markets from Polymarket, Manifold Markets, and Metaculus.
    Detects cross-platform price discrepancies (arbitrage opportunities).

    Usage:
        cfg = Config()
        agg = PredictionMarketAggregator(cfg)
        signals = agg.fetch_all()
    """

    def __init__(self, config: Config):
        self.config = config
        pm_cfg = config._raw_strategy.get("prediction_markets", {})
        self.platforms = pm_cfg.get("platforms", ["polymarket", "manifold", "metaculus"])
        self.arb_threshold_pct = pm_cfg.get("arbitrage_threshold_pct", 5.0)
        self.max_markets_per_platform = pm_cfg.get("max_markets_per_platform", 50)

        # Initialize Polymarket client if enabled
        self._poly_client: Optional[PolymarketClient] = None
        if config.polymarket.enabled and "polymarket" in self.platforms:
            try:
                self._poly_client = PolymarketClient(config)
            except Exception as e:
                _log(f"failed to init Polymarket client: {e}")

        _log(f"initialized with platforms: {self.platforms}")

    # ------------------------------------------------------------------
    # Polymarket
    # ------------------------------------------------------------------

    def _fetch_polymarket(self) -> List[Dict[str, Any]]:
        if self._poly_client is None:
            return []

        _log("fetching Polymarket markets...")
        try:
            markets = self._poly_client.list_markets(limit=self.max_markets_per_platform)
        except Exception as e:
            _log(f"Polymarket fetch failed: {e}")
            return []

        results = []
        for m in markets:
            if not m.question or m.closed:
                continue

            # Get YES token price as probability
            prob = None
            for tok in m.tokens:
                outcome = tok.get("outcome", "").lower()
                if outcome == "yes":
                    token_id = tok.get("token_id", "")
                    if token_id:
                        try:
                            price = self._poly_client.get_midpoint_price(token_id)
                            if price is not None:
                                prob = round(price, 4)
                        except Exception:
                            pass
                    break

            if prob is not None:
                results.append({
                    "question": m.question,
                    "probability": prob,
                    "platform": "polymarket",
                    "category": _classify_category(m.question),
                    "volume": None,
                })

        _log(f"  polymarket: {len(results)} markets with prices")
        return results

    # ------------------------------------------------------------------
    # Manifold Markets
    # ------------------------------------------------------------------

    def _fetch_manifold(self) -> List[Dict[str, Any]]:
        if "manifold" not in self.platforms:
            return []

        _log("fetching Manifold Markets...")
        url = f"https://api.manifold.markets/v0/markets?limit={self.max_markets_per_platform}&sort=liquidity"
        data = _http_get(url)
        if not data or not isinstance(data, list):
            _log("  manifold: no data returned")
            return []

        results = []
        for m in data:
            if m.get("isResolved") or m.get("closeTime", 0) < time.time() * 1000:
                continue

            question = m.get("question", "")
            prob = m.get("probability")
            if question and prob is not None:
                results.append({
                    "question": question,
                    "probability": round(float(prob), 4),
                    "platform": "manifold",
                    "category": _classify_category(question),
                    "volume": m.get("volume"),
                })

        _log(f"  manifold: {len(results)} markets")
        return results

    # ------------------------------------------------------------------
    # Metaculus
    # ------------------------------------------------------------------

    def _fetch_metaculus(self) -> List[Dict[str, Any]]:
        if "metaculus" not in self.platforms:
            return []

        _log("fetching Metaculus questions...")
        url = f"https://www.metaculus.com/api2/questions/?limit={self.max_markets_per_platform}&status=open&type=forecast&order_by=-activity"
        data = _http_get(url, timeout=20)
        if not data:
            _log("  metaculus: no data returned")
            return []

        questions = data.get("results", [])
        results = []
        for q in questions:
            title = q.get("title", "")
            # Metaculus uses community_prediction.full.q2 as median forecast
            cp = q.get("community_prediction") or {}
            full = cp.get("full") or {}
            median = full.get("q2")

            if title and median is not None:
                results.append({
                    "question": title,
                    "probability": round(float(median), 4),
                    "platform": "metaculus",
                    "category": _classify_category(title),
                    "volume": q.get("number_of_predictions"),
                })

        _log(f"  metaculus: {len(results)} questions")
        return results

    # ------------------------------------------------------------------
    # Cross-platform matching and arbitrage detection
    # ------------------------------------------------------------------

    def _normalize_question(self, question: str) -> str:
        """Normalize a question for fuzzy matching across platforms."""
        q = question.lower().strip()
        q = re.sub(r'[^\w\s]', '', q)
        q = re.sub(r'\s+', ' ', q)
        # Remove common prefixes/suffixes
        for prefix in ["will ", "is ", "does ", "do ", "can "]:
            if q.startswith(prefix):
                q = q[len(prefix):]
        return q

    def _find_matches(self, all_markets: List[Dict[str, Any]]) -> List[PredictionMarketSignal]:
        """
        Group markets by similar questions across platforms and detect
        arbitrage (price spread > threshold).
        """
        # Group by normalized question, keeping first per platform
        grouped: Dict[str, Dict[str, Dict[str, Any]]] = {}  # norm_q -> {platform -> market}

        for m in all_markets:
            norm_q = self._normalize_question(m["question"])
            if norm_q not in grouped:
                grouped[norm_q] = {}
            platform = m["platform"]
            if platform not in grouped[norm_q]:
                grouped[norm_q][platform] = m

        signals = []
        for norm_q, platforms in grouped.items():
            prices = {p: m["probability"] for p, m in platforms.items()}
            probs = list(prices.values())
            avg_prob = round(sum(probs) / len(probs), 4)
            spread = round((max(probs) - min(probs)) * 100, 2) if len(probs) > 1 else 0.0
            is_arb = spread >= self.arb_threshold_pct and len(probs) > 1

            # Use the longest question text for display
            best_question = max(platforms.values(), key=lambda m: len(m["question"]))["question"]
            category = list(platforms.values())[0]["category"]

            # Sum volume across platforms
            total_volume = None
            for m in platforms.values():
                if m.get("volume") is not None:
                    total_volume = (total_volume or 0) + m["volume"]

            signals.append(PredictionMarketSignal(
                question=best_question,
                platform_prices=prices,
                avg_probability=avg_prob,
                spread_pct=spread,
                arbitrage_opportunity=is_arb,
                category=category,
                volume=total_volume,
                platforms_count=len(platforms),
            ))

        # Sort: arbitrage opportunities first, then by spread
        signals.sort(key=lambda s: (-int(s.arbitrage_opportunity), -s.spread_pct))
        return signals

    # ------------------------------------------------------------------
    # Main fetch
    # ------------------------------------------------------------------

    def fetch_all(self) -> List[PredictionMarketSignal]:
        _log("aggregating prediction markets...")
        all_markets: List[Dict[str, Any]] = []

        # Fetch from each platform (errors handled internally)
        all_markets.extend(self._fetch_polymarket())
        all_markets.extend(self._fetch_manifold())
        all_markets.extend(self._fetch_metaculus())

        _log(f"total raw markets: {len(all_markets)}")

        if not all_markets:
            return []

        signals = self._find_matches(all_markets)

        # Log arbitrage opportunities
        arb_count = sum(1 for s in signals if s.arbitrage_opportunity)
        multi_platform = sum(1 for s in signals if s.platforms_count > 1)
        _log(f"summary: {len(signals)} unique questions, {multi_platform} cross-platform, {arb_count} arbitrage opportunities")

        for s in signals:
            if s.arbitrage_opportunity:
                _log(f"  ARB [{s.spread_pct:.1f}%] {s.question[:60]}  prices={s.platform_prices}")

        return signals

    def fetch_by_category(self, category: str) -> List[PredictionMarketSignal]:
        all_signals = self.fetch_all()
        return [s for s in all_signals if s.category == category]

    def get_arbitrage_opportunities(self, min_spread_pct: Optional[float] = None) -> List[PredictionMarketSignal]:
        threshold = min_spread_pct or self.arb_threshold_pct
        all_signals = self.fetch_all()
        return [s for s in all_signals if s.spread_pct >= threshold and s.platforms_count > 1]

    def signals_to_json(self, signals: List[PredictionMarketSignal]) -> str:
        return json.dumps([s.to_dict() for s in signals], indent=2)


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    agg = PredictionMarketAggregator(cfg)
    signals = agg.fetch_all()

    print(f"\n{len(signals)} unique prediction markets found")
    arb = [s for s in signals if s.arbitrage_opportunity]
    if arb:
        print(f"\n{len(arb)} arbitrage opportunities:")
        for s in arb:
            print(f"  [{s.spread_pct:.1f}% spread] {s.question[:70]}")
            for plat, price in s.platform_prices.items():
                print(f"    {plat}: {price:.2%}")
    else:
        print("No cross-platform arbitrage opportunities found.")
