"""
FRED API macro signal fetcher.

Fetches key economic indicators from the Federal Reserve Economic Data (FRED)
API: yields, mortgage rates, VIX, unemployment, CPI, fed funds, GDP,
and consumer sentiment. Compares current values against 30-day-ago values
and flags threshold breaches.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from src.core.config import Config

try:
    from fredapi import Fred
except ImportError:
    Fred = None  # type: ignore


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] fred_macro: {msg}")


# Default series with human-readable names, thresholds, and directions.
# direction: "rising" means breaching threshold is bearish (stress indicator)
#            "falling" means breaching threshold is bullish
DEFAULT_SERIES = {
    "DGS10":       {"name": "10Y Treasury Yield",      "threshold": 4.5,  "direction": "rising"},
    "DGS30":       {"name": "30Y Treasury Yield",      "threshold": 5.0,  "direction": "rising"},
    "MORTGAGE30US": {"name": "30Y Mortgage Rate",       "threshold": 7.5,  "direction": "rising"},
    "T10Y2Y":      {"name": "10Y-2Y Yield Curve",      "threshold": -0.2, "direction": "falling"},
    "VIXCLS":      {"name": "VIX Close",                "threshold": 25.0, "direction": "rising"},
    "UNRATE":      {"name": "Unemployment Rate",        "threshold": 5.0,  "direction": "rising"},
    "CPIAUCSL":    {"name": "CPI All Urban Consumers",  "threshold": None, "direction": "rising"},
    "FEDFUNDS":    {"name": "Federal Funds Rate",       "threshold": 5.5,  "direction": "rising"},
    "GDP":         {"name": "Gross Domestic Product",    "threshold": None, "direction": "falling"},
    "UMCSENT":     {"name": "Consumer Sentiment",       "threshold": 60.0, "direction": "falling"},
}


@dataclass
class FredSignal:
    series_id: str
    name: str
    value: Optional[float]
    prev_value: Optional[float]
    change_pct: Optional[float]
    threshold: Optional[float]
    breached: bool
    direction: str          # "rising" or "falling"
    last_updated: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "series_id": self.series_id,
            "name": self.name,
            "value": self.value,
            "prev_value": self.prev_value,
            "change_pct": self.change_pct,
            "threshold": self.threshold,
            "breached": self.breached,
            "direction": self.direction,
            "last_updated": self.last_updated,
            "error": self.error,
        }


class FredMacroFetcher:
    """
    Fetches FRED economic data series and evaluates threshold breaches.

    Usage:
        cfg = Config()
        fetcher = FredMacroFetcher(cfg)
        signals = fetcher.fetch_all()
    """

    def __init__(self, config: Config):
        self.config = config
        self._fred: Optional[Any] = None

        # Load series config from strategy.json or use defaults
        fred_cfg = config._raw_strategy.get("fred_api", {})
        self.series_config: Dict[str, Dict[str, Any]] = {}
        configured_series = fred_cfg.get("series", [])
        if configured_series:
            for s in configured_series:
                sid = s["id"]
                self.series_config[sid] = {
                    "name": s.get("name", sid),
                    "threshold": s.get("threshold"),
                    "direction": s.get("direction", "rising"),
                }
        else:
            self.series_config = dict(DEFAULT_SERIES)

        # Resolve API key: env var > config fred_api_key > config file path > None
        self._api_key = self._resolve_api_key(fred_cfg)

        if self._api_key and Fred is not None:
            self._fred = Fred(api_key=self._api_key)
            _log(f"initialized with {len(self.series_config)} series")
        elif Fred is None:
            _log("WARNING: fredapi not installed, signals will be empty")
        else:
            _log("WARNING: no FRED API key found, signals will be empty")

    def _resolve_api_key(self, fred_cfg: Dict[str, Any]) -> Optional[str]:
        # 1. Environment variable
        key = os.environ.get("FRED_API_KEY")
        if key:
            return key

        # 2. Direct key in config
        key = fred_cfg.get("api_key")
        if key:
            return key

        # 3. Key file path from strategy.json macro_signals section
        key_path = self.config._raw_strategy.get("macro_signals", {}).get("fred_api_key_path")
        if key_path:
            full_path = os.path.join(self.config.project_root, key_path)
            if os.path.isfile(full_path):
                try:
                    with open(full_path) as f:
                        data = json.load(f)
                    return data.get("api_key") or data.get("key")
                except Exception:
                    pass
        return None

    def _fetch_series(self, series_id: str) -> FredSignal:
        meta = self.series_config.get(series_id, {"name": series_id, "threshold": None, "direction": "rising"})
        now_str = datetime.now(timezone.utc).isoformat()

        if self._fred is None:
            return FredSignal(
                series_id=series_id, name=meta["name"],
                value=None, prev_value=None, change_pct=None,
                threshold=meta.get("threshold"), breached=False,
                direction=meta.get("direction", "rising"),
                last_updated=now_str,
                error="FRED client not available (missing key or library)",
            )

        try:
            # Fetch last 60 days to ensure we get a 30-day-ago value
            end = datetime.now()
            start = end - timedelta(days=90)
            data = self._fred.get_series(series_id, observation_start=start, observation_end=end)

            if data is None or data.empty:
                return FredSignal(
                    series_id=series_id, name=meta["name"],
                    value=None, prev_value=None, change_pct=None,
                    threshold=meta.get("threshold"), breached=False,
                    direction=meta.get("direction", "rising"),
                    last_updated=now_str, error="no data returned",
                )

            # Drop NaN values
            data = data.dropna()
            if data.empty:
                return FredSignal(
                    series_id=series_id, name=meta["name"],
                    value=None, prev_value=None, change_pct=None,
                    threshold=meta.get("threshold"), breached=False,
                    direction=meta.get("direction", "rising"),
                    last_updated=now_str, error="all values NaN",
                )

            current_value = float(data.iloc[-1])

            # Find value closest to 30 days ago
            prev_value = None
            target_date = data.index[-1] - timedelta(days=30)
            # Get the observation closest to 30 days ago
            earlier = data[data.index <= target_date]
            if not earlier.empty:
                prev_value = float(earlier.iloc[-1])

            # Calculate change
            change_pct = None
            if prev_value is not None and prev_value != 0:
                change_pct = round((current_value - prev_value) / abs(prev_value) * 100, 2)

            # Threshold breach
            threshold = meta.get("threshold")
            breached = False
            direction = meta.get("direction", "rising")
            if threshold is not None:
                if direction == "rising":
                    breached = current_value >= threshold
                elif direction == "falling":
                    breached = current_value <= threshold

            return FredSignal(
                series_id=series_id,
                name=meta["name"],
                value=round(current_value, 4),
                prev_value=round(prev_value, 4) if prev_value is not None else None,
                change_pct=change_pct,
                threshold=threshold,
                breached=breached,
                direction=direction,
                last_updated=str(data.index[-1]),
            )

        except Exception as e:
            return FredSignal(
                series_id=series_id, name=meta["name"],
                value=None, prev_value=None, change_pct=None,
                threshold=meta.get("threshold"), breached=False,
                direction=meta.get("direction", "rising"),
                last_updated=now_str, error=str(e),
            )

    def fetch_all(self) -> List[FredSignal]:
        if self._fred is None:
            _log("skipping fetch: FRED client not available")
            return []

        _log(f"fetching {len(self.series_config)} FRED series...")
        signals = []
        for series_id in sorted(self.series_config.keys()):
            sig = self._fetch_series(series_id)
            signals.append(sig)
            if sig.value is not None:
                breach_flag = " [BREACHED]" if sig.breached else ""
                chg = f" ({sig.change_pct:+.2f}%)" if sig.change_pct is not None else ""
                _log(f"  {series_id:<15} {sig.value:>10.4f}{chg}{breach_flag}")
            else:
                _log(f"  {series_id:<15} ERROR: {sig.error}")

        breached = sum(1 for s in signals if s.breached)
        _log(f"summary: {len(signals)} series, {breached} threshold breaches")
        return signals

    def signals_to_json(self, signals: List[FredSignal]) -> str:
        return json.dumps([s.to_dict() for s in signals], indent=2)


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    fetcher = FredMacroFetcher(cfg)

    if fetcher._fred is not None:
        signals = fetcher.fetch_all()
        print(f"\nFetched {len(signals)} FRED signals")
    else:
        print("FRED client not available (missing API key or fredapi library)")
        print(f"Series configured: {list(fetcher.series_config.keys())}")
