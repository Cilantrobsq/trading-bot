"""
Cross-platform spread scanner.

Compares Polymarket prediction market prices with external price
references (yfinance for underlying assets) to detect when prediction
market prices diverge from model probability. Starts with crypto
price markets (BTC/ETH).

Example: If Polymarket has "BTC > $100K by June 30" priced at $0.45
(45% probability), but BTC is currently at $98K with 45 days left
and historical 30-day volatility suggests a 62% chance, that is a
+17% edge worth investigating.
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore

from src.core.config import Config
from src.execution.polymarket_client import PolymarketClient, Market


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] spread_scanner: {msg}")


@dataclass
class SpreadOpportunity:
    """A detected pricing divergence between Polymarket and model estimate."""
    market_question: str
    market_id: str
    token_id: str
    outcome: str                    # "YES" or "NO"
    polymarket_price: float         # current market probability (0-1)
    model_probability: float        # our estimated probability (0-1)
    edge_pct: float                 # model_prob - market_price (as percentage)
    direction: str                  # "BUY_YES" or "BUY_NO"
    underlying_ticker: str          # e.g., "BTC-USD"
    underlying_price: float         # current price of the underlying
    target_price: float             # strike price from market question
    days_to_expiry: int
    volatility_30d: Optional[float] # annualized 30-day vol
    confidence: str                 # "high", "medium", "low"
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_question": self.market_question,
            "market_id": self.market_id,
            "token_id": self.token_id,
            "outcome": self.outcome,
            "polymarket_price": self.polymarket_price,
            "model_probability": self.model_probability,
            "edge_pct": self.edge_pct,
            "direction": self.direction,
            "underlying_ticker": self.underlying_ticker,
            "underlying_price": self.underlying_price,
            "target_price": self.target_price,
            "days_to_expiry": self.days_to_expiry,
            "volatility_30d": self.volatility_30d,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


# Mapping from common crypto symbols to yfinance tickers
CRYPTO_YFINANCE_MAP = {
    "btc": "BTC-USD",
    "bitcoin": "BTC-USD",
    "eth": "ETH-USD",
    "ethereum": "ETH-USD",
    "sol": "SOL-USD",
    "solana": "SOL-USD",
}

# Common price thresholds to look for in market questions
PRICE_PATTERNS = [
    # "$100K", "$100,000", "$100000"
    (r'\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', 1.0),
    (r'\$(\d+(?:\.\d+)?)k', 1000.0),
    (r'\$(\d+(?:\.\d+)?)K', 1000.0),
    (r'\$(\d+(?:\.\d+)?)M', 1_000_000.0),
]


def _extract_target_price(question: str) -> Optional[float]:
    """
    Try to extract a target price from a market question string.

    Handles formats like:
    - "BTC > $100K"
    - "Bitcoin above $100,000"
    - "ETH > $5,000"
    """
    import re

    for pattern, multiplier in PRICE_PATTERNS:
        matches = re.findall(pattern, question)
        for match_str in matches:
            try:
                # Remove commas
                clean = match_str.replace(",", "")
                value = float(clean) * multiplier
                # Sanity check: should be a reasonable price
                if value > 0:
                    return value
            except ValueError:
                continue
    return None


def _extract_crypto_symbol(question: str) -> Optional[str]:
    """
    Identify which crypto the market question is about.
    Returns the yfinance ticker if found.
    """
    q_lower = question.lower()
    for keyword, ticker in CRYPTO_YFINANCE_MAP.items():
        if keyword in q_lower:
            return ticker
    return None


def _parse_end_date(end_date_str: str) -> Optional[datetime]:
    """Parse various date formats from the API into a datetime."""
    if not end_date_str:
        return None

    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(end_date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _normal_cdf(x: float) -> float:
    """
    Approximate the standard normal CDF using the error function.
    Avoids needing scipy.
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def estimate_probability_lognormal(
    current_price: float,
    target_price: float,
    days_to_expiry: int,
    annual_volatility: float,
    is_above: bool = True,
) -> float:
    """
    Estimate the probability that an asset price will be above (or below)
    a target price at expiry, using a log-normal model.

    This is essentially a simplified Black-Scholes framework assuming
    risk-neutral drift of 0 (conservative assumption for crypto).

    Args:
        current_price: Current asset price.
        target_price: Strike/target price.
        days_to_expiry: Trading days until expiry.
        annual_volatility: Annualized volatility (e.g., 0.65 for 65%).
        is_above: If True, probability of price > target; if False, price < target.

    Returns:
        Estimated probability between 0 and 1.
    """
    if current_price <= 0 or target_price <= 0 or days_to_expiry <= 0:
        return 0.5  # degenerate case

    t = days_to_expiry / 365.0
    sigma_sqrt_t = annual_volatility * math.sqrt(t)

    if sigma_sqrt_t == 0:
        # Zero vol: deterministic
        if is_above:
            return 1.0 if current_price >= target_price else 0.0
        else:
            return 1.0 if current_price <= target_price else 0.0

    # d2 in Black-Scholes (with drift = 0 for conservative estimate)
    d2 = (math.log(current_price / target_price) - 0.5 * annual_volatility ** 2 * t) / sigma_sqrt_t

    prob_above = _normal_cdf(d2)

    if is_above:
        return round(prob_above, 4)
    else:
        return round(1.0 - prob_above, 4)


def fetch_volatility(ticker: str, period_days: int = 30) -> Optional[float]:
    """
    Fetch annualized historical volatility for a yfinance ticker.

    Uses daily log returns over the specified period.
    Returns annualized volatility (e.g., 0.65 for 65%).
    """
    if yf is None:
        return None

    try:
        data = yf.Ticker(ticker)
        hist = data.history(period=f"{period_days + 5}d")
        if hist.empty or len(hist) < 5:
            return None

        # Daily log returns
        closes = hist["Close"].values
        log_returns = []
        for i in range(1, len(closes)):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns.append(math.log(closes[i] / closes[i - 1]))

        if len(log_returns) < 5:
            return None

        # Standard deviation of daily returns
        mean_ret = sum(log_returns) / len(log_returns)
        variance = sum((r - mean_ret) ** 2 for r in log_returns) / (len(log_returns) - 1)
        daily_vol = math.sqrt(variance)

        # Annualize (365 for crypto which trades every day)
        annual_vol = daily_vol * math.sqrt(365)
        return round(annual_vol, 4)

    except Exception as e:
        _log(f"volatility fetch error for {ticker}: {e}")
        return None


def fetch_current_price(ticker: str) -> Optional[float]:
    """Fetch the current price for a yfinance ticker."""
    if yf is None:
        return None
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None
    except Exception as e:
        _log(f"price fetch error for {ticker}: {e}")
        return None


class SpreadScanner:
    """
    Scans Polymarket crypto price markets and compares them to
    model-estimated probabilities based on current prices and
    historical volatility.

    Usage:
        cfg = Config()
        scanner = SpreadScanner(cfg)
        opportunities = scanner.scan()
        scanner.print_opportunities(opportunities)
    """

    def __init__(self, config: Config, polymarket_client: Optional[PolymarketClient] = None):
        self.config = config
        self.client = polymarket_client or PolymarketClient(config)
        self.min_edge_pct = config.risk.min_spread_after_fees_pct
        _log(f"initialized (min_edge={self.min_edge_pct}%)")

    def scan(self) -> List[SpreadOpportunity]:
        """
        Run a full scan: find crypto markets on Polymarket, compare
        with model estimates, return opportunities above threshold.
        """
        _log("starting spread scan...")

        # Step 1: Find crypto markets
        crypto_markets = self.client.find_crypto_markets()
        _log(f"found {len(crypto_markets)} crypto-related markets")

        if not crypto_markets:
            _log("no crypto markets found, exiting scan")
            return []

        # Step 2: For each market, try to extract the underlying and target
        opportunities: List[SpreadOpportunity] = []

        for market in crypto_markets:
            opps = self._analyze_market(market)
            opportunities.extend(opps)

        # Sort by edge size (largest first)
        opportunities.sort(key=lambda o: abs(o.edge_pct), reverse=True)

        _log(f"scan complete: {len(opportunities)} opportunities found")
        return opportunities

    def scan_manual(
        self,
        markets: List[Dict[str, Any]],
    ) -> List[SpreadOpportunity]:
        """
        Scan a manually specified list of markets.

        Each dict should have:
        - question: str
        - condition_id: str
        - token_id: str (YES token)
        - underlying_ticker: str (yfinance ticker)
        - target_price: float
        - end_date: str (ISO date)
        - is_above: bool (default True)
        """
        opportunities = []
        for spec in markets:
            opp = self._analyze_manual_market(spec)
            if opp:
                opportunities.append(opp)
        opportunities.sort(key=lambda o: abs(o.edge_pct), reverse=True)
        return opportunities

    def _analyze_market(self, market: Market) -> List[SpreadOpportunity]:
        """Analyze a single Polymarket market for spread opportunities."""
        results = []

        # Extract crypto symbol
        yf_ticker = _extract_crypto_symbol(market.question)
        if not yf_ticker:
            return results

        # Extract target price
        target_price = _extract_target_price(market.question)
        if not target_price:
            _log(f"  could not extract target price from: {market.question[:60]}")
            return results

        # Determine direction (above/below)
        q_lower = market.question.lower()
        is_above = True
        if "below" in q_lower or "under" in q_lower or "<" in q_lower:
            is_above = False

        # Calculate days to expiry
        end_dt = _parse_end_date(market.end_date)
        now = datetime.now(timezone.utc)
        if end_dt and end_dt > now:
            days_to_expiry = (end_dt - now).days
        else:
            days_to_expiry = 30  # default if no end date

        # Fetch underlying price and volatility
        underlying_price = fetch_current_price(yf_ticker)
        if underlying_price is None:
            _log(f"  could not fetch price for {yf_ticker}")
            return results

        volatility = fetch_volatility(yf_ticker)
        if volatility is None:
            # Use a reasonable default for crypto
            volatility = 0.65
            _log(f"  using default volatility {volatility} for {yf_ticker}")

        # Estimate model probability
        model_prob = estimate_probability_lognormal(
            underlying_price, target_price, days_to_expiry, volatility, is_above
        )

        # Get Polymarket price
        for token in market.tokens:
            token_id = token.get("token_id", "")
            outcome = token.get("outcome", "")
            if not token_id:
                continue

            book = self.client.get_order_book(token_id)
            if not book or book.midpoint is None:
                continue

            market_price = book.midpoint

            # Calculate edge
            if outcome == "Yes":
                edge = (model_prob - market_price) * 100
                direction = "BUY_YES" if edge > 0 else "SELL_YES"
            else:
                # NO token: complementary
                no_model_prob = 1.0 - model_prob
                edge = (no_model_prob - market_price) * 100
                direction = "BUY_NO" if edge > 0 else "SELL_NO"

            # Only report if edge exceeds minimum threshold
            if abs(edge) < self.min_edge_pct:
                continue

            # Confidence assessment
            if abs(edge) > 15:
                confidence = "high"
            elif abs(edge) > 8:
                confidence = "medium"
            else:
                confidence = "low"

            opp = SpreadOpportunity(
                market_question=market.question,
                market_id=market.condition_id,
                token_id=token_id,
                outcome=outcome,
                polymarket_price=round(market_price, 4),
                model_probability=model_prob,
                edge_pct=round(edge, 2),
                direction=direction,
                underlying_ticker=yf_ticker,
                underlying_price=round(underlying_price, 2),
                target_price=target_price,
                days_to_expiry=days_to_expiry,
                volatility_30d=volatility,
                confidence=confidence,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            results.append(opp)

            _log(
                f"  {market.question[:50]}... "
                f"market={market_price:.2f} model={model_prob:.2f} "
                f"edge={edge:+.1f}% -> {direction} ({confidence})"
            )

        return results

    def _analyze_manual_market(self, spec: Dict[str, Any]) -> Optional[SpreadOpportunity]:
        """Analyze a manually specified market."""
        yf_ticker = spec["underlying_ticker"]
        target_price = spec["target_price"]
        is_above = spec.get("is_above", True)

        # Days to expiry
        end_dt = _parse_end_date(spec.get("end_date", ""))
        now = datetime.now(timezone.utc)
        days_to_expiry = (end_dt - now).days if end_dt and end_dt > now else 30

        # Fetch data
        underlying_price = fetch_current_price(yf_ticker)
        if underlying_price is None:
            return None

        volatility = fetch_volatility(yf_ticker)
        if volatility is None:
            volatility = 0.65

        model_prob = estimate_probability_lognormal(
            underlying_price, target_price, days_to_expiry, volatility, is_above
        )

        # Get Polymarket price
        token_id = spec["token_id"]
        book = self.client.get_order_book(token_id)
        if not book or book.midpoint is None:
            return None

        market_price = book.midpoint
        edge = (model_prob - market_price) * 100
        direction = "BUY_YES" if edge > 0 else "SELL_YES"

        if abs(edge) > 15:
            confidence = "high"
        elif abs(edge) > 8:
            confidence = "medium"
        else:
            confidence = "low"

        return SpreadOpportunity(
            market_question=spec.get("question", ""),
            market_id=spec.get("condition_id", ""),
            token_id=token_id,
            outcome="Yes",
            polymarket_price=round(market_price, 4),
            model_probability=model_prob,
            edge_pct=round(edge, 2),
            direction=direction,
            underlying_ticker=yf_ticker,
            underlying_price=round(underlying_price, 2),
            target_price=target_price,
            days_to_expiry=days_to_expiry,
            volatility_30d=volatility,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def print_opportunities(self, opportunities: List[SpreadOpportunity]) -> None:
        """Print a formatted table of spread opportunities."""
        if not opportunities:
            print("\n--- Spread Scanner: No opportunities found ---")
            return

        print(f"\n--- Spread Scanner: {len(opportunities)} Opportunities ---")
        print(f"  {'Market':<45} {'Mkt':>5} {'Model':>5} {'Edge':>6} {'Dir':>10} {'Conf':>6}")
        print(f"  {'-'*45} {'-'*5} {'-'*5} {'-'*6} {'-'*10} {'-'*6}")

        for opp in opportunities:
            q = opp.market_question[:45]
            print(
                f"  {q:<45} "
                f"{opp.polymarket_price:>5.2f} "
                f"{opp.model_probability:>5.2f} "
                f"{opp.edge_pct:>+5.1f}% "
                f"{opp.direction:>10} "
                f"{opp.confidence:>6}"
            )
            print(
                f"    {opp.underlying_ticker}: ${opp.underlying_price:,.0f} -> "
                f"${opp.target_price:,.0f}, "
                f"{opp.days_to_expiry}d, "
                f"vol={opp.volatility_30d:.0%}" if opp.volatility_30d else ""
            )
        print("---")

    def opportunities_to_json(self, opportunities: List[SpreadOpportunity]) -> str:
        """Serialize opportunities to JSON."""
        return json.dumps(
            [o.to_dict() for o in opportunities],
            indent=2,
        )


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)

    print("Spread Scanner - standalone test\n")

    # Test the probability model directly
    print("Model test: BTC at $97,000, target $100,000, 30 days, 65% vol")
    prob = estimate_probability_lognormal(97000, 100000, 30, 0.65, is_above=True)
    print(f"  P(BTC > $100K) = {prob:.2%}\n")

    print("Model test: ETH at $3,800, target $5,000, 60 days, 75% vol")
    prob = estimate_probability_lognormal(3800, 5000, 60, 0.75, is_above=True)
    print(f"  P(ETH > $5K) = {prob:.2%}\n")

    if yf is not None:
        print("Live BTC volatility:")
        vol = fetch_volatility("BTC-USD")
        price = fetch_current_price("BTC-USD")
        if vol and price:
            print(f"  Price: ${price:,.2f}, 30d annualized vol: {vol:.2%}")

    if cfg.polymarket.enabled:
        scanner = SpreadScanner(cfg)
        opportunities = scanner.scan()
        scanner.print_opportunities(opportunities)
    else:
        print("Polymarket disabled in config, skipping live scan.")
