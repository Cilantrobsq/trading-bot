#!/usr/bin/env python3
"""
Main trading bot runner. Orchestrates the full pipeline:
1. Fetch macro signals (yfinance)
2. Fetch news (RSS feeds)
3. Assess market regime (BotBrain)
4. Check thesis expirations
5. Plan trades
6. Execute paper trades for triggered stops/takes
7. Log all decisions
8. Export dashboard data

Run via cron every 30 min during market hours, or manually.
"""

import json
import os
import sys
from datetime import datetime, timezone

# Ensure project root on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.config import Config
from src.core.bot_brain import BotBrain
from src.core.decision_log import DecisionLog
from src.core.paper_trader import PaperTrader
from src.signals.macro import MacroSignalFetcher
from src.signals.fred_macro import FredMacroFetcher
from src.signals.news import NewsFeedMonitor
from src.signals.global_markets import GlobalMarketCollector
from src.signals.global_macro import GlobalMacroFetcher
from src.signals.timezone_arb import TimezoneArbDetector
from src.signals.cross_correlation import CrossCorrelationEngine
from src.reasoning.thesis import ThesisManager
from src.reasoning.overrides import OverrideManager


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] bot: {msg}")


def run():
    _log("=== Trading Bot Run Starting ===")

    cfg = Config(PROJECT_ROOT)
    decision_log = DecisionLog()
    brain = BotBrain()
    thesis_mgr = ThesisManager()
    override_mgr = OverrideManager()
    paper_trader = PaperTrader(cfg)

    # Step 1: Fetch macro signals
    _log("Step 1: Fetching macro signals...")
    fetcher = MacroSignalFetcher(cfg)
    signals = fetcher.fetch_all()

    # Save signals snapshot
    os.makedirs(cfg.data_path("snapshots"), exist_ok=True)
    signals_data = {
        "signals": [s.to_dict() for s in signals],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(cfg.data_path("snapshots", "latest-signals.json"), "w") as f:
        json.dump(signals_data, f, indent=2)

    ok_count = sum(1 for s in signals if s.signal != "error")
    err_count = sum(1 for s in signals if s.signal == "error")
    _log(f"  Signals: {ok_count} OK, {err_count} errors")

    decision_log.log_decision(
        decision_type="signal_eval",
        input_data={"ticker_count": len(signals)},
        output_data={
            "ok": ok_count,
            "errors": err_count,
            "bullish": sum(1 for s in signals if s.signal == "bullish"),
            "bearish": sum(1 for s in signals if s.signal == "bearish"),
        },
        reasoning=f"Fetched {len(signals)} macro signals via yfinance",
        confidence=80,
        action_taken="signals_updated",
    )

    # Step 1b: Fetch FRED macro data (if API key available)
    _log("Step 1b: Fetching FRED macro data...")
    try:
        fred_fetcher = FredMacroFetcher(cfg)
        fred_signals = fred_fetcher.fetch_all()
        if fred_signals:
            fred_data = {
                "signals": [s.to_dict() for s in fred_signals],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(cfg.data_path("snapshots", "latest-fred.json"), "w") as f:
                json.dump(fred_data, f, indent=2)
            fred_ok = sum(1 for s in fred_signals if s.error is None)
            _log(f"  FRED: {fred_ok}/{len(fred_signals)} series fetched")
        else:
            _log("  FRED: skipped (no API key)")
    except Exception as e:
        _log(f"  FRED fetch failed: {e}")
        fred_signals = []

    # Step 1c: Fetch global market data
    _log("Step 1c: Fetching global markets...")
    global_data = {}
    try:
        global_collector = GlobalMarketCollector()
        global_data = global_collector.fetch_all()
        with open(cfg.data_path("snapshots", "latest-global-markets.json"), "w") as f:
            json.dump(global_data, f, indent=2)
        _log(f"  Global: {global_data.get('total_markets', 0)} markets, breadth={global_data.get('global_breadth', 0)}%")

        decision_log.log_decision(
            decision_type="signal_eval",
            input_data={"global_markets": global_data.get("total_markets", 0)},
            output_data={
                "breadth": global_data.get("global_breadth", 0),
                "gaps": len(global_data.get("gaps", [])),
                "sessions": {k: v.get("avg_change_pct", 0) for k, v in global_data.get("sessions", {}).items()},
            },
            reasoning=f"Global markets: {global_data.get('total_markets', 0)} indices, breadth {global_data.get('global_breadth', 0)}%",
            confidence=75,
            action_taken="global_markets_updated",
        )
    except Exception as e:
        _log(f"  Global markets fetch failed: {e}")

    # Step 1d: Fetch global macro indicators
    _log("Step 1d: Fetching global macro indicators...")
    global_macro_data = {}
    try:
        key_path = os.path.join(PROJECT_ROOT, "secrets", "fred.json")
        global_macro = GlobalMacroFetcher(key_path=key_path)
        global_macro_result = global_macro.full_analysis()
        global_macro_data = global_macro_result
        with open(cfg.data_path("snapshots", "latest-global-macro.json"), "w") as f:
            json.dump(global_macro_result, f, indent=2)
        _log(f"  Global macro: {global_macro_result.get('fetched_ok', 0)}/{global_macro_result.get('total_series', 0)} series, {global_macro_result.get('total_breaches', 0)} breaches")
    except Exception as e:
        _log(f"  Global macro fetch failed: {e}")

    # Step 1e: Timezone arbitrage analysis
    _log("Step 1e: Running timezone arbitrage analysis...")
    tz_arb_data = {}
    try:
        tz_detector = TimezoneArbDetector()
        tz_arb_data = tz_detector.full_analysis(global_data=global_data if global_data else None)
        with open(cfg.data_path("snapshots", "latest-tz-arb.json"), "w") as f:
            json.dump(tz_arb_data, f, indent=2)
        ll_count = len(tz_arb_data.get("lead_lag", []))
        rt_count = len(tz_arb_data.get("realtime_signals", []))
        _log(f"  TZ Arb: {ll_count} lead-lag pairs, {rt_count} realtime signals")
    except Exception as e:
        _log(f"  TZ arb analysis failed: {e}")

    # Step 1f: Cross-market correlation analysis
    _log("Step 1f: Running cross-market correlation analysis...")
    correlation_data = {}
    try:
        corr_engine = CrossCorrelationEngine()
        correlation_data = corr_engine.full_analysis()
        with open(cfg.data_path("snapshots", "latest-correlations.json"), "w") as f:
            json.dump(correlation_data, f, indent=2)
        anomaly_count = len(correlation_data.get("anomalies", []))
        systemic = correlation_data.get("systemic_risk_score", 0)
        _log(f"  Correlations: {anomaly_count} anomalies, systemic risk={systemic}")
    except Exception as e:
        _log(f"  Correlation analysis failed: {e}")

    # Step 2: Fetch news
    _log("Step 2: Fetching news feeds...")
    try:
        news_monitor = NewsFeedMonitor(cfg)
        news_items = news_monitor.fetch_all()
        news_data = [i.to_dict() for i in news_items]
        with open(cfg.data_path("snapshots", "latest-news.json"), "w") as f:
            json.dump(news_data, f, indent=2)
        relevant = sum(1 for i in news_items if i.relevance_score > 0)
        _log(f"  News: {len(news_items)} total, {relevant} relevant")
    except Exception as e:
        _log(f"  News fetch failed: {e}")
        news_items = []

    # Step 3: Assess market regime
    _log("Step 3: Assessing market regime...")
    regime = brain.assess_regime()
    state = brain.get_state_dict()
    _log(f"  Regime: {regime} (confidence: {state['regime_confidence']}%)")
    _log(f"  Sentiment: {state['overall_sentiment']}")

    decision_log.log_decision(
        decision_type="signal_eval",
        input_data={"signals_count": ok_count},
        output_data={
            "regime": regime,
            "confidence": state["regime_confidence"],
            "sentiment": state["overall_sentiment"],
        },
        reasoning=f"Market regime assessed as {regime}",
        confidence=state["regime_confidence"],
        action_taken="regime_assessed",
    )

    # Step 4: Check thesis expirations
    _log("Step 4: Checking thesis expirations...")
    expired = thesis_mgr.check_expirations()
    if expired:
        _log(f"  {len(expired)} theses expired")
        for t in expired:
            decision_log.log_decision(
                decision_type="thesis_update",
                input_data={"thesis_id": t.id, "title": t.title},
                output_data={"new_status": "expired"},
                reasoning=f"Thesis '{t.title}' exceeded time horizon ({t.time_horizon} days)",
                action_taken="thesis_expired",
            )

    # Step 5: Plan trades
    _log("Step 5: Planning trades...")
    active_theses = [t.to_dict() for t in thesis_mgr.get_active()]
    active_overrides = [o.to_dict() for o in override_mgr.get_active()]
    planned = brain.plan_trades(theses=active_theses, overrides=active_overrides)
    _log(f"  Planned {len(planned)} actions")

    for action in planned:
        decision_log.log_decision(
            decision_type="trade",
            input_data={
                "market": action.market,
                "direction": action.direction,
                "size_pct": action.size_pct,
            },
            output_data={
                "action_type": action.action_type,
                "blocked_by": action.blocked_by,
                "priority": action.priority,
            },
            reasoning=action.reasoning,
            confidence=60,
            action_taken="planned" if not action.blocked_by else f"blocked:{action.blocked_by}",
        )

    # Step 6: Check stop-loss/take-profit triggers on open positions
    _log("Step 6: Checking position triggers...")
    if paper_trader.portfolio.positions:
        # Build price map from signals
        price_map = {}
        for sig in signals:
            if sig.price is not None:
                price_map[sig.ticker] = sig.price
        closed = paper_trader.auto_close_triggers(price_map)
        if closed:
            _log(f"  Closed {len(closed)} positions via triggers")
            for c in closed:
                _log(f"    {c['market_name']}: {c['reason']} @ ${c['exit_price']:.4f} P&L: ${c['realized_pnl']:.2f}")
        else:
            _log(f"  {len(paper_trader.portfolio.positions)} positions open, no triggers hit")
    else:
        _log("  No open positions")

    # Step 7: Check circuit breakers
    _log("Step 7: Checking circuit breakers...")
    pnl = paper_trader.pnl_summary()
    risk = brain.check_circuit_breakers(
        daily_pnl=pnl["total_return_usd"],
        daily_pnl_pct=pnl["total_return_pct"],
        exposure_pct=100 - (pnl["cash"] / pnl["current_value"] * 100) if pnl["current_value"] > 0 else 0,
    )
    if risk.circuit_breaker_active:
        _log("  CIRCUIT BREAKER ACTIVE")
    else:
        _log(f"  All clear. Exposure: {risk.exposure_pct:.1f}%")

    # Step 8: Save full snapshot
    _log("Step 8: Saving snapshot...")
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "regime_confidence": state["regime_confidence"],
        "sentiment": state["overall_sentiment"],
        "portfolio": pnl,
        "signals_summary": {
            "total": len(signals),
            "bullish": sum(1 for s in signals if s.signal == "bullish"),
            "bearish": sum(1 for s in signals if s.signal == "bearish"),
            "neutral": sum(1 for s in signals if s.signal == "neutral"),
            "errors": err_count,
        },
        "news_count": len(news_items),
        "active_theses": len(active_theses),
        "planned_actions": len(planned),
        "circuit_breaker": risk.circuit_breaker_active,
    }
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    with open(cfg.data_path("snapshots", f"snapshot-{ts}.json"), "w") as f:
        json.dump(snapshot, f, indent=2)
    with open(cfg.data_path("snapshots", "latest-snapshot.json"), "w") as f:
        json.dump(snapshot, f, indent=2)

    _log("=== Trading Bot Run Complete ===")
    _log(f"  Regime: {regime}, Sentiment: {state['overall_sentiment']}")
    _log(f"  Portfolio: ${pnl['current_value']:,.2f} ({pnl['total_return_pct']:+.2f}%)")
    _log(f"  Open positions: {pnl['open_positions']}")
    _log(f"  Planned actions: {len(planned)}")

    return snapshot


if __name__ == "__main__":
    run()
