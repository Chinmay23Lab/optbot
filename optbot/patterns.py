"""Candlestick and chart patterns, coded with fixed rules so they can be tested on history.

Every function looks only at bar i and earlier (no look-ahead). Each pattern gives, per bar,
+1 (bullish), -1 (bearish) or 0 (none). Bars need .o .h .l .c attributes.
"""
from __future__ import annotations


def _prior_trend(c, i, n=5):
    """+1 if price rose over the n bars before bar i, -1 if it fell (reversal patterns need one)."""
    if i - n - 1 < 0:
        return 0
    return 1 if c[i - 1] > c[i - 1 - n] else -1


def candle_patterns_full(bars) -> dict[str, list[int]]:
    n = len(bars)
    names = [
        # single candle
        "hammer", "inverted hammer", "hanging man", "shooting star", "marubozu", "dragonfly doji",
        "gravestone doji", "belt hold", "strong close",
        # two candles
        "engulfing", "harami", "piercing / dark cloud", "tweezer bottom / top", "kicker", "inside-bar break",
        "outside bar",
        # three candles
        "morning / evening star", "three soldiers / crows", "three inside up / down", "three outside up / down",
        "abandoned baby", "three-bar reversal",
    ]
    out = {k: [0] * n for k in names}
    c = [b.c for b in bars]
    for i in range(3, n):
        b, p, q = bars[i], bars[i - 1], bars[i - 2]
        rng = b.h - b.l
        if rng <= 0:
            continue
        body = abs(b.c - b.o)
        up, lo = b.h - max(b.o, b.c), min(b.o, b.c) - b.l
        pbody, qbody = abs(p.c - p.o), abs(q.c - q.o)
        prng = max(p.h - p.l, 1e-9)
        tr = _prior_trend(c, i)
        bull, bear = b.c > b.o, b.c < b.o
        pbull, pbear = p.c > p.o, p.c < p.o
        hammer_shape = lo >= 2 * body and up <= 0.25 * rng and lo >= 0.5 * rng
        star_shape = up >= 2 * body and lo <= 0.25 * rng and up >= 0.5 * rng
        # single
        if hammer_shape and tr == -1:
            out["hammer"][i] = 1
        if star_shape and tr == -1:
            out["inverted hammer"][i] = 1
        if hammer_shape and tr == 1:
            out["hanging man"][i] = -1
        if star_shape and tr == 1:
            out["shooting star"][i] = -1
        if body >= 0.9 * rng:
            out["marubozu"][i] = 1 if bull else -1
        if body <= 0.1 * rng:
            if up <= 0.1 * rng and tr == -1:
                out["dragonfly doji"][i] = 1
            elif lo <= 0.1 * rng and tr == 1:
                out["gravestone doji"][i] = -1
        if bull and b.o - b.l <= 0.05 * rng and body >= 0.6 * rng and tr == -1:
            out["belt hold"][i] = 1
        elif bear and b.h - b.o <= 0.05 * rng and body >= 0.6 * rng and tr == 1:
            out["belt hold"][i] = -1
        if body >= 0.6 * rng and bull and b.c - b.l >= 0.75 * rng:
            out["strong close"][i] = 1
        elif body >= 0.6 * rng and bear and b.h - b.c >= 0.75 * rng:
            out["strong close"][i] = -1
        # two candles
        if bull and pbear and b.c >= p.o and b.o <= p.c and body > pbody:
            out["engulfing"][i] = 1
        elif bear and pbull and b.c <= p.o and b.o >= p.c and body > pbody:
            out["engulfing"][i] = -1
        if pbody >= 0.6 * prng and body <= 0.5 * pbody and max(b.o, b.c) <= max(p.o, p.c) and min(b.o, b.c) >= min(p.o, p.c):
            out["harami"][i] = 1 if pbear and tr == -1 else (-1 if pbull and tr == 1 else 0)
        mid = (p.o + p.c) / 2
        if pbear and bull and b.o < p.c and mid < b.c < p.o and tr == -1:
            out["piercing / dark cloud"][i] = 1
        elif pbull and bear and b.o > p.c and p.o < b.c < mid and tr == 1:
            out["piercing / dark cloud"][i] = -1
        tol = 0.05 * rng
        if abs(b.l - p.l) <= tol and pbear and bull and tr == -1:
            out["tweezer bottom / top"][i] = 1
        elif abs(b.h - p.h) <= tol and pbull and bear and tr == 1:
            out["tweezer bottom / top"][i] = -1
        if pbear and bull and b.o > p.o and body >= 0.6 * rng:
            out["kicker"][i] = 1
        elif pbull and bear and b.o < p.o and body >= 0.6 * rng:
            out["kicker"][i] = -1
        if p.h <= q.h and p.l >= q.l:
            out["inside-bar break"][i] = 1 if b.c > p.h else (-1 if b.c < p.l else 0)
        if b.h > p.h and b.l < p.l:
            out["outside bar"][i] = 1 if bull and b.c > p.h else (-1 if bear and b.c < p.l else 0)
        # three candles
        small_mid = pbody <= 0.35 * max(qbody, 1e-9)
        if q.c < q.o and small_mid and bull and b.c > (q.o + q.c) / 2 and tr == -1:
            out["morning / evening star"][i] = 1
        elif q.c > q.o and small_mid and bear and b.c < (q.o + q.c) / 2 and tr == 1:
            out["morning / evening star"][i] = -1
        if all(x.c > x.o for x in (q, p, b)) and q.c < p.c < b.c and q.o < p.o < q.c and p.o < b.o < p.c:
            out["three soldiers / crows"][i] = 1
        elif all(x.c < x.o for x in (q, p, b)) and q.c > p.c > b.c and q.c < p.o < q.o and p.c < b.o < p.o:
            out["three soldiers / crows"][i] = -1
        if out["harami"][i - 1] == 1 and bull and b.c > q.o:
            out["three inside up / down"][i] = 1
        elif out["harami"][i - 1] == -1 and bear and b.c < q.o:
            out["three inside up / down"][i] = -1
        if out["engulfing"][i - 1] == 1 and bull and b.c > p.c:
            out["three outside up / down"][i] = 1
        elif out["engulfing"][i - 1] == -1 and bear and b.c < p.c:
            out["three outside up / down"][i] = -1
        if pbody <= 0.1 * prng and p.h < q.l and b.l > p.h and bull and q.c < q.o:
            out["abandoned baby"][i] = 1
        elif pbody <= 0.1 * prng and p.l > q.h and b.h < p.l and bear and q.c > q.o:
            out["abandoned baby"][i] = -1
        if p.l < q.l and p.l < b.l and b.c > q.h:
            out["three-bar reversal"][i] = 1
        elif p.h > q.h and p.h > b.h and b.c < q.l:
            out["three-bar reversal"][i] = -1
    return out


def _swings(bars, k=3):
    """Swing highs/lows confirmed k bars later. Returns, per bar i, the swings known by bar i:
    lists of (index, price) for highs and lows."""
    n = len(bars)
    highs, lows = [], []
    known_h, known_l = [None] * n, [None] * n
    for i in range(n):
        j = i - k
        if j - k >= 0:
            win = bars[j - k:j + k + 1]
            if bars[j].h == max(x.h for x in win):
                highs.append((j, bars[j].h))
            if bars[j].l == min(x.l for x in win):
                lows.append((j, bars[j].l))
        known_h[i], known_l[i] = len(highs), len(lows)
    return highs, lows, known_h, known_l


def chart_patterns(bars, a) -> dict[str, list[int]]:
    """Chart patterns that can be defined objectively. `a` is ATR per bar (tolerances scale with it).
    Each fires on the bar that BREAKS the pattern (the usual entry point)."""
    n = len(bars)
    names = ["double bottom / top", "triple bottom / top", "inverse head & shoulders / head & shoulders",
             "ascending / descending triangle", "symmetrical triangle break", "range breakout (20 bars)",
             "flag / pennant", "higher highs & lows / lower highs & lows", "swing high / low break",
             "rising / falling wedge break", "cup and handle (rounded base)", "channel breakout"]
    out = {k: [0] * n for k in names}
    highs, lows, kh, kl = _swings(bars)
    for i in range(30, n):
        b, p = bars[i], bars[i - 1]
        tol = 0.5 * a[i]
        H, L = highs[:kh[i]], lows[:kl[i]]
        def crossed_up(level):
            return p.c <= level < b.c

        def crossed_dn(level):
            return p.c >= level > b.c
        # double / triple bottom & top: neckline = the swing between them
        if len(L) >= 2 and H:
            (i1, l1), (i2, l2) = L[-2], L[-1]
            neck = max((h for j, h in H if i1 < j < i2), default=None)
            if neck and abs(l1 - l2) <= tol and crossed_up(neck):
                out["double bottom / top"][i] = 1
            if len(L) >= 3 and neck:
                l0 = L[-3][1]
                if max(l0, l1, l2) - min(l0, l1, l2) <= tol and crossed_up(neck):
                    out["triple bottom / top"][i] = 1
            if len(L) >= 3:
                (j0, s1), (j1, hd), (j2, s2) = L[-3], L[-2], L[-1]
                nk = [h for j, h in H if j0 < j < j2]
                if nk and hd < min(s1, s2) - tol and abs(s1 - s2) <= 2 * tol and crossed_up(max(nk)):
                    out["inverse head & shoulders / head & shoulders"][i] = 1
        if len(H) >= 2 and L:
            (i1, h1), (i2, h2) = H[-2], H[-1]
            neck = min((l for j, l in L if i1 < j < i2), default=None)
            if neck and abs(h1 - h2) <= tol and crossed_dn(neck):
                out["double bottom / top"][i] = -1
            if len(H) >= 3 and neck:
                h0 = H[-3][1]
                if max(h0, h1, h2) - min(h0, h1, h2) <= tol and crossed_dn(neck):
                    out["triple bottom / top"][i] = -1
            if len(H) >= 3:
                (j0, s1), (j1, hd), (j2, s2) = H[-3], H[-2], H[-1]
                nk = [l for j, l in L if j0 < j < j2]
                if nk and hd > max(s1, s2) + tol and abs(s1 - s2) <= 2 * tol and crossed_dn(min(nk)):
                    out["inverse head & shoulders / head & shoulders"][i] = -1
        # triangles and wedges from the last two swing highs and lows
        if len(H) >= 2 and len(L) >= 2:
            (_, h1), (_, h2) = H[-2], H[-1]
            (_, l1), (_, l2) = L[-2], L[-1]
            flat_top, flat_bot = abs(h1 - h2) <= tol, abs(l1 - l2) <= tol
            if flat_top and l2 > l1 + tol and crossed_up(max(h1, h2)):
                out["ascending / descending triangle"][i] = 1
            if flat_bot and h2 < h1 - tol and crossed_dn(min(l1, l2)):
                out["ascending / descending triangle"][i] = -1
            if h2 < h1 - tol and l2 > l1 + tol:
                if crossed_up(h2):
                    out["symmetrical triangle break"][i] = 1
                elif crossed_dn(l2):
                    out["symmetrical triangle break"][i] = -1
            # rising wedge (both rising, lows faster) breaks down; falling wedge breaks up
            if h2 > h1 and l2 > l1 and (l2 - l1) > (h2 - h1) and crossed_dn(l2):
                out["rising / falling wedge break"][i] = -1
            if h2 < h1 and l2 < l1 and (h1 - h2) > (l1 - l2) and crossed_up(h2):
                out["rising / falling wedge break"][i] = 1
            if h2 > h1 + tol and l2 > l1 + tol and crossed_up(h2):
                out["higher highs & lows / lower highs & lows"][i] = 1
            elif h2 < h1 - tol and l2 < l1 - tol and crossed_dn(l2):
                out["higher highs & lows / lower highs & lows"][i] = -1
            # channel: both slopes alike, break of the channel edge
            if abs((h2 - h1) - (l2 - l1)) <= tol:
                if crossed_up(h2 + (h2 - h1) / 2):
                    out["channel breakout"][i] = 1
                elif crossed_dn(l2 + (l2 - l1) / 2):
                    out["channel breakout"][i] = -1
        if H and crossed_up(H[-1][1]):
            out["swing high / low break"][i] = 1
        elif L and crossed_dn(L[-1][1]):
            out["swing high / low break"][i] = -1
        hi20 = max(x.h for x in bars[i - 20:i])
        lo20 = min(x.l for x in bars[i - 20:i])
        if b.c > hi20:
            out["range breakout (20 bars)"][i] = 1
        elif b.c < lo20:
            out["range breakout (20 bars)"][i] = -1
        # flag: strong move over bars i-13..i-6, then a tight pause i-5..i-1, then a break in the move's direction
        pole = bars[i - 6].c - bars[i - 13].c
        box = bars[i - 5:i]
        bh, bl = max(x.h for x in box), min(x.l for x in box)
        if abs(pole) >= 3 * a[i] and bh - bl <= 0.5 * abs(pole):
            if pole > 0 and b.c > bh:
                out["flag / pennant"][i] = 1
            elif pole < 0 and b.c < bl:
                out["flag / pennant"][i] = -1
        # cup and handle (rounded base): 30-bar base whose middle is lowest, rim retested, then rim broken
        win = bars[i - 30:i]
        rim_l, rim_r = win[0].h, max(x.h for x in win[-8:])
        mid_low = min(x.l for x in win[8:22])
        if abs(rim_l - rim_r) <= tol and mid_low < min(rim_l, rim_r) - 2 * a[i] and crossed_up(max(rim_l, rim_r)):
            out["cup and handle (rounded base)"][i] = 1
    return out
