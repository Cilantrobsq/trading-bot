"""
Portfolio manager for the trading bot.

Tracks positions, calculates exposure, and enforces risk limits
defined in strategy.json (max_position_size_pct, max_per_market_pct,
stop_loss, take_profit).
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.config import Config, RiskManagement


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] portfolio: {msg}")


@dataclass
class Position:
    """A single open position."""
    market_id: str
    market_name: str
    side: str              # "YES" or "NO"
    entry_price: float     # price per share (0.00 - 1.00)
    quantity: float        # number of shares
    entry_time: str        # ISO timestamp
    theme_id: str = ""     # which theme this belongs to
    current_price: float = 0.0
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0

    @property
    def cost_basis(self) -> float:
        """Total USD invested in this position."""
        return self.entry_price * self.quantity

    @property
    def current_value(self) -> float:
        """Current market value based on current_price."""
        return self.current_price * self.quantity

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss in USD."""
        return self.current_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as a percentage of cost basis."""
        if self.cost_basis == 0:
            return 0.0
        return (self.unrealized_pnl / self.cost_basis) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_id": self.market_id,
            "market_name": self.market_name,
            "side": self.side,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "entry_time": self.entry_time,
            "theme_id": self.theme_id,
            "current_price": self.current_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Position":
        return cls(**d)


class RiskViolation(Exception):
    """Raised when a proposed trade would violate risk limits."""
    pass


class Portfolio:
    """
    Manages open positions and enforces risk limits.

    The portfolio tracks:
    - Open positions by market
    - Cash balance
    - Total exposure and per-theme exposure
    - Stop-loss and take-profit triggers

    Usage:
        cfg = Config()
        port = Portfolio(cfg)
        port.open_position("market-abc", "BTC > 100K", "YES", 0.65, 100, "theme-housing-bonds-war")
        port.update_price("market-abc", 0.72)
        triggers = port.check_triggers()
    """

    def __init__(self, config: Config, initial_balance: Optional[float] = None):
        self.config = config
        self.risk: RiskManagement = config.risk
        self.balance: float = initial_balance or config.paper_trading.initial_balance_usd
        self.initial_balance: float = self.balance
        self.positions: Dict[str, Position] = {}  # market_id -> Position
        self.closed_trades: List[Dict[str, Any]] = []
        _log(f"initialized with balance=${self.balance:,.2f}")

    # ------------------------------------------------------------------
    # Exposure calculations
    # ------------------------------------------------------------------

    def total_invested(self) -> float:
        """Sum of cost basis across all open positions."""
        return sum(p.cost_basis for p in self.positions.values())

    def total_portfolio_value(self) -> float:
        """Cash + current value of all positions."""
        return self.balance + sum(p.current_value for p in self.positions.values())

    def exposure_pct(self) -> float:
        """Total invested as percentage of portfolio value."""
        tv = self.total_portfolio_value()
        if tv == 0:
            return 0.0
        return (self.total_invested() / tv) * 100

    def market_exposure_pct(self, market_id: str) -> float:
        """Single market cost basis as percentage of portfolio value."""
        tv = self.total_portfolio_value()
        if tv == 0:
            return 0.0
        pos = self.positions.get(market_id)
        if pos is None:
            return 0.0
        return (pos.cost_basis / tv) * 100

    def theme_exposure_pct(self, theme_id: str) -> float:
        """Total cost basis for a theme as percentage of portfolio value."""
        tv = self.total_portfolio_value()
        if tv == 0:
            return 0.0
        theme_cost = sum(
            p.cost_basis for p in self.positions.values()
            if p.theme_id == theme_id
        )
        return (theme_cost / tv) * 100

    def total_unrealized_pnl(self) -> float:
        """Sum of unrealized P&L across all positions."""
        return sum(p.unrealized_pnl for p in self.positions.values())

    def total_realized_pnl(self) -> float:
        """Sum of realized P&L from closed trades."""
        return sum(t.get("realized_pnl", 0.0) for t in self.closed_trades)

    # ------------------------------------------------------------------
    # Risk checks
    # ------------------------------------------------------------------

    def check_position_allowed(
        self, market_id: str, cost: float, theme_id: str = ""
    ) -> None:
        """
        Validate that a proposed trade does not violate risk limits.
        Raises RiskViolation if any limit would be breached.
        """
        tv = self.total_portfolio_value()
        if tv <= 0:
            raise RiskViolation("Portfolio value is zero or negative")

        # Check cash availability
        if cost > self.balance:
            raise RiskViolation(
                f"Insufficient cash: need ${cost:.2f}, have ${self.balance:.2f}"
            )

        # Max position size (overall)
        new_invested = self.total_invested() + cost
        new_exposure_pct = (new_invested / tv) * 100
        # Individual position size check not relevant for total, but enforce
        # max_position_size_pct per individual position
        position_pct = (cost / tv) * 100
        existing = self.positions.get(market_id)
        if existing:
            position_pct = ((existing.cost_basis + cost) / tv) * 100

        if position_pct > self.risk.max_position_size_pct:
            raise RiskViolation(
                f"Position would be {position_pct:.1f}% of portfolio, "
                f"limit is {self.risk.max_position_size_pct}%"
            )

        # Max per market
        market_pct = position_pct  # same as above for single-market check
        if market_pct > self.risk.max_per_market_pct:
            raise RiskViolation(
                f"Market exposure would be {market_pct:.1f}%, "
                f"limit is {self.risk.max_per_market_pct}%"
            )

        # Max per theme
        if theme_id:
            theme_cost = sum(
                p.cost_basis for p in self.positions.values()
                if p.theme_id == theme_id
            )
            theme_pct = ((theme_cost + cost) / tv) * 100
            if theme_pct > self.risk.max_single_theme_exposure_pct:
                raise RiskViolation(
                    f"Theme '{theme_id}' exposure would be {theme_pct:.1f}%, "
                    f"limit is {self.risk.max_single_theme_exposure_pct}%"
                )

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def open_position(
        self,
        market_id: str,
        market_name: str,
        side: str,
        price: float,
        quantity: float,
        theme_id: str = "",
    ) -> Position:
        """
        Open a new position (or add to an existing one).

        Args:
            market_id: Unique identifier for the market.
            market_name: Human-readable market name.
            side: "YES" or "NO".
            price: Price per share (0.00 to 1.00).
            quantity: Number of shares to buy.
            theme_id: Optional theme this trade belongs to.

        Returns:
            The created/updated Position.

        Raises:
            RiskViolation: If the trade would violate risk limits.
            ValueError: If parameters are invalid.
        """
        if side not in ("YES", "NO"):
            raise ValueError(f"Side must be 'YES' or 'NO', got '{side}'")
        if price <= 0 or price >= 1:
            raise ValueError(f"Price must be between 0 and 1, got {price}")
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")

        cost = price * quantity
        self.check_position_allowed(market_id, cost, theme_id)

        now = datetime.now(timezone.utc).isoformat()

        if market_id in self.positions:
            # Average into existing position
            existing = self.positions[market_id]
            total_cost = existing.cost_basis + cost
            total_qty = existing.quantity + quantity
            existing.entry_price = total_cost / total_qty
            existing.quantity = total_qty
            existing.current_price = price
            pos = existing
            _log(f"added to position {market_name}: +{quantity} @ ${price:.4f}")
        else:
            # Calculate stop-loss and take-profit prices
            stop_loss_price = price * (1 - self.risk.stop_loss_pct / 100)
            take_profit_price = price * (1 + self.risk.take_profit_pct / 100)
            # Clamp to valid range
            take_profit_price = min(take_profit_price, 0.99)
            stop_loss_price = max(stop_loss_price, 0.01)

            pos = Position(
                market_id=market_id,
                market_name=market_name,
                side=side,
                entry_price=price,
                quantity=quantity,
                entry_time=now,
                theme_id=theme_id,
                current_price=price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
            )
            self.positions[market_id] = pos
            _log(
                f"opened {side} {market_name}: {quantity} @ ${price:.4f} "
                f"(SL=${stop_loss_price:.4f}, TP=${take_profit_price:.4f})"
            )

        self.balance -= cost
        return pos

    def close_position(
        self, market_id: str, exit_price: float, reason: str = "manual"
    ) -> Dict[str, Any]:
        """
        Close an open position entirely.

        Returns a dict with the trade summary (entry, exit, P&L).
        """
        if market_id not in self.positions:
            raise KeyError(f"No open position for market_id={market_id}")

        pos = self.positions.pop(market_id)
        proceeds = exit_price * pos.quantity
        realized_pnl = proceeds - pos.cost_basis

        self.balance += proceeds

        trade_record = {
            "market_id": pos.market_id,
            "market_name": pos.market_name,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "quantity": pos.quantity,
            "cost_basis": pos.cost_basis,
            "proceeds": proceeds,
            "realized_pnl": realized_pnl,
            "realized_pnl_pct": (realized_pnl / pos.cost_basis * 100) if pos.cost_basis else 0,
            "entry_time": pos.entry_time,
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "theme_id": pos.theme_id,
        }
        self.closed_trades.append(trade_record)

        pnl_str = f"+${realized_pnl:.2f}" if realized_pnl >= 0 else f"-${abs(realized_pnl):.2f}"
        _log(f"closed {pos.market_name}: {pnl_str} ({reason})")
        return trade_record

    def update_price(self, market_id: str, new_price: float) -> None:
        """Update the current price of an open position."""
        if market_id in self.positions:
            self.positions[market_id].current_price = new_price

    # ------------------------------------------------------------------
    # Trigger checks
    # ------------------------------------------------------------------

    def check_triggers(self) -> List[Dict[str, Any]]:
        """
        Check all open positions for stop-loss or take-profit triggers.

        Returns a list of dicts describing triggered positions:
            {"market_id": ..., "trigger": "stop_loss"|"take_profit", "price": ...}
        """
        triggers = []
        for mid, pos in self.positions.items():
            if pos.current_price <= pos.stop_loss_price:
                triggers.append({
                    "market_id": mid,
                    "market_name": pos.market_name,
                    "trigger": "stop_loss",
                    "current_price": pos.current_price,
                    "trigger_price": pos.stop_loss_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                })
            elif pos.current_price >= pos.take_profit_price:
                triggers.append({
                    "market_id": mid,
                    "market_name": pos.market_name,
                    "trigger": "take_profit",
                    "current_price": pos.current_price,
                    "trigger_price": pos.take_profit_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                })
        return triggers

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a comprehensive portfolio summary as a dict."""
        return {
            "cash": round(self.balance, 2),
            "total_invested": round(self.total_invested(), 2),
            "total_portfolio_value": round(self.total_portfolio_value(), 2),
            "exposure_pct": round(self.exposure_pct(), 2),
            "unrealized_pnl": round(self.total_unrealized_pnl(), 2),
            "realized_pnl": round(self.total_realized_pnl(), 2),
            "open_positions": len(self.positions),
            "closed_trades": len(self.closed_trades),
            "positions": {mid: p.to_dict() for mid, p in self.positions.items()},
        }

    def to_json(self) -> str:
        """Serialize portfolio state to JSON string."""
        return json.dumps(self.summary(), indent=2)

    def __repr__(self) -> str:
        return (
            f"Portfolio(cash=${self.balance:,.2f}, "
            f"positions={len(self.positions)}, "
            f"value=${self.total_portfolio_value():,.2f})"
        )


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    port = Portfolio(cfg)

    # Simulate a trade
    port.open_position("test-market-1", "BTC > $100K by June", "YES", 0.65, 100, "theme-housing-bonds-war")
    port.update_price("test-market-1", 0.72)

    print(port)
    print(json.dumps(port.summary(), indent=2))

    triggers = port.check_triggers()
    if triggers:
        print(f"Triggers: {triggers}")
    else:
        print("No triggers fired.")
