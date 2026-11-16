"""Time handling in IST, plus a simulated clock for tests and replays."""
from __future__ import annotations

import time as _time
from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


class Clock:
    def now(self) -> datetime:
        return datetime.now(IST)

    def sleep(self, seconds: float) -> None:
        _time.sleep(max(0.0, seconds))


class SimClock(Clock):
    def __init__(self, start: datetime):
        self._now = start

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


class MarketCalendar:
    def __init__(self, market_cfg: dict):
        self.cfg = market_cfg
        self.holidays = {date.fromisoformat(d) for d in market_cfg.get("holidays", [])}
        self.no_trade = {date.fromisoformat(d) for d in market_cfg.get("no_trade_days", [])}

    def t(self, key: str) -> time:
        return parse_hhmm(self.cfg[key])

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def is_no_trade_day(self, d: date) -> bool:
        return d in self.no_trade

    def at(self, d: date, key: str) -> datetime:
        return datetime.combine(d, self.t(key), tzinfo=IST)

    def next_trading_day(self, d: date) -> date:
        d = d + timedelta(days=1)
        while not self.is_trading_day(d):
            d += timedelta(days=1)
        return d
