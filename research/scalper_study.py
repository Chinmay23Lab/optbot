"""Scalper backtest: buy one at-the-money option for ~₹10k, take +X% of premium, stop at -Y%, or leave after N minutes.

Entry on a 5- or 15-minute trigger only in the direction of the 1-hour trend. Exits are checked on 5-minute bars.
Premium model: ATM premium ≈ 0.4 × price × IV × √(days to expiry / 365), IV = last 20 days' realised volatility
(floored at 10%), days to expiry = 3 for indices (weekly), 12 for stocks (monthly). Option moves 0.5 × the
underlying. Costs per trade: ₹60 brokerage/fees + 0.15% of premium turnover. Max 5 trades a day, stop after
2 losses or +₹6,000. Last 250 trading days = "last year", the rest = "2 years before".
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from datetime import time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sniper_study as ss  # noqa: E402

BUDGET, MAX_TRADES, MAX_LOSSES, DAY_TARGET = 10_000, 5, 2, 6_000
FIRST, LAST, SQUARE = time(9, 30), time(14, 45), time(15, 10)
DTE = {"index": 3, "stock": 12}


def daily_vol(b5):
    """realised annual volatility from the last 20 daily closes, per day"""
    closes, out, last = {}, {}, None
    for x in b5:
        closes[x.ts.date()] = x.c
    days = sorted(closes)
    for k, d in enumerate(days):
        w = [math.log(closes[days[j]] / closes[days[j - 1]]) for j in range(max(1, k - 20), k)]
        if len(w) >= 10:
            m = sum(w) / len(w)
            last = math.sqrt(sum((r - m) ** 2 for r in w) / (len(w) - 1)) * math.sqrt(252)
        out[d] = max(0.10, last or 0.2)
    return out


def trend_1h(b5):
    """+1 / -1 / 0 per 1-hour bar close: EMA9 above/below EMA21 and price on the same side of EMA21"""
    b60 = ss.resample(b5, 60)
    c = [x.c for x in b60]
    e9, e21 = ss.ema(c, 9), ss.ema(c, 21)
    return [(x.ts + timedelta(minutes=60), 1 if e9[i] > e21[i] and c[i] > e21[i] else -1 if e9[i] < e21[i] and c[i] < e21[i]
             else 0) for i, x in enumerate(b60)]


def triggers(bt, kind):
    c = [x.c for x in bt]
    if kind == "ema":
        f, s = ss.ema(c, 5), ss.ema(c, 21)
        return [0] + [1 if f[i - 1] <= s[i - 1] and f[i] > s[i] else -1 if f[i - 1] >= s[i - 1] and f[i] < s[i] else 0
                      for i in range(1, len(c))]
    return [0, 0] + [1 if bt[i - 1].c < bt[i - 2].c and bt[i].c > bt[i - 1].h else
                     -1 if bt[i - 1].c > bt[i - 2].c and bt[i].c < bt[i - 1].l else 0 for i in range(2, len(c))]


def run(b5, lot, kind, tf, trig_kind, tp, sl, tmax):
    vol = daily_vol(b5)
    tr1h = trend_1h(b5)
    bt = b5 if tf == 5 else ss.resample(b5, tf)
    trig = triggers(bt, trig_kind)
    idx5 = {x.ts: i for i, x in enumerate(b5)}
    out, j, cur = [], 0, 0
    day, n_day, losses, pnl_day = None, 0, 0, 0.0
    busy_until = None
    for i, x in enumerate(bt):
        done = x.ts + timedelta(minutes=tf)
        while j < len(tr1h) and tr1h[j][0] <= done:
            cur = tr1h[j][1]
            j += 1
        if x.ts.date() != day:
            day, n_day, losses, pnl_day = x.ts.date(), 0, 0, 0.0
        if busy_until and done <= busy_until:
            continue
        if not (FIRST <= done.time() <= LAST) or not cur or trig[i] != cur:
            continue
        if n_day >= MAX_TRADES or losses >= MAX_LOSSES or pnl_day >= DAY_TARGET:
            continue
        k = idx5.get(done - timedelta(minutes=5))
        if k is None:
            continue
        entry = b5[k].c
        prem = 0.4 * entry * vol[x.ts.date()] * math.sqrt(DTE[kind] / 365)
        lots = int(BUDGET // (prem * lot))
        if lots < 1:
            if prem * lot > 1.5 * BUDGET:
                continue
            lots = 1
        qty = lots * lot
        up = tp * prem / 0.5     # underlying move for the premium target
        dn = sl * prem / 0.5
        d = cur
        exit_px, m = None, k + 1
        while m < len(b5) and b5[m].ts.date() == day:
            y = b5[m]
            if (y.l <= entry - dn) if d == 1 else (y.h >= entry + dn):
                exit_px = entry - d * dn
                break
            if (y.h >= entry + up) if d == 1 else (y.l <= entry - up):
                exit_px = entry + d * up
                break
            if y.ts + timedelta(minutes=5) - done >= timedelta(minutes=tmax) or (y.ts + timedelta(minutes=5)).time() >= SQUARE:
                exit_px = y.c
                break
            m += 1
        if exit_px is None:
            continue
        gross = 0.5 * d * (exit_px - entry) * qty
        cost = 60 + 0.0015 * 2 * prem * qty
        r = gross - cost
        out.append((day, r))
        n_day += 1
        pnl_day += r
        losses += r < 0
        busy_until = b5[m].ts + timedelta(minutes=5)
    return out


def summ(rs):
    if len(rs) < 2:
        return "-"
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1))
    return f"{m:+,.0f} (n={len(rs)}, win {100 * sum(x > 0 for x in rs) / len(rs):.0f}%, t {m / (sd / math.sqrt(len(rs))) if sd else 0:.1f})"


def analyze(data: Path, test_days=250, names=None) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    grid = [(tf, tk, tp, sl, tm) for tf in (5, 15) for tk in ("pb", "ema") for tp in (0.15, 0.20, 0.25)
            for sl in (0.08, 0.10, 0.15) for tm in (10, 15, 30)]
    res = defaultdict(lambda: ([], [], defaultdict(float), defaultdict(float)))
    for name, (lot, kind) in lots.items():
        if names and name not in names:
            continue
        p = data / f"{name}_5m.csv"
        if lot <= 0 or not p.exists():
            continue
        b5 = ss.load_bars(p)
        days = sorted({b.ts.date() for b in b5})
        if len(days) < test_days + 100:
            continue
        cut = days[-test_days]
        for g in grid:
            te, trn, dte, dtr = res[(kind,) + g]
            for d, r in run(b5, lot, kind, *g):
                (te if d >= cut else trn).append(r)
                (dte if d >= cut else dtr)[(name, d)] += r
    rows = []
    for key, (te, trn, dte, dtr) in res.items():
        if len(te) < 20 or len(trn) < 20:
            continue
        mt, mr = sum(te) / len(te), sum(trn) / len(trn)
        rows.append((min(mt, mr), key, te, trn, dte))
    rows.sort(key=lambda r: -r[0])
    out = ["# Scalper: ~₹10k ATM option buys, 1-hour trend + 5/15-minute trigger", "",
           "Ranked by the worse of the two periods. ₹ per trade after costs.", "",
           "| Names | Entry chart | Trigger | Target | Stop | Time stop | Last year | 2 years before | Avg ₹/day traded, last year |",
           "|---|---|---|---|---|---|---|---|---|"]
    for kind in ("index", "stock"):
        for worst, key, te, trn, dte in [r for r in rows if r[1][0] == kind][:12]:
            _, tf, tk, tp, sl, tm = key
            perday = sum(dte.values()) / max(1, len({d for _, d in dte}))
            out.append(f"| {kind} | {tf}m | {'pullback-break' if tk == 'pb' else 'EMA5/21 cross'} | +{tp:.0%} | -{sl:.0%} | "
                       f"{tm} min | {summ(te)} | {summ(trn)} | {perday:+,.0f} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="universe_data")
    ap.add_argument("--report", default="scalper_report.md")
    ap.add_argument("--names", default="NIFTY,BANKNIFTY,FINNIFTY,SENSEX,BANKEX,RELIANCE,HDFCBANK,ICICIBANK,SBIN,INFY,TCS,"
                                        "AXISBANK,KOTAKBANK,BHARTIARTL,LT")
    a = ap.parse_args()
    rep = analyze(Path(a.data), names=set(a.names.split(",")) if a.names else None)
    Path(a.report).write_text(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
