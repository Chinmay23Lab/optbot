"""Plain-language Telegram messages for trades: exactly which strikes, how many, and the money involved."""
from __future__ import annotations

from .models import Position

STYLE_NAMES = {"conservative": "Safe", "target_5k": "₹5k target", "swing": "Swing (1-2 days)",
               "option_buyer": "Option buying", "tradingview": "Your TradingView indicator",
               "sniper": "Sniper-style (bot)", "combined": "Combined ₹20k (all styles)", "stocks": "Stock options",
               "scalper": "Scalper"}


def _style(profile: str) -> str:
    return STYLE_NAMES.get(profile, profile)


def _leg_name(c) -> str:
    strike = int(c.strike) if float(c.strike).is_integer() else c.strike
    return f"{c.index} {c.expiry:%d %b} {strike} {c.right}"


def _single_entry(pos: Position, buy, stop_pct: float, why: str) -> str:
    up = pos.direction == "long"
    lot = buy.contract.lot_size
    stop_at = pos.entry_debit * (1 - stop_pct)
    kind = "stock" if pos.meta.get("kind") == "stock" else "index"
    return "\n".join([
        f"{'📈' if up else '📉'} NEW PAPER TRADE ({_style(pos.profile)})",
        f"View: {pos.index} ({kind}) likely to go {'UP' if up else 'DOWN'}",
        "",
        "Place this 1 order:",
        f"BUY {_leg_name(buy.contract)} @ ₹{buy.entry_price:.2f}",
        f"Quantity: {pos.lots} lot{'s' if pos.lots > 1 else ''} = {pos.qty}" + (f" (1 lot = {lot})" if pos.lots > 1 else ""),
        "",
        f"Cost: ₹{pos.entry_debit:.2f} × {pos.qty} = ₹{pos.cost:,.0f} (no extra margin when only buying)",
        *([f"{pos.index} levels: entry {pos.meta['u_entry']} | SL {pos.meta['u_sl']} | TP1 {pos.meta['u_tp1']} | "
           f"TP2 {pos.meta['u_tp2']} | TP3 {pos.meta['u_tp3']}",
           ("Exits fully at TP1." if pos.meta.get("u_exit_mode") == "tp1" else
            "At TP1 the stop moves to entry, at TP2 to TP1; exits at TP3 or the moved stop."),
           f"Safety stop: also exits if the option itself falls to ₹{stop_at:.2f}"]
          if "u_sl" in pos.meta else
          [f"Stop: exits if the option falls to ₹{stop_at:.2f} (loss ≈ ₹{pos.cost * stop_pct:,.0f})",
           "Profit: no cap. A trailing stop follows the price up and locks in more as it rises."]),
        f"Most it can ever lose: ₹{pos.cost:,.0f} (what you paid)",
        "",
        f"Why: {why}",
        "This is a paper (practice) trade: the bot is still being tested.",
    ])


def entry_message(pos: Position, stop_pct: float, worst_fraction: float, hold_days: int | None, why: str) -> str:
    buy = next(l for l in pos.legs if l.side == "BUY")
    sell = next((l for l in pos.legs if l.side == "SELL"), None)
    if sell is None:
        return _single_entry(pos, buy, stop_pct, why)
    lot = buy.contract.lot_size
    up = pos.direction == "long"
    max_profit = (pos.width - pos.entry_debit) * pos.qty - pos.entry_charges
    stop_at = pos.entry_debit * (1 - stop_pct)
    target_level = int(sell.contract.strike)
    lines = [
        f"📈 NEW PAPER TRADE ({_style(pos.profile)})" if up else f"📉 NEW PAPER TRADE ({_style(pos.profile)})",
        f"View: {pos.index} likely to go {'UP' if up else 'DOWN'}",
        "",
        "Place these 2 orders, in this order:",
        f"1) BUY  {_leg_name(buy.contract)} @ ₹{buy.entry_price:.2f}",
        f"2) SELL {_leg_name(sell.contract)} @ ₹{sell.entry_price:.2f}",
        f"Quantity: {pos.lots} lot{'s' if pos.lots > 1 else ''} = {pos.qty} each" + (f" (1 lot = {lot})" if pos.lots > 1 else ""),
        "",
        f"Net cost: ₹{pos.entry_debit:.2f} × {pos.qty} = ₹{pos.cost:,.0f}",
        "(Buy first, then sell: the bought option protects the sold one, so far less margin is blocked."
        " Angel One's order screen shows the exact margin before you confirm.)",
        "",
        f"Max profit: ₹{max_profit:,.0f} if {pos.index} is {'above' if up else 'below'} {target_level} at expiry",
        f"Stop: exits if the pair is worth ₹{stop_at:.2f} or less (loss ≈ ₹{pos.cost * stop_pct:,.0f})",
        f"Most it can ever lose: ₹{pos.cost:,.0f} (the net cost, even on a sudden jump)",
    ]
    if hold_days:
        lines.append(f"May hold up to {hold_days} days if it keeps working.")
    lines += ["", f"Why: {why}", "This is a paper (practice) trade: the bot is still being tested."]
    return "\n".join(lines)


def exit_message(pos: Position, reason: str) -> str:
    buy = next(l for l in pos.legs if l.side == "BUY")
    sell = next((l for l in pos.legs if l.side == "SELL"), None)
    pnl = pos.realized_pnl()
    if sell is None:
        return "\n".join([
            f"{'✅' if pnl >= 0 else '❌'} CLOSED ({_style(pos.profile)}): {pos.index} ₹{pnl:+,.0f} after charges",
            f"Reason: {reason}",
            f"SELL {_leg_name(buy.contract)} @ ₹{(buy.exit_price or 0):.2f}",
            f"Quantity: {pos.qty}",
        ])
    return "\n".join([
        f"{'✅' if pnl >= 0 else '❌'} CLOSED ({_style(pos.profile)}): {pos.index} ₹{pnl:+,.0f} after charges",
        f"Reason: {reason}",
        "Close both orders:",
        f"1) SELL {_leg_name(buy.contract)} @ ₹{(buy.exit_price or 0):.2f}",
        f"2) BUY  {_leg_name(sell.contract)} @ ₹{(sell.exit_price or 0):.2f}",
        f"Quantity: {pos.qty} each",
    ])
