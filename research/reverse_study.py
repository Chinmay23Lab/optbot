"""Stop-and-reverse: when a bought call hits its stop, buy a put right away (and the other way round)?

Chinmay's 26 Nov question: the NIFTY CE hit its stop, then NIFTY fell ~250 points and the bot did nothing.
Live rules G and R (1-hour chart, stop 1.5 ATR, everything booked at TP1 = 2x the stop, same day). After a
stop-out, the variants take ONE reverse trade with the same stop/target sizes:
  * entry at the close of the bar that hit the stop (what the bot could really do: it acts on finished bars)
  * entry at the stop price itself (best case: instant reverse on the tick)
  * reverse only if the stop came before 14:00 / before 13:00
Rupees per lot of an ATM option bought, after charges. Last year vs the 2 years before.
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
