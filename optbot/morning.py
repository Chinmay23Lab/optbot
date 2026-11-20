"""Morning global check for the Telegram note: US close, Asia this morning, crude, rupee, and Moneycontrol headlines.

Information only for now (20 Nov 2026): it does not change any trade until research/edge_study.py shows it helps.
Every fetch is best-effort; if a source is down the note just leaves it out.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

log = logging.getLogger(__name__)

MARKETS = [("S&P 500", "^GSPC"), ("Nasdaq", "^IXIC"), ("Nikkei", "^N225"), ("Kospi", "^KS11"),
           ("Hang Seng", "^HSI"), ("Crude", "CL=F"), ("USD/INR", "INR=X")]
FEEDS = ["https://www.moneycontrol.com/rss/marketreports.xml", "https://www.moneycontrol.com/rss/latestnews.xml"]
UA = {"User-Agent": "Mozilla/5.0 (optbot morning note)"}


def _change(sym: str) -> float | None:
    import requests
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"range": "5d", "interval": "1d"},
                     headers=UA, timeout=10)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    price = res["meta"].get("regularMarketPrice")
    prev = res["meta"].get("chartPreviousClose")
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    if len(closes) >= 2:
        prev = closes[-2]
    if price is None or not prev:
        return None
    return (float(price) / float(prev) - 1) * 100


def markets_line() -> str:
    parts = []
    for name, sym in MARKETS:
        try:
            ch = _change(sym)
        except Exception as e:  # noqa: BLE001
            log.info("morning: %s failed: %s", sym, e)
            continue
        if ch is not None:
            parts.append(f"{name} {ch:+.1f}%")
    return ", ".join(parts)


def headlines(n: int = 5) -> list[str]:
    import requests
    out: list[str] = []
    for url in FEEDS:
        try:
            r = requests.get(url, headers=UA, timeout=10)
            r.raise_for_status()
            if b"<!ENTITY" in r.content or b"<!DOCTYPE" in r.content:
                raise ValueError("feed with a DTD refused")
            root = ET.fromstring(r.content)
        except Exception as e:  # noqa: BLE001
            log.info("morning: feed %s failed: %s", url, e)
            continue
        for item in root.iter("item"):
            t = re.sub(r"\s+", " ", (item.findtext("title") or "")).strip()
            if t and t not in out:
                out.append(t)
            if len(out) >= n:
                return out
    return out


def morning_note() -> str:
    lines = []
    m = markets_line()
    if m:
        lines.append("Global: " + m)
    h = headlines()
    if h:
        lines.append("Moneycontrol:")
        lines += [f"• {x}" for x in h]
    return "\n".join(lines)
