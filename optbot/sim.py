"""Synthetic market for tests and dry runs (no network, no credentials).

Index paths are random walks; option prices come from Black-Scholes with a bid/ask spread.
This exercises the whole pipeline. It says NOTHING about whether the strategy makes money:
only paper trading on real Angel One data can do that.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

from .clock import IST, SimClock
from .instruments import Instruments
from .models import Candle, Contract, Quote

SPOTS = {"NIFTY": 25800.0, "BANKNIFTY": 58500.0, "FINNIFTY": 27400.0, "SENSEX": 84500.0, "BANKEX": 65000.0}
LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "SENSEX": 20, "BANKEX": 30}


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(spot: float, strike: float, t_years: float, vol: float, right: str, r: float = 0.065) -> float:
    t = max(t_years, 1e-5)
    d1 = (math.log(spot / strike) + (r + vol * vol / 2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if right == "CE":
        return spot * _ncdf(d1) - strike * math.exp(-r * t) * _ncdf(d2)
    return strike * math.exp(-r * t) * _ncdf(-d2) - spot * _ncdf(-d1)


def synthetic_rows(index_cfg: dict, today: date) -> list[dict]:
    rows = []
    for idx, c in index_cfg.items():
        step = c["strike_step"]
        spot = SPOTS[idx]
        rows.append({"token": f"S-{idx}", "symbol": c["spot_names"][0], "name": c["spot_names"][0],
                     "exch_seg": c["spot_exchange"], "instrumenttype": "AMXIDX", "expiry": "", "strike": "0",
                     "lotsize": "1", "tick_size": "5"})
        # weekly-style expiries 1..3 weeks out
        for w in range(0, 3):
            exp = today + timedelta(days=((1 - today.weekday()) % 7) + 7 * w)
            for k in range(-40, 41):
                strike = round(spot / step) * step + k * step
                for right in ("CE", "PE"):
                    rows.append({"token": f"{idx}-{exp:%d%b%y}-{int(strike)}-{right}",
                                 "symbol": f"{idx}{exp:%d%b%y}{int(strike)}{right}".upper(), "name": idx,
                                 "exch_seg": c["segment"], "instrumenttype": "OPTIDX",
                                 "expiry": exp.strftime("%d%b%Y").upper(), "strike": f"{strike * 100:.6f}",
                                 "lotsize": str(LOTS[idx]), "tick_size": "5"})
    rows.append({"token": "S-VIX", "symbol": "India VIX", "name": "INDIA VIX", "exch_seg": "NSE",
                 "instrumenttype": "AMXIDX", "expiry": "", "strike": "0", "lotsize": "1", "tick_size": "5"})
    return rows


class SimMarket:
    def __init__(self, clock: SimClock, inst: Instruments, seed: int = 7, vix: float = 13.5):
        self.clock = clock
        self.inst = inst
        self.rng = random.Random(seed)
        self._vix = vix
        self.paths: dict[str, list[tuple[datetime, float]]] = {}
        self.history: dict[str, list[Candle]] = {}
        self.today: date | None = None

    def _ensure_day(self, d: date) -> None:
        if self.today == d:
            return
        self.today = d
        for idx, s0 in SPOTS.items():
            # 30 days of daily history ending yesterday
            px, hist = s0, []
            for i in range(30, 0, -1):
                o = px
                px *= math.exp(self.rng.gauss(0.0004, 0.009))
                hist.append(Candle(datetime.combine(d - timedelta(days=i), datetime.min.time(), tzinfo=IST),
                                   o, max(o, px) * 1.003, min(o, px) * 0.997, px))
            self.history[idx] = hist
            # intraday: 1-minute path 09:15..15:30 with a random trend for the day
            drift = self.rng.choice([-1, 0, 1]) * self.rng.uniform(0.00002, 0.00008)
            t = datetime.combine(d, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15)
            p, path = px, []
            while t <= t.replace(hour=15, minute=30):
                path.append((t, p))
                p *= math.exp(self.rng.gauss(drift, 0.0006))
                t += timedelta(minutes=1)
            self.paths[idx] = path

    def _spot(self, idx: str, at: datetime) -> float:
        self._ensure_day(at.date())
        path = self.paths[idx]
        i = max(0, min(len(path) - 1, int((at - path[0][0]).total_seconds() // 60)))
        return path[i][1]

    # --- DataSource interface -------------------------------------------------
    def index_ltp(self, index: str) -> float | None:
        return self._spot(index, self.clock.now())

    def vix(self) -> float | None:
        return self._vix

    def daily_candles(self, index: str, n: int) -> list[Candle]:
        self._ensure_day(self.clock.now().date())
        return self.history[index][-n:]

    def intraday_candles(self, index: str, day: date) -> list[Candle]:
        now = self.clock.now()
        self._ensure_day(day)
        out = []
        path = [x for x in self.paths[index] if x[0] < now]
        for i in range(0, len(path) - 4, 5):
            chunk = path[i : i + 5]
            if chunk[0][0] + timedelta(minutes=5) > now:
                break
            ps = [p for _, p in chunk]
            out.append(Candle(chunk[0][0], ps[0], max(ps), min(ps), ps[-1]))
        # warm-up candles from "yesterday" so EMAs are seeded
        y = self.history[index][-1]
        warm = [Candle(y.ts.replace(hour=15, minute=0) + timedelta(minutes=5 * k), y.close, y.close, y.close, y.close)
                for k in range(6)]
        return warm + out

    def history_candles(self, name: str, days: int) -> list[Candle]:
        """Synthetic past 5-minute candles (random walk ending at today's open) plus today's candles."""
        day = self.clock.now().date()
        today = [c for c in self.intraday_candles(name, day) if c.ts.date() == day]
        key = (name, day, days)
        cache = getattr(self, "_hist", {})
        self._hist = cache
        if key not in cache:
            rnd = random.Random(hash(key) & 0xFFFF)
            p = today[0].open if today else self._spot(name, self.clock.now())
            bars, d = [], day - timedelta(days=1)
            while len(bars) < days * 75 * 5 // 7:
                if d.weekday() < 5:
                    t = datetime.combine(d, datetime.min.time(), tzinfo=IST).replace(hour=15, minute=25)
                    for k in range(75):
                        c = p
                        p = p / (1 + rnd.gauss(0, 0.0012))
                        bars.append(Candle(t - timedelta(minutes=5 * k), p, max(p, c) * 1.0003, min(p, c) * 0.9997, c))
                d -= timedelta(days=1)
            cache[key] = sorted(bars, key=lambda b: b.ts)
        return cache[key] + today

    def quotes(self, contracts: list[Contract]) -> dict[str, Quote]:
        now = self.clock.now()
        out = {}
        for c in contracts:
            spot = self._spot(c.index, now)
            expiry_dt = datetime.combine(c.expiry, datetime.min.time(), tzinfo=IST).replace(hour=15, minute=30)
            t = max((expiry_dt - now).total_seconds(), 60) / (365 * 24 * 3600)
            px = max(0.05, bs_price(spot, c.strike, t, self._vix / 100 * 1.05, c.right))
            half = max(c.tick, px * 0.004)
            bid = max(0.05, round((px - half) / c.tick) * c.tick)
            ask = round((px + half) / c.tick) * c.tick
            out[c.token] = Quote(c.token, round(px, 2), round(bid, 2), round(ask, 2), 0, now)
        return out
