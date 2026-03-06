#!/usr/bin/env python3
"""
CLI script: Fetch all macro signals and news, print a summary table.

Usage:
    python3 scripts/run_signals.py [project_root]
    python3 scripts/run_signals.py /path/to/trading-bot

If project_root is not provided, it defaults to the parent directory
of the scripts/ folder.
"""

import os
import sys

# Ensure the project root is on sys.path so src.* imports work
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from src.core.config import Config
from src.signals.macro import MacroSignalFetcher, TickerSignal
from src.signals.news import NewsFeedMonitor


def print_signal_table(signals: list) -> None:
    """Print a formatted table of macro signals."""
    print(f"\n{'='*80}")
    print(f"  MACRO SIGNALS SUMMARY")
    print(f"{'='*80}")
    print(f"  {'Ticker':<15} {'Name':<25} {'Price':>10} {'Chg%':>8} {'Signal':>10} {'Threshold':>10}")
    print(f"  {'-'*15} {'-'*25} {'-'*10} {'-'*8} {'-'*10} {'-'*10}")

    for s in signals:
        price_str = f"${s.price:.4f}" if s.price is not None else "N/A"
        chg_str = f"{s.change_pct:+.2f}%" if s.change_pct is not None else "N/A"
        thr_str = str(s.threshold) if s.threshold is not None else "-"
        breach = " *" if s.threshold_breached else ""

        print(
            f"  {s.ticker:<15} {s.name:<25} {price_str:>10} {chg_str:>8} "
            f"{s.signal:>10} {thr_str:>10}{breach}"
        )

    # Counts
    bullish = sum(1 for s in signals if s.signal == "bullish")
    bearish = sum(1 for s in signals if s.signal == "bearish")
    neutral = sum(1 for s in signals if s.signal == "neutral")
    errors = sum(1 for s in signals if s.signal == "error")

    print(f"\n  Totals: {bullish} bullish | {bearish} bearish | {neutral} neutral | {errors} errors")
    print(f"  * = threshold breached")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else PROJECT_ROOT
    cfg = Config(root)

    print(f"Trading Bot Signal Scanner")
    print(f"Config: {cfg}")
    print(f"Active themes: {[t.name for t in cfg.active_themes()]}")

    # --- Macro Signals ---
    print(f"\n--- Fetching Macro Signals ---")
    fetcher = MacroSignalFetcher(cfg)
    signals = fetcher.fetch_all()
    print_signal_table(signals)

    # --- News Feed ---
    print(f"\n--- Fetching News Feeds ---")
    monitor = NewsFeedMonitor(cfg)
    articles = monitor.fetch_all()
    monitor.print_summary(articles)

    # --- Theme-level summary ---
    print(f"\n{'='*80}")
    print(f"  THEME SIGNAL SUMMARY")
    print(f"{'='*80}")

    for theme in cfg.active_themes():
        theme_signals = [s for s in signals if s.ticker in _theme_tickers(theme)]
        bullish = sum(1 for s in theme_signals if s.signal == "bullish")
        bearish = sum(1 for s in theme_signals if s.signal == "bearish")
        breaches = sum(1 for s in theme_signals if s.threshold_breached)

        theme_articles = [
            a for a in articles
            if theme.id in a.matched_themes
        ]

        print(f"\n  Theme: {theme.name}")
        print(f"    Signals: {bullish} bullish, {bearish} bearish, {breaches} threshold breaches")
        print(f"    News: {len(theme_articles)} relevant articles")
        if theme_articles:
            for a in theme_articles[:3]:
                sent = {"positive": "+", "negative": "-", "neutral": " "}[a.sentiment_hint]
                print(f"      [{sent}] {a.title[:70]}")

    print(f"\n{'='*80}")
    print("Done.")


def _theme_tickers(theme) -> set:
    """Extract all tickers from a theme."""
    tickers = set()
    for sig in theme.macro_signals:
        if "ticker" in sig:
            tickers.add(sig["ticker"])
    for category, items in theme.equities.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "ticker" in item:
                    tickers.add(item["ticker"])
    return tickers


if __name__ == "__main__":
    main()
