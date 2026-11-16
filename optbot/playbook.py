"""Morning playbook: market regime, bias and which directions are allowed per index.

The playbook only narrows what the engine may do (direction, no-trade days). It can never raise
size or loosen risk limits. Provider "rules" is built in; provider "command" runs any external
program (for example a Vibe-Trading script) that reads context JSON on stdin and prints playbook JSON.
"""
from __future__ import annotations

import json
import logging
import shlex
import subprocess
from datetime import date

from .indicators import ema, pct_change
from .models import Candle

log = logging.getLogger(__name__)

DIRECTIONS = ("long", "short")


def classify(daily: list[Candle]) -> dict:
    if len(daily) < 10:
        return {"regime": "unknown", "bias": "neutral", "allowed": list(DIRECTIONS), "confidence": 0.0,
                "note": "not enough history"}
    closes = [c.close for c in daily]
    e20 = ema(closes, 20)
    slope = pct_change(e20[-6], e20[-1])
    ret5 = pct_change(closes[-6], closes[-1])
    last = closes[-1]
    above = last > e20[-1]
    if above and slope > 0.3 and ret5 > 0.5:
        regime, bias, allowed = "trend_up", "bullish", ["long"]
    elif not above and slope < -0.3 and ret5 < -0.5:
        regime, bias, allowed = "trend_down", "bearish", ["short"]
    else:
        regime, bias, allowed = "range", "neutral", list(DIRECTIONS)
    conf = min(1.0, abs(ret5) / 3 + abs(slope) / 2)
    return {"regime": regime, "bias": bias, "allowed": allowed, "confidence": round(conf, 2),
            "note": f"close {last:.0f} vs EMA20 {e20[-1]:.0f}, 5-day {ret5:+.1f}%, EMA slope {slope:+.2f}%"}


def build_context(day: date, data, indices: list[str], vix: float | None) -> dict:
    ctx = {"date": day.isoformat(), "vix": vix, "indices": {}}
    for idx in indices:
        try:
            dc = data.daily_candles(idx, 30)
        except Exception as e:  # noqa: BLE001
            log.warning("daily candles failed for %s: %s", idx, e)
            dc = []
        ctx["indices"][idx] = [
            {"d": c.ts.date().isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close} for c in dc
        ]
    return ctx


def rules_playbook(ctx: dict, vix_cfg: dict, no_trade_day: bool) -> dict:
    vix = ctx.get("vix")
    pb = {"date": ctx["date"], "vix": vix, "provider": "rules", "no_trade": False, "reason": "", "indices": {}}
    if no_trade_day:
        pb.update(no_trade=True, reason="configured no-trade day")
    elif vix is not None and vix > vix_cfg.get("no_trade_above", 30):
        pb.update(no_trade=True, reason=f"VIX {vix:.1f} too high")
    for idx, rows in ctx["indices"].items():
        candles = [Candle(None, r["o"], r["h"], r["l"], r["c"]) for r in rows]  # type: ignore[arg-type]
        pb["indices"][idx] = classify(candles)
    return pb


def command_playbook(ctx: dict, cmd: str, timeout: int, fallback: dict) -> dict:
    try:
        out = subprocess.run(shlex.split(cmd), input=json.dumps(ctx), capture_output=True, text=True, timeout=timeout)
        ext = json.loads(out.stdout)
    except Exception as e:  # noqa: BLE001
        log.warning("playbook command failed (%s); using rules playbook", e)
        fallback["reason"] = (fallback.get("reason") or "") + " [external playbook failed]"
        return fallback
    merged = json.loads(json.dumps(fallback))
    merged["provider"] = "command"
    if ext.get("no_trade"):
        merged["no_trade"] = True
        merged["reason"] = ext.get("reason", "external playbook says no trade")
    for idx, v in (ext.get("indices") or {}).items():
        if idx not in merged["indices"]:
            continue
        allowed = [d for d in v.get("allowed", DIRECTIONS) if d in DIRECTIONS]
        # The external view can only narrow directions, never widen beyond rules + itself.
        merged["indices"][idx].update(
            bias=v.get("bias", merged["indices"][idx]["bias"]),
            allowed=allowed,
            note=str(v.get("note", ""))[:300],
        )
    if ext.get("summary"):
        merged["summary"] = str(ext["summary"])[:500]
    return merged


def make_playbook(day: date, data, indices: list[str], cfg, calendar) -> dict:
    vix = None
    try:
        vix = data.vix()
    except Exception as e:  # noqa: BLE001
        log.warning("vix fetch failed: %s", e)
    ctx = build_context(day, data, indices, vix)
    pb = rules_playbook(ctx, cfg["vix"], calendar.is_no_trade_day(day))
    pcfg = cfg.get("playbook", {}) or {}
    if pcfg.get("provider") == "command" and pcfg.get("command"):
        pb = command_playbook(ctx, pcfg["command"], int(pcfg.get("command_timeout_sec", 180)), pb)
    pb.setdefault("summary", summarize(pb))
    return pb


def summarize(pb: dict) -> str:
    if pb.get("no_trade"):
        return f"No trading today: {pb.get('reason')}."
    parts = []
    for idx, v in pb["indices"].items():
        parts.append(f"{idx} {v['bias']} ({v['regime']})")
    vix = pb.get("vix")
    return ("VIX {:.1f}. ".format(vix) if vix else "") + ", ".join(parts) + "."
