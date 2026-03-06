#!/usr/bin/env python3
"""Trading Bot Dashboard - Flask API + UI server."""

import json
import os
import glob
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Paths relative to this file's parent (trading-bot/)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
PAPER_DIR = DATA_DIR / "paper-trades"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
TRADES_DIR = DATA_DIR / "trades"

# Keys to strip from config before serving
SECRET_KEYS = {"api_key", "secret_key", "password", "token", "pat", "credentials"}


def _read_json(path):
    """Read a JSON file, return None if missing or malformed."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def _sanitize(obj):
    """Recursively remove keys that look like secrets."""
    if isinstance(obj, dict):
        return {
            k: _sanitize(v)
            for k, v in obj.items()
            if k.lower() not in SECRET_KEYS and not k.lower().endswith("_path")
        }
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    return obj


def _latest_file(directory, pattern="*.json"):
    """Return the most recently modified file matching pattern in directory."""
    files = sorted(
        glob.glob(str(directory / pattern)),
        key=os.path.getmtime,
        reverse=True,
    )
    return Path(files[0]) if files else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/portfolio")
def api_portfolio():
    """Portfolio state: balance, positions, P&L."""
    # Try portfolio.json first, then latest file in paper-trades/
    portfolio = _read_json(PAPER_DIR / "portfolio.json")
    if portfolio is None:
        latest = _latest_file(PAPER_DIR)
        portfolio = _read_json(latest) if latest else None

    if portfolio is None:
        # Return sensible defaults from strategy config
        strategy = _read_json(CONFIG_DIR / "strategy.json") or {}
        paper_cfg = strategy.get("paper_trading", {})
        initial = paper_cfg.get("initial_balance_usd", 10000)
        return jsonify({
            "balance": initial,
            "initial_balance": initial,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "positions": [],
            "mode": "paper" if paper_cfg.get("enabled", True) else "live",
            "last_updated": None,
            "_note": "No portfolio data yet. Waiting for first trade cycle.",
        })

    return jsonify(portfolio)


@app.route("/api/signals")
def api_signals():
    """Current macro signals snapshot."""
    signals = _read_json(SNAPSHOTS_DIR / "latest-signals.json")
    if signals is None:
        # Build skeleton from themes config so the UI has something
        themes = _read_json(CONFIG_DIR / "themes.json")
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
            return jsonify({"signals": skeleton, "last_updated": None,
                            "_note": "No live signal data yet. Showing configured indicators."})
        return jsonify({"signals": [], "last_updated": None,
                        "_note": "No signal data available."})

    return jsonify(signals)


@app.route("/api/opportunities")
def api_opportunities():
    """Current arbitrage / trade opportunities."""
    opps = _read_json(SNAPSHOTS_DIR / "latest-opportunities.json")
    if opps is None:
        return jsonify({
            "opportunities": [],
            "last_updated": None,
            "_note": "No opportunity data yet. Waiting for scanner cycle.",
        })
    return jsonify(opps)


@app.route("/api/trades")
def api_trades():
    """Trade history from paper-trades/ and trades/ directories."""
    trades = []

    # Collect from both directories
    for d in [PAPER_DIR, TRADES_DIR]:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json"), key=os.path.getmtime, reverse=True):
            if f.name == "portfolio.json":
                continue
            data = _read_json(f)
            if data is None:
                continue
            # Handle both single trade and list-of-trades formats
            if isinstance(data, list):
                trades.extend(data)
            elif isinstance(data, dict):
                if "trades" in data:
                    trades.extend(data["trades"])
                else:
                    trades.append(data)

    # Sort by timestamp descending, limit to 100
    trades.sort(key=lambda t: t.get("timestamp", t.get("time", "")), reverse=True)
    trades = trades[:100]

    return jsonify({
        "trades": trades,
        "count": len(trades),
        "_note": "No trades recorded yet." if not trades else None,
    })


@app.route("/api/config")
def api_config():
    """Strategy and theme config (sanitized)."""
    strategy = _read_json(CONFIG_DIR / "strategy.json") or {}
    themes = _read_json(CONFIG_DIR / "themes.json") or {}
    return jsonify({
        "strategy": _sanitize(strategy),
        "themes": _sanitize(themes),
    })


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(tz=__import__('datetime').timezone.utc).isoformat(),
        "data_dir_exists": DATA_DIR.exists(),
        "paper_trades_count": len(list(PAPER_DIR.glob("*.json"))) if PAPER_DIR.exists() else 0,
        "snapshots_count": len(list(SNAPSHOTS_DIR.glob("*.json"))) if SNAPSHOTS_DIR.exists() else 0,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555, debug=True)
