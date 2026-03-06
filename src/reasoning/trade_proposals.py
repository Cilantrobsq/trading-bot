"""
Trade proposal generator for the trading bot.

Synthesizes signals, brain state, global markets, timezone arbitrage,
correlations, theses, and FRED data into specific, actionable trade
proposals with entry, target, stop-loss, risk/reward ratio, and expiry.

Each proposal has a validity window (countdown timer on dashboard).
Proposals expire when their analysis window closes or market conditions
change significantly.
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROPOSALS_FILE = os.path.join(BASE_DIR, "data", "proposals", "active.json")
ARCHIVE_FILE = os.path.join(BASE_DIR, "data", "proposals", "archive.json")


@dataclass
class TradeProposal:
    """A specific, actionable trade proposal with full risk parameters."""
    id: str
    ticker: str
    name: str
    direction: str          # "long" or "short"
    entry_price: float      # suggested entry price
    target_price: float     # take-profit price
    stop_price: float       # stop-loss price
    risk_reward: float      # reward / risk ratio
    position_size_pct: float  # % of portfolio to allocate
    position_size_usd: float  # dollar amount
    confidence: int         # 0-100
    max_loss_usd: float     # max dollar loss if stopped out
    max_gain_usd: float     # max dollar gain if target hit
    category: str           # "macro", "momentum", "mean_reversion", "timezone_arb", "correlation_arb", "thesis"
    reasoning: str          # human-readable explanation
    supporting_signals: List[str]  # list of signal names supporting this
    opposing_signals: List[str]    # list of signals against
    created_at: str = ""
    expires_at: str = ""    # ISO timestamp when proposal becomes stale
    status: str = "active"  # "active", "expired", "taken", "invalidated"
    urgency: str = "normal" # "high", "normal", "low"

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TradeProposal":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > datetime.fromisoformat(self.expires_at)

    def seconds_remaining(self) -> int:
        if not self.expires_at:
            return -1
        remaining = datetime.fromisoformat(self.expires_at) - datetime.now(timezone.utc)
        return max(0, int(remaining.total_seconds()))


class TradeProposalGenerator:
    """
    Generates trade proposals by synthesizing all available signals.

    Sources:
    - yfinance signals (price momentum, threshold breaches)
    - FRED macro data (rate changes, inflation, sentiment)
    - Global market sessions (timezone gaps, breadth divergence)
    - Cross-correlations (breakdown anomalies, unusual correlations)
    - Active theses (directional views with conviction)
    - Brain state (regime, sentiment, planned actions)
    """

    def __init__(self, portfolio_value: float = 10000.0):
        self.portfolio_value = portfolio_value
        self.proposals: List[TradeProposal] = []
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing active proposals."""
        if not os.path.isfile(PROPOSALS_FILE):
            return
        try:
            with open(PROPOSALS_FILE) as f:
                data = json.load(f)
            self.proposals = [TradeProposal.from_dict(p) for p in data]
        except (json.JSONDecodeError, KeyError):
            self.proposals = []

    def _save(self) -> None:
        """Persist proposals to disk."""
        os.makedirs(os.path.dirname(PROPOSALS_FILE), exist_ok=True)
        with open(PROPOSALS_FILE, "w") as f:
            json.dump([p.to_dict() for p in self.proposals], f, indent=2)

    def _archive_expired(self) -> int:
        """Move expired proposals to archive. Return count archived."""
        active = []
        expired = []
        for p in self.proposals:
            if p.is_expired() or p.status != "active":
                p.status = "expired" if p.status == "active" else p.status
                expired.append(p)
            else:
                active.append(p)
        self.proposals = active

        if expired:
            os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
            existing_archive = []
            if os.path.isfile(ARCHIVE_FILE):
                try:
                    with open(ARCHIVE_FILE) as f:
                        existing_archive = json.load(f)
                except (json.JSONDecodeError, FileNotFoundError):
                    pass
            existing_archive.extend([p.to_dict() for p in expired])
            # Keep last 200 archived proposals
            existing_archive = existing_archive[-200:]
            with open(ARCHIVE_FILE, "w") as f:
                json.dump(existing_archive, f, indent=2)

        return len(expired)

    def _make_proposal(
        self,
        ticker: str,
        name: str,
        direction: str,
        entry_price: float,
        target_price: float,
        stop_price: float,
        confidence: int,
        category: str,
        reasoning: str,
        supporting: List[str],
        opposing: List[str],
        validity_hours: float = 4.0,
        urgency: str = "normal",
    ) -> Optional[TradeProposal]:
        """Create a proposal if risk/reward meets minimum threshold."""
        if entry_price <= 0 or target_price <= 0 or stop_price <= 0:
            return None

        # Calculate risk/reward
        if direction == "long":
            reward = target_price - entry_price
            risk = entry_price - stop_price
        else:
            reward = entry_price - target_price
            risk = stop_price - entry_price

        if risk <= 0:
            return None
        rr = round(reward / risk, 2)

        # Minimum 1.5:1 R:R to propose
        if rr < 1.5:
            return None

        # Position sizing (Kelly-inspired, simplified)
        win_prob = confidence / 100.0
        if win_prob <= 0 or win_prob >= 1:
            return None
        kelly = max(0, (win_prob * rr - (1 - win_prob)) / rr)
        # Quarter Kelly for safety
        size_frac = min(kelly * 0.25, 0.10)  # max 10% of portfolio
        size_usd = round(self.portfolio_value * size_frac, 2)
        size_pct = round(size_frac * 100, 2)

        if size_usd < 10:  # minimum $10 position
            return None

        # Calculate max loss/gain
        if direction == "long":
            shares = size_usd / entry_price if entry_price > 0 else 0
            max_loss = round(shares * risk, 2)
            max_gain = round(shares * reward, 2)
        else:
            shares = size_usd / entry_price if entry_price > 0 else 0
            max_loss = round(shares * risk, 2)
            max_gain = round(shares * reward, 2)

        # Don't duplicate existing active proposals for same ticker+direction
        for existing in self.proposals:
            if (existing.ticker == ticker and
                existing.direction == direction and
                existing.status == "active"):
                return None

        expires = datetime.now(timezone.utc) + timedelta(hours=validity_hours)

        proposal = TradeProposal(
            id=str(uuid.uuid4())[:8],
            ticker=ticker,
            name=name,
            direction=direction,
            entry_price=round(entry_price, 4),
            target_price=round(target_price, 4),
            stop_price=round(stop_price, 4),
            risk_reward=rr,
            position_size_pct=size_pct,
            position_size_usd=size_usd,
            confidence=confidence,
            max_loss_usd=max_loss,
            max_gain_usd=max_gain,
            category=category,
            reasoning=reasoning,
            supporting_signals=supporting,
            opposing_signals=opposing,
            expires_at=expires.isoformat(),
            urgency=urgency,
        )
        return proposal

    # ------------------------------------------------------------------
    # Signal-based proposal generators
    # ------------------------------------------------------------------

    def _from_momentum_signals(self, signals_data: Dict) -> List[TradeProposal]:
        """Generate proposals from yfinance price momentum signals."""
        proposals = []
        signals = signals_data.get("signals", [])
        if not signals:
            return proposals

        for sig in signals:
            if sig.get("error"):
                continue
            price = sig.get("price")
            change_pct = sig.get("change_pct")
            ticker = sig.get("ticker", "")
            name = sig.get("name", ticker)
            signal_type = sig.get("signal", "neutral")

            if price is None or change_pct is None:
                continue

            # Strong momentum: >2% daily move with trend continuation potential
            if abs(change_pct) >= 2.0 and signal_type in ("bullish", "bearish"):
                direction = "long" if signal_type == "bullish" else "short"
                # Target: continue half the move, stop: reverse half the move
                move = abs(change_pct) / 100
                if direction == "long":
                    target = round(price * (1 + move * 0.5), 4)
                    stop = round(price * (1 - move * 0.3), 4)
                else:
                    target = round(price * (1 - move * 0.5), 4)
                    stop = round(price * (1 + move * 0.3), 4)

                confidence = min(75, 50 + int(abs(change_pct) * 5))
                supporting = [f"{name} {change_pct:+.1f}% today"]
                opposing = []

                # Threshold breach adds conviction
                if sig.get("threshold_breached"):
                    confidence = min(85, confidence + 10)
                    supporting.append(f"Threshold breached at {sig.get('threshold')}")

                p = self._make_proposal(
                    ticker=ticker, name=name, direction=direction,
                    entry_price=price, target_price=target, stop_price=stop,
                    confidence=confidence, category="momentum",
                    reasoning=f"Strong {direction} momentum: {name} moved {change_pct:+.1f}% today. "
                              f"Targeting continuation to {target:.2f} with stop at {stop:.2f}.",
                    supporting=supporting, opposing=opposing,
                    validity_hours=6.0,
                    urgency="high" if abs(change_pct) > 3 else "normal",
                )
                if p:
                    proposals.append(p)

        return proposals

    def _from_fred_signals(self, fred_data: Dict) -> List[TradeProposal]:
        """Generate proposals from FRED macro threshold breaches."""
        proposals = []
        signals = fred_data.get("signals", [])
        if not signals:
            return proposals

        # Map FRED signals to tradable instruments
        fred_trade_map = {
            "VIXCLS": {"ticker": "^VIX", "name": "VIX", "inverse": False},
            "DGS10": {"ticker": "^TNX", "name": "10Y Treasury", "inverse": False},
            "UMCSENT": {"ticker": "XLY", "name": "Consumer Discretionary (sentiment proxy)", "inverse": False},
            "UNRATE": {"ticker": "XLY", "name": "Consumer Discretionary (jobs proxy)", "inverse": True},
        }

        for sig in signals:
            series_id = sig.get("series_id", "")
            if series_id not in fred_trade_map:
                continue
            if not sig.get("breached"):
                continue

            mapping = fred_trade_map[series_id]
            value = sig.get("value")
            change_pct = sig.get("change_pct", 0)
            if value is None:
                continue

            direction_hint = sig.get("direction", "")
            if "up" in direction_hint.lower() or change_pct > 0:
                macro_direction = "rising"
            else:
                macro_direction = "falling"

            # VIX breach: trade the fear
            if series_id == "VIXCLS" and value > 25:
                # VIX elevated, expect mean reversion
                p = self._make_proposal(
                    ticker="^VIX", name="VIX Mean Reversion",
                    direction="short",
                    entry_price=value, target_price=value * 0.85, stop_price=value * 1.15,
                    confidence=60, category="mean_reversion",
                    reasoning=f"VIX at {value:.1f} (breached 25 threshold). "
                              f"Historically mean-reverts. Target 15% decline to {value*0.85:.1f}, "
                              f"stop at {value*1.15:.1f}.",
                    supporting=[f"VIX at {value:.1f}, above 25 threshold"],
                    opposing=["Elevated VIX can persist in crisis"],
                    validity_hours=24.0,
                )
                if p:
                    proposals.append(p)

            # Consumer sentiment breach: consumer discretionary play
            if series_id == "UMCSENT" and value < 60:
                p = self._make_proposal(
                    ticker="XLY", name="Consumer Weakness Play",
                    direction="short",
                    entry_price=180.0,  # approximate, updated by live price
                    target_price=170.0,
                    stop_price=186.0,
                    confidence=55, category="macro",
                    reasoning=f"Consumer Sentiment at {value:.1f} (below 60 threshold). "
                              f"Weak consumers = weak discretionary spending.",
                    supporting=[f"Consumer Sentiment {value:.1f}"],
                    opposing=["Markets may have already priced this in"],
                    validity_hours=48.0,
                )
                if p:
                    proposals.append(p)

        return proposals

    def _from_timezone_arb(self, tz_data: Dict) -> List[TradeProposal]:
        """Generate proposals from timezone/session divergences."""
        proposals = []
        rt_signals = tz_data.get("realtime_signals", [])
        if not rt_signals:
            return proposals

        for sig in rt_signals:
            sig_type = sig.get("signal_type", "")
            strength = sig.get("strength", 0)
            direction = sig.get("direction", "")
            target = sig.get("target_market", "")
            source = sig.get("source_market", "")
            desc = sig.get("description", "")

            if strength < 0.5:
                continue

            # Session handoff signals
            if "handoff" in sig_type.lower() or "follow" in sig_type.lower():
                if "bullish" in direction.lower():
                    trade_dir = "long"
                elif "bearish" in direction.lower():
                    trade_dir = "short"
                else:
                    continue

                # Use SPY as proxy for US session trades
                proxy_ticker = "SPY"
                proxy_name = "S&P 500 (session handoff)"
                proxy_price = 530.0  # approximate, gets updated

                if trade_dir == "long":
                    target_p = proxy_price * 1.005
                    stop_p = proxy_price * 0.997
                else:
                    target_p = proxy_price * 0.995
                    stop_p = proxy_price * 1.003

                confidence = min(70, 45 + int(strength * 30))
                p = self._make_proposal(
                    ticker=proxy_ticker, name=proxy_name,
                    direction=trade_dir,
                    entry_price=proxy_price, target_price=target_p, stop_price=stop_p,
                    confidence=confidence, category="timezone_arb",
                    reasoning=f"Timezone arbitrage: {desc}. {source} session "
                              f"{'strongly ' if strength > 0.7 else ''}signals {trade_dir} handoff to {target}.",
                    supporting=[f"{source} -> {target}: {direction}"],
                    opposing=["Session handoffs are probabilistic, not guaranteed"],
                    validity_hours=2.0,
                    urgency="high",
                )
                if p:
                    proposals.append(p)

            # Divergence signals
            if "divergence" in sig_type.lower():
                confidence = min(65, 40 + int(strength * 25))
                supporting_data = sig.get("supporting_data", {})
                p = self._make_proposal(
                    ticker="SPY", name="S&P 500 (session divergence)",
                    direction="long" if "bullish" in direction.lower() else "short",
                    entry_price=530.0, target_price=530.0 * 1.003, stop_price=530.0 * 0.998,
                    confidence=confidence, category="timezone_arb",
                    reasoning=f"Session divergence detected: {desc}",
                    supporting=[desc],
                    opposing=["Divergences can persist or close in either direction"],
                    validity_hours=3.0,
                )
                if p:
                    proposals.append(p)

        return proposals

    def _from_correlation_anomalies(self, corr_data: Dict) -> List[TradeProposal]:
        """Generate proposals from correlation breakdowns."""
        proposals = []
        anomalies = corr_data.get("anomalies", [])
        if not anomalies:
            return proposals

        for anomaly in anomalies:
            if not anomaly.get("is_breakdown"):
                continue

            ticker_a = anomaly.get("ticker_a", "")
            ticker_b = anomaly.get("ticker_b", "")
            name_a = anomaly.get("name_a", ticker_a)
            name_b = anomaly.get("name_b", ticker_b)
            corr_30d = anomaly.get("correlation_30d")
            corr_90d = anomaly.get("correlation_90d")
            desc = anomaly.get("description", "")

            if corr_30d is None or corr_90d is None:
                continue

            # Correlation breakdown: pair historically correlated, now diverging
            # Mean reversion trade: expect correlation to restore
            change = abs((corr_30d or 0) - (corr_90d or 0))
            if change < 0.3:
                continue

            p = self._make_proposal(
                ticker=f"{ticker_a}/{ticker_b}", name=f"Correlation Reversion: {name_a} vs {name_b}",
                direction="long",  # simplified; real implementation would be pair trade
                entry_price=100.0,  # notional
                target_price=103.0,
                stop_price=98.0,
                confidence=55, category="correlation_arb",
                reasoning=f"Correlation breakdown: {name_a} and {name_b} historically correlated "
                          f"({corr_90d:.2f} over 90d) but diverged to {corr_30d:.2f} over 30d. "
                          f"Mean reversion expected.",
                supporting=[desc],
                opposing=["Regime change may justify new correlation structure"],
                validity_hours=24.0,
            )
            if p:
                proposals.append(p)

        return proposals

    def _from_global_sessions(self, global_data: Dict) -> List[TradeProposal]:
        """Generate proposals from global session breadth/divergence."""
        proposals = []
        sessions = global_data.get("sessions", {})
        gaps = global_data.get("gaps", [])
        breadth = global_data.get("global_breadth", 50)

        # Extreme breadth: >80% bullish or <20% = strong signal
        if breadth > 80:
            p = self._make_proposal(
                ticker="SPY", name="S&P 500 (extreme bullish breadth)",
                direction="long",
                entry_price=530.0, target_price=535.0, stop_price=527.0,
                confidence=70, category="macro",
                reasoning=f"Global breadth at {breadth}% (>80% of markets positive). "
                          f"Strong global risk-on environment.",
                supporting=[f"Global breadth {breadth}%"],
                opposing=["Extreme breadth can precede reversals"],
                validity_hours=8.0,
            )
            if p:
                proposals.append(p)
        elif breadth < 20:
            p = self._make_proposal(
                ticker="SPY", name="S&P 500 (extreme bearish breadth)",
                direction="short",
                entry_price=530.0, target_price=525.0, stop_price=533.0,
                confidence=65, category="macro",
                reasoning=f"Global breadth at {breadth}% (<20% of markets positive). "
                          f"Broad-based selling across all sessions.",
                supporting=[f"Global breadth {breadth}%"],
                opposing=["Extreme selling can trigger snapback rallies"],
                validity_hours=8.0,
            )
            if p:
                proposals.append(p)

        # Session gap signals
        for gap in gaps:
            if gap.get("divergent") and abs(gap.get("gap_magnitude", 0)) > 1.0:
                desc = gap.get("description", "")
                p = self._make_proposal(
                    ticker="SPY", name=f"Session Gap: {gap.get('from_session','')} -> {gap.get('to_session','')}",
                    direction="long" if gap.get("to_avg_change", 0) > 0 else "short",
                    entry_price=530.0,
                    target_price=530.0 * (1 + 0.003 if gap.get("to_avg_change", 0) > 0 else 530.0 * 0.997),
                    stop_price=530.0 * (0.998 if gap.get("to_avg_change", 0) > 0 else 530.0 * 1.002),
                    confidence=55, category="timezone_arb",
                    reasoning=f"Session gap signal: {desc}",
                    supporting=[desc],
                    opposing=["Gaps can fill in either direction"],
                    validity_hours=4.0,
                )
                if p:
                    proposals.append(p)

        return proposals

    def _from_theses(self, theses: List[Dict], signals_data: Dict) -> List[TradeProposal]:
        """Generate proposals from active theses that align with current signals."""
        proposals = []
        if not theses:
            return proposals

        # Build a price lookup from current signals
        prices = {}
        for sig in signals_data.get("signals", []):
            if sig.get("price") is not None:
                prices[sig.get("ticker", "")] = sig["price"]

        for thesis in theses:
            if thesis.get("status") != "active":
                continue
            direction_str = thesis.get("direction", "neutral")
            if direction_str == "neutral":
                continue

            confidence = thesis.get("confidence", 50)
            if confidence < 40:
                continue

            tickers = thesis.get("affected_tickers", [])
            for ticker in tickers:
                price = prices.get(ticker)
                if price is None or price <= 0:
                    continue

                direction = "long" if direction_str == "bullish" else "short"
                # Set targets based on time horizon
                horizon = thesis.get("time_horizon", 30)
                if horizon <= 7:
                    move_target = 0.02  # 2% for short-term
                elif horizon <= 30:
                    move_target = 0.05  # 5% for medium-term
                else:
                    move_target = 0.10  # 10% for long-term

                if direction == "long":
                    target = round(price * (1 + move_target), 4)
                    stop = round(price * (1 - move_target * 0.4), 4)
                else:
                    target = round(price * (1 - move_target), 4)
                    stop = round(price * (1 + move_target * 0.4), 4)

                p = self._make_proposal(
                    ticker=ticker, name=f"{ticker} ({thesis.get('title', 'thesis')})",
                    direction=direction,
                    entry_price=price, target_price=target, stop_price=stop,
                    confidence=confidence, category="thesis",
                    reasoning=f"Thesis-driven: {thesis.get('title', '')}. "
                              f"{thesis.get('reasoning', '')[:200]}",
                    supporting=[f"Thesis confidence {confidence}%"] + thesis.get("catalysts", [])[:3],
                    opposing=thesis.get("invalidation_conditions", [])[:3],
                    validity_hours=min(horizon * 24, 168),  # max 1 week
                )
                if p:
                    proposals.append(p)

        return proposals

    def _from_brain_planned_actions(self, brain_data: Dict, signals_data: Dict) -> List[TradeProposal]:
        """Convert brain's planned actions into detailed proposals."""
        proposals = []
        actions = brain_data.get("planned_actions", [])
        if not actions:
            return proposals

        prices = {}
        for sig in signals_data.get("signals", []):
            if sig.get("price") is not None:
                prices[sig.get("ticker", "")] = sig["price"]

        for action in actions:
            if action.get("blocked_by"):
                continue

            market = action.get("market", "")
            direction = action.get("direction", "")
            if direction == "close":
                continue

            price = prices.get(market, 0)
            if price <= 0:
                continue

            trade_dir = "long" if direction == "long" else "short"
            size_pct = action.get("size_pct", 5)
            reasoning = action.get("reasoning", "")

            if trade_dir == "long":
                target = round(price * 1.03, 4)
                stop = round(price * 0.985, 4)
            else:
                target = round(price * 0.97, 4)
                stop = round(price * 1.015, 4)

            p = self._make_proposal(
                ticker=market, name=f"{market} (brain action)",
                direction=trade_dir,
                entry_price=price, target_price=target, stop_price=stop,
                confidence=60, category="macro",
                reasoning=f"Brain planned action: {reasoning}",
                supporting=[reasoning],
                opposing=[],
                validity_hours=4.0,
            )
            if p:
                proposals.append(p)

        return proposals

    # ------------------------------------------------------------------
    # Crypto proposals
    # ------------------------------------------------------------------

    def _from_crypto_signals(self, crypto_data: Dict) -> List[TradeProposal]:
        """Generate proposals from crypto market signals."""
        proposals = []
        coins = crypto_data.get("coins", [])
        fear_greed = crypto_data.get("fear_greed", {})
        anomalies = crypto_data.get("anomalies", [])
        crypto_signals = crypto_data.get("signals", [])

        if not coins:
            return proposals

        prices = {c["symbol"]: c["price"] for c in coins if c.get("price")}

        # Fear & Greed extreme
        fg_value = fear_greed.get("value")
        if fg_value is not None and fg_value <= 20:
            btc_price = prices.get("BTC", 0)
            if btc_price > 0:
                p = self._make_proposal(
                    ticker="BTC-USD", name="Bitcoin (Extreme Fear Buy)",
                    direction="long",
                    entry_price=btc_price, target_price=btc_price * 1.10,
                    stop_price=btc_price * 0.92,
                    confidence=70, category="crypto",
                    reasoning=f"Crypto Fear & Greed at {fg_value} (Extreme Fear). "
                              f"Historically strong buying signal.",
                    supporting=[f"Fear & Greed: {fg_value}"],
                    opposing=["Fear can persist in prolonged bear markets"],
                    validity_hours=48.0,
                )
                if p:
                    proposals.append(p)
        elif fg_value is not None and fg_value >= 80:
            btc_price = prices.get("BTC", 0)
            if btc_price > 0:
                p = self._make_proposal(
                    ticker="BTC-USD", name="Bitcoin (Extreme Greed Caution)",
                    direction="short",
                    entry_price=btc_price, target_price=btc_price * 0.90,
                    stop_price=btc_price * 1.05,
                    confidence=60, category="crypto",
                    reasoning=f"Crypto Fear & Greed at {fg_value} (Extreme Greed). Distribution risk.",
                    supporting=[f"Fear & Greed: {fg_value}"],
                    opposing=["Greed can sustain in parabolic moves"],
                    validity_hours=48.0,
                )
                if p:
                    proposals.append(p)

        # Large crypto movers
        for anomaly in anomalies:
            if anomaly.get("type") in ("large_move_24h", "flash_move_1h"):
                symbol = anomaly.get("symbol", "")
                change = anomaly.get("value", 0)
                price = prices.get(symbol, 0)
                if price <= 0 or abs(change) < 15:
                    continue
                direction = "short" if change > 0 else "long"
                if direction == "short":
                    target = price * 0.90
                    stop = price * 1.05
                else:
                    target = price * 1.10
                    stop = price * 0.95
                p = self._make_proposal(
                    ticker=f"{symbol}-USD", name=f"{symbol} Mean Reversion",
                    direction=direction,
                    entry_price=price, target_price=target, stop_price=stop,
                    confidence=55, category="crypto",
                    reasoning=f"{symbol} moved {change:+.1f}%. Mean reversion expected.",
                    supporting=[anomaly.get("description", "")],
                    opposing=["Momentum can persist in crypto"],
                    validity_hours=12.0,
                )
                if p:
                    proposals.append(p)

        # Sector rotation
        for sig in crypto_signals:
            if "sector_hot" in sig.get("signal", ""):
                affected = sig.get("affected", [])
                if affected:
                    symbol = affected[0]
                    price = prices.get(symbol, 0)
                    if price > 0:
                        p = self._make_proposal(
                            ticker=f"{symbol}-USD", name=f"{symbol} Sector Momentum",
                            direction="long",
                            entry_price=price, target_price=price * 1.08,
                            stop_price=price * 0.95,
                            confidence=60, category="crypto",
                            reasoning=sig.get("description", "Sector momentum"),
                            supporting=[sig.get("description", "")],
                            opposing=["Sector rotations can reverse quickly"],
                            validity_hours=24.0,
                        )
                        if p:
                            proposals.append(p)

        return proposals

    # ------------------------------------------------------------------
    # Influencer proposals
    # ------------------------------------------------------------------

    def _from_influencer_signals(self, influencer_data: Dict) -> List[TradeProposal]:
        """Generate proposals from influencer sentiment signals."""
        proposals = []
        signals = influencer_data.get("signals", [])
        if not signals:
            return proposals

        for sig in signals:
            if sig.get("strength", 0) < 0.5:
                continue
            direction = sig.get("direction", "neutral")
            if direction == "neutral":
                continue

            topics = sig.get("topics", [])
            description = sig.get("description", "")
            ticker, name, price_approx = None, None, None

            if "Bitcoin" in topics or "Crypto" in topics:
                ticker, name, price_approx = "BTC-USD", "Bitcoin (Influencer Signal)", 85000
            elif "AI" in topics or "Semiconductors" in topics:
                ticker, name, price_approx = "NVDA", "NVIDIA (AI Influencer Signal)", 900
            elif "Interest Rates" in topics or "Treasuries" in topics:
                ticker, name, price_approx = "TLT", "Treasury Bonds (Rate Signal)", 90
            elif "Gold" in topics:
                ticker, name, price_approx = "GLD", "Gold (Safe Haven Signal)", 280
            elif "Equities" in topics:
                ticker, name, price_approx = "SPY", "S&P 500 (Market Signal)", 560

            if ticker and price_approx:
                trade_dir = "long" if direction == "bullish" else "short"
                if trade_dir == "long":
                    target = price_approx * 1.03
                    stop = price_approx * 0.985
                else:
                    target = price_approx * 0.97
                    stop = price_approx * 1.015

                confidence = min(65, 45 + int(sig.get("strength", 0) * 25))
                p = self._make_proposal(
                    ticker=ticker, name=name,
                    direction=trade_dir,
                    entry_price=price_approx, target_price=target, stop_price=stop,
                    confidence=confidence, category="influencer",
                    reasoning=f"Key figure signal: {description[:200]}",
                    supporting=[description[:100]],
                    opposing=["Influencer sentiment can be contrarian indicator"],
                    validity_hours=12.0,
                )
                if p:
                    proposals.append(p)

        return proposals

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def generate_all(
        self,
        signals_data: Optional[Dict] = None,
        fred_data: Optional[Dict] = None,
        global_data: Optional[Dict] = None,
        tz_arb_data: Optional[Dict] = None,
        corr_data: Optional[Dict] = None,
        brain_data: Optional[Dict] = None,
        theses: Optional[List[Dict]] = None,
        crypto_data: Optional[Dict] = None,
        influencer_data: Optional[Dict] = None,
    ) -> List[TradeProposal]:
        """
        Run all proposal generators and return combined list.

        Call this from run_bot.py after all signals are collected.
        """
        # First, expire old proposals
        archived = self._archive_expired()
        if archived:
            logger.info("Archived %d expired proposals", archived)

        new_proposals = []

        if signals_data:
            new_proposals.extend(self._from_momentum_signals(signals_data))

        if fred_data:
            new_proposals.extend(self._from_fred_signals(fred_data))

        if tz_arb_data:
            new_proposals.extend(self._from_timezone_arb(tz_arb_data))

        if corr_data:
            new_proposals.extend(self._from_correlation_anomalies(corr_data))

        if global_data:
            new_proposals.extend(self._from_global_sessions(global_data))

        if theses and signals_data:
            new_proposals.extend(self._from_theses(theses, signals_data))

        if brain_data and signals_data:
            new_proposals.extend(self._from_brain_planned_actions(brain_data, signals_data))

        if crypto_data:
            new_proposals.extend(self._from_crypto_signals(crypto_data))

        if influencer_data:
            new_proposals.extend(self._from_influencer_signals(influencer_data))

        # Add new proposals to active list
        self.proposals.extend(new_proposals)

        # Sort by confidence (highest first), then by R:R
        self.proposals.sort(key=lambda p: (p.confidence, p.risk_reward), reverse=True)

        self._save()
        logger.info(
            "Generated %d new proposals (%d total active)",
            len(new_proposals), len(self.proposals),
        )
        return self.proposals

    def get_active(self) -> List[TradeProposal]:
        """Return only active, non-expired proposals."""
        return [p for p in self.proposals if p.status == "active" and not p.is_expired()]

    def get_for_export(self) -> List[Dict]:
        """Return proposals formatted for dashboard export."""
        result = []
        for p in self.get_active():
            d = p.to_dict()
            d["seconds_remaining"] = p.seconds_remaining()
            result.append(d)
        return result
