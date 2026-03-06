"""
Cross-market correlation engine.

Computes rolling correlations between global markets to identify:
1. Correlation breakdowns (historically correlated markets diverging)
2. Unusual correlations (historically uncorrelated markets moving together)
3. Risk concentration (everything moving in lockstep = systemic risk)
4. Decorrelation opportunities (pairs that move independently for hedging)
5. Regime shifts (correlation structure changes signal regime transitions)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import yfinance as yf
    import numpy as np
    import pandas as pd
except ImportError:
    yf = None
    np = None
    pd = None


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] cross_corr: {msg}")


# Core universe for correlation analysis
CORRELATION_UNIVERSE = {
    # Equity indices
    "^GSPC":    "S&P 500",
    "^IXIC":    "Nasdaq",
    "^N225":    "Nikkei",
    "^GDAXI":   "DAX",
    "^FTSE":    "FTSE 100",
    "^HSI":     "Hang Seng",
    "000001.SS":"Shanghai",
    "^AXJO":    "ASX 200",
    "^BVSP":    "Bovespa",
    # Rates/Bonds
    "^TNX":     "US 10Y",
    # Commodities
    "GC=F":     "Gold",
    "CL=F":     "WTI Oil",
    "HG=F":     "Copper",
    # Crypto
    "BTC-USD":  "Bitcoin",
    "ETH-USD":  "Ethereum",
    # FX
    "DX-Y.NYB": "Dollar Index",
    "USDJPY=X": "USD/JPY",
}


@dataclass
class CorrelationPair:
    ticker_a: str
    name_a: str
    ticker_b: str
    name_b: str
    correlation_30d: Optional[float] = None
    correlation_90d: Optional[float] = None
    correlation_change: Optional[float] = None  # 30d minus 90d
    is_breakdown: bool = False      # historically correlated, now diverging
    is_unusual: bool = False        # historically uncorrelated, now correlated
    is_concentrated: bool = False   # very high correlation = risk
    signal: str = "neutral"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker_a": self.ticker_a,
            "name_a": self.name_a,
            "ticker_b": self.ticker_b,
            "name_b": self.name_b,
            "correlation_30d": self.correlation_30d,
            "correlation_90d": self.correlation_90d,
            "correlation_change": self.correlation_change,
            "is_breakdown": self.is_breakdown,
            "is_unusual": self.is_unusual,
            "is_concentrated": self.is_concentrated,
            "signal": self.signal,
            "description": self.description,
        }


@dataclass
class CorrelationMatrix:
    tickers: List[str]
    names: List[str]
    matrix_30d: List[List[Optional[float]]]
    matrix_90d: List[List[Optional[float]]]
    avg_correlation_30d: float = 0.0
    avg_correlation_90d: float = 0.0
    systemic_risk_score: float = 0.0  # 0-100, high = everything correlated

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tickers": self.tickers,
            "names": self.names,
            "matrix_30d": self.matrix_30d,
            "matrix_90d": self.matrix_90d,
            "avg_correlation_30d": self.avg_correlation_30d,
            "avg_correlation_90d": self.avg_correlation_90d,
            "systemic_risk_score": self.systemic_risk_score,
        }


class CrossCorrelationEngine:
    """
    Computes and analyzes cross-market correlations.
    """

    def __init__(self, lookback_days: int = 120):
        self.lookback_days = lookback_days
        self._prices_df: Optional[Any] = None

    def _fetch_prices(self, tickers: List[str]) -> Optional[Any]:
        """Fetch closing prices for all tickers into a DataFrame."""
        if yf is None or pd is None:
            return None

        try:
            data = yf.download(
                tickers,
                period=f"{self.lookback_days + 30}d",
                progress=False,
                auto_adjust=True,
                group_by="ticker",
            )
            if data is None or data.empty:
                return None

            # Extract Close prices
            closes = {}
            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        close = data["Close"]
                    else:
                        close = data[ticker]["Close"] if ticker in data.columns.get_level_values(0) else None
                    if close is not None and not close.empty:
                        closes[ticker] = close
                except Exception:
                    pass

            if not closes:
                return None

            df = pd.DataFrame(closes)
            return df.dropna(how="all")

        except Exception as e:
            _log(f"fetch failed: {e}")
            return None

    def compute_matrix(self, tickers: Optional[List[str]] = None) -> CorrelationMatrix:
        """
        Compute correlation matrices at 30d and 90d windows.
        """
        if tickers is None:
            tickers = list(CORRELATION_UNIVERSE.keys())

        names = [CORRELATION_UNIVERSE.get(t, t) for t in tickers]

        if pd is None or np is None:
            return CorrelationMatrix(
                tickers=tickers, names=names,
                matrix_30d=[], matrix_90d=[],
            )

        _log(f"fetching prices for {len(tickers)} tickers...")
        df = self._fetch_prices(tickers)
        if df is None or df.empty:
            _log("no price data available")
            return CorrelationMatrix(
                tickers=tickers, names=names,
                matrix_30d=[], matrix_90d=[],
            )

        self._prices_df = df

        # Compute daily returns
        returns = df.pct_change().dropna()

        # Available tickers (some may have failed)
        avail = [t for t in tickers if t in returns.columns]
        avail_names = [CORRELATION_UNIVERSE.get(t, t) for t in avail]

        # 30-day correlation
        ret_30 = returns.tail(30)
        corr_30 = ret_30[avail].corr()

        # 90-day correlation
        ret_90 = returns.tail(90)
        corr_90 = ret_90[avail].corr()

        # Convert to nested lists (ensure native Python types)
        matrix_30 = [[round(float(corr_30.iloc[i, j]), 3) if not pd.isna(corr_30.iloc[i, j]) else None
                       for j in range(len(avail))] for i in range(len(avail))]
        matrix_90 = [[round(float(corr_90.iloc[i, j]), 3) if not pd.isna(corr_90.iloc[i, j]) else None
                       for j in range(len(avail))] for i in range(len(avail))]

        # Average off-diagonal correlation
        off_diag_30 = []
        off_diag_90 = []
        for i in range(len(avail)):
            for j in range(i + 1, len(avail)):
                v30 = corr_30.iloc[i, j]
                v90 = corr_90.iloc[i, j]
                if not pd.isna(v30):
                    off_diag_30.append(abs(v30))
                if not pd.isna(v90):
                    off_diag_90.append(abs(v90))

        avg_30 = round(float(np.mean(off_diag_30)), 3) if off_diag_30 else 0
        avg_90 = round(float(np.mean(off_diag_90)), 3) if off_diag_90 else 0

        # Systemic risk: avg absolute correlation * 100
        systemic = round(avg_30 * 100, 1)

        _log(f"matrix computed: {len(avail)} tickers, avg_corr_30d={avg_30}, systemic_risk={systemic}")

        return CorrelationMatrix(
            tickers=avail,
            names=avail_names,
            matrix_30d=matrix_30,
            matrix_90d=matrix_90,
            avg_correlation_30d=avg_30,
            avg_correlation_90d=avg_90,
            systemic_risk_score=systemic,
        )

    def find_anomalies(self, matrix: CorrelationMatrix) -> List[CorrelationPair]:
        """
        Identify correlation anomalies: breakdowns, unusual correlations, concentration.
        """
        pairs = []
        n = len(matrix.tickers)

        for i in range(n):
            for j in range(i + 1, n):
                c30 = matrix.matrix_30d[i][j] if i < len(matrix.matrix_30d) and j < len(matrix.matrix_30d[i]) else None
                c90 = matrix.matrix_90d[i][j] if i < len(matrix.matrix_90d) and j < len(matrix.matrix_90d[i]) else None

                if c30 is None or c90 is None:
                    continue

                change = round(float(c30 - c90), 3)
                is_breakdown = bool(c90 > 0.6 and c30 < 0.3)
                is_unusual = bool(abs(c90) < 0.3 and abs(c30) > 0.6)
                is_concentrated = bool(c30 > 0.85)

                signal = "neutral"
                desc = ""

                if is_breakdown:
                    signal = "breakdown"
                    desc = (f"{matrix.names[i]} and {matrix.names[j]} historically correlated "
                            f"(90d: {c90:.2f}) but now diverging (30d: {c30:.2f}). "
                            f"Potential mean-reversion opportunity or regime shift.")
                elif is_unusual:
                    signal = "unusual"
                    desc = (f"{matrix.names[i]} and {matrix.names[j]} historically uncorrelated "
                            f"(90d: {c90:.2f}) but now moving together (30d: {c30:.2f}). "
                            f"May indicate contagion or shared driver.")
                elif is_concentrated:
                    signal = "concentration_risk"
                    desc = (f"{matrix.names[i]} and {matrix.names[j]} extremely correlated "
                            f"(30d: {c30:.2f}). Holding both adds no diversification.")

                if signal != "neutral":
                    pairs.append(CorrelationPair(
                        ticker_a=matrix.tickers[i],
                        name_a=matrix.names[i],
                        ticker_b=matrix.tickers[j],
                        name_b=matrix.names[j],
                        correlation_30d=c30,
                        correlation_90d=c90,
                        correlation_change=change,
                        is_breakdown=is_breakdown,
                        is_unusual=is_unusual,
                        is_concentrated=is_concentrated,
                        signal=signal,
                        description=desc,
                    ))

        # Sort by absolute change (most significant first)
        pairs.sort(key=lambda p: abs(p.correlation_change or 0), reverse=True)
        _log(f"found {len(pairs)} correlation anomalies")
        return pairs

    def full_analysis(self) -> Dict[str, Any]:
        """Run complete correlation analysis."""
        matrix = self.compute_matrix()
        anomalies = self.find_anomalies(matrix)

        # Top 5 most correlated pairs (30d)
        top_correlated = []
        n = len(matrix.tickers)
        all_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                c30 = matrix.matrix_30d[i][j] if i < len(matrix.matrix_30d) and j < len(matrix.matrix_30d[i]) else None
                if c30 is not None:
                    all_pairs.append((matrix.names[i], matrix.names[j], c30))

        all_pairs.sort(key=lambda x: x[2], reverse=True)
        top_correlated = [{"pair": f"{a} / {b}", "correlation": c} for a, b, c in all_pairs[:10]]

        # Top 5 most negatively correlated (hedges)
        all_pairs.sort(key=lambda x: x[2])
        best_hedges = [{"pair": f"{a} / {b}", "correlation": c} for a, b, c in all_pairs[:10]]

        return {
            "matrix": matrix.to_dict(),
            "anomalies": [a.to_dict() for a in anomalies],
            "top_correlated": top_correlated,
            "best_hedges": best_hedges,
            "systemic_risk_score": matrix.systemic_risk_score,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }


# ------------------------------------------------------------------
if __name__ == "__main__":
    engine = CrossCorrelationEngine()
    result = engine.full_analysis()
    print(json.dumps(result, indent=2))
