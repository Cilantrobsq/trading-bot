"""
Decision logging for the trading bot.

Records every decision the bot makes (signal evaluations, position sizing,
trades, risk checks, overrides) to an append-only JSONL file with daily
rotation. Provides query methods for the dashboard and post-hoc analysis.
"""

import json
import logging
import os
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DECISIONS_DIR = os.path.join(BASE_DIR, "data", "decisions")

VALID_DECISION_TYPES = {
    "signal_eval", "position_size", "trade", "risk_check", "override", "thesis_update",
}


@dataclass
class DecisionEntry:
    """A single logged decision."""

    id: str
    timestamp: str
    decision_type: str  # signal_eval, position_size, trade, risk_check, override, thesis_update
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    confidence: int = 0  # 0-100
    action_taken: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DecisionEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_json_line(self) -> str:
        """Serialize to a single JSON line for JSONL format."""
        return json.dumps(self.to_dict(), default=str)


class DecisionLog:
    """
    Append-only decision log with daily file rotation.

    Writes to data/decisions/decisions-YYYY-MM-DD.jsonl, one JSON object
    per line. Provides query methods for retrieving recent decisions,
    filtering by type, and generating daily summaries.

    Usage:
        log = DecisionLog()
        log.log_decision(
            decision_type="signal_eval",
            input_data={"ticker": "BTC", "signal": "momentum"},
            output_data={"score": 0.72},
            reasoning="Strong uptrend confirmed by 20-day MA crossover",
            confidence=75,
            action_taken="signal_passed",
        )
        recent = log.get_recent(10)
        summary = log.daily_summary()
    """

    def __init__(self, decisions_dir: Optional[str] = None):
        self.decisions_dir = decisions_dir or DECISIONS_DIR
        os.makedirs(self.decisions_dir, exist_ok=True)

    def _current_file(self) -> str:
        """Get the path for today's decision log file."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.decisions_dir, f"decisions-{date_str}.jsonl")

    def _all_files(self) -> List[str]:
        """Get all decision log files sorted by date (newest first)."""
        if not os.path.isdir(self.decisions_dir):
            return []
        files = [
            os.path.join(self.decisions_dir, f)
            for f in os.listdir(self.decisions_dir)
            if f.startswith("decisions-") and f.endswith(".jsonl")
        ]
        return sorted(files, reverse=True)

    def log_decision(
        self,
        decision_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        reasoning: str = "",
        confidence: int = 0,
        action_taken: Optional[str] = None,
    ) -> DecisionEntry:
        """
        Log a decision to the current day's JSONL file.

        Args:
            decision_type: One of signal_eval, position_size, trade,
                          risk_check, override, thesis_update.
            input_data: What went into the decision.
            output_data: What came out.
            reasoning: Human-readable explanation.
            confidence: 0-100 confidence score.
            action_taken: What action was actually taken (or null).

        Returns:
            The created DecisionEntry.
        """
        if decision_type not in VALID_DECISION_TYPES:
            logger.warning("Unknown decision type '%s', logging anyway", decision_type)

        entry = DecisionEntry(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision_type=decision_type,
            input_data=input_data or {},
            output_data=output_data or {},
            reasoning=reasoning,
            confidence=max(0, min(100, confidence)),
            action_taken=action_taken,
        )

        filepath = self._current_file()
        with open(filepath, "a") as f:
            f.write(entry.to_json_line() + "\n")

        logger.debug("Logged %s decision: %s", decision_type, entry.id)
        return entry

    def _read_file(self, filepath: str) -> List[DecisionEntry]:
        """Read all entries from a JSONL file."""
        entries = []
        try:
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(DecisionEntry.from_dict(data))
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning("Skipping malformed line in %s: %s", filepath, e)
        except FileNotFoundError:
            pass
        return entries

    def get_recent(self, n: int = 50) -> List[DecisionEntry]:
        """Get the N most recent decisions across all log files."""
        entries: List[DecisionEntry] = []
        for filepath in self._all_files():
            entries.extend(self._read_file(filepath))
            if len(entries) >= n:
                break
        # Sort by timestamp descending, take N
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:n]

    def get_by_type(self, decision_type: str, limit: int = 100) -> List[DecisionEntry]:
        """Get recent decisions of a specific type."""
        all_entries = self.get_recent(limit * 3)  # over-fetch to filter
        filtered = [e for e in all_entries if e.decision_type == decision_type]
        return filtered[:limit]

    def get_by_timerange(
        self, since: str, until: Optional[str] = None
    ) -> List[DecisionEntry]:
        """
        Get decisions within a time range.

        Args:
            since: ISO timestamp for the start of the range.
            until: ISO timestamp for the end (default: now).
        """
        if until is None:
            until = datetime.now(timezone.utc).isoformat()

        entries: List[DecisionEntry] = []
        for filepath in self._all_files():
            file_entries = self._read_file(filepath)
            for entry in file_entries:
                if since <= entry.timestamp <= until:
                    entries.append(entry)
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    def get_today(self) -> List[DecisionEntry]:
        """Get all decisions from today."""
        filepath = self._current_file()
        entries = self._read_file(filepath)
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    def daily_summary(self) -> Dict[str, Any]:
        """
        Aggregate today's decisions into a summary.

        Returns counts by type, average confidence, and actions taken.
        """
        entries = self.get_today()
        if not entries:
            return {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "total_decisions": 0,
                "by_type": {},
                "avg_confidence": 0,
                "actions_taken": [],
            }

        type_counts = Counter(e.decision_type for e in entries)
        confidences = [e.confidence for e in entries if e.confidence > 0]
        actions = [e.action_taken for e in entries if e.action_taken]

        return {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "total_decisions": len(entries),
            "by_type": dict(type_counts),
            "avg_confidence": round(sum(confidences) / len(confidences), 1) if confidences else 0,
            "actions_taken": actions,
            "first_decision": entries[-1].timestamp if entries else None,
            "last_decision": entries[0].timestamp if entries else None,
        }
