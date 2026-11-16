from __future__ import annotations

from .models import Candle


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def atr(candles: list[Candle], period: int) -> float:
    if len(candles) < 2:
        return candles[0].high - candles[0].low if candles else 0.0
    trs = []
    for prev, c in zip(candles, candles[1:]):
        trs.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
    trs = trs[-period:]
    return sum(trs) / len(trs)


def pct_change(a: float, b: float) -> float:
    return (b - a) / a * 100 if a else 0.0
