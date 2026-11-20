"""Two ideas from Chinmay (20 Nov 2026), tested on years of index data before anything goes live.

A. Morning global check. Before 9:15 IST we know: last night's US close (S&P 500, Nasdaq), the Asian morning
   (Nikkei, Kospi, Hang Seng up to 9:15 IST), crude oil and the rupee, and at 9:15 the opening gap (what GIFT
   Nifty shows in advance). Does that say which way the Indian index goes today? And do our rule G/R trades do
   better when they agree with it, or when held longer on days it is strongly on our side?
   (News can't be tested: there is no free archive of old headlines with times.)

B. Our own indicator. 15 common indicators, each giving up / down for every bar, used alone, in pairs and in
   threes (575 combinations): (1) as their own entry signal, (2) as a filter on rule G/R trades. Combinations
   are ranked on the older two years, then the top ones are checked on the last year they never saw.

Same option model and costs as sniper_study (ATM option bought, delta 0.5, ₹150 per lot round trip).

Usage:
  python research/edge_study.py global --out global_data     # Yahoo Finance daily/hourly history, no login
  python research/edge_study.py analyze --data sniper_data --global global_data --report edge_report.md
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
import time as _time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sniper_study as ss  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
DAILY = {"SPX": "^GSPC", "NASDAQ": "^IXIC", "NIKKEI": "^N225", "KOSPI": "^KS11", "HANGSENG": "^HSI",
         "CRUDE": "CL=F", "USDINR": "INR=X", "DXY": "DX-Y.NYB"}
HOURLY = {"NIKKEI": "^N225", "KOSPI": "^KS11", "HANGSENG": "^HSI"}
INDEX_NAMES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX"]


# ------------------------------------------------------------------------------------------- fetch
def _yahoo(sym: str, rng: str, interval: str) -> list[tuple[datetime, float, float]]:
    import requests
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    for attempt in range(4):
        r = requests.get(url, params={"range": rng, "interval": interval}, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0 (research script)"})
        if r.status_code == 200:
            break
        _time.sleep(3 + 3 * attempt)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    tz = ZoneInfo(res["meta"].get("exchangeTimezoneName") or "UTC")
    q = res["indicators"]["quote"][0]
    out = []
    for t, o, c in zip(res.get("timestamp") or [], q["open"], q["close"]):
        if o is None or c is None:
            continue
        out.append((datetime.fromtimestamp(t, timezone.utc).astimezone(tz), float(o), float(c)))
    return out


def fetch_global(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, sym in DAILY.items():
        rows = _yahoo(sym, "5y", "1d")
        with (out / f"{name}_1d.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts", "open", "close"])
            w.writerows([(t.isoformat(), o, c) for t, o, c in rows])
        print(f"{name}: {len(rows)} daily bars from {rows[0][0].date() if rows else None}")
    for name, sym in HOURLY.items():
        rows = _yahoo(sym, "730d", "60m")
        with (out / f"{name}_60m.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts", "open", "close"])
            w.writerows([(t.isoformat(), o, c) for t, o, c in rows])
        print(f"{name}: {len(rows)} hourly bars from {rows[0][0].date() if rows else None}")


def _load(p: Path):
    if not p.exists():
        return []
    with p.open() as f:
        return [(datetime.fromisoformat(r["ts"]), float(r["open"]), float(r["close"])) for r in csv.DictReader(f)]


# ------------------------------------------------------------------------------------ global cues
def global_cues(gdir: Path, days: list[date], b5_nifty) -> dict[date, dict[str, float]]:
    """For each Indian trading day: every cue as a % change, using only what is known by 9:15 IST."""
    daily = {k: _load(gdir / f"{k}_1d.csv") for k in DAILY}
    hourly = {k: _load(gdir / f"{k}_60m.csv") for k in HOURLY}
    # previous session's change for overnight markets: last bar whose local date is before the Indian day
    chg = {}
    for k, rows in daily.items():
        chg[k] = [(t.date(), (c / rows[i - 1][2] - 1) * 100) for i, (t, o, c) in enumerate(rows) if i]
    # Indian open gap from our own 5-minute data
    first, last = {}, {}
    for b in b5_nifty:
        d = b.ts.date()
        first.setdefault(d, b.o)
        last[d] = b.c
    out: dict[date, dict[str, float]] = {}
    nd = sorted(first)
    for j, d in enumerate(nd):
        if d not in days or j == 0:
            continue
        cue = {"GAP": (first[d] / last[nd[j - 1]] - 1) * 100}
        for k in ("SPX", "NASDAQ", "CRUDE", "USDINR", "DXY"):
            prev = [v for dd, v in chg[k] if dd < d]
            if prev:
                cue[k] = prev[-1]
        # Asian morning: from the previous close to the last hourly bar that has closed by 9:15 IST
        cut = datetime.combine(d, datetime.min.time(), IST).replace(hour=9, minute=15)
        for k, rows in hourly.items():
            closes = [(t, c) for t, o, c in rows if t.astimezone(IST).date() == d and t + timedelta(minutes=60) <= cut]
            prevc = [c for t, o, c in daily[k] if t.date() < d]
            if closes and prevc:
                cue[k + "_AM"] = (closes[-1][1] / prevc[-1] - 1) * 100
        out[d] = cue
    return out


def _sgn(x: float, dead: float = 0.0) -> int:
    return 1 if x > dead else -1 if x < -dead else 0


def score(cue: dict[str, float]) -> int:
    """Simple vote: US overnight, Asia this morning, and the opening gap. -3..+3."""
    us = cue.get("SPX")
    asia = [cue[k] for k in ("NIKKEI_AM", "KOSPI_AM", "HANGSENG_AM") if k in cue]
    s = _sgn(us, 0.2) if us is not None else 0
    s += _sgn(sum(asia) / len(asia), 0.2) if asia else 0
    s += _sgn(cue.get("GAP", 0.0), 0.15)
    return s


# ----------------------------------------------------------------------------- 15 indicator states
def indicator_states(bars) -> dict[str, list[int]]:
    """For each bar, +1 (up) / -1 (down) / 0 (no view) from 15 common indicators. Completed bars only."""
    n = len(bars)
    c = [b.c for b in bars]
    h = [b.h for b in bars]
    lo = [b.l for b in bars]
    e9, e21, e50 = ss.ema(c, 9), ss.ema(c, 21), ss.ema(c, 50)
    macd = [a - b for a, b in zip(ss.ema(c, 12), ss.ema(c, 26))]
    sig = ss.ema(macd, 9)
    r = ss.rsi(c, 14)
    sma20 = ss.sma(c, 20)
    a14 = ss.atr(bars, 14)
    st = ss.supertrend_dir(bars, ss.atr(bars, 10), 3.0)
    S: dict[str, list[int]] = {k: [0] * n for k in (
        "EMA 9/21", "Price vs EMA 50", "MACD", "RSI above/below 50", "Stochastic %K/%D", "ADX + DI",
        "Supertrend", "Price vs day average", "Bollinger middle", "CCI", "Williams %R", "Rate of change",
        "Aroon", "Donchian middle", "Heikin-Ashi colour")}
    # stochastic
    k_raw = []
    for i in range(n):
        hh, ll = max(h[max(0, i - 13):i + 1]), min(lo[max(0, i - 13):i + 1])
        k_raw.append(100 * (c[i] - ll) / (hh - ll) if hh > ll else 50)
    k3 = ss.sma(k_raw, 3)
    d3 = ss.sma(k3, 3)
    # ADX / DI (Wilder)
    pdm = [0.0] + [max(h[i] - h[i - 1], 0) if h[i] - h[i - 1] > lo[i - 1] - lo[i] else 0 for i in range(1, n)]
    ndm = [0.0] + [max(lo[i - 1] - lo[i], 0) if lo[i - 1] - lo[i] > h[i] - h[i - 1] else 0 for i in range(1, n)]
    sp = sn = None
    pdi, ndi, dx = [], [], []
    for i in range(n):
        sp = pdm[i] if sp is None else sp + (pdm[i] - sp) / 14
        sn = ndm[i] if sn is None else sn + (ndm[i] - sn) / 14
        a = a14[i] or 1e-9
        p_, m_ = 100 * sp / a, 100 * sn / a
        pdi.append(p_)
        ndi.append(m_)
        dx.append(100 * abs(p_ - m_) / (p_ + m_) if p_ + m_ else 0)
    adx = []
    ax = None
    for x in dx:
        ax = x if ax is None else ax + (x - ax) / 14
        adx.append(ax)
    # CCI
    tp = [(h[i] + lo[i] + c[i]) / 3 for i in range(n)]
    tp20 = ss.sma(tp, 20)
    # Heikin-Ashi
    ha_o, ha_c = [], []
    for i, b in enumerate(bars):
        hc = (b.o + b.h + b.l + b.c) / 4
        ho = (b.o + b.c) / 2 if i == 0 else (ha_o[-1] + ha_c[-1]) / 2
        ha_o.append(ho)
        ha_c.append(hc)
    day_sum, day_n, cur_day = 0.0, 0, None
    for i in range(n):
        if i < 50:
            if bars[i].ts.date() != cur_day:
                cur_day, day_sum, day_n = bars[i].ts.date(), 0.0, 0
            day_sum += tp[i]
            day_n += 1
            continue
        S["EMA 9/21"][i] = _sgn(e9[i] - e21[i])
        S["Price vs EMA 50"][i] = _sgn(c[i] - e50[i])
        S["MACD"][i] = _sgn(macd[i] - sig[i])
        S["RSI above/below 50"][i] = _sgn(r[i] - 50)
        S["Stochastic %K/%D"][i] = _sgn(k3[i] - d3[i])
        S["ADX + DI"][i] = _sgn(pdi[i] - ndi[i]) if adx[i] > 20 else 0
        S["Supertrend"][i] = st[i]
        if bars[i].ts.date() != cur_day:
            cur_day, day_sum, day_n = bars[i].ts.date(), 0.0, 0
        day_sum += tp[i]
        day_n += 1
        S["Price vs day average"][i] = _sgn(c[i] - day_sum / day_n)
        S["Bollinger middle"][i] = _sgn(c[i] - sma20[i])
        md = sum(abs(x - tp20[i]) for x in tp[i - 19:i + 1]) / 20
        S["CCI"][i] = _sgn((tp[i] - tp20[i]) / (0.015 * md) if md else 0)
        hh, ll = max(h[i - 13:i + 1]), min(lo[i - 13:i + 1])
        S["Williams %R"][i] = _sgn((-100 * (hh - c[i]) / (hh - ll) if hh > ll else -50) + 50)
        S["Rate of change"][i] = _sgn(c[i] - c[i - 10])
        win_h, win_l = h[i - 25:i + 1], lo[i - 25:i + 1]
        up = 100 * (25 - (25 - win_h.index(max(win_h)))) / 25
        dn = 100 * (25 - (25 - win_l.index(min(win_l)))) / 25
        S["Aroon"][i] = _sgn(up - dn)
        S["Donchian middle"][i] = _sgn(c[i] - (max(h[i - 20:i]) + min(lo[i - 20:i])) / 2)
        S["Heikin-Ashi colour"][i] = _sgn(ha_c[i] - ha_o[i])
    return S


def vote_state(S, need: int) -> list[int]:
    """+1 / -1 when at least `need` of the 15 indicators point that way on this bar."""
    cols = list(S.values())
    out = []
    for i in range(len(cols[0])):
        up = sum(1 for col in cols if col[i] > 0)
        dn = sum(1 for col in cols if col[i] < 0)
        out.append(1 if up >= need else -1 if dn >= need else 0)
    return out


VOTES = (8, 10, 12, 13, 15)


def combo_state(S, names) -> list[int]:
    cols = [S[k] for k in names]
    return [v if v and all(col[i] == v for col in cols[1:]) else 0 for i, v in enumerate(cols[0])]


# --------------------------------------------------------------------------------------- analysis
def summ(rs):
    if len(rs) < 2:
        return "-"
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1))
    return f"{m:+,.0f} (n={len(rs)}, win {100 * sum(x > 0 for x in rs) / len(rs):.0f}%, t {m / (sd / math.sqrt(len(rs))) if sd else 0:.1f})"


def mean(rs):
    return sum(rs) / len(rs) if rs else 0.0


def analyze(data: Path, gdir: Path | None, test_days: int = 250) -> str:
    lots = {}
    for line in (data / "lots.csv").read_text().splitlines():
        k, lot, kind = line.split(",")
        lots[k] = (int(lot), kind)
    out = ["# Global cues and our own indicator combinations", ""]
    idx = [k for k in INDEX_NAMES if k in lots and (data / f"{k}_5m.csv").exists() and lots[k][0] > 0]
    b5s = {k: ss.load_bars(data / f"{k}_5m.csv") for k in idx}
    alldays = sorted({b.ts.date() for b in b5s["NIFTY"]})
    cut = alldays[-test_days]
    cost = ss.COST_RS["index"]

    # base G/R trades on the 1-hour chart (live rules), and everything needed for filters
    per_index = {}
    for k in idx:
        b5 = b5s[k]
        h1, h2 = ss.TIMEFRAMES[60]
        bt = ss.resample(b5, 60)
        at = ss.atr(bt)
        sigs = ss.make_signals(bt, ss.resample(b5, h1), ss.resample(b5, h2), h1, h2, 60)
        rules = {r: next(f for kk, f in sigs.items() if kk.startswith(r + " ")) for r in ("G", "R")}
        per_index[k] = (b5, bt, at, rules)

    def run(k, fn, mode="tp1", tf_bars=None, base=60):
        b5, bt, at, _ = per_index[k]
        bars, a = (bt, at) if tf_bars is None else tf_bars
        return ss.backtest(bars, a, fn, 1.5, mode, 1, base, 2.0)

    def split(trs_by_index):
        te, tr = [], []
        for k, trs in trs_by_index.items():
            lot = lots[k][0]
            for t in trs:
                (te if t.day >= cut else tr).append(ss.rupees(t, lot, cost))
        return te, tr

    # ---------------------------------------------------------------- A. global cues
    if gdir and (gdir / "SPX_1d.csv").exists():
        cues = global_cues(gdir, alldays, b5s["NIFTY"])
        out += ["## A. Morning global check", "",
                "Does each cue, known by 9:15, point the right way for the index's move from 9:30 to the close?", "",
                "| Cue | Index | Days | Right direction | Avg move when cue up | when cue down |", "|---|---|---|---|---|---|"]
        moves = {}
        for k in idx:
            m = {}
            for b in b5s[k]:
                d = b.ts.date()
                if b.ts.time() >= ss.FIRST_ENTRY and d not in m:
                    m[d] = [b.o, b.c]
                elif d in m:
                    m[d][1] = b.c
            moves[k] = {d: (v[1] / v[0] - 1) * 100 for d, v in m.items()}
        names = ["SPX", "NASDAQ", "NIKKEI_AM", "KOSPI_AM", "HANGSENG_AM", "GAP", "CRUDE", "USDINR", "DXY", "SCORE"]
        for cue_name in names:
            for k in ("NIFTY", "BANKNIFTY"):
                if k not in moves:
                    continue
                pairs = []
                for d, cue in cues.items():
                    v = score(cue) if cue_name == "SCORE" else cue.get(cue_name)
                    if v is None or d not in moves[k] or v == 0:
                        continue
                    pairs.append((v, moves[k][d]))
                if len(pairs) < 30:
                    continue
                right = sum((v > 0) == (mv > 0) for v, mv in pairs) / len(pairs) * 100
                upm = [mv for v, mv in pairs if v > 0]
                dnm = [mv for v, mv in pairs if v < 0]
                out.append(f"| {cue_name} | {k} | {len(pairs)} | {right:.0f}% | {mean(upm):+.2f}% | {mean(dnm):+.2f}% |")
        out += ["", "SCORE = vote of US overnight, Asia this morning and the opening gap (−3 to +3). "
                "50% = no better than a coin toss.", ""]

        # filters on G/R
        out += ["### Rule G/R trades filtered by the morning score (₹ per trade per lot)", "",
                "| Rule | Trades kept | Last year | 2 years before |", "|---|---|---|---|"]
        for rule in ("G", "R"):
            for label, keep in (("all trades (live now)", lambda s, d: True),
                                ("only when score agrees (≥ +1 our way)", lambda s, d: s * d >= 1),
                                ("only when score strongly agrees (≥ +2)", lambda s, d: s * d >= 2),
                                ("skip only when strongly against (≤ −2)", lambda s, d: s * d > -2),
                                ("only when score disagrees (check)", lambda s, d: s * d <= -1)):
                trs = {}
                for k in idx:
                    trs[k] = [t for t in run(k, per_index[k][3][rule])
                              if t.day in cues and keep(score(cues[t.day]), t.d)]
                te, tr = split(trs)
                out.append(f"| {rule} | {label} | {summ(te)} | {summ(tr)} |")
        out += ["", "### Hold longer on days the score strongly agrees?", "",
                "| Rule | Exit on strong-agree days | Last year | 2 years before |", "|---|---|---|---|"]
        for rule in ("G", "R"):
            for mode, label in (("tp1", "all at TP1 (live now)"), ("half", "half at TP1, trail the rest"),
                                ("run", "TP1 then run to TP3")):
                trs = {k: [t for t in run(k, per_index[k][3][rule], mode)
                           if t.day in cues and score(cues[t.day]) * t.d >= 2] for k in idx}
                te, tr = split(trs)
                out.append(f"| {rule} | {label} | {summ(te)} | {summ(tr)} |")
        out.append("")
    else:
        out += ["## A. Morning global check", "", "No global data downloaded.", ""]

    # ---------------------------------------------------------------- B. our own indicator
    out += ["## B. Our own indicator: 15 indicators, alone, in pairs and in threes", ""]
    states = {}
    for k in idx:
        b5, bt, at, _ = per_index[k]
        b15 = ss.resample(b5, 15)
        states[k] = {60: (bt, at, indicator_states(bt)), 15: (b15, ss.atr(b15), indicator_states(b15))}
    names = list(states[idx[0]][60][2].keys())
    combos = [c for r in (1, 2, 3) for c in itertools.combinations(names, r)]

    # B1: the combination as its own entry: all members turn the same way on this bar
    for tf in (60, 15):
        rows = []
        for combo in combos:
            trs = {}
            for k in idx:
                bars, a, S = states[k][tf]
                cs = combo_state(S, combo)
                fn = (lambda cs_: (lambda i: cs_[i] if i and cs_[i] and cs_[i - 1] != cs_[i] else 0))(cs)
                trs[k] = run(k, fn, "tp1", (bars, a), tf)
            te, tr = split(trs)
            rows.append((combo, te, tr))
        vote_rows = []
        for need in VOTES:
            trs = {}
            for k in idx:
                bars, a, S = states[k][tf]
                cs = vote_state(S, need)
                fn = (lambda cs_: (lambda i: cs_[i] if i and cs_[i] and cs_[i - 1] != cs_[i] else 0))(cs)
                trs[k] = run(k, fn, "tp1", (bars, a), tf)
            vote_rows.append((need, *split(trs)))
        both = sum(1 for _, te, tr in rows if len(te) > 30 and len(tr) > 60 and mean(te) > 0 and mean(tr) > 0)
        ranked = sorted([r for r in rows if len(r[2]) >= 60], key=lambda r: -mean(r[2]))[:8]
        out += [f"### {tf}-minute chart: the combination alone as the entry signal", "",
                f"{len(rows)} combinations tested; {both} made money in both periods.", "",
                "Top 8 picked on the older two years, then checked on the last year:", "",
                "| Combination | 2 years before (picked on) | Last year (unseen) |", "|---|---|---|"]
        for combo, te, tr in ranked:
            out.append(f"| {' + '.join(combo)} | {summ(tr)} | {summ(te)} |")
        out += ["", "All 15 voted together (enter when at least N of 15 newly agree):", "",
                "| Agree | 2 years before | Last year |", "|---|---|---|"]
        for need, te, tr in vote_rows:
            out.append(f"| {need} of 15 | {summ(tr)} | {summ(te)} |")
        out.append("")

    # B2: the combination as a filter on rule G/R (1-hour): keep the trade only when the combination agrees
    for rule in ("G", "R"):
        base = {k: run(k, per_index[k][3][rule]) for k in idx}
        bte, btr = split(base)
        rows = []
        for combo in combos:
            trs = {}
            for k in idx:
                bt, at, S = states[k][60]
                cs = combo_state(S, combo)
                f0 = per_index[k][3][rule]
                fn = (lambda cs_, f_: (lambda i: d if (d := f_(i)) and cs_[i] == d else 0))(cs, f0)
                trs[k] = run(k, fn)
            te, tr = split(trs)
            rows.append((combo, te, tr))
        for need in VOTES:
            trs = {}
            for k in idx:
                bt, at, S = states[k][60]
                cs = vote_state(S, need)
                f0 = per_index[k][3][rule]
                fn = (lambda cs_, f_: (lambda i: d if (d := f_(i)) and cs_[i] == d else 0))(cs, f0)
                trs[k] = run(k, fn)
            te, tr = split(trs)
            rows.append(((f"{need} of 15 agree",), te, tr))
        vote_lines = [f"| {r[0][0]} | {summ(r[2])} | {summ(r[1])} |" for r in rows[-len(VOTES):]]
        ranked = sorted([r for r in rows if len(r[2]) >= 30], key=lambda r: -mean(r[2]))[:8]
        out += [f"### Rule {rule} (1-hour) with a combination as an extra check", "",
                f"Rule {rule} alone: last year {summ(bte)}, 2 years before {summ(btr)}.", "",
                "Top 8 checks picked on the older two years, then checked on the last year:", "",
                "| Extra check | 2 years before (picked on) | Last year (unseen) |", "|---|---|---|"]
        for combo, te, tr in ranked:
            out.append(f"| {' + '.join(combo)} | {summ(tr)} | {summ(te)} |")
        out += ["", f"Rule {rule} only when N of the 15 indicators agree:", "",
                "| Extra check | 2 years before | Last year |", "|---|---|---|", *vote_lines, ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("global")
    g.add_argument("--out", default="global_data")
    a_ = sub.add_parser("analyze")
    a_.add_argument("--data", default="sniper_data")
    a_.add_argument("--global", dest="gdir", default="global_data")
    a_.add_argument("--report", default="edge_report.md")
    a = ap.parse_args()
    if a.cmd == "global":
        fetch_global(Path(a.out))
        return 0
    rep = analyze(Path(a.data), Path(a.gdir) if a.gdir else None)
    Path(a.report).write_text(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
