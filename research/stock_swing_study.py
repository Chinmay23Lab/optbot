"""Positional (multi-day) stock-option trades on the DAILY chart, with next-month expiry.

Chinmay, 19 Nov: the tip-channel calls are positional (hold days, monthly expiry) and come out ahead overall.
Signals on daily bars; entry at the signal day's close; stop and targets on the stock price; hold up to N days.
Option model: ATM next-month option, moves 0.5 x the stock; decay ≈ 0.045% of the stock price per night
(an ATM option with ~30-45 days left loses about 1/(2*days) of its value a day). Costs ₹350 per lot.
Last 250 trading days = "last year", the rest = "2 years before". Ranked by the worse of the two periods.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sniper_study as ss  # noqa: E402

THETA = 0.00045
COST = 350.0


def daily(b5):
    out, cur = [], None
    for x in b5:
        if cur is None or x.ts.date() != cur.ts.date():
            if cur:
                out.append(cur)
            cur = ss.Bar(x.ts, x.o, x.h, x.l, x.c)
        else:
            cur = ss.Bar(cur.ts, cur.o, max(cur.h, x.h), min(cur.l, x.l), x.c)
    if cur:
        out.append(cur)
    return out


def signals(d):
    c = [x.c for x in d]
    e9, e21, s50 = ss.ema(c, 9), ss.ema(c, 21), ss.sma(c, 50)
    r = ss.rsi(c, 14)
    hi20 = [max(x.h for x in d[max(0, i - 20):i]) if i else 0 for i in range(len(d))]
    lo20 = [min(x.l for x in d[max(0, i - 20):i]) if i else 0 for i in range(len(d))]

    def brk(i):   # 20-day breakout in the direction of the 50-day trend
        if i < 60:
            return 0
        if c[i] > hi20[i] and c[i] > s50[i]:
            return 1
        if c[i] < lo20[i] and c[i] < s50[i]:
            return -1
        return 0

    def cross(i):  # daily EMA9/21 cross with the 50-day trend
        if i < 60:
            return 0
        if e9[i - 1] <= e21[i - 1] and e9[i] > e21[i] and c[i] > s50[i]:
            return 1
        if e9[i - 1] >= e21[i - 1] and e9[i] < e21[i] and c[i] < s50[i]:
            return -1
        return 0

    def pullback(i):  # uptrend (EMA9>21>SMA50), RSI dipped under 45 and turns up today (mirror for down)
        if i < 60:
            return 0
        if e9[i] > e21[i] > s50[i] and r[i - 1] < 45 <= r[i]:
            return 1
        if e9[i] < e21[i] < s50[i] and r[i - 1] > 55 >= r[i]:
            return -1
        return 0
    return {"20-day breakout with 50-day trend": brk, "daily EMA9/21 cross with trend": cross,
            "pullback in trend (RSI turn)": pullback}


def backtest(d, a, fn, sl_atr, tp_mult, max_days):
    out, i = [], 0
    while i < len(d) - 1:
        s = fn(i)
        if not s or a[i] <= 0:
            i += 1
            continue
        entry, risk = d[i].c, sl_atr * a[i]
        stop, tgt = entry - s * risk, entry + s * tp_mult * risk
        exit_px, k = None, i + 1
        while k < len(d) and k - i <= max_days:
            x = d[k]
            if (x.l <= stop) if s == 1 else (x.h >= stop):
                exit_px = min(stop, x.o) if s == 1 else max(stop, x.o)
                break
            if (x.h >= tgt) if s == 1 else (x.l <= tgt):
                exit_px = max(tgt, x.o) if s == 1 else min(tgt, x.o)
                break
            k += 1
        k = min(k, len(d) - 1)
        if exit_px is None:
            exit_px = d[k].c
        out.append((d[i].ts.date(), s * (exit_px - entry), k - i, entry))
        i = k + 1
    return out


def summ(rs):
    if len(rs) < 2:
        return "-"
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1))
    return f"{m:+,.0f} (n={len(rs)}, win {100 * sum(x > 0 for x in rs) / len(rs):.0f}%, t {m / (sd / math.sqrt(len(rs))) if sd else 0:.1f})"


def analyze(data: Path, test_days=250, only=None) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    grid = [(sl, tp, md) for sl in (1.0, 1.5, 2.0) for tp in (1.5, 2.0, 3.0) for md in (3, 5, 10)]
    res = defaultdict(lambda: ([], []))
    for name, (lot, kind) in lots.items():
        if kind != "stock" or lot <= 0 or (only and name not in only):
            continue
        p = data / f"{name}_5m.csv"
        if not p.exists():
            continue
        d = daily(ss.load_bars(p))
        if len(d) < test_days + 100:
            continue
        cut = d[-test_days].ts.date()
        a = ss.atr(d)
        for sname, fn in signals(d).items():
            for g in grid:
                for day, pts, nights, entry in backtest(d, a, fn, *g):
                    r = pts * 0.5 * lot - COST - nights * THETA * entry * lot
                    res[(sname,) + g][0 if day >= cut else 1].append(r)
    rows = sorted(((min(sum(te) / len(te), sum(tr) / len(tr)), k, te, tr) for k, (te, tr) in res.items()
                   if len(te) >= 20 and len(tr) >= 20), key=lambda r: -r[0])
    out = ["# Positional stock-option trades on the daily chart (next-month expiry)", "",
           "₹ per trade per lot after charges and decay. Ranked by the worse of the two periods.", "",
           "| Signal | Stop (daily ATR) | Target (x stop) | Max days | Last year | 2 years before |", "|---|---|---|---|---|---|"]
    for _, (sname, sl, tp, md), te, tr in rows[:25]:
        out.append(f"| {sname} | {sl} | {tp} | {md} | {summ(te)} | {summ(tr)} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="universe_data")
    ap.add_argument("--report", default="stock_swing_report.md")
    a = ap.parse_args()
    rep = analyze(Path(a.data))
    Path(a.report).write_text(rep)
    print(rep)
    rep10 = analyze(Path(a.data), only={"RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "INFY", "TCS", "AXISBANK",
                                        "KOTAKBANK", "BHARTIARTL", "LT"})
    print("\n## Same, 10 big stocks only\n" + rep10.split("\n", 4)[4])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
