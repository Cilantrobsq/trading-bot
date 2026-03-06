"""
Polymarket Gamma API client (read-only).

The CLOB API returns stale data. The Gamma API at gamma-api.polymarket.com
provides live market listings with outcome prices, volume, and liquidity.

Fetches:
- All active markets with live prices
- Crypto (BTC up/down) markets
- Finance/economics/geopolitics markets
- Cross-references with Kalshi for arbitrage detection
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] polymarket_gamma: {msg}")


# Categories we care about for trading signals
FINANCE_KEYWORDS = {
    "crypto": ["bitcoin", "btc ", "ethereum", "eth ", " crypto", "solana", "sol ",
               "xrp", "dogecoin", "doge ", "defi", "blockchain", "nft ",
               "megaeth", "stablecoin", "usdc", "usdt"],
    "economics": ["recession", "inflation", "fed", "interest rate", "gdp",
                   "unemployment", "cpi", "tariff", "trade war", "deficit",
                   "debt ceiling", "treasury", "fomc"],
    "markets": ["s&p", "sp500", "nasdaq", "dow", "stock market", "bear market",
                "bull market", "crash", "correction", "ath", "all-time high"],
    "geopolitics": ["war", "sanctions", "nato", "ceasefire", "invasion",
                     "nuclear", "missile", "coup", "regime"],
    "tech": ["ai ", "artificial intelligence", "openai", "chatgpt", "gpt",
             "apple", "google", "meta", "microsoft", "tesla", "nvidia"],
    "energy": ["oil", "opec", "gas price", "energy", "solar", "nuclear power"],
}


@dataclass
class PolymarketMarket:
    """A market from the Polymarket Gamma API."""
    condition_id: str
    question: str
    outcomes: List[str]
    outcome_prices: List[float]
    volume: float
    liquidity: float
    end_date: str
    category: str
    slug: str
    active: bool
    closed: bool
    image: str = ""
    description: str = ""

    @property
    def yes_price(self) -> Optional[float]:
        if len(self.outcome_prices) >= 1:
            return self.outcome_prices[0]
        return None

    @property
    def no_price(self) -> Optional[float]:
        if len(self.outcome_prices) >= 2:
            return self.outcome_prices[1]
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "question": self.question,
            "outcomes": self.outcomes,
            "outcome_prices": self.outcome_prices,
            "yes_price": self.yes_price,
            "no_price": self.no_price,
            "volume": self.volume,
            "liquidity": self.liquidity,
            "end_date": self.end_date,
            "category": self.category,
            "slug": self.slug,
        }


def _classify(question: str) -> str:
    """Classify a market question into a category."""
    q_lower = question.lower()
    for cat, keywords in FINANCE_KEYWORDS.items():
        for kw in keywords:
            if kw in q_lower:
                return cat
    return "other"


class PolymarketGammaClient:
    """
    Client for Polymarket's Gamma API (gamma-api.polymarket.com).

    The _q search parameter does not work for filtering, so we fetch
    a large batch and filter client-side.
    """

    API_BASE = "https://gamma-api.polymarket.com"

    def __init__(self):
        self._last_request = 0.0
        self._min_interval = 0.5  # conservative rate limit
        _log("initialized gamma client")

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Any:
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

        url = f"{self.API_BASE}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urlencode(clean)

        req = Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "TradingBot/1.0")

        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError) as e:
            _log(f"error fetching {url[:80]}: {e}")
            return None

    def _parse_market(self, raw: Dict[str, Any]) -> PolymarketMarket:
        """Parse a raw API response into a PolymarketMarket."""
        prices_raw = raw.get("outcomePrices", "[]")
        if isinstance(prices_raw, str):
            try:
                prices = [float(p) for p in json.loads(prices_raw)]
            except (json.JSONDecodeError, ValueError):
                prices = []
        elif isinstance(prices_raw, list):
            prices = [float(p) for p in prices_raw]
        else:
            prices = []

        outcomes_raw = raw.get("outcomes", "[]")
        if isinstance(outcomes_raw, str):
            try:
                outcomes = json.loads(outcomes_raw)
            except json.JSONDecodeError:
                outcomes = []
        elif isinstance(outcomes_raw, list):
            outcomes = outcomes_raw
        else:
            outcomes = []

        question = raw.get("question", "")

        return PolymarketMarket(
            condition_id=raw.get("conditionId", raw.get("condition_id", "")),
            question=question,
            outcomes=outcomes,
            outcome_prices=prices,
            volume=float(raw.get("volume", 0) or 0),
            liquidity=float(raw.get("liquidity", 0) or 0),
            end_date=raw.get("endDate", raw.get("end_date", "")),
            category=_classify(question),
            slug=raw.get("slug", ""),
            active=raw.get("active", True),
            closed=raw.get("closed", False),
            image=raw.get("image", ""),
            description=(raw.get("description", "") or "")[:200],
        )

    def fetch_markets(self, limit: int = 100, offset: int = 0) -> List[PolymarketMarket]:
        """Fetch active markets from Gamma API."""
        data = self._request("/markets", {
            "limit": min(limit, 100),
            "offset": offset,
            "active": "true",
            "closed": "false",
        })
        if not data or not isinstance(data, list):
            return []
        return [self._parse_market(m) for m in data]

    def fetch_all_markets(self, max_pages: int = 5) -> List[PolymarketMarket]:
        """Fetch multiple pages of markets to get comprehensive coverage."""
        all_markets = []
        for page in range(max_pages):
            markets = self.fetch_markets(limit=100, offset=page * 100)
            if not markets:
                break
            all_markets.extend(markets)
            _log(f"  page {page+1}: {len(markets)} markets (total: {len(all_markets)})")
        return all_markets

    def fetch_finance_markets(self) -> List[PolymarketMarket]:
        """Fetch all markets and filter to finance-relevant ones."""
        all_markets = self.fetch_all_markets(max_pages=5)
        finance = [m for m in all_markets if m.category != "other"]
        _log(f"filtered to {len(finance)} finance-relevant markets from {len(all_markets)} total")
        return finance

    def fetch_crypto_markets(self) -> List[PolymarketMarket]:
        """Get crypto-specific markets (BTC up/down, price targets, etc)."""
        all_markets = self.fetch_all_markets(max_pages=5)
        crypto = [m for m in all_markets if m.category == "crypto"]
        _log(f"found {len(crypto)} crypto markets")
        return crypto

    def full_scan(self) -> Dict[str, Any]:
        """Full scan: fetch all markets, categorize, compute stats."""
        _log("starting full polymarket scan...")
        all_markets = self.fetch_all_markets(max_pages=5)

        by_category: Dict[str, List[Dict]] = {}
        total_volume = 0.0
        total_liquidity = 0.0

        for m in all_markets:
            cat = m.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(m.to_dict())
            total_volume += m.volume
            total_liquidity += m.liquidity

        # Sort each category by volume descending
        for cat in by_category:
            by_category[cat].sort(key=lambda x: x.get("volume", 0), reverse=True)

        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "polymarket",
            "total_markets": len(all_markets),
            "finance_markets": sum(len(v) for k, v in by_category.items() if k != "other"),
            "total_volume": round(total_volume, 2),
            "total_liquidity": round(total_liquidity, 2),
            "categories": {cat: len(markets) for cat, markets in by_category.items()},
            "markets": {cat: markets[:20] for cat, markets in by_category.items() if cat != "other"},
            # Keep top "other" markets by volume for discovery
            "top_other": by_category.get("other", [])[:10],
        }

        _log(f"scan complete: {len(all_markets)} markets, "
             f"{output['finance_markets']} finance-relevant, "
             f"vol=${total_volume:,.0f}")

        return output


if __name__ == "__main__":
    client = PolymarketGammaClient()
    result = client.full_scan()

    print(f"\nTotal: {result['total_markets']} markets")
    print(f"Finance-relevant: {result['finance_markets']}")
    print(f"Categories: {result['categories']}")
    print(f"\nFinance markets by category:")
    for cat, markets in result["markets"].items():
        print(f"\n  {cat} ({len(markets)}):")
        for m in markets[:5]:
            print(f"    {m['question'][:60]}")
            print(f"      prices={m['outcome_prices']} vol={m['volume']:.0f}")
