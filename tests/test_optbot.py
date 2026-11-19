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
    rm = RiskManager(profile("target_5k", max_risk_per_trade=2000, max_debit_per_lot=4000))
    rm.new_day(date(2026, 11, 17))
    assert rm.update_day(5200) is None and not rm.state.stopped
    assert rm.update_day(6000) is None
    assert rm.update_day(4700) is not None  # below 80% of the ₹6,000 peak


def test_sizing_respects_risk_and_cash():
    rm = RiskManager(profile("target_5k", max_risk_per_trade=2000, max_debit_per_lot=4000))
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
    assert exit_reason(_pos(), v, t, profile("conservative", style="spread", exit_mode="target", target_pct_of_max_profit=0.60), mkt, [], CFG["strategy"]) == "profit target"
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


def test_tv_command_paper_trades_your_signal(tmp_path):
    from optbot.engine import Engine
    from optbot.instruments import Instruments
    from optbot.journal import Journal
    from optbot.notify import Notifier
    from optbot.sim import SimMarket, synthetic_rows
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(dict(CFG)))
    cfg = load_config(p)
    d = date(2026, 11, 18)
    clock = SimClock(datetime(2026, 11, 18, 10, 30, tzinfo=IST))
    inst = Instruments(synthetic_rows(cfg["indices"], d), cfg["indices"], cfg["vix"]["names"])
    eng = Engine(cfg, SimMarket(clock, inst, seed=3), inst, clock, Notifier(), Journal(cfg.data_dir / "journal.sqlite"))
    eng.start_day(d)
    assert "Send it like this" in eng.cmd_tv("hello")
    out = eng.cmd_tv("nifty up")
    tv = next(b for b in eng.books if b.profile.name == "tradingview")
    assert len(tv.account.open) == 1, out
    assert tv.account.open[0].legs[0].contract.right == "CE"
    eng.cmd_tv("NIFTY down")   # flip: closes the call, buys a put
    assert [p.legs[0].contract.right for p in tv.account.open] == ["PE"]
    assert all(not b.account.open for b in eng.books if b.profile.name != "tradingview")


def test_sniper_live_signal_matches_backtest_rules_without_lookahead():
    import random as _r
    from datetime import timedelta
    from optbot.sniper_rules import Bar, live_signal, make_signals, resample
    rnd = _r.Random(4)
    p, c5, d = 22000.0, [], date(2026, 9, 1)
    while len(c5) < 75 * 40:
        if d.weekday() < 5:
            for k in range(75):
                o = p
                p *= 1 + rnd.gauss(0, 0.0015)
                t = datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST) + timedelta(minutes=5 * k)
                c5.append(Candle(t, o, max(o, p) + 2, min(o, p) - 2, p))
        d += timedelta(days=1)
    b5 = [Bar(c.ts.replace(tzinfo=None), c.open, c.high, c.low, c.close) for c in c5]
    b15 = resample(b5, 15)
    full = make_signals(b15, resample(b5, 30), resample(b5, 60), 30, 60, 15)
    fa = next(v for k, v in full.items() if k.startswith("A"))
    hits = checked = 0
    for i in range(len(b15) - 150, len(b15)):
        end = b15[i].ts + timedelta(minutes=15)
        upto = [c for c in c5 if c.ts.replace(tzinfo=None) + timedelta(minutes=5) <= end]
        dlive, *_ = live_signal(upto, end.replace(tzinfo=IST), "A", 15)
        assert dlive == fa(i), i
        checked += 1
        hits += bool(dlive)
    assert checked == 150 and hits > 0


def test_loss_cap_keeps_bought_options_open_but_blocks_new_trades(tmp_path):
    """18 Nov: Bharti 2120 PE was force-closed by the account's daily loss cap, then rallied 10.40 -> 14.40."""
    from optbot.engine import Engine
    from optbot.instruments import Instruments
    from optbot.journal import Journal
    from optbot.notify import Notifier
    from optbot.sim import SimMarket, synthetic_rows
    assert profile("option_buyer").closes_open_on_loss_cap() is False
    assert profile("conservative", style="spread").closes_open_on_loss_cap() is True
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(dict(CFG)))
    cfg = load_config(p)
    d = date(2026, 11, 18)
    clock = SimClock(datetime(2026, 11, 18, 10, 30, tzinfo=IST))
    inst = Instruments(synthetic_rows(cfg["indices"], d), cfg["indices"], cfg["vix"]["names"])
    eng = Engine(cfg, SimMarket(clock, inst, seed=3), inst, clock, Notifier(), Journal(cfg.data_dir / "journal.sqlite"))
    eng.start_day(d)
    eng.cmd_tv("nifty up")
    tv = next(b for b in eng.books if b.profile.name == "tradingview")
    assert len(tv.account.open) == 1
    tv.profile.daily_loss_cap = -1e9      # any P&L now counts as "cap hit"
    eng.tick()
    assert len(tv.account.open) == 1, "bought option must keep running to its own stop"
    assert tv.risk.state.stopped and "daily loss cap" in tv.risk.state.stop_reason


def test_patterns_use_no_future_bars():
    import random as _r
    from datetime import timedelta as _td
    from optbot.patterns import candle_patterns_full, chart_patterns
    from optbot.sniper_rules import Bar, atr
    _r.seed(4)
    bars, p, t = [], 100.0, datetime(2026, 1, 1, 9, 15)
    for k in range(400):
        o = p + _r.gauss(0, 0.3)
        p = o + _r.gauss(0, 1)
        bars.append(Bar(t + _td(minutes=60 * k), o, max(o, p) + abs(_r.gauss(0, .5)), min(o, p) - abs(_r.gauss(0, .5)), p))
    full_c, full_ch = candle_patterns_full(bars), chart_patterns(bars, atr(bars))
    for cut in (150, 260, 399):
        part = bars[:cut + 1]
        pc, pch = candle_patterns_full(part), chart_patterns(part, atr(part))
        for k in pc:
            assert pc[k][cut] == full_c[k][cut], k
        for k in pch:
            assert pch[k][cut] == full_ch[k][cut], k


def test_scalper_signal_matches_study_and_uses_no_future_bars():
    import random as _r
    import sys
    from datetime import timedelta
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
    import scalper_study as scs
    from optbot.sniper_rules import Bar, resample, scalper_signal
    rnd = _r.Random(7)
    p, c5, d = 1500.0, [], date(2026, 9, 1)
    while len(c5) < 75 * 25:
        if d.weekday() < 5:
            for k in range(75):
                o = p
                p *= 1 + rnd.gauss(0.0001, 0.002)
                t = datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST) + timedelta(minutes=5 * k)
                c5.append(Candle(t, o, max(o, p) + 0.5, min(o, p) - 0.5, p))
        d += timedelta(days=1)
    b5 = [Bar(c.ts.replace(tzinfo=None), c.open, c.high, c.low, c.close) for c in c5]
    b15 = resample(b5, 15)
    trig = scs.triggers(b15, "pb")
    tr = scs.trend_1h(b5)
    hits = 0
    for i in range(len(b15) - 120, len(b15)):
        end = b15[i].ts + timedelta(minutes=15)
        trend = 0
        for t_end, v in tr:
            if t_end <= end:
                trend = v
        want = trend if trend and trig[i] == trend else 0
        upto = [c for c in c5 if c.ts.replace(tzinfo=None) + timedelta(minutes=5) <= end]
        got, why = scalper_signal(upto, end.replace(tzinfo=IST), 15, "pb")
        assert got == want, (i, why)
        hits += bool(got)
    assert hits > 0


def test_scalper_exits_on_option_price_and_time():
    from types import SimpleNamespace
    from optbot.engine import Engine
    now = datetime(2026, 11, 20, 10, 0, tzinfo=IST)
    meta = {"o_tp": 120.0, "o_sl": 90.0, "tp_pct": 0.2, "sl_pct": 0.1, "time_min": 15,
            "t_exit": datetime(2026, 11, 20, 10, 15, tzinfo=IST).isoformat()}
    pos = SimpleNamespace(meta=meta, entry_debit=100.0)
    ex = Engine._premium_exit
    assert ex(None, pos, 121, now).startswith("target")
    assert ex(None, pos, 89, now).startswith("stop")
    assert ex(None, pos, 105, now) is None
    assert ex(None, pos, 105, now.replace(minute=15)).startswith("time stop")
    assert profile("scalper").entry_signal == "scalper"


def test_tip_tracker_entry_targets_and_closing_stop():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
    from tips_tracker import evaluate
    t0 = datetime(2026, 11, 19, 13, 10, tzinfo=IST)
    from datetime import timedelta as td
    mk = lambda k, o, h, l, c, day=0: (t0 + td(days=day, minutes=5 * k), o, h, l, c)  # noqa: E731
    tip = {"above": 60, "sl": 45, "sl_close": True, "targets": [75, 90]}
    # dips below SL intraday but closes above it: closing-basis stop must NOT trigger
    r = evaluate(tip, [mk(0, 58, 61, 57, 60), mk(1, 60, 62, 44, 50), mk(2, 50, 76, 50, 74)])
    assert r["entry"] == 60 and r["exit"] is None and r["hits"] == [0]
    r = evaluate(tip, [mk(0, 58, 61, 57, 60), mk(1, 60, 60, 40, 44)])
    assert r["status"].startswith("stop-loss") and r["exit"] == 44
    r = evaluate(tip, [mk(0, 58, 61, 57, 60), mk(1, 60, 91, 59, 88)])
    assert r["status"] == "all targets hit" and r["exit"] == 90
    assert evaluate(tip, [mk(0, 50, 55, 49, 52)])["entry"] is None
