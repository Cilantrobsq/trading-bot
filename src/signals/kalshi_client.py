"""
Kalshi Elections API client (read-only).

Fetches prediction market data from Kalshi's public elections API:
- BTC/ETH/S&P price range markets (daily settlement)
- Event listing and market details
- Implied probability distributions from market prices

No authentication required for read access.
Reference: https://trading-api.readme.io/reference/getevents
"""

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] kalshi: {msg}")


# Series tickers for financial markets
KALSHI_SERIES = {
    "btc": "KXBTC",
    "eth": "KXETH",
    "sp500": "KXINX",
}


@dataclass
class KalshiBucket:
    """A single price bucket in a Kalshi range market."""
    ticker: str
    label: str           # e.g. "$62,250 to 62,749.99"
    low: float           # lower bound of range
    high: float          # upper bound of range (inf for top bucket)
    yes_bid: int         # cents (0-99)
    yes_ask: int         # cents (0-99)
    last_price: int      # cents
    volume: int
    midpoint: float      # (yes_bid + yes_ask) / 2 as probability

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "label": self.label,
            "low": self.low,
            "high": self.high,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "last_price": self.last_price,
            "volume": self.volume,
            "midpoint_prob": self.midpoint,
        }


@dataclass
class KalshiEvent:
    """A Kalshi event with its constituent markets."""
    title: str
    event_ticker: str
    series_ticker: str
    close_time: str
    buckets: List[KalshiBucket] = field(default_factory=list)
    total_volume: int = 0

    def implied_distribution(self) -> List[Dict[str, Any]]:
        """Return the implied probability distribution from market prices."""
        dist = []
        for b in self.buckets:
            dist.append({
                "range": b.label,
                "low": b.low,
                "high": b.high,
                "probability": b.midpoint,
                "volume": b.volume,
            })
        return dist

    def implied_expected_price(self) -> Optional[float]:
        """Calculate the probability-weighted expected price."""
        total_prob = sum(b.midpoint for b in self.buckets)
        if total_prob == 0:
            return None
        weighted = 0.0
        for b in self.buckets:
            mid_price = (b.low + b.high) / 2 if b.high < float("inf") else b.low * 1.01
            weighted += mid_price * (b.midpoint / total_prob)
        return round(weighted, 2)

    def prob_above(self, price: float) -> float:
        """Calculate implied probability that price will be above a given level."""
        total_prob = sum(b.midpoint for b in self.buckets) or 1.0
        above = sum(b.midpoint for b in self.buckets if b.low >= price)
        # Partial probability for the bucket containing the price
        for b in self.buckets:
            if b.low < price <= b.high and b.high < float("inf"):
                bucket_width = b.high - b.low
                fraction_above = (b.high - price) / bucket_width if bucket_width > 0 else 0.5
                above += b.midpoint * fraction_above
        return round(above / total_prob, 4)

    def prob_below(self, price: float) -> float:
        """Calculate implied probability that price will be below a given level."""
        return round(1.0 - self.prob_above(price), 4)

    def to_dict(self) -> Dict[str, Any]:
        exp_price = self.implied_expected_price()
        return {
            "title": self.title,
            "event_ticker": self.event_ticker,
            "series_ticker": self.series_ticker,
            "close_time": self.close_time,
            "bucket_count": len(self.buckets),
            "total_volume": self.total_volume,
            "expected_price": exp_price,
            "distribution": self.implied_distribution(),
            "buckets": [b.to_dict() for b in self.buckets],
        }


def _parse_bucket_bounds(label: str) -> Tuple[float, float]:
    """Parse price bounds from a Kalshi bucket label like '$62,250 to 62,749.99' or '$55,249.99 or below'."""
    import re

    label_clean = label.replace(",", "").replace("$", "")

    # "X or below" pattern (bottom bucket)
    m = re.match(r"([\d.]+)\s+or\s+below", label_clean, re.IGNORECASE)
    if m:
        return 0.0, float(m.group(1))

    # "X or above" pattern (top bucket)
    m = re.match(r"([\d.]+)\s+or\s+above", label_clean, re.IGNORECASE)
    if m:
        return float(m.group(1)), float("inf")

    # "X to Y" pattern
    m = re.match(r"([\d.]+)\s+to\s+([\d.]+)", label_clean)
    if m:
        return float(m.group(1)), float(m.group(2))

    return 0.0, 0.0


class KalshiClient:
    """
    Read-only client for Kalshi's elections API.

    Fetches BTC, ETH, and S&P 500 price range markets and constructs
    implied probability distributions from market prices.
    """

    API_BASE = "https://api.elections.kalshi.com/v1"

    def __init__(self):
        self._last_request = 0.0
        self._min_interval = 0.25  # 4 req/sec max
        _log("initialized kalshi client")

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Any:
        """Make a rate-limited GET request."""
        # Simple rate limiting
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

        url = f"{self.API_BASE}{path}"
        if params:
            from urllib.parse import urlencode
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urlencode(clean)

        req = Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "TradingBot/1.0")

        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            _log(f"HTTP {e.code} for {url}")
            raise
        except URLError as e:
            _log(f"network error: {e.reason}")
            raise

    def fetch_price_range_event(self, series_ticker: str) -> List[KalshiEvent]:
        """
        Fetch price range events for a given series (BTC, ETH, S&P).
        Returns a list of KalshiEvent objects with their buckets.
        """
        _log(f"fetching {series_ticker} events...")
        try:
            data = self._request("/events", {
                "limit": 5,
                "status": "open",
                "series_ticker": series_ticker,
                "with_nested_markets": "true",
            })
        except Exception as e:
            _log(f"failed to fetch {series_ticker}: {e}")
            return []

        events = []
        for e in data.get("events", []):
            title = e.get("title", "")
            event_ticker = e.get("ticker", "")
            markets = e.get("markets", [])

            buckets = []
            total_vol = 0
            for m in markets:
                label = m.get("yes_sub_title", "") or m.get("subtitle", "")
                ticker = m.get("ticker_name", "")
                yes_bid = m.get("yes_bid") or 0
                yes_ask = m.get("yes_ask") or 0
                last = m.get("last_price") or 0
                vol = m.get("volume") or 0
                total_vol += vol

                low, high = _parse_bucket_bounds(label)

                midpoint = (yes_bid + yes_ask) / 200.0 if (yes_bid + yes_ask) > 0 else last / 100.0

                buckets.append(KalshiBucket(
                    ticker=ticker,
                    label=label,
                    low=low,
                    high=high,
                    yes_bid=yes_bid,
                    yes_ask=yes_ask,
                    last_price=last,
                    volume=vol,
                    midpoint=round(midpoint, 4),
                ))

            # Sort buckets by low bound
            buckets.sort(key=lambda b: b.low)

            events.append(KalshiEvent(
                title=title,
                event_ticker=event_ticker,
                series_ticker=series_ticker,
                close_time=e.get("close_time", ""),
                buckets=buckets,
                total_volume=total_vol,
            ))

        _log(f"  {series_ticker}: {len(events)} events, {sum(len(ev.buckets) for ev in events)} total buckets")
        return events

    def fetch_all_financial(self) -> Dict[str, List[KalshiEvent]]:
        """Fetch all financial series (BTC, ETH, S&P)."""
        result = {}
        for name, ticker in KALSHI_SERIES.items():
            events = self.fetch_price_range_event(ticker)
            if events:
                result[name] = events
        return result

    def full_scan(self) -> Dict[str, Any]:
        """
        Full scan: fetch all financial markets, compute distributions
        and model comparisons.
        """
        _log("starting full kalshi scan...")
        all_events = self.fetch_all_financial()

        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "kalshi",
            "markets": {},
            "summary": {
                "total_events": 0,
                "total_buckets": 0,
                "total_volume": 0,
                "assets_tracked": list(all_events.keys()),
            },
        }

        for asset, events in all_events.items():
            market_data = []
            for ev in events:
                ed = ev.to_dict()
                market_data.append(ed)
                output["summary"]["total_events"] += 1
                output["summary"]["total_buckets"] += len(ev.buckets)
                output["summary"]["total_volume"] += ev.total_volume
            output["markets"][asset] = market_data

        _log(f"scan complete: {output['summary']['total_events']} events, "
             f"{output['summary']['total_buckets']} buckets, "
             f"vol={output['summary']['total_volume']}")

        return output


if __name__ == "__main__":
    client = KalshiClient()
    result = client.full_scan()
    print(json.dumps(result, indent=2, default=str)[:3000])

    # Show BTC implied distribution
    all_events = client.fetch_all_financial()
    if "btc" in all_events:
        btc = all_events["btc"][0]
        exp = btc.implied_expected_price()
        print(f"\nBTC implied expected price: ${exp:,.2f}" if exp else "\nNo BTC data")
        print(f"P(BTC > $90K): {btc.prob_above(90000):.1%}")
        print(f"P(BTC > $80K): {btc.prob_above(80000):.1%}")
        print(f"P(BTC > $70K): {btc.prob_above(70000):.1%}")
