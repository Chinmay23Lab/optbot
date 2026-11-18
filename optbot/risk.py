"""Risk manager: the last word on whether a trade may open, and how big it may be."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .config import Profile


@dataclass
class DayState:
    day: date
    peak_pnl: float = 0.0
    locked: bool = False          # target reached: lock floor now applies
    stopped: bool = False         # no more entries today
    stop_reason: str = ""
    cap_note_sent: bool = False   # told the user open trades stay on after the loss cap


class RiskManager:
    def __init__(self, profile: Profile):
        self.p = profile
        self.state: DayState | None = None

    def new_day(self, day: date) -> None:
        self.state = DayState(day)

    def day_pnl(self, realized: float, open_pnl: float) -> float:
        return realized + open_pnl

    def update_day(self, day_pnl: float) -> str | None:
        """Track the day's P&L. Returns a reason string if all positions must be closed now."""
        s = self.state
        assert s is not None
        s.peak_pnl = max(s.peak_pnl, day_pnl)
        if day_pnl <= -self.p.daily_loss_cap:
            s.stopped, s.stop_reason = True, f"daily loss cap ₹{self.p.daily_loss_cap:.0f} hit"
            return s.stop_reason
        if s.peak_pnl >= self.p.daily_profit_target:
            if not s.locked:
                s.locked = True
                if not self.p.continue_after_target:
                    s.stopped, s.stop_reason = True, f"daily target ₹{self.p.daily_profit_target:.0f} reached"
            floor = self.p.daily_profit_target * self.p.daily_profit_lock_pct
            # Ratchet: the floor also rises with the peak, keeping the same share of the best level.
            floor = max(floor, s.peak_pnl * self.p.daily_profit_lock_pct)
            if day_pnl < floor:
                s.stopped, s.stop_reason = True, f"profit lock: day P&L fell below ₹{floor:.0f}"
                return s.stop_reason
        return None

    def can_enter(self, *, killed: bool, paused: bool, equity: float, realized_today: float, losers_today: int,
                  week_realized: float, open_count: int, trades_today: int, open_pnl: float) -> tuple[bool, str]:
        p, s = self.p, self.state
        assert s is not None
        if killed:
            return False, "kill switch on"
        if paused:
            return False, "paused"
        if equity <= p.account_floor:
            return False, f"account at/below floor ₹{p.account_floor:.0f}"
        if s.stopped:
            return False, s.stop_reason
        if realized_today + open_pnl <= -p.daily_loss_cap:
            return False, "daily loss cap"
        if losers_today >= p.max_losing_trades_per_day:
            return False, f"{losers_today} losing trade(s) today"
        if week_realized <= -p.weekly_loss_cap:
            return False, f"weekly loss cap ₹{p.weekly_loss_cap:.0f} hit"
        if open_count >= p.max_open_positions:
            return False, "max open positions"
        if trades_today >= p.max_trades_per_day:
            return False, "max trades for the day"
        return True, "ok"

    def size(self, cost_per_lot: float, risk_per_lot: float, cash: float, capital_in_use: float) -> int:
        p = self.p
        if cost_per_lot <= 0 or cost_per_lot > p.max_debit_per_lot:
            return 0
        budget = p.capital * p.max_capital_in_use_pct - capital_in_use
        by_cash = math.floor(min(cash, budget) / cost_per_lot)
        by_risk = math.floor(p.max_risk_per_trade / risk_per_lot) if risk_per_lot > 0 else 0
        return max(0, min(p.max_lots, by_cash, by_risk))
