"""
Market regime detector for the trading bot.

Detects market regime shifts -- the #1 killer of trading bots.
Uses VIX, S&P 500 trend, yield curve, and credit spreads to
classify the current environment and adjust risk accordingly.

Regimes: BULL_QUIET, BULL_VOLATILE, BEAR_QUIET, BEAR_VOLATILE, SIDEWAYS, CRISIS
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

import yfinance as yf


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] regime_detector: {msg}")


class Regime(str, Enum):
    BULL_QUIET = "BULL_QUIET"
    BULL_VOLATILE = "BULL_VOLATILE"
    BEAR_QUIET = "BEAR_QUIET"
    BEAR_VOLATILE = "BEAR_VOLATILE"
    SIDEWAYS = "SIDEWAYS"
    CRISIS = "CRISIS"


# Risk multipliers: 0.0 = halt all trading, 1.0 = full risk budget
_RISK_MULTIPLIERS: Dict[Regime, float] = {
    Regime.CRISIS: 0.0,
    Regime.BEAR_VOLATILE: 0.3,
    Regime.BEAR_QUIET: 0.5,
    Regime.SIDEWAYS: 0.7,
    Regime.BULL_VOLATILE: 0.8,
    Regime.BULL_QUIET: 1.0,
}


@dataclass
class RegimeSnapshot:
    """Point-in-time regime classification with supporting data."""
    regime: Regime
    risk_multiplier: float
    timestamp: str
    vix_level: Optional[float] = None
    vix_50d_ma: Optional[float] = None
    sp500_price: Optional[float] = None
    sp500_50d_ma: Optional[float] = None
    sp500_200d_ma: Optional[float] = None
    sp500_pct_below_200d: Optional[float] = None
    yield_10y: Optional[float] = None
    yield_3m: Optional[float] = None
    yield_curve_spread: Optional[float] = None
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "risk_multiplier": self.risk_multiplier,
            "timestamp": self.timestamp,
            "vix_level": self.vix_level,
            "vix_50d_ma": self.vix_50d_ma,
            "sp500_price": self.sp500_price,
            "sp500_50d_ma": self.sp500_50d_ma,
            "sp500_200d_ma": self.sp500_200d_ma,
            "sp500_pct_below_200d": self.sp500_pct_below_200d,
            "yield_10y": self.yield_10y,
            "yield_3m": self.yield_3m,
            "yield_curve_spread": self.yield_curve_spread,
            "reasoning": self.reasoning,
        }


class RegimeDetector:
    """
    Detects market regime using VIX, S&P 500 trend, and yield curve.

    The regime determines the risk multiplier applied to all position
    sizing. In CRISIS mode, the multiplier is 0.0 (no new trades).

    Usage:
        from src.core.config import Config
        cfg = Config()
        detector = RegimeDetector(cfg.project_root)
        snapshot = detector.detect_regime()
        print(snapshot.regime, snapshot.risk_multiplier)
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.data_dir = os.path.join(project_root, "data")
        self.history_file = os.path.join(self.data_dir, "regime-history.jsonl")
        os.makedirs(self.data_dir, exist_ok=True)
        self._last_snapshot: Optional[RegimeSnapshot] = None
        _log("initialized")

    def _fetch_ticker_data(self, ticker: str, period: str = "1y") -> Optional[Any]:
        """Fetch historical price data via yfinance. Returns a DataFrame or None."""
        try:
            data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
            if data is None or data.empty:
                _log(f"no data returned for {ticker}")
                return None
            return data
        except Exception as e:
            _log(f"failed to fetch {ticker}: {e}")
            return None

    def _compute_ma(self, df: Any, window: int) -> Optional[float]:
        """Compute the simple moving average of the Close column."""
        try:
            close = df["Close"]
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]
            if len(close) < window:
                return None
            return float(close.rolling(window=window).mean().iloc[-1])
        except Exception as e:
            _log(f"MA computation failed: {e}")
            return None

    def _latest_close(self, df: Any) -> Optional[float]:
        """Get the most recent closing price from a DataFrame."""
        try:
            close = df["Close"]
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]
            return float(close.iloc[-1])
        except Exception:
            return None

    def detect_regime(self) -> RegimeSnapshot:
        """
        Analyze current market conditions and classify the regime.

        Fetches live data for:
        - ^VIX (volatility index)
        - ^GSPC (S&P 500)
        - ^TNX (10-year Treasury yield)
        - ^IRX (3-month T-bill yield)

        Returns a RegimeSnapshot with the classification and all supporting data.
        """
        now = datetime.now(timezone.utc).isoformat()
        reasons = []

        # -- Fetch data --
        vix_df = self._fetch_ticker_data("^VIX", period="6mo")
        sp_df = self._fetch_ticker_data("^GSPC", period="1y")
        tnx_df = self._fetch_ticker_data("^TNX", period="3mo")
        irx_df = self._fetch_ticker_data("^IRX", period="3mo")

        # -- VIX --
        vix_level = self._latest_close(vix_df) if vix_df is not None else None
        vix_50d_ma = self._compute_ma(vix_df, 50) if vix_df is not None else None

        # -- S&P 500 --
        sp_price = self._latest_close(sp_df) if sp_df is not None else None
        sp_50d = self._compute_ma(sp_df, 50) if sp_df is not None else None
        sp_200d = self._compute_ma(sp_df, 200) if sp_df is not None else None

        sp_pct_below_200d = None
        if sp_price is not None and sp_200d is not None and sp_200d > 0:
            sp_pct_below_200d = round(((sp_price - sp_200d) / sp_200d) * 100, 2)

        # -- Yield curve --
        yield_10y = self._latest_close(tnx_df) if tnx_df is not None else None
        yield_3m = self._latest_close(irx_df) if irx_df is not None else None
        yield_spread = None
        if yield_10y is not None and yield_3m is not None:
            yield_spread = round(yield_10y - yield_3m, 3)

        # -- Classification logic --
        # Booleans for readability
        sp_below_200d = (sp_pct_below_200d is not None and sp_pct_below_200d < 0)
        sp_below_200d_severe = (sp_pct_below_200d is not None and sp_pct_below_200d < -5)
        sp_below_50d = (sp_price is not None and sp_50d is not None and sp_price < sp_50d)
        sp_above_50d = (sp_price is not None and sp_50d is not None and sp_price >= sp_50d)
        sp_above_both = (sp_above_50d and sp_price is not None and sp_200d is not None
                         and sp_price >= sp_200d)

        vix_crisis = (vix_level is not None and vix_level > 35)
        vix_high = (vix_level is not None and vix_level > 25)
        vix_elevated = (vix_level is not None and vix_level > 20)
        vix_low = (vix_level is not None and vix_level < 18)

        # Priority-ordered regime rules
        regime = Regime.SIDEWAYS  # default

        if vix_crisis or sp_below_200d_severe:
            regime = Regime.CRISIS
            if vix_crisis:
                reasons.append(f"VIX at {vix_level:.1f} (>35 = crisis)")
            if sp_below_200d_severe:
                reasons.append(f"S&P {sp_pct_below_200d:.1f}% below 200d MA (>5% = crisis)")

        elif vix_high and sp_below_50d:
            regime = Regime.BEAR_VOLATILE
            reasons.append(f"VIX {vix_level:.1f} (>25) + S&P below 50d MA")

        elif sp_below_50d and not vix_elevated:
            regime = Regime.BEAR_QUIET
            reasons.append("S&P below 50d MA with low volatility")

        elif vix_elevated and sp_above_50d:
            regime = Regime.BULL_VOLATILE
            reasons.append(f"VIX {vix_level:.1f} (>20) but S&P above 50d MA")

        elif vix_low and sp_above_both:
            regime = Regime.BULL_QUIET
            reasons.append(f"VIX {vix_level:.1f} (<18), S&P above 50d and 200d MA")

        else:
            reasons.append("No strong directional signal, classifying as SIDEWAYS")

        # Add yield curve context
        if yield_spread is not None:
            if yield_spread < 0:
                reasons.append(f"Yield curve INVERTED ({yield_spread:.3f}%) -- recession signal")
            else:
                reasons.append(f"Yield curve normal ({yield_spread:.3f}%)")

        risk_mult = _RISK_MULTIPLIERS[regime]
        reasoning = "; ".join(reasons)

        _log(f"regime={regime.value}, risk_multiplier={risk_mult}, reason={reasoning}")

        snapshot = RegimeSnapshot(
            regime=regime,
            risk_multiplier=risk_mult,
            timestamp=now,
            vix_level=round(vix_level, 2) if vix_level else None,
            vix_50d_ma=round(vix_50d_ma, 2) if vix_50d_ma else None,
            sp500_price=round(sp_price, 2) if sp_price else None,
            sp500_50d_ma=round(sp_50d, 2) if sp_50d else None,
            sp500_200d_ma=round(sp_200d, 2) if sp_200d else None,
            sp500_pct_below_200d=sp_pct_below_200d,
            yield_10y=round(yield_10y, 3) if yield_10y else None,
            yield_3m=round(yield_3m, 3) if yield_3m else None,
            yield_curve_spread=yield_spread,
            reasoning=reasoning,
        )

        self._last_snapshot = snapshot
        self._persist(snapshot)
        return snapshot

    def get_risk_multiplier(self) -> float:
        """
        Return the current risk multiplier (0.0 to 1.0).

        If no regime detection has been run yet, performs a detection first.
        """
        if self._last_snapshot is None:
            self.detect_regime()
        return self._last_snapshot.risk_multiplier if self._last_snapshot else 0.5

    def get_last_snapshot(self) -> Optional[RegimeSnapshot]:
        """Return the most recent regime snapshot, or None."""
        if self._last_snapshot is not None:
            return self._last_snapshot
        # Try loading from history file
        return self._load_latest_from_history()

    def _persist(self, snapshot: RegimeSnapshot) -> None:
        """Append the snapshot to the JSONL history file."""
        try:
            with open(self.history_file, "a") as f:
                f.write(json.dumps(snapshot.to_dict()) + "\n")
            _log(f"persisted regime to {self.history_file}")
        except Exception as e:
            _log(f"failed to persist regime: {e}")

    def _load_latest_from_history(self) -> Optional[RegimeSnapshot]:
        """Load the most recent entry from the history file."""
        if not os.path.isfile(self.history_file):
            return None
        try:
            last_line = ""
            with open(self.history_file, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
            if not last_line:
                return None
            data = json.loads(last_line)
            snapshot = RegimeSnapshot(
                regime=Regime(data["regime"]),
                risk_multiplier=data["risk_multiplier"],
                timestamp=data["timestamp"],
                vix_level=data.get("vix_level"),
                vix_50d_ma=data.get("vix_50d_ma"),
                sp500_price=data.get("sp500_price"),
                sp500_50d_ma=data.get("sp500_50d_ma"),
                sp500_200d_ma=data.get("sp500_200d_ma"),
                sp500_pct_below_200d=data.get("sp500_pct_below_200d"),
                yield_10y=data.get("yield_10y"),
                yield_3m=data.get("yield_3m"),
                yield_curve_spread=data.get("yield_curve_spread"),
                reasoning=data.get("reasoning", ""),
            )
            self._last_snapshot = snapshot
            return snapshot
        except Exception as e:
            _log(f"failed to load history: {e}")
            return None

    def get_regime_history(self, max_entries: int = 50) -> list:
        """Load recent regime history entries."""
        if not os.path.isfile(self.history_file):
            return []
        entries = []
        try:
            with open(self.history_file, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        entries.append(json.loads(stripped))
            return entries[-max_entries:]
        except Exception as e:
            _log(f"failed to read history: {e}")
            return []


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    detector = RegimeDetector(root)
    snapshot = detector.detect_regime()
    print(json.dumps(snapshot.to_dict(), indent=2))
