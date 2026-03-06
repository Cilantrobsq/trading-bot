"""
Macro signal fetcher using yfinance.

Fetches all tickers defined in strategy.json and themes.json,
evaluates threshold alerts, and returns signal states
(bullish / bearish / neutral) per ticker.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore

from src.core.config import Config


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] macro: {msg}")


@dataclass
class TickerSignal:
    """Result of evaluating a single ticker."""
    ticker: str
    name: str
    price: Optional[float]
    prev_close: Optional[float]
    change_pct: Optional[float]
    threshold: Optional[float]
    threshold_breached: bool
    signal: str           # "bullish", "bearish", "neutral", "error"
    source: str           # "yfinance"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "price": self.price,
            "prev_close": self.prev_close,
            "change_pct": self.change_pct,
            "threshold": self.threshold,
            "threshold_breached": self.threshold_breached,
            "signal": self.signal,
            "source": self.source,
            "error": self.error,
        }


class MacroSignalFetcher:
    """
    Fetches macro signals from yfinance for all configured tickers.

    Evaluates each ticker against its threshold (if any) and determines
    a signal state: bullish, bearish, or neutral.

    Usage:
        cfg = Config()
        fetcher = MacroSignalFetcher(cfg)
        signals = fetcher.fetch_all()
        for s in signals:
            print(f"{s.ticker}: {s.signal} @ {s.price}")
    """

    def __init__(self, config: Config):
        self.config = config
        # Build a map of ticker -> {name, threshold, direction}
        self.ticker_meta: Dict[str, Dict[str, Any]] = {}
        self._build_ticker_map()

    def _build_ticker_map(self) -> None:
        """
        Gather all tickers from config: strategy yfinance_tickers,
        macro_indicators, and theme macro_signals/equities.
        """
        # From strategy.json yfinance_tickers
        for t in self.config.yfinance_tickers:
            if t not in self.ticker_meta:
                self.ticker_meta[t] = {"name": t, "threshold": None, "direction": None}

        # From strategy.json macro_indicators (FRED-based, but some have
        # equivalent yfinance tickers mapped in themes)
        for ind in self.config.macro_indicators:
            # FRED indicators like DGS10 don't have direct yfinance tickers,
            # but we track the threshold for matching theme signals
            pass

        # From themes
        for theme in self.config.themes:
            for sig in theme.macro_signals:
                ticker = sig.get("ticker")
                if ticker:
                    if ticker not in self.ticker_meta:
                        self.ticker_meta[ticker] = {
                            "name": sig.get("signal", sig.get("name", ticker)),
                            "threshold": sig.get("threshold_alert"),
                            "direction": sig.get("direction"),
                        }
                    else:
                        # Merge threshold if we have one and the existing doesn't
                        if sig.get("threshold_alert") and not self.ticker_meta[ticker]["threshold"]:
                            self.ticker_meta[ticker]["threshold"] = sig["threshold_alert"]
                        if sig.get("direction") and not self.ticker_meta[ticker]["direction"]:
                            self.ticker_meta[ticker]["direction"] = sig["direction"]

            # Equities
            for category, items in theme.equities.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and "ticker" in item:
                            t = item["ticker"]
                            if t not in self.ticker_meta:
                                self.ticker_meta[t] = {
                                    "name": item.get("name", t),
                                    "threshold": None,
                                    "direction": None,
                                }

        _log(f"tracking {len(self.ticker_meta)} tickers")

    def _fetch_ticker(self, ticker: str) -> TickerSignal:
        """Fetch current price data for a single ticker via yfinance."""
        meta = self.ticker_meta.get(ticker, {"name": ticker, "threshold": None, "direction": None})

        if yf is None:
            return TickerSignal(
                ticker=ticker,
                name=meta["name"],
                price=None,
                prev_close=None,
                change_pct=None,
                threshold=meta["threshold"],
                threshold_breached=False,
                signal="error",
                source="yfinance",
                error="yfinance not installed",
            )

        try:
            info = yf.Ticker(ticker)
            # Use fast_info for speed; fall back to info if needed
            try:
                price = info.fast_info.get("lastPrice") or info.fast_info.get("last_price")
                prev_close = info.fast_info.get("previousClose") or info.fast_info.get("previous_close")
            except Exception:
                price = None
                prev_close = None

            # Fallback: try history
            if price is None:
                hist = info.history(period="2d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    if len(hist) > 1:
                        prev_close = float(hist["Close"].iloc[-2])

            if price is None:
                return TickerSignal(
                    ticker=ticker, name=meta["name"],
                    price=None, prev_close=None, change_pct=None,
                    threshold=meta["threshold"], threshold_breached=False,
                    signal="error", source="yfinance",
                    error="no price data returned",
                )

            # Calculate change
            change_pct = None
            if prev_close and prev_close > 0:
                change_pct = round((price - prev_close) / prev_close * 100, 2)

            # Evaluate threshold
            threshold = meta["threshold"]
            threshold_breached = False
            if threshold is not None:
                threshold_breached = price >= threshold

            # Determine signal
            signal = self._evaluate_signal(price, prev_close, change_pct, threshold, threshold_breached, meta)

            return TickerSignal(
                ticker=ticker,
                name=meta["name"],
                price=round(price, 4),
                prev_close=round(prev_close, 4) if prev_close else None,
                change_pct=change_pct,
                threshold=threshold,
                threshold_breached=threshold_breached,
                signal=signal,
                source="yfinance",
            )

        except Exception as e:
            return TickerSignal(
                ticker=ticker, name=meta["name"],
                price=None, prev_close=None, change_pct=None,
                threshold=meta["threshold"], threshold_breached=False,
                signal="error", source="yfinance",
                error=str(e),
            )

    def _evaluate_signal(
        self,
        price: float,
        prev_close: Optional[float],
        change_pct: Optional[float],
        threshold: Optional[float],
        threshold_breached: bool,
        meta: Dict[str, Any],
    ) -> str:
        """
        Determine signal state based on price action and thresholds.

        Logic:
        - If threshold is breached and direction contains "negative" or "rising"
          -> bearish (the thing being measured is in a stress zone)
        - If change > +1.5% -> bullish for the asset
        - If change < -1.5% -> bearish for the asset
        - Otherwise -> neutral
        """
        direction = meta.get("direction") or ""

        # Threshold-based signal (for yields, rates, VIX)
        if threshold_breached:
            if "negative" in direction.lower() or "rising" in direction.lower() or "stress" in direction.lower():
                return "bearish"
            else:
                return "bullish"

        # Percentage-change-based signal
        if change_pct is not None:
            if change_pct >= 1.5:
                return "bullish"
            elif change_pct <= -1.5:
                return "bearish"

        return "neutral"

    def fetch_all(self) -> List[TickerSignal]:
        """
        Fetch signals for all configured tickers.
        Returns a list of TickerSignal objects.
        """
        _log(f"fetching {len(self.ticker_meta)} tickers...")
        signals = []
        for ticker in sorted(self.ticker_meta.keys()):
            sig = self._fetch_ticker(ticker)
            signals.append(sig)
            status = f"{sig.signal:>8}"
            if sig.price is not None:
                status += f"  ${sig.price:.4f}"
                if sig.change_pct is not None:
                    status += f"  ({sig.change_pct:+.2f}%)"
                if sig.threshold_breached:
                    status += f"  [THRESHOLD BREACHED: {sig.threshold}]"
            else:
                status += f"  ERROR: {sig.error}"
            _log(f"  {ticker:<15} {status}")

        # Summary counts
        bullish = sum(1 for s in signals if s.signal == "bullish")
        bearish = sum(1 for s in signals if s.signal == "bearish")
        neutral = sum(1 for s in signals if s.signal == "neutral")
        errors = sum(1 for s in signals if s.signal == "error")
        _log(
            f"summary: {bullish} bullish, {bearish} bearish, "
            f"{neutral} neutral, {errors} errors"
        )
        return signals

    def fetch_subset(self, tickers: List[str]) -> List[TickerSignal]:
        """Fetch signals for a specific list of tickers."""
        signals = []
        for ticker in tickers:
            if ticker not in self.ticker_meta:
                self.ticker_meta[ticker] = {"name": ticker, "threshold": None, "direction": None}
            signals.append(self._fetch_ticker(ticker))
        return signals

    def get_theme_signals(self, theme_id: str) -> List[TickerSignal]:
        """Fetch signals for all tickers associated with a specific theme."""
        theme = self.config.theme_by_id(theme_id)
        if theme is None:
            _log(f"theme not found: {theme_id}")
            return []

        tickers = set()
        for sig in theme.macro_signals:
            if "ticker" in sig:
                tickers.add(sig["ticker"])
        for category, items in theme.equities.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "ticker" in item:
                        tickers.add(item["ticker"])

        return self.fetch_subset(sorted(tickers))

    def signals_to_json(self, signals: List[TickerSignal]) -> str:
        """Serialize a list of signals to JSON."""
        return json.dumps(
            [s.to_dict() for s in signals],
            indent=2,
        )


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    fetcher = MacroSignalFetcher(cfg)

    print(f"\nTracking {len(fetcher.ticker_meta)} tickers across all themes\n")

    if yf is not None:
        signals = fetcher.fetch_all()
        print(f"\nFetched {len(signals)} signals")
    else:
        print("yfinance not installed -- skipping live fetch")
        print("Ticker map:")
        for t, meta in sorted(fetcher.ticker_meta.items()):
            print(f"  {t:<15} name={meta['name']}, threshold={meta['threshold']}")
