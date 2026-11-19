"""Chinmay's friend's two TradingView strategies, rebuilt and tested on NIFTY and BANKNIFTY (19 Nov 2026).

1. "EMA/ADX": EMA9 crosses EMA21, ADX(14) > 20, DI+ > DI- (or reverse), RSI < 70 (> 30), Stoch RSI < 80 (> 20),
   close inside the Bollinger band. Stop and target both 1.5 ATR (as written), plus wider-target variants.
   Note: the script calls ta.stoch(rsi, 14, 3, 3), which in Pine means stoch(source=rsi, high=14, low=3, length=3);
   that is almost certainly a typo, so the standard Stoch RSI (14, smoothed 3) is used.
2. "BB reversal": after a close at/below the lower band, buy when price closes back inside (sell mirror at the upper
   band). The script has no stop or target (it only reverses), so we test: reverse on the opposite signal, and fixed
   ATR stops/targets.
Same costs and option model as sniper_study.py; last 250 trading days = "last year", the rest = "2 years before".
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sniper_study as ss  # noqa: E402

NAMES = ("NIFTY", "BANKNIFTY")


def rma(xs, n):
    out, a = [], None
    for x in xs:
        a = x if a is None else a + (x - a) / n
        out.append(a)
    return out


def dmi_adx(bars, n=14):
    pdm, mdm, tr = [0.0], [0.0], [bars[0].h - bars[0].l]
    for i in range(1, len(bars)):
        up, dn = bars[i].h - bars[i - 1].h, bars[i - 1].l - bars[i].l
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
        tr.append(max(bars[i].h - bars[i].l, abs(bars[i].h - bars[i - 1].c), abs(bars[i].l - bars[i - 1].c)))
    atr_, p_, m_ = rma(tr, n), rma(pdm, n), rma(mdm, n)
    pdi = [100 * p / a if a else 0 for p, a in zip(p_, atr_)]
    mdi = [100 * m / a if a else 0 for m, a in zip(m_, atr_)]
    dx = [100 * abs(p - m) / (p + m) if p + m else 0 for p, m in zip(pdi, mdi)]
    return pdi, mdi, rma(dx, n)


def stdev(xs, n):
    out = []
    for i in range(len(xs)):
        w = xs[max(0, i - n + 1):i + 1]
        m = sum(w) / len(w)
        out.append(math.sqrt(sum((x - m) ** 2 for x in w) / len(w)))
    return out


def stoch_rsi(r, n=14, k=3):
    raw = []
    for i in range(len(r)):
        w = r[max(0, i - n + 1):i + 1]
        lo, hi = min(w), max(w)
        raw.append(100 * (r[i] - lo) / (hi - lo) if hi > lo else 50)
    return ss.sma(raw, k)


def signals(b):
    c = [x.c for x in b]
    e9, e21 = ss.ema(c, 9), ss.ema(c, 21)
    r = ss.rsi(c, 14)
    st = stoch_rsi(r)
    pdi, mdi, adx = dmi_adx(b)
    mid, sd = ss.sma(c, 20), stdev(c, 20)
    up = [m + 2 * s for m, s in zip(mid, sd)]
    lo = [m - 2 * s for m, s in zip(mid, sd)]

    def ema_adx(i):
        if i < 50:
            return 0
        if e9[i - 1] <= e21[i - 1] and e9[i] > e21[i] and adx[i] > 20 and pdi[i] > mdi[i] and r[i] < 70 and st[i] < 80 and c[i] < up[i]:
            return 1
        if e9[i - 1] >= e21[i - 1] and e9[i] < e21[i] and adx[i] > 20 and mdi[i] > pdi[i] and r[i] > 30 and st[i] > 20 and c[i] > lo[i]:
            return -1
        return 0

    # BB reversal: armed by a close outside the band, fires on the first close back inside
    bb = [0] * len(b)
    armed_l = armed_s = False
    for i in range(20, len(b)):
        if c[i] <= lo[i]:
            armed_l = True
        elif armed_l:
            bb[i], armed_l = 1, False
        if c[i] >= up[i]:
            armed_s = True
        elif armed_s:
            bb[i], armed_s = -1, False
    return {"Friend 1: EMA9/21 + ADX/DMI + RSI/StochRSI/BB": ema_adx,
            "Friend 2: Bollinger band re-entry": lambda i: bb[i] if i >= 50 else 0}


def summ(items):
    rs = [ss.rupees(t, lot, cost) for t, lot, cost in items]
    if not rs:
        return "-"
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / max(1, len(rs) - 1))
    return f"{m:+,.0f} (n={len(rs)}, win {100 * sum(x > 0 for x in rs) / len(rs):.0f}%, t {m / (sd / math.sqrt(len(rs))) if sd else 0:.1f})"


def analyze(data: Path, test_days=250) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    # (sl_atr, mode, tp_step): as written = SL 1.5 ATR, TP 1.5 ATR -> tp_step 1.0; plus 2x target; plus reverse-only
    variants = [(1.5, "tp1", 1.0, "as written: SL 1.5 ATR, target 1.5 ATR"),
                (1.5, "tp1", 2.0, "SL 1.5 ATR, target 3 ATR"),
                (1.5, "flip", 2.0, "SL 1.5 ATR, hold till opposite signal")]
    test, train = {}, {}
    for name in NAMES:
        if name not in lots:
            continue
        lot, kind = lots[name]
        b5 = ss.load_bars(data / f"{name}_5m.csv")
        days = sorted({x.ts.date() for x in b5})
        cut = days[-test_days]
        for tf in (5, 15, 30, 60):
            bt = b5 if tf == 5 else ss.resample(b5, tf)
            at = ss.atr(bt)
            for sname, fn in signals(bt).items():
                for sl, mode, tp, label in variants:
                    tr = ss.backtest(bt, at, fn, sl, mode, 1, tf, tp)
                    key = (sname, f"{tf}m", label)
                    test.setdefault(key, []).extend((t, lot, ss.COST_RS[kind]) for t in tr if t.day >= cut)
                    train.setdefault(key, []).extend((t, lot, ss.COST_RS[kind]) for t in tr if t.day < cut)
    lines = ["# Friend's two strategies on NIFTY + BANKNIFTY, 3 years", "",
             "Rupees per trade per lot of an at-the-money option bought, after charges. Same-day exits.", "",
             "| Strategy | Chart | Exit | Last year | 2 years before |", "|---|---|---|---|---|"]
    for key in test:
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {summ(test[key])} | {summ(train.get(key, []))} |")
    lines += ["", "For comparison, the bot's current 1-hour rules on all names: +₹366 / +₹374 (candle), +₹536 / +₹563 (breakout)."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="sniper_data")
    ap.add_argument("--report", default="friend_report.md")
    a = ap.parse_args()
    rep = analyze(Path(a.data))
    Path(a.report).write_text(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
