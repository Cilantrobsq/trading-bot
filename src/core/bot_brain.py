"""
Bot brain: the central thinking engine for the trading bot.

Combines signals, theses, overrides, and risk state into a unified
market assessment. Determines market regime, plans trades, and
enforces circuit breakers. Exposes full state for dashboard display.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRAIN_STATE_FILE = os.path.join(BASE_DIR, "data", "brain-state.json")
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "data", "snapshots")
CONFIG_DIR = os.path.join(BASE_DIR, "config")

VALID_REGIMES = ("risk_on", "risk_off", "neutral", "volatile", "unknown")


@dataclass
class ThemeAssessment:
    """Assessment of a single trading theme."""
    theme_id: str
    theme_name: str
    conviction: float  # -1.0 (strong bearish) to 1.0 (strong bullish)
    signals_supporting: List[str] = field(default_factory=list)
    signals_against: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlannedAction:
    """A trade action the bot is considering or planning."""
    action_type: str  # "buy", "sell", "close", "adjust_stop", "hedge"
    market: str
    direction: str  # "long", "short", "close"
    size_pct: float  # percentage of portfolio
    reasoning: str
    priority: int  # 1 (highest) to 5 (lowest)
    blocked_by: Optional[str] = None  # reason if blocked (e.g. "kill_switch", "risk_limit")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskState:
    """Current risk metrics for the portfolio."""
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    max_daily_loss_pct: float = -5.0  # circuit breaker threshold
    circuit_breaker_active: bool = False
    exposure_pct: float = 0.0
    max_exposure_pct: float = 80.0
    correlation_warning: bool = False
    correlation_details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BrainState:
    """Complete state of the bot's current market assessment."""
    market_regime: str = "unknown"  # risk_on, risk_off, neutral, volatile, unknown
    regime_confidence: int = 0  # 0-100
    overall_sentiment: float = 0.0  # -1.0 to 1.0
    active_themes: List[ThemeAssessment] = field(default_factory=list)
    planned_actions: List[PlannedAction] = field(default_factory=list)
    risk_state: RiskState = field(default_factory=RiskState)
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "market_regime": self.market_regime,
            "regime_confidence": self.regime_confidence,
            "overall_sentiment": self.overall_sentiment,
            "active_themes": [t.to_dict() for t in self.active_themes],
            "planned_actions": [a.to_dict() for a in self.planned_actions],
            "risk_state": self.risk_state.to_dict(),
            "last_updated": self.last_updated,
        }
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BrainState":
        state = cls()
        state.market_regime = d.get("market_regime", "unknown")
        state.regime_confidence = d.get("regime_confidence", 0)
        state.overall_sentiment = d.get("overall_sentiment", 0.0)
        state.last_updated = d.get("last_updated", "")

        for t in d.get("active_themes", []):
            state.active_themes.append(ThemeAssessment(**t))
        for a in d.get("planned_actions", []):
            state.planned_actions.append(PlannedAction(**a))

        risk = d.get("risk_state", {})
        if risk:
            state.risk_state = RiskState(**{
                k: v for k, v in risk.items() if k in RiskState.__dataclass_fields__
            })

        return state


class BotBrain:
    """
    Central thinking engine that combines all signals into a market assessment.

    Evaluates market regime, generates trade plans, and enforces circuit
    breakers. State is persisted to data/brain-state.json for dashboard
    display and recovery across restarts.

    Usage:
        brain = BotBrain()
        brain.assess_regime()
        brain.plan_trades()
        brain.check_circuit_breakers()
        state = brain.get_state()
    """

    def __init__(self, state_file: Optional[str] = None):
        self.state_file = state_file or BRAIN_STATE_FILE
        self.state = BrainState()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self._load_state()

    def _load_state(self) -> None:
        """Load brain state from disk."""
        if not os.path.isfile(self.state_file):
            return
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            self.state = BrainState.from_dict(data)
            logger.info("Loaded brain state from %s", self.state_file)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to load brain state: %s", e)

    def _save_state(self) -> None:
        """Persist brain state to disk."""
        self.state.last_updated = datetime.now(timezone.utc).isoformat()
        with open(self.state_file, "w") as f:
            json.dump(self.state.to_dict(), f, indent=2, default=str)

    def _load_signals(self) -> Dict[str, Any]:
        """Load the latest signal snapshot."""
        signals_file = os.path.join(SNAPSHOTS_DIR, "latest-signals.json")
        if not os.path.isfile(signals_file):
            return {}
        try:
            with open(signals_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _load_themes_config(self) -> List[Dict[str, Any]]:
        """Load theme configuration."""
        themes_file = os.path.join(CONFIG_DIR, "themes.json")
        if not os.path.isfile(themes_file):
            return []
        try:
            with open(themes_file, "r") as f:
                data = json.load(f)
            return data.get("themes", [])
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _load_portfolio(self) -> Dict[str, Any]:
        """Load current portfolio state."""
        portfolio_file = os.path.join(BASE_DIR, "data", "paper-trades", "portfolio.json")
        if not os.path.isfile(portfolio_file):
            # Try _state.json
            portfolio_file = os.path.join(BASE_DIR, "data", "paper-trades", "_state.json")
        if not os.path.isfile(portfolio_file):
            return {}
        try:
            with open(portfolio_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def assess_regime(self) -> str:
        """
        Evaluate all macro signals to determine the current market regime.

        Reads the latest signals snapshot and classifies the market as:
        - risk_on: majority of signals positive, low volatility
        - risk_off: majority negative, elevated fear indicators
        - volatile: mixed signals with high dispersion
        - neutral: no strong directional signal
        - unknown: insufficient data

        Returns the determined regime string.
        """
        signals_data = self._load_signals()
        signals = signals_data.get("signals", [])

        if not signals:
            self.state.market_regime = "unknown"
            self.state.regime_confidence = 0
            self._save_state()
            return "unknown"

        # Score signals
        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        volatility_elevated = False

        for sig in signals:
            status = sig.get("status", "").lower()
            direction = sig.get("direction", "").lower()
            name = sig.get("name", "").lower()

            # Check for volatility indicators
            if "vix" in name or "volatility" in name:
                value = sig.get("value")
                if value is not None and isinstance(value, (int, float)):
                    if value > 25:
                        volatility_elevated = True

            if status == "awaiting_data":
                continue

            if any(w in direction for w in ["bullish", "up", "positive", "above"]):
                bullish_count += 1
            elif any(w in direction for w in ["bearish", "down", "negative", "below"]):
                bearish_count += 1
            else:
                neutral_count += 1

        total = bullish_count + bearish_count + neutral_count
        if total == 0:
            regime = "unknown"
            confidence = 0
        elif volatility_elevated and abs(bullish_count - bearish_count) < total * 0.3:
            regime = "volatile"
            confidence = min(80, 40 + abs(bullish_count - bearish_count) * 10)
        elif bullish_count > bearish_count * 1.5:
            regime = "risk_on"
            confidence = min(95, int((bullish_count / total) * 100))
        elif bearish_count > bullish_count * 1.5:
            regime = "risk_off"
            confidence = min(95, int((bearish_count / total) * 100))
        else:
            regime = "neutral"
            confidence = max(20, 60 - abs(bullish_count - bearish_count) * 5)

        self.state.market_regime = regime
        self.state.regime_confidence = confidence

        # Calculate overall sentiment (-1 to 1)
        if total > 0:
            self.state.overall_sentiment = round(
                (bullish_count - bearish_count) / total, 2
            )
        else:
            self.state.overall_sentiment = 0.0

        # Assess themes
        self._assess_themes(signals)

        self._save_state()
        logger.info(
            "Regime assessment: %s (confidence=%d%%, sentiment=%.2f)",
            regime, confidence, self.state.overall_sentiment,
        )
        return regime

    def _assess_themes(self, signals: List[Dict[str, Any]]) -> None:
        """Evaluate conviction for each configured theme based on signals."""
        themes_config = self._load_themes_config()
        self.state.active_themes = []

        for theme in themes_config:
            if theme.get("status") != "active":
                continue

            theme_id = theme.get("id", "")
            theme_name = theme.get("name", theme_id)
            supporting = []
            against = []

            # Check theme's macro signals
            for sig_config in theme.get("macro_signals", []):
                sig_name = sig_config.get("signal", sig_config.get("name", ""))
                sig_direction = sig_config.get("direction", "").lower()

                # Find matching signal in latest data
                for sig_data in signals:
                    data_name = sig_data.get("name", "")
                    if data_name.lower() != sig_name.lower():
                        continue
                    data_status = sig_data.get("status", "").lower()
                    if data_status == "awaiting_data":
                        continue

                    # Does actual data align with expected direction?
                    data_direction = sig_data.get("direction", "").lower()
                    if sig_direction in data_direction or data_direction in sig_direction:
                        supporting.append(data_name)
                    else:
                        against.append(data_name)

            # Calculate conviction
            total_signals = len(supporting) + len(against)
            if total_signals > 0:
                conviction = round((len(supporting) - len(against)) / total_signals, 2)
            else:
                conviction = 0.0

            self.state.active_themes.append(ThemeAssessment(
                theme_id=theme_id,
                theme_name=theme_name,
                conviction=conviction,
                signals_supporting=supporting,
                signals_against=against,
            ))

    def plan_trades(
        self,
        theses: Optional[List[Dict[str, Any]]] = None,
        overrides: Optional[List[Dict[str, Any]]] = None,
    ) -> List[PlannedAction]:
        """
        Generate planned trade actions based on signals, theses, and overrides.

        This method evaluates the current regime, active theses, and signal
        overrides to produce a prioritized list of trade actions.

        Args:
            theses: List of active thesis dicts (from ThesisManager).
            overrides: List of active override dicts (from OverrideManager).

        Returns:
            List of PlannedAction objects.
        """
        theses = theses or []
        overrides = overrides or []
        planned: List[PlannedAction] = []

        portfolio = self._load_portfolio()
        positions = portfolio.get("positions", {})

        # Check if kill switch is active
        kill_switch_file = os.path.join(BASE_DIR, "data", "kill-switch.json")
        kill_switch_active = False
        if os.path.isfile(kill_switch_file):
            try:
                with open(kill_switch_file, "r") as f:
                    ks = json.load(f)
                kill_switch_active = ks.get("active", False)
            except (json.JSONDecodeError, FileNotFoundError):
                pass

        blocker = "kill_switch" if kill_switch_active else None

        # Risk-off regime: plan defensive actions
        if self.state.market_regime == "risk_off":
            # Close positions that don't have strong thesis support
            for mid, pos in positions.items():
                has_thesis = any(
                    mid in str(t.get("affected_tickers", []))
                    for t in theses
                    if t.get("status") == "active" and t.get("direction") == "bullish"
                )
                if not has_thesis:
                    planned.append(PlannedAction(
                        action_type="close",
                        market=pos.get("market_name", mid),
                        direction="close",
                        size_pct=100,
                        reasoning=f"Risk-off regime, no supporting thesis for {pos.get('market_name', mid)}",
                        priority=2,
                        blocked_by=blocker,
                    ))

        # Thesis-driven actions
        for thesis in theses:
            if thesis.get("status") != "active":
                continue

            direction = thesis.get("direction", "neutral")
            if direction == "neutral":
                continue

            confidence = thesis.get("confidence", 50)
            size_pct = min(10, confidence / 10)  # higher confidence = bigger position

            for ticker in thesis.get("affected_tickers", []):
                action_type = "buy" if direction == "bullish" else "sell"
                trade_direction = "long" if direction == "bullish" else "short"

                planned.append(PlannedAction(
                    action_type=action_type,
                    market=ticker,
                    direction=trade_direction,
                    size_pct=round(size_pct, 1),
                    reasoning=f"Thesis: {thesis.get('title', 'untitled')} "
                              f"(confidence={confidence}%, {direction})",
                    priority=3 if confidence >= 70 else 4,
                    blocked_by=blocker,
                ))

        # Apply regime adjustments
        if self.state.market_regime == "volatile":
            for action in planned:
                action.size_pct = round(action.size_pct * 0.5, 1)
                action.reasoning += " [size reduced: volatile regime]"

        # Circuit breaker check
        if self.state.risk_state.circuit_breaker_active:
            for action in planned:
                if action.action_type in ("buy", "sell"):
                    action.blocked_by = "circuit_breaker"

        self.state.planned_actions = planned
        self._save_state()
        logger.info("Planned %d trade actions", len(planned))
        return planned

    def check_circuit_breakers(
        self,
        daily_pnl: float = 0.0,
        daily_pnl_pct: float = 0.0,
        exposure_pct: float = 0.0,
    ) -> RiskState:
        """
        Verify daily loss limits, exposure limits, and correlation limits.

        Args:
            daily_pnl: Today's P&L in USD.
            daily_pnl_pct: Today's P&L as percentage.
            exposure_pct: Current portfolio exposure percentage.

        Returns:
            Updated RiskState.
        """
        risk = self.state.risk_state
        risk.daily_pnl = daily_pnl
        risk.daily_pnl_pct = daily_pnl_pct
        risk.exposure_pct = exposure_pct

        # Daily loss circuit breaker
        if daily_pnl_pct <= risk.max_daily_loss_pct:
            risk.circuit_breaker_active = True
            logger.warning(
                "CIRCUIT BREAKER ACTIVE: daily P&L %.2f%% exceeds limit %.2f%%",
                daily_pnl_pct, risk.max_daily_loss_pct,
            )
        else:
            risk.circuit_breaker_active = False

        # Exposure warning
        if exposure_pct > risk.max_exposure_pct:
            logger.warning(
                "Exposure %.1f%% exceeds max %.1f%%",
                exposure_pct, risk.max_exposure_pct,
            )

        # Correlation check: if >60% of portfolio is in one theme, warn
        portfolio = self._load_portfolio()
        positions = portfolio.get("positions", {})
        if positions:
            theme_costs: Dict[str, float] = {}
            total_cost = 0.0
            for pos in positions.values():
                cost = pos.get("entry_price", 0) * pos.get("quantity", 0)
                theme = pos.get("theme_id", "unknown")
                theme_costs[theme] = theme_costs.get(theme, 0) + cost
                total_cost += cost

            if total_cost > 0:
                for theme, cost in theme_costs.items():
                    pct = (cost / total_cost) * 100
                    if pct > 60:
                        risk.correlation_warning = True
                        risk.correlation_details = (
                            f"Theme '{theme}' represents {pct:.0f}% of portfolio"
                        )
                        break
                else:
                    risk.correlation_warning = False
                    risk.correlation_details = ""

        self.state.risk_state = risk
        self._save_state()
        return risk

    def get_state(self) -> BrainState:
        """Return the full brain state for dashboard display."""
        return self.state

    def get_state_dict(self) -> Dict[str, Any]:
        """Return brain state as a serializable dict."""
        return self.state.to_dict()

    def update_sentiment(self, sentiment: float) -> None:
        """Manually update the overall sentiment score."""
        self.state.overall_sentiment = max(-1.0, min(1.0, sentiment))
        self._save_state()

    def set_regime(self, regime: str, confidence: int = 50) -> None:
        """Manually set the market regime (for overrides/testing)."""
        if regime not in VALID_REGIMES:
            raise ValueError(f"Invalid regime: {regime}. Must be one of {VALID_REGIMES}")
        self.state.market_regime = regime
        self.state.regime_confidence = max(0, min(100, confidence))
        self._save_state()
