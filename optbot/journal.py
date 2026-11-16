"""SQLite journal: every decision (including skips), every trade, and daily results per profile."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import Position

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (ts TEXT, day TEXT, profile TEXT, idx TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS trades (
  id TEXT PRIMARY KEY, profile TEXT, day TEXT, idx TEXT, direction TEXT, lots INTEGER, qty INTEGER,
  buy_symbol TEXT, sell_symbol TEXT, entry_time TEXT, exit_time TEXT, entry_debit REAL, exit_value REAL,
  width REAL, charges REAL, pnl REAL, exit_reason TEXT, meta TEXT);
CREATE TABLE IF NOT EXISTS days (day TEXT, profile TEXT, start_equity REAL, end_equity REAL, realized REAL,
  trades INTEGER, playbook TEXT, PRIMARY KEY(day, profile));
"""


class Journal:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(SCHEMA)

    def decision(self, ts: datetime, profile: str, idx: str, action: str, detail: dict | str) -> None:
        self.db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?)",
                        (ts.isoformat(), ts.date().isoformat(), profile, idx, action,
                         detail if isinstance(detail, str) else json.dumps(detail, default=str)))
        self.db.commit()

    def trade(self, p: Position) -> None:
        buy = next(l for l in p.legs if l.side == "BUY")
        sell = next(l for l in p.legs if l.side == "SELL")
        self.db.execute(
            "INSERT OR REPLACE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.profile, p.entry_time.date().isoformat(), p.index, p.direction, p.lots, p.qty,
             buy.contract.symbol, sell.contract.symbol, p.entry_time.isoformat(),
             p.exit_time.isoformat() if p.exit_time else None, p.entry_debit, p.exit_value, p.width,
             p.entry_charges + p.exit_charges, p.realized_pnl() if p.exit_time else None, p.exit_reason,
             json.dumps(p.meta, default=str)))
        self.db.commit()

    def realized(self, profile: str, start: date, end: date) -> tuple[float, int, int]:
        """(net realized P&L, closed trades, losing trades) between two dates inclusive."""
        row = self.db.execute(
            "SELECT COALESCE(SUM(pnl),0), COUNT(*), COALESCE(SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END),0) "
            "FROM trades WHERE profile=? AND day>=? AND day<=? AND exit_time IS NOT NULL",
            (profile, start.isoformat(), end.isoformat())).fetchone()
        return float(row[0]), int(row[1]), int(row[2])

    def trades_opened(self, profile: str, day: date) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM trades WHERE profile=? AND day=?",
                                   (profile, day.isoformat())).fetchone()[0])

    def week_realized(self, profile: str, day: date) -> float:
        monday = day - timedelta(days=day.weekday())
        return self.realized(profile, monday, day)[0]

    def start_day(self, day: date, profile: str, equity: float, playbook: dict) -> None:
        self.db.execute("INSERT OR IGNORE INTO days (day, profile, start_equity, playbook) VALUES (?,?,?,?)",
                        (day.isoformat(), profile, equity, json.dumps(playbook, default=str)))
        self.db.commit()

    def end_day(self, day: date, profile: str, equity: float) -> None:
        realized, n, _ = self.realized(profile, day, day)
        self.db.execute("UPDATE days SET end_equity=?, realized=?, trades=? WHERE day=? AND profile=?",
                        (equity, realized, n, day.isoformat(), profile))
        self.db.commit()

    def day_trades(self, profile: str, day: date) -> list[dict]:
        cur = self.db.execute("SELECT idx, direction, lots, buy_symbol, sell_symbol, entry_debit, exit_value, pnl, "
                              "exit_reason FROM trades WHERE profile=? AND day=? ORDER BY entry_time",
                              (profile, day.isoformat()))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def summary(self, profile: str, capital: float = 0.0) -> dict:
        r = self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl),0), COALESCE(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0), "
            "COALESCE(SUM(charges),0), COUNT(DISTINCT day) FROM trades WHERE profile=? AND exit_time IS NOT NULL",
            (profile,)).fetchone()
        n, pnl, wins, charges, days = int(r[0]), float(r[1]), int(r[2]), float(r[3]), int(r[4])
        eq = [row[0] for row in self.db.execute(
            "SELECT end_equity FROM days WHERE profile=? AND end_equity IS NOT NULL ORDER BY day", (profile,))]
        peak, mdd = capital, 0.0
        for e in eq:
            peak = max(peak, e)
            mdd = max(mdd, peak - e)
        return {"trades": n, "net_pnl": round(pnl, 2), "win_rate": round(wins / n * 100, 1) if n else 0.0,
                "charges": round(charges, 2), "trading_days": days, "max_drawdown": round(mdd, 2),
                "sessions": len(eq)}
