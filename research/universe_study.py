"""Rules G and R (1-hour chart) on a wide stock list, e.g. all Nifty 50 names.

Lighter than sniper_study.analyze: only the two live rules and the exits worth comparing, so 50 names fit in one
run. Same option model and costs as sniper_study. Last 250 trading days = "last year", the rest = "2 years before".
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sniper_study as ss  # noqa: E402

RULES = ("G", "R")
EXITS = [(1.5, "tp1", 1, 2.0, "all at TP1, same day (live now)"),
         (1.5, "half", 1, 2.0, "half at TP1, trail rest, same day"),
         (1.5, "tp1", 3, 2.0, "all at TP1, hold up to 3 days"),
         (1.5, "half", 3, 2.0, "half at TP1, trail rest, up to 3 days")]


def summ(rs):
    if len(rs) < 2:
        return "-"
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1))
    return f"{m:+,.0f} (n={len(rs)}, win {100 * sum(x > 0 for x in rs) / len(rs):.0f}%, t {m / (sd / math.sqrt(len(rs))) if sd else 0:.1f})"


def analyze(data: Path, test_days=250) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    pooled: dict = {}
    per: dict = {}
    for name, (lot, kind) in sorted(lots.items()):
        p = data / f"{name}_5m.csv"
        if kind != "stock" or lot <= 0 or not p.exists():
            continue
        b5 = ss.load_bars(p)
        days = sorted({b.ts.date() for b in b5})
        if len(days) < test_days + 100:
            continue
        cut = days[-test_days]
        h1, h2 = ss.TIMEFRAMES[60]
        bt = ss.resample(b5, 60)
        at = ss.atr(bt)
        sigs = ss.make_signals(bt, ss.resample(b5, h1), ss.resample(b5, h2), h1, h2, 60)
        for rule in RULES:
            fn = next(f for k, f in sigs.items() if k.startswith(rule + " "))
            for sl, mode, md, tp, label in EXITS:
                tr = ss.backtest(bt, at, fn, sl, mode, md, 60, tp)
                cost = ss.COST_RS[kind]
                te = [ss.rupees(t, lot, cost) for t in tr if t.day >= cut]
                trn = [ss.rupees(t, lot, cost) for t in tr if t.day < cut]
                k = (rule, label)
                pooled.setdefault(k, ([], []))
                pooled[k][0].extend(te)
                pooled[k][1].extend(trn)
                per.setdefault((name, rule, label), (te, trn))
    out = ["# Rules G and R on the wide stock list, 1-hour chart", "",
           "Rupees per trade per lot of an at-the-money stock option bought, after charges and overnight decay.", "",
           "## All stocks pooled", "", "| Rule | Exit | Last year | 2 years before |", "|---|---|---|---|"]
    for (rule, label), (te, trn) in pooled.items():
        out.append(f"| {rule} | {label} | {summ(te)} | {summ(trn)} |")
    out += ["", "## Per stock (live exit: all at TP1, same day)", "",
            "| Stock | Rule | Last year | 2 years before |", "|---|---|---|---|"]
    for (name, rule, label), (te, trn) in sorted(per.items()):
        if label == EXITS[0][4]:
            out.append(f"| {name} | {rule} | {summ(te)} | {summ(trn)} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="universe_data")
    ap.add_argument("--report", default="universe_report.md")
    a = ap.parse_args()
    rep = analyze(Path(a.data))
    Path(a.report).write_text(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
