"""Test every coded candlestick and chart pattern on the price history fetched by sniper_study.py.

For each pattern, on the 30-minute and 1-hour charts:
  * "D + pattern": the current 1-hour signal (EMA cross + MACD, RSI, Supertrend, VWMA, pivot) AND the pattern
    on the signal bar or the bar before;
  * "pattern + trend + all 5": the pattern itself is the entry, if the 100/200 EMA trend and all 5 checks agree.
One exit only (the bot's current one: stop 1.5 ATR, book everything at TP1 = 2x the stop, same day), so the
number of settings tried stays small. Ranked by the WORSE of last year and the 2 years before.
Usage: python research/pattern_study.py --data sniper_data --report pattern_report.md
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sniper_study as ss  # noqa: E402
from optbot.patterns import candle_patterns_full, chart_patterns  # noqa: E402
from optbot.sniper_rules import TIMEFRAMES  # noqa: E402

SL, MODE, DAYS, TP = 1.5, "tp1", 1, 2.0


def summ(items):
    rs = [ss.rupees(t, lot, cost) for t, lot, cost in items]
    if not rs:
        return 0.0, 0, 0.0, 0.0
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / max(1, len(rs) - 1))
    return m, len(rs), 100 * sum(x > 0 for x in rs) / len(rs), (m / (sd / math.sqrt(len(rs))) if sd else 0.0)


def analyze(data: Path, test_days: int = 250, tfs=(30, 60)) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    test, train, kinds = {}, {}, {}
    for name, (lot, kind) in lots.items():
        p = data / f"{name}_5m.csv"
        if not p.exists() or lot <= 0:
            continue
        b5 = ss.load_bars(p)
        days = sorted({b.ts.date() for b in b5})
        if len(days) < test_days + 100:
            continue
        cut = days[-test_days]
        for tf in tfs:
            h1, h2 = TIMEFRAMES[tf]
            bt = b5 if tf == 5 else ss.resample(b5, tf)
            at = ss.atr(bt)
            cp, ch = candle_patterns_full(bt), chart_patterns(bt, at)
            kinds.update({k: "candle" for k in cp})
            kinds.update({k: "chart" for k in ch})
            sigs = ss.make_signals(bt, ss.resample(b5, h1), ss.resample(b5, h2), h1, h2, tf, extra={**cp, **ch})
            for sname, fn in sigs.items():
                tr = ss.backtest(bt, at, fn, SL, MODE, DAYS, tf, TP)
                key = f"{tf}m {sname}"
                cost = ss.COST_RS[kind]
                test.setdefault(key, []).extend((t, lot, cost) for t in tr if t.day >= cut)
                train.setdefault(key, []).extend((t, lot, cost) for t in tr if t.day < cut)
    rows = []
    for key in test:
        m1, n1, w1, t1 = summ(test[key])
        m0, n0, w0, t0 = summ(train.get(key, []))
        rows.append((key, m1, n1, w1, t1, m0, n0, t0))
    lines = ["# Every candlestick and chart pattern, 3-year test", "",
             f"Exit for all: stop {SL} ATR, book everything at TP1 ({TP}x the stop), same day. Rupees per lot of an "
             "at-the-money option bought, after charges. Last year = last 250 trading days.", "",
             "## Ranked by the worse of the two periods (at least 30 trades in each)", "",
             "| Rule | Last year ₹/trade | trades | win % | t | 2 years before ₹/trade | trades | t |",
             "|---|---|---|---|---|---|---|---|"]
    ok = sorted([r for r in rows if r[2] >= 30 and r[6] >= 30], key=lambda r: -min(r[1], r[5]))
    for key, m1, n1, w1, t1, m0, n0, t0 in ok:
        lines.append(f"| {key} | {m1:+,.0f} | {n1} | {w1:.0f}% | {t1:.1f} | {m0:+,.0f} | {n0} | {t0:.1f} |")
    few = [r for r in rows if not (r[2] >= 30 and r[6] >= 30)]
    lines += ["", f"## Too rare to judge (fewer than 30 trades in a period): {len(few)} rules", "",
              ", ".join(sorted(f"{r[0]} ({r[2]}+{r[6]})" for r in few)), "",
              f"Patterns coded: {sum(v == 'candle' for v in kinds.values())} candlestick, "
              f"{sum(v == 'chart' for v in kinds.values())} chart."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="sniper_data")
    ap.add_argument("--report", default="pattern_report.md")
    a = ap.parse_args()
    rep = analyze(Path(a.data))
    Path(a.report).write_text(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
