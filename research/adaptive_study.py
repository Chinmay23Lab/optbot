"""3-year test of the adaptive day-type account (optbot/adaptive.py) on the index 5-minute history.

Variants: trend days only, range days only, both. Exits: the rule's own stop and target, else 15:10 square-off.
Rupees per lot of an ATM option bought (delta 0.5), after ₹150 charges. Last 250 trading days vs the 2 years before.
Usage: python research/adaptive_study.py --data sniper_data --report adaptive_report.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import edge_study as es  # noqa: E402
import sniper_study as ss  # noqa: E402
from optbot.adaptive import Adaptive  # noqa: E402


def sim(b15, modes):
    ad = Adaptive(b15, modes)
    out, i, n = [], 0, len(b15)
    while i < n:
        d, why, stop, tgt = ad.signal(i)
        if not d:
            i += 1
            continue
        entry, day, m, px = b15[i].c, b15[i].ts.date(), i + 1, None
        while m < n:
            x = b15[m]
            if x.ts.date() != day:
                px, m = b15[m - 1].c, m - 1
                break
            if (x.l <= stop) if d == 1 else (x.h >= stop):
                px = min(stop, x.o) if d == 1 else max(stop, x.o)
                break
            if (x.h >= tgt) if d == 1 else (x.l <= tgt):
                px = tgt
                break
            if (x.ts + timedelta(minutes=15)).time() >= ss.SQUARE_OFF:
                px = x.c
                break
            m += 1
        if px is None:
            px, m = b15[-1].c, n - 1
        out.append((day, d * (px - entry), why.split(":")[0]))
        i = m + 1
    return out


def analyze(data: Path, test_days: int = 250) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    idx = [k for k in es.INDEX_NAMES if k in lots and (data / f"{k}_5m.csv").exists() and lots[k][0] > 0]
    cost = ss.COST_RS["index"]
    series = {}
    for k in idx:
        b5 = ss.load_bars(data / f"{k}_5m.csv")
        days = sorted({b.ts.date() for b in b5})
        series[k] = (ss.resample(b5, 15), days[-test_days])
    out = ["# Adaptive day-type account: 3-year test", "",
           "Rupees per trade per lot, after charges (ATM option bought). Last year = last 250 trading days.", "",
           "| Variant | Trade type | Last year | 2 years before | Total ₹ last year |", "|---|---|---|---|---|"]
    for label, modes in (("both", ("trend", "range")), ("trend days only", ("trend",)), ("range days only", ("range",))):
        by = {}
        for k, (b15, cut) in series.items():
            lot = lots[k][0]
            for day, pts, kind in sim(b15, modes):
                rs = pts * ss.OPTION_DELTA * lot - cost
                for key in ("all", kind):
                    te, tr = by.setdefault(key, ([], []))
                    (te if day >= cut else tr).append(rs)
        for key, (te, tr) in by.items():
            out.append(f"| {label} | {key} | {es.summ(te)} | {es.summ(tr)} | {sum(te):+,.0f} |")
        for k, (b15, cut) in series.items():
            lot = lots[k][0]
            te = [p * ss.OPTION_DELTA * lot - cost for day, p, _ in sim(b15, modes) if day >= cut]
            tr = [p * ss.OPTION_DELTA * lot - cost for day, p, _ in sim(b15, modes) if day < cut]
            out.append(f"| {label} | {k} only | {es.summ(te)} | {es.summ(tr)} | {sum(te):+,.0f} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="sniper_data")
    ap.add_argument("--report", default="adaptive_report.md")
    a = ap.parse_args()
    rep = analyze(Path(a.data))
    Path(a.report).write_text(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
