"""
Global market data collector.

Fetches price data from major markets across all trading sessions:
- Asia-Pacific: Nikkei 225, Hang Seng, Shanghai Composite, KOSPI, ASX 200, Nifty 50, TWSE
- Europe: FTSE 100, DAX 40, CAC 40, STOXX 600, IBEX 35, FTSE MIB, SMI, AEX
- Americas: S&P 500, Nasdaq, Dow Jones, Russell 2000, TSX (Canada), Bovespa (Brazil), Merval (Argentina)
- Forex: Major pairs and crosses for timezone/flow analysis
- Commodities: Oil, Gold, Copper, Iron Ore proxies
- Crypto: BTC, ETH (24/7 global flow indicator)

Computes session-level summaries, cross-session momentum, and gap analysis.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] global_markets: {msg}")


# Trading sessions (UTC approximate open/close)
SESSIONS = {
    "asia": {"open_utc": 0, "close_utc": 8, "label": "Asia-Pacific"},
    "europe": {"open_utc": 7, "close_utc": 16, "label": "Europe"},
    "americas": {"open_utc": 13, "close_utc": 21, "label": "Americas"},
}

# Global market tickers organized by region
GLOBAL_TICKERS = {
    "asia": {
        "^N225":    {"name": "Nikkei 225",         "country": "JP", "currency": "JPY"},
        "^HSI":     {"name": "Hang Seng",           "country": "HK", "currency": "HKD"},
        "000001.SS":{"name": "Shanghai Composite",  "country": "CN", "currency": "CNY"},
        "^KS11":    {"name": "KOSPI",               "country": "KR", "currency": "KRW"},
        "^AXJO":    {"name": "ASX 200",             "country": "AU", "currency": "AUD"},
        "^BSESN":   {"name": "BSE Sensex",          "country": "IN", "currency": "INR"},
        "^TWII":    {"name": "TWSE",                "country": "TW", "currency": "TWD"},
        "^STI":     {"name": "Straits Times",       "country": "SG", "currency": "SGD"},
    },
    "europe": {
        "^FTSE":    {"name": "FTSE 100",            "country": "GB", "currency": "GBP"},
        "^GDAXI":   {"name": "DAX 40",              "country": "DE", "currency": "EUR"},
        "^FCHI":    {"name": "CAC 40",              "country": "FR", "currency": "EUR"},
        "^STOXX":   {"name": "STOXX 600",           "country": "EU", "currency": "EUR"},
        "^IBEX":    {"name": "IBEX 35",             "country": "ES", "currency": "EUR"},
        "FTSEMIB.MI":{"name": "FTSE MIB",           "country": "IT", "currency": "EUR"},
        "^SSMI":    {"name": "Swiss Market Index",  "country": "CH", "currency": "CHF"},
        "^AEX":     {"name": "AEX",                 "country": "NL", "currency": "EUR"},
    },
    "americas": {
        "^GSPC":    {"name": "S&P 500",             "country": "US", "currency": "USD"},
        "^IXIC":    {"name": "Nasdaq Composite",    "country": "US", "currency": "USD"},
        "^DJI":     {"name": "Dow Jones",           "country": "US", "currency": "USD"},
        "^RUT":     {"name": "Russell 2000",        "country": "US", "currency": "USD"},
        "^GSPTSE":  {"name": "TSX Composite",       "country": "CA", "currency": "CAD"},
        "^BVSP":    {"name": "Bovespa",             "country": "BR", "currency": "BRL"},
    },
}

# Key forex pairs for flow analysis
FOREX_TICKERS = {
    "EURUSD=X":  {"name": "EUR/USD", "base": "EUR", "quote": "USD"},
    "GBPUSD=X":  {"name": "GBP/USD", "base": "GBP", "quote": "USD"},
    "USDJPY=X":  {"name": "USD/JPY", "base": "USD", "quote": "JPY"},
    "USDCNH=X":  {"name": "USD/CNH", "base": "USD", "quote": "CNH"},
    "AUDUSD=X":  {"name": "AUD/USD", "base": "AUD", "quote": "USD"},
    "USDCHF=X":  {"name": "USD/CHF", "base": "USD", "quote": "CHF"},
    "EURJPY=X":  {"name": "EUR/JPY", "base": "EUR", "quote": "JPY"},
    "EURGBP=X":  {"name": "EUR/GBP", "base": "EUR", "quote": "GBP"},
    "DX-Y.NYB":  {"name": "US Dollar Index", "base": "USD", "quote": "basket"},
}

# Commodities for global demand signals
COMMODITY_TICKERS = {
    "GC=F":   {"name": "Gold Futures",   "unit": "USD/oz"},
    "CL=F":   {"name": "WTI Crude Oil",  "unit": "USD/bbl"},
    "BZ=F":   {"name": "Brent Crude",    "unit": "USD/bbl"},
    "HG=F":   {"name": "Copper Futures",  "unit": "USD/lb"},
    "SI=F":   {"name": "Silver Futures",  "unit": "USD/oz"},
    "NG=F":   {"name": "Natural Gas",     "unit": "USD/MMBtu"},
}

# Crypto as 24/7 global sentiment proxy
CRYPTO_TICKERS = {
    "BTC-USD":  {"name": "Bitcoin",   "pair": "BTC/USD"},
    "ETH-USD":  {"name": "Ethereum",  "pair": "ETH/USD"},
}

# Bond yield proxies (global rates)
BOND_TICKERS = {
    "^TNX":    {"name": "US 10Y Yield",       "country": "US"},
    "^TYX":    {"name": "US 30Y Yield",       "country": "US"},
    "^IRX":    {"name": "US 3M T-Bill",       "country": "US"},
    "DE10Y=X": {"name": "Germany 10Y Yield",  "country": "DE"},
    "GB10Y=X": {"name": "UK 10Y Gilt Yield",  "country": "GB"},
    "JP10Y=X": {"name": "Japan 10Y JGB Yield","country": "JP"},
}


@dataclass
class MarketDataPoint:
    ticker: str
    name: str
    region: str
    price: Optional[float] = None
    prev_close: Optional[float] = None
    change_pct: Optional[float] = None
    week_change_pct: Optional[float] = None
    month_change_pct: Optional[float] = None
    volume: Optional[float] = None
    avg_volume: Optional[float] = None
    volume_ratio: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    pct_from_52w_high: Optional[float] = None
    ma_50d: Optional[float] = None
    ma_200d: Optional[float] = None
    above_50d: Optional[bool] = None
    above_200d: Optional[bool] = None
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "ticker": self.ticker,
            "name": self.name,
            "region": self.region,
            "price": self.price,
            "prev_close": self.prev_close,
            "change_pct": self.change_pct,
            "week_change_pct": self.week_change_pct,
            "month_change_pct": self.month_change_pct,
            "volume": self.volume,
            "avg_volume": self.avg_volume,
            "volume_ratio": self.volume_ratio,
            "high_52w": self.high_52w,
            "low_52w": self.low_52w,
            "pct_from_52w_high": self.pct_from_52w_high,
            "ma_50d": self.ma_50d,
            "ma_200d": self.ma_200d,
            "above_50d": self.above_50d,
            "above_200d": self.above_200d,
            "error": self.error,
        }
        if self.extra:
            d["extra"] = self.extra
        return d


@dataclass
class SessionSummary:
    session: str
    label: str
    markets_up: int = 0
    markets_down: int = 0
    markets_flat: int = 0
    avg_change_pct: float = 0.0
    strongest: Optional[str] = None
    strongest_pct: Optional[float] = None
    weakest: Optional[str] = None
    weakest_pct: Optional[float] = None
    breadth: float = 0.0  # % of markets positive

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session": self.session,
            "label": self.label,
            "markets_up": self.markets_up,
            "markets_down": self.markets_down,
            "markets_flat": self.markets_flat,
            "avg_change_pct": self.avg_change_pct,
            "strongest": self.strongest,
            "strongest_pct": self.strongest_pct,
            "weakest": self.weakest,
            "weakest_pct": self.weakest_pct,
            "breadth": self.breadth,
        }


@dataclass
class GapSignal:
    """Detects gaps between sessions (e.g., Asia closes down, US opens up)."""
    from_session: str
    to_session: str
    from_avg_change: float
    to_avg_change: float
    gap_magnitude: float  # absolute difference
    divergent: bool  # True if sessions moved in opposite directions
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_session": self.from_session,
            "to_session": self.to_session,
            "from_avg_change": self.from_avg_change,
            "to_avg_change": self.to_avg_change,
            "gap_magnitude": self.gap_magnitude,
            "divergent": self.divergent,
            "description": self.description,
        }


class GlobalMarketCollector:
    """
    Fetches and analyzes global market data across all major trading sessions.
    Produces session summaries, cross-session gap analysis, and market breadth.
    """

    def __init__(self):
        self._data: Dict[str, List[MarketDataPoint]] = {}
        self._session_summaries: Dict[str, SessionSummary] = {}
        self._gaps: List[GapSignal] = []

    def _fetch_one(self, ticker: str, name: str, region: str, period: str = "3mo") -> MarketDataPoint:
        if yf is None:
            return MarketDataPoint(ticker=ticker, name=name, region=region, error="yfinance not installed")

        try:
            t = yf.Ticker(ticker)

            # Get history for moving averages and weekly/monthly change
            hist = t.history(period=period)
            if hist is None or hist.empty:
                return MarketDataPoint(ticker=ticker, name=name, region=region, error="no data")

            close = hist["Close"]
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]

            price = float(close.iloc[-1])
            prev_close = float(close.iloc[-2]) if len(close) > 1 else None

            change_pct = None
            if prev_close and prev_close > 0:
                change_pct = round((price - prev_close) / prev_close * 100, 2)

            # Weekly change (5 trading days ago)
            week_change = None
            if len(close) > 5:
                week_ago = float(close.iloc[-6])
                if week_ago > 0:
                    week_change = round((price - week_ago) / week_ago * 100, 2)

            # Monthly change (22 trading days ago)
            month_change = None
            if len(close) > 22:
                month_ago = float(close.iloc[-23])
                if month_ago > 0:
                    month_change = round((price - month_ago) / month_ago * 100, 2)

            # Volume analysis
            vol = None
            avg_vol = None
            vol_ratio = None
            if "Volume" in hist.columns:
                vol_series = hist["Volume"]
                if hasattr(vol_series, "columns"):
                    vol_series = vol_series.iloc[:, 0]
                vol = float(vol_series.iloc[-1]) if len(vol_series) > 0 else None
                if len(vol_series) > 20:
                    avg_vol = float(vol_series.iloc[-21:-1].mean())
                    if avg_vol and avg_vol > 0 and vol:
                        vol_ratio = round(vol / avg_vol, 2)

            # 52-week high/low
            high_52w = float(close.max()) if len(close) > 0 else None
            low_52w = float(close.min()) if len(close) > 0 else None
            pct_from_high = None
            if high_52w and high_52w > 0:
                pct_from_high = round((price - high_52w) / high_52w * 100, 2)

            # Moving averages
            ma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
            ma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

            above_50 = price > ma_50 if ma_50 else None
            above_200 = price > ma_200 if ma_200 else None

            return MarketDataPoint(
                ticker=ticker, name=name, region=region,
                price=round(price, 4),
                prev_close=round(prev_close, 4) if prev_close else None,
                change_pct=change_pct,
                week_change_pct=week_change,
                month_change_pct=month_change,
                volume=vol,
                avg_volume=avg_vol,
                volume_ratio=vol_ratio,
                high_52w=round(high_52w, 4) if high_52w else None,
                low_52w=round(low_52w, 4) if low_52w else None,
                pct_from_52w_high=pct_from_high,
                ma_50d=round(ma_50, 4) if ma_50 else None,
                ma_200d=round(ma_200, 4) if ma_200 else None,
                above_50d=above_50,
                above_200d=above_200,
            )

        except Exception as e:
            return MarketDataPoint(ticker=ticker, name=name, region=region, error=str(e)[:200])

    def fetch_all(self) -> Dict[str, Any]:
        """
        Fetch all global market data. Returns a dict with:
        - indices: {asia: [...], europe: [...], americas: [...]}
        - forex: [...]
        - commodities: [...]
        - crypto: [...]
        - bonds: [...]
        - sessions: {asia: summary, europe: summary, americas: summary}
        - gaps: [gap signals]
        - global_breadth: overall % of indices positive
        - fetched_at: timestamp
        """
        _log("fetching global market data...")

        all_indices: Dict[str, List[MarketDataPoint]] = {}

        # Fetch indices by region
        for region, tickers in GLOBAL_TICKERS.items():
            region_data = []
            for ticker, meta in tickers.items():
                dp = self._fetch_one(ticker, meta["name"], region, period="1y")
                if meta.get("currency"):
                    dp.extra["currency"] = meta["currency"]
                if meta.get("country"):
                    dp.extra["country"] = meta["country"]
                region_data.append(dp)
                status = f"{dp.change_pct:+.2f}%" if dp.change_pct is not None else "ERR"
                _log(f"  {region}/{dp.name}: {status}")
            all_indices[region] = region_data

        # Fetch forex
        forex_data = []
        for ticker, meta in FOREX_TICKERS.items():
            dp = self._fetch_one(ticker, meta["name"], "forex", period="3mo")
            dp.extra["base"] = meta.get("base", "")
            dp.extra["quote"] = meta.get("quote", "")
            forex_data.append(dp)

        _log(f"  forex: {len(forex_data)} pairs fetched")

        # Fetch commodities
        commodity_data = []
        for ticker, meta in COMMODITY_TICKERS.items():
            dp = self._fetch_one(ticker, meta["name"], "commodities", period="3mo")
            dp.extra["unit"] = meta.get("unit", "")
            commodity_data.append(dp)

        _log(f"  commodities: {len(commodity_data)} fetched")

        # Fetch crypto
        crypto_data = []
        for ticker, meta in CRYPTO_TICKERS.items():
            dp = self._fetch_one(ticker, meta["name"], "crypto", period="3mo")
            crypto_data.append(dp)

        _log(f"  crypto: {len(crypto_data)} fetched")

        # Fetch bonds
        bond_data = []
        for ticker, meta in BOND_TICKERS.items():
            dp = self._fetch_one(ticker, meta["name"], "bonds", period="3mo")
            dp.extra["country"] = meta.get("country", "")
            bond_data.append(dp)

        _log(f"  bonds: {len(bond_data)} fetched")

        # Compute session summaries
        sessions = {}
        for region, data_points in all_indices.items():
            sessions[region] = self._compute_session_summary(region, data_points)

        # Compute gap signals
        gaps = self._compute_gaps(sessions)

        # Global breadth
        all_idx = []
        for region_data in all_indices.values():
            all_idx.extend(region_data)
        total_valid = sum(1 for d in all_idx if d.change_pct is not None)
        total_up = sum(1 for d in all_idx if d.change_pct is not None and d.change_pct > 0)
        global_breadth = round(total_up / total_valid * 100, 1) if total_valid > 0 else 0

        result = {
            "indices": {r: [d.to_dict() for d in pts] for r, pts in all_indices.items()},
            "forex": [d.to_dict() for d in forex_data],
            "commodities": [d.to_dict() for d in commodity_data],
            "crypto": [d.to_dict() for d in crypto_data],
            "bonds": [d.to_dict() for d in bond_data],
            "sessions": {k: v.to_dict() for k, v in sessions.items()},
            "gaps": [g.to_dict() for g in gaps],
            "global_breadth": global_breadth,
            "total_markets": len(all_idx),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        _log(f"done: {len(all_idx)} indices, breadth={global_breadth}%")
        return result

    def _compute_session_summary(self, session: str, data_points: List[MarketDataPoint]) -> SessionSummary:
        valid = [d for d in data_points if d.change_pct is not None]
        if not valid:
            return SessionSummary(
                session=session,
                label=SESSIONS.get(session, {}).get("label", session),
            )

        up = sum(1 for d in valid if d.change_pct > 0.1)
        down = sum(1 for d in valid if d.change_pct < -0.1)
        flat = len(valid) - up - down
        avg = round(sum(d.change_pct for d in valid) / len(valid), 2)

        strongest = max(valid, key=lambda d: d.change_pct)
        weakest = min(valid, key=lambda d: d.change_pct)

        breadth = round(up / len(valid) * 100, 1)

        return SessionSummary(
            session=session,
            label=SESSIONS.get(session, {}).get("label", session),
            markets_up=up,
            markets_down=down,
            markets_flat=flat,
            avg_change_pct=avg,
            strongest=strongest.name,
            strongest_pct=strongest.change_pct,
            weakest=weakest.name,
            weakest_pct=weakest.change_pct,
            breadth=breadth,
        )

    def _compute_gaps(self, sessions: Dict[str, SessionSummary]) -> List[GapSignal]:
        gaps = []
        pairs = [("asia", "europe"), ("europe", "americas"), ("asia", "americas")]

        for from_s, to_s in pairs:
            s1 = sessions.get(from_s)
            s2 = sessions.get(to_s)
            if not s1 or not s2:
                continue

            a = s1.avg_change_pct
            b = s2.avg_change_pct
            mag = round(abs(b - a), 2)
            divergent = (a > 0.1 and b < -0.1) or (a < -0.1 and b > 0.1)

            desc = ""
            if divergent:
                a_dir = "up" if a > 0 else "down"
                b_dir = "up" if b > 0 else "down"
                desc = f"{s1.label} {a_dir} ({a:+.2f}%) but {s2.label} {b_dir} ({b:+.2f}%): {mag:.2f}pp divergence"
            else:
                direction = "bullish" if a > 0 and b > 0 else "bearish" if a < 0 and b < 0 else "mixed"
                desc = f"{s1.label} ({a:+.2f}%) -> {s2.label} ({b:+.2f}%): {direction} continuation, {mag:.2f}pp gap"

            gaps.append(GapSignal(
                from_session=from_s,
                to_session=to_s,
                from_avg_change=a,
                to_avg_change=b,
                gap_magnitude=mag,
                divergent=divergent,
                description=desc,
            ))

        return gaps


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    collector = GlobalMarketCollector()
    result = collector.fetch_all()
    print(json.dumps(result, indent=2))
