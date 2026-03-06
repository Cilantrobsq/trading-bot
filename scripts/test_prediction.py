#!/usr/bin/env python3
"""Quick test of prediction market scanner."""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.signals.kalshi_client import KalshiClient

print("=== Testing Kalshi Client ===")
client = KalshiClient()
result = client.full_scan()
print(json.dumps(result["summary"], indent=2))

for asset, events in result.get("markets", {}).items():
    for ev in events[:1]:
        title = ev.get("title", "?")
        exp = ev.get("expected_price", 0)
        vol = ev.get("total_volume", 0)
        print(f"\n{asset}: {title[:60]}")
        print(f"  expected=${exp:,.0f} vol={vol}")
        buckets = ev.get("buckets", [])
        top = sorted(buckets, key=lambda b: b.get("midpoint_prob", 0), reverse=True)[:5]
        for b in top:
            label = b.get("label", "?")
            prob = b.get("midpoint_prob", 0)
            bvol = b.get("volume", 0)
            print(f"  {label:<30} prob={prob:.1%} vol={bvol}")

print("\n=== Testing Polymarket Gamma Client ===")
from src.signals.polymarket_gamma import PolymarketGammaClient

poly = PolymarketGammaClient()
poly_result = poly.full_scan()
print(f"Total markets: {poly_result['total_markets']}")
print(f"Finance-relevant: {poly_result['finance_markets']}")
print(f"Categories: {poly_result['categories']}")

for cat, markets in poly_result.get("markets", {}).items():
    print(f"\n  {cat} ({len(markets)}):")
    for m in markets[:3]:
        q = m.get("question", "?")[:60]
        prices = m.get("outcome_prices", [])
        vol = m.get("volume", 0)
        print(f"    {q}")
        print(f"      prices={prices} vol={vol:.0f}")

print("\n=== Testing Full Scanner ===")
from src.signals.prediction_scanner import PredictionMarketScanner

scanner = PredictionMarketScanner()
full = scanner.full_scan()
print(json.dumps(full["summary"], indent=2))

if full.get("edge_signals"):
    print(f"\nEdge signals ({len(full['edge_signals'])}):")
    for s in full["edge_signals"][:5]:
        print(f"  [{s['platform']}] {s['question'][:50]}")
        model = s.get("model_probability", 0)
        print(f"    market={s['yes_price']:.2%} model={model:.2%} edge={s['edge_pct']:+.1f}%")
