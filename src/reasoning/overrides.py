"""
Signal override system for the trading bot.

Allows users to manually boost, suppress, or invert signal scores
before they reach the decision engine. Useful for expressing short-term
views that haven't been formalized into a full thesis.
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OVERRIDES_FILE = os.path.join(BASE_DIR, "data", "overrides.json")


@dataclass
class SignalOverride:
    """
    A manual override applied to signal scores.

    Override types:
    - boost: multiply signal score by strength (>1.0 amplifies)
    - suppress: multiply signal score by strength (<1.0 reduces)
    - invert: flip the signal direction (bullish -> bearish and vice versa)
    """

    id: str
    signal_type: str  # e.g. "macro", "sentiment", "volatility", "momentum"
    ticker_or_market: str  # specific ticker, "*" for all
    override_type: str  # "boost", "suppress", "invert"
    strength: float  # 0.0 to 2.0 (multiplier)
    reason: str
    created_by: str = "user"
    active: bool = True
    created_at: str = ""
    expires_at: Optional[str] = None  # ISO timestamp or null for no expiry

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SignalOverride":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def is_expired(self) -> bool:
        """Check if this override has passed its expiry time."""
        if self.expires_at is None:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expiry
        except (ValueError, TypeError):
            return False

    def applies_to(self, signal_type: str, ticker: str) -> bool:
        """Check if this override applies to a given signal type and ticker."""
        if not self.active or self.is_expired():
            return False
        type_match = self.signal_type == "*" or self.signal_type.lower() == signal_type.lower()
        ticker_match = self.ticker_or_market == "*" or self.ticker_or_market.upper() == ticker.upper()
        return type_match and ticker_match


class OverrideManager:
    """
    Manages signal overrides: creation, removal, and application to scores.

    Overrides are persisted to data/overrides.json and applied as multipliers
    to signal scores before they reach the decision engine.

    Usage:
        mgr = OverrideManager()
        mgr.create_override("volatility", "VIX", "suppress", 0.3,
                           "VIX is overreacting to noise")
        adjusted_score = mgr.apply("volatility", "VIX", original_score=-0.8)
    """

    def __init__(self, overrides_file: Optional[str] = None):
        self.overrides_file = overrides_file or OVERRIDES_FILE
        self.overrides: Dict[str, SignalOverride] = {}
        os.makedirs(os.path.dirname(self.overrides_file), exist_ok=True)
        self._load()

    def _load(self) -> None:
        """Load overrides from disk."""
        if not os.path.isfile(self.overrides_file):
            return
        try:
            with open(self.overrides_file, "r") as f:
                data = json.load(f)
            for item in data:
                override = SignalOverride.from_dict(item)
                self.overrides[override.id] = override
            logger.info("Loaded %d overrides from %s", len(self.overrides), self.overrides_file)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load overrides: %s", e)

    def _save(self) -> None:
        """Persist all overrides to disk."""
        data = [o.to_dict() for o in self.overrides.values()]
        with open(self.overrides_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def create_override(
        self,
        signal_type: str,
        ticker_or_market: str,
        override_type: str,
        strength: float,
        reason: str,
        created_by: str = "user",
        expires_at: Optional[str] = None,
    ) -> SignalOverride:
        """Create a new signal override."""
        if override_type not in ("boost", "suppress", "invert"):
            raise ValueError(f"Override type must be boost/suppress/invert, got '{override_type}'")
        strength = max(0.0, min(2.0, strength))

        override = SignalOverride(
            id=str(uuid.uuid4())[:8],
            signal_type=signal_type,
            ticker_or_market=ticker_or_market,
            override_type=override_type,
            strength=strength,
            reason=reason,
            created_by=created_by,
            expires_at=expires_at,
        )
        self.overrides[override.id] = override
        self._save()
        logger.info(
            "Created override: %s %s signals for %s (strength=%.2f)",
            override_type, signal_type, ticker_or_market, strength,
        )
        return override

    def remove_override(self, override_id: str) -> None:
        """Remove an override by ID."""
        if override_id not in self.overrides:
            raise KeyError(f"Override not found: {override_id}")
        del self.overrides[override_id]
        self._save()
        logger.info("Removed override %s", override_id)

    def deactivate_override(self, override_id: str) -> SignalOverride:
        """Deactivate an override without deleting it."""
        if override_id not in self.overrides:
            raise KeyError(f"Override not found: {override_id}")
        self.overrides[override_id].active = False
        self._save()
        return self.overrides[override_id]

    def get_active(self) -> List[SignalOverride]:
        """Return all active, non-expired overrides."""
        self._cleanup_expired()
        return [o for o in self.overrides.values() if o.active and not o.is_expired()]

    def get_all(self) -> List[SignalOverride]:
        """Return all overrides including inactive."""
        return list(self.overrides.values())

    def _cleanup_expired(self) -> None:
        """Mark expired overrides as inactive."""
        changed = False
        for override in self.overrides.values():
            if override.active and override.is_expired():
                override.active = False
                changed = True
                logger.info("Override %s expired and deactivated", override.id)
        if changed:
            self._save()

    def apply(self, signal_type: str, ticker: str, score: float) -> float:
        """
        Apply all matching overrides to a signal score.

        Args:
            signal_type: Type of signal (e.g. "macro", "sentiment").
            ticker: Ticker or market identifier.
            score: Original signal score.

        Returns:
            Adjusted score after applying all matching overrides.
        """
        adjusted = score
        for override in self.get_active():
            if not override.applies_to(signal_type, ticker):
                continue

            if override.override_type == "boost":
                adjusted *= override.strength
            elif override.override_type == "suppress":
                adjusted *= override.strength
            elif override.override_type == "invert":
                adjusted *= -1.0 * override.strength

            logger.debug(
                "Applied override %s (%s) to %s/%s: %.4f -> %.4f",
                override.id, override.override_type, signal_type, ticker, score, adjusted,
            )

        return adjusted

    def get_overrides_for(self, signal_type: str, ticker: str) -> List[SignalOverride]:
        """Get all active overrides that apply to a specific signal/ticker pair."""
        return [o for o in self.get_active() if o.applies_to(signal_type, ticker)]
