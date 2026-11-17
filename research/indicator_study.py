"""Indicator study: which common indicators would actually have made money on Indian index options?

Runs in two steps:
  fetch    log in to SmartAPI (read-only) and download years of 5-minute and daily index candles
  analyze  test every indicator (alone and with filters) on the same entry/exit rules, after costs

Honesty rules built in:
  * Every signal is computed only from bars that were complete at the time (no look-ahead).
  * Rules are ranked on older data (train) and then checked on the most recent year (test) the
    ranking never saw. Only what holds up there is worth adding to the bot.
  * Results are in index points per trade after a cost hurdle that approximates a 1-lot debit spread
    (4 orders, charges and bid/ask slippage), then converted to rupees per lot.

Usage:
  python research/indicator_study.py fetch --out research_data --years 3
  python research/indicator_study.py analyze --data research_data
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INDICES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX"]
SPREAD_DELTA = 0.40          # an ATM debit spread moves roughly 0.4 x the index
COST_PER_LOT_RS = 250.0      # 4 orders: brokerage, taxes and slippage, round trip
FIRST_ENTRY, LAST_ENTRY, SQUARE_OFF = time(9, 30), time(14, 0), time(15, 10)


# ----------------------------------------------------------------------------------------- fetch
def fetch(out: Path, years: int) -> None:
    from optbot.clock import IST, Clock
    from optbot.config import load_config
    from optbot.instruments import Instruments, download_scrip_master
    from optbot.marketdata import AngelData

    cfg = load_config(ROOT / "config.yaml")
    out.mkdir(parents=True, exist_ok=True)
    sm = out / "instruments.json"
    download_scrip_master(sm)
    inst = Instruments.from_file(sm, cfg["indices"], cfg["vix"]["names"])
    data = AngelData(cfg.secrets, inst, Clock())
    lots = {}
    try:
        end = datetime.now(IST)
        start = end - timedelta(days=365 * years)
        for idx in INDICES:
            if idx not in inst.spot_tokens:
                print(f"{idx}: no spot token, skipped")
                continue
            lots[idx] = inst.lot_size(idx) or 0
            exch, tok = inst.spot_tokens[idx]
            rows, s = [], start
            while s < end:
                e = min(end, s + timedelta(days=90))
                rows += data._candles(exch, tok, "FIVE_MINUTE", s, e)
                s = e
            seen, uniq = set(), []
            for c in rows:
                if c.ts not in seen:
                    seen.add(c.ts)
                    uniq.append(c)
            uniq.sort(key=lambda c: c.ts)
            with (out / f"{idx}_5m.csv").open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ts", "open", "high", "low", "close"])
                for c in uniq:
                    w.writerow([c.ts.isoformat(), c.open, c.high, c.low, c.close])
            first = uniq[0].ts.date() if uniq else None
            print(f"{idx}: {len(uniq)} five-minute candles from {first}")
    finally:
        data.logout()
    with (out / "lots.csv").open("w") as f:
        for k, v in lots.items():
            f.write(f"{k},{v}\n")


# ----------------------------------------------------------------------------------------- data
@dataclass
class Bar:
    ts: datetime
    o: float
    h: float
    l: float
    c: float


def load_bars(path: Path) -> list[Bar]:
    out = []
    with path.open() as f:
        for r in csv.DictReader(f):
            out.append(Bar(datetime.fromisoformat(r["ts"]), float(r["open"]), float(r["high"]), float(r["low"]),
                           float(r["close"])))
    return out


# ----------------------------------------------------------------------------------------- indicators
def ema(xs, n):
    k, out, e = 2 / (n + 1), [], None
    for x in xs:
        e = x if e is None else e + k * (x - e)
        out.append(e)
    return out


def rma(xs, n):
    out, e = [], None
    for i, x in enumerate(xs):
        e = x if e is None else (e * (n - 1) + x) / n
        out.append(e)
    return out


def sma(xs, n):
    out, s = [], 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        out.append(s / min(i + 1, n))
    return out


def stdev(xs, n):
    out = []
    for i in range(len(xs)):
        w = xs[max(0, i - n + 1): i + 1]
        m = sum(w) / len(w)
        out.append(math.sqrt(sum((v - m) ** 2 for v in w) / len(w)))
    return out


def true_range(b):
    tr = [b[0].h - b[0].l]
    for i in range(1, len(b)):
        tr.append(max(b[i].h - b[i].l, abs(b[i].h - b[i - 1].c), abs(b[i].l - b[i - 1].c)))
    return tr


def rsi(c, n=14):
    g = [0.0] + [max(0.0, c[i] - c[i - 1]) for i in range(1, len(c))]
    l = [0.0] + [max(0.0, c[i - 1] - c[i]) for i in range(1, len(c))]
    ag, al = rma(g, n), rma(l, n)
    return [100.0 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i]) for i in range(len(c))]


def adx(b, n=14):
    up = [0.0] + [b[i].h - b[i - 1].h for i in range(1, len(b))]
    dn = [0.0] + [b[i - 1].l - b[i].l for i in range(1, len(b))]
    pdm = [u if u > d and u > 0 else 0.0 for u, d in zip(up, dn)]
    mdm = [d if d > u and d > 0 else 0.0 for u, d in zip(up, dn)]
    atr = rma(true_range(b), n)
    pdi = [100 * p / a if a else 0 for p, a in zip(rma(pdm, n), atr)]
    mdi = [100 * m / a if a else 0 for m, a in zip(rma(mdm, n), atr)]
    dx = [100 * abs(p - m) / (p + m) if p + m else 0 for p, m in zip(pdi, mdi)]
    return rma(dx, n), pdi, mdi


def supertrend(b, n=10, mult=3.0):
    atr = rma(true_range(b), n)
    dirn, fu, fl, out = 1, None, None, []
    for i, x in enumerate(b):
        mid = (x.h + x.l) / 2
        bu, bl = mid + mult * atr[i], mid - mult * atr[i]
        if fu is None:
            fu, fl = bu, bl
        else:
            fu = bu if bu < fu or b[i - 1].c > fu else fu
            fl = bl if bl > fl or b[i - 1].c < fl else fl
        if dirn == 1 and x.c < fl:
            dirn = -1
        elif dirn == -1 and x.c > fu:
            dirn = 1
        out.append(dirn)
    return out


def cross(a, b, i):
    """+1 if a crossed above b on bar i, -1 if below, else 0."""
    if i == 0:
        return 0
    if a[i - 1] <= b[i - 1] and a[i] > b[i]:
        return 1
    if a[i - 1] >= b[i - 1] and a[i] < b[i]:
        return -1
    return 0


# ----------------------------------------------------------------------------------------- signals
def compute(bars: list[Bar]) -> dict:
    c = [x.c for x in bars]
    ind = {"c": c}
    ind["e9"], ind["e21"], ind["e50"] = ema(c, 9), ema(c, 21), ema(c, 50)
    ind["atr"] = rma(true_range(bars), 14)
    ind["rsi"] = rsi(c)
    m = [a - b for a, b in zip(ema(c, 12), ema(c, 26))]
    ind["macd"], ind["macds"] = m, ema(m, 9)
    mid, sd = sma(c, 20), stdev(c, 20)
    ind["bbu"] = [a + 2 * s for a, s in zip(mid, sd)]
    ind["bbl"] = [a - 2 * s for a, s in zip(mid, sd)]
    ind["bbm"] = mid
    ind["adx"], ind["pdi"], ind["mdi"] = adx(bars)
    ind["st"] = supertrend(bars)
    hh, ll = [], []
    for i in range(len(bars)):
        w = bars[max(0, i - 20): i]  # previous 20 bars, excluding this one
        hh.append(max((x.h for x in w), default=bars[i].h))
        ll.append(min((x.l for x in w), default=bars[i].l))
    ind["dch"], ind["dcl"] = hh, ll
    # session average price (index has no volume, so this stands in for VWAP)
    sap, day, s, n = [], None, 0.0, 0
    for x in bars:
        if x.ts.date() != day:
            day, s, n = x.ts.date(), 0.0, 0
        s += (x.h + x.l + x.c) / 3
        n += 1
        sap.append(s / n)
    ind["sap"] = sap
    return ind


def orb_levels(bars):
    """Opening range (first 15 minutes) per day, known only after 09:30."""
    lv, day, hi, lo, k = [], None, None, None, 0
    for x in bars:
        if x.ts.date() != day:
            day, hi, lo, k = x.ts.date(), x.h, x.l, 1
        elif k < 3:
            hi, lo, k = max(hi, x.h), min(lo, x.l), k + 1
        lv.append((hi, lo) if k >= 3 else (None, None))
    return lv


def signal_fns(bars, ind):
    c, e9, e21 = ind["c"], ind["e9"], ind["e21"]
    orb = orb_levels(bars)

    def orb_ema(i):
        hi, lo = orb[i]
        if hi is None or i == 0:
            return 0
        if c[i] > hi >= c[i - 1] and e9[i] > e21[i]:
            return 1
        if c[i] < lo <= c[i - 1] and e9[i] < e21[i]:
            return -1
        return 0

    def rsi_mom(i):
        r = ind["rsi"]
        if i and r[i - 1] <= 60 < r[i]:
            return 1
        if i and r[i - 1] >= 40 > r[i]:
            return -1
        return 0

    def rsi_rev(i):
        r = ind["rsi"]
        if i and r[i - 1] < 30 <= r[i]:
            return 1
        if i and r[i - 1] > 70 >= r[i]:
            return -1
        return 0

    def bb_break(i):
        return cross(c, ind["bbu"], i) if cross(c, ind["bbu"], i) == 1 else (-1 if cross(c, ind["bbl"], i) == -1 else 0)

    def bb_rev(i):
        if cross(c, ind["bbl"], i) == 1:
            return 1
        if cross(c, ind["bbu"], i) == -1:
            return -1
        return 0

    def donchian(i):
        if i and c[i] > ind["dch"][i] and c[i - 1] <= ind["dch"][i - 1]:
            return 1
        if i and c[i] < ind["dcl"][i] and c[i - 1] >= ind["dcl"][i - 1]:
            return -1
        return 0

    def st_flip(i):
        st = ind["st"]
        return st[i] if i and st[i] != st[i - 1] else 0

    def adx_di(i):
        if ind["adx"][i] < 25:
            return 0
        return cross(ind["pdi"], ind["mdi"], i)

    def sap_cross(i):
        x = cross(c, ind["sap"], i)
        if x == 1 and e9[i] > e21[i]:
            return 1
        if x == -1 and e9[i] < e21[i]:
            return -1
        return 0

    return {
        "Opening-range breakout + EMA (current bot)": orb_ema,
        "EMA 9/21 crossover": lambda i: cross(e9, e21, i),
        "Supertrend (10,3) flip": st_flip,
        "MACD signal cross": lambda i: cross(ind["macd"], ind["macds"], i),
        "RSI momentum (60/40)": rsi_mom,
        "RSI reversal (30/70)": rsi_rev,
        "Bollinger breakout": bb_break,
        "Bollinger reversal": bb_rev,
        "Donchian 20-bar breakout": donchian,
        "ADX>25 + DI cross": adx_di,
        "VWAP-style cross + EMA": sap_cross,
    }


def filters(bars, ind, daily_bias):
    return {
        "": lambda i, d: True,
        " + daily trend": lambda i, d: daily_bias.get(bars[i].ts.date(), 0) == d,
        " + ADX>20": lambda i, d: ind["adx"][i] > 20,
        " + EMA50 side": lambda i, d: (ind["c"][i] > ind["e50"][i]) == (d == 1),
    }


def daily_trend(bars) -> dict:
    """Bias per day from daily closes up to the PREVIOUS day (what the morning playbook knows)."""
    closes, days = [], []
    for x in bars:
        if not days or x.ts.date() != days[-1]:
            days.append(x.ts.date())
            closes.append(x.c)
        else:
            closes[-1] = x.c
    e20 = ema(closes, 20)
    bias = {}
    for k in range(1, len(days)):
        j = k - 1
        if j < 25:
            bias[days[k]] = 0
            continue
        slope = (e20[j] - e20[j - 5]) / e20[j - 5] * 100
        ret5 = (closes[j] - closes[j - 5]) / closes[j - 5] * 100
        if closes[j] > e20[j] and slope > 0.3 and ret5 > 0.5:
            bias[days[k]] = 1
        elif closes[j] < e20[j] and slope < -0.3 and ret5 < -0.5:
            bias[days[k]] = -1
        else:
            bias[days[k]] = 0
    return bias


# ----------------------------------------------------------------------------------------- backtest
@dataclass
class Trade:
    day: date
    d: int
    pts: float


def backtest(bars, ind, sig, filt, trail_atr: float, cost_pts: float) -> list[Trade]:
    trades, i, n = [], 0, len(bars)
    while i < n:
        day = bars[i].ts.date()
        j = i
        while j < n and bars[j].ts.date() == day:
            j += 1
        entered = False
        k = i
        while k < j and not entered:
            # a bar's timestamp is its start; it is complete at ts + 5 min
            t_done = (bars[k].ts + timedelta(minutes=5)).time()
            if FIRST_ENTRY <= t_done <= LAST_ENTRY:
                d = sig(k)
                if d and filt(k, d):
                    entered = True
                    entry, a = bars[k].c, ind["atr"][k]
                    stop = entry - d * trail_atr * a
                    best = entry
                    exit_px = None
                    for m in range(k + 1, j):
                        b = bars[m]
                        if d == 1 and b.l <= stop:
                            exit_px = min(stop, b.o)
                        elif d == -1 and b.h >= stop:
                            exit_px = max(stop, b.o)
                        if exit_px is not None:
                            break
                        if (b.ts + timedelta(minutes=5)).time() >= SQUARE_OFF:
                            exit_px = b.c
                            break
                        best = max(best, b.c) if d == 1 else min(best, b.c)
                        stop = max(stop, best - trail_atr * a) if d == 1 else min(stop, best + trail_atr * a)
                    if exit_px is None:
                        exit_px = bars[j - 1].c
                    trades.append(Trade(day, d, d * (exit_px - entry) - cost_pts))
            k += 1
        i = j
    return trades


def stats(tr: list[Trade]) -> dict:
    if not tr:
        return {"n": 0, "win": 0.0, "exp": 0.0, "pf": 0.0, "total": 0.0, "dd": 0.0, "t": 0.0}
    p = [t.pts for t in tr]
    w = [x for x in p if x > 0]
    l = [-x for x in p if x <= 0]
    eq = peak = dd = 0.0
    for x in p:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    mean = sum(p) / len(p)
    sd = math.sqrt(sum((x - mean) ** 2 for x in p) / max(1, len(p) - 1))
    return {"n": len(p), "win": 100 * len(w) / len(p), "exp": mean,
            "pf": (sum(w) / sum(l)) if l and sum(l) else float("inf"), "total": sum(p), "dd": dd,
            "t": mean / (sd / math.sqrt(len(p))) if sd > 0 else 0.0}


def random_baseline(bars, ind, trail_atr, cost_pts, seed=1):
    rnd = random.Random(seed)
    return lambda i: rnd.choice([1, -1]) if rnd.random() < 0.03 else 0


def analyze(data: Path, test_days: int = 250) -> str:
    lots = {}
    if (data / "lots.csv").exists():
        for line in (data / "lots.csv").read_text().splitlines():
            k, v = line.split(",")
            lots[k] = int(v)
    lines = ["# Indicator study", "",
             f"Exits are the same for every rule: trailing stop of N x ATR (5-min), closed by 15:10 at the latest. "
             f"One trade per index per day, entries 09:30-14:00. Costs: ₹{COST_PER_LOT_RS:.0f} per lot round trip. "
             f"Rupees assume a 1-lot debit spread moving about {SPREAD_DELTA} x the index.", ""]
    results = []  # (name, idx, trail, train_stats, test_stats, rs_per_point)
    for idx in INDICES:
        f = data / f"{idx}_5m.csv"
        if not f.exists():
            continue
        bars = [b for b in load_bars(f) if time(9, 15) <= b.ts.time() < time(15, 30)]
        if len(bars) < 2000:
            continue
        days = sorted({b.ts.date() for b in bars})
        split = days[-test_days] if len(days) > test_days + 100 else days[len(days) * 2 // 3]
        lot = lots.get(idx) or {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "SENSEX": 20}.get(idx, 1)
        rs_per_pt = lot * SPREAD_DELTA
        cost_pts = COST_PER_LOT_RS / rs_per_pt
        ind = compute(bars)
        bias = daily_trend(bars)
        lines.append(f"- {idx}: {len(days)} sessions ({days[0]} to {days[-1]}), test period from {split}, "
                     f"lot {lot}, cost hurdle {cost_pts:.1f} pts/trade")
        sigs = signal_fns(bars, ind)
        sigs["Random entry (baseline)"] = random_baseline(bars, ind, 1.5, cost_pts)
        for sname, sfn in sigs.items():
            for fname, ffn in filters(bars, ind, bias).items():
                if sname.startswith("Random") and fname:
                    continue
                for trail in (1.0, 2.0):
                    tr = backtest(bars, ind, sfn, ffn, trail, cost_pts)
                    results.append((sname + fname, idx, trail,
                                    stats([t for t in tr if t.day < split]), stats([t for t in tr if t.day >= split]),
                                    rs_per_pt))
    lines.append("")

    def row(r):
        name, idx, trail, a, b, k = r
        return (f"| {name} | {idx} | {trail:g} | {a['n']} | {a['win']:.0f}% | {a['exp'] * k:+,.0f} | {a['pf']:.2f} "
                f"| {b['n']} | {b['win']:.0f}% | {b['exp'] * k:+,.0f} | {b['pf']:.2f} | {b['total'] * k:+,.0f} | {b['t']:.1f} |")

    head = ("| Rule | Index | Trail ATR | Train trades | Train win | Train ₹/trade | Train PF "
            "| Test trades | Test win | Test ₹/trade | Test PF | Test total ₹ | Test t |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    eligible = [r for r in results if r[3]["n"] >= 60]
    top = sorted(eligible, key=lambda r: r[3]["exp"] * r[5], reverse=True)[:15]
    lines += ["## Best 15 rules on the older data, and how they did on the recent year they never saw", "", head]
    lines += [row(r) for r in top]
    held = [r for r in top if r[4]["n"] >= 30 and r[4]["t"] >= 2.0]
    lines += ["", f"**{len(held)} of the top 15 were clearly profitable after costs on the unseen year** "
                  "(at least 30 trades and t >= 2, i.e. unlikely to be luck). "
                  "t = average profit divided by its uncertainty; below 2 it can easily be chance.", ""]
    for r in held:
        lines.append(f"- {r[0]} on {r[1]} (trail {r[2]:g} ATR): {r[4]['n']} trades, {r[4]['win']:.0f}% wins, "
                     f"≈ ₹{r[4]['exp'] * r[5]:+,.0f} per trade per lot")
    lines.append("")
    lines += ["## Baselines", "", head]
    lines += [row(r) for r in results if r[0].startswith("Random") or r[0] == "Opening-range breakout + EMA (current bot)"]
    lines += ["", "## Every single indicator, no filter (trail 2 x ATR)", "", head]
    lines += [row(r) for r in results if r[2] == 2.0 and " + " not in r[0] and not r[0].startswith("Random")]
    allpos = sum(1 for r in eligible if r[3]["exp"] > 0)
    lines += ["", f"Rules tested: {len(results)}. Profitable after costs on older data: {allpos} of {len(eligible)} "
                  f"with enough trades."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--out", default="research_data")
    f.add_argument("--years", type=int, default=3)
    a = sub.add_parser("analyze")
    a.add_argument("--data", default="research_data")
    a.add_argument("--report", default="")
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(Path(args.out), args.years)
    else:
        rep = analyze(Path(args.data))
        print(rep)
        if args.report:
            Path(args.report).write_text(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
