"""
Global macro indicator fetcher.

Extends beyond US FRED data to track global central bank rates,
PMIs, and key economic indicators via FRED's international series.

FRED provides international data series. No additional API keys needed.

Covers:
- Central bank policy rates (Fed, ECB, BOJ, BOE, PBOC, RBA, BOC, Riksbank)
- Purchasing Managers Indices (global manufacturing/services)
- Trade balances and current accounts
- Inflation rates (CPI) across major economies
- Yield differentials (carry trade signals)
- Commodity-linked economic indicators
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

try:
    from fredapi import Fred
except ImportError:
    Fred = None


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] global_macro: {msg}")


# International FRED series
GLOBAL_SERIES = {
    # Central Bank Rates
    "FEDFUNDS":   {"name": "Fed Funds Rate",        "country": "US", "category": "rates",    "threshold": 5.5, "direction": "rising"},
    "ECBDFR":     {"name": "ECB Deposit Rate",      "country": "EU", "category": "rates",    "threshold": 4.0, "direction": "rising"},
    "IRSTCB01JPM156N": {"name": "BOJ Policy Rate",  "country": "JP", "category": "rates",    "threshold": 0.5, "direction": "rising"},
    "IUDSOIA":    {"name": "BOE Bank Rate",          "country": "GB", "category": "rates",    "threshold": 5.0, "direction": "rising"},

    # Inflation (CPI YoY)
    "CPALTT01USM657N":  {"name": "US CPI YoY",          "country": "US", "category": "inflation", "threshold": 3.0, "direction": "rising"},
    "CP0000EZ19M086NEST": {"name": "Eurozone HICP YoY", "country": "EU", "category": "inflation", "threshold": 3.0, "direction": "rising"},
    "CPALTT01JPM659N":  {"name": "Japan CPI YoY",       "country": "JP", "category": "inflation", "threshold": 3.0, "direction": "rising"},
    "CPALTT01GBM659N":  {"name": "UK CPI YoY",          "country": "GB", "category": "inflation", "threshold": 3.0, "direction": "rising"},
    "CPALTT01CNM659N":  {"name": "China CPI YoY",       "country": "CN", "category": "inflation", "threshold": 3.0, "direction": "rising"},

    # Manufacturing PMIs (or proxies from FRED)
    "MANEMP":     {"name": "US Manufacturing Employment", "country": "US", "category": "pmi_proxy", "threshold": None, "direction": "falling"},
    "INDPRO":     {"name": "US Industrial Production",    "country": "US", "category": "production","threshold": None, "direction": "falling"},

    # Trade and External
    "BOPGSTB":    {"name": "US Trade Balance",       "country": "US", "category": "trade", "threshold": None, "direction": "falling"},
    "XTIMVA01CNM667S": {"name": "China Exports",    "country": "CN", "category": "trade", "threshold": None, "direction": "falling"},

    # Yield Spreads (carry trade signals)
    "T10Y2Y":     {"name": "US 10Y-2Y Spread",      "country": "US", "category": "yields",   "threshold": -0.2, "direction": "falling"},
    "T10Y3M":     {"name": "US 10Y-3M Spread",      "country": "US", "category": "yields",   "threshold": -0.5, "direction": "falling"},

    # Financial Conditions
    "STLFSI4":    {"name": "Financial Stress Index", "country": "US", "category": "stress",   "threshold": 1.5, "direction": "rising"},
    "BAMLH0A0HYM2": {"name": "HY Credit Spread",   "country": "US", "category": "credit",   "threshold": 5.0, "direction": "rising"},

    # Global Demand Proxies
    "PCOPPUSDM":  {"name": "Copper Price (Global)",  "country": "GL", "category": "commodities", "threshold": None, "direction": "falling"},
    "DCOILBRENTEU": {"name": "Brent Crude (Global)", "country": "GL", "category": "commodities", "threshold": 90, "direction": "rising"},

    # Labor Market
    "UNRATE":     {"name": "US Unemployment",        "country": "US", "category": "labor",    "threshold": 5.0, "direction": "rising"},
    "LRHUTTTTJPM156S": {"name": "Japan Unemployment","country": "JP", "category": "labor",    "threshold": 3.5, "direction": "rising"},
    "LRHUTTTTEZM156S": {"name": "Eurozone Unemployment","country": "EU","category": "labor",  "threshold": 8.0, "direction": "rising"},

    # Money Supply
    "M2SL":       {"name": "US M2 Money Supply",     "country": "US", "category": "money",    "threshold": None, "direction": "falling"},
    "MANMM101EZM189S": {"name": "Eurozone M1",      "country": "EU", "category": "money",    "threshold": None, "direction": "falling"},
}


@dataclass
class GlobalMacroSignal:
    series_id: str
    name: str
    country: str
    category: str
    value: Optional[float] = None
    prev_value: Optional[float] = None
    change_pct: Optional[float] = None
    threshold: Optional[float] = None
    breached: bool = False
    direction: str = "rising"
    last_updated: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "series_id": self.series_id,
            "name": self.name,
            "country": self.country,
            "category": self.category,
            "value": self.value,
            "prev_value": self.prev_value,
            "change_pct": self.change_pct,
            "threshold": self.threshold,
            "breached": self.breached,
            "direction": self.direction,
            "last_updated": self.last_updated,
            "error": self.error,
        }


@dataclass
class RateDifferential:
    """Carry trade signal from interest rate differentials."""
    high_rate_country: str
    low_rate_country: str
    high_rate: float
    low_rate: float
    differential: float
    direction: str  # "carry_into_high" or "carry_unwinding"
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "high_rate_country": self.high_rate_country,
            "low_rate_country": self.low_rate_country,
            "high_rate": self.high_rate,
            "low_rate": self.low_rate,
            "differential": self.differential,
            "direction": self.direction,
            "description": self.description,
        }


class GlobalMacroFetcher:
    """
    Fetches international economic indicators from FRED.
    """

    def __init__(self, api_key: Optional[str] = None, key_path: Optional[str] = None):
        self._fred = None
        self._api_key = api_key

        if not self._api_key and key_path:
            try:
                import os
                if os.path.isfile(key_path):
                    with open(key_path) as f:
                        data = json.load(f)
                    self._api_key = data.get("api_key") or data.get("key")
            except Exception:
                pass

        if self._api_key and Fred is not None:
            self._fred = Fred(api_key=self._api_key)
            _log(f"initialized with {len(GLOBAL_SERIES)} global series")
        else:
            _log("WARNING: FRED client not available")

    def _fetch_one(self, series_id: str) -> GlobalMacroSignal:
        meta = GLOBAL_SERIES.get(series_id, {
            "name": series_id, "country": "??", "category": "other",
            "threshold": None, "direction": "rising"
        })
        now_str = datetime.now(timezone.utc).isoformat()

        if self._fred is None:
            return GlobalMacroSignal(
                series_id=series_id, name=meta["name"],
                country=meta["country"], category=meta["category"],
                direction=meta.get("direction", "rising"),
                last_updated=now_str,
                error="FRED client not available",
            )

        try:
            end = datetime.now()
            start = end - timedelta(days=180)
            data = self._fred.get_series(series_id, observation_start=start, observation_end=end)

            if data is None or data.empty:
                return GlobalMacroSignal(
                    series_id=series_id, name=meta["name"],
                    country=meta["country"], category=meta["category"],
                    direction=meta.get("direction", "rising"),
                    last_updated=now_str, error="no data",
                )

            data = data.dropna()
            if data.empty:
                return GlobalMacroSignal(
                    series_id=series_id, name=meta["name"],
                    country=meta["country"], category=meta["category"],
                    direction=meta.get("direction", "rising"),
                    last_updated=now_str, error="all NaN",
                )

            current = float(data.iloc[-1])

            # Previous value (30 days ago or earlier)
            prev = None
            target = data.index[-1] - timedelta(days=30)
            earlier = data[data.index <= target]
            if not earlier.empty:
                prev = float(earlier.iloc[-1])

            change = None
            if prev is not None and prev != 0:
                change = round((current - prev) / abs(prev) * 100, 2)

            # Threshold check
            threshold = meta.get("threshold")
            breached = False
            direction = meta.get("direction", "rising")
            if threshold is not None:
                if direction == "rising":
                    breached = current >= threshold
                elif direction == "falling":
                    breached = current <= threshold

            return GlobalMacroSignal(
                series_id=series_id,
                name=meta["name"],
                country=meta["country"],
                category=meta["category"],
                value=round(current, 4),
                prev_value=round(prev, 4) if prev else None,
                change_pct=change,
                threshold=threshold,
                breached=breached,
                direction=direction,
                last_updated=str(data.index[-1]),
            )

        except Exception as e:
            return GlobalMacroSignal(
                series_id=series_id, name=meta["name"],
                country=meta["country"], category=meta["category"],
                direction=meta.get("direction", "rising"),
                last_updated=now_str, error=str(e)[:200],
            )

    def fetch_all(self) -> List[GlobalMacroSignal]:
        if self._fred is None:
            _log("skipping: FRED client not available")
            return []

        _log(f"fetching {len(GLOBAL_SERIES)} global series...")
        signals = []
        for sid in sorted(GLOBAL_SERIES.keys()):
            sig = self._fetch_one(sid)
            signals.append(sig)
            if sig.value is not None:
                flag = " [BREACHED]" if sig.breached else ""
                chg = f" ({sig.change_pct:+.2f}%)" if sig.change_pct is not None else ""
                _log(f"  {sig.country}/{sid:<20} {sig.value:>12.4f}{chg}{flag}")
            else:
                _log(f"  {sig.country}/{sid:<20} ERROR: {sig.error}")

        ok = sum(1 for s in signals if s.error is None)
        breached = sum(1 for s in signals if s.breached)
        _log(f"done: {ok}/{len(signals)} fetched, {breached} breaches")
        return signals

    def compute_rate_differentials(self, signals: List[GlobalMacroSignal]) -> List[RateDifferential]:
        """Compute interest rate differentials between major central banks."""
        rates = {}
        for s in signals:
            if s.category == "rates" and s.value is not None:
                rates[s.country] = {"name": s.name, "rate": s.value}

        if len(rates) < 2:
            return []

        diffs = []
        countries = sorted(rates.keys())
        for i in range(len(countries)):
            for j in range(i + 1, len(countries)):
                c1, c2 = countries[i], countries[j]
                r1, r2 = rates[c1]["rate"], rates[c2]["rate"]

                if r1 > r2:
                    high, low = c1, c2
                    h_rate, l_rate = r1, r2
                else:
                    high, low = c2, c1
                    h_rate, l_rate = r2, r1

                diff = round(h_rate - l_rate, 2)

                desc = f"{high} rate ({h_rate}%) minus {low} rate ({l_rate}%) = {diff}pp differential"
                if diff > 3:
                    desc += ". Large spread favors carry trade into " + high
                    direction = "carry_into_high"
                elif diff < 1:
                    desc += ". Narrow spread reduces carry trade incentive"
                    direction = "carry_unwinding"
                else:
                    direction = "carry_into_high"

                diffs.append(RateDifferential(
                    high_rate_country=high,
                    low_rate_country=low,
                    high_rate=h_rate,
                    low_rate=l_rate,
                    differential=diff,
                    direction=direction,
                    description=desc,
                ))

        diffs.sort(key=lambda d: d.differential, reverse=True)
        return diffs

    def full_analysis(self) -> Dict[str, Any]:
        """Run complete global macro analysis."""
        signals = self.fetch_all()

        # Group by category
        by_category: Dict[str, List[Dict]] = {}
        for s in signals:
            cat = s.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(s.to_dict())

        # Group by country
        by_country: Dict[str, List[Dict]] = {}
        for s in signals:
            c = s.country
            if c not in by_country:
                by_country[c] = []
            by_country[c].append(s.to_dict())

        # Rate differentials
        rate_diffs = self.compute_rate_differentials(signals)

        # Breaches summary
        breaches = [s.to_dict() for s in signals if s.breached]

        return {
            "signals": [s.to_dict() for s in signals],
            "by_category": by_category,
            "by_country": by_country,
            "rate_differentials": [d.to_dict() for d in rate_diffs],
            "breaches": breaches,
            "total_series": len(signals),
            "fetched_ok": sum(1 for s in signals if s.error is None),
            "total_breaches": len(breaches),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }


# ------------------------------------------------------------------
if __name__ == "__main__":
    import os, sys
    key_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "secrets", "fred.json")
    fetcher = GlobalMacroFetcher(key_path=key_path)
    result = fetcher.full_analysis()
    print(json.dumps(result, indent=2))
