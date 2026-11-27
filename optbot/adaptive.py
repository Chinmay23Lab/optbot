"""Adaptive day-type rules (27 Nov 2026, Chinmay: "don't stick to one rule, the market changes every day").

Each 15-minute bar after the first hour, the day is classed from what has happened so far (no look-ahead):
  * jumpy  - the first hour's range is over twice its 10-day average: stay out
  * trend  - price has closed beyond the first-hour range by 0.2 ATR with the 15m EMA9/21 agreeing: ride it
  * range  - price is still inside the first-hour range and the day is quiet: buy near the range low on a bullish
             candle (engulfing, hammer, strong close), sell near the high on a bearish one; target the middle
Used by research/adaptive_study.py (3-year test) and by the engine's "adaptive" paper account, so both run
the same code.
"""
from __future__ import annotations

from datetime import time, timedelta

from .sniper_rules import Bar, atr, candle_patterns, ema

FIRST_HOUR_END = time(10, 15)
LAST_ENTRY = time(14, 0)
TREND_CLEAR_ATR = 0.2     # close beyond the first-hour range by this many 15m ATRs
TREND_SL_ATR = 1.5
TREND_TP_X = 2.0
RANGE_EDGE = 0.20         # "near the edge" = within this share of the first-hour range
RANGE_MIN_RR = 1.0
JUMPY_X = 2.0
CANDLES = ("engulfing", "pin bar", "strong close")


def _days(bars: list[Bar]) -> list[tuple[int, int]]:
    """(start, end) index of each session, end exclusive."""
    out, s = [], 0
    for i in range(1, len(bars) + 1):
        if i == len(bars) or bars[i].ts.date() != bars[s].ts.date():
            out.append((s, i))
            s = i
    return out


class Adaptive:
    """Precomputes indicators on a list of completed 15-minute bars; signal(i) looks at bar i and earlier only."""

    def __init__(self, b15: list[Bar], modes=("trend", "range")):
        self.b, self.modes = b15, set(modes)
        c = [x.c for x in b15]
        self.a = atr(b15)
        self.e9, self.e21 = ema(c, 9), ema(c, 21)
        self.pat = candle_patterns(b15)
        self.day_of = [0] * len(b15)
        self.days = _days(b15)
        self.ib: list[tuple[float, float] | None] = []
        for k, (s, e) in enumerate(self.days):
            for j in range(s, e):
                self.day_of[j] = k
            first = [x for x in b15[s:e] if (x.ts + timedelta(minutes=15)).time() <= FIRST_HOUR_END]
            self.ib.append((max(x.h for x in first), min(x.l for x in first)) if len(first) >= 4 else None)
        self.taken: dict[tuple[int, str], int] = {}

    def day_type(self, i: int) -> str:
        k = self.day_of[i]
        ib = self.ib[k]
        if ib is None:
            return "unknown"
        prev = [h - lo for h, lo in (x for x in self.ib[max(0, k - 10):k] if x)]
        if len(prev) >= 5 and (ib[0] - ib[1]) > JUMPY_X * (sum(prev) / len(prev)):
            return "jumpy"
        s = self.days[k][0]
        a = self.a[i] or 1e-9
        hi_close = max(x.c for x in self.b[s:i + 1])
        lo_close = min(x.c for x in self.b[s:i + 1])
        if hi_close > ib[0] + TREND_CLEAR_ATR * a or lo_close < ib[1] - TREND_CLEAR_ATR * a:
            return "trend"
        return "range"

    def signal(self, i: int) -> tuple[int, str, float, float]:
        """(direction, reason, stop price, target price) for an entry at bar i's close; direction 0 = none."""
        b = self.b[i]
        done = (b.ts + timedelta(minutes=15)).time()
        if not (FIRST_HOUR_END < done <= LAST_ENTRY) or i < 30:
            return 0, "outside entry window", 0, 0
        k = self.day_of[i]
        ib = self.ib[k]
        if ib is None:
            return 0, "first hour incomplete", 0, 0
        kind = self.day_type(i)
        a = self.a[i]
        if kind == "jumpy":
            return 0, "jumpy day: staying out", 0, 0
        if kind == "trend" and "trend" in self.modes:
            for d in (1, -1):
                beyond = (b.c > ib[0] + TREND_CLEAR_ATR * a) if d == 1 else (b.c < ib[1] - TREND_CLEAR_ATR * a)
                if beyond and (self.e9[i] - self.e21[i]) * d > 0 and not self.taken.get((k, f"t{d}")):
                    self.taken[(k, f"t{d}")] = i
                    risk = TREND_SL_ATR * a
                    return d, f"trend day: close beyond first-hour {'high' if d == 1 else 'low'}", \
                        b.c - d * risk, b.c + d * TREND_TP_X * risk
            return 0, "trend day: no fresh breakout", 0, 0
        if kind == "range" and "range" in self.modes:
            hi, lo = ib
            w = hi - lo
            mid = (hi + lo) / 2
            for d in (1, -1):
                near = (b.l <= lo + RANGE_EDGE * w) if d == 1 else (b.h >= hi - RANGE_EDGE * w)
                cndl = any(self.pat[n][i] == d for n in CANDLES)
                if near and cndl and self.taken.get((k, f"r{d}"), 0) < 1:
                    s = self.days[k][0]
                    stop = (min(x.l for x in self.b[s:i + 1]) - 0.3 * a) if d == 1 else \
                        (max(x.h for x in self.b[s:i + 1]) + 0.3 * a)
                    risk, reward = d * (b.c - stop), d * (mid - b.c)
                    if risk > 0 and reward >= RANGE_MIN_RR * risk:
                        self.taken[(k, f"r{d}")] = 1
                        return d, f"range day: {'bullish candle near the low' if d == 1 else 'bearish candle near the high'}", \
                            stop, mid
            return 0, "range day: no candle at the edge", 0, 0
        return 0, f"{kind} day", 0, 0
