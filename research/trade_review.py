"""After-close review of a day's paper trades: how high did each bought option go after the bot entered,
and what would holding to that high (or to the close) have made? Read-only."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=date.today().isoformat())
    ap.add_argument("--journal", default="data/journal.sqlite")
    a = ap.parse_args()
    from optbot.clock import IST, Clock
    from optbot.config import load_config
    from optbot.instruments import Instruments, download_scrip_master
    from optbot.marketdata import AngelData
    db = sqlite3.connect(a.journal)
    trades = db.execute("SELECT profile, idx, direction, qty, buy_symbol, sell_symbol, entry_time, exit_time, "
                        "entry_debit, exit_value, pnl, exit_reason FROM trades WHERE day=? ORDER BY entry_time",
                        (a.day,)).fetchall()
    if not trades:
        print(f"no trades on {a.day}")
        return 0
    cfg = load_config(ROOT / "config.yaml")
    sm = Path("review_instruments.json")
    download_scrip_master(sm)
    rows = json.loads(sm.read_text())
    tok = {(r.get("exch_seg"), r.get("symbol")): str(r["token"]) for r in rows}
    data = AngelData(cfg.secrets, Instruments(rows, cfg["indices"], cfg["vix"]["names"], []), Clock())
    try:
        for prof, idx, dirn, qty, buy, sell, et, xt, ed, xv, pnl, why in trades:
            et_dt = datetime.fromisoformat(et)
            seg = next((s for s in ("NFO", "BFO") if (s, buy) in tok), None)
            line = f"{prof} | {idx} {dirn} {buy}{' / sell ' + sell if sell else ''} x{qty} | in {et_dt:%H:%M} at {ed:.2f}"
            line += f" | out {datetime.fromisoformat(xt):%H:%M} at {xv:.2f} ({why}) P&L ₹{pnl:+,.0f}" if xt else " | still open"
            if sell or not seg:
                print(line + " | (spread or contract not found: option high not checked)")
                continue
            end = et_dt.replace(hour=15, minute=30)
            cs = [c for c in data._candles(seg, tok[(seg, buy)], "FIVE_MINUTE", et_dt, end) if c.ts >= et_dt]
            if not cs:
                print(line + " | no candles")
                continue
            hi = max(cs, key=lambda c: c.high)
            close = cs[-1].close
            print(line + f" | option high after entry {hi.high:.2f} at {hi.ts:%H:%M} (₹{(hi.high - ed) * qty:+,.0f} "
                         f"before charges if sold there), day close {close:.2f} (₹{(close - ed) * qty:+,.0f})")
    finally:
        data.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
