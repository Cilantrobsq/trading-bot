#!/usr/bin/env python3
"""Export trading bot state to static JSON for GitHub Pages dashboard.

Reads from data/ and config/ directories, produces web/public/data/dashboard.json.
Called by cron every 15 minutes, pushes to GitHub so the static site stays current.
"""

import json
import os
import glob
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
PAPER_DIR = DATA_DIR / "paper-trades"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
TRADES_DIR = DATA_DIR / "trades"
OUTPUT_DIR = BASE_DIR / "web" / "public" / "data"

SECRET_KEYS = {"api_key", "secret_key", "password", "token", "pat", "credentials"}


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def sanitize(obj):
    if isinstance(obj, dict):
        return {
            k: sanitize(v)
            for k, v in obj.items()
            if k.lower() not in SECRET_KEYS and not k.lower().endswith("_path")
        }
    if isinstance(obj, list):
        return [sanitize(item) for item in obj]
    return obj


def latest_file(directory, pattern="*.json"):
    files = sorted(
        glob.glob(str(directory / pattern)),
        key=os.path.getmtime,
        reverse=True,
    )
    return Path(files[0]) if files else None


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


def get_global_markets():
    data = read_json(SNAPSHOTS_DIR / "latest-global-markets.json")
    if data is None:
        return None
    return data


def get_global_macro():
    data = read_json(SNAPSHOTS_DIR / "latest-global-macro.json")
    if data is None:
        return None
    return sanitize(data)


def get_tz_arb():
    data = read_json(SNAPSHOTS_DIR / "latest-tz-arb.json")
    if data is None:
        return None
    return data


def get_cross_correlations():
    data = read_json(SNAPSHOTS_DIR / "latest-correlations.json")
    if data is None:
        return None
    return data


def get_brain():
    data = read_json(DATA_DIR / "brain-state.json")
    if data is None:
        return None
    return sanitize(data)


def get_fred():
    data = read_json(SNAPSHOTS_DIR / "latest-fred.json")
    if data is None:
        return None
    return sanitize(data)


def get_news():
    data = read_json(SNAPSHOTS_DIR / "latest-news.json")
    if data is None:
        return None
    return data


def get_decisions():
    from datetime import date
    decisions_dir = DATA_DIR / "decisions"
    today = date.today().isoformat()
    decisions_file = decisions_dir / f"decisions-{today}.jsonl"
    if not decisions_file.exists():
        candidates = sorted(decisions_dir.glob("decisions-*.jsonl"), reverse=True) if decisions_dir.exists() else []
        if candidates:
            decisions_file = candidates[0]
        else:
            return None
    decisions = []
    try:
        with open(decisions_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        decisions.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        return None
    return decisions[-50:] if decisions else None


def get_proposals():
    proposals_file = DATA_DIR / "proposals" / "active.json"
    data = read_json(proposals_file)
    if data is None or not isinstance(data, list):
        return None
    # Add seconds_remaining for each proposal
    from datetime import datetime, timezone as tz
    now = datetime.now(tz.utc)
    for p in data:
        expires = p.get("expires_at", "")
        if expires:
            try:
                exp_dt = datetime.fromisoformat(expires)
                remaining = max(0, int((exp_dt - now).total_seconds()))
                p["seconds_remaining"] = remaining
            except (ValueError, TypeError):
                p["seconds_remaining"] = 0
        else:
            p["seconds_remaining"] = -1
    # Filter to active only
    return [p for p in data if p.get("status") == "active" and p.get("seconds_remaining", 0) > 0]


def get_crypto():
    data = read_json(SNAPSHOTS_DIR / "latest-crypto.json")
    if data is None:
        return None
    return data


def get_influencers():
    data = read_json(SNAPSHOTS_DIR / "latest-influencers.json")
    if data is None:
        return None
    return data


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    global_markets = get_global_markets()
    global_macro = get_global_macro()
    tz_arb = get_tz_arb()
    cross_corr = get_cross_correlations()
    brain = get_brain()
    fred = get_fred()
    news = get_news()
    decisions = get_decisions()
    crypto = get_crypto()
    influencers = get_influencers()

    dashboard = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": get_portfolio(),
        "signals": get_signals(),
        "opportunities": get_opportunities(),
        "trades": get_trades(),
        "config": get_config(),
    }

    # Add brain state
    if brain:
        dashboard["brain"] = brain

    # Add FRED macro data
    if fred:
        dashboard["fred"] = fred

    # Add news
    if news:
        dashboard["news"] = news

    # Add decisions log
    if decisions:
        dashboard["decisions"] = decisions

    # Add global data if available
    if global_markets:
        dashboard["global_markets"] = global_markets
    if global_macro:
        dashboard["global_macro"] = global_macro
    if tz_arb:
        dashboard["timezone_arb"] = tz_arb
    if cross_corr:
        dashboard["cross_correlations"] = cross_corr

    # Trade proposals
    proposals = get_proposals()
    if proposals:
        dashboard["proposals"] = proposals

    # Crypto market data
    if crypto:
        dashboard["crypto"] = crypto

    # Influencer data
    if influencers:
        dashboard["influencers"] = influencers

    output_path = OUTPUT_DIR / "dashboard.json"
    with open(output_path, "w") as f:
        json.dump(dashboard, f, indent=2)

    gm_count = len(global_markets.get("indices", {}).get("asia", []) +
                    global_markets.get("indices", {}).get("europe", []) +
                    global_markets.get("indices", {}).get("americas", [])) if global_markets else 0

    print(f"Exported dashboard to {output_path}")
    print(f"  Portfolio balance: ${dashboard['portfolio']['balance']:,.2f}")
    print(f"  Signals: {len(dashboard['signals']['signals'])}")
    print(f"  Global markets: {gm_count}")
    print(f"  Opportunities: {len(dashboard['opportunities']['opportunities'])}")
    print(f"  Trades: {dashboard['trades']['count']}")

    if "--push" in sys.argv:
        os.chdir(BASE_DIR)
        subprocess.run(["git", "add", "web/public/data/dashboard.json"], check=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if result.returncode != 0:
            subprocess.run([
                "git", "commit", "-m",
                f"data: update dashboard snapshot {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            ], check=True)
            subprocess.run(["git", "push"], check=True)
            print("Pushed to GitHub.")
        else:
            print("No changes to push.")


if __name__ == "__main__":
    main()
