"""
Correlation tracker for the trading bot.

Avoids concentrated bets that blow up together by monitoring
pairwise correlations across open positions and suggesting
hedges when the portfolio becomes too correlated.
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yfinance as yf


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] correlation_tracker: {msg}")


@dataclass
class CorrelationReport:
    """Results of a portfolio correlation analysis."""
    correlation_matrix: Dict[str, Dict[str, float]]
    high_correlations: List[Dict[str, Any]]  # pairs with correlation > threshold
    diversification_score: float  # 0-100, higher = more diversified
    warnings: List[str]
    suggested_hedges: List[Dict[str, Any]]
    tickers_analyzed: List[str]
    timestamp: str
    period_days: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_matrix": self.correlation_matrix,
            "high_correlations": self.high_correlations,
            "diversification_score": round(self.diversification_score, 1),
            "warnings": self.warnings,
            "suggested_hedges": self.suggested_hedges,
            "tickers_analyzed": self.tickers_analyzed,
            "timestamp": self.timestamp,
            "period_days": self.period_days,
        }


# Common hedge instruments and their typical negative correlations
_HEDGE_CANDIDATES = {
    "^VIX": "VIX (volatility hedge)",
    "GLD": "Gold ETF",
    "TLT": "20+ Year Treasury ETF",
    "SH": "Short S&P 500 ETF",
    "SQQQ": "3x Short Nasdaq ETF",
    "UUP": "US Dollar Bullish ETF",
}


class CorrelationTracker:
    """
    Tracks correlations between portfolio positions and market instruments.

    Computes pairwise correlations from daily returns over a lookback
    period, flags concentrated bets, and suggests hedges.

    Usage:
        from src.core.config import Config
        cfg = Config()
        tracker = CorrelationTracker(cfg.project_root)
        report = tracker.calculate_correlations(["AAPL", "MSFT", "GOOGL"])
        score = tracker.get_diversification_score()
    """

    # Cache correlation results for up to 6 hours
    _CACHE_TTL_SECONDS = 6 * 3600

    def __init__(self, project_root: str, correlation_threshold: float = 0.7):
        self.project_root = project_root
        self.data_dir = os.path.join(project_root, "data")
        os.makedirs(self.data_dir, exist_ok=True)

        self.threshold = correlation_threshold
        self._cache: Optional[CorrelationReport] = None
        self._cache_time: float = 0.0
        self._cache_key: Optional[str] = None  # hash of tickers + period

        _log(f"initialized with threshold={correlation_threshold}")

    def _fetch_returns(
        self, tickers: List[str], period_days: int
    ) -> Tuple[Dict[str, List[float]], List[str]]:
        """
        Fetch daily returns for a list of tickers.

        Returns:
            Tuple of (returns_dict, valid_tickers).
            returns_dict maps ticker to list of daily returns.
            valid_tickers is the list of tickers that had data.
        """
        period_map = {
            30: "1mo",
            60: "3mo",
            90: "3mo",
            180: "6mo",
            365: "1y",
        }
        # Find closest period
        yf_period = "3mo"
        for days, period_str in sorted(period_map.items()):
            if period_days <= days:
                yf_period = period_str
                break

        returns_dict: Dict[str, List[float]] = {}
        valid_tickers: List[str] = []

        for ticker in tickers:
            try:
                data = yf.download(ticker, period=yf_period, progress=False, auto_adjust=True)
                if data is None or data.empty or len(data) < 10:
                    _log(f"insufficient data for {ticker}, skipping")
                    continue
                close = data["Close"]
                if hasattr(close, "columns"):
                    close = close.iloc[:, 0]
                daily_returns = close.pct_change().dropna().tolist()
                if len(daily_returns) >= 10:
                    returns_dict[ticker] = daily_returns
                    valid_tickers.append(ticker)
            except Exception as e:
                _log(f"failed to fetch {ticker}: {e}")

        return returns_dict, valid_tickers

    def _align_returns(
        self, returns_dict: Dict[str, List[float]]
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Align return series to the same length (minimum common length).

        Returns a 2D numpy array (rows=observations, cols=tickers) and
        the list of tickers in column order.
        """
        if not returns_dict:
            return np.array([]), []

        tickers = list(returns_dict.keys())
        min_len = min(len(returns_dict[t]) for t in tickers)

        # Use the most recent min_len observations
        matrix = np.zeros((min_len, len(tickers)))
        for i, ticker in enumerate(tickers):
            series = returns_dict[ticker]
            matrix[:, i] = series[-min_len:]

        return matrix, tickers

    def calculate_correlations(
        self, tickers: List[str], period_days: int = 60
    ) -> CorrelationReport:
        """
        Calculate pairwise correlations for a set of tickers.

        Args:
            tickers: List of ticker symbols.
            period_days: Lookback period for return calculation.

        Returns:
            CorrelationReport with full matrix, high-correlation pairs,
            diversification score, and hedge suggestions.
        """
        cache_key = f"{sorted(tickers)}_{period_days}"
        if (
            self._cache is not None
            and self._cache_key == cache_key
            and (time.monotonic() - self._cache_time) < self._CACHE_TTL_SECONDS
        ):
            _log("returning cached correlation report")
            return self._cache

        now = datetime.now(timezone.utc).isoformat()
        warnings: List[str] = []
        high_corrs: List[Dict[str, Any]] = []

        if len(tickers) < 2:
            report = CorrelationReport(
                correlation_matrix={},
                high_correlations=[],
                diversification_score=100.0,
                warnings=["Need at least 2 tickers for correlation analysis"],
                suggested_hedges=[],
                tickers_analyzed=tickers,
                timestamp=now,
                period_days=period_days,
            )
            self._cache = report
            self._cache_time = time.monotonic()
            self._cache_key = cache_key
            return report

        _log(f"calculating correlations for {len(tickers)} tickers, period={period_days}d")

        returns_dict, valid_tickers = self._fetch_returns(tickers, period_days)

        skipped = set(tickers) - set(valid_tickers)
        if skipped:
            warnings.append(f"No data for: {', '.join(sorted(skipped))}")

        if len(valid_tickers) < 2:
            report = CorrelationReport(
                correlation_matrix={},
                high_correlations=[],
                diversification_score=100.0,
                warnings=warnings + ["Fewer than 2 tickers with valid data"],
                suggested_hedges=[],
                tickers_analyzed=valid_tickers,
                timestamp=now,
                period_days=period_days,
            )
            self._cache = report
            self._cache_time = time.monotonic()
            self._cache_key = cache_key
            return report

        matrix, aligned_tickers = self._align_returns(returns_dict)

        # Compute correlation matrix
        try:
            corr_matrix = np.corrcoef(matrix, rowvar=False)
        except Exception as e:
            _log(f"correlation computation failed: {e}")
            corr_matrix = np.eye(len(aligned_tickers))
            warnings.append(f"Correlation computation error: {e}")

        # Handle NaN values
        corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)

        # Build correlation dict
        corr_dict: Dict[str, Dict[str, float]] = {}
        for i, t1 in enumerate(aligned_tickers):
            corr_dict[t1] = {}
            for j, t2 in enumerate(aligned_tickers):
                corr_dict[t1][t2] = round(float(corr_matrix[i, j]), 4)

        # Find high-correlation pairs
        seen_pairs = set()
        for i in range(len(aligned_tickers)):
            for j in range(i + 1, len(aligned_tickers)):
                corr_val = float(corr_matrix[i, j])
                if abs(corr_val) >= self.threshold:
                    pair_key = tuple(sorted([aligned_tickers[i], aligned_tickers[j]]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        high_corrs.append({
                            "ticker_a": aligned_tickers[i],
                            "ticker_b": aligned_tickers[j],
                            "correlation": round(corr_val, 4),
                            "risk": "HIGH" if abs(corr_val) > 0.85 else "MODERATE",
                        })

        if high_corrs:
            warnings.append(
                f"{len(high_corrs)} highly correlated pair(s) detected "
                f"(threshold: {self.threshold})"
            )

        # Diversification score: based on average pairwise correlation
        n = len(aligned_tickers)
        if n >= 2:
            # Extract upper triangle (excluding diagonal)
            upper_corrs = []
            for i in range(n):
                for j in range(i + 1, n):
                    upper_corrs.append(abs(float(corr_matrix[i, j])))
            avg_corr = sum(upper_corrs) / len(upper_corrs) if upper_corrs else 0.0
            # Score: 0 avg corr = 100, 1.0 avg corr = 0
            diversification_score = max(0.0, min(100.0, (1.0 - avg_corr) * 100))
        else:
            diversification_score = 100.0

        # Suggest hedges
        hedges = self._suggest_hedges(aligned_tickers, returns_dict, period_days)

        report = CorrelationReport(
            correlation_matrix=corr_dict,
            high_correlations=high_corrs,
            diversification_score=diversification_score,
            warnings=warnings,
            suggested_hedges=hedges,
            tickers_analyzed=aligned_tickers,
            timestamp=now,
            period_days=period_days,
        )

        # Cache the result
        self._cache = report
        self._cache_time = time.monotonic()
        self._cache_key = cache_key

        _log(
            f"correlation analysis complete: {len(aligned_tickers)} tickers, "
            f"diversification={diversification_score:.1f}, "
            f"high_corr_pairs={len(high_corrs)}"
        )

        return report

    def check_portfolio_correlation(
        self, positions: Dict[str, Any], period_days: int = 60
    ) -> CorrelationReport:
        """
        Check correlations across open portfolio positions.

        Args:
            positions: Dict mapping market_id to position data.
                Each position should have a "ticker" or "market_name" key.

        Returns:
            CorrelationReport for the current portfolio.
        """
        tickers = []
        for pos_data in positions.values():
            ticker = None
            if isinstance(pos_data, dict):
                ticker = pos_data.get("ticker") or pos_data.get("market_name")
            elif hasattr(pos_data, "market_name"):
                ticker = pos_data.market_name
            if ticker:
                tickers.append(ticker)

        if not tickers:
            return CorrelationReport(
                correlation_matrix={},
                high_correlations=[],
                diversification_score=100.0,
                warnings=["No positions with ticker data to analyze"],
                suggested_hedges=[],
                tickers_analyzed=[],
                timestamp=datetime.now(timezone.utc).isoformat(),
                period_days=period_days,
            )

        return self.calculate_correlations(tickers, period_days)

    def get_diversification_score(self) -> float:
        """
        Return the most recent diversification score (0-100).

        Returns 100.0 if no analysis has been run yet.
        """
        if self._cache is not None:
            return self._cache.diversification_score
        return 100.0

    def _suggest_hedges(
        self,
        portfolio_tickers: List[str],
        portfolio_returns: Dict[str, List[float]],
        period_days: int,
    ) -> List[Dict[str, Any]]:
        """
        Suggest hedging instruments based on negative correlations.

        Fetches returns for common hedge instruments and identifies
        those with the most negative correlation to the portfolio.
        """
        if not portfolio_tickers:
            return []

        hedges: List[Dict[str, Any]] = []

        # Get hedge candidate returns
        hedge_tickers = [t for t in _HEDGE_CANDIDATES if t not in portfolio_tickers]
        if not hedge_tickers:
            return []

        hedge_returns, valid_hedges = self._fetch_returns(hedge_tickers, period_days)

        if not valid_hedges or not portfolio_returns:
            return []

        # Calculate average portfolio return series
        min_len = min(len(portfolio_returns[t]) for t in portfolio_tickers)
        min_len = min(min_len, min(len(hedge_returns[t]) for t in valid_hedges))

        if min_len < 10:
            return []

        # Average portfolio returns
        port_matrix = np.zeros((min_len, len(portfolio_tickers)))
        for i, t in enumerate(portfolio_tickers):
            port_matrix[:, i] = portfolio_returns[t][-min_len:]
        avg_port_returns = port_matrix.mean(axis=1)

        # Check each hedge
        for hedge_ticker in valid_hedges:
            hedge_ret = np.array(hedge_returns[hedge_ticker][-min_len:])
            try:
                corr = float(np.corrcoef(avg_port_returns, hedge_ret)[0, 1])
            except Exception:
                continue

            if np.isnan(corr):
                continue

            if corr < -0.2:  # Only suggest meaningfully negative correlations
                hedges.append({
                    "ticker": hedge_ticker,
                    "name": _HEDGE_CANDIDATES.get(hedge_ticker, hedge_ticker),
                    "correlation_to_portfolio": round(corr, 4),
                    "hedge_effectiveness": "STRONG" if corr < -0.5 else "MODERATE",
                })

        # Sort by most negative correlation
        hedges.sort(key=lambda h: h["correlation_to_portfolio"])

        return hedges[:5]  # Top 5 suggestions


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    tracker = CorrelationTracker(root)

    # Test with some tech stocks
    tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
    report = tracker.calculate_correlations(tickers, period_days=60)
    print(json.dumps(report.to_dict(), indent=2))
