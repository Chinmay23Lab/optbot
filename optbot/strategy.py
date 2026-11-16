"""Entry signals, spread construction and exit rules.

Entry: opening-range breakout on 5-minute index candles, confirmed by EMA trend, filtered by the
morning playbook. Trade: a debit spread (bull call or bear put), sized by the risk manager.
Exit: stop loss, optional profit target, trailing stop, setup failure, time and expiry-day exits.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .config import Profile
from .indicators import atr, ema
from .instruments import Instruments
from .models import Candle, Contract, Position, Quote


@dataclass
class Signal:
    index: str
    direction: str  # long | short
    strength: float
    reason: str
    or_high: float
    or_low: float


@dataclass
class SpreadCandidate:
    buy: Contract
    sell: Contract
    debit: float
    width: float
    lot_size: int

    @property
    def cost_per_lot(self) -> float:
        return self.debit * self.lot_size

    def rr(self) -> float:
        return (self.width - self.debit) / self.debit if self.debit > 0 else 0.0


def today_candles(candles: list[Candle], day: date) -> list[Candle]:
    return [c for c in candles if c.ts.date() == day]


def opening_range(today: list[Candle], minutes: int) -> tuple[float, float] | None:
    n = max(1, minutes // 5)
    if len(today) < n:
        return None
    first = today[:n]
    return max(c.high for c in first), min(c.low for c in first)


def signal(index: str, candles: list[Candle], day: date, scfg: dict, pb_index: dict | None) -> tuple[Signal | None, str]:
    today = today_candles(candles, day)
    n_or = max(1, scfg["opening_range_minutes"] // 5)
    if len(today) <= n_or:
        return None, "opening range not complete"
    rng = opening_range(today, scfg["opening_range_minutes"])
    assert rng
    hi, lo = rng
    closes = [c.close for c in candles]
    ef, es = ema(closes, scfg["ema_fast"])[-1], ema(closes, scfg["ema_slow"])[-1]
    a = atr(candles[-(scfg["atr_period"] + 1):], scfg["atr_period"])
    if a <= 0:
        return None, "no ATR"
    last = today[-1].close
    allowed = (pb_index or {}).get("allowed", ["long", "short"])
    if last > hi:
        strength = (last - hi) / a
        if not (ef > es and last > es):
            return None, "breakout up but EMA trend not confirming"
        if not scfg["min_breakout_atr"] <= strength <= scfg["max_breakout_atr"]:
            return None, f"breakout up {strength:.2f} ATR outside band"
        if "long" not in allowed:
            return None, "playbook disallows long"
        return Signal(index, "long", strength, f"close {last:.1f} > OR high {hi:.1f}, EMA{scfg['ema_fast']}>EMA{scfg['ema_slow']}", hi, lo), "signal"
    if last < lo:
        strength = (lo - last) / a
        if not (ef < es and last < es):
            return None, "breakout down but EMA trend not confirming"
        if not scfg["min_breakout_atr"] <= strength <= scfg["max_breakout_atr"]:
            return None, f"breakout down {strength:.2f} ATR outside band"
        if "short" not in allowed:
            return None, "playbook disallows short"
        return Signal(index, "short", strength, f"close {last:.1f} < OR low {lo:.1f}, EMA{scfg['ema_fast']}<EMA{scfg['ema_slow']}", hi, lo), "signal"
    return None, "inside opening range"


def pick_expiry(inst: Instruments, index: str, today: date, min_dte: int) -> date | None:
    for e in inst.expiries(index):
        if (e - today).days >= min_dte:
            return e
    return None


def candidate_contracts(inst: Instruments, index: str, direction: str, spot: float, expiry: date,
                        step: float, max_steps: int) -> tuple[Contract | None, list[Contract]]:
    atm = round(spot / step) * step
    right = "CE" if direction == "long" else "PE"
    sign = 1 if direction == "long" else -1
    buy = inst.find(index, expiry, atm, right)
    sells = [c for k in range(1, max_steps + 1) if (c := inst.find(index, expiry, atm + sign * k * step, right))]
    return buy, sells


def build_candidates(buy: Contract, sells: list[Contract], quotes: dict[str, Quote], scfg: dict,
                     slip_ticks: int) -> list[SpreadCandidate]:
    qb = quotes.get(buy.token)
    if not qb or qb.ask <= 0 or qb.spread_pct() > scfg["max_leg_spread_pct"]:
        return []
    out = []
    for s in sells:
        qs = quotes.get(s.token)
        if not qs or qs.bid <= 0 or qs.spread_pct() > scfg["max_leg_spread_pct"]:
            continue
        debit = (qb.ask + slip_ticks * buy.tick) - (qs.bid - slip_ticks * s.tick)
        cand = SpreadCandidate(buy, s, round(debit, 2), abs(s.strike - buy.strike), buy.lot_size)
        if cand.debit > 0 and cand.rr() >= scfg["min_reward_to_risk"]:
            out.append(cand)
    return out


def choose_for_profile(cands: list[SpreadCandidate], profile: Profile) -> SpreadCandidate | None:
    """Widest spread whose 1-lot cost fits the profile (more room to run), else None."""
    cap = min(profile.max_debit_per_lot, profile.max_risk_per_trade / profile.stop_pct)
    fit = [c for c in cands if c.cost_per_lot <= cap]
    return max(fit, key=lambda c: c.width) if fit else None


def exit_reason(pos: Position, value: float, now: datetime, profile: Profile, market, candles: list[Candle],
                scfg: dict) -> str | None:
    """Update the position's trailing state and return an exit reason, or None to hold."""
    debit = pos.entry_debit
    pos.peak_value = max(pos.peak_value, value)
    gain = (pos.peak_value - debit) / debit if debit else 0.0

    if now.time() >= market.t("square_off"):
        return "time exit (square-off)"
    expiries = {l.contract.expiry for l in pos.legs}
    if now.date() in expiries and now.time() >= market.t("expiry_day_exit"):
        return "expiry-day exit"
    if value <= debit * (1 - profile.stop_pct):
        return f"stop loss ({profile.stop_pct:.0%} of debit)"
    if value >= 0.95 * pos.width:
        return "near max profit"
    if profile.exit_mode == "target" and profile.target_pct_of_max_profit:
        if value >= debit + profile.target_pct_of_max_profit * (pos.width - debit):
            return "profit target"
    if gain >= profile.trail_trigger_pct:
        pos.trail_active = True
    if pos.trail_active:
        trail_stop = max(debit * 1.02, pos.peak_value - profile.trail_giveback_pct * (pos.peak_value - debit))
        pos.meta["trail_stop"] = round(trail_stop, 2)
        if value <= trail_stop:
            return f"trailing stop (peak {pos.peak_value:.1f}, stop {trail_stop:.1f})"
    elif candles:
        closes = [c.close for c in candles]
        es = ema(closes, scfg["ema_slow"])[-1]
        last = closes[-1]
        orh, orl = pos.meta.get("or_high"), pos.meta.get("or_low")
        if pos.direction == "long" and orh and last < orh and last < es:
            return "setup failed (back inside range, below EMA)"
        if pos.direction == "short" and orl and last > orl and last > es:
            return "setup failed (back inside range, above EMA)"
    return None
