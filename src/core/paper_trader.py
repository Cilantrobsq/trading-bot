"""
Paper trading engine for the trading bot.

Simulates trades using the initial_balance from config without risking
real capital. Records every trade to data/paper-trades/ as individual
JSON files and maintains a running P&L ledger.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.config import Config
from src.core.portfolio import Portfolio, Position, RiskViolation


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] paper_trader: {msg}")


class PaperTrader:
    """
    Paper trading engine that simulates order execution.

    All trades are recorded to data/paper-trades/ as JSON files.
    Uses the Portfolio class for position tracking and risk enforcement.

    Usage:
        cfg = Config()
        trader = PaperTrader(cfg)
        trader.buy("market-abc", "BTC > 100K", "YES", 0.65, 100)
        trader.update_prices({"market-abc": 0.72})
        trader.sell("market-abc", 0.72)
        trader.print_summary()
    """

    def __init__(self, config: Config):
        self.config = config
        self.portfolio = Portfolio(config)
        self.trade_dir = config.data_path("paper-trades")
        self.state_file = os.path.join(self.trade_dir, "_state.json")

        os.makedirs(self.trade_dir, exist_ok=True)

        # Load existing state if available
        self._load_state()

        _log(
            f"initialized paper trader: balance=${self.portfolio.balance:,.2f}, "
            f"trade_dir={self.trade_dir}"
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Load portfolio state from disk if a state file exists."""
        if not os.path.isfile(self.state_file):
            return
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
            self.portfolio.balance = state.get("cash", self.portfolio.balance)
            self.portfolio.initial_balance = state.get(
                "initial_balance", self.portfolio.initial_balance
            )
            self.portfolio.closed_trades = state.get("closed_trades", [])
            for mid, pdata in state.get("positions", {}).items():
                self.portfolio.positions[mid] = Position.from_dict(pdata)
            _log(
                f"restored state: {len(self.portfolio.positions)} positions, "
                f"${self.portfolio.balance:,.2f} cash"
            )
        except (json.JSONDecodeError, KeyError) as e:
            _log(f"warning: could not load state file ({e}), starting fresh")

    def _save_state(self) -> None:
        """Persist current portfolio state to disk."""
        state = self.portfolio.summary()
        state["initial_balance"] = self.portfolio.initial_balance
        state["closed_trades_detail"] = self.portfolio.closed_trades
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _record_trade(self, trade: Dict[str, Any]) -> str:
        """
        Write a single trade record to a JSON file in the paper-trades dir.
        Returns the file path.
        """
        trade_id = trade.get("trade_id", str(uuid.uuid4())[:8])
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"trade-{ts}-{trade_id}.json"
        filepath = os.path.join(self.trade_dir, filename)
        with open(filepath, "w") as f:
            json.dump(trade, f, indent=2)
        _log(f"recorded trade -> {filename}")
        return filepath

    # ------------------------------------------------------------------
    # Trading operations
    # ------------------------------------------------------------------

    def buy(
        self,
        market_id: str,
        market_name: str,
        side: str,
        price: float,
        quantity: float,
        theme_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a paper buy order.

        Returns the trade record dict, or None if the trade was rejected
        by risk checks.
        """
        try:
            pos = self.portfolio.open_position(
                market_id, market_name, side, price, quantity, theme_id
            )
        except RiskViolation as e:
            _log(f"REJECTED buy {market_name}: {e}")
            return None
        except ValueError as e:
            _log(f"INVALID buy {market_name}: {e}")
            return None

        trade = {
            "trade_id": str(uuid.uuid4())[:8],
            "action": "BUY",
            "market_id": market_id,
            "market_name": market_name,
            "side": side,
            "price": price,
            "quantity": quantity,
            "cost": round(price * quantity, 4),
            "theme_id": theme_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "balance_after": round(self.portfolio.balance, 2),
            "paper": True,
        }
        self._record_trade(trade)
        self._save_state()
        return trade

    def sell(
        self,
        market_id: str,
        exit_price: float,
        reason: str = "manual",
    ) -> Optional[Dict[str, Any]]:
        """
        Close a paper position (sell all shares).

        Returns the trade record dict, or None if no position exists.
        """
        try:
            closed = self.portfolio.close_position(market_id, exit_price, reason)
        except KeyError as e:
            _log(f"REJECTED sell: {e}")
            return None

        trade = {
            "trade_id": str(uuid.uuid4())[:8],
            "action": "SELL",
            "market_id": closed["market_id"],
            "market_name": closed["market_name"],
            "side": closed["side"],
            "entry_price": closed["entry_price"],
            "exit_price": exit_price,
            "quantity": closed["quantity"],
            "proceeds": round(closed["proceeds"], 4),
            "realized_pnl": round(closed["realized_pnl"], 4),
            "realized_pnl_pct": round(closed["realized_pnl_pct"], 2),
            "reason": reason,
            "theme_id": closed["theme_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "balance_after": round(self.portfolio.balance, 2),
            "paper": True,
        }
        self._record_trade(trade)
        self._save_state()
        return trade

    def update_prices(self, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Update current prices for open positions and check triggers.

        Args:
            prices: Dict mapping market_id to current price.

        Returns:
            List of triggered stop-loss/take-profit events.
        """
        for market_id, price in prices.items():
            self.portfolio.update_price(market_id, price)

        triggers = self.portfolio.check_triggers()
        for t in triggers:
            _log(
                f"TRIGGER {t['trigger'].upper()} on {t['market_name']}: "
                f"price={t['current_price']:.4f}, trigger={t['trigger_price']:.4f}"
            )
        self._save_state()
        return triggers

    def auto_close_triggers(self, prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Update prices and automatically close any triggered positions.
        Returns the list of closed trade records.
        """
        triggers = self.update_prices(prices)
        closed = []
        for t in triggers:
            result = self.sell(t["market_id"], t["current_price"], reason=t["trigger"])
            if result:
                closed.append(result)
        return closed

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def pnl_summary(self) -> Dict[str, Any]:
        """Calculate detailed P&L metrics."""
        total_value = self.portfolio.total_portfolio_value()
        initial = self.portfolio.initial_balance
        total_return = total_value - initial
        total_return_pct = (total_return / initial * 100) if initial else 0

        wins = [t for t in self.portfolio.closed_trades if t.get("realized_pnl", 0) > 0]
        losses = [t for t in self.portfolio.closed_trades if t.get("realized_pnl", 0) <= 0]

        return {
            "initial_balance": initial,
            "current_value": round(total_value, 2),
            "cash": round(self.portfolio.balance, 2),
            "total_return_usd": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "unrealized_pnl": round(self.portfolio.total_unrealized_pnl(), 2),
            "realized_pnl": round(self.portfolio.total_realized_pnl(), 2),
            "open_positions": len(self.portfolio.positions),
            "total_trades": len(self.portfolio.closed_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(
                len(wins) / len(self.portfolio.closed_trades) * 100, 1
            ) if self.portfolio.closed_trades else 0,
        }

    def print_summary(self) -> None:
        """Print a formatted P&L summary to stdout."""
        s = self.pnl_summary()
        print("\n--- Paper Trading Summary ---")
        print(f"  Initial Balance:  ${s['initial_balance']:>12,.2f}")
        print(f"  Current Value:    ${s['current_value']:>12,.2f}")
        print(f"  Cash:             ${s['cash']:>12,.2f}")
        print(f"  Total Return:     ${s['total_return_usd']:>12,.2f} ({s['total_return_pct']:+.2f}%)")
        print(f"  Unrealized P&L:   ${s['unrealized_pnl']:>12,.2f}")
        print(f"  Realized P&L:     ${s['realized_pnl']:>12,.2f}")
        print(f"  Open Positions:   {s['open_positions']}")
        print(f"  Total Trades:     {s['total_trades']}")
        if s["total_trades"] > 0:
            print(f"  Win Rate:         {s['win_rate_pct']:.1f}%")
            print(f"  Wins / Losses:    {s['winning_trades']} / {s['losing_trades']}")
        print("---")

    def print_positions(self) -> None:
        """Print all open positions."""
        if not self.portfolio.positions:
            print("  No open positions.")
            return
        print("\n--- Open Positions ---")
        for mid, pos in self.portfolio.positions.items():
            pnl = pos.unrealized_pnl
            pnl_sign = "+" if pnl >= 0 else ""
            print(
                f"  {pos.market_name:<40} {pos.side:>3} "
                f"{pos.quantity:>8.1f} @ ${pos.entry_price:.4f} "
                f"-> ${pos.current_price:.4f} "
                f"P&L: {pnl_sign}${pnl:.2f} ({pos.unrealized_pnl_pct:+.1f}%)"
            )
        print("---")


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = Config(root)
    trader = PaperTrader(cfg)

    # Simulate some trades
    trader.buy("demo-btc-100k", "BTC > $100K by June", "YES", 0.65, 50, "theme-housing-bonds-war")
    trader.buy("demo-eth-5k", "ETH > $5K by July", "YES", 0.40, 100, "theme-housing-bonds-war")

    # Price moves
    trader.update_prices({"demo-btc-100k": 0.72, "demo-eth-5k": 0.38})

    trader.print_positions()
    trader.print_summary()

    # Close one
    trader.sell("demo-btc-100k", 0.72, reason="take_profit_manual")
    trader.print_summary()
