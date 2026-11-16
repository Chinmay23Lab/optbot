from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from optbot.charges import order_charges
from optbot.clock import IST, MarketCalendar, SimClock
from optbot.config import Profile, load_config
from optbot.models import Candle, Contract, Leg, Position, Quote
from optbot.paper import PaperAccount, PaperBroker, liquidation_value
from optbot.risk import RiskManager
from optbot.strategy import exit_reason, signal

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())


def profile(name="conservative", **over) -> Profile:
    d = dict(CFG["profiles"][name])
    d.update(over)
    return Profile.from_dict(name, d)


def test_no_order_placement_anywhere():
    """This build must not be able to place, modify or cancel real orders."""
    src = "\n".join(p.read_text() for p in (ROOT / "optbot").rglob("*.py"))
    for forbidden in ("placeOrder", "modifyOrder", "cancelOrder", "gttCreateRule", "placeOrderFullResponse"):
        assert forbidden not in src, forbidden


def test_live_mode_refused(tmp_path):
    cfg = dict(CFG)
    cfg["mode"] = "live"
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg))
    with pytest.raises(SystemExit):
        load_config(p)


def test_charges_sell_has_stt_buy_has_stamp():
    c = CFG["charges"]
    buy = order_charges(c, "NFO", "BUY", 100.0, 65)
    sell = order_charges(c, "NFO", "SELL", 100.0, 65)
    assert sell > buy > 20
    # STT on a ₹6,500 sell at 0.15% is ₹9.75
    assert sell - buy == pytest.approx(9.75 - 6500 * 0.003 / 100, abs=0.05)


def _contract(strike, right="CE", token=None, lot=65):
    return Contract(token or f"T{strike}{right}", f"NIFTY{strike}{right}", "NIFTY", "NFO", date(2026, 11, 24),
                    float(strike), right, lot, 0.05)


def test_paper_round_trip_accounting(tmp_path):
    clock = SimClock(datetime(2026, 11, 17, 10, 0, tzinfo=IST))
    acct = PaperAccount("t", 20000, tmp_path / "t.json")
    broker = PaperBroker(CFG["charges"], {"slippage_ticks": 1}, clock)
    b, s = _contract(25800), _contract(25900)
    q = {b.token: Quote(b.token, 100, 99.8, 100.2), s.token: Quote(s.token, 60, 59.8, 60.2)}
    pos = broker.open_spread(acct, "NIFTY", "long", b, s, 1, q, {})
    assert pos and pos.entry_debit == pytest.approx(100.25 - 59.75)
    assert acct.cash == pytest.approx(20000 - pos.cost - pos.entry_charges)
    q2 = {b.token: Quote(b.token, 130, 129.8, 130.2), s.token: Quote(s.token, 70, 69.8, 70.2)}
    assert liquidation_value(pos, q2) == pytest.approx(129.8 - 70.2)
    assert broker.close_position(acct, pos, q2, "test")
    assert acct.open == []
    assert acct.cash == pytest.approx(20000 + pos.realized_pnl())
    # state survives a restart
    acct2 = PaperAccount("t", 20000, tmp_path / "t.json")
    assert acct2.cash == pytest.approx(acct.cash)


def test_risk_daily_cap_and_profit_lock():
    rm = RiskManager(profile("conservative"))
    rm.new_day(date(2026, 11, 17))
    assert rm.update_day(-1000) is not None
    rm.new_day(date(2026, 11, 17))
    assert rm.update_day(1200) is None and rm.state.stopped  # target hit: no new entries, positions held
    assert rm.update_day(900) is not None                     # fell below 80% of the ₹1,200 peak


def test_risk_target_5k_keeps_trading_after_target():
    rm = RiskManager(profile("target_5k"))
    rm.new_day(date(2026, 11, 17))
    assert rm.update_day(5200) is None and not rm.state.stopped
    assert rm.update_day(6000) is None
    assert rm.update_day(4700) is not None  # below 80% of the ₹6,000 peak


def test_sizing_respects_risk_and_cash():
    rm = RiskManager(profile("target_5k"))
    assert rm.size(cost_per_lot=2500, risk_per_lot=1000, cash=20000, capital_in_use=0) == 2  # ₹2,000 risk cap
    assert rm.size(cost_per_lot=2500, risk_per_lot=1000, cash=3000, capital_in_use=0) == 1
    assert rm.size(cost_per_lot=5000, risk_per_lot=2000, cash=20000, capital_in_use=0) == 0  # over per-lot cap


def _pos(debit=40.0, width=100.0):
    b, s = _contract(25800), _contract(25900)
    return Position("x", "p", "NIFTY", "long", [Leg(b, "BUY", 65, 100), Leg(s, "SELL", 65, 60)], 1,
                    datetime(2026, 11, 17, 10, 0, tzinfo=IST), debit, width, peak_value=debit,
                    meta={"or_high": 25800, "or_low": 25700})


def test_exits_stop_trail_and_time():
    mkt = MarketCalendar(CFG["market"])
    t = datetime(2026, 11, 17, 11, 0, tzinfo=IST)
    trail = profile("target_5k")
    p = _pos()
    assert "stop loss" in exit_reason(p, 23.0, t, trail, mkt, [], CFG["strategy"])
    p = _pos()
    assert exit_reason(p, 60.0, t, trail, mkt, [], CFG["strategy"]) is None   # +50%: trailing armed
    assert p.trail_active
    assert exit_reason(p, 55.0, t, trail, mkt, [], CFG["strategy"]) is None   # small pullback: hold
    assert "trailing stop" in exit_reason(p, 53.0, t, trail, mkt, [], CFG["strategy"])
    p = _pos()
    assert "time exit" in exit_reason(p, 45.0, t.replace(hour=15, minute=11), trail, mkt, [], CFG["strategy"])


def test_target_profile_books_target_but_trail_profile_does_not():
    mkt = MarketCalendar(CFG["market"])
    t = datetime(2026, 11, 17, 11, 0, tzinfo=IST)
    v = 40 + 0.6 * 60 + 1  # beyond 60% of max profit
    assert exit_reason(_pos(), v, t, profile("conservative"), mkt, [], CFG["strategy"]) == "profit target"
    assert exit_reason(_pos(), v, t, profile("target_5k"), mkt, [], CFG["strategy"]) is None


def _candles(closes, day=date(2026, 11, 17)):
    out = []
    for i, c in enumerate(closes):
        ts = datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST).replace(minute=15) + __import__("datetime").timedelta(minutes=5 * i)
        out.append(Candle(ts, c, c + 5, c - 5, c))
    return out


def test_signal_breakout_and_playbook_filter():
    s = CFG["strategy"]
    closes = [25700, 25710, 25705, 25700, 25705, 25708, 25712, 25714, 25725]
    cs = _candles(closes)
    sig, why = signal("NIFTY", cs, date(2026, 11, 17), s, {"allowed": ["long", "short"]})
    assert sig and sig.direction == "long", why
    sig, why = signal("NIFTY", cs, date(2026, 11, 17), s, {"allowed": ["short"]})
    assert sig is None and "disallows" in why


def test_simulation_runs_end_to_end(tmp_path):
    from optbot.__main__ import main
    cfg = dict(CFG)
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg))
    assert main(["--config", str(p), "simulate", "--days", "2", "--start", "2026-11-17"]) == 0
