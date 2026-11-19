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
# Signal timeframe -> the two higher timeframes that must agree (375 minutes = the whole day).
TIMEFRAMES = {5: (15, 30), 10: (30, 60), 15: (30, 60), 30: (60, 120), 60: (120, 375)}
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
from optbot.sniper_rules import (Bar, a15_for, atr, ema, htf_dir, make_signals, pivots,  # noqa: E402,F401
                                  resample, rsi, sma, supertrend_dir)


def load_bars(path: Path) -> list[Bar]:
    with path.open() as f:
        return [Bar(datetime.fromisoformat(r["ts"]), float(r["open"]), float(r["high"]), float(r["low"]),
                    float(r["close"])) for r in csv.DictReader(f)]


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


def backtest(b15, a15, sig, sl_atr: float, mode: str, max_days: int, base: int = 15, tp_step: float = 2.0) -> list[Trade]:
    """mode 'tp1': exit everything at TP1. mode 'run': at TP1 move SL to entry, then exit at TP3 or stop.
    mode 'flip': no target; hold until the stop or an opposite signal, then exit and take the reverse trade.
    mode 'tp1flip': like 'flip', but at TP1 the stop moves to entry (a winner can't turn into a loser).
    mode 'half': book half at TP1, then trail the other half with a stop one risk-distance behind the best
    close (never below entry); no upper target."""
    flip = mode in ("flip", "tp1flip")
    trades, n, i = [], len(b15), 0
    busy_until = -1
    while i < n:
        b = b15[i]
        done = (b.ts + timedelta(minutes=base)).time()
        if i <= busy_until or not (FIRST_ENTRY <= done <= LAST_ENTRY):
            i += 1
            continue
        d = sig(i)
        if not d:
            i += 1
            continue
        entry, risk = b.c, sl_atr * a15[i]
        stop, tp1, tp3 = entry - d * risk, entry + d * tp_step * risk, entry + d * 3 * tp_step * risk
        hit1, exit_px, days, last_day, m = False, None, 1, b.ts.date(), i + 1
        rev = False
        half_pts, best = None, entry
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
                if mode == "half":
                    half_pts = d * (tp1 - entry)
                if mode != "flip":
                    stop = entry
            if flip and (FIRST_ENTRY <= (x.ts + timedelta(minutes=base)).time() <= LAST_ENTRY or max_days > 1) \
                    and sig(m) == -d:
                exit_px, rev = x.c, True   # reversal signal: book here, the reverse trade starts on this bar
                break
            if mode == "half":
                if hit1:   # trail behind the best close since TP1
                    best = max(best, x.c) if d == 1 else min(best, x.c)
                    stop = max(stop, best - risk) if d == 1 else min(stop, best + risk)
            elif not flip and hit1 and ((x.h >= tp3) if d == 1 else (x.l <= tp3)):
                exit_px = tp3
                break
            if max_days == 1 and (x.ts + timedelta(minutes=base)).time() >= SQUARE_OFF:
                exit_px = x.c
                break
            m += 1
        if exit_px is None:
            exit_px = b15[min(m, n - 1)].c
        nights = (b15[min(m, n - 1)].ts.date() - b.ts.date()).days and \
            len({x.ts.date() for x in b15[i:min(m, n - 1) + 1]}) - 1
        pts = d * (exit_px - entry)
        if half_pts is not None:
            pts = 0.5 * half_pts + 0.5 * pts
        trades.append(Trade(b.ts.date(), pts, hit1, nights, entry))
        reversed_here = rev
        busy_until = m - 1 if reversed_here else m
        i = m if reversed_here else m + 1
    return trades


EXIT_NAMES = {"tp1": "all at TP1", "run": "TP1 then run to TP3", "flip": "hold till reversal, then flip", "half": "half at TP1, trail the rest",
              "tp1flip": "TP1 locks entry, hold till reversal, flip"}


def rupees(t: Trade, lot: int, cost_rs: float) -> float:
    return t.pts * OPTION_DELTA * lot - cost_rs - t.nights * THETA_PER_NIGHT * t.price * lot


def train_summary(items) -> str:
    rs = [rupees(t, lot, cost) for t, lot, cost in items]
    if len(rs) < 2:
        return "-"
    mean = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in rs) / (len(rs) - 1))
    return f"{mean:+,.0f} ({mean / (sd / math.sqrt(len(rs))) if sd else 0:.1f}, n={len(rs)})"


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
    # TP spacing seen on Chinmay's screenshots: about 1.3x the stop distance (NIFTY) and 2x (Bharti Airtel)
    variants = [(sl, mode, md, tp) for sl in (1.0, 1.5) for mode in ("tp1", "run") for md in (1, 3) for tp in (1.3, 2.0)]
    variants += [(sl, mode, md, 2.0) for sl in (1.0, 1.5) for mode in ("flip", "tp1flip") for md in (1, 3)]
    variants += [(sl, "half", md, tp) for sl in (1.0, 1.5) for md in (1, 3) for tp in (1.3, 2.0)]
    rows, combined, combined_train = [], {}, {}
    for name, (lot, kind) in lots.items():
        p = data / f"{name}_5m.csv"
        if not p.exists() or lot <= 0:
            continue
        b5 = load_bars(p)
        days = sorted({b.ts.date() for b in b5})
        if len(days) < test_days + 100:
            continue
        cut = days[-test_days]
        for tf, (h1, h2) in TIMEFRAMES.items():
            bt = b5 if tf == 5 else resample(b5, tf)
            at = atr(bt)
            sigs = make_signals(bt, resample(b5, h1), resample(b5, h2), h1, h2, tf)
            sigs["Random entries (baseline)"] = random_signals()
            for sname, fn in sigs.items():
                for sl, mode, md, tp in variants:
                    tr = backtest(bt, at, fn, sl, mode, md, tf, tp)
                    train = [t for t in tr if t.day < cut]
                    test = [t for t in tr if t.day >= cut]
                    key = (f"{tf}m {sname}", sl, mode, md, tp)
                    st_tr, st_te = stats(train, lot, COST_RS[kind]), stats(test, lot, COST_RS[kind])
                    rows.append((name, kind, key, st_tr, st_te))
                    cb = combined.setdefault(key, [])
                    cb += [(t, lot, COST_RS[kind]) for t in test]
                    combined_train.setdefault(key, []).extend((t, lot, COST_RS[kind]) for t in train)
    lines = ["# Sniper-style signals: 3-year test", "",
             f"Rebuilt from the visible rules of Sniper Short 2.0 plus the indicators it combines (EMA, MACD, RSI, Supertrend, VWMA, pivots). Test period = last {test_days} trading days, "
             "never used to pick settings. Rupees per lot of an at-the-money option bought, after charges.", ""]
    lines += ["## All names together, test period: top 30 signal settings, then the best random baselines", "",
              "| Signal | SL (ATR) | TP step (x SL) | Exit | Hold days | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t | Older 2 years: ₹/trade (t) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    agg = []
    for key, items in combined.items():
        rs = [rupees(t, lot, cost) for t, lot, cost in items]
        if not rs:
            continue
        mean = sum(rs) / len(rs)
        sd = math.sqrt(sum((x - mean) ** 2 for x in rs) / max(1, len(rs) - 1))
        agg.append((key, len(rs), 100 * sum(t.tp1 for t, _, _ in items) / len(items),
                    100 * sum(x > 0 for x in rs) / len(rs), mean, sum(rs), mean / (sd / math.sqrt(len(rs))) if sd else 0))
    ranked = sorted([r for r in agg if r[1] >= 30], key=lambda r: -r[4])   # too few trades proves nothing
    shown = [r for r in ranked if "Random" not in r[0][0]][:30] + [r for r in ranked if "Random" in r[0][0]][:5]
    for key, n, tp1, win, mean, tot, t in shown:
        s, sl, mode, md, tp = key
        lines.append(f"| {s} | {sl} | {tp} | {EXIT_NAMES[mode]} | {md} | {n} | "
                     f"{tp1:.0f}% | {win:.0f}% | {mean:+,.0f} | {tot:+,.0f} | {t:.1f} | {train_summary(combined_train.get(key, []))} |")
    lines += ["", "## Reversal flip: hold until the opposite signal, then book and reverse (best 15, all timeframes)", "",
              "| Signal | SL (ATR) | Exit | Hold days | Trades | Win % | ₹/trade | Total ₹ | t | Older 2 years: ₹/trade (t) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for key, n, tp1, win, mean, tot, t in [r for r in ranked if r[0][2] in ("flip", "tp1flip") and "Random" not in r[0][0]][:15]:
        s, sl, mode, md, tp = key
        lines.append(f"| {s} | {sl} | {EXIT_NAMES[mode]} | {md} | {n} | {win:.0f}% | {mean:+,.0f} | {tot:+,.0f} | {t:.1f} | "
                     f"{train_summary(combined_train.get(key, []))} |")
    def mean_n(items):
        rs = [rupees(t, lot, cost) for t, lot, cost in items]
        return (sum(rs) / len(rs), len(rs)) if rs else (0.0, 0)

    robust = []
    for key, n, tp1, win, mean, tot, t in agg:
        tm, tn = mean_n(combined_train.get(key, []))
        if n >= 30 and tn >= 30 and "Random" not in key[0]:
            robust.append((min(mean, tm), key, n, win, mean, t, tm, tn))
    robust.sort(key=lambda r: -r[0])
    lines += ["", "## Most consistent: ranked by the WORSE of the two periods (every signal, incl. candle patterns)", "",
              "| Signal | SL (ATR) | TP step | Exit | Hold days | Win % | Last year ₹/trade (n, t) | Older 2 years ₹/trade (n) |",
              "|---|---|---|---|---|---|---|---|"]
    for worst, key, n, win, mean, t, tm, tn in robust[:20]:
        s, sl, mode, md, tp = key
        lines.append(f"| {s} | {sl} | {tp} | {EXIT_NAMES[mode]} | {md} | {win:.0f}% | {mean:+,.0f} ({n}, {t:.1f}) | {tm:+,.0f} ({tn}) |")
    lines += ["", "## Per name: best signal and settings picked on older data, results on the unseen year", "",
              "| Name | Settings | Trades | TP1 before SL | Win % | ₹/trade | Total ₹ | t |", "|---|---|---|---|---|---|---|---|"]
    for name in lots:
        best = [r for r in rows if r[0] == name and "Random" not in r[2][0] and r[3]["n"] >= 30]
        if not best:
            continue
        r = max(best, key=lambda r: r[3]["rs"])   # chosen on TRAIN, reported on TEST
        te = r[4]
        _, sl, mode, md, tp = r[2]
        lines.append(f"| {name} | {' '.join(r[2][0].split()[:2])}, SL {sl}, TP {tp}x, {mode}, {md}d | {te['n']} | {te['tp1']:.0f}% | {te['win']:.0f}% | "
                     f"{te['rs']:+,.0f} | {te['total']:+,.0f} | {te['t']:.1f} |")
    lines += ["", "t of 2 or more = unlikely to be luck. Random entries with the same SL/TP show what a hit rate "
              "is worth on its own: with TP1 at 2x the stop about 33% is what chance gives, at 1.3x about 43%."]
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
