"""
Timezone arbitrage detector.

Analyzes how movements in earlier-opening markets (Asia) predict
movements in later-opening markets (Europe, Americas) and identifies
exploitable patterns:

1. Session Lead/Lag: When Asia moves sharply, does Europe follow?
   Does the US reverse or continue?
2. Overnight Gap Analysis: Price gaps between session closes and opens
3. Momentum Handoff: Does momentum carry across sessions or fade?
4. Divergence Detection: When Asia and Europe disagree, who wins?
5. Currency Flow Signals: FX moves as early indicators of equity direction

Uses historical data to compute statistical edges and generates
real-time signals when patterns trigger.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import yfinance as yf
    import numpy as np
except ImportError:
    yf = None
    np = None


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] tz_arb: {msg}")


# Representative index for each session
SESSION_PROXIES = {
    "asia":     {"ticker": "^N225",  "name": "Nikkei 225"},
    "europe":   {"ticker": "^GDAXI", "name": "DAX 40"},
    "americas": {"ticker": "^GSPC",  "name": "S&P 500"},
}

# Cross-session pairs to analyze
ANALYSIS_PAIRS = [
    ("^N225", "^GDAXI",  "asia_to_europe",    "Asia -> Europe"),
    ("^N225", "^GSPC",   "asia_to_us",         "Asia -> US"),
    ("^GDAXI", "^GSPC",  "europe_to_us",       "Europe -> US"),
    ("^HSI", "^GSPC",    "hk_to_us",           "Hong Kong -> US"),
    ("^AXJO", "^GDAXI",  "aus_to_europe",      "Australia -> Europe"),
    ("000001.SS", "^GSPC", "shanghai_to_us",    "Shanghai -> US"),
]

# FX pairs that signal equity direction
FX_EQUITY_LINKS = [
    {"fx": "USDJPY=X", "equity": "^N225", "relationship": "positive",
     "note": "Weak yen (higher USDJPY) is bullish for Nikkei (export earnings)"},
    {"fx": "EURUSD=X", "equity": "^GDAXI", "relationship": "mixed",
     "note": "EUR strength can be bearish for DAX exporters"},
    {"fx": "AUDUSD=X", "equity": "^AXJO", "relationship": "positive",
     "note": "AUD strength correlates with commodity/risk appetite for ASX"},
    {"fx": "DX-Y.NYB", "equity": "^GSPC", "relationship": "negative",
     "note": "Strong dollar is headwind for S&P 500 multinationals"},
]


@dataclass
class LeadLagResult:
    leader_ticker: str
    follower_ticker: str
    pair_name: str
    label: str
    correlation: Optional[float] = None
    lead_lag_days: int = 0
    same_direction_pct: Optional[float] = None
    reversal_pct: Optional[float] = None
    avg_follow_magnitude: Optional[float] = None
    sharp_move_threshold: float = 1.0  # % move considered "sharp"
    sharp_follow_rate: Optional[float] = None  # % of sharp moves that are followed
    sample_size: int = 0
    signal: str = "neutral"  # "follow", "fade", "neutral"
    confidence: float = 0.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "leader": self.leader_ticker,
            "follower": self.follower_ticker,
            "pair_name": self.pair_name,
            "label": self.label,
            "correlation": self.correlation,
            "lead_lag_days": self.lead_lag_days,
            "same_direction_pct": self.same_direction_pct,
            "reversal_pct": self.reversal_pct,
            "avg_follow_magnitude": self.avg_follow_magnitude,
            "sharp_move_threshold": self.sharp_move_threshold,
            "sharp_follow_rate": self.sharp_follow_rate,
            "sample_size": self.sample_size,
            "signal": self.signal,
            "confidence": self.confidence,
            "description": self.description,
        }


@dataclass
class TimezoneSignal:
    """A real-time signal from timezone analysis."""
    signal_type: str  # "momentum_handoff", "session_divergence", "fx_equity_lead", "gap_reversion"
    direction: str    # "bullish", "bearish", "neutral"
    strength: float   # 0.0 to 1.0
    target_market: str
    source_market: str
    description: str
    supporting_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "direction": self.direction,
            "strength": self.strength,
            "target_market": self.target_market,
            "source_market": self.source_market,
            "description": self.description,
            "supporting_data": self.supporting_data,
        }


class TimezoneArbDetector:
    """
    Detects timezone-based arbitrage patterns using historical
    lead-lag analysis and real-time session comparison.
    """

    def __init__(self, lookback_days: int = 120):
        self.lookback_days = lookback_days
        self._lead_lag_cache: Dict[str, LeadLagResult] = {}
        self._returns_cache: Dict[str, Any] = {}

    def _get_returns(self, ticker: str) -> Optional[Any]:
        """Fetch daily returns for a ticker."""
        if ticker in self._returns_cache:
            return self._returns_cache[ticker]

        if yf is None or np is None:
            return None

        try:
            data = yf.download(ticker, period=f"{self.lookback_days + 30}d", progress=False, auto_adjust=True)
            if data is None or data.empty:
                return None

            close = data["Close"]
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]

            returns = close.pct_change().dropna() * 100  # in percent
            self._returns_cache[ticker] = returns
            return returns
        except Exception as e:
            _log(f"failed to get returns for {ticker}: {e}")
            return None

    def analyze_lead_lag(self, leader: str, follower: str, pair_name: str, label: str) -> LeadLagResult:
        """
        Analyze whether leader's daily returns predict follower's next-day returns.
        """
        ret_l = self._get_returns(leader)
        ret_f = self._get_returns(follower)

        if ret_l is None or ret_f is None or np is None:
            return LeadLagResult(
                leader_ticker=leader, follower_ticker=follower,
                pair_name=pair_name, label=label,
                description="Insufficient data",
            )

        # Align dates
        common = ret_l.index.intersection(ret_f.index)
        if len(common) < 30:
            return LeadLagResult(
                leader_ticker=leader, follower_ticker=follower,
                pair_name=pair_name, label=label,
                sample_size=len(common),
                description="Insufficient overlapping data",
            )

        l_aligned = ret_l.loc[common].values
        f_aligned = ret_f.loc[common].values

        # Same-day correlation
        corr = float(np.corrcoef(l_aligned, f_aligned)[0, 1])

        # Leader today -> Follower today (for same-day effect due to timezone)
        # Since Asia opens first, Asia's "today" return could predict Europe/US "today"
        same_dir = np.sum(np.sign(l_aligned) == np.sign(f_aligned))
        same_dir_pct = round(same_dir / len(l_aligned) * 100, 1)
        reversal_pct = round(100 - same_dir_pct, 1)

        # Sharp move analysis: when leader moves > threshold
        threshold = 1.0
        sharp_mask = np.abs(l_aligned) > threshold
        sharp_count = int(np.sum(sharp_mask))

        sharp_follow_rate = None
        avg_follow_mag = None
        if sharp_count > 5:
            sharp_leader = l_aligned[sharp_mask]
            sharp_follower = f_aligned[sharp_mask]
            # How often does follower move in same direction after sharp leader move?
            same_after_sharp = np.sum(np.sign(sharp_leader) == np.sign(sharp_follower))
            sharp_follow_rate = round(same_after_sharp / sharp_count * 100, 1)
            avg_follow_mag = round(float(np.mean(np.abs(sharp_follower))), 2)

        # Determine signal
        signal = "neutral"
        confidence = 0.0
        desc = ""

        if sharp_follow_rate is not None:
            if sharp_follow_rate > 65:
                signal = "follow"
                confidence = min((sharp_follow_rate - 50) / 50 * 100, 100)
                desc = (f"When {label.split(' -> ')[0]} moves sharply (>{threshold}%), "
                        f"{label.split(' -> ')[1]} follows {sharp_follow_rate}% of the time "
                        f"(avg magnitude: {avg_follow_mag}%)")
            elif sharp_follow_rate < 35:
                signal = "fade"
                confidence = min((50 - sharp_follow_rate) / 50 * 100, 100)
                desc = (f"When {label.split(' -> ')[0]} moves sharply, "
                        f"{label.split(' -> ')[1]} reverses {100 - sharp_follow_rate:.0f}% of the time")
            else:
                desc = f"No strong lead-lag pattern detected between {label}"

        result = LeadLagResult(
            leader_ticker=leader,
            follower_ticker=follower,
            pair_name=pair_name,
            label=label,
            correlation=round(corr, 3),
            same_direction_pct=same_dir_pct,
            reversal_pct=reversal_pct,
            avg_follow_magnitude=avg_follow_mag,
            sharp_move_threshold=threshold,
            sharp_follow_rate=sharp_follow_rate,
            sample_size=len(common),
            signal=signal,
            confidence=round(confidence, 1),
            description=desc,
        )

        self._lead_lag_cache[pair_name] = result
        return result

    def analyze_all_pairs(self) -> List[LeadLagResult]:
        """Run lead-lag analysis on all configured pairs."""
        _log(f"analyzing {len(ANALYSIS_PAIRS)} cross-session pairs...")
        results = []
        for leader, follower, pair_name, label in ANALYSIS_PAIRS:
            result = self.analyze_lead_lag(leader, follower, pair_name, label)
            results.append(result)
            sig = result.signal.upper()
            _log(f"  {label}: {sig} (corr={result.correlation}, sharp_follow={result.sharp_follow_rate}%)")
        return results

    def generate_realtime_signals(self, global_data: Dict[str, Any]) -> List[TimezoneSignal]:
        """
        Generate real-time timezone arbitrage signals from fresh global market data.

        Takes the output of GlobalMarketCollector.fetch_all() as input.
        """
        signals = []

        sessions = global_data.get("sessions", {})
        indices = global_data.get("indices", {})

        # 1. Momentum handoff signals
        for from_s, to_s in [("asia", "europe"), ("europe", "americas"), ("asia", "americas")]:
            s_from = sessions.get(from_s, {})
            s_to = sessions.get(to_s, {})

            avg_from = s_from.get("avg_change_pct", 0)
            avg_to = s_to.get("avg_change_pct", 0)

            if abs(avg_from) > 0.5:
                # Strong move in earlier session
                if avg_from > 0.5 and avg_to < -0.3:
                    signals.append(TimezoneSignal(
                        signal_type="session_divergence",
                        direction="bearish",
                        strength=min(abs(avg_from - avg_to) / 3, 1.0),
                        target_market=to_s,
                        source_market=from_s,
                        description=f"{s_from.get('label', from_s)} rallied ({avg_from:+.2f}%) but {s_to.get('label', to_s)} selling ({avg_to:+.2f}%)",
                        supporting_data={"from_change": avg_from, "to_change": avg_to},
                    ))
                elif avg_from < -0.5 and avg_to > 0.3:
                    signals.append(TimezoneSignal(
                        signal_type="session_divergence",
                        direction="bullish",
                        strength=min(abs(avg_from - avg_to) / 3, 1.0),
                        target_market=to_s,
                        source_market=from_s,
                        description=f"{s_from.get('label', from_s)} sold off ({avg_from:+.2f}%) but {s_to.get('label', to_s)} buying ({avg_to:+.2f}%)",
                        supporting_data={"from_change": avg_from, "to_change": avg_to},
                    ))
                elif abs(avg_from) > 1.0 and (avg_from > 0) == (avg_to > 0):
                    signals.append(TimezoneSignal(
                        signal_type="momentum_handoff",
                        direction="bullish" if avg_from > 0 else "bearish",
                        strength=min(abs(avg_from) / 3, 1.0),
                        target_market=to_s,
                        source_market=from_s,
                        description=f"Strong momentum from {s_from.get('label', from_s)} ({avg_from:+.2f}%) continuing in {s_to.get('label', to_s)} ({avg_to:+.2f}%)",
                        supporting_data={"from_change": avg_from, "to_change": avg_to},
                    ))

        # 2. Breadth divergence
        for region in ["asia", "europe", "americas"]:
            s = sessions.get(region, {})
            breadth = s.get("breadth", 50)
            avg_chg = s.get("avg_change_pct", 0)

            if breadth > 80 and avg_chg > 0.3:
                signals.append(TimezoneSignal(
                    signal_type="broad_strength",
                    direction="bullish",
                    strength=breadth / 100,
                    target_market=region,
                    source_market=region,
                    description=f"{s.get('label', region)}: {breadth}% of markets positive, strong breadth",
                    supporting_data={"breadth": breadth, "avg_change": avg_chg},
                ))
            elif breadth < 20 and avg_chg < -0.3:
                signals.append(TimezoneSignal(
                    signal_type="broad_weakness",
                    direction="bearish",
                    strength=(100 - breadth) / 100,
                    target_market=region,
                    source_market=region,
                    description=f"{s.get('label', region)}: only {breadth}% positive, broad weakness",
                    supporting_data={"breadth": breadth, "avg_change": avg_chg},
                ))

        # 3. FX-equity divergence
        forex_data = {d.get("ticker", d.get("name", "")): d for d in global_data.get("forex", [])}
        all_indices_flat = {}
        for region_data in indices.values():
            for idx in region_data:
                all_indices_flat[idx.get("ticker", "")] = idx

        for link in FX_EQUITY_LINKS:
            fx = forex_data.get(link["fx"])
            eq = all_indices_flat.get(link["equity"])
            if not fx or not eq:
                continue
            fx_chg = fx.get("change_pct")
            eq_chg = eq.get("change_pct")
            if fx_chg is None or eq_chg is None:
                continue

            rel = link["relationship"]
            divergent = False
            if rel == "positive" and ((fx_chg > 0.3 and eq_chg < -0.3) or (fx_chg < -0.3 and eq_chg > 0.3)):
                divergent = True
            elif rel == "negative" and ((fx_chg > 0.3 and eq_chg > 0.3) or (fx_chg < -0.3 and eq_chg < -0.3)):
                divergent = True

            if divergent:
                signals.append(TimezoneSignal(
                    signal_type="fx_equity_divergence",
                    direction="neutral",
                    strength=min((abs(fx_chg) + abs(eq_chg)) / 4, 1.0),
                    target_market=link["equity"],
                    source_market=link["fx"],
                    description=f"FX-equity divergence: {fx.get('name', link['fx'])} ({fx_chg:+.2f}%) vs {eq.get('name', link['equity'])} ({eq_chg:+.2f}%). {link['note']}",
                    supporting_data={"fx_change": fx_chg, "equity_change": eq_chg, "expected_rel": rel},
                ))

        _log(f"generated {len(signals)} timezone signals")
        return signals

    def full_analysis(self, global_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run complete timezone arbitrage analysis.
        Returns lead-lag analysis + real-time signals.
        """
        lead_lag = self.analyze_all_pairs()
        realtime = self.generate_realtime_signals(global_data) if global_data else []

        return {
            "lead_lag": [r.to_dict() for r in lead_lag],
            "realtime_signals": [s.to_dict() for s in realtime],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }


# ------------------------------------------------------------------
if __name__ == "__main__":
    detector = TimezoneArbDetector()
    results = detector.analyze_all_pairs()
    for r in results:
        print(json.dumps(r.to_dict(), indent=2))
