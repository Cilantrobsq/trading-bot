"""
Unified prediction market scanner.

Combines Kalshi and Polymarket data, compares prices against our model,
detects cross-platform arbitrage, and generates trading signals.

Output feeds into the dashboard Prediction Markets tab.
"""

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.signals.kalshi_client import KalshiClient, KalshiEvent
from src.signals.polymarket_gamma import PolymarketGammaClient, PolymarketMarket


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] prediction_scanner: {msg}")


def _normal_cdf(x: float) -> float:
    """Standard normal CDF approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _lognormal_prob(current: float, target: float, days: int, vol: float, above: bool = True) -> float:
    """P(price > target) using log-normal model with zero drift."""
    if current <= 0 or target <= 0 or days <= 0 or vol <= 0:
        return 0.5
    t = days / 365.0
    sigma_sqrt_t = vol * math.sqrt(t)
    if sigma_sqrt_t == 0:
        return (1.0 if current >= target else 0.0) if above else (1.0 if current <= target else 0.0)
    d2 = (math.log(current / target) - 0.5 * vol**2 * t) / sigma_sqrt_t
    p = _normal_cdf(d2)
    return round(p if above else 1.0 - p, 4)


@dataclass
class PredictionSignal:
    """A signal derived from prediction market data."""
    platform: str
    question: str
    category: str
    yes_price: float
    no_price: float
    volume: float
    model_probability: Optional[float] = None
    edge_pct: Optional[float] = None
    direction: Optional[str] = None  # BUY_YES, BUY_NO, or None
    confidence: str = "low"
    end_date: str = ""
    underlying: Optional[str] = None
    current_price: Optional[float] = None
    target_price: Optional[float] = None
    cross_platform_spread: Optional[float] = None
    matching_platform: Optional[str] = None
    matching_price: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "platform": self.platform,
            "question": self.question,
            "category": self.category,
            "yes_price": self.yes_price,
            "no_price": self.no_price,
            "volume": self.volume,
            "end_date": self.end_date,
        }
        if self.model_probability is not None:
            d["model_probability"] = self.model_probability
        if self.edge_pct is not None:
            d["edge_pct"] = self.edge_pct
            d["direction"] = self.direction
            d["confidence"] = self.confidence
        if self.underlying:
            d["underlying"] = self.underlying
            d["current_price"] = self.current_price
            d["target_price"] = self.target_price
        if self.cross_platform_spread is not None:
            d["cross_platform_spread"] = self.cross_platform_spread
            d["matching_platform"] = self.matching_platform
            d["matching_price"] = self.matching_price
        return d


@dataclass
class KalshiDistribution:
    """Kalshi implied price distribution for dashboard rendering."""
    asset: str
    title: str
    expected_price: Optional[float]
    buckets: List[Dict[str, Any]]
    total_volume: int
    close_time: str
    prob_above_levels: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "title": self.title,
            "expected_price": self.expected_price,
            "buckets": self.buckets,
            "total_volume": self.total_volume,
            "close_time": self.close_time,
            "prob_above_levels": self.prob_above_levels,
        }


class PredictionMarketScanner:
    """
    Unified scanner combining Kalshi + Polymarket.

    Produces:
    1. Kalshi price distributions (BTC, ETH, S&P)
    2. Polymarket signals by category
    3. Model vs market comparisons
    4. Cross-platform arbitrage detection
    """

    def __init__(self):
        self.kalshi = KalshiClient()
        self.polymarket = PolymarketGammaClient()
        _log("initialized prediction market scanner")

    def _get_current_prices(self) -> Dict[str, float]:
        """Get current spot prices for model comparison. Uses yfinance if available."""
        prices = {}
        try:
            import yfinance as yf
            for ticker in ["BTC-USD", "ETH-USD", "^GSPC"]:
                hist = yf.Ticker(ticker).history(period="1d")
                if not hist.empty:
                    prices[ticker] = float(hist["Close"].iloc[-1])
        except Exception as e:
            _log(f"yfinance price fetch failed: {e}")
        return prices

    def _get_volatilities(self) -> Dict[str, float]:
        """Get 30-day annualized volatilities."""
        vols = {}
        try:
            import yfinance as yf
            for ticker in ["BTC-USD", "ETH-USD", "^GSPC"]:
                hist = yf.Ticker(ticker).history(period="35d")
                if not hist.empty and len(hist) >= 5:
                    closes = hist["Close"].values
                    log_rets = [math.log(closes[i]/closes[i-1]) for i in range(1, len(closes)) if closes[i] > 0 and closes[i-1] > 0]
                    if len(log_rets) >= 5:
                        mean_r = sum(log_rets) / len(log_rets)
                        var = sum((r - mean_r)**2 for r in log_rets) / (len(log_rets) - 1)
                        daily_vol = math.sqrt(var)
                        annual_vol = daily_vol * math.sqrt(365)
                        vols[ticker] = round(annual_vol, 4)
        except Exception as e:
            _log(f"volatility fetch failed: {e}")

        # Defaults
        vols.setdefault("BTC-USD", 0.65)
        vols.setdefault("ETH-USD", 0.75)
        vols.setdefault("^GSPC", 0.18)
        return vols

    def scan_kalshi(self) -> Dict[str, Any]:
        """Scan Kalshi markets and build distributions."""
        kalshi_data = self.kalshi.full_scan()

        distributions = []
        signals = []
        prices = self._get_current_prices()
        vols = self._get_volatilities()

        ticker_map = {"btc": "BTC-USD", "eth": "ETH-USD", "sp500": "^GSPC"}
        price_levels = {
            "btc": [60000, 70000, 80000, 90000, 100000],
            "eth": [2000, 2500, 3000, 3500, 4000],
            "sp500": [5000, 5200, 5400, 5600, 5800],
        }

        for asset, events_data in kalshi_data.get("markets", {}).items():
            yf_ticker = ticker_map.get(asset, "")
            current = prices.get(yf_ticker)
            vol = vols.get(yf_ticker, 0.5)

            for ev_data in events_data:
                buckets = ev_data.get("buckets", [])
                if not buckets:
                    continue

                # Build probability levels
                prob_levels = {}
                # Reconstruct event to use its methods
                from src.signals.kalshi_client import KalshiBucket, KalshiEvent
                kb_list = []
                for b in buckets:
                    kb_list.append(KalshiBucket(
                        ticker=b.get("ticker", ""),
                        label=b.get("label", ""),
                        low=b.get("low", 0),
                        high=b.get("high", 0),
                        yes_bid=b.get("yes_bid", 0),
                        yes_ask=b.get("yes_ask", 0),
                        last_price=b.get("last_price", 0),
                        volume=b.get("volume", 0),
                        midpoint=b.get("midpoint_prob", 0),
                    ))

                event = KalshiEvent(
                    title=ev_data.get("title", ""),
                    event_ticker=ev_data.get("event_ticker", ""),
                    series_ticker=ev_data.get("series_ticker", ""),
                    close_time=ev_data.get("close_time", ""),
                    buckets=kb_list,
                    total_volume=ev_data.get("total_volume", 0),
                )

                for level in price_levels.get(asset, []):
                    market_prob = event.prob_above(level)
                    prob_levels[f">${level:,.0f}"] = market_prob

                    # Compare with model if we have spot price
                    if current and vol:
                        model_prob = _lognormal_prob(current, level, 1, vol, above=True)
                        edge = (model_prob - market_prob) * 100
                        if abs(edge) > 5:
                            conf = "high" if abs(edge) > 15 else "medium" if abs(edge) > 8 else "low"
                            signals.append(PredictionSignal(
                                platform="kalshi",
                                question=f"P({asset.upper()} > ${level:,.0f}) today",
                                category="crypto" if asset in ("btc", "eth") else "markets",
                                yes_price=market_prob,
                                no_price=round(1 - market_prob, 4),
                                volume=event.total_volume,
                                model_probability=model_prob,
                                edge_pct=round(edge, 2),
                                direction="BUY_YES" if edge > 0 else "BUY_NO",
                                confidence=conf,
                                underlying=yf_ticker,
                                current_price=current,
                                target_price=float(level),
                            ))

                distributions.append(KalshiDistribution(
                    asset=asset,
                    title=ev_data.get("title", ""),
                    expected_price=ev_data.get("expected_price"),
                    buckets=buckets,
                    total_volume=ev_data.get("total_volume", 0),
                    close_time=ev_data.get("close_time", ""),
                    prob_above_levels=prob_levels,
                ).to_dict())

        return {
            "distributions": distributions,
            "signals": [s.to_dict() for s in signals],
            "raw": kalshi_data.get("summary", {}),
        }

    def scan_polymarket(self) -> Dict[str, Any]:
        """Scan Polymarket for finance-relevant markets."""
        poly_data = self.polymarket.full_scan()

        signals = []
        for cat, markets in poly_data.get("markets", {}).items():
            for m in markets[:15]:  # top 15 per category by volume
                yes_p = m.get("outcome_prices", [0])[0] if m.get("outcome_prices") else 0
                no_p = m.get("outcome_prices", [0, 0])[1] if len(m.get("outcome_prices", [])) > 1 else 1 - yes_p

                signals.append(PredictionSignal(
                    platform="polymarket",
                    question=m.get("question", ""),
                    category=cat,
                    yes_price=yes_p,
                    no_price=no_p,
                    volume=m.get("volume", 0),
                    end_date=m.get("end_date", ""),
                ).to_dict())

        return {
            "signals": signals,
            "categories": poly_data.get("categories", {}),
            "total_markets": poly_data.get("total_markets", 0),
            "finance_markets": poly_data.get("finance_markets", 0),
            "total_volume": poly_data.get("total_volume", 0),
        }

    def detect_cross_platform_arb(
        self,
        kalshi_signals: List[Dict],
        poly_signals: List[Dict],
        threshold_pct: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """
        Detect cross-platform arbitrage opportunities.

        Matches similar questions across platforms and flags
        price discrepancies above threshold.
        """
        import re

        def normalize(q: str) -> str:
            q = q.lower().strip()
            q = re.sub(r'[^\w\s]', '', q)
            q = re.sub(r'\s+', ' ', q)
            return q

        arb_opportunities = []

        # Look for BTC/crypto price predictions on both platforms
        kalshi_crypto = [s for s in kalshi_signals if s.get("category") == "crypto"]
        poly_crypto = [s for s in poly_signals if s.get("category") == "crypto"]

        # For each Kalshi signal with a model comparison, check if Polymarket
        # has a similar market with different pricing
        for ks in kalshi_crypto:
            if ks.get("edge_pct") is None:
                continue
            for ps in poly_crypto:
                # Check if they reference similar concepts
                kq = normalize(ks.get("question", ""))
                pq = normalize(ps.get("question", ""))

                # Simple similarity: both mention same crypto and price direction
                common_tokens = set(kq.split()) & set(pq.split())
                if len(common_tokens) < 2:
                    continue

                spread = abs(ks.get("yes_price", 0) - ps.get("yes_price", 0)) * 100
                if spread >= threshold_pct:
                    arb_opportunities.append({
                        "type": "cross_platform",
                        "kalshi_question": ks.get("question", ""),
                        "kalshi_price": ks.get("yes_price", 0),
                        "polymarket_question": ps.get("question", ""),
                        "polymarket_price": ps.get("yes_price", 0),
                        "spread_pct": round(spread, 2),
                        "kalshi_volume": ks.get("volume", 0),
                        "polymarket_volume": ps.get("volume", 0),
                    })

        arb_opportunities.sort(key=lambda x: x["spread_pct"], reverse=True)
        return arb_opportunities

    def full_scan(self) -> Dict[str, Any]:
        """
        Complete prediction market scan: Kalshi distributions,
        Polymarket signals, model comparisons, and arbitrage detection.
        """
        _log("=== Full Prediction Market Scan ===")

        # Scan both platforms
        kalshi_result = self.scan_kalshi()
        poly_result = self.scan_polymarket()

        # Cross-platform arbitrage
        arb = self.detect_cross_platform_arb(
            kalshi_result.get("signals", []),
            poly_result.get("signals", []),
        )

        # Build combined output
        all_signals = kalshi_result.get("signals", []) + poly_result.get("signals", [])

        # Separate model-edge signals (actionable) from informational
        edge_signals = [s for s in all_signals if s.get("edge_pct") is not None]
        info_signals = [s for s in all_signals if s.get("edge_pct") is None]

        # Sort edge signals by absolute edge
        edge_signals.sort(key=lambda s: abs(s.get("edge_pct", 0)), reverse=True)

        # Sort info signals by volume
        info_signals.sort(key=lambda s: s.get("volume", 0), reverse=True)

        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kalshi": {
                "distributions": kalshi_result.get("distributions", []),
                "summary": kalshi_result.get("raw", {}),
            },
            "polymarket": {
                "categories": poly_result.get("categories", {}),
                "total_markets": poly_result.get("total_markets", 0),
                "finance_markets": poly_result.get("finance_markets", 0),
                "total_volume": poly_result.get("total_volume", 0),
            },
            "edge_signals": edge_signals,
            "market_signals": info_signals[:50],  # top 50 by volume
            "arbitrage": arb,
            "summary": {
                "platforms": ["kalshi", "polymarket"],
                "total_signals": len(all_signals),
                "edge_signals": len(edge_signals),
                "arbitrage_opportunities": len(arb),
                "kalshi_distributions": len(kalshi_result.get("distributions", [])),
                "polymarket_finance_markets": poly_result.get("finance_markets", 0),
            },
        }

        _log(f"scan complete: {len(all_signals)} signals, "
             f"{len(edge_signals)} with model edge, "
             f"{len(arb)} arbitrage opportunities")

        return output

    def save(self, data: Dict[str, Any], path: str) -> None:
        """Save scan results to JSON."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        _log(f"saved to {path}")


if __name__ == "__main__":
    scanner = PredictionMarketScanner()
    result = scanner.full_scan()

    print(f"\n=== Prediction Market Summary ===")
    print(f"Total signals: {result['summary']['total_signals']}")
    print(f"Edge signals: {result['summary']['edge_signals']}")
    print(f"Arbitrage: {result['summary']['arbitrage_opportunities']}")

    if result["edge_signals"]:
        print(f"\nTop edge signals:")
        for s in result["edge_signals"][:5]:
            print(f"  [{s['platform']}] {s['question'][:50]}")
            print(f"    market={s['yes_price']:.2%} model={s.get('model_probability',0):.2%} edge={s['edge_pct']:+.1f}%")

    if result["kalshi"]["distributions"]:
        print(f"\nKalshi distributions:")
        for d in result["kalshi"]["distributions"]:
            print(f"  {d['asset']}: {d['title'][:50]}")
            print(f"    expected=${d.get('expected_price', 0):,.0f}, vol={d['total_volume']}")
            for level, prob in d.get("prob_above_levels", {}).items():
                print(f"    P({level}): {prob:.1%}")

    print(json.dumps(result["summary"], indent=2))
