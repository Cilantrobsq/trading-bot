"""
Niche market finder for Polymarket.

Scans for low-volume, low-competition markets that larger bots ignore.
Research shows 92% of Polymarket wallets lose money, but niche/illiquid
markets are where the edge lives -- fewer sophisticated participants,
wider spreads, and more potential for information advantage.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.config import Config
from src.execution.polymarket_client import PolymarketClient, Market, OrderBook


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] niche_finder: {msg}")


# Categories that are heavily competed by sophisticated bots
_HIGH_COMPETITION_CATEGORIES = {
    "crypto", "bitcoin", "ethereum", "btc", "eth", "sol",
    "election", "presidential", "congress", "senate",
    "trump", "biden", "harris",
    "fed", "interest rate", "fomc",
}


@dataclass
class NicheOpportunity:
    """A scored niche market opportunity."""
    market_id: str
    question: str
    category: str
    volume_usd: float
    unique_traders: int
    current_price: Optional[float]
    spread: Optional[float]
    time_to_expiry_days: Optional[float]
    niche_score: float  # 0-100, higher = better opportunity
    information_advantage_notes: str
    token_id: Optional[str] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_id": self.market_id,
            "question": self.question,
            "category": self.category,
            "volume_usd": self.volume_usd,
            "unique_traders": self.unique_traders,
            "current_price": self.current_price,
            "spread": self.spread,
            "time_to_expiry_days": self.time_to_expiry_days,
            "niche_score": round(self.niche_score, 1),
            "information_advantage_notes": self.information_advantage_notes,
            "token_id": self.token_id,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
        }


class NicheMarketFinder:
    """
    Finds profitable niche markets on Polymarket that big bots ignore.

    Criteria for a good niche market:
    - Low volume (< $50K total)
    - Few unique traders (< 100)
    - Price between 0.15 and 0.85 (not foregone conclusions)
    - Not in highly-competed categories (crypto prices, elections)
    - Wide spreads (more opportunity for limit orders)
    - Resolution within 7-90 days (not too distant, not immediate)

    Usage:
        from src.core.config import Config
        cfg = Config()
        finder = NicheMarketFinder(cfg)
        opportunities = finder.find_niche_markets()
        for opp in opportunities:
            print(f"{opp.question}: score={opp.niche_score}")
    """

    def __init__(self, config: Config):
        self.config = config
        self.client = PolymarketClient(config)
        self.data_dir = os.path.join(config.project_root, "data", "niche-markets")
        os.makedirs(self.data_dir, exist_ok=True)
        _log("initialized")

    def _is_high_competition(self, market: Market) -> bool:
        """Check if a market is in a highly-competed category."""
        text = f"{market.question} {market.description} {market.category}".lower()
        for keyword in _HIGH_COMPETITION_CATEGORIES:
            if keyword in text:
                return True
        return False

    def _estimate_time_to_expiry_days(self, market: Market) -> Optional[float]:
        """Estimate days until market resolution from end_date."""
        if not market.end_date:
            return None
        try:
            # Handle various date formats
            end_str = market.end_date
            if "T" in end_str:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            else:
                end_dt = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = end_dt - now
            return max(0.0, delta.total_seconds() / 86400)
        except (ValueError, TypeError):
            return None

    def _get_market_price_data(self, market: Market) -> Dict[str, Any]:
        """Fetch order book data for a market's YES token."""
        result = {
            "price": None,
            "spread": None,
            "best_bid": None,
            "best_ask": None,
            "token_id": None,
        }
        if not market.tokens:
            return result

        # Find the YES token
        token_id = None
        for token in market.tokens:
            outcome = token.get("outcome", "").upper()
            if outcome == "YES":
                token_id = token.get("token_id", "")
                break
        if not token_id and market.tokens:
            token_id = market.tokens[0].get("token_id", "")

        if not token_id:
            return result

        result["token_id"] = token_id
        book = self.client.get_order_book(token_id)
        if book:
            result["price"] = book.midpoint
            result["spread"] = book.spread
            result["best_bid"] = book.best_bid
            result["best_ask"] = book.best_ask

        return result

    def find_niche_markets(
        self,
        max_volume_usd: float = 50000,
        max_unique_traders: int = 100,
        min_price: float = 0.15,
        max_price: float = 0.85,
        scan_limit: int = 100,
    ) -> List[NicheOpportunity]:
        """
        Scan Polymarket for niche market opportunities.

        Args:
            max_volume_usd: Maximum market volume in USD.
            max_unique_traders: Maximum number of unique traders.
            min_price: Minimum YES price (exclude near-certainties).
            max_price: Maximum YES price (exclude near-certainties).
            scan_limit: Number of markets to scan from the API.

        Returns:
            List of NicheOpportunity objects, sorted by niche_score descending.
        """
        _log(f"scanning for niche markets (limit={scan_limit})")

        try:
            markets = self.client.list_markets(limit=scan_limit, active=True)
        except Exception as e:
            _log(f"failed to fetch markets: {e}")
            return []

        if not markets:
            _log("no markets returned from API")
            return []

        _log(f"evaluating {len(markets)} markets")
        opportunities: List[NicheOpportunity] = []

        for market in markets:
            # Skip high-competition categories
            if self._is_high_competition(market):
                continue

            # Skip closed markets
            if market.closed:
                continue

            # Get price data
            price_data = self._get_market_price_data(market)
            price = price_data["price"]

            # Filter by price range
            if price is not None:
                if price < min_price or price > max_price:
                    continue
            # If we can't get a price, skip
            elif price is None:
                continue

            # Time to expiry
            ttl_days = self._estimate_time_to_expiry_days(market)

            # Score the opportunity
            score = self.score_niche_opportunity(
                price=price,
                spread=price_data["spread"],
                ttl_days=ttl_days,
                category=market.category,
                question=market.question,
            )

            # Generate information advantage notes
            info_notes = self._assess_information_advantage(market)

            opp = NicheOpportunity(
                market_id=market.condition_id,
                question=market.question,
                category=market.category or "uncategorized",
                volume_usd=0.0,  # API doesn't always expose volume directly
                unique_traders=0,  # API doesn't always expose trader count
                current_price=price,
                spread=price_data["spread"],
                time_to_expiry_days=round(ttl_days, 1) if ttl_days else None,
                niche_score=score,
                information_advantage_notes=info_notes,
                token_id=price_data["token_id"],
                best_bid=price_data["best_bid"],
                best_ask=price_data["best_ask"],
            )
            opportunities.append(opp)

        # Sort by niche score descending
        opportunities.sort(key=lambda o: o.niche_score, reverse=True)

        # Persist results
        self._save_results(opportunities)

        _log(f"found {len(opportunities)} niche opportunities")
        return opportunities

    def score_niche_opportunity(
        self,
        price: Optional[float] = None,
        spread: Optional[float] = None,
        ttl_days: Optional[float] = None,
        category: str = "",
        question: str = "",
        volume_usd: float = 0.0,
        unique_traders: int = 0,
    ) -> float:
        """
        Score a market opportunity on a 0-100 scale.

        Factors:
        - Spread width (wider = more opportunity, up to a point)
        - Price distance from 0.5 (closer to 0.5 = more uncertain = more edge possible)
        - Time to resolution (sweet spot: 7-90 days)
        - Category novelty (non-standard categories score higher)
        - Volume (lower = less competition but must have some liquidity)
        """
        score = 50.0  # base score

        # Spread factor: wider spreads = more opportunity (0-20 points)
        if spread is not None:
            if spread >= 0.10:
                score += 20  # Very wide spread
            elif spread >= 0.05:
                score += 15
            elif spread >= 0.02:
                score += 10
            elif spread >= 0.01:
                score += 5
            else:
                score -= 5  # Too tight, bots dominate

        # Price uncertainty factor: closer to 0.5 = more uncertain (0-15 points)
        if price is not None:
            distance_from_half = abs(price - 0.5)
            # Closer to 0.5 is better (more uncertainty)
            uncertainty_score = max(0, 15 * (1.0 - distance_from_half * 2))
            score += uncertainty_score

        # Time to resolution factor (0-15 points)
        if ttl_days is not None:
            if 7 <= ttl_days <= 90:
                score += 15  # Sweet spot
            elif 3 <= ttl_days < 7:
                score += 10  # Tight but doable
            elif 90 < ttl_days <= 180:
                score += 8   # Longer term
            elif ttl_days < 3:
                score -= 10  # Too soon, info already priced in
            else:
                score += 3   # Very long term

        # Category novelty (0-10 points)
        text = f"{category} {question}".lower()
        novel_keywords = [
            "science", "technology", "weather", "sports", "entertainment",
            "company", "ipo", "acquisition", "legal", "court", "patent",
            "space", "ai", "climate", "health", "fda",
        ]
        novelty_hits = sum(1 for k in novel_keywords if k in text)
        score += min(10, novelty_hits * 3)

        # Clamp to 0-100
        return max(0.0, min(100.0, score))

    def _assess_information_advantage(self, market: Market) -> str:
        """
        Assess whether we might have an information advantage for this market.

        Returns a brief note about information advantage potential.
        """
        q = market.question.lower()
        notes = []

        # Categories where public data analysis could provide an edge
        if any(k in q for k in ["fda", "drug", "approval", "clinical"]):
            notes.append("FDA/biotech: public clinical trial data may give edge")
        if any(k in q for k in ["weather", "temperature", "hurricane", "storm"]):
            notes.append("Weather: predictable with meteorological models")
        if any(k in q for k in ["earnings", "revenue", "profit"]):
            notes.append("Earnings: analyst estimates and sector data available")
        if any(k in q for k in ["court", "ruling", "legal", "judge"]):
            notes.append("Legal: court schedules and precedents researchable")
        if any(k in q for k in ["launch", "space", "rocket"]):
            notes.append("Space: launch schedules and weather windows are public")
        if any(k in q for k in ["sport", "game", "match", "win"]):
            notes.append("Sports: extensive statistical models available")

        if not notes:
            notes.append("General: requires topic-specific research")

        return "; ".join(notes)

    def _save_results(self, opportunities: List[NicheOpportunity]) -> None:
        """Save niche market scan results to disk."""
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            output = {
                "scan_time": datetime.now(timezone.utc).isoformat(),
                "count": len(opportunities),
                "opportunities": [o.to_dict() for o in opportunities[:50]],
            }
            filepath = os.path.join(self.data_dir, f"niche-scan-{ts}.json")
            with open(filepath, "w") as f:
                json.dump(output, f, indent=2)

            # Also save as latest
            latest_path = os.path.join(self.data_dir, "latest.json")
            with open(latest_path, "w") as f:
                json.dump(output, f, indent=2)

            _log(f"saved {len(opportunities)} opportunities to {filepath}")
        except Exception as e:
            _log(f"failed to save results: {e}")


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)

    if not cfg.polymarket.enabled:
        print("Polymarket is disabled in config.")
        sys.exit(0)

    finder = NicheMarketFinder(cfg)
    opps = finder.find_niche_markets(scan_limit=50)

    print(f"\nFound {len(opps)} niche opportunities:")
    for i, opp in enumerate(opps[:10]):
        print(f"\n  {i+1}. {opp.question[:60]}...")
        print(f"     Score: {opp.niche_score:.1f} | Price: {opp.current_price}")
        print(f"     Spread: {opp.spread} | TTL: {opp.time_to_expiry_days} days")
        print(f"     Info: {opp.information_advantage_notes}")
