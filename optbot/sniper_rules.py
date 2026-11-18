"""Sniper-style entry rules, shared by the live bot and research/sniper_study.py (one copy, identical logic).

Rebuilt from the visible parts of the Sniper Short 2.0 TradingView indicator: EMA 5/21 band cross, EMA 100/200
trend, agreement of two higher timeframes, plus MACD, RSI, Supertrend, VWMA (approximated by SMA, as index
candles carry no volume) and the previous session's standard pivot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class Bar:
    ts: datetime   # start of the bar
    o: float
    h: float
    l: float
    c: float


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


def htf_dir(bars15: list[Bar], bars_h: list[Bar], minutes: int, base: int = 15) -> list[int]:
    """For each 15m bar, the EMA5 vs EMA21 direction of the last COMPLETED higher-timeframe bar."""
    c = [b.c for b in bars_h]
    f, s = ema(c, 5), ema(c, 21)
    ends = [b.ts + timedelta(minutes=minutes) for b in bars_h]
    out, j = [], -1
    for b in bars15:
        done = b.ts + timedelta(minutes=base)
        while j + 1 < len(bars_h) and ends[j + 1] <= done:
            j += 1
        out.append(0 if j < 21 else (1 if f[j] > s[j] else -1))
    return out


def sma(xs, n):
    out, run = [], 0.0
    for i, x in enumerate(xs):
        run += x - (xs[i - n] if i >= n else 0)
        out.append(run / min(i + 1, n))
    return out


def rsi(xs, n=14):
    out, g, l = [50.0], None, None
    for i in range(1, len(xs)):
        ch = xs[i] - xs[i - 1]
        up, dn = max(ch, 0), max(-ch, 0)
        g = up if g is None else g + (up - g) / n
        l = dn if l is None else l + (dn - l) / n
        out.append(100.0 if l == 0 else 100 - 100 / (1 + g / l))
    return out


def a15_for(bars):
    return atr(bars, 10)


def supertrend_dir(bars, a, mult):
    out, d, up_b, dn_b = [], 1, None, None
    for i, b in enumerate(bars):
        mid = (b.h + b.l) / 2
        ub, lb = mid + mult * a[i], mid - mult * a[i]
        if i == 0:
            up_b, dn_b = ub, lb
        else:
            up_b = ub if ub < up_b or bars[i - 1].c > up_b else up_b
            dn_b = lb if lb > dn_b or bars[i - 1].c < dn_b else dn_b
            if d == 1 and b.c < dn_b:
                d = -1
            elif d == -1 and b.c > up_b:
                d = 1
        out.append(d)
    return out


def pivots(bars):
    """Standard pivot (H+L+C)/3 of the previous session, for each bar."""
    out, prev, cur_day, h, l, c = [], None, None, None, None, None
    for b in bars:
        day = b.ts.date()
        if day != cur_day:
            if cur_day is not None:
                prev = (h + l + c) / 3
            cur_day, h, l = day, b.h, b.l
        h, l, c = max(h, b.h), min(l, b.l), b.c
        out.append(prev)
    return out


# ----------------------------------------------------------------------------------------- signals
def candle_patterns(bars) -> dict[str, list[int]]:
    """Classic candlestick patterns per bar: +1 bullish, -1 bearish, 0 none. Uses bar i and earlier only."""
    n = len(bars)
    out = {k: [0] * n for k in ("engulfing", "pin bar", "strong close", "inside-bar break")}
    for i in range(2, n):
        b, p, q = bars[i], bars[i - 1], bars[i - 2]
        rng = b.h - b.l
        if rng <= 0:
            continue
        body = abs(b.c - b.o)
        up, lo = b.h - max(b.o, b.c), min(b.o, b.c) - b.l
        if b.c > b.o and p.c < p.o and b.c >= p.o and b.o <= p.c and body > abs(p.c - p.o):
            out["engulfing"][i] = 1
        elif b.c < b.o and p.c > p.o and b.c <= p.o and b.o >= p.c and body > abs(p.c - p.o):
            out["engulfing"][i] = -1
        if lo >= 2 * body and lo >= 0.6 * rng and up <= 0.25 * rng:
            out["pin bar"][i] = 1           # hammer
        elif up >= 2 * body and up >= 0.6 * rng and lo <= 0.25 * rng:
            out["pin bar"][i] = -1          # shooting star
        if body >= 0.6 * rng and b.c - b.l >= 0.75 * rng and b.c > b.o:
            out["strong close"][i] = 1
        elif body >= 0.6 * rng and b.h - b.c >= 0.75 * rng and b.c < b.o:
            out["strong close"][i] = -1
        if p.h <= q.h and p.l >= q.l:       # previous bar was an inside bar
            out["inside-bar break"][i] = 1 if b.c > p.h else (-1 if b.c < p.l else 0)
    return out


def make_signals(b15, b30, b60, h1: int = 30, h2: int = 60, base: int = 15):
    c = [b.c for b in b15]
    e5, e21, e100, e200 = ema(c, 5), ema(c, 21), ema(c, 100), ema(c, 200)
    d30, d60 = htf_dir(b15, b30, h1, base), htf_dir(b15, b60, h2, base)

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

    # Confirmations Chinmay says the indicator combines: MACD, RSI, Supertrend, VWMA, standard pivot points.
    # Index candles carry no volume, so VWMA is approximated by a 20-bar simple average.
    ml = [a - b for a, b in zip(ema(c, 12), ema(c, 26))]
    hist = [a - b for a, b in zip(ml, ema(ml, 9))]
    r = rsi(c, 14)
    st = supertrend_dir(b15, a15_for(b15), 3.0)
    vw = sma(c, 20)
    piv = pivots(b15)

    def confirms(i, d):
        checks = [hist[i] * d > 0, (r[i] - 50) * d > 0, st[i] == d, (c[i] - vw[i]) * d > 0,
                  piv[i] is not None and (c[i] - piv[i]) * d > 0]
        return sum(checks)

    pat = candle_patterns(b15)

    def candle(i, d, kinds=("engulfing", "pin bar", "strong close", "inside-bar break")):
        return any(pat[k][i] == d for k in kinds)

    D = lambda i: (d if (d := cross(i)) and confirms(i, d) == 5 else 0)  # noqa: E731
    E = lambda i: (d if (d := cross(i)) and trend(i, d) and confirms(i, d) >= 4 else 0)  # noqa: E731
    F = lambda i: (d if (d := cross(i)) and trend(i, d) and d30[i] == d and d60[i] == d and confirms(i, d) == 5 else 0)  # noqa: E731

    def pattern_entry(i, kinds, need):
        if i < 200:
            return 0
        for d in (1, -1):
            if candle(i, d, kinds) and trend(i, d) and confirms(i, d) >= need:
                return d
        return 0

    return {
        "G D + confirming candle": lambda i: (d if (d := D(i)) and candle(i, d) else 0),
        "H E + confirming candle": lambda i: (d if (d := E(i)) and candle(i, d) else 0),
        "I F + confirming candle": lambda i: (d if (d := F(i)) and candle(i, d) else 0),
        "J any candle pattern + trend + all 5": lambda i: pattern_entry(i, tuple(pat), 5),
        "K engulfing + trend + all 5": lambda i: pattern_entry(i, ("engulfing",), 5),
        "L pin bar (hammer/shooting star) + trend + 4 of 5": lambda i: pattern_entry(i, ("pin bar",), 4),
        "D cross + all 5 (MACD, RSI, Supertrend, VWMA, pivot)": lambda i: (d if (d := cross(i)) and confirms(i, d) == 5 else 0),
        "E cross + trend + 4 of 5 confirmations": lambda i: (d if (d := cross(i)) and trend(i, d) and confirms(i, d) >= 4 else 0),
        "F everything: C + all 5 confirmations": lambda i: (d if (d := cross(i)) and trend(i, d) and d30[i] == d
                                                             and d60[i] == d and confirms(i, d) == 5 else 0),
        "A band cross": lambda i: cross(i),
        "B cross + 100/200 trend": lambda i: (d if (d := cross(i)) and trend(i, d) else 0),
        "C cross + trend + higher timeframes agree": lambda i: (d if (d := cross(i)) and trend(i, d)
                                                     and d30[i] == d and d60[i] == d else 0),
    }




# ----------------------------------------------------------------------------------------- live use
TIMEFRAMES = {5: (15, 30), 10: (30, 60), 15: (30, 60), 30: (60, 120), 60: (120, 375)}


def live_signal(candles5, now: datetime, rule: str, tf: int) -> tuple[int, str, float, float]:
    """Check the latest COMPLETED `tf`-minute bar for a fresh signal.

    candles5: completed 5-minute candles (optbot.models.Candle), oldest first, several weeks back.
    Returns (direction 1/-1/0, reason, ATR of the signal timeframe, close of the signal bar).
    """
    b5 = [Bar(c.ts.replace(tzinfo=None), c.open, c.high, c.low, c.close) for c in candles5]
    if len(b5) < 50:
        return 0, "not enough history", 0.0, 0.0
    h1, h2 = TIMEFRAMES[tf]
    naive_now = now.replace(tzinfo=None)
    bt = b5 if tf == 5 else resample(b5, tf)
    while bt and bt[-1].ts + timedelta(minutes=tf) > naive_now:   # drop the bar still forming
        bt.pop()
    if len(bt) < 210:
        return 0, f"need 210 {tf}-minute bars, have {len(bt)}", 0.0, 0.0
    i = len(bt) - 1
    if naive_now - (bt[i].ts + timedelta(minutes=tf)) > timedelta(minutes=10):
        return 0, "no new bar yet", 0.0, 0.0
    sigs = make_signals(bt, resample(b5, h1), resample(b5, h2), h1, h2, tf)
    name = next(k for k in sigs if k.startswith(rule))
    d = sigs[name](i)
    a = atr(bt)[i]
    if not d:
        return 0, f"no {tf}m signal ({name})", a, bt[i].c
    return d, f"{tf}m {name}", a, bt[i].c
