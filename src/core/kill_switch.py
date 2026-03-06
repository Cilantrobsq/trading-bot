"""
Kill switch for the trading bot.

Simple mechanism to halt all trade execution. When active, no new trades
are placed and existing positions get tightened stop-losses. Can be
toggled from the dashboard API or programmatically.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KILL_SWITCH_FILE = os.path.join(BASE_DIR, "data", "kill-switch.json")


class KillSwitch:
    """
    Emergency kill switch for the trading bot.

    When activated:
    - All new trade execution is blocked
    - Existing positions should have stop-losses tightened
    - The bot continues to monitor signals but takes no action

    State is persisted to data/kill-switch.json.

    Usage:
        ks = KillSwitch()
        ks.activate("Market crash detected")
        if ks.is_active():
            # block all trades
            pass
        ks.deactivate()
    """

    def __init__(self, state_file: Optional[str] = None):
        self.state_file = state_file or KILL_SWITCH_FILE
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load kill switch state from disk."""
        if not os.path.isfile(self.state_file):
            return {
                "active": False,
                "reason": "",
                "activated_at": None,
                "activated_by": None,
                "deactivated_at": None,
                "history": [],
            }
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {
                "active": False,
                "reason": "",
                "activated_at": None,
                "activated_by": None,
                "deactivated_at": None,
                "history": [],
            }

    def _save(self) -> None:
        """Persist kill switch state to disk."""
        with open(self.state_file, "w") as f:
            json.dump(self._state, f, indent=2, default=str)

    def activate(self, reason: str = "Manual activation", activated_by: str = "user") -> None:
        """
        Activate the kill switch, blocking all trade execution.

        Args:
            reason: Why the kill switch was activated.
            activated_by: Who or what triggered it (user, circuit_breaker, etc).
        """
        now = datetime.now(timezone.utc).isoformat()
        self._state["active"] = True
        self._state["reason"] = reason
        self._state["activated_at"] = now
        self._state["activated_by"] = activated_by
        self._state["deactivated_at"] = None

        # Append to history
        history = self._state.get("history", [])
        history.append({
            "action": "activate",
            "reason": reason,
            "by": activated_by,
            "timestamp": now,
        })
        # Keep last 50 entries
        self._state["history"] = history[-50:]

        self._save()
        logger.warning("KILL SWITCH ACTIVATED: %s (by %s)", reason, activated_by)

    def deactivate(self, deactivated_by: str = "user") -> None:
        """Deactivate the kill switch, resuming normal trading."""
        now = datetime.now(timezone.utc).isoformat()
        was_active = self._state.get("active", False)
        self._state["active"] = False
        self._state["deactivated_at"] = now

        if was_active:
            history = self._state.get("history", [])
            history.append({
                "action": "deactivate",
                "reason": f"Deactivated by {deactivated_by}",
                "by": deactivated_by,
                "timestamp": now,
            })
            self._state["history"] = history[-50:]

        self._save()
        logger.info("Kill switch deactivated by %s", deactivated_by)

    def is_active(self) -> bool:
        """Check if the kill switch is currently active."""
        return self._state.get("active", False)

    def status(self) -> Dict[str, Any]:
        """Return the full kill switch status."""
        return {
            "active": self._state.get("active", False),
            "reason": self._state.get("reason", ""),
            "activated_at": self._state.get("activated_at"),
            "activated_by": self._state.get("activated_by"),
            "deactivated_at": self._state.get("deactivated_at"),
            "history_count": len(self._state.get("history", [])),
        }

    def get_history(self, limit: int = 20) -> list:
        """Return recent kill switch history entries."""
        history = self._state.get("history", [])
        return list(reversed(history[-limit:]))
