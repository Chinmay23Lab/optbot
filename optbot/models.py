from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class Contract:
    token: str
    symbol: str
    index: str          # NIFTY, BANKNIFTY, ...
    segment: str        # NFO or BFO
    expiry: date
    strike: float
    right: str          # CE or PE
    lot_size: int
    tick: float


@dataclass
class Quote:
    token: str
    ltp: float
    bid: float
    ask: float
    oi: float = 0.0
    ts: datetime | None = None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.ltp

    def spread_pct(self) -> float:
        m = self.mid
        if m <= 0 or self.bid <= 0 or self.ask <= 0:
            return 999.0
        return (self.ask - self.bid) / m * 100


@dataclass
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class Leg:
    contract: Contract
    side: str           # BUY or SELL (at entry)
    qty: int            # units (lots * lot_size)
    entry_price: float = 0.0
    exit_price: float | None = None


@dataclass
class Position:
    id: str
    profile: str
    index: str
    direction: str      # long (bull call spread) or short (bear put spread)
    legs: list[Leg]
    lots: int
    entry_time: datetime
    entry_debit: float  # per unit, paid
    width: float        # strike distance
    entry_charges: float = 0.0
    peak_value: float = 0.0
    trail_active: bool = False
    exit_time: datetime | None = None
    exit_value: float | None = None
    exit_charges: float = 0.0
    exit_reason: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def qty(self) -> int:
        return self.legs[0].qty

    @property
    def cost(self) -> float:
        return self.entry_debit * self.qty

    @property
    def max_profit_per_unit(self) -> float:
        return self.width - self.entry_debit

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    def realized_pnl(self) -> float:
        if self.exit_value is None:
            return 0.0
        return (self.exit_value - self.entry_debit) * self.qty - self.entry_charges - self.exit_charges
