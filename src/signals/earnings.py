"""
Earnings and corporate events signal module.

Uses yfinance to fetch upcoming earnings dates, historical earnings
surprise data, and pre-earnings price movement averages for tracked tickers.
Flags tickers with earnings within 7 days.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from src.core.config import Config

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] earnings: {msg}")


@dataclass
class EarningsSignal:
    ticker: str
    earnings_date: Optional[str]
    days_until: Optional[int]
    expected_eps: Optional[float]
    previous_eps: Optional[float]
    surprise_history_pct: Optional[float]  # avg historical earnings surprise %
    pre_earnings_move_avg: Optional[float]  # avg absolute price move in the 5 days before earnings
    upcoming: bool = False                  # True if earnings within 7 days
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "earnings_date": self.earnings_date,
            "days_until": self.days_until,
            "expected_eps": self.expected_eps,
            "previous_eps": self.previous_eps,
            "surprise_history_pct": self.surprise_history_pct,
            "pre_earnings_move_avg": self.pre_earnings_move_avg,
            "upcoming": self.upcoming,
            "error": self.error,
        }


class EarningsFetcher:
    """
    Fetches earnings calendar and surprise history for tracked tickers.

    Usage:
        cfg = Config()
        fetcher = EarningsFetcher(cfg)
        signals = fetcher.fetch_all()
        upcoming = fetcher.get_upcoming(signals, days=7)
    """

    def __init__(self, config: Config):
        self.config = config
        # Use tickers from config (yfinance_tickers + all theme tickers)
        self.tickers = list(set(config.yfinance_tickers + config.all_theme_tickers()))
        # Filter out forex and index tickers that don't have earnings
        self.tickers = [t for t in self.tickers if not t.endswith("=X") and not t.startswith("^")]
        _log(f"tracking {len(self.tickers)} tickers for earnings")

    def _fetch_ticker_earnings(self, ticker: str) -> EarningsSignal:
        if yf is None:
            return EarningsSignal(
                ticker=ticker, earnings_date=None, days_until=None,
                expected_eps=None, previous_eps=None,
                surprise_history_pct=None, pre_earnings_move_avg=None,
                error="yfinance not installed",
            )

        try:
            stock = yf.Ticker(ticker)
            now = datetime.now(timezone.utc)

            # Get next earnings date
            earnings_date_str = None
            days_until = None
            upcoming = False

            try:
                cal = stock.calendar
                if cal is not None:
                    # calendar can be a dict or DataFrame
                    if isinstance(cal, dict):
                        ed = cal.get("Earnings Date")
                        if isinstance(ed, list) and ed:
                            next_date = ed[0]
                        else:
                            next_date = ed
                    elif pd is not None and hasattr(cal, 'loc'):
                        try:
                            next_date = cal.loc["Earnings Date"].iloc[0] if "Earnings Date" in cal.index else None
                        except Exception:
                            next_date = None
                    else:
                        next_date = None

                    if next_date is not None:
                        if hasattr(next_date, 'strftime'):
                            earnings_date_str = next_date.strftime("%Y-%m-%d")
                            if hasattr(next_date, 'tzinfo') and next_date.tzinfo is None:
                                next_date = next_date.replace(tzinfo=timezone.utc)
                            delta = next_date - now
                            days_until = delta.days
                            upcoming = 0 <= days_until <= 7
                        else:
                            earnings_date_str = str(next_date)
            except Exception:
                pass

            # Get earnings history for surprise calculation
            expected_eps = None
            previous_eps = None
            surprise_history_pct = None

            try:
                earnings_hist = stock.earnings_history
                if earnings_hist is not None and hasattr(earnings_hist, 'empty') and not earnings_hist.empty:
                    # Calculate average surprise %
                    if "surprisePercent" in earnings_hist.columns:
                        surprises = earnings_hist["surprisePercent"].dropna()
                        if not surprises.empty:
                            surprise_history_pct = round(float(surprises.mean()) * 100, 2)

                    # Get most recent EPS values
                    if "epsEstimate" in earnings_hist.columns:
                        estimates = earnings_hist["epsEstimate"].dropna()
                        if not estimates.empty:
                            expected_eps = round(float(estimates.iloc[-1]), 4)

                    if "epsActual" in earnings_hist.columns:
                        actuals = earnings_hist["epsActual"].dropna()
                        if not actuals.empty:
                            previous_eps = round(float(actuals.iloc[-1]), 4)
            except Exception:
                pass

            # Calculate average pre-earnings price move (5 days before past earnings)
            pre_earnings_move_avg = self._calc_pre_earnings_move(stock)

            return EarningsSignal(
                ticker=ticker,
                earnings_date=earnings_date_str,
                days_until=days_until,
                expected_eps=expected_eps,
                previous_eps=previous_eps,
                surprise_history_pct=surprise_history_pct,
                pre_earnings_move_avg=pre_earnings_move_avg,
                upcoming=upcoming,
            )

        except Exception as e:
            return EarningsSignal(
                ticker=ticker, earnings_date=None, days_until=None,
                expected_eps=None, previous_eps=None,
                surprise_history_pct=None, pre_earnings_move_avg=None,
                error=str(e),
            )

    def _calc_pre_earnings_move(self, stock: Any) -> Optional[float]:
        """Calculate average absolute price move in the 5 trading days before past earnings."""
        try:
            earnings_dates = stock.earnings_dates
            if earnings_dates is None or (hasattr(earnings_dates, 'empty') and earnings_dates.empty):
                return None

            hist = stock.history(period="2y")
            if hist is None or hist.empty:
                return None

            moves = []
            dates = earnings_dates.index.tolist()

            for ed in dates[:8]:  # Last 8 earnings for sample
                if hasattr(ed, 'tz_localize'):
                    try:
                        ed_naive = ed.tz_localize(None)
                    except Exception:
                        ed_naive = ed.tz_convert(None) if hasattr(ed, 'tz_convert') else ed
                else:
                    ed_naive = ed

                # Find price 5 trading days before earnings
                pre_mask = hist.index <= ed_naive
                pre_prices = hist.loc[pre_mask, "Close"]
                if len(pre_prices) >= 6:
                    price_at_minus_5 = float(pre_prices.iloc[-6])
                    price_at_minus_1 = float(pre_prices.iloc[-1])
                    if price_at_minus_5 > 0:
                        move = abs((price_at_minus_1 - price_at_minus_5) / price_at_minus_5 * 100)
                        moves.append(move)

            if moves:
                return round(sum(moves) / len(moves), 2)
        except Exception:
            pass
        return None

    def fetch_all(self) -> List[EarningsSignal]:
        if yf is None:
            _log("yfinance not installed, returning empty")
            return []

        _log(f"fetching earnings for {len(self.tickers)} tickers...")
        signals = []

        for ticker in sorted(self.tickers):
            sig = self._fetch_ticker_earnings(ticker)
            signals.append(sig)

            if sig.error:
                _log(f"  {ticker:<10} ERROR: {sig.error}")
            elif sig.earnings_date:
                flag = " ** UPCOMING **" if sig.upcoming else ""
                _log(f"  {ticker:<10} next={sig.earnings_date}  days={sig.days_until}  surprise_avg={sig.surprise_history_pct}%{flag}")
            else:
                _log(f"  {ticker:<10} no earnings date found")

        upcoming_count = sum(1 for s in signals if s.upcoming)
        _log(f"summary: {len(signals)} tickers checked, {upcoming_count} with earnings within 7 days")
        return signals

    @staticmethod
    def get_upcoming(signals: List[EarningsSignal], days: int = 7) -> List[EarningsSignal]:
        """Filter to tickers with earnings within N days."""
        return [s for s in signals if s.days_until is not None and 0 <= s.days_until <= days]

    def signals_to_json(self, signals: List[EarningsSignal]) -> str:
        return json.dumps([s.to_dict() for s in signals], indent=2)


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    fetcher = EarningsFetcher(cfg)

    if yf is not None:
        signals = fetcher.fetch_all()
        upcoming = fetcher.get_upcoming(signals)
        if upcoming:
            print(f"\n{len(upcoming)} tickers with upcoming earnings:")
            for s in upcoming:
                print(f"  {s.ticker}: {s.earnings_date} ({s.days_until} days)")
        else:
            print("\nNo upcoming earnings in the next 7 days.")
    else:
        print("yfinance not installed -- skipping")
