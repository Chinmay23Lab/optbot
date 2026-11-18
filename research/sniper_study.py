"""Sniper-style study: rebuild the visible rules of Chinmay's TradingView indicator and test them on years of data.

What the indicator shows on screen (from Chinmay's screenshot, 18 Nov 2026), and how it is rebuilt here:
  * EMA bands with settings 5, 21, 100 and 200            -> fast band EMA5/EMA21, trend EMA100/EMA200
  * BUY / SELL labels when price leaves the band         -> EMA5 crossing EMA21 on the 15-minute chart
  * A table checking 3m..1h for agreement ("FINAL" row)  -> 30-minute and 1-hour EMA5/EMA21 must agree
  * SL just beyond the band, TP1/TP2/TP3 at equal steps  -> SL = k x ATR, TP1 = 2 x SL, TP2 = 4 x SL, TP3 = 6 x SL
The real indicator's code is private, so this is a close reconstruction, not the original.

Measured honestly:
  * signals use only completed bars (no look-ahead); higher timeframes use the last completed bar
  * ranked on older data, then checked on the most recent year it never saw
  * compared with random entries that use the same SL/TP, so a "hit rate" can be judged fairly
  * results in rupees per lot of an at-the-money option bought (delta ~0.5), after charges and slippage

Usage:
  python research/sniper_study.py fetch --out sniper_data --years 3
  python research/sniper_study.py analyze --data sniper_data --report sniper_report.md
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
OPTION_DELTA = 0.5                       # at-the-money option moves about half as much as the underlying
COST_RS = {"index": 150.0, "stock": 350.0}  # per lot, round trip: brokerage, taxes, bid/ask slippage
THETA_PER_NIGHT = 0.001                  # an ATM option loses roughly 0.1% of the underlying's price per night held
FIRST_ENTRY, LAST_ENTRY, SQUARE_OFF = time(9, 30), time(14, 0), time(15, 10)


# ----------------------------------------------------------------------------------------- fetch
def fetch(out: Path, years: int) -> None:
    from optbot.clock import IST, Clock
    from optbot.config import load_config
    from optbot.instruments import Instruments, download_scrip_master
    from optbot.marketdata import AngelData

    cfg = load_config(ROOT / "config.yaml")
    stocks = (cfg.get("stocks") or {}).get("names") or []
    out.mkdir(parents=True, exist_ok=True)
    sm = out / "instruments.json"
    download_scrip_master(sm)
    inst = Instruments.from_file(sm, cfg["indices"], cfg["vix"]["names"], stocks)
    data = AngelData(cfg.secrets, inst, Clock())
    lots = {}
    try:
        end = datetime.now(IST)
        start = end - timedelta(days=365 * years)
        for name in INDICES + stocks:
            if name not in inst.spot_tokens:
                print(f"{name}: no price token, skipped")
                continue
            lots[name] = (inst.lot_size(name) or 0, "stock" if name in stocks else "index")
            exch, tok = inst.spot_tokens[name]
            rows, s = [], start
            while s < end:
                e = min(end, s + timedelta(days=90))
                rows += data._candles(exch, tok, "FIVE_MINUTE", s, e)
                s = e
            uniq = sorted({c.ts: c for c in rows}.values(), key=lambda c: c.ts)
            with (out / f"{name}_5m.csv").open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ts", "open", "high", "low", "close"])
                for c in uniq:
                    w.writerow([c.ts.isoformat(), c.open, c.high, c.low, c.close])
            print(f"{name}: {len(uniq)} five-minute candles from {uniq[0].ts.date() if uniq else None}")
    finally:
        data.logout()
    with (out / "lots.csv").open("w") as f:
        for k, (lot, kind) in lots.items():
            f.write(f"{k},{lot},{kind}\n")


# ----------------------------------------------------------------------------------------- data
@dataclass
class Bar:
    ts: datetime   # start of the bar
    o: float
    h: float
    l: float
    c: float


def load_bars(path: Path) -> list[Bar]:
    with path.open() as f:
        return [Bar(datetime.fromisoformat(r["ts"]), float(r["open"]), float(r["high"]), float(r["low"]),
                    float(r["close"])) for r in csv.DictReader(f)]


def resample(bars: list[Bar], minutes: int) -> list[Bar]:
    """Group 5-minute bars into `minutes` bars, aligned to 9:15 each session."""
    out: list[Bar] = []
    cur = None
    for b in bars:
        mins = (b.ts.hour * 60 + b.ts.minute) - (9 * 60 + 15)
        slot = b.ts.replace(hour=9, minute=15, second=0, microsecond=0) + timedelta(minutes=(mins // minutes) * minutes)
        if cur is None or cur.ts != slot:
            cur = Bar(slot, b.o, b.h, b.l, b.c)
            out.append(cur)
        else:
            cur.h, cur.l, cur.c = max(cur.h, b.h), min(cur.l, b.l), b.c
    return out


def ema(xs, n):
    k, out, e = 2 / (n + 1), [], None
    for x in xs:
        e = x if e is None else e + k * (x - e)
        out.append(e)
    return out


def atr(bars, n=14):
    out, a, prev = [], None, None
    for b in bars:
        tr = b.h - b.l if prev is None else max(b.h - b.l, abs(b.h - prev), abs(b.l - prev))
        a = tr if a is None else a + (tr - a) / n
        out.append(a)
        prev = b.c
    return out


def htf_dir(bars15: list[Bar], bars_h: list[Bar], minutes: int) -> list[int]:
    """For each 15m bar, the EMA5 vs EMA21 direction of the last COMPLETED higher-timeframe bar."""
    c = [b.c for b in bars_h]
    f, s = ema(c, 5), ema(c, 21)
    ends = [b.ts + timedelta(minutes=minutes) for b in bars_h]
    out, j = [], -1
    for b in bars15:
        done = b.ts + timedelta(minutes=15)
        while j + 1 < len(bars_h) and ends[j + 1] <= done:
            j += 1
        out.append(0 if j < 21 else (1 if f[j] > s[j] else -1))
    return out


# ----------------------------------------------------------------------------------------- signals
def make_signals(b15, b30, b60):
    c = [b.c for b in b15]
    e5, e21, e100, e200 = ema(c, 5), ema(c, 21), ema(c, 100), ema(c, 200)
    d30, d60 = htf_dir(b15, b30, 30), htf_dir(b15, b60, 60)

    def cross(i):
        if i < 200:
            return 0
        if e5[i - 1] <= e21[i - 1] and e5[i] > e21[i]:
            return 1
        if e5[i - 1] >= e21[i - 1] and e5[i] < e21[i]:
            return -1
        return 0

    def trend(i, d):
        return (c[i] > e100[i] and c[i] > e200[i]) if d == 1 else (c[i] < e100[i] and c[i] < e200[i])

    return {
        "A band cross": lambda i: cross(i),
        "B cross + 100/200 trend": lambda i: (d if (d := cross(i)) and trend(i, d) else 0),
        "C cross + trend + 30m/1h agree": lambda i: (d if (d := cross(i)) and trend(i, d)
                                                     and d30[i] == d and d60[i] == d else 0),
    }


def random_signals(seed=1):
    rnd = random.Random(seed)
    return lambda i: rnd.choice([1, -1]) if i >= 200 and rnd.random() < 0.04 else 0


# ----------------------------------------------------------------------------------------- backtest
@dataclass
class Trade:
    day: date
    pts: float      # underlying points, before costs
    tp1: bool       # TP1 reached before the stop
    nights: int = 0
    price: float = 0.0


def backtest(b15, a15, sig, sl_atr: float, mode: str, max_days: int) -> list[Trade]:
    """mode 'tp1': exit everything at TP1. mode 'run': at TP1 move SL to entry, then exit at TP3 or stop."""
    trades, n, i = [], len(b15), 0
    busy_until = -1
    while i < n:
        b = b15[i]
        done = (b.ts + timedelta(minutes=15)).time()
        if i <= busy_until or not (FIRST_ENTRY <= done <= LAST_ENTRY):
            i += 1
            continue
        d = sig(i)
        if not d:
            i += 1
            continue
        entry, risk = b.c, sl_atr * a15[i]
        stop, tp1, tp3 = entry - d * risk, entry + d * 2 * risk, entry + d * 6 * risk
        hit1, exit_px, days, last_day, m = False, None, 1, b.ts.date(), i + 1
        while m < n:
            x = b15[m]
            if x.ts.date() != last_day:
                days += 1
                last_day = x.ts.date()
                if days > max_days:
                    exit_px = b15[m - 1].c
                    m -= 1
                    break
            lo_hit = (x.l <= stop) if d == 1 else (x.h >= stop)
            if lo_hit:   # stop first when both touch in one bar (the cautious assumption)
                exit_px = min(stop, x.o) if d == 1 else max(stop, x.o)
                break
            if not hit1 and ((x.h >= tp1) if d == 1 else (x.l <= tp1)):
                hit1 = True
                if mode == "tp1":
                    exit_px = tp1
                    break
                stop = entry
            if hit1 and ((x.h >= tp3) if d == 1 else (x.l <= tp3)):
                exit_px = tp3
                break
            if max_days == 1 and (x.ts + timedelta(minutes=15)).time() >= SQUARE_OFF:
                exit_px = x.c
                break
            m += 1
        if exit_px is None:
            exit_px = b15[min(m, n - 1)].c
        nights = (b15[min(m, n - 1)].ts.date() - b.ts.date()).days and \
            len({x.ts.date() for x in b15[i:min(m, n - 1) + 1]}) - 1
        trades.append(Trade(b.ts.date(), d * (exit_px - entry), hit1, nights, entry))
        busy_until = m
        i = m + 1
    return trades


def rupees(t: Trade, lot: int, cost_rs: float) -> float:
    return t.pts * OPTION_DELTA * lot - cost_rs - t.nights * THETA_PER_NIGHT * t.price * lot


def stats(tr: list[Trade], lot: int, cost_rs: float) -> dict:
    if not tr:
        return {"n": 0, "tp1": 0.0, "win": 0.0, "rs": 0.0, "total": 0.0, "t": 0.0}
    rs = [rupees(t, lot, cost_rs) for t in tr]
    mean = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in rs) / max(1, len(rs) - 1))
    return {"n": len(rs), "tp1": 100 * sum(t.tp1 for t in tr) / len(tr), "win": 100 * sum(x > 0 for x in rs) / len(rs),
            "rs": mean, "total": sum(rs), "t": mean / (sd / math.sqrt(len(rs))) if sd > 0 else 0.0}


# ----------------------------------------------------------------------------------------- analyze
def analyze(data: Path, test_days: int = 250) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    variants = [(sl, mode, md) for sl in (1.0, 1.5) for mode in ("tp1", "run") for md in (1, 3)]
    rows, combined = [], {}
    for name, (lot, kind) in lots.items():
        p = data / f"{name}_5m.csv"
        if not p.exists() or lot <= 0:
            continue
        b5 = load_bars(p)
        b15, b30, b60 = resample(b5, 15), resample(b5, 30), resample(b5, 60)
        a15 = atr(b15)
        days = sorted({b.ts.date() for b in b15})
        if len(days) < test_days + 100:
            continue
        cut = days[-test_days]
        sigs = make_signals(b15, b30, b60)
        sigs["Random entries (baseline)"] = random_signals()
        for sname, fn in sigs.items():
            for sl, mode, md in variants:
                tr = backtest(b15, a15, fn, sl, mode, md)
                train = [t for t in tr if t.day < cut]
                test = [t for t in tr if t.day >= cut]
                key = (sname, sl, mode, md)
                st_tr, st_te = stats(train, lot, COST_RS[kind]), stats(test, lot, COST_RS[kind])
                rows.append((name, kind, key, st_tr, st_te))
                cb = combined.setdefault(key, [])
                cb += [(t, lot, COST_RS[kind]) for t in test]
    lines = ["# Sniper-style signals: 3-year test", "",
             f"Rebuilt from the visible rules of Sniper Short 2.0. Test period = last {test_days} trading days, "
             "never used to pick settings. Rupees per lot of an at-the-money option bought, after charges.", ""]
    lines += ["## All names together, test period (best settings first)", "",
              "| Signal | SL (ATR) | Exit | Hold days | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    agg = []
    for key, items in combined.items():
        rs = [rupees(t, lot, cost) for t, lot, cost in items]
        if not rs:
            continue
        mean = sum(rs) / len(rs)
        sd = math.sqrt(sum((x - mean) ** 2 for x in rs) / max(1, len(rs) - 1))
        agg.append((key, len(rs), 100 * sum(t.tp1 for t, _, _ in items) / len(items),
                    100 * sum(x > 0 for x in rs) / len(rs), mean, sum(rs), mean / (sd / math.sqrt(len(rs))) if sd else 0))
    for key, n, tp1, win, mean, tot, t in sorted(agg, key=lambda r: -r[4]):
        s, sl, mode, md = key
        lines.append(f"| {s} | {sl} | {'all at TP1' if mode == 'tp1' else 'TP1 then run to TP3'} | {md} | {n} | "
                     f"{tp1:.0f}% | {win:.0f}% | {mean:+,.0f} | {tot:+,.0f} | {t:.1f} |")
    lines += ["", "## Per name (test period), signal C with each name's best settings", "",
              "| Name | Settings | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t |", "|---|---|---|---|---|---|---|---|"]
    for name in lots:
        best = [r for r in rows if r[0] == name and r[2][0].startswith("C")]
        if not best:
            continue
        r = max(best, key=lambda r: r[3]["rs"])   # chosen on TRAIN, reported on TEST
        te = r[4]
        _, sl, mode, md = r[2]
        lines.append(f"| {name} | SL {sl}, {mode}, {md}d | {te['n']} | {te['tp1']:.0f}% | {te['win']:.0f}% | "
                     f"{te['rs']:+,.0f} | {te['total']:+,.0f} | {te['t']:.1f} |")
    lines += ["", "t of 2 or more = unlikely to be luck. Random entries with the same SL/TP show what a hit rate "
              "is worth on its own: with TP1 at 2x the stop, about 33% is what chance gives."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--out", default="sniper_data")
    f.add_argument("--years", type=int, default=3)
    a = sub.add_parser("analyze")
    a.add_argument("--data", default="sniper_data")
    a.add_argument("--report", default="sniper_report.md")
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(Path(args.out), args.years)
    else:
        rep = analyze(Path(args.data))
        Path(args.report).write_text(rep)
        print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
