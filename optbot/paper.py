"""Paper broker: simulated fills against live bid/ask with slippage and full charges.

There is no live broker in this build. Nothing here can reach an exchange.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from .charges import order_charges
from .models import Contract, Leg, Position, Quote

log = logging.getLogger(__name__)


def _round_tick(x: float, tick: float) -> float:
    return round(round(x / tick) * tick, 2)


class PaperAccount:
    def __init__(self, profile: str, capital: float, state_path: Path):
        self.profile = profile
        self.capital = capital
        self.state_path = state_path
        self.cash = capital
        self.open: list[Position] = []
        self.killed = False
        self.paused = False
        self.load()

    # --- persistence -----------------------------------------------------------
    def save(self) -> None:
        state = {
            "profile": self.profile,
            "cash": self.cash,
            "killed": self.killed,
            "paused": self.paused,
            "open": [asdict(p) for p in self.open],
        }
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, default=str, indent=1))
        tmp.replace(self.state_path)

    def load(self) -> None:
        if not self.state_path.exists():
            return
        s = json.loads(self.state_path.read_text())
        self.cash = float(s["cash"])
        self.killed = bool(s.get("killed"))
        self.paused = bool(s.get("paused"))
        self.open = [position_from_dict(d) for d in s.get("open", [])]

    # --- valuation -------------------------------------------------------------
    def equity(self, quotes: dict[str, Quote]) -> float:
        return self.cash + sum(liquidation_value(p, quotes) * p.qty for p in self.open if liquidation_value(p, quotes) is not None)

    def capital_in_use(self) -> float:
        return sum(p.cost for p in self.open)


def position_from_dict(d: dict) -> Position:
    legs = []
    for l in d["legs"]:
        c = dict(l["contract"])
        c["expiry"] = date.fromisoformat(str(c["expiry"]))
        legs.append(Leg(contract=Contract(**c), side=l["side"], qty=int(l["qty"]),
                        entry_price=float(l["entry_price"]), exit_price=l.get("exit_price")))
    d = dict(d)
    d["legs"] = legs
    for k in ("entry_time", "exit_time"):
        if d.get(k) and d[k] != "None":
            d[k] = datetime.fromisoformat(str(d[k]))
        else:
            d[k] = None
    return Position(**d)


def liquidation_value(p: Position, quotes: dict[str, Quote]) -> float | None:
    """Per-unit value if the spread were closed now: sell the long leg at bid, buy back the short at ask."""
    long_leg = next(l for l in p.legs if l.side == "BUY")
    short_leg = next((l for l in p.legs if l.side == "SELL"), None)
    ql = quotes.get(long_leg.contract.token)
    if short_leg is None:   # a single bought option: worth its bid
        return ql.bid if ql and ql.bid > 0 else None
    qs = quotes.get(short_leg.contract.token)
    if not ql or not qs or ql.bid <= 0 or qs.ask <= 0:
        return None
    return max(0.0, ql.bid - qs.ask)


class PaperBroker:
    def __init__(self, charges_cfg: dict, paper_cfg: dict, clock):
        self.charges_cfg = charges_cfg
        self.slip = int(paper_cfg.get("slippage_ticks", 1))
        self.clock = clock

    def _fill(self, c: Contract, side: str, q: Quote) -> float:
        if side == "BUY":
            return _round_tick(q.ask + self.slip * c.tick, c.tick)
        return max(c.tick, _round_tick(q.bid - self.slip * c.tick, c.tick))

    def open_spread(self, acct: PaperAccount, index: str, direction: str, buy: Contract, sell: Contract,
                    lots: int, quotes: dict[str, Quote], meta: dict) -> Position | None:
        qb, qs = quotes.get(buy.token), quotes.get(sell.token)
        if not qb or not qs:
            return None
        qty = lots * buy.lot_size
        # Long (protective) leg first, then the short leg: the same order the live adapter would use.
        pb = self._fill(buy, "BUY", qb)
        ps = self._fill(sell, "SELL", qs)
        debit = round(pb - ps, 2)
        if debit <= 0:
            return None
        ch = order_charges(self.charges_cfg, buy.segment, "BUY", pb, qty) + order_charges(
            self.charges_cfg, sell.segment, "SELL", ps, qty)
        cost = debit * qty + ch
        if cost > acct.cash:
            log.info("[%s] not enough cash for %s (need %.0f, have %.0f)", acct.profile, index, cost, acct.cash)
            return None
        pos = Position(
            id=uuid.uuid4().hex[:8], profile=acct.profile, index=index, direction=direction,
            legs=[Leg(buy, "BUY", qty, pb), Leg(sell, "SELL", qty, ps)], lots=lots,
            entry_time=self.clock.now(), entry_debit=debit, width=abs(sell.strike - buy.strike),
            entry_charges=round(ch, 2), peak_value=debit, meta=meta,
        )
        acct.cash -= cost
        acct.open.append(pos)
        acct.save()
        return pos

    def open_single(self, acct: PaperAccount, index: str, direction: str, buy: Contract, lots: int,
                    quotes: dict[str, Quote], meta: dict) -> Position | None:
        """Buy one option (call for an up view, put for a down view). Most it can lose is what was paid."""
        qb = quotes.get(buy.token)
        if not qb:
            return None
        qty = lots * buy.lot_size
        pb = self._fill(buy, "BUY", qb)
        ch = order_charges(self.charges_cfg, buy.segment, "BUY", pb, qty)
        cost = pb * qty + ch
        if cost > acct.cash:
            log.info("[%s] not enough cash for %s (need %.0f, have %.0f)", acct.profile, index, cost, acct.cash)
            return None
        pos = Position(
            id=uuid.uuid4().hex[:8], profile=acct.profile, index=index, direction=direction,
            legs=[Leg(buy, "BUY", qty, pb)], lots=lots, entry_time=self.clock.now(), entry_debit=pb, width=0.0,
            entry_charges=round(ch, 2), peak_value=pb, meta=meta,
        )
        acct.cash -= cost
        acct.open.append(pos)
        acct.save()
        return pos

    def close_position(self, acct: PaperAccount, pos: Position, quotes: dict[str, Quote], reason: str) -> bool:
        long_leg = next(l for l in pos.legs if l.side == "BUY")
        short_leg = next((l for l in pos.legs if l.side == "SELL"), None)
        if short_leg is None:
            ql = quotes.get(long_leg.contract.token)
            if not ql:
                return False
            p_long = self._fill(long_leg.contract, "SELL", ql)
            ch = order_charges(self.charges_cfg, long_leg.contract.segment, "SELL", p_long, pos.qty)
            long_leg.exit_price = p_long
            pos.exit_value, pos.exit_charges = p_long, round(ch, 2)
            pos.exit_time, pos.exit_reason = self.clock.now(), reason
            acct.cash += p_long * pos.qty - ch
            acct.open = [p for p in acct.open if p.id != pos.id]
            acct.save()
            return True
        ql, qs = quotes.get(long_leg.contract.token), quotes.get(short_leg.contract.token)
        if not ql or not qs:
            return False
        # Buy back the short leg first, then sell the long leg.
        p_short = self._fill(short_leg.contract, "BUY", qs)
        p_long = self._fill(long_leg.contract, "SELL", ql)
        qty = pos.qty
        ch = order_charges(self.charges_cfg, short_leg.contract.segment, "BUY", p_short, qty) + order_charges(
            self.charges_cfg, long_leg.contract.segment, "SELL", p_long, qty)
        value = round(max(0.0, p_long - p_short), 2) if p_long >= p_short else round(p_long - p_short, 2)
        short_leg.exit_price, long_leg.exit_price = p_short, p_long
        pos.exit_value = value
        pos.exit_charges = round(ch, 2)
        pos.exit_time = self.clock.now()
        pos.exit_reason = reason
        acct.cash += value * qty - ch
        acct.open = [p for p in acct.open if p.id != pos.id]
        acct.save()
        return True
