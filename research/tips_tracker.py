"""Track the tip-channel calls in research/tips.yaml honestly, as paper trades. No orders.

For each call: find the option in Angel One's instrument list, read its 5-minute candles since the call was given,
then check entry ("above" price traded), stop-loss (closing basis = a day's close at/below SL; otherwise any
5-minute low at/below SL), and targets. The whole position exits at SL or at the last target; otherwise it is
marked at the latest price. P&L is for the advised lots, after charges. A Telegram summary lists winners AND losers.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from optbot.charges import order_charges  # noqa: E402
from optbot.clock import IST  # noqa: E402


def find_contract(rows, t):
    want = []
    for r in rows:
        if r.get("exch_seg") != "NFO" or r.get("instrumenttype") != "OPTSTK" or (r.get("name") or "").upper() != t["name"]:
            continue
        sym = r.get("symbol", "")
        if not sym.endswith(t["right"]) or abs(float(r["strike"]) / 100 - float(t["strike"])) > 1e-6:
            continue
        exp = datetime.strptime(r["expiry"].upper(), "%d%b%Y").date()
        if exp.strftime("%b").upper() == t["expiry_month"].upper():
            want.append((exp, r))
    return min(want, key=lambda x: x[0])[1] if want else None


def evaluate(t, candles):
    """candles: (ts, o, h, l, c) after the call was given, oldest first. Returns a result dict (per unit prices)."""
    above, sl, targets = float(t["above"]), t.get("sl"), [float(x) for x in t.get("targets") or []]
    res = {"status": "waiting for entry", "entry": None, "exit": None, "hits": [], "last": candles[-1][4] if candles else None}
    i0 = next((i for i, c in enumerate(candles) if c[2] >= above), None)
    if i0 is None:
        return res
    entry = max(above, candles[i0][1]) if candles[i0][1] > above else above
    res.update(status="open", entry=entry, entry_time=candles[i0][0].strftime("%d %b %H:%M"))
    for k in range(i0, len(candles)):
        ts, o, h, l, c = candles[k]
        if sl is not None and not t.get("sl_close") and l <= sl and k > i0:
            res.update(status="stop-loss hit", exit=min(o, float(sl)))
            return res
        for j, tg in enumerate(targets):
            if j not in res["hits"] and h >= tg:
                res["hits"].append(j)
        if targets and len(res["hits"]) == len(targets):
            res.update(status="all targets hit", exit=targets[-1])
            return res
        last_of_day = k == len(candles) - 1 or candles[k + 1][0].date() != ts.date()
        if sl is not None and t.get("sl_close") and last_of_day and c <= sl:
            res.update(status="stop-loss hit (closing basis)", exit=c)
            return res
    return res


def summary(results, charges_cfg):
    lines, total, done, wins = ["📋 Tip calls tracked (paper, no orders)"], 0.0, 0, 0
    for t, r, lot in results:
        label = f"{t['name']} {t['strike']} {t['right']}"
        if r is None:
            lines.append(f"• {label}: option not found")
            continue
        if r["entry"] is None:
            lines.append(f"• {label}: not triggered yet (needs {t['above']}, last {r['last']})")
            continue
        qty = lot * int(t.get("lots") or 1)
        px = r["exit"] if r["exit"] is not None else r["last"]
        cost = order_charges(charges_cfg, "NFO", "BUY", r["entry"], qty) + order_charges(charges_cfg, "NFO", "SELL", px, qty)
        pnl = (px - r["entry"]) * qty - cost
        total += pnl
        tg = ", ".join(f"T{j + 1}" for j in sorted(r["hits"])) or "no target yet"
        state = r["status"] if r["exit"] is not None else f"open, last {px}"
        lines.append(f"• {label}: bought {r['entry']} ({r['entry_time']}), {state}, {tg}: {'✅' if pnl > 0 else '❌'} ₹{pnl:+,.0f}")
        if r["exit"] is not None:
            done += 1
            wins += pnl > 0
    lines.append(f"Total ₹{total:+,.0f} for the advised lots after charges. Closed calls: {done}, winners {wins}"
                 + (f" ({100 * wins / done:.0f}%)" if done else "") + ".")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tips", default=str(ROOT / "research" / "tips.yaml"))
    ap.add_argument("--send", action="store_true", help="send the summary on Telegram")
    a = ap.parse_args()
    from optbot.clock import Clock
    from optbot.config import load_config
    from optbot.instruments import Instruments, download_scrip_master
    from optbot.marketdata import AngelData
    from optbot.notify import make_notifier
    cfg = load_config(ROOT / "config.yaml")
    tips = yaml.safe_load(Path(a.tips).read_text()) or []
    sm = Path("tips_instruments.json")
    download_scrip_master(sm)
    rows = json.loads(sm.read_text())
    inst = Instruments(rows, cfg["indices"], cfg["vix"]["names"], [])
    data = AngelData(cfg.secrets, inst, Clock())
    results = []
    try:
        now = datetime.now(IST)
        for t in tips:
            t["name"] = t["name"].upper()
            r = find_contract(rows, t)
            if not r:
                results.append((t, None, 0))
                continue
            given = datetime.strptime(t["given"], "%Y-%m-%d %H:%M").replace(tzinfo=IST)
            cs = data._candles("NFO", str(r["token"]), "FIVE_MINUTE", given, now)
            cs = [(c.ts, c.open, c.high, c.low, c.close) for c in cs if c.ts >= given - timedelta(minutes=4)]
            results.append((t, evaluate(t, cs), int(r.get("lotsize") or 0)))
    finally:
        data.logout()
    text = summary(results, cfg["charges"])
    print(text)
    if a.send:
        make_notifier(cfg, cfg.secrets).send(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
