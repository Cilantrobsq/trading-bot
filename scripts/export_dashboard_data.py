#!/usr/bin/env python3
"""Export trading bot data to a static JSON file for the dashboard.

Reads from the trading-bot data/ and config/ directories and produces
a single dashboard.json that the React frontend can fetch.

Usage:
    python3 scripts/export_dashboard_data.py [--output web/dist/data/dashboard.json]
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
PAPER_DIR = DATA_DIR / "paper-trades"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
TRADES_DIR = DATA_DIR / "trades"

DEFAULT_OUTPUT = BASE_DIR / "web" / "dist" / "data" / "dashboard.json"


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def sanitize(obj):
    SECRET_KEYS = {"api_key", "secret_key", "password", "token", "pat", "credentials"}
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()
                if k.lower() not in SECRET_KEYS and not k.lower().endswith("_path")}
    if isinstance(obj, list):
        return [sanitize(item) for item in obj]
    return obj


def latest_file(directory, pattern="*.json"):
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def get_portfolio():
    portfolio = read_json(PAPER_DIR / "portfolio.json")
    if portfolio is None:
        latest = latest_file(PAPER_DIR)
        portfolio = read_json(latest) if latest else None
    if portfolio is None:
        strategy = read_json(CONFIG_DIR / "strategy.json") or {}
        paper_cfg = strategy.get("paper_trading", {})
        initial = paper_cfg.get("initial_balance_usd", 10000)
        return {
            "balance": initial,
            "initial_balance": initial,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "positions": [],
            "mode": "paper" if paper_cfg.get("enabled", True) else "live",
            "last_updated": None,
        }
    return portfolio


def get_signals():
    signals = read_json(SNAPSHOTS_DIR / "latest-signals.json")
    if signals is None:
        themes = read_json(CONFIG_DIR / "themes.json")
        if themes:
            skeleton = []
            for theme in themes.get("themes", []):
                for sig in theme.get("macro_signals", []):
                    skeleton.append({
                        "name": sig.get("signal", sig.get("name", "?")),
                        "ticker": sig.get("ticker", "N/A"),
                        "value": None,
                        "threshold": sig.get("threshold_alert"),
                        "direction": sig.get("direction", sig.get("note", "")),
                        "status": "awaiting_data",
                        "theme": theme.get("name", ""),
                    })
            return {"signals": skeleton, "last_updated": None}
        return {"signals": [], "last_updated": None}
    return signals


def get_opportunities():
    opps = read_json(SNAPSHOTS_DIR / "latest-opportunities.json")
    if opps is None:
        return {"opportunities": [], "last_updated": None}
    return opps


def get_trades():
    trades = []
    for d in [PAPER_DIR, TRADES_DIR]:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json"), key=os.path.getmtime, reverse=True):
            if f.name == "portfolio.json":
                continue
            data = read_json(f)
            if data is None:
                continue
            if isinstance(data, list):
                trades.extend(data)
            elif isinstance(data, dict):
                if "trades" in data:
                    trades.extend(data["trades"])
                else:
                    trades.append(data)
    trades.sort(key=lambda t: t.get("timestamp", t.get("time", "")), reverse=True)
    trades = trades[:100]
    return {"trades": trades, "count": len(trades)}


def get_config():
    strategy = read_json(CONFIG_DIR / "strategy.json") or {}
    themes = read_json(CONFIG_DIR / "themes.json") or {}
    return {"strategy": sanitize(strategy), "themes": sanitize(themes)}


def get_brain():
    return read_json(DATA_DIR / "brain-state.json") or {
        "market_regime": "unknown",
        "regime_confidence": 0,
        "overall_sentiment": 0.0,
        "active_themes": [],
        "planned_actions": [],
        "risk_state": {
            "daily_pnl": 0, "daily_pnl_pct": 0, "max_daily_loss_pct": 5,
            "circuit_breaker_active": False, "exposure_pct": 0, "correlation_warning": False
        },
        "last_updated": None
    }


def get_decisions():
    decisions_dir = DATA_DIR / "decisions"
    if not decisions_dir.exists():
        return []
    entries = []
    for f in sorted(decisions_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True)[:3]:
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except (json.JSONDecodeError, PermissionError):
            continue
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries[:100]


def get_theses():
    data = read_json(DATA_DIR / "theses" / "theses.json")
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return data.get("theses", [])


def get_overrides():
    data = read_json(DATA_DIR / "overrides.json")
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return data.get("overrides", [])


def get_kill_switch():
    return read_json(DATA_DIR / "kill-switch.json") or {
        "active": False, "reason": None, "activated_at": None
    }


def get_regime():
    return read_json(SNAPSHOTS_DIR / "latest-regime.json") or {
        "regime": "unknown", "risk_multiplier": 1.0, "details": {}, "last_updated": None
    }


def get_circuit_breaker():
    return read_json(DATA_DIR / "circuit-breaker.json") or {
        "active": False, "daily_pnl": 0, "hourly_pnl": 0,
        "trades_this_hour": 0, "last_trigger": None, "reason": None
    }


def get_correlations():
    return read_json(SNAPSHOTS_DIR / "latest-correlations.json") or {
        "diversification_score": 100, "high_correlations": [],
        "warnings": [], "suggested_hedges": []
    }


def get_fred():
    return read_json(SNAPSHOTS_DIR / "latest-fred.json") or {
        "signals": [], "fetched_at": None
    }


def get_news():
    data = read_json(SNAPSHOTS_DIR / "latest-news.json")
    if data is None:
        return []
    if isinstance(data, list):
        # Return top 50 most relevant
        data.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return data[:50]
    return data.get("items", [])[:50]


def get_snapshot():
    return read_json(SNAPSHOTS_DIR / "latest-snapshot.json") or {
        "timestamp": None, "regime": "unknown", "portfolio": {}
    }


def get_niche_markets():
    data = read_json(SNAPSHOTS_DIR / "latest-niche-markets.json")
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return data.get("markets", [])


def main():
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dashboard = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": get_portfolio(),
        "signals": get_signals(),
        "opportunities": get_opportunities(),
        "trades": get_trades(),
        "config": get_config(),
        "brain": get_brain(),
        "decisions": get_decisions(),
        "theses": get_theses(),
        "overrides": get_overrides(),
        "kill_switch": get_kill_switch(),
        "regime": get_regime(),
        "circuit_breaker": get_circuit_breaker(),
        "correlations": get_correlations(),
        "niche_markets": get_niche_markets(),
        "fred": get_fred(),
        "news": get_news(),
        "snapshot": get_snapshot(),
    }

    with open(output_path, "w") as f:
        json.dump(dashboard, f, indent=2, default=str)

    print(f"Exported dashboard data to {output_path} ({output_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
