"""Per-order charges for index options (brokerage, STT, exchange, SEBI, stamp duty, GST)."""
from __future__ import annotations


def order_charges(cfg: dict, segment: str, side: str, price: float, qty: int) -> float:
    turnover = price * qty
    brokerage = cfg["brokerage_per_order"] if turnover > 0 else 0.0
    stt = turnover * cfg["stt_sell_pct"] / 100 if side == "SELL" else 0.0
    exch = turnover * cfg["exchange_txn_pct"].get(segment, 0.035) / 100
    sebi = turnover * cfg["sebi_fee_per_crore"] / 1e7
    stamp = turnover * cfg["stamp_buy_pct"] / 100 if side == "BUY" else 0.0
    gst = (brokerage + exch + sebi) * cfg["gst_pct"] / 100
    return round(brokerage + stt + exch + sebi + stamp + gst, 2)
