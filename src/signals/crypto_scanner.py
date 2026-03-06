"""
Crypto market scanner.

Fetches comprehensive crypto market data:
- Top coins by market cap (price, 24h change, volume, market cap)
- BTC dominance and total market cap
- Fear & Greed Index
- Sector performance (DeFi, L1, L2, AI, Meme)
- Cross-market signals (crypto vs traditional correlation breaks)
- Notable large moves and volume spikes

Uses CoinGecko free API (no key required, 30 calls/min) + yfinance for
crypto-equity correlation data.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CRYPTO_DATA_FILE = os.path.join(BASE_DIR, "data", "snapshots", "latest-crypto.json")

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Top coins to track (CoinGecko IDs)
TOP_COINS = [
    "bitcoin", "ethereum", "solana", "ripple", "cardano",
    "dogecoin", "avalanche-2", "polkadot", "chainlink", "polygon",
    "uniswap", "aave", "bnb", "near", "arbitrum",
    "optimism", "cosmos", "filecoin", "litecoin", "bitcoin-cash",
    "toncoin", "sui", "aptos", "celestia", "render-token",
    "injective-protocol", "jupiter-exchange-solana", "fetch-ai",
    "pepe", "shiba-inu",
]

# Sector classification
CRYPTO_SECTORS = {
    "L1": ["bitcoin", "ethereum", "solana", "cardano", "avalanche-2", "polkadot",
            "near", "cosmos", "toncoin", "sui", "aptos", "bnb"],
    "L2": ["arbitrum", "optimism", "polygon"],
    "DeFi": ["uniswap", "aave", "chainlink", "injective-protocol", "jupiter-exchange-solana"],
    "AI": ["fetch-ai", "render-token", "near"],
    "Meme": ["dogecoin", "pepe", "shiba-inu"],
    "Store of Value": ["bitcoin", "litecoin", "bitcoin-cash"],
    "Infrastructure": ["filecoin", "chainlink", "celestia"],
}

# yfinance tickers for crypto (for correlation with equities)
CRYPTO_YF_TICKERS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
    "DOGE-USD", "AVAX-USD", "DOT-USD", "LINK-USD", "BNB-USD",
]


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] crypto_scanner: {msg}")


def _get(url: str, params: Optional[Dict] = None, timeout: int = 15) -> Optional[Dict]:
    """Safe GET request with error handling."""
    if requests is None:
        return None
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        _log(f"API error: {url} -> {e}")
        return None


class CryptoScanner:
    """
    Comprehensive crypto market scanner.

    Collects:
    - Market overview (total cap, BTC dominance, 24h volume)
    - Top 30 coins with full metrics
    - Fear & Greed Index
    - Sector performance aggregation
    - Volume anomalies and large movers
    - Crypto-equity divergence signals
    """

    def __init__(self):
        self.data: Dict[str, Any] = {}

    def fetch_market_overview(self) -> Dict[str, Any]:
        """Fetch global crypto market data from CoinGecko."""
        _log("Fetching market overview...")
        data = _get(f"{COINGECKO_BASE}/global")
        if not data or "data" not in data:
            _log("Failed to fetch market overview")
            return {}

        g = data["data"]
        overview = {
            "total_market_cap_usd": g.get("total_market_cap", {}).get("usd", 0),
            "total_volume_24h_usd": g.get("total_volume", {}).get("usd", 0),
            "btc_dominance": round(g.get("market_cap_percentage", {}).get("btc", 0), 2),
            "eth_dominance": round(g.get("market_cap_percentage", {}).get("eth", 0), 2),
            "active_cryptocurrencies": g.get("active_cryptocurrencies", 0),
            "market_cap_change_24h_pct": round(g.get("market_cap_change_percentage_24h_usd", 0), 2),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _log(f"Market cap: ${overview['total_market_cap_usd']/1e12:.2f}T, "
             f"BTC dom: {overview['btc_dominance']}%, "
             f"24h change: {overview['market_cap_change_24h_pct']:+.2f}%")
        return overview

    def fetch_top_coins(self) -> List[Dict[str, Any]]:
        """Fetch detailed data for top coins."""
        _log(f"Fetching top {len(TOP_COINS)} coins...")
        ids_str = ",".join(TOP_COINS)
        data = _get(f"{COINGECKO_BASE}/coins/markets", params={
            "vs_currency": "usd",
            "ids": ids_str,
            "order": "market_cap_desc",
            "per_page": 50,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "1h,24h,7d,30d",
        })

        if not data:
            _log("Failed to fetch coin data")
            return []

        coins = []
        for coin in data:
            coins.append({
                "id": coin.get("id"),
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name"),
                "price": coin.get("current_price"),
                "market_cap": coin.get("market_cap"),
                "market_cap_rank": coin.get("market_cap_rank"),
                "volume_24h": coin.get("total_volume"),
                "change_1h_pct": round(coin.get("price_change_percentage_1h_in_currency") or 0, 2),
                "change_24h_pct": round(coin.get("price_change_percentage_24h_in_currency") or 0, 2),
                "change_7d_pct": round(coin.get("price_change_percentage_7d_in_currency") or 0, 2),
                "change_30d_pct": round(coin.get("price_change_percentage_30d_in_currency") or 0, 2),
                "ath": coin.get("ath"),
                "ath_change_pct": round(coin.get("ath_change_percentage") or 0, 2),
                "atl": coin.get("atl"),
                "circulating_supply": coin.get("circulating_supply"),
                "total_supply": coin.get("total_supply"),
                "volume_to_mcap": round(
                    (coin.get("total_volume") or 0) / (coin.get("market_cap") or 1), 4
                ),
            })

        _log(f"Got data for {len(coins)} coins")
        return coins

    def fetch_fear_greed(self) -> Dict[str, Any]:
        """Fetch Crypto Fear & Greed Index from alternative.me."""
        _log("Fetching Fear & Greed Index...")
        data = _get("https://api.alternative.me/fng/?limit=7&format=json")
        if not data or "data" not in data:
            return {"value": None, "classification": "unknown", "history": []}

        entries = data["data"]
        current = entries[0] if entries else {}
        history = []
        for e in entries:
            history.append({
                "value": int(e.get("value", 0)),
                "classification": e.get("value_classification", ""),
                "date": datetime.fromtimestamp(int(e.get("timestamp", 0))).strftime("%Y-%m-%d"),
            })

        result = {
            "value": int(current.get("value", 0)),
            "classification": current.get("value_classification", ""),
            "history": history,
        }
        _log(f"Fear & Greed: {result['value']} ({result['classification']})")
        return result

    def compute_sector_performance(self, coins: List[Dict]) -> List[Dict[str, Any]]:
        """Aggregate performance by crypto sector."""
        _log("Computing sector performance...")
        coin_lookup = {c["id"]: c for c in coins if c.get("id")}

        sectors = []
        for sector_name, coin_ids in CRYPTO_SECTORS.items():
            sector_coins = [coin_lookup[cid] for cid in coin_ids if cid in coin_lookup]
            if not sector_coins:
                continue

            avg_24h = sum(c.get("change_24h_pct", 0) for c in sector_coins) / len(sector_coins)
            avg_7d = sum(c.get("change_7d_pct", 0) for c in sector_coins) / len(sector_coins)
            avg_30d = sum(c.get("change_30d_pct", 0) for c in sector_coins) / len(sector_coins)
            total_mcap = sum(c.get("market_cap", 0) or 0 for c in sector_coins)
            total_vol = sum(c.get("volume_24h", 0) or 0 for c in sector_coins)

            best = max(sector_coins, key=lambda c: c.get("change_24h_pct", 0))
            worst = min(sector_coins, key=lambda c: c.get("change_24h_pct", 0))

            sectors.append({
                "sector": sector_name,
                "coin_count": len(sector_coins),
                "avg_change_24h_pct": round(avg_24h, 2),
                "avg_change_7d_pct": round(avg_7d, 2),
                "avg_change_30d_pct": round(avg_30d, 2),
                "total_market_cap": total_mcap,
                "total_volume_24h": total_vol,
                "best_performer": {"symbol": best["symbol"], "change_24h": best.get("change_24h_pct", 0)},
                "worst_performer": {"symbol": worst["symbol"], "change_24h": worst.get("change_24h_pct", 0)},
            })

        sectors.sort(key=lambda s: s["avg_change_24h_pct"], reverse=True)
        return sectors

    def detect_anomalies(self, coins: List[Dict]) -> List[Dict[str, Any]]:
        """Detect notable moves, volume spikes, and other anomalies."""
        _log("Detecting anomalies...")
        anomalies = []

        for coin in coins:
            symbol = coin.get("symbol", "?")
            change_24h = coin.get("change_24h_pct", 0)
            change_1h = coin.get("change_1h_pct", 0)
            vol_ratio = coin.get("volume_to_mcap", 0)

            # Large 24h move (>10%)
            if abs(change_24h) > 10:
                anomalies.append({
                    "type": "large_move_24h",
                    "symbol": symbol,
                    "value": change_24h,
                    "severity": "high" if abs(change_24h) > 20 else "medium",
                    "description": f"{symbol} moved {change_24h:+.1f}% in 24h",
                })

            # Flash move (>5% in 1h)
            if abs(change_1h) > 5:
                anomalies.append({
                    "type": "flash_move_1h",
                    "symbol": symbol,
                    "value": change_1h,
                    "severity": "high",
                    "description": f"{symbol} flash move: {change_1h:+.1f}% in 1 hour",
                })

            # Volume spike (volume > 30% of market cap)
            if vol_ratio > 0.3:
                anomalies.append({
                    "type": "volume_spike",
                    "symbol": symbol,
                    "value": vol_ratio,
                    "severity": "medium",
                    "description": f"{symbol} volume spike: {vol_ratio:.0%} of market cap traded in 24h",
                })

            # Near ATH (within 10%)
            ath_change = coin.get("ath_change_pct", -100)
            if ath_change > -10 and ath_change < 0:
                anomalies.append({
                    "type": "near_ath",
                    "symbol": symbol,
                    "value": ath_change,
                    "severity": "low",
                    "description": f"{symbol} is {abs(ath_change):.1f}% from all-time high",
                })

        anomalies.sort(key=lambda a: {"high": 0, "medium": 1, "low": 2}.get(a["severity"], 3))
        _log(f"Found {len(anomalies)} anomalies")
        return anomalies

    def generate_signals(self, coins: List[Dict], fear_greed: Dict,
                         overview: Dict, sectors: List[Dict]) -> List[Dict[str, Any]]:
        """Generate actionable trading signals from crypto data."""
        signals = []

        # Fear & Greed extremes
        fg_value = fear_greed.get("value", 50)
        if fg_value is not None:
            if fg_value <= 20:
                signals.append({
                    "signal": "extreme_fear",
                    "direction": "bullish",
                    "strength": round((25 - fg_value) / 25, 2),
                    "description": f"Crypto Fear & Greed at {fg_value} (Extreme Fear). Historically a buying opportunity.",
                    "affected": ["BTC-USD", "ETH-USD"],
                })
            elif fg_value >= 80:
                signals.append({
                    "signal": "extreme_greed",
                    "direction": "bearish",
                    "strength": round((fg_value - 75) / 25, 2),
                    "description": f"Crypto Fear & Greed at {fg_value} (Extreme Greed). Distribution risk elevated.",
                    "affected": ["BTC-USD", "ETH-USD"],
                })

        # BTC dominance shift
        btc_dom = overview.get("btc_dominance", 0)
        if btc_dom > 60:
            signals.append({
                "signal": "btc_dominance_high",
                "direction": "alt_bearish",
                "strength": round((btc_dom - 55) / 15, 2),
                "description": f"BTC dominance at {btc_dom}%. Capital concentrating in BTC, alt season unlikely.",
                "affected": ["alts"],
            })
        elif btc_dom < 40:
            signals.append({
                "signal": "alt_season",
                "direction": "alt_bullish",
                "strength": round((45 - btc_dom) / 15, 2),
                "description": f"BTC dominance at {btc_dom}%. Alt season conditions present.",
                "affected": ["alts"],
            })

        # Sector rotation signals
        for sector in sectors:
            if sector["avg_change_24h_pct"] > 5:
                signals.append({
                    "signal": f"sector_hot_{sector['sector'].lower()}",
                    "direction": "bullish",
                    "strength": min(1.0, sector["avg_change_24h_pct"] / 10),
                    "description": f"{sector['sector']} sector up {sector['avg_change_24h_pct']:+.1f}% (24h). "
                                   f"Led by {sector['best_performer']['symbol']}.",
                    "affected": [sector["best_performer"]["symbol"]],
                })
            elif sector["avg_change_24h_pct"] < -5:
                signals.append({
                    "signal": f"sector_dump_{sector['sector'].lower()}",
                    "direction": "bearish",
                    "strength": min(1.0, abs(sector["avg_change_24h_pct"]) / 10),
                    "description": f"{sector['sector']} sector down {sector['avg_change_24h_pct']:+.1f}% (24h). "
                                   f"Led by {sector['worst_performer']['symbol']}.",
                    "affected": [sector["worst_performer"]["symbol"]],
                })

        # Market-wide momentum
        mcap_change = overview.get("market_cap_change_24h_pct", 0)
        if abs(mcap_change) > 3:
            direction = "bullish" if mcap_change > 0 else "bearish"
            signals.append({
                "signal": "market_momentum",
                "direction": direction,
                "strength": min(1.0, abs(mcap_change) / 5),
                "description": f"Total crypto market cap changed {mcap_change:+.1f}% in 24h.",
                "affected": ["BTC-USD", "ETH-USD"],
            })

        # Individual coin signals (top movers)
        for coin in coins:
            change = coin.get("change_24h_pct", 0)
            if abs(change) > 15:
                direction = "bullish" if change > 0 else "bearish"
                signals.append({
                    "signal": f"large_move_{coin['symbol']}",
                    "direction": direction,
                    "strength": min(1.0, abs(change) / 25),
                    "description": f"{coin['symbol']} {change:+.1f}% in 24h. "
                                   f"Vol/MCap ratio: {coin.get('volume_to_mcap', 0):.2%}.",
                    "affected": [f"{coin['symbol']}-USD"],
                })

        return signals

    def full_scan(self) -> Dict[str, Any]:
        """Run complete crypto market scan."""
        _log("=== Starting full crypto scan ===")

        overview = self.fetch_market_overview()
        coins = self.fetch_top_coins()
        fear_greed = self.fetch_fear_greed()
        sectors = self.compute_sector_performance(coins)
        anomalies = self.detect_anomalies(coins)
        signals = self.generate_signals(coins, fear_greed, overview, sectors)

        result = {
            "overview": overview,
            "coins": coins,
            "fear_greed": fear_greed,
            "sectors": sectors,
            "anomalies": anomalies,
            "signals": signals,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "coin_count": len(coins),
            "signal_count": len(signals),
            "anomaly_count": len(anomalies),
        }

        # Save to disk
        os.makedirs(os.path.dirname(CRYPTO_DATA_FILE), exist_ok=True)
        with open(CRYPTO_DATA_FILE, "w") as f:
            json.dump(result, f, indent=2)

        _log(f"=== Crypto scan complete: {len(coins)} coins, "
             f"{len(signals)} signals, {len(anomalies)} anomalies ===")

        return result


if __name__ == "__main__":
    scanner = CryptoScanner()
    result = scanner.full_scan()
    print(json.dumps(result, indent=2)[:3000])
