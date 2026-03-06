"""
Polymarket CLOB API client (read-only).

Wraps the Polymarket CLOB API at clob.polymarket.com for:
- Market listing and search
- Order book fetching
- Price queries

No order placement is implemented yet. Includes proper rate limiting:
- Public endpoints: 60 req/min
- /books endpoint: 300 req/10s

Reference: https://docs.polymarket.com/developers/CLOB/introduction
"""

import json
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from src.core.config import Config


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] polymarket: {msg}")


class RateLimiter:
    """
    Token-bucket rate limiter supporting multiple rate limit tiers.

    Tracks separate buckets for different endpoint categories
    (public general: 60/min, books: 300/10s).
    """

    def __init__(self):
        self._locks: Dict[str, threading.Lock] = {}
        self._timestamps: Dict[str, List[float]] = {}
        self._limits: Dict[str, tuple] = {
            "public": (60, 60.0),      # 60 requests per 60 seconds
            "books": (300, 10.0),      # 300 requests per 10 seconds
        }

    def _get_lock(self, bucket: str) -> threading.Lock:
        if bucket not in self._locks:
            self._locks[bucket] = threading.Lock()
            self._timestamps[bucket] = []
        return self._locks[bucket]

    def wait(self, bucket: str = "public") -> None:
        """Block until a request is allowed under the rate limit."""
        if bucket not in self._limits:
            bucket = "public"

        max_requests, window_seconds = self._limits[bucket]
        lock = self._get_lock(bucket)

        with lock:
            now = time.monotonic()
            # Prune old timestamps outside the window
            cutoff = now - window_seconds
            self._timestamps[bucket] = [
                ts for ts in self._timestamps[bucket] if ts > cutoff
            ]

            if len(self._timestamps[bucket]) >= max_requests:
                # Must wait until the oldest request in the window expires
                oldest = self._timestamps[bucket][0]
                sleep_time = oldest + window_seconds - now + 0.05  # small buffer
                if sleep_time > 0:
                    _log(f"rate limit ({bucket}): sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                # Re-prune after sleeping
                now = time.monotonic()
                cutoff = now - window_seconds
                self._timestamps[bucket] = [
                    ts for ts in self._timestamps[bucket] if ts > cutoff
                ]

            self._timestamps[bucket].append(time.monotonic())


@dataclass
class Market:
    """Represents a Polymarket market/condition."""
    condition_id: str
    question: str
    description: str
    tokens: List[Dict[str, str]] = field(default_factory=list)
    end_date: str = ""
    active: bool = True
    closed: bool = False
    game_start_time: str = ""
    category: str = ""
    slug: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "question": self.question,
            "description": self.description,
            "tokens": self.tokens,
            "end_date": self.end_date,
            "active": self.active,
            "closed": self.closed,
            "category": self.category,
            "slug": self.slug,
        }


@dataclass
class OrderBookLevel:
    """A single price level in the order book."""
    price: float
    size: float


@dataclass
class OrderBook:
    """Order book for a token (YES or NO side of a market)."""
    token_id: str
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    timestamp: str = ""

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid is not None and self.best_ask is not None:
            return round(self.best_ask - self.best_bid, 4)
        return None

    @property
    def midpoint(self) -> Optional[float]:
        if self.best_bid is not None and self.best_ask is not None:
            return round((self.best_bid + self.best_ask) / 2, 4)
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "spread": self.spread,
            "midpoint": self.midpoint,
            "bid_depth": len(self.bids),
            "ask_depth": len(self.asks),
            "bids": [{"price": b.price, "size": b.size} for b in self.bids[:10]],
            "asks": [{"price": a.price, "size": a.size} for a in self.asks[:10]],
        }


class PolymarketClient:
    """
    Read-only client for the Polymarket CLOB API.

    Provides methods to list markets, fetch order books, and query
    prices. All requests are rate-limited per the documented limits.

    Usage:
        cfg = Config()
        client = PolymarketClient(cfg)
        markets = client.list_markets(limit=10)
        book = client.get_order_book(token_id)
        price = client.get_midpoint_price(token_id)
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_base = config.polymarket.api_base  # https://clob.polymarket.com
        self.data_api = config.polymarket.data_api   # https://data-api.polymarket.com
        self.rate_limiter = RateLimiter()
        self._user_agent = "TradingBot/1.0"
        _log(f"initialized client: api={self.api_base}")

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        url: str,
        rate_bucket: str = "public",
        timeout: float = 15.0,
    ) -> Any:
        """
        Make a rate-limited GET request and return parsed JSON.

        Raises:
            HTTPError: On 4xx/5xx responses.
            URLError: On network failures.
            json.JSONDecodeError: On unparseable responses.
        """
        self.rate_limiter.wait(rate_bucket)

        req = Request(url)
        req.add_header("User-Agent", self._user_agent)
        req.add_header("Accept", "application/json")

        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            _log(f"HTTP {e.code} for {url}: {body}")
            raise
        except URLError as e:
            _log(f"network error for {url}: {e.reason}")
            raise

    def _clob_url(self, path: str, **params: Any) -> str:
        """Build a CLOB API URL with optional query parameters."""
        url = f"{self.api_base}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urlencode(clean)
        return url

    # ------------------------------------------------------------------
    # Market listing
    # ------------------------------------------------------------------

    def list_markets(
        self,
        limit: int = 25,
        offset: int = 0,
        active: bool = True,
        closed: Optional[bool] = None,
    ) -> List[Market]:
        """
        List available markets from the CLOB API.

        Args:
            limit: Max number of markets to return (max 100).
            offset: Pagination offset.
            active: Only return active markets.
            closed: Filter by closed status (None = no filter).

        Returns:
            List of Market objects.
        """
        params: Dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
        }
        if active:
            params["active"] = "true"
        if closed is not None:
            params["closed"] = "true" if closed else "false"

        url = self._clob_url("/markets", **params)
        _log(f"listing markets (limit={limit}, offset={offset})")

        try:
            data = self._request(url)
        except Exception as e:
            _log(f"failed to list markets: {e}")
            return []

        markets = []
        items = data if isinstance(data, list) else data.get("data", data.get("markets", []))

        for item in items:
            if not isinstance(item, dict):
                continue
            tokens = item.get("tokens", [])
            market = Market(
                condition_id=item.get("condition_id", ""),
                question=item.get("question", ""),
                description=item.get("description", "")[:500],
                tokens=tokens,
                end_date=item.get("end_date_iso", item.get("end_date", "")),
                active=item.get("active", True),
                closed=item.get("closed", False),
                category=item.get("category", ""),
                slug=item.get("slug", ""),
            )
            markets.append(market)

        _log(f"received {len(markets)} markets")
        return markets

    def search_markets(self, query: str, limit: int = 25) -> List[Market]:
        """
        Search markets by keyword.

        The CLOB API may not have a direct search endpoint, so we
        list markets and filter client-side.
        """
        # Fetch a larger batch and filter
        all_markets = self.list_markets(limit=100)
        query_lower = query.lower()
        matched = [
            m for m in all_markets
            if query_lower in m.question.lower() or query_lower in m.description.lower()
        ]
        return matched[:limit]

    def get_market(self, condition_id: str) -> Optional[Market]:
        """Fetch a single market by condition ID."""
        url = self._clob_url(f"/markets/{condition_id}")
        try:
            data = self._request(url)
        except Exception as e:
            _log(f"failed to get market {condition_id}: {e}")
            return None

        if not isinstance(data, dict):
            return None

        tokens = data.get("tokens", [])
        return Market(
            condition_id=data.get("condition_id", condition_id),
            question=data.get("question", ""),
            description=data.get("description", "")[:500],
            tokens=tokens,
            end_date=data.get("end_date_iso", data.get("end_date", "")),
            active=data.get("active", True),
            closed=data.get("closed", False),
            category=data.get("category", ""),
            slug=data.get("slug", ""),
        )

    # ------------------------------------------------------------------
    # Order book
    # ------------------------------------------------------------------

    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        """
        Fetch the order book for a specific token.

        Uses the /books rate limit bucket (300 req/10s).

        Args:
            token_id: The token ID (YES or NO side of a market).

        Returns:
            OrderBook object, or None on failure.
        """
        url = self._clob_url("/book", token_id=token_id)
        try:
            data = self._request(url, rate_bucket="books")
        except Exception as e:
            _log(f"failed to get book for {token_id}: {e}")
            return None

        if not isinstance(data, dict):
            return None

        bids = []
        for b in data.get("bids", []):
            try:
                bids.append(OrderBookLevel(
                    price=float(b.get("price", 0)),
                    size=float(b.get("size", 0)),
                ))
            except (ValueError, TypeError):
                continue

        asks = []
        for a in data.get("asks", []):
            try:
                asks.append(OrderBookLevel(
                    price=float(a.get("price", 0)),
                    size=float(a.get("size", 0)),
                ))
            except (ValueError, TypeError):
                continue

        # Sort bids descending, asks ascending
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)

        return OrderBook(
            token_id=token_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def get_books_batch(self, token_ids: List[str]) -> Dict[str, OrderBook]:
        """Fetch order books for multiple tokens."""
        results = {}
        for tid in token_ids:
            book = self.get_order_book(tid)
            if book:
                results[tid] = book
        return results

    # ------------------------------------------------------------------
    # Price queries
    # ------------------------------------------------------------------

    def get_midpoint_price(self, token_id: str) -> Optional[float]:
        """Get the midpoint price for a token from the order book."""
        book = self.get_order_book(token_id)
        if book:
            return book.midpoint
        return None

    def get_prices(self, token_ids: List[str]) -> Dict[str, Optional[float]]:
        """Get midpoint prices for multiple tokens."""
        prices = {}
        for tid in token_ids:
            prices[tid] = self.get_midpoint_price(tid)
        return prices

    def get_spread(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed spread information for a token.

        Returns dict with best_bid, best_ask, spread, midpoint,
        spread_pct.
        """
        book = self.get_order_book(token_id)
        if not book:
            return None

        result = book.to_dict()
        if book.best_bid and book.midpoint and book.midpoint > 0:
            result["spread_pct"] = round(
                (book.spread or 0) / book.midpoint * 100, 2
            )
        else:
            result["spread_pct"] = None
        return result

    # ------------------------------------------------------------------
    # Market analysis helpers
    # ------------------------------------------------------------------

    def get_market_with_prices(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a market and its current prices for all tokens.

        Returns a combined dict with market info and live pricing.
        """
        market = self.get_market(condition_id)
        if not market:
            return None

        result = market.to_dict()
        result["prices"] = {}

        for token in market.tokens:
            token_id = token.get("token_id", "")
            outcome = token.get("outcome", "")
            if token_id:
                book = self.get_order_book(token_id)
                if book:
                    result["prices"][outcome] = {
                        "midpoint": book.midpoint,
                        "best_bid": book.best_bid,
                        "best_ask": book.best_ask,
                        "spread": book.spread,
                    }

        return result

    def find_crypto_markets(self, symbols: Optional[List[str]] = None) -> List[Market]:
        """
        Find crypto price prediction markets.

        Args:
            symbols: Crypto symbols to search for (default: BTC, ETH, SOL).

        Returns:
            List of matching markets.
        """
        if symbols is None:
            symbols = ["BTC", "ETH", "SOL", "Bitcoin", "Ethereum"]

        all_markets = self.list_markets(limit=100)
        matched = []
        for m in all_markets:
            q_lower = m.question.lower()
            for sym in symbols:
                if sym.lower() in q_lower:
                    matched.append(m)
                    break
        return matched

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """
        Quick health check: fetch a small number of markets to verify
        API connectivity.
        """
        start = time.monotonic()
        try:
            markets = self.list_markets(limit=1)
            elapsed = time.monotonic() - start
            return {
                "status": "ok",
                "latency_ms": round(elapsed * 1000, 1),
                "markets_accessible": len(markets) > 0,
                "api_base": self.api_base,
            }
        except Exception as e:
            elapsed = time.monotonic() - start
            return {
                "status": "error",
                "error": str(e),
                "latency_ms": round(elapsed * 1000, 1),
                "api_base": self.api_base,
            }


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

    client = PolymarketClient(cfg)

    # Health check
    health = client.health_check()
    print(f"\nHealth: {json.dumps(health, indent=2)}")

    if health["status"] == "ok":
        # List some markets
        markets = client.list_markets(limit=5)
        print(f"\nSample markets ({len(markets)}):")
        for m in markets:
            print(f"  - {m.question[:70]}...")
            if m.tokens:
                for tok in m.tokens:
                    tid = tok.get("token_id", "")
                    outcome = tok.get("outcome", "")
                    if tid:
                        price = client.get_midpoint_price(tid)
                        print(f"    {outcome}: midpoint=${price}")
