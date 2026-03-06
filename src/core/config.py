"""
Configuration loader for the trading bot.

Reads strategy.json and themes.json from the config directory,
validates required fields, and provides typed access to all settings.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _log(msg: str) -> None:
    """Print a timestamped log message to stdout."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] config: {msg}")


@dataclass
class RiskManagement:
    max_position_size_pct: float
    max_per_market_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    max_single_theme_exposure_pct: float = 40.0
    max_per_event_category_pct: float = 15.0
    min_spread_after_fees_pct: float = 1.5
    kelly_fraction: float = 0.25


@dataclass
class PolymarketConfig:
    enabled: bool
    api_base: str
    data_api: str
    chain: str
    fee_note: str


@dataclass
class PaperTradingConfig:
    enabled: bool
    initial_balance_usd: float
    note: str = ""


@dataclass
class MacroIndicator:
    id: str
    name: str
    threshold_alert: Optional[float] = None


@dataclass
class Theme:
    id: str
    name: str
    status: str
    description: str
    macro_signals: List[Dict[str, Any]] = field(default_factory=list)
    equities: Dict[str, Any] = field(default_factory=dict)
    signal_logic: Dict[str, Any] = field(default_factory=dict)
    data_sources: List[str] = field(default_factory=list)
    regulation_watch: Dict[str, Any] = field(default_factory=dict)


class Config:
    """
    Central configuration object for the trading bot.

    Loads strategy.json and themes.json from a config directory,
    parses them into typed dataclass instances, and exposes them
    as attributes.

    Usage:
        cfg = Config("/path/to/trading-bot")
        print(cfg.risk.max_position_size_pct)
        print(cfg.themes[0].name)
        print(cfg.yfinance_tickers)
    """

    def __init__(self, project_root: Optional[str] = None):
        if project_root is None:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
        self.project_root = project_root
        self.config_dir = os.path.join(project_root, "config")

        self._raw_strategy: Dict[str, Any] = {}
        self._raw_themes: Dict[str, Any] = {}

        self._load_strategy()
        self._load_themes()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_json(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.config_dir, filename)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r") as f:
            data = json.load(f)
        _log(f"loaded {filename} ({len(data)} top-level keys)")
        return data

    def _load_strategy(self) -> None:
        self._raw_strategy = self._load_json("strategy.json")
        s = self._raw_strategy

        # Risk management
        rm = s.get("risk_management", {})
        self.risk = RiskManagement(
            max_position_size_pct=rm["max_position_size_pct"],
            max_per_market_pct=rm["max_per_market_pct"],
            stop_loss_pct=rm["stop_loss_pct"],
            take_profit_pct=rm["take_profit_pct"],
            max_single_theme_exposure_pct=rm.get("max_single_theme_exposure_pct", 40.0),
            max_per_event_category_pct=rm.get("max_per_event_category_pct", 15.0),
            min_spread_after_fees_pct=rm.get("min_spread_after_fees_pct", 1.5),
            kelly_fraction=rm.get("kelly_fraction", 0.25),
        )

        # Polymarket
        pm = s.get("polymarket", {})
        self.polymarket = PolymarketConfig(
            enabled=pm.get("enabled", False),
            api_base=pm.get("api_base", "https://clob.polymarket.com"),
            data_api=pm.get("data_api", "https://data-api.polymarket.com"),
            chain=pm.get("chain", "polygon"),
            fee_note=pm.get("fee_note", ""),
        )

        # Paper trading
        pt = s.get("paper_trading", {})
        self.paper_trading = PaperTradingConfig(
            enabled=pt.get("enabled", True),
            initial_balance_usd=pt.get("initial_balance_usd", 10000),
            note=pt.get("note", ""),
        )

        # Macro indicators
        mi = s.get("macro_signals", {})
        self.macro_signals_enabled = mi.get("enabled", False)
        self.macro_indicators: List[MacroIndicator] = []
        for ind in mi.get("indicators", []):
            self.macro_indicators.append(MacroIndicator(
                id=ind["id"],
                name=ind["name"],
                threshold_alert=ind.get("threshold_alert"),
            ))

        # Data sources (filter out __comment__ entries used for readability)
        ds = s.get("data_sources", {})
        self.yfinance_tickers: List[str] = [
            t for t in ds.get("yfinance_tickers", [])
            if not t.startswith("__comment")
        ]
        self.news_feeds: List[str] = [
            f for f in ds.get("news_feeds", [])
            if not f.startswith("__comment")
        ]

    def _load_themes(self) -> None:
        self._raw_themes = self._load_json("themes.json")
        self.themes: List[Theme] = []
        for t in self._raw_themes.get("themes", []):
            self.themes.append(Theme(
                id=t["id"],
                name=t["name"],
                status=t.get("status", "inactive"),
                description=t.get("description", ""),
                macro_signals=t.get("macro_signals", []),
                equities=t.get("equities", {}),
                signal_logic=t.get("signal_logic", {}),
                data_sources=t.get("data_sources", []),
                regulation_watch=t.get("regulation_watch", {}),
            ))
        _log(f"loaded {len(self.themes)} themes")

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def active_themes(self) -> List[Theme]:
        """Return only themes with status 'active'."""
        return [t for t in self.themes if t.status == "active"]

    def theme_by_id(self, theme_id: str) -> Optional[Theme]:
        """Look up a theme by its id string."""
        for t in self.themes:
            if t.id == theme_id:
                return t
        return None

    def all_theme_tickers(self) -> List[str]:
        """Collect every ticker mentioned across all active themes."""
        tickers = set()
        for theme in self.active_themes():
            for sig in theme.macro_signals:
                if "ticker" in sig:
                    tickers.add(sig["ticker"])
            for category_list in theme.equities.values():
                if isinstance(category_list, list):
                    for item in category_list:
                        if isinstance(item, dict) and "ticker" in item:
                            tickers.add(item["ticker"])
        return sorted(tickers)

    def secrets_path(self, filename: str) -> str:
        """Return the absolute path to a file in the secrets directory."""
        return os.path.join(self.project_root, "secrets", filename)

    def data_path(self, *parts: str) -> str:
        """Return the absolute path under the data directory."""
        return os.path.join(self.project_root, "data", *parts)

    def __repr__(self) -> str:
        return (
            f"Config(themes={len(self.themes)}, "
            f"tickers={len(self.yfinance_tickers)}, "
            f"feeds={len(self.news_feeds)}, "
            f"paper={self.paper_trading.enabled})"
        )


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    print(cfg)
    print(f"  Risk: stop_loss={cfg.risk.stop_loss_pct}%, take_profit={cfg.risk.take_profit_pct}%")
    print(f"  Active themes: {[t.name for t in cfg.active_themes()]}")
    print(f"  yfinance tickers: {cfg.yfinance_tickers}")
    print(f"  All theme tickers: {cfg.all_theme_tickers()}")
