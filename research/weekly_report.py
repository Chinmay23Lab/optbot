"""Weekly paper P&L per account, sent on Telegram after Friday's close (Chinmay, 20 Nov).

For each account: the working capital it was given, what it is worth at the end of the week, the week's
closed trades (winners and losers) and the trades still open. Reads only the bot's saved journal and account
files: no broker login, no orders.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
IST = ZoneInfo("Asia/Kolkata")


def _name(prof: str) -> str:
    from optbot.messages import STYLE_NAMES
    return STYLE_NAMES.get(prof, prof)


def _symbol(t: dict) -> str:
    return t["buy_symbol"] if not t.get("sell_symbol") else f"{t['buy_symbol']} / {t['sell_symbol']}"


def build(db: sqlite3.Connection, state_dir: Path, profiles: list[tuple[str, float]], monday: date,
          friday: date) -> str:
    lines = [f"Weekly paper report, {monday:%d %b} to {friday:%d %b %Y}"]
    ranking: list[tuple[float, str]] = []
    tot_cap = tot_now = tot_week = 0.0
    for prof, capital in profiles:
        st_path = state_dir / f"{prof}.json"
        st = json.loads(st_path.read_text()) if st_path.exists() else {"cash": capital, "open": []}
        cash = float(st["cash"])
        open_lines, open_value, open_pnl = [], 0.0, 0.0
        for p in st.get("open", []):
            leg = next(l for l in p["legs"] if l["side"] == "BUY")
            qty = int(p["qty"])
            paid = float(p["entry_debit"])
            mark = (p.get("meta") or {}).get("carry_mark")
            mark = float(mark) if mark is not None else paid
            value = mark * qty
            pnl = (mark - paid) * qty
            open_value += value
            open_pnl += pnl
            since = str(p["entry_time"])[:10]
            open_lines.append(f"    {leg['contract']['symbol']} x{p['lots']} lot(s): bought {paid:.2f} on {since}, "
                              f"last {mark:.2f}, ₹{pnl:+,.0f} so far")
        now = cash + open_value
        rows = db.execute(
            "SELECT day, idx, direction, lots, buy_symbol, sell_symbol, entry_debit, exit_value, pnl, exit_reason "
            "FROM trades WHERE profile=? AND exit_time IS NOT NULL AND substr(exit_time,1,10)>=? "
            "AND substr(exit_time,1,10)<=? ORDER BY exit_time", (prof, monday.isoformat(), friday.isoformat()))
        cols = [c[0] for c in rows.description]
        closed = [dict(zip(cols, r)) for r in rows.fetchall()]
        week = sum(t["pnl"] or 0 for t in closed)
        wins = [t for t in closed if (t["pnl"] or 0) > 0]
        losses = [t for t in closed if (t["pnl"] or 0) <= 0]
        ranking.append((now - capital, f"{_name(prof)} ₹{capital:,.0f} → ₹{now:,.0f}"))
        tot_cap += capital
        tot_now += now
        tot_week += week
        lines.append(f"\n{_name(prof)}: started with ₹{capital:,.0f}, now ₹{now:,.0f} (₹{now - capital:+,.0f}). "
                     f"This week: ₹{week:+,.0f} from {len(closed)} closed trade(s), "
                     f"{len(wins)} profit, {len(losses)} loss.")
        for label, group in (("  Profits:", wins), ("  Losses:", losses)):
            if group:
                lines.append(label)
                for t in group:
                    d = date.fromisoformat(t["day"])
                    lines.append(f"    {d:%a %d %b} {_symbol(t)} x{t['lots']}: {t['entry_debit']:.2f} → "
                                 f"{(t['exit_value'] or 0):.2f}, ₹{t['pnl']:+,.0f} ({t['exit_reason']})")
        if open_lines:
            lines.append(f"  Still open ({len(open_lines)}), ₹{open_pnl:+,.0f} at Friday's close:")
            lines.extend(open_lines)
        else:
            lines.append("  No trades open.")
    ranking.sort(reverse=True)
    lines.insert(1, "Best to worst on ₹20,000 each: " + "; ".join(r for _, r in ranking))
    lines.append("\nEach style is a separate test with its own pretend ₹20,000 (your real capital is one ₹20,000). "
                 "Paper money only.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="any day of the week to report (default: today)")
    ap.add_argument("--send", action="store_true", help="send the report on Telegram")
    a = ap.parse_args()
    from optbot.config import load_config
    from optbot.notify import make_notifier
    cfg = load_config(ROOT / "config.yaml")
    d = date.fromisoformat(a.day) if a.day else datetime.now(IST).date()
    monday = d - timedelta(days=d.weekday())
    friday = monday + timedelta(days=4)
    db_path = cfg.data_dir / "journal.sqlite"
    if not db_path.exists():
        print("no journal found")
        return 1
    db = sqlite3.connect(str(db_path))
    text = build(db, cfg.data_dir / "state", [(p.name, p.capital) for p in cfg.profiles], monday, friday)
    print(text)
    if a.send:
        make_notifier(cfg, cfg.secrets).send(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
