#!/usr/bin/env python3
"""Trading Bot Dashboard - FastAPI backend.

Serves the React frontend (from web/dist/) and provides API endpoints
for live data. Replaces the old Flask app.py.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.bot_brain import BotBrain
from src.core.decision_log import DecisionLog
from src.core.kill_switch import KillSwitch
from src.reasoning.thesis import ThesisManager
from src.reasoning.overrides import OverrideManager

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
PAPER_DIR = DATA_DIR / "paper-trades"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
TRADES_DIR = DATA_DIR / "trades"
FRONTEND_DIR = BASE_DIR / "web" / "dist"

SECRET_KEYS = {"api_key", "secret_key", "password", "token", "pat", "credentials"}

app = FastAPI(title="Trading Bot Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Initialize reasoning and transparency modules
bot_brain = BotBrain()
decision_log = DecisionLog()
kill_switch = KillSwitch()
thesis_manager = ThesisManager()
override_manager = OverrideManager()


# ---- Pydantic models for request validation ----

class ThesisCreate(BaseModel):
    title: str
    direction: str  # bullish, bearish, neutral
    confidence: int = Field(50, ge=0, le=100)
    reasoning: str = ""
    catalysts: List[str] = []
    invalidation_conditions: List[str] = []
    time_horizon: int = 30
    affected_tickers: List[str] = []
    affected_themes: List[str] = []


class ThesisUpdate(BaseModel):
    title: Optional[str] = None
    direction: Optional[str] = None
    confidence: Optional[int] = None
    reasoning: Optional[str] = None
    catalysts: Optional[List[str]] = None
    invalidation_conditions: Optional[List[str]] = None
    time_horizon: Optional[int] = None
    affected_tickers: Optional[List[str]] = None
    affected_themes: Optional[List[str]] = None
    status: Optional[str] = None


class OverrideCreate(BaseModel):
    signal_type: str
    ticker_or_market: str
    override_type: str  # boost, suppress, invert
    strength: float = Field(1.0, ge=0.0, le=2.0)
    reason: str = ""
    expires_at: Optional[str] = None


class KillSwitchToggle(BaseModel):
    active: bool
    reason: str = ""


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def sanitize(obj):
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


@app.get("/api/portfolio")
def api_portfolio():
    portfolio = read_json(PAPER_DIR / "portfolio.json")
    if portfolio is None:
        latest = latest_file(PAPER_DIR)
        portfolio = read_json(latest) if latest else None
    if portfolio is None:
        strategy = read_json(CONFIG_DIR / "strategy.json") or {}
        paper_cfg = strategy.get("paper_trading", {})
        initial = paper_cfg.get("initial_balance_usd", 10000)
        return {
            "balance": initial, "initial_balance": initial,
            "total_pnl": 0, "total_pnl_pct": 0, "positions": [],
            "mode": "paper" if paper_cfg.get("enabled", True) else "live",
            "last_updated": None,
        }
    return portfolio


@app.get("/api/signals")
def api_signals():
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


@app.get("/api/opportunities")
def api_opportunities():
    opps = read_json(SNAPSHOTS_DIR / "latest-opportunities.json")
    if opps is None:
        return {"opportunities": [], "last_updated": None}
    return opps


@app.get("/api/trades")
def api_trades():
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
    return {"trades": trades[:100], "count": min(len(trades), 100)}


@app.get("/api/config")
def api_config():
    strategy = read_json(CONFIG_DIR / "strategy.json") or {}
    themes = read_json(CONFIG_DIR / "themes.json") or {}
    return {"strategy": sanitize(strategy), "themes": sanitize(themes)}


@app.get("/api/dashboard")
def api_dashboard():
    """All data in one call (for static export compatibility)."""
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "portfolio": api_portfolio(),
        "signals": api_signals(),
        "opportunities": api_opportunities(),
        "trades": api_trades(),
        "config": api_config(),
        "brain": api_brain(),
        "decisions": api_decisions(limit=50),
        "theses": api_theses_list(),
        "overrides": api_overrides_list(),
        "kill_switch": api_kill_switch_status(),
    }


@app.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_dir_exists": DATA_DIR.exists(),
        "paper_trades_count": len(list(PAPER_DIR.glob("*.json"))) if PAPER_DIR.exists() else 0,
        "snapshots_count": len(list(SNAPSHOTS_DIR.glob("*.json"))) if SNAPSHOTS_DIR.exists() else 0,
    }


# ====================================================================
# Bot Brain / Reasoning / Transparency endpoints
# ====================================================================


@app.get("/api/brain")
def api_brain():
    """Returns current BotBrain state (regime, sentiment, planned actions, risk)."""
    try:
        bot_brain.assess_regime()
        return bot_brain.get_state_dict()
    except Exception as e:
        logger.error("Failed to get brain state: %s", e)
        return bot_brain.get_state_dict()


@app.get("/api/decisions")
def api_decisions(
    limit: int = Query(50, ge=1, le=500),
    type: Optional[str] = Query(None, alias="type"),
    since: Optional[str] = Query(None),
):
    """Returns recent decision log entries."""
    try:
        if since:
            entries = decision_log.get_by_timerange(since)
        elif type:
            entries = decision_log.get_by_type(type, limit=limit)
        else:
            entries = decision_log.get_recent(limit)
        return {
            "decisions": [e.to_dict() for e in entries],
            "count": len(entries),
            "summary": decision_log.daily_summary(),
        }
    except Exception as e:
        logger.error("Failed to get decisions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/theses")
def api_theses_list():
    """Returns all theses."""
    thesis_manager.check_expirations()
    return {
        "theses": [t.to_dict() for t in thesis_manager.get_all()],
        "active_count": len(thesis_manager.get_active()),
    }


@app.post("/api/theses")
def api_theses_create(body: ThesisCreate):
    """Create a new thesis."""
    try:
        thesis = thesis_manager.create_thesis(
            title=body.title,
            direction=body.direction,
            confidence=body.confidence,
            reasoning=body.reasoning,
            catalysts=body.catalysts,
            invalidation_conditions=body.invalidation_conditions,
            time_horizon=body.time_horizon,
            affected_tickers=body.affected_tickers,
            affected_themes=body.affected_themes,
        )
        decision_log.log_decision(
            decision_type="thesis_update",
            input_data=body.model_dump(),
            output_data={"thesis_id": thesis.id},
            reasoning=f"Created thesis: {body.title}",
            confidence=body.confidence,
            action_taken="thesis_created",
        )
        return thesis.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/theses/{thesis_id}")
def api_theses_update(thesis_id: str, body: ThesisUpdate):
    """Update an existing thesis."""
    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        thesis = thesis_manager.update_thesis(thesis_id, updates)
        decision_log.log_decision(
            decision_type="thesis_update",
            input_data={"thesis_id": thesis_id, "updates": updates},
            output_data=thesis.to_dict(),
            reasoning=f"Updated thesis: {thesis.title}",
            action_taken="thesis_updated",
        )
        return thesis.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Thesis not found: {thesis_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/theses/{thesis_id}")
def api_theses_delete(thesis_id: str):
    """Delete a thesis."""
    try:
        thesis_manager.delete_thesis(thesis_id)
        decision_log.log_decision(
            decision_type="thesis_update",
            input_data={"thesis_id": thesis_id},
            reasoning=f"Deleted thesis {thesis_id}",
            action_taken="thesis_deleted",
        )
        return {"deleted": thesis_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Thesis not found: {thesis_id}")


@app.get("/api/overrides")
def api_overrides_list():
    """Returns active signal overrides."""
    return {
        "overrides": [o.to_dict() for o in override_manager.get_active()],
        "total": len(override_manager.get_all()),
    }


@app.post("/api/overrides")
def api_overrides_create(body: OverrideCreate):
    """Create a new signal override."""
    try:
        override = override_manager.create_override(
            signal_type=body.signal_type,
            ticker_or_market=body.ticker_or_market,
            override_type=body.override_type,
            strength=body.strength,
            reason=body.reason,
            expires_at=body.expires_at,
        )
        decision_log.log_decision(
            decision_type="override",
            input_data=body.model_dump(),
            output_data={"override_id": override.id},
            reasoning=f"Created override: {body.override_type} {body.signal_type} for {body.ticker_or_market}",
            action_taken="override_created",
        )
        return override.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/overrides/{override_id}")
def api_overrides_delete(override_id: str):
    """Remove a signal override."""
    try:
        override_manager.remove_override(override_id)
        decision_log.log_decision(
            decision_type="override",
            input_data={"override_id": override_id},
            reasoning=f"Removed override {override_id}",
            action_taken="override_removed",
        )
        return {"deleted": override_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Override not found: {override_id}")


@app.get("/api/kill-switch")
def api_kill_switch_status():
    """Returns kill switch status."""
    return kill_switch.status()


@app.post("/api/kill-switch")
def api_kill_switch_toggle(body: KillSwitchToggle):
    """Toggle the kill switch."""
    if body.active:
        kill_switch.activate(reason=body.reason or "Activated via API")
        decision_log.log_decision(
            decision_type="risk_check",
            input_data={"action": "kill_switch_activate", "reason": body.reason},
            reasoning=f"Kill switch activated: {body.reason}",
            action_taken="kill_switch_on",
        )
    else:
        kill_switch.deactivate()
        decision_log.log_decision(
            decision_type="risk_check",
            input_data={"action": "kill_switch_deactivate"},
            reasoning="Kill switch deactivated via API",
            action_taken="kill_switch_off",
        )
    return kill_switch.status()


# ------------------------------------------------------------------
# Competitive edge endpoints
# ------------------------------------------------------------------

VALIDATIONS_DIR = DATA_DIR / "validations"
NICHE_DIR = DATA_DIR / "niche-markets"


@app.get("/api/regime")
def api_regime():
    """Current market regime and risk multiplier."""
    try:
        from src.core.regime_detector import RegimeDetector
        detector = RegimeDetector(str(BASE_DIR))
        snapshot = detector.get_last_snapshot()
        if snapshot:
            return snapshot.to_dict()
        snapshot = detector.detect_regime()
        return snapshot.to_dict()
    except Exception as e:
        history_file = DATA_DIR / "regime-history.jsonl"
        if history_file.exists():
            try:
                last_line = ""
                with open(history_file) as f:
                    for line in f:
                        if line.strip():
                            last_line = line.strip()
                if last_line:
                    return json.loads(last_line)
            except Exception:
                pass
        return {
            "regime": "UNKNOWN",
            "risk_multiplier": 0.5,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.get("/api/circuit-breaker")
def api_circuit_breaker_status():
    """Circuit breaker status."""
    try:
        from src.core.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(str(BASE_DIR))
        return cb.status()
    except Exception as e:
        state_file = DATA_DIR / "circuit-breaker.json"
        data = read_json(state_file)
        if data:
            return data
        return {
            "tripped": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.post("/api/circuit-breaker/reset")
def api_circuit_breaker_reset():
    """Manual circuit breaker reset."""
    try:
        from src.core.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(str(BASE_DIR))
        msg = cb.reset()
        return {"status": "ok", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/correlations")
def api_correlations():
    """Portfolio correlation report."""
    try:
        from src.core.correlation_tracker import CorrelationTracker
        tracker = CorrelationTracker(str(BASE_DIR))
        strategy = read_json(CONFIG_DIR / "strategy.json") or {}
        tickers = strategy.get("data_sources", {}).get("yfinance_tickers", [])
        equity_tickers = [
            t for t in tickers
            if not t.startswith("^") and "=" not in t
        ][:10]
        if not equity_tickers:
            return {
                "diversification_score": 100.0,
                "warning": "No equity tickers configured",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        report = tracker.calculate_correlations(equity_tickers, period_days=60)
        return report.to_dict()
    except Exception as e:
        return {
            "error": str(e),
            "diversification_score": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.get("/api/niche-markets")
def api_niche_markets():
    """Niche market opportunities (cached scan results)."""
    latest_file = NICHE_DIR / "latest.json" if NICHE_DIR.exists() else None
    if latest_file and latest_file.exists():
        data = read_json(latest_file)
        if data:
            return data
    return {
        "opportunities": [],
        "count": 0,
        "note": "No niche market scan results available. Run niche_finder.py to populate.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/validations")
def api_validations():
    """Signal validation results."""
    results = []
    if VALIDATIONS_DIR.exists():
        for f in sorted(VALIDATIONS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
            data = read_json(f)
            if data:
                results.append(data)
    return {
        "validations": results,
        "count": len(results),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Serve React frontend (Vite builds with base=/trading-bot/)
if FRONTEND_DIR.exists():
    if (FRONTEND_DIR / "assets").exists():
        app.mount("/trading-bot/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    if (FRONTEND_DIR / "data").exists():
        app.mount("/trading-bot/data", StaticFiles(directory=FRONTEND_DIR / "data"), name="data")

    @app.get("/trading-bot/{full_path:path}")
    def serve_frontend_prefixed(full_path: str):
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/")
    def redirect_root():
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/trading-bot/")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5555)
