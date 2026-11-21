"""Hold winners longer when the move is strong? (Chinmay's 19 Nov Bank Nifty signal ran through TP1, TP2 and TP3.)

Rules G and R (1-hour) and the strict 15-minute rule D. Exits compared:
  * all at TP1, same day (live now)
  * TP1 then run to TP3 (stop moves to entry at TP1), up to 1 / 2 / 3 days
  * the same, but only on strong-trend trades (ADX(14) on the 1-hour chart above 25); other trades exit at TP1
  * half at TP1, trail the rest, up to 2 days
Rupees per trade per lot (ATM option bought, delta 0.5, costs and overnight decay), last year vs the 2 years before.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edge_study as es  # noqa: E402
import sniper_study as ss  # noqa: E402


def adx(bars, n=14):
    h = [b.h for b in bars]
    lo = [b.l for b in bars]
    a = ss.atr(bars, n)
    sp = sn = ax = None
    out = []
    for i in range(len(bars)):
        up = h[i] - h[i - 1] if i else 0
        dn = lo[i - 1] - lo[i] if i else 0
        pdm = up if up > dn and up > 0 else 0
        ndm = dn if dn > up and dn > 0 else 0
        sp = pdm if sp is None else sp + (pdm - sp) / n
        sn = ndm if sn is None else sn + (ndm - sn) / n
        p_, m_ = 100 * sp / (a[i] or 1e-9), 100 * sn / (a[i] or 1e-9)
        dx = 100 * abs(p_ - m_) / (p_ + m_) if p_ + m_ else 0
        ax = dx if ax is None else ax + (dx - ax) / n
        out.append(ax)
    return out


def analyze(data: Path, test_days: int = 250) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    idx = [k for k in es.INDEX_NAMES if k in lots and (data / f"{k}_5m.csv").exists() and lots[k][0] > 0]
    out = ["# Hold winners longer on strong moves?", "",
           "| Rule | Exit | Last year | 2 years before |", "|---|---|---|---|"]
    cost = ss.COST_RS["index"]
    setups = {}
    for k in idx:
        b5 = ss.load_bars(data / f"{k}_5m.csv")
        days = sorted({b.ts.date() for b in b5})
        cut = days[-test_days]
        for tf, rules in ((60, ("G", "R")), (15, ("D",))):
            h1, h2 = ss.TIMEFRAMES[tf]
            bt = ss.resample(b5, tf)
            at = ss.atr(bt)
            sigs = ss.make_signals(bt, ss.resample(b5, h1), ss.resample(b5, h2), h1, h2, tf)
            # strength from the 1-hour ADX at the bar's time
            b60 = ss.resample(b5, 60)
            ad60 = adx(b60)
            j, strong = 0, []
            for x in bt:
                while j + 1 < len(b60) and b60[j + 1].ts <= x.ts:
                    j += 1
                strong.append(ad60[j] > 25)
            for r in rules:
                fn = next(f for kk, f in sigs.items() if kk.startswith(r + " "))
                setups.setdefault(r, []).append((k, bt, at, fn, strong, tf, cut))
    variants = [("all at TP1, same day (live now)", "tp1", 1, False),
                ("TP1 then run to TP3, same day", "run", 1, False),
                ("TP1 then run to TP3, up to 2 days", "run", 2, False),
                ("TP1 then run to TP3, up to 3 days", "run", 3, False),
                ("half at TP1, trail rest, up to 2 days", "half", 2, False),
                ("strong trend (1h ADX>25): run to TP3 up to 2 days; else TP1", "run", 2, True),
                ("strong trend: half at TP1 + trail up to 2 days; else TP1", "half", 2, True)]
    for r, items in setups.items():
        for label, mode, md, only_strong in variants:
            te, tr = [], []
            for k, bt, at, fn, strong, tf, cut in items:
                lot = lots[k][0]
                if only_strong:
                    f_s = (lambda f, s: (lambda i: f(i) if s[i] else 0))(fn, strong)
                    f_w = (lambda f, s: (lambda i: 0 if s[i] else f(i)))(fn, strong)
                    trs = ss.backtest(bt, at, f_s, 1.5 if tf == 60 else 1.0, mode, md, tf, 2.0) + \
                        ss.backtest(bt, at, f_w, 1.5 if tf == 60 else 1.0, "tp1", 1, tf, 2.0)
                else:
                    trs = ss.backtest(bt, at, fn, 1.5 if tf == 60 else 1.0, mode, md, tf, 2.0)
                for t in trs:
                    (te if t.day >= cut else tr).append(ss.rupees(t, lot, cost))
            out.append(f"| {r} | {label} | {es.summ(te)} | {es.summ(tr)} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="sniper_data")
    ap.add_argument("--report", default="hold_report.md")
    a = ap.parse_args()
    rep = analyze(Path(a.data))
    Path(a.report).write_text(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
