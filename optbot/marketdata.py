"""Market data sources.

AngelData is READ-ONLY on purpose: it wraps SmartAPI login, candles and quotes, and exposes no
order methods. Paper orders are filled by optbot.paper against these quotes.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from .clock import IST, Clock
from .instruments import Instruments
from .models import Candle, Contract, Quote

log = logging.getLogger(__name__)


class DataSource(Protocol):
    def index_ltp(self, index: str) -> float | None: ...
    def vix(self) -> float | None: ...
    def intraday_candles(self, index: str, day: date) -> list[Candle]: ...  # recent sessions incl. today
    def daily_candles(self, index: str, n: int) -> list[Candle]: ...
    def quotes(self, contracts: list[Contract]) -> dict[str, Quote]: ...


class RateLimiter:
    def __init__(self, per_sec: float):
        self.min_gap = 1.0 / per_sec
        self.last = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            gap = time.monotonic() - self.last
            if gap < self.min_gap:
                time.sleep(self.min_gap - gap)
            self.last = time.monotonic()


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(IST)


class AngelData:
    """SmartAPI market data (login, candles, quotes). No order placement exists in this class."""

    def __init__(self, secrets: dict, instruments: Instruments, clock: Clock, record_dir: Path | None = None):
        from SmartApi import SmartConnect  # imported lazily so tests run without the SDK
        import pyotp

        missing = [k for k in ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET") if not secrets.get(k)]
        if missing:
            raise SystemExit(f"Missing in .env: {', '.join(missing)}")
        self._secrets = secrets
        self._pyotp = pyotp
        self.api = SmartConnect(api_key=secrets["ANGEL_API_KEY"])
        self.inst = instruments
        self.clock = clock
        self.quote_rl = RateLimiter(1.0)
        self.candle_rl = RateLimiter(0.4)   # Angel blocked us at 1/s once stocks were added (18 Nov)
        self._candle_cache: dict[tuple, tuple[float, list[Candle]]] = {}
        self.record_dir = record_dir
        if record_dir:
            record_dir.mkdir(parents=True, exist_ok=True)
        self.login()

    # --- session -------------------------------------------------------------
    def login(self) -> None:
        totp = self._pyotp.TOTP(self._secrets["ANGEL_TOTP_SECRET"]).now()
        resp = self.api.generateSession(self._secrets["ANGEL_CLIENT_CODE"], self._secrets["ANGEL_PIN"], totp)
        if not resp or not resp.get("status"):
            raise RuntimeError(f"SmartAPI login failed: {resp and resp.get('message')}")
        log.info("SmartAPI login ok")

    def logout(self) -> None:
        try:
            self.api.terminateSession(self._secrets["ANGEL_CLIENT_CODE"])
        except Exception as e:  # noqa: BLE001
            log.warning("logout failed: %s", e)

    def _call(self, fn, *args):
        for attempt in range(3):
            try:
                resp = fn(*args)
                if resp and resp.get("status"):
                    return resp.get("data")
                msg = (resp or {}).get("message", "")
                if "token" in str(msg).lower() or "session" in str(msg).lower():
                    self.login()
                    continue
                log.warning("SmartAPI %s: %s", getattr(fn, "__name__", fn), msg)
            except Exception as e:  # noqa: BLE001
                rate = "access rate" in str(e)
                if not rate or attempt:
                    log.warning("SmartAPI error (%s), attempt %d", e, attempt + 1)
                time.sleep((3 + 3 * attempt) if rate else (1 + attempt))  # back off harder on rate limits
        return None

    # --- quotes --------------------------------------------------------------
    def _market(self, mode: str, by_exch: dict[str, list[str]]) -> list[dict]:
        out: list[dict] = []
        for exch, toks in by_exch.items():
            for i in range(0, len(toks), 50):
                self.quote_rl.wait()
                data = self._call(self.api.getMarketData, mode, {exch: toks[i : i + 50]})
                if data:
                    out.extend(data.get("fetched", []))
        return out

    def index_ltp(self, index: str) -> float | None:
        exch, tok = self.inst.spot_tokens[index]
        rows = self._market("LTP", {exch: [tok]})
        return float(rows[0]["ltp"]) if rows else None

    def vix(self) -> float | None:
        if not self.inst.vix_token:
            return None
        exch, tok = self.inst.vix_token
        rows = self._market("LTP", {exch: [tok]})
        return float(rows[0]["ltp"]) if rows else None

    def quotes(self, contracts: list[Contract]) -> dict[str, Quote]:
        by_exch: dict[str, list[str]] = {}
        for c in contracts:
            by_exch.setdefault(c.segment, []).append(c.token)
        now = self.clock.now()
        out: dict[str, Quote] = {}
        for r in self._market("FULL", by_exch):
            depth = r.get("depth") or {}
            buys = depth.get("buy") or [{}]
            sells = depth.get("sell") or [{}]
            q = Quote(
                token=str(r.get("symbolToken")),
                ltp=float(r.get("ltp") or 0),
                bid=float(buys[0].get("price") or 0),
                ask=float(sells[0].get("price") or 0),
                oi=float(r.get("opnInterest") or 0),
                ts=now,
            )
            out[q.token] = q
        self._record(now, out)
        return out

    def _record(self, now: datetime, quotes: dict[str, Quote]) -> None:
        if not self.record_dir or not quotes:
            return
        path = self.record_dir / f"{now.date().isoformat()}.jsonl"
        with path.open("a") as f:
            for q in quotes.values():
                f.write(json.dumps({"t": now.isoformat(), "k": q.token, "l": q.ltp, "b": q.bid, "a": q.ask, "oi": q.oi}) + "\n")

    # --- candles -------------------------------------------------------------
    def _candles(self, exch: str, tok: str, interval: str, start: datetime, end: datetime) -> list[Candle]:
        self.candle_rl.wait()
        data = self._call(
            self.api.getCandleData,
            {
                "exchange": exch,
                "symboltoken": tok,
                "interval": interval,
                "fromdate": start.strftime("%Y-%m-%d %H:%M"),
                "todate": end.strftime("%Y-%m-%d %H:%M"),
            },
        )
        return [Candle(_parse_ts(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in (data or [])]

    def intraday_candles(self, index: str, day: date) -> list[Candle]:
        now = self.clock.now()
        key = ("5m", index, day, now.replace(second=0, microsecond=0).minute // 5)
        cached = self._candle_cache.get(key)
        if cached:
            return cached[1]
        exch, tok = self.inst.spot_tokens[index]
        # A few sessions back, so EMAs are warmed up at the open; the strategy picks out today's.
        start = datetime.combine(day - timedelta(days=5), datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15)
        candles = self._candles(exch, tok, "FIVE_MINUTE", start, now)
        # keep completed candles only
        candles = [c for c in candles if c.ts + timedelta(minutes=5) <= now]
        self._candle_cache = {k: v for k, v in self._candle_cache.items() if k[1] != index or k[0] != "5m"}
        self._candle_cache[key] = (time.time(), candles)
        return candles

    def history_candles(self, name: str, days: int) -> list[Candle]:
        """Completed 5-minute candles going back `days` calendar days. Older days are fetched once per
        session; afterwards only today's candles are refreshed (once per 5-minute slot)."""
        now = self.clock.now()
        today = now.date()
        if not hasattr(self, "_hist"):
            self._hist = {}
        key = (name, today)
        if key not in self._hist or self._hist[key][0] < days:
            exch, tok = self.inst.spot_tokens[name]
            start = datetime.combine(today - timedelta(days=days), datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15)
            end = datetime.combine(today, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=14)
            old, s = [], start
            while s < end:
                e = min(end, s + timedelta(days=60))
                old += self._candles(exch, tok, "FIVE_MINUTE", s, e)
                s = e
            self._hist[key] = (days, sorted({c.ts: c for c in old if c.ts.date() < today}.values(), key=lambda c: c.ts))
        today_c = [c for c in self.intraday_candles(name, today) if c.ts.date() == today]
        return self._hist[key][1] + today_c

    def daily_candles(self, index: str, n: int) -> list[Candle]:
        exch, tok = self.inst.spot_tokens[index]
        end = self.clock.now()
        return self._candles(exch, tok, "ONE_DAY", end - timedelta(days=int(n * 1.6) + 7), end)[-n:]
