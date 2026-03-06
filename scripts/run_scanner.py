#!/usr/bin/env python3
"""
CLI script: Run the cross-platform spread scanner and print opportunities.

Usage:
    python3 scripts/run_scanner.py [project_root]
    python3 scripts/run_scanner.py /path/to/trading-bot

If project_root is not provided, it defaults to the parent directory
of the scripts/ folder.
"""

import json
import os
import sys

# Ensure the project root is on sys.path so src.* imports work
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from src.core.config import Config
from src.execution.polymarket_client import PolymarketClient
from src.arbitrage.spread_scanner import (
    SpreadScanner,
    estimate_probability_lognormal,
    fetch_current_price,
    fetch_volatility,
)


def print_model_diagnostics() -> None:
    """Print some sanity-check probability estimates using the model."""
    print(f"\n{'='*70}")
    print(f"  MODEL DIAGNOSTICS (log-normal probability estimates)")
    print(f"{'='*70}")

    test_cases = [
        ("BTC-USD", 100_000, 30, True),
        ("BTC-USD", 120_000, 60, True),
        ("BTC-USD", 80_000, 30, False),
        ("ETH-USD", 5_000, 30, True),
        ("ETH-USD", 4_000, 30, False),
        ("SOL-USD", 200, 30, True),
    ]

    for ticker, target, days, is_above in test_cases:
        price = fetch_current_price(ticker)
        vol = fetch_volatility(ticker)

        if price is None:
            print(f"  {ticker}: price unavailable, skipping")
            continue

        effective_vol = vol if vol else 0.65
        prob = estimate_probability_lognormal(price, target, days, effective_vol, is_above)
        direction = ">" if is_above else "<"
        vol_str = f"{effective_vol:.0%}" if vol else "65% (default)"

        print(
            f"  {ticker} @ ${price:>10,.2f}  "
            f"P({direction} ${target:>10,.0f} in {days:>2}d) = {prob:>6.1%}  "
            f"vol={vol_str}"
        )

    print()


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else PROJECT_ROOT
    cfg = Config(root)

    print(f"Trading Bot Spread Scanner")
    print(f"Config: {cfg}")

    if not cfg.polymarket.enabled:
        print("Polymarket is DISABLED in config. Enable it in strategy.json to scan.")
        sys.exit(0)

    # --- Model diagnostics ---
    print_model_diagnostics()

    # --- Polymarket health check ---
    print(f"\n--- Polymarket API Health Check ---")
    client = PolymarketClient(cfg)
    health = client.health_check()
    print(f"  Status: {health['status']}")
    print(f"  Latency: {health['latency_ms']}ms")
    print(f"  API: {health['api_base']}")

    if health["status"] != "ok":
        print(f"  Error: {health.get('error', 'unknown')}")
        print("  Cannot proceed with scan. Fix API connectivity first.")
        sys.exit(1)

    # --- Find crypto markets ---
    print(f"\n--- Scanning Crypto Markets ---")
    crypto_markets = client.find_crypto_markets()
    print(f"  Found {len(crypto_markets)} crypto-related markets")

    if crypto_markets:
        print(f"\n  Sample markets:")
        for m in crypto_markets[:10]:
            print(f"    - {m.question[:70]}")
            print(f"      end: {m.end_date}, tokens: {len(m.tokens)}")

    # --- Run spread scanner ---
    print(f"\n--- Running Spread Scanner ---")
    print(f"  Minimum edge threshold: {cfg.risk.min_spread_after_fees_pct}%")

    scanner = SpreadScanner(cfg, polymarket_client=client)
    opportunities = scanner.scan()

    # --- Print results ---
    scanner.print_opportunities(opportunities)

    # Filter by confidence
    high_conf = [o for o in opportunities if o.confidence == "high"]
    if high_conf:
        print(f"\n  HIGH CONFIDENCE opportunities: {len(high_conf)}")
        for o in high_conf:
            print(
                f"    {o.direction}: {o.market_question[:50]}..."
                f" edge={o.edge_pct:+.1f}%"
                f" (mkt={o.polymarket_price:.2f}, model={o.model_probability:.2f})"
            )

    # --- Save to file ---
    if opportunities:
        output_dir = cfg.data_path("snapshots")
        os.makedirs(output_dir, exist_ok=True)
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_file = os.path.join(output_dir, f"scan-{ts}.json")
        with open(output_file, "w") as f:
            json.dump([o.to_dict() for o in opportunities], f, indent=2)
        print(f"\n  Results saved to: {output_file}")

    print(f"\n{'='*70}")
    print("Done.")


if __name__ == "__main__":
    main()
