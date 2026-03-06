"""
Circuit breaker for the trading bot.

Prevents catastrophic losses (Knight Capital style) by enforcing
hard limits on daily loss, hourly loss, trade frequency, and
position size. When triggered, all trading halts until cooldown
expires or manual reset.
"""

import json
import os
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] circuit_breaker: {msg}")


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker thresholds."""
    max_daily_loss_pct: float = 5.0
    max_hourly_loss_pct: float = 2.0
    max_trades_per_hour: int = 10
    max_position_size_usd: float = 500.0
    cooldown_minutes: int = 30


class CircuitBreaker:
    """
    Trading circuit breaker that prevents runaway losses.

    Tracks running P&L and trade counts, and halts trading when
    any threshold is breached. Automatically resets after the
    cooldown period or at midnight UTC (daily counters).

    Usage:
        from src.core.config import Config
        cfg = Config()
        cb = CircuitBreaker(cfg.project_root, initial_portfolio_value=10000)
        allowed, reason = cb.check_trade({"size_usd": 200, "market": "BTC"})
        if allowed:
            # execute trade ...
            cb.record_trade({"pnl": -15.50, "size_usd": 200})
        else:
            print(f"Trade blocked: {reason}")
    """

    def __init__(
        self,
        project_root: str,
        initial_portfolio_value: float = 10000.0,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        self.project_root = project_root
        self.data_dir = os.path.join(project_root, "data")
        self.state_file = os.path.join(self.data_dir, "circuit-breaker.json")
        os.makedirs(self.data_dir, exist_ok=True)

        self.cfg = config or CircuitBreakerConfig()
        self.portfolio_value = initial_portfolio_value

        # Running state
        self._daily_pnl: float = 0.0
        self._hourly_pnl: float = 0.0
        self._trade_timestamps: deque = deque()  # timestamps of trades in the last hour
        self._daily_trade_count: int = 0
        self._tripped: bool = False
        self._trip_reason: str = ""
        self._trip_time: Optional[datetime] = None
        self._last_reset_date: Optional[str] = None  # YYYY-MM-DD of last daily reset
        self._trade_log: List[Dict[str, Any]] = []

        self._lock = threading.Lock()

        # Load persisted state
        self._load_state()
        # Check if we need a daily reset
        self._check_daily_reset()

        _log(
            f"initialized: max_daily_loss={self.cfg.max_daily_loss_pct}%, "
            f"max_hourly_loss={self.cfg.max_hourly_loss_pct}%, "
            f"max_trades/hr={self.cfg.max_trades_per_hour}, "
            f"max_position=${self.cfg.max_position_size_usd}"
        )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _today_str(self) -> str:
        return self._now().strftime("%Y-%m-%d")

    def _check_daily_reset(self) -> None:
        """Auto-reset daily counters at midnight UTC."""
        today = self._today_str()
        if self._last_reset_date != today:
            _log(f"daily reset (previous: {self._last_reset_date}, now: {today})")
            self._daily_pnl = 0.0
            self._daily_trade_count = 0
            self._trade_log = []
            self._last_reset_date = today
            # Also clear trip if it was from a previous day
            if self._tripped and self._trip_time:
                trip_date = self._trip_time.strftime("%Y-%m-%d")
                if trip_date != today:
                    _log("clearing previous-day circuit breaker trip")
                    self._tripped = False
                    self._trip_reason = ""
                    self._trip_time = None
            self._save_state()

    def _prune_hourly_trades(self) -> None:
        """Remove trade timestamps older than 1 hour from the deque."""
        cutoff = self._now() - timedelta(hours=1)
        while self._trade_timestamps and self._trade_timestamps[0] < cutoff:
            self._trade_timestamps.popleft()

    def _compute_hourly_pnl(self) -> float:
        """Sum P&L from trades within the last hour."""
        cutoff = self._now() - timedelta(hours=1)
        total = 0.0
        for trade in self._trade_log:
            ts_str = trade.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts >= cutoff:
                    total += trade.get("pnl", 0.0)
            except (ValueError, TypeError):
                continue
        return total

    def check_trade(self, trade_details: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check whether a proposed trade is allowed.

        Args:
            trade_details: Dict with at least "size_usd" key.
                Optional: "market", "side", "price", "quantity".

        Returns:
            Tuple of (allowed: bool, reason: str).
            If allowed is False, reason explains why.
        """
        with self._lock:
            self._check_daily_reset()
            self._prune_hourly_trades()

            # Check if circuit breaker is tripped
            if self._tripped:
                # Check if cooldown has expired
                if self._trip_time:
                    elapsed = (self._now() - self._trip_time).total_seconds() / 60
                    if elapsed >= self.cfg.cooldown_minutes:
                        _log(f"cooldown expired after {elapsed:.0f} min, auto-resetting")
                        self._tripped = False
                        self._trip_reason = ""
                        self._trip_time = None
                    else:
                        remaining = self.cfg.cooldown_minutes - elapsed
                        return (
                            False,
                            f"Circuit breaker ACTIVE: {self._trip_reason}. "
                            f"Cooldown: {remaining:.0f} min remaining."
                        )

            size_usd = trade_details.get("size_usd", 0.0)

            # Check position size
            if size_usd > self.cfg.max_position_size_usd:
                reason = (
                    f"Position size ${size_usd:.2f} exceeds "
                    f"max ${self.cfg.max_position_size_usd:.2f}"
                )
                _log(f"BLOCKED: {reason}")
                return (False, reason)

            # Check trade count per hour
            trades_this_hour = len(self._trade_timestamps)
            if trades_this_hour >= self.cfg.max_trades_per_hour:
                reason = (
                    f"Trade count {trades_this_hour} exceeds "
                    f"max {self.cfg.max_trades_per_hour}/hour"
                )
                self._trigger(reason)
                return (False, reason)

            # Check daily loss
            if self.portfolio_value > 0:
                daily_loss_pct = abs(min(self._daily_pnl, 0.0)) / self.portfolio_value * 100
                if daily_loss_pct >= self.cfg.max_daily_loss_pct:
                    reason = (
                        f"Daily loss {daily_loss_pct:.2f}% exceeds "
                        f"max {self.cfg.max_daily_loss_pct}%"
                    )
                    self._trigger(reason)
                    return (False, reason)

            # Check hourly loss
            hourly_pnl = self._compute_hourly_pnl()
            if self.portfolio_value > 0:
                hourly_loss_pct = abs(min(hourly_pnl, 0.0)) / self.portfolio_value * 100
                if hourly_loss_pct >= self.cfg.max_hourly_loss_pct:
                    reason = (
                        f"Hourly loss {hourly_loss_pct:.2f}% exceeds "
                        f"max {self.cfg.max_hourly_loss_pct}%"
                    )
                    self._trigger(reason)
                    return (False, reason)

            return (True, "OK")

    def record_trade(self, trade_result: Dict[str, Any]) -> None:
        """
        Record a completed trade for P&L tracking.

        Args:
            trade_result: Dict with at least "pnl" key (float).
                Optional: "size_usd", "market", "timestamp".
        """
        with self._lock:
            pnl = trade_result.get("pnl", 0.0)
            now = self._now()

            self._daily_pnl += pnl
            self._daily_trade_count += 1
            self._trade_timestamps.append(now)

            record = {
                "pnl": pnl,
                "size_usd": trade_result.get("size_usd", 0.0),
                "market": trade_result.get("market", ""),
                "timestamp": trade_result.get("timestamp", now.isoformat()),
            }
            self._trade_log.append(record)

            _log(
                f"recorded trade: pnl=${pnl:+.2f}, "
                f"daily_pnl=${self._daily_pnl:+.2f}, "
                f"trades_today={self._daily_trade_count}"
            )

            # Re-check thresholds after recording
            if self.portfolio_value > 0:
                daily_loss_pct = abs(min(self._daily_pnl, 0.0)) / self.portfolio_value * 100
                if daily_loss_pct >= self.cfg.max_daily_loss_pct:
                    self._trigger(
                        f"Daily loss {daily_loss_pct:.2f}% hit limit "
                        f"after trade (max {self.cfg.max_daily_loss_pct}%)"
                    )

            self._save_state()

    def _trigger(self, reason: str) -> None:
        """Activate the circuit breaker."""
        self._tripped = True
        self._trip_reason = reason
        self._trip_time = self._now()
        _log(f"CIRCUIT BREAKER TRIGGERED: {reason}")
        self._save_state()

    def reset(self) -> str:
        """
        Manually reset the circuit breaker.

        Returns a status message.
        """
        with self._lock:
            was_tripped = self._tripped
            self._tripped = False
            self._trip_reason = ""
            self._trip_time = None
            self._save_state()
            msg = "Circuit breaker reset" if was_tripped else "Circuit breaker was not tripped"
            _log(msg)
            return msg

    def status(self) -> Dict[str, Any]:
        """Return the current circuit breaker state."""
        with self._lock:
            self._check_daily_reset()
            self._prune_hourly_trades()
            hourly_pnl = self._compute_hourly_pnl()

            daily_loss_pct = 0.0
            hourly_loss_pct = 0.0
            if self.portfolio_value > 0:
                daily_loss_pct = abs(min(self._daily_pnl, 0.0)) / self.portfolio_value * 100
                hourly_loss_pct = abs(min(hourly_pnl, 0.0)) / self.portfolio_value * 100

            cooldown_remaining = 0.0
            if self._tripped and self._trip_time:
                elapsed = (self._now() - self._trip_time).total_seconds() / 60
                cooldown_remaining = max(0.0, self.cfg.cooldown_minutes - elapsed)

            return {
                "tripped": self._tripped,
                "trip_reason": self._trip_reason,
                "trip_time": self._trip_time.isoformat() if self._trip_time else None,
                "cooldown_remaining_min": round(cooldown_remaining, 1),
                "daily_pnl": round(self._daily_pnl, 2),
                "daily_loss_pct": round(daily_loss_pct, 2),
                "max_daily_loss_pct": self.cfg.max_daily_loss_pct,
                "hourly_pnl": round(hourly_pnl, 2),
                "hourly_loss_pct": round(hourly_loss_pct, 2),
                "max_hourly_loss_pct": self.cfg.max_hourly_loss_pct,
                "trades_this_hour": len(self._trade_timestamps),
                "max_trades_per_hour": self.cfg.max_trades_per_hour,
                "daily_trade_count": self._daily_trade_count,
                "max_position_size_usd": self.cfg.max_position_size_usd,
                "portfolio_value": round(self.portfolio_value, 2),
                "timestamp": self._now().isoformat(),
            }

    def _save_state(self) -> None:
        """Persist circuit breaker state to disk."""
        try:
            state = {
                "tripped": self._tripped,
                "trip_reason": self._trip_reason,
                "trip_time": self._trip_time.isoformat() if self._trip_time else None,
                "daily_pnl": self._daily_pnl,
                "daily_trade_count": self._daily_trade_count,
                "last_reset_date": self._last_reset_date,
                "portfolio_value": self.portfolio_value,
                "trade_log": self._trade_log[-100:],  # keep last 100 trades
                "saved_at": self._now().isoformat(),
            }
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            _log(f"failed to save state: {e}")

    def _load_state(self) -> None:
        """Load circuit breaker state from disk."""
        if not os.path.isfile(self.state_file):
            return
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)

            self._tripped = state.get("tripped", False)
            self._trip_reason = state.get("trip_reason", "")
            trip_time_str = state.get("trip_time")
            if trip_time_str:
                self._trip_time = datetime.fromisoformat(trip_time_str)
            self._daily_pnl = state.get("daily_pnl", 0.0)
            self._daily_trade_count = state.get("daily_trade_count", 0)
            self._last_reset_date = state.get("last_reset_date")
            self.portfolio_value = state.get("portfolio_value", self.portfolio_value)
            self._trade_log = state.get("trade_log", [])

            _log(
                f"loaded state: tripped={self._tripped}, "
                f"daily_pnl=${self._daily_pnl:+.2f}, "
                f"trades_today={self._daily_trade_count}"
            )
        except Exception as e:
            _log(f"failed to load state: {e}")


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    cb = CircuitBreaker(root, initial_portfolio_value=10000)

    # Simulate some trades
    allowed, reason = cb.check_trade({"size_usd": 200})
    print(f"Trade 1: allowed={allowed}, reason={reason}")

    cb.record_trade({"pnl": -50, "size_usd": 200, "market": "test"})
    cb.record_trade({"pnl": -80, "size_usd": 300, "market": "test2"})

    print(json.dumps(cb.status(), indent=2))

    # Try a too-large trade
    allowed, reason = cb.check_trade({"size_usd": 600})
    print(f"Large trade: allowed={allowed}, reason={reason}")
