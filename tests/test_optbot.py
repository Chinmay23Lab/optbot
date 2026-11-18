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


def test_split_session_resumes_and_reports_once(tmp_path):
    """Morning and afternoon runs (as on GitHub Actions) continue the same day and report once."""
    from datetime import time as dtime
    from optbot.config import load_config
    from optbot.engine import Engine
    from optbot.instruments import Instruments
    from optbot.journal import Journal
    from optbot.notify import Notifier
    from optbot.sim import SimMarket, synthetic_rows

    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(dict(CFG)))
    cfg = load_config(p)
    d = date(2026, 11, 17)
    clock = SimClock(datetime(2026, 11, 17, 8, 45, tzinfo=IST))
    inst = Instruments(synthetic_rows(cfg["indices"], d), cfg["indices"], cfg["vix"]["names"])
    sent = []

    class Rec(Notifier):
        def send(self, text):
            sent.append(text)

    def engine():
        return Engine(cfg, SimMarket(clock, inst, seed=3), inst, clock, Rec(), Journal(cfg.data_dir / "journal.sqlite"))

    assert engine().run_window(d, dtime(12, 0)) is None
    assert clock.now().time() >= dtime(12, 0)
    report = engine().run_window(d, dtime(15, 40))
    assert report and "Paper report" in report
    assert engine().run_window(d, dtime(15, 40)) is None  # already ended
    assert sum("Good morning" in s for s in sent) == 1


def test_swing_holds_overnight_only_when_working():
    from datetime import timedelta
    mkt = MarketCalendar(CFG["market"])
    sw = profile("swing")
    sq = datetime(2026, 11, 17, 15, 11, tzinfo=IST)
    # in profit, trend agrees -> carried, not closed
    p = _pos()
    pass
    p.meta["trend_ok"] = True
    assert exit_reason(p, 50.0, sq, sw, mkt, [], CFG["strategy"]) is None and p.meta["carry"]
    # losing at square-off -> closed
    p2 = _pos()
    assert "not in profit" in exit_reason(p2, 35.0, sq, sw, mkt, [], CFG["strategy"])
    # next day: trend turned -> exit
    p.meta["trend_ok"] = False
    assert "trend turned" in exit_reason(p, 50.0, datetime(2026, 11, 18, 10, 0, tzinfo=IST), sw, mkt, [], CFG["strategy"])
    # held max days -> closed at square-off on day 2
    p3 = _pos()
    p3.meta["trend_ok"] = True
    assert "maximum" in exit_reason(p3, 60.0, datetime(2026, 11, 19, 15, 11, tzinfo=IST), sw, mkt, [], CFG["strategy"])
    # intraday profiles never carry
    assert "time exit" in exit_reason(_pos(), 60.0, sq, profile("target_5k"), mkt, [], CFG["strategy"])


def test_swing_entry_needs_daily_trend():
    from optbot.strategy import trend_agrees
    assert trend_agrees({"bias": "bullish", "confidence": 0.5}, "long", 0.3)
    assert not trend_agrees({"bias": "bullish", "confidence": 0.1}, "long", 0.3)
    assert not trend_agrees({"bias": "neutral", "confidence": 0.9}, "long", 0.3)
    assert not trend_agrees({"bias": "bullish", "confidence": 0.9}, "short", 0.3)


def test_carried_position_survives_end_of_day(tmp_path):
    from optbot.engine import Engine
    from optbot.journal import Journal
    from optbot.notify import Notifier
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(dict(CFG)))
    cfg = load_config(p)
    clock = SimClock(datetime(2026, 11, 17, 15, 20, tzinfo=IST))
    eng = Engine(cfg, None, None, clock, Notifier(), Journal(cfg.data_dir / "journal.sqlite"))
    eng.day = date(2026, 11, 17)
    eng.data = type("D", (), {"quotes": lambda self, cs: {}})()
    book = next(b for b in eng.books if b.profile.name == "swing")
    pos = _pos(); pos.profile = "swing"; pos.meta.update(carry=True, carry_mark=50.0)
    book.account.open.append(pos); book.account.save()
    eng.end_day()
    again = Engine(cfg, None, None, clock, Notifier(), Journal(cfg.data_dir / "journal.sqlite"))
    assert len(next(b for b in again.books if b.profile.name == "swing").account.open) == 1


def test_trail_tightens_on_big_gains():
    mkt = MarketCalendar(CFG["market"])
    t = datetime(2026, 11, 17, 11, 0, tzinfo=IST)
    p = _pos(debit=40.0, width=300.0)
    assert exit_reason(p, 119.0, t, profile("target_5k"), mkt, [], CFG["strategy"]) is None
    # +198% gain: may give back only 10% of the 79-point gain -> stop at about 111
    assert p.meta["trail_stop"] >= 110
    assert "trailing stop" in exit_reason(p, 110.0, t, profile("target_5k"), mkt, [], CFG["strategy"])


def test_report_explains_why_no_trade(tmp_path):
    from optbot.engine import Engine
    from optbot.journal import Journal
    from optbot.notify import Notifier
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(dict(CFG)))
    cfg = load_config(p)
    clock = SimClock(datetime(2026, 11, 18, 11, 0, tzinfo=IST))
    eng = Engine(cfg, None, None, clock, Notifier(), Journal(cfg.data_dir / "journal.sqlite"))
    eng.day = date(2026, 11, 18)
    eng._note("*", "NIFTY", "no-signal", "inside opening range")
    eng._note("*", "BANKNIFTY", "no-signal", "breakout up 0.12 ATR outside band")
    eng._note("swing", "*", "blocked", "1 loser today")
    why = eng.why_summary()
    text = "\n".join(why)
    assert "NIFTY inside opening range" in text and "Swing (1-2 days) stopped taking trades: 1 loser today" in text
    assert "Why it did not trade more today" in eng.report()


def test_instruments_load_stock_options_and_spot():
    from optbot.instruments import Instruments
    rows = [
        {"token": "2885", "symbol": "RELIANCE-EQ", "name": "RELIANCE", "exch_seg": "NSE", "instrumenttype": "",
         "expiry": "", "strike": "-1", "lotsize": "1", "tick_size": "10"},
        {"token": "111", "symbol": "RELIANCE29DEC261400CE", "name": "RELIANCE", "exch_seg": "NFO",
         "instrumenttype": "OPTSTK", "expiry": "29DEC2026", "strike": "140000.000000", "lotsize": "500", "tick_size": "5"},
        {"token": "112", "symbol": "RELIANCE29DEC261420CE", "name": "RELIANCE", "exch_seg": "NFO",
         "instrumenttype": "OPTSTK", "expiry": "29DEC2026", "strike": "142000.000000", "lotsize": "500", "tick_size": "5"},
    ]
    inst = Instruments(rows, CFG["indices"], CFG["vix"]["names"], ["RELIANCE"])
    assert inst.spot_tokens["RELIANCE"] == ("NSE", "2885")
    assert len(inst.options["RELIANCE"]) == 2 and inst.lot_size("RELIANCE") == 500
    from optbot.strategy import single_candidates
    picks = single_candidates(inst, "RELIANCE", "long", 1405.0, date(2026, 12, 29))
    assert [c.strike for c in picks] == [1400.0, 1420.0]


def test_single_option_round_trip_and_exits(tmp_path):
    from optbot.messages import entry_message, exit_message
    from optbot.strategy import choose_single
    acct = PaperAccount("option_buyer", 20000, tmp_path / "b.json")
    broker = PaperBroker(CFG["charges"], {"slippage_ticks": 1}, SimClock(datetime(2026, 11, 18, 10, 0, tzinfo=IST)))
    c = _contract(26000, "CE", "T1")
    prof = profile("option_buyer")
    cand, why = choose_single([c], {"T1": Quote("T1", 100, 99.5, 100.5)}, prof, 5.0, 1)
    assert cand and cand.cost_per_lot <= 8000
    pos = broker.open_single(acct, "NIFTY", "long", c, 1, {"T1": Quote("T1", 100, 99.5, 100.5)}, {})
    assert pos and len(pos.legs) == 1 and pos.width == 0
    assert "Place this 1 order" in entry_message(pos, 0.3, 1.0, None, "test")
    assert liquidation_value(pos, {"T1": Quote("T1", 150, 149.5, 150.5)}) == 149.5
    cal = MarketCalendar(CFG["market"])
    now = datetime(2026, 11, 18, 11, 0, tzinfo=IST)
    assert exit_reason(pos, 150.0, now, prof, cal, [], CFG["strategy"]) is None   # no "max profit" cap on a bought option
    assert broker.close_position(acct, pos, {"T1": Quote("T1", 150, 149.5, 150.5)}, "test")
    assert pos.realized_pnl() > 0 and "SELL NIFTY" in exit_message(pos, "test")
    too_dear, why = choose_single([c], {"T1": Quote("T1", 200, 199.5, 200.5)}, prof, 5.0, 1)
    assert too_dear is None and "above" in why
