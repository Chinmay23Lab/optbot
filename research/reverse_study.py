"""Stop-and-reverse: when a bought call hits its stop, buy a put right away (and the other way round)?

Chinmay's 26 Nov question: the NIFTY CE hit its stop, then NIFTY fell ~250 points and the bot did nothing.
Live rules G and R (1-hour chart, stop 1.5 ATR, everything booked at TP1 = 2x the stop, same day). After a
stop-out, the variants take ONE reverse trade with the same stop/target sizes:
  * entry at the close of the bar that hit the stop (what the bot could really do: it acts on finished bars)
  * entry at the stop price itself (best case: instant reverse on the tick)
  * reverse only if the stop came before 14:00 / before 13:00
Rupees per lot of an ATM option bought, after charges. Last year vs the 2 years before.
Part 2 (Chinmay, 26 Nov 14:07: "don't wait for the stop; get into the reverse trade when the trend turns"):
the same 1-hour entries, followed on the 15-minute chart. If an early trend-turn sign appears while the trade
is open, exit at that 15-minute close (before the stop), and optionally buy the opposite side right away.
Turn signs tried: 15m EMA5/21 cross against, 15m Supertrend flip against, 15m strict D signal against,
15m close below the last 4 bars' low (above the high for a put).
Usage: python research/reverse_study.py --data sniper_data --report reverse_report.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edge_study as es  # noqa: E402
import sniper_study as ss  # noqa: E402

SL, TP = 1.5, 2.0


def run_trade(bars, at, i, d, entry, base):
    """One TP1 trade from bar i (entry already set). Returns (pts, exit_bar, hit_stop, stop_px)."""
    risk = SL * at[i]
    stop, tp1 = entry - d * risk, entry + d * TP * risk
    n, m, day = len(bars), i + 1, bars[i].ts.date()
    while m < n:
        x = bars[m]
        if x.ts.date() != day:
            return d * (bars[m - 1].c - entry), m - 1, False, stop
        if (x.l <= stop) if d == 1 else (x.h >= stop):
            px = min(stop, x.o) if d == 1 else max(stop, x.o)
            return d * (px - entry), m, True, px
        if (x.h >= tp1) if d == 1 else (x.l <= tp1):
            return d * (tp1 - entry), m, False, stop
        if (x.ts + timedelta(minutes=base)).time() >= ss.SQUARE_OFF:
            return d * (x.c - entry), m, False, stop
        m += 1
    return d * (bars[-1].c - entry), n - 1, False, stop


def sim(bars, at, sig, base, reverse: str | None, cutoff: time | None):
    """Returns list of (day, pts, is_reverse)."""
    out, i, n = [], 0, len(bars)
    while i < n:
        b = bars[i]
        done = (b.ts + timedelta(minutes=base)).time()
        d = sig(i) if ss.FIRST_ENTRY <= done <= ss.LAST_ENTRY else 0
        if not d:
            i += 1
            continue
        pts, m, stopped, px = run_trade(bars, at, i, d, b.c, base)
        out.append((b.ts.date(), pts, False))
        end = m
        if reverse and stopped and m < n:
            x = bars[m]
            when = (x.ts + timedelta(minutes=base)).time()
            if (cutoff is None or when <= cutoff) and when < ss.SQUARE_OFF:
                entry = x.c if reverse == "close" else px
                rp, m2, _, _ = run_trade(bars, at, m, -d, entry, base)
                if reverse == "stop":   # instant reverse also earns the stop bar's move from the stop to its close
                    rp += -d * (x.c - px)
                out.append((x.ts.date(), rp, True))
                end = m2
        i = end + 1
    return out


def turn_signs(b15):
    from optbot.sniper_rules import a15_for, supertrend_dir
    c = [b.c for b in b15]
    e5, e21 = ss.ema(c, 5), ss.ema(c, 21)
    st = supertrend_dir(b15, a15_for(b15), 3.0)
    return {
        "15m EMA5/21 cross against": lambda i, d: i > 0 and (e5[i] - e21[i]) * d < 0 <= (e5[i - 1] - e21[i - 1]) * d,
        "15m Supertrend flips against": lambda i, d: i > 0 and st[i] == -d and st[i - 1] == d,
        "15m close beyond last 4 bars": lambda i, d: i >= 4 and ((b15[i].c < min(x.l for x in b15[i - 4:i])) if d == 1
                                                                 else (b15[i].c > max(x.h for x in b15[i - 4:i]))),
    }, None


def sim_early(b15, sig15, risk_at, sign, reverse: bool):
    """Entries from the 1-hour rule mapped onto 15m bars. Exits: stop, TP1, square-off, or the turn sign."""
    out, i, n = [], 0, len(b15)
    while i < n:
        b = b15[i]
        done = (b.ts + timedelta(minutes=15)).time()
        d = sig15(i) if ss.FIRST_ENTRY <= done <= ss.LAST_ENTRY else 0
        if not d:
            i += 1
            continue
        is_rev, entry, risk = False, b.c, risk_at(i)
        while True:
            stop, tp1, day, m = entry - d * risk, entry + d * TP * risk, b15[i].ts.date(), i + 1
            px, turned = None, False
            while m < n:
                x = b15[m]
                if x.ts.date() != day:
                    px, m = b15[m - 1].c, m - 1
                    break
                if (x.l <= stop) if d == 1 else (x.h >= stop):
                    px = min(stop, x.o) if d == 1 else max(stop, x.o)
                    break
                if (x.h >= tp1) if d == 1 else (x.l <= tp1):
                    px = tp1
                    break
                if (x.ts + timedelta(minutes=15)).time() >= ss.SQUARE_OFF:
                    px = x.c
                    break
                if sign is not None and sign(m, d):
                    px, turned = x.c, True
                    break
                m += 1
            if px is None:
                px, m = b15[-1].c, n - 1
            out.append((b15[i].ts.date(), d * (px - entry), is_rev))
            when = (b15[m].ts + timedelta(minutes=15)).time()
            if reverse and turned and not is_rev and when <= ss.LAST_ENTRY:
                i, d, entry, is_rev = m, -d, b15[m].c, True   # buy the other side on the same bar
                continue
            break
        i = m + 1
    return out


def analyze_early(data: Path, lots, idx, test_days: int = 250) -> list[str]:
    cost = ss.COST_RS["index"]
    out = ["", "## Part 2: exit early when the 15-minute chart turns (before the stop), and flip", "",
           "| Rule | Exit | All trades, last year | All, 2 years before | Flip trades only, last year | "
           "Flip only, 2 years before | Total ₹ last year |", "|---|---|---|---|---|---|---|"]
    for r in ("G", "R"):
        setups = []
        for k in idx:
            b5 = ss.load_bars(data / f"{k}_5m.csv")
            days = sorted({b.ts.date() for b in b5})
            cut = days[-test_days]
            h1, h2 = ss.TIMEFRAMES[60]
            b60 = ss.resample(b5, 60)
            a60 = ss.atr(b60)
            fn = next(f for kk, f in ss.make_signals(b60, ss.resample(b5, h1), ss.resample(b5, h2), h1, h2, 60).items()
                      if kk.startswith(r + " "))
            b15 = ss.resample(b5, 15)
            # 15m bar j is the last one of 1-hour bar h when j ends where h ends
            pos = {x.ts: h for h, x in enumerate(b60)}
            last_of, hour_of = {}, []
            h = -1
            for j, x in enumerate(b15):
                start = x.ts.replace(minute=15) if x.ts.minute >= 15 else (x.ts - timedelta(hours=1)).replace(minute=15)
                h = pos.get(start, h)
                hour_of.append(h)
                if (x.ts + timedelta(minutes=15)) == start + timedelta(minutes=60) or \
                        (j + 1 < len(b15) and b15[j + 1].ts.date() != x.ts.date()):
                    last_of[j] = h
            sig15 = (lambda f, lo: (lambda j: f(lo[j]) if j in lo else 0))(fn, last_of)
            risk_at = (lambda a, ho: (lambda j: SL * a[ho[j]]))(a60, hour_of)
            signs, _ = turn_signs(b15)
            setups.append((k, b15, sig15, risk_at, signs, cut))
        names = list(setups[0][4]) if setups else []
        variants = [("no early exit (live now)", None, False)] + \
            [(f"{nm}: exit early", nm, False) for nm in names] + [(f"{nm}: exit early + flip", nm, True) for nm in names]
        for label, nm, rev in variants:
            te, tr, rte, rtr = [], [], [], []
            for k, b15, sig15, risk_at, signs, cut in setups:
                lot = lots[k][0]
                for day, pts, is_rev in sim_early(b15, sig15, risk_at, signs[nm] if nm else None, rev):
                    rs = pts * ss.OPTION_DELTA * lot - cost
                    (te if day >= cut else tr).append(rs)
                    if is_rev:
                        (rte if day >= cut else rtr).append(rs)
            out.append(f"| {r} | {label} | {es.summ(te)} | {es.summ(tr)} | {es.summ(rte)} | {es.summ(rtr)} | {sum(te):+,.0f} |")
    return out


def analyze(data: Path, test_days: int = 250) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    idx = [k for k in es.INDEX_NAMES if k in lots and (data / f"{k}_5m.csv").exists() and lots[k][0] > 0]
    cost = ss.COST_RS["index"]
    variants = [("no reverse (live now)", None, None),
                ("reverse at close of stop bar", "close", None),
                ("reverse at the stop price (instant)", "stop", None),
                ("reverse at close, only if stopped by 14:00", "close", time(14, 0)),
                ("reverse at close, only if stopped by 13:00", "close", time(13, 0))]
    out = ["# Stop-and-reverse after a stop-loss (1-hour rules G and R)", "",
           "Rupees per trade per lot, after charges. 'All trades' = the rule's trades plus the reverse trades; "
           "'reverse trades only' = just the extra put/call taken after a stop.", "",
           "| Rule | Variant | All trades, last year | All, 2 years before | Reverse trades only, last year | "
           "Reverse only, 2 years before | Total ₹ last year |",
           "|---|---|---|---|---|---|---|"]
    for r in ("G", "R"):
        setups = []
        for k in idx:
            b5 = ss.load_bars(data / f"{k}_5m.csv")
            days = sorted({b.ts.date() for b in b5})
            cut = days[-test_days]
            h1, h2 = ss.TIMEFRAMES[60]
            bt = ss.resample(b5, 60)
            at = ss.atr(bt)
            sigs = ss.make_signals(bt, ss.resample(b5, h1), ss.resample(b5, h2), h1, h2, 60)
            fn = next(f for kk, f in sigs.items() if kk.startswith(r + " "))
            setups.append((k, bt, at, fn, cut))
        for label, rev, cutoff in variants:
            te, tr, rte, rtr = [], [], [], []
            for k, bt, at, fn, cut in setups:
                lot = lots[k][0]
                for day, pts, is_rev in sim(bt, at, fn, 60, rev, cutoff):
                    rs = pts * ss.OPTION_DELTA * lot - cost
                    (te if day >= cut else tr).append(rs)
                    if is_rev:
                        (rte if day >= cut else rtr).append(rs)
            out.append(f"| {r} | {label} | {es.summ(te)} | {es.summ(tr)} | {es.summ(rte)} | {es.summ(rtr)} | "
                       f"{sum(te):+,.0f} |")
    out += analyze_early(data, lots, idx, test_days)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="sniper_data")
    ap.add_argument("--report", default="reverse_report.md")
    a = ap.parse_args()
    rep = analyze(Path(a.data))
    Path(a.report).write_text(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
