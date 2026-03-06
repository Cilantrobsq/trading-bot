"""
Thesis management for the trading bot.

Allows users to express structured market views (bullish/bearish/neutral)
with reasoning, catalysts, invalidation conditions, and time horizons.
Theses inform trading decisions and are tracked for P&L attribution.
"""

import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
THESES_DIR = os.path.join(BASE_DIR, "data", "theses")
THESES_FILE = os.path.join(THESES_DIR, "theses.json")


@dataclass
class Thesis:
    """A structured market thesis representing a directional view."""

    id: str
    title: str
    direction: str  # "bullish", "bearish", "neutral"
    confidence: int  # 0-100
    reasoning: str
    catalysts: List[str] = field(default_factory=list)
    invalidation_conditions: List[str] = field(default_factory=list)
    time_horizon: int = 30  # days
    affected_tickers: List[str] = field(default_factory=list)
    affected_themes: List[str] = field(default_factory=list)
    status: str = "active"  # active, invalidated, expired, realized
    created_at: str = ""
    updated_at: str = ""
    outcome: Optional[Dict[str, Any]] = None  # null until resolved

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Thesis":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def is_expired(self) -> bool:
        """Check if the thesis has exceeded its time horizon."""
        created = datetime.fromisoformat(self.created_at)
        elapsed = (datetime.now(timezone.utc) - created).days
        return elapsed > self.time_horizon


class ThesisManager:
    """
    Manages market theses: CRUD operations, persistence, and P&L tracking.

    Theses are persisted to data/theses/theses.json and can be used by
    the decision engine to weight signals and plan trades.
    """

    def __init__(self, theses_file: Optional[str] = None):
        self.theses_file = theses_file or THESES_FILE
        self.theses: Dict[str, Thesis] = {}
        os.makedirs(os.path.dirname(self.theses_file), exist_ok=True)
        self._load()

    def _load(self) -> None:
        """Load theses from disk."""
        if not os.path.isfile(self.theses_file):
            return
        try:
            with open(self.theses_file, "r") as f:
                data = json.load(f)
            for item in data:
                thesis = Thesis.from_dict(item)
                self.theses[thesis.id] = thesis
            logger.info("Loaded %d theses from %s", len(self.theses), self.theses_file)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load theses: %s", e)

    def _save(self) -> None:
        """Persist all theses to disk."""
        data = [t.to_dict() for t in self.theses.values()]
        with open(self.theses_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def create_thesis(
        self,
        title: str,
        direction: str,
        confidence: int,
        reasoning: str,
        catalysts: Optional[List[str]] = None,
        invalidation_conditions: Optional[List[str]] = None,
        time_horizon: int = 30,
        affected_tickers: Optional[List[str]] = None,
        affected_themes: Optional[List[str]] = None,
    ) -> Thesis:
        """Create a new thesis and persist it."""
        if direction not in ("bullish", "bearish", "neutral"):
            raise ValueError(f"Direction must be bullish/bearish/neutral, got '{direction}'")
        confidence = max(0, min(100, confidence))

        thesis = Thesis(
            id=str(uuid.uuid4())[:8],
            title=title,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            catalysts=catalysts or [],
            invalidation_conditions=invalidation_conditions or [],
            time_horizon=time_horizon,
            affected_tickers=affected_tickers or [],
            affected_themes=affected_themes or [],
        )
        self.theses[thesis.id] = thesis
        self._save()
        logger.info("Created thesis '%s' (id=%s, direction=%s)", title, thesis.id, direction)
        return thesis

    def update_thesis(self, thesis_id: str, updates: Dict[str, Any]) -> Thesis:
        """Update fields on an existing thesis."""
        if thesis_id not in self.theses:
            raise KeyError(f"Thesis not found: {thesis_id}")

        thesis = self.theses[thesis_id]
        allowed_fields = {
            "title", "direction", "confidence", "reasoning", "catalysts",
            "invalidation_conditions", "time_horizon", "affected_tickers",
            "affected_themes", "status",
        }
        for key, value in updates.items():
            if key in allowed_fields:
                setattr(thesis, key, value)

        if "direction" in updates and updates["direction"] not in ("bullish", "bearish", "neutral"):
            raise ValueError(f"Invalid direction: {updates['direction']}")
        if "confidence" in updates:
            thesis.confidence = max(0, min(100, thesis.confidence))

        thesis.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated thesis %s", thesis_id)
        return thesis

    def invalidate_thesis(self, thesis_id: str, reason: str = "") -> Thesis:
        """Mark a thesis as invalidated."""
        if thesis_id not in self.theses:
            raise KeyError(f"Thesis not found: {thesis_id}")

        thesis = self.theses[thesis_id]
        thesis.status = "invalidated"
        thesis.updated_at = datetime.now(timezone.utc).isoformat()
        thesis.outcome = {
            "status": "invalidated",
            "reason": reason,
            "invalidated_at": thesis.updated_at,
        }
        self._save()
        logger.info("Invalidated thesis %s: %s", thesis_id, reason)
        return thesis

    def resolve_thesis(
        self, thesis_id: str, realized: bool, pnl: float = 0.0, notes: str = ""
    ) -> Thesis:
        """
        Resolve a thesis as realized or expired, recording the outcome.

        Args:
            thesis_id: ID of the thesis to resolve.
            realized: True if the thesis played out as predicted.
            pnl: Approximate P&L from positions aligned with this thesis.
            notes: Free-text notes about the outcome.
        """
        if thesis_id not in self.theses:
            raise KeyError(f"Thesis not found: {thesis_id}")

        thesis = self.theses[thesis_id]
        thesis.status = "realized" if realized else "expired"
        thesis.updated_at = datetime.now(timezone.utc).isoformat()
        thesis.outcome = {
            "status": thesis.status,
            "realized": realized,
            "pnl": pnl,
            "notes": notes,
            "resolved_at": thesis.updated_at,
        }
        self._save()
        logger.info("Resolved thesis %s: realized=%s, pnl=%.2f", thesis_id, realized, pnl)
        return thesis

    def delete_thesis(self, thesis_id: str) -> None:
        """Remove a thesis entirely."""
        if thesis_id not in self.theses:
            raise KeyError(f"Thesis not found: {thesis_id}")
        del self.theses[thesis_id]
        self._save()
        logger.info("Deleted thesis %s", thesis_id)

    def get_thesis(self, thesis_id: str) -> Optional[Thesis]:
        """Get a single thesis by ID."""
        return self.theses.get(thesis_id)

    def get_all(self) -> List[Thesis]:
        """Return all theses."""
        return list(self.theses.values())

    def get_active(self) -> List[Thesis]:
        """Return only active theses."""
        return [t for t in self.theses.values() if t.status == "active"]

    def get_by_ticker(self, ticker: str) -> List[Thesis]:
        """Return active theses affecting a specific ticker."""
        ticker_upper = ticker.upper()
        return [
            t for t in self.get_active()
            if ticker_upper in [s.upper() for s in t.affected_tickers]
        ]

    def check_expirations(self) -> List[Thesis]:
        """Check for and mark expired theses. Returns list of newly expired."""
        expired = []
        for thesis in self.get_active():
            if thesis.is_expired():
                thesis.status = "expired"
                thesis.updated_at = datetime.now(timezone.utc).isoformat()
                thesis.outcome = {
                    "status": "expired",
                    "reason": "Time horizon exceeded",
                    "expired_at": thesis.updated_at,
                }
                expired.append(thesis)
                logger.info("Thesis '%s' expired (horizon: %d days)", thesis.title, thesis.time_horizon)
        if expired:
            self._save()
        return expired

    def decompose_natural_language(self, text: str) -> Dict[str, Any]:
        """
        Parse a natural language market view into structured thesis fields.

        Attempts to use Claude API if available; falls back to keyword extraction.

        Args:
            text: Free-form text like "I think tech stocks will rally because
                  the Fed is cutting rates. Watch AAPL and MSFT. If CPI comes
                  in hot, this thesis is dead."

        Returns:
            Dict with extracted thesis fields ready for create_thesis().
        """
        # Try Claude API first
        try:
            return self._decompose_with_claude(text)
        except Exception as e:
            logger.debug("Claude decomposition unavailable (%s), using keyword extraction", e)

        return self._decompose_keywords(text)

    def _decompose_with_claude(self, text: str) -> Dict[str, Any]:
        """Use Claude API to extract structured thesis from natural language."""
        import anthropic

        secrets_path = os.path.join(BASE_DIR, "secrets", "anthropic.json")
        if not os.path.isfile(secrets_path):
            raise FileNotFoundError("No anthropic.json secrets file")

        with open(secrets_path) as f:
            api_key = json.load(f).get("api_key", "")
        if not api_key:
            raise ValueError("No API key in anthropic.json")

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Extract a structured market thesis from this text. Return ONLY valid JSON with these fields:\n"
            '- title: short thesis title (string)\n'
            '- direction: "bullish", "bearish", or "neutral" (string)\n'
            '- confidence: 0-100 (integer)\n'
            '- reasoning: the core argument (string)\n'
            '- catalysts: list of catalyst events (list of strings)\n'
            '- invalidation_conditions: what would disprove this (list of strings)\n'
            '- time_horizon: in days (integer, default 30)\n'
            '- affected_tickers: stock/crypto tickers mentioned (list of strings, uppercase)\n'
            '- affected_themes: broad themes like "tech", "energy", "rates" (list of strings)\n\n'
            f"Text: {text}"
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if json_match:
            content = json_match.group(1)

        return json.loads(content.strip())

    def _decompose_keywords(self, text: str) -> Dict[str, Any]:
        """Simple keyword-based extraction as fallback."""
        text_lower = text.lower()

        # Direction detection
        bullish_words = ["bullish", "long", "buy", "rally", "up", "rise", "growth", "positive"]
        bearish_words = ["bearish", "short", "sell", "crash", "down", "fall", "decline", "negative"]
        bull_score = sum(1 for w in bullish_words if w in text_lower)
        bear_score = sum(1 for w in bearish_words if w in text_lower)

        if bull_score > bear_score:
            direction = "bullish"
        elif bear_score > bull_score:
            direction = "bearish"
        else:
            direction = "neutral"

        # Ticker extraction (uppercase 1-5 letter words that look like tickers)
        ticker_pattern = r'\b([A-Z]{1,5})\b'
        common_words = {
            "I", "A", "THE", "AND", "OR", "IF", "FOR", "IN", "ON", "AT",
            "TO", "IS", "IT", "BY", "AS", "OF", "AN", "BE", "DO", "SO",
            "UP", "NO", "NOT", "BUT", "ALL", "CAN", "HAD", "HAS", "HER",
            "HIS", "HOW", "ITS", "MAY", "NEW", "NOW", "OLD", "OUR", "OUT",
            "OWN", "SAY", "SHE", "TOO", "USE", "WAY", "WHO", "BOY", "DID",
            "GET", "LET", "PUT", "RUN", "TOP", "YES", "YET", "CPI", "GDP",
            "FED", "IMO", "WILL", "WHEN", "WITH", "THAT", "THIS", "FROM",
            "HAVE", "WHAT", "BEEN", "THEY", "THAN", "EACH", "MAKE", "LIKE",
            "LONG", "LOOK", "MANY", "SOME", "THEN", "THEM", "VERY", "ALSO",
            "BACK", "MUCH", "BECAUSE", "THINK", "WATCH",
        }
        potential_tickers = re.findall(ticker_pattern, text)
        tickers = [t for t in potential_tickers if t not in common_words and len(t) >= 2]

        # Confidence (default moderate)
        confidence = 50
        high_conf = ["certain", "confident", "strong", "convinced", "definitely"]
        low_conf = ["maybe", "might", "possibly", "uncertain", "unsure", "risky"]
        if any(w in text_lower for w in high_conf):
            confidence = 75
        elif any(w in text_lower for w in low_conf):
            confidence = 30

        # Time horizon
        time_horizon = 30
        day_match = re.search(r'(\d+)\s*days?', text_lower)
        week_match = re.search(r'(\d+)\s*weeks?', text_lower)
        month_match = re.search(r'(\d+)\s*months?', text_lower)
        if day_match:
            time_horizon = int(day_match.group(1))
        elif week_match:
            time_horizon = int(week_match.group(1)) * 7
        elif month_match:
            time_horizon = int(month_match.group(1)) * 30

        # Title: first sentence or first 60 chars
        title = text.split(".")[0].strip()
        if len(title) > 60:
            title = title[:57] + "..."

        return {
            "title": title,
            "direction": direction,
            "confidence": confidence,
            "reasoning": text,
            "catalysts": [],
            "invalidation_conditions": [],
            "time_horizon": time_horizon,
            "affected_tickers": tickers,
            "affected_themes": [],
        }
