"""The trading loop: wakes before the open, trades the session on paper, reports, then sleeps."""
from __future__ import annotations

import logging
import re
import threading
from datetime import date, datetime, timedelta

from .clock import Clock, MarketCalendar
from .config import Config
from .instruments import Instruments
from .journal import Journal
from .models import Position, Quote
from .messages import STYLE_NAMES, entry_message, exit_message
from .notify import Notifier
from .paper import PaperAccount, PaperBroker, liquidation_value
from .playbook import make_playbook
from .risk import RiskManager
from .strategy import (build_candidates, candidate_contracts, choose_for_profile, choose_single, single_candidates, exit_reason, pick_expiry,
                       signal, trend_agrees, worst_loss_fraction)

log = logging.getLogger(__name__)


class Book:
    """One profile = one paper account + its risk manager."""

    def __init__(self, profile, account: PaperAccount):
        self.profile = profile
        self.account = account
        self.risk = RiskManager(profile)
        self.traded_indices: set[str] = set()


class Engine:
    def __init__(self, cfg: Config, data, inst: Instruments, clock: Clock, notifier: Notifier, journal: Journal):
        self.cfg = cfg
        self.data = data
        self.inst = inst
        self.clock = clock
        self.notify = notifier
        self.journal = journal
        self.market = MarketCalendar(cfg["market"])
        self.broker = PaperBroker(cfg["charges"], cfg.get("paper", {}), clock)
        state_dir = cfg.data_dir / "state"
        state_dir.mkdir(exist_ok=True)
        self.books = [Book(p, PaperAccount(p.name, p.capital, state_dir / f"{p.name}.json")) for p in cfg.profiles]
        self.indices = list(cfg["indices"].keys())
        self.stocks = [s.upper() for s in ((cfg.get("stocks") or {}).get("names") or [])]
        self.playbook: dict = {}
        self.day: date | None = None
        self.vix: float | None = None
        self.lock = threading.RLock()
        self._last_reason: dict[tuple, str] = {}
        self._last_chain_snap = None

    # ------------------------------------------------------------------ helpers
    def _quotes_for(self, positions: list[Position]) -> dict[str, Quote]:
        contracts = {l.contract.token: l.contract for p in positions for l in p.legs}
        return self.data.quotes(list(contracts.values())) if contracts else {}

    def _all_open(self) -> list[Position]:
        return [p for b in self.books for p in b.account.open]

    def _open_pnl(self, book: Book, quotes: dict[str, Quote]) -> float:
        total = 0.0
        for p in book.account.open:
            v = liquidation_value(p, quotes)
            if v is not None:
                if "carry_mark" in p.meta:   # held from an earlier day: today's P&L counts from last close
                    total += (v - p.meta["carry_mark"]) * p.qty
                else:
                    total += (v - p.entry_debit) * p.qty - p.entry_charges
        return total

    def _carrying(self) -> bool:
        """True when every open position has been cleared to stay open overnight."""
        return all(p.meta.get("carry") for p in self._all_open())

    def _refresh_trend(self) -> None:
        for b in self.books:
            for p in b.account.open:
                p.meta["trend_ok"] = trend_agrees(self.playbook.get("indices", {}).get(p.index), p.direction,
                                                  b.profile.min_trend_confidence)

    def _note(self, profile: str, idx: str, action: str, detail) -> None:
        key = (profile, idx)
        text = str(detail)
        if self._last_reason.get(key) == action + text:
            return
        self._last_reason[key] = action + text
        self.journal.decision(self.clock.now(), profile, idx, action, detail)

    def _close(self, book: Book, pos: Position, quotes: dict[str, Quote], reason: str) -> None:
        if self.broker.close_position(book.account, pos, quotes, reason):
            self.journal.trade(pos)
            pnl = pos.realized_pnl()
            self.notify.send(exit_message(pos, reason))

    # ------------------------------------------------------------------ day lifecycle
    def start_day(self, day: date) -> None:
        self.day = day
        self.playbook = make_playbook(day, self.data, self.indices, self.cfg, self.market)
        self.vix = self.playbook.get("vix")
        for b in self.books:
            b.risk.new_day(day)
            b.traded_indices = set()
            for p in b.account.open:   # positions carried from an earlier day
                p.meta["carry"] = False
                b.traded_indices.add(p.index)
        self._refresh_trend()
        for b in self.books:
            b.account.save()
            self.journal.start_day(day, b.profile.name, b.account.cash + sum(p.cost for p in b.account.open), self.playbook)
        (self.cfg.data_dir / "playbooks").mkdir(exist_ok=True)
        import json
        (self.cfg.data_dir / "playbooks" / f"{day.isoformat()}.json").write_text(json.dumps(self.playbook, indent=1, default=str))
        self.notify.send(f"Good morning. Playbook {day:%d %b}: {self.playbook.get('summary')}")
        held = [f"[{b.profile.name}] {p.index} {p.direction} x{p.lots}" for b in self.books for p in b.account.open]
        if held:
            self.notify.send("Still holding from yesterday: " + "; ".join(held))

    def end_day(self) -> str:
        with self.lock:
            quotes = self._quotes_for(self._all_open())
            for b in self.books:
                for p in list(b.account.open):
                    if p.meta.get("carry"):
                        continue
                    self._close(b, p, quotes, "end of day")
                b.account.save()
                self.journal.end_day(self.day, b.profile.name, b.account.cash + b.account.capital_in_use())
            report = self.report()
        self.notify.send(report)
        return report

    def report(self) -> str:
        d = self.day or self.clock.now().date()
        lines = [f"Paper report {d:%a %d %b %Y}"]
        for b in self.books:
            realized, n, _ = self.journal.realized(b.profile.name, d, d)
            s = self.journal.summary(b.profile.name, b.profile.capital)
            lines.append(f"\n{b.profile.name}: today ₹{realized:+,.0f} in {n} trade(s), "
                         f"account ₹{b.account.cash:,.0f} (started ₹{b.profile.capital:,.0f})")
            for t in self.journal.day_trades(b.profile.name, d):
                pnl = t["pnl"]
                lines.append(f"  {t['idx']} {t['direction']} x{t['lots']}: "
                             + (f"₹{pnl:+,.0f} ({t['exit_reason']})" if pnl is not None else "open"))
            for p in b.account.open:
                if p.meta.get("carry"):
                    lines.append(f"  holding overnight: {p.index} {p.direction} x{p.lots} (paid {p.entry_debit:.1f}, "
                                 f"last {p.meta.get('carry_mark')})")
            lines.append(f"  to date: {s['trades']} trades, net ₹{s['net_pnl']:+,.0f}, win rate {s['win_rate']}%, "
                         f"charges ₹{s['charges']:,.0f}, max drawdown ₹{s['max_drawdown']:,.0f}")
        why = self.why_summary(d)
        if why:
            lines.append("\nWhy it did not trade more today:")
            lines.extend("  " + w for w in why)
        return "\n".join(lines)

    def why_summary(self, d: date | None = None) -> list[str]:
        """Plain-English reasons the bot did not trade, from today's journal."""
        d = d or self.day or self.clock.now().date()
        rows = self.journal.day_decisions(d)
        if not rows:
            return []
        per_index: dict[str, str] = {}
        counts: dict[str, int] = {}
        blocked: dict[str, str] = {}
        general: list[str] = []
        for prof, idx, action, detail in rows:
            if action == "no-signal" and idx != "*":
                per_index[idx] = detail
                key = re.sub(r"[-\d.]+ ATR", "ATR", detail)
                counts[key] = counts.get(key, 0) + 1
            elif action == "blocked":
                blocked[prof] = detail
            elif action == "skip":
                where = idx if prof == "*" else f"{STYLE_NAMES.get(prof, prof)} on {idx}"
                line = f"{where}: {detail}"
                if line not in general:
                    general.append(line)
            elif action in ("no-trade", "stop-day"):
                line = f"{STYLE_NAMES.get(prof, 'All styles') if prof != '*' else 'All styles'}: {detail}"
                if line not in general:
                    general.append(line)
        out = []
        if per_index:
            out.append("Last check per index: " + "; ".join(f"{i} {r}" for i, r in sorted(per_index.items())))
            top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
            out.append("Most common reason: " + ", ".join(f"{k} ({n}x)" for k, n in top))
        for prof, why in blocked.items():
            out.append(f"{STYLE_NAMES.get(prof, prof)} stopped taking trades: {why}")
        out.extend(general[-6:])
        return out

    # ------------------------------------------------------------------ commands
    def cmd_status(self) -> str:
        with self.lock:
            quotes = self._quotes_for(self._all_open())
            out = []
            for b in self.books:
                d = self.day or self.clock.now().date()
                realized = self.journal.realized(b.profile.name, d, d)[0]
                op = self._open_pnl(b, quotes)
                flags = " [KILLED]" if b.account.killed else " [PAUSED]" if b.account.paused else ""
                out.append(f"{b.profile.name}{flags}: day ₹{realized + op:+,.0f}, {len(b.account.open)} open")
                for p in b.account.open:
                    v = liquidation_value(p, quotes)
                    out.append(f"  {p.index} {p.direction} x{p.lots}: paid {p.entry_debit:.1f}, now "
                               f"{v if v is None else round(v, 1)}, trail {p.meta.get('trail_stop', '-')}")
            return "\n".join(out)

    def cmd_pause(self) -> str:
        with self.lock:
            for b in self.books:
                b.account.paused = True
                b.account.save()
        return "Paused: no new entries. Open trades keep their exits."

    def cmd_resume(self) -> str:
        with self.lock:
            for b in self.books:
                b.account.paused = False
                b.account.killed = False
                b.account.save()
        return "Resumed."

    def cmd_kill(self) -> str:
        with self.lock:
            quotes = self._quotes_for(self._all_open())
            for b in self.books:
                for p in list(b.account.open):
                    self._close(b, p, quotes, "kill switch")
                b.account.killed = True
                b.account.save()
        return "KILL: all positions closed, new trades blocked until /resume."

    def cmd_report(self) -> str:
        with self.lock:
            return self.report()

    TV_UP = {"up", "buy", "long", "call", "ce", "bull", "bullish"}
    TV_DOWN = {"down", "sell", "short", "put", "pe", "bear", "bearish"}

    def cmd_tv(self, args: str = "") -> str:
        """/tv NIFTY up : paper-trade a signal from your TradingView indicator in the 'tradingview' account."""
        words = args.upper().replace(",", " ").split()
        direction = next(("long" for w in words if w.lower() in self.TV_UP), None) or \
            next(("short" for w in words if w.lower() in self.TV_DOWN), None)
        aliases = {"BANK": "BANKNIFTY", "NIFTYBANK": "BANKNIFTY", "FIN": "FINNIFTY", "NIFTY50": "NIFTY"}
        name = next((aliases.get(w, w) for w in words if aliases.get(w, w) in [*self.indices, *self.stocks]), None)
        if not name or not direction:
            return ("Send it like this: /tv NIFTY up  or  /tv BANKNIFTY down  or  /tv RELIANCE up\n"
                    f"Names I know: {', '.join(self.indices + self.stocks)}")
        books = [b for b in self.books if b.profile.signal_source == "tradingview"]
        if not books or self.inst is None or self.data is None:
            return "The TradingView practice account is not running right now (market hours only)."
        with self.lock:
            now = self.clock.now()
            d = now.date()
            if not (self.market.t("first_entry") <= now.time() < self.market.t("last_entry")):
                return f"Noted, but new trades are only taken between {self.market.t('first_entry'):%H:%M} and {self.market.t('last_entry'):%H:%M}."
            if not self.inst.options.get(name) or name not in self.inst.spot_tokens:
                return f"{name}: no option prices available right now."
            b = books[0]
            self.journal.decision(now, b.profile.name, name, "tv-signal", direction)
            quotes = self._quotes_for(b.account.open)
            for p in list(b.account.open):
                if p.index == name and p.direction != direction:
                    self._close(b, p, quotes, "your indicator flipped direction")
                elif p.index == name:
                    return f"Already holding {name} in that direction; keeping it."
            realized, _, losers = self.journal.realized(b.profile.name, d, d)
            ok, why = b.risk.can_enter(
                killed=b.account.killed, paused=b.account.paused, equity=b.account.equity(quotes),
                realized_today=realized, losers_today=losers,
                week_realized=self.journal.week_realized(b.profile.name, d),
                open_count=len(b.account.open), trades_today=self.journal.trades_opened(b.profile.name, d),
                open_pnl=self._open_pnl(b, quotes))
            if not ok:
                return f"Signal noted but not traded: {why}."
            from .strategy import Signal
            sig = Signal(name, direction, 0.0, "your TradingView indicator (sent with /tv)", None, None)
            before = len(b.account.open)
            b.traded_indices.discard(name)
            self._enter_single(b, sig, now, d, self.cfg["strategy"])
            if len(b.account.open) > before:
                return "Paper trade placed (details above)."
            return f"Signal noted but not traded: {self._last_reason.get((b.profile.name, name), 'see report')[4:]}"

    def command_handlers(self) -> dict:
        return {"/status": self.cmd_status, "/pause": self.cmd_pause, "/resume": self.cmd_resume,
                "/kill": self.cmd_kill, "/report": self.cmd_report, "/tv": self.cmd_tv}

    # ------------------------------------------------------------------ option-chain history
    def snapshot_chains(self) -> None:
        """Save prices and open interest around the money for each index (builds our own history for research)."""
        rc = self.cfg.get("record_option_chain") or {}
        if not rc.get("enabled") or self.data is None or self.inst is None:
            return
        now = self.clock.now()
        if not (self.market.t("open") <= now.time() <= self.market.t("close")):
            return
        if now.minute % 5 < 2:   # stay clear of the 5-minute candle fetches to respect API rate limits
            return
        every = float(rc.get("every_minutes", 5)) * 60
        if self._last_chain_snap and (now - self._last_chain_snap).total_seconds() < every:
            return
        self._last_chain_snap = now
        import csv
        k = int(rc.get("strikes_each_side", 10))
        rows, contracts = [], []
        for idx in self.indices:
            try:
                spot = self.data.index_ltp(idx)
                exps = [e for e in self.inst.expiries(idx) if e >= now.date()][:1]
                if not spot or not exps:
                    continue
                step = self.cfg["indices"][idx]["strike_step"]
                atm = round(spot / step) * step
                wanted = {atm + i * step for i in range(-k, k + 1)}
                cs = [c for c in self.inst.chain(idx, exps[0]) if c.strike in wanted]
                contracts += cs
                rows += [(idx, spot, c) for c in cs]
            except Exception as e:  # noqa: BLE001
                log.warning("chain snapshot %s: %s", idx, e)
        if not contracts:
            return
        q = self.data.quotes(contracts)
        d = self.cfg.data_dir / "chain"
        d.mkdir(exist_ok=True)
        path = d / f"{now.date().isoformat()}.csv"
        new = not path.exists()
        with path.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["ts", "index", "spot", "expiry", "strike", "right", "ltp", "bid", "ask", "oi"])
            for idx, spot, c in rows:
                x = q.get(c.token)
                if x:
                    w.writerow([now.isoformat(timespec="seconds"), idx, spot, c.expiry.isoformat(), c.strike, c.right,
                                x.ltp, x.bid, x.ask, x.oi])

    # ------------------------------------------------------------------ the tick
    def tick(self) -> None:
        try:
            self.snapshot_chains()
        except Exception as e:  # noqa: BLE001
            log.warning("chain snapshot failed: %s", e)
        with self.lock:
            now = self.clock.now()
            d = now.date()
            scfg = self.cfg["strategy"]
            candles = {}

            def get_candles(idx: str):
                if idx not in candles:
                    try:
                        candles[idx] = self.data.intraday_candles(idx, d)
                    except Exception as e:  # noqa: BLE001
                        log.warning("candles %s: %s", idx, e)
                        candles[idx] = []
                return candles[idx]

            # 1) manage open positions and day-level limits
            quotes = self._quotes_for(self._all_open())
            for b in self.books:
                realized, _, _ = self.journal.realized(b.profile.name, d, d)
                forced = b.risk.update_day(realized + self._open_pnl(b, quotes))
                if forced and forced.startswith("daily loss cap") and not b.profile.closes_open_on_loss_cap():
                    # No new trades today, but open bought options keep running to their own stop or target.
                    if not b.risk.state.cap_note_sent and b.account.open:
                        b.risk.state.cap_note_sent = True
                        self.notify.send(f"[{b.profile.name}] {forced}: no new trades today. The "
                                         f"{len(b.account.open)} open trade(s) stay on with their own stop-loss.")
                    self._note(b.profile.name, "*", "stop-day", forced)
                    forced = None
                if forced and forced.startswith("profit lock") and b.profile.style == "buy":
                    # "Lock your losses, not your profits" (Chinmay, 19 Nov): no new trades, but winners keep
                    # running on their own stop / trailing stop instead of being sold on a dip.
                    if not b.risk.state.cap_note_sent and b.account.open:
                        b.risk.state.cap_note_sent = True
                        self.notify.send(f"[{b.profile.name}] {forced}: no new trades today. Open winners keep "
                                         f"running on their own stop-loss.")
                    self._note(b.profile.name, "*", "stop-day", forced)
                    forced = None
                for p in list(b.account.open):
                    v = liquidation_value(p, quotes)
                    if v is None:
                        self._note(b.profile.name, p.index, "no-quote", "missing quote for open position")
                        continue
                    was_carry = p.meta.get("carry")
                    was_trailing = p.trail_active
                    reason = forced
                    if not reason and "u_sl" in p.meta:
                        reason = self._underlying_exit(b, p)
                    if not reason and "o_tp" in p.meta:
                        reason = self._premium_exit(p, v, now)
                    reason = reason or exit_reason(p, v, now, b.profile, self.market, get_candles(p.index), scfg)
                    if reason:
                        self._close(b, p, quotes, reason)
                    else:
                        if p.trail_active and not was_trailing:
                            up = (v - p.entry_debit) * p.qty
                            self.notify.send(f"🔒 {p.index} trade is up ₹{up:,.0f}. Stop moved into profit "
                                             f"(exits if the pair falls to ₹{p.meta.get('trail_stop')}), and it keeps "
                                             f"rising with the price.")
                        if p.meta.get("carry") and not was_carry:
                            up = (v - p.entry_debit) * p.qty
                            self.notify.send(f"[{b.profile.name}] HOLDING {p.index} {p.direction} x{p.lots} overnight: "
                                             f"up ₹{up:,.0f} so far, daily trend agrees. Max loss stays capped by the spread.")
                        b.account.save()
                if forced:
                    self._note(b.profile.name, "*", "stop-day", forced)

            # 2) look for entries
            t = now.time()
            if not (self.market.t("first_entry") <= t < self.market.t("last_entry")):
                return
            if self.playbook.get("no_trade"):
                self._note("*", "*", "no-trade", self.playbook.get("reason"))
                return
            vmax = self.cfg["vix"].get("max_for_entry", 25)
            if self.vix is not None and self.vix > vmax:
                self._note("*", "*", "skip", f"VIX {self.vix:.1f} > {vmax}")
                return

            # which books may enter at all?
            ready = []
            for b in self.books:
                realized, n_closed, losers = self.journal.realized(b.profile.name, d, d)
                ok, why = b.risk.can_enter(
                    killed=b.account.killed, paused=b.account.paused, equity=b.account.equity(quotes),
                    realized_today=realized, losers_today=losers,
                    week_realized=self.journal.week_realized(b.profile.name, d),
                    open_count=len(b.account.open), trades_today=self.journal.trades_opened(b.profile.name, d),
                    open_pnl=self._open_pnl(b, quotes))
                if ok:
                    ready.append(b)
                else:
                    self._note(b.profile.name, "*", "blocked", why)
            ready = [b for b in ready if b.profile.signal_source == "bot"]
            if not ready:
                return
            for b in [b for b in ready if b.profile.entry_signal == "sniper"]:
                self._sniper_entries(b, now, d, scfg)
            for b in [b for b in ready if b.profile.entry_signal == "scalper"]:
                self._scalper_entries(b, now, d, scfg)
            ready = [b for b in ready if b.profile.entry_signal not in ("sniper", "scalper")]
            if not ready:
                return

            names = (self.indices if any(b.profile.trade_indices for b in ready) else []) + \
                    (self.stocks if any(b.profile.trade_stocks for b in ready) else [])
            signals = []
            for idx in names:
                if not self.inst.options.get(idx) or idx not in self.inst.spot_tokens:
                    continue
                sig, why = signal(idx, get_candles(idx), d, scfg, self.playbook.get("indices", {}).get(idx))
                if sig:
                    signals.append(sig)
                else:
                    self._note("*", idx, "no-signal", why)
            signals.sort(key=lambda s: -s.strength)

            for sig in signals:
                is_stock = sig.index in self.stocks
                books = [b for b in ready if (b.profile.trade_stocks if is_stock else b.profile.trade_indices)
                         and sig.index not in b.traded_indices
                         and not any(p.index == sig.index for p in b.account.open)
                         and len(b.account.open) < b.profile.max_open_positions]
                if not books:
                    continue
                pb_idx = self.playbook.get("indices", {}).get(sig.index)
                eligible = []
                for b in books:
                    if b.profile.hold_overnight and not trend_agrees(pb_idx, sig.direction, b.profile.min_trend_confidence):
                        self._note(b.profile.name, sig.index, "skip", "daily trend not strong in this direction")
                    elif sig.strength < b.profile.min_signal_strength:
                        self._note(b.profile.name, sig.index, "skip", f"breakout {sig.strength:.2f} ATR too weak")
                    elif b.profile.style == "buy":
                        self._enter_single(b, sig, now, d, scfg)
                    else:
                        eligible.append(b)
                spot = self.data.index_ltp(sig.index) if eligible else None
                step = self.cfg["indices"].get(sig.index, {}).get("strike_step", 0)
                cache: dict = {}
                for b in eligible:
                    min_dte = b.profile.min_days_to_expiry or scfg["min_days_to_expiry"]
                    if min_dte not in cache:
                        expiry = pick_expiry(self.inst, sig.index, d, min_dte)
                        if not expiry or not spot:
                            self._note("*", sig.index, "skip", "no expiry or spot price")
                            cache[min_dte] = ([], {})
                        else:
                            buy, sells = candidate_contracts(self.inst, sig.index, sig.direction, spot, expiry, step,
                                                             scfg["max_spread_width_steps"])
                            if not buy or not sells:
                                self._note("*", sig.index, "skip", "strikes not found in instrument list")
                                cache[min_dte] = ([], {})
                            else:
                                q = self.data.quotes([buy, *sells])
                                cache[min_dte] = (build_candidates(buy, sells, q, scfg,
                                                                   int(self.cfg.get("paper", {}).get("slippage_ticks", 1))), q)
                                if not cache[min_dte][0]:
                                    self._note("*", sig.index, "skip", "no liquid spread with enough reward")
                    cands, q = cache[min_dte]
                    if not cands:
                        continue
                    c = choose_for_profile(cands, b.profile)
                    if not c:
                        self._note(b.profile.name, sig.index, "skip", "every spread costs more than the per-lot cap")
                        continue
                    lots = b.risk.size(c.cost_per_lot, c.cost_per_lot * worst_loss_fraction(b.profile), b.account.cash,
                                       b.account.capital_in_use())
                    if lots < 1:
                        self._note(b.profile.name, sig.index, "skip", f"size 0 (1 lot costs ₹{c.cost_per_lot:.0f})")
                        continue
                    meta = {"signal": sig.reason, "strength": round(sig.strength, 2), "or_high": sig.or_high,
                            "or_low": sig.or_low, "spot": spot, "vix": self.vix,
                            "playbook_bias": (pb_idx or {}).get("bias"), "trend_ok": True}
                    pos = self.broker.open_spread(b.account, sig.index, sig.direction, c.buy, c.sell, lots, q, meta)
                    if pos:
                        b.traded_indices.add(sig.index)
                        self.journal.trade(pos)
                        self.journal.decision(now, b.profile.name, sig.index, "enter", meta)
                        self.notify.send(entry_message(
                            pos, b.profile.stop_pct, worst_loss_fraction(b.profile),
                            b.profile.max_hold_days if b.profile.hold_overnight else None, sig.reason))

    HIST_DAYS = {5: 12, 10: 20, 15: 20, 30: 45, 60: 95}

    def _sniper_entries(self, b: Book, now: datetime, d: date, scfg: dict) -> None:
        """Sniper-style entries: EMA band cross on the chosen timeframe with the configured confirmations."""
        from .sniper_rules import live_signal
        from .strategy import Signal
        sc = b.profile.sniper or {}
        rule, tf = str(sc.get("rule", "C")), int(sc.get("tf", 15))
        sl_atr, tp_step = float(sc.get("sl_atr", 1.0)), float(sc.get("tp_step", 2.0))
        names = (self.indices if b.profile.trade_indices else []) + (self.stocks if b.profile.trade_stocks else [])
        cache = self._sniper_cache = getattr(self, "_sniper_cache", {})
        for name in names:
            if len(b.account.open) >= b.profile.max_open_positions:
                return
            if name in b.traded_indices or any(p.index == name for p in b.account.open):
                continue
            if not self.inst.options.get(name) or name not in self.inst.spot_tokens:
                continue
            # A tf-minute bar closes at 9:15 + k*tf. Only fetch candles in the 10 minutes after a close: that is
            # the only time a fresh signal can appear, and it keeps us well inside Angel One's rate limits.
            mins = (now.hour * 60 + now.minute) - (9 * 60 + 15)
            if mins < tf or mins % tf >= 10:
                continue
            slot = (name, rule, tf, now.replace(second=0, microsecond=0, minute=now.minute - now.minute % 5))
            if slot not in cache:
                try:
                    c5 = self.data.history_candles(name, self.HIST_DAYS.get(tf, 30))
                    res = live_signal(c5, now, rule, tf)
                except Exception as e:  # noqa: BLE001
                    log.warning("sniper %s: %s", name, e)
                    res = (0, f"data error: {e}", 0.0, 0.0)
                if res[1].startswith(("data error", "no new bar yet", "need ", "not enough")):
                    # missing data: don't remember it, try again on the next tick
                    self._note(b.profile.name, name, "no-signal", res[1])
                    continue
                cache[slot] = res
            direction, why, a, _ = cache[slot]
            if not direction:
                if why != "no new bar yet":
                    self._note(b.profile.name, name, "no-signal", why)
                continue
            spot = self.data.index_ltp(name)
            if not spot or a <= 0:
                continue
            risk = sl_atr * a
            levels = {"u_entry": round(spot, 2), "u_sl": round(spot - direction * risk, 2),
                      "u_tp1": round(spot + direction * tp_step * risk, 2),
                      "u_tp2": round(spot + direction * 2 * tp_step * risk, 2),
                      "u_tp3": round(spot + direction * 3 * tp_step * risk, 2),
                      "u_exit_mode": sc.get("exit", "run")}
            sig = Signal(name, "long" if direction == 1 else "short", 0.0, why, None, None)
            self._enter_single(b, sig, now, d, scfg, levels)

    def _scalper_entries(self, b: Book, now: datetime, d: date, scfg: dict) -> None:
        """Scalper: 5/15-minute trigger in the 1-hour trend's direction. Several trades a day, one per name at a time."""
        from .sniper_rules import scalper_signal
        from .strategy import Signal
        sc = b.profile.scalper or {}
        tf, trig = int(sc.get("tf", 15)), str(sc.get("trigger", "pb"))
        mins = (now.hour * 60 + now.minute) - (9 * 60 + 15)
        if mins < tf or mins % tf >= 5:   # only in the 5 minutes after an entry-chart bar closes
            return
        names = (self.indices if b.profile.trade_indices else []) + (self.stocks if b.profile.trade_stocks else [])
        cache = self._scalp_cache = getattr(self, "_scalp_cache", {})
        bar_end = now.replace(second=0, microsecond=0) - timedelta(minutes=mins % tf)
        for name in names:
            if len(b.account.open) >= b.profile.max_open_positions:
                return
            if any(p.index == name for p in b.account.open):
                continue
            if not self.inst.options.get(name) or name not in self.inst.spot_tokens:
                continue
            slot = (name, tf, trig, bar_end)
            if slot not in cache:
                try:
                    res = scalper_signal(self.data.history_candles(name, 12), now, tf, trig)
                except Exception as e:  # noqa: BLE001
                    log.warning("scalper %s: %s", name, e)
                    continue
                if res[1] == "no new bar yet" or res[1].startswith("need "):
                    self._note(b.profile.name, name, "no-signal", res[1])
                    continue
                cache[slot] = res
            direction, why = cache[slot]
            if not direction:
                self._note(b.profile.name, name, "no-signal", why)
                continue
            if cache.get(("done",) + slot):
                continue
            cache[("done",) + slot] = True   # one entry per name per bar
            sig = Signal(name, "long" if direction == 1 else "short", 0.0, why, None, None)
            self._enter_single(b, sig, now, d, scfg, {
                "scalp": True, "tp_pct": float(sc.get("tp_pct", 0.20)), "sl_pct": float(sc.get("sl_pct", 0.10)),
                "time_min": int(sc.get("time_min", 15)), "budget": float(sc.get("budget", 10000))})

    def _premium_exit(self, p: Position, v: float, now: datetime) -> str | None:
        """Scalper exits on the option's own price: target %, stop %, or time stop."""
        m = p.meta
        if v >= m["o_tp"]:
            return f"target +{m['tp_pct']:.0%} on the option ({p.entry_debit:.2f} → {v:.2f})"
        if v <= m["o_sl"]:
            return f"stop -{m['sl_pct']:.0%} on the option ({p.entry_debit:.2f} → {v:.2f})"
        if now >= datetime.fromisoformat(m["t_exit"]):
            return f"time stop: {m['time_min']} minutes up ({p.entry_debit:.2f} → {v:.2f})"
        return None

    def _underlying_exit(self, b: Book, p: Position) -> str | None:
        """Exit on the underlying's SL/TP levels for Sniper-style trades."""
        m = p.meta
        spot = self.data.index_ltp(p.index)
        if not spot:
            return None
        up = p.direction == "long"
        beyond = (lambda lvl: spot >= lvl) if up else (lambda lvl: spot <= lvl)
        if (spot <= m["u_sl"]) if up else (spot >= m["u_sl"]):
            return f"{'breakeven stop' if m.get('tp1_hit') else 'stop-loss'} level {m['u_sl']} hit ({p.index} at {spot:.1f})"
        if not m.get("tp1_hit") and beyond(m["u_tp1"]):
            if m.get("u_exit_mode") == "tp1":
                return f"TP1 {m['u_tp1']} hit"
            m["tp1_hit"] = True
            m["u_sl"] = m["u_entry"]
            self.notify.send(f"🎯 {p.index} reached TP1 {m['u_tp1']}. Stop moved to entry {m['u_entry']} "
                             f"(this trade can no longer lose on the index move). Now aiming for TP2 {m['u_tp2']} / TP3 {m['u_tp3']}.")
            b.account.save()
        if m.get("tp1_hit") and not m.get("tp2_hit") and beyond(m["u_tp2"]):
            m["tp2_hit"] = True
            m["u_sl"] = m["u_tp1"]
            self.notify.send(f"🎯 {p.index} reached TP2 {m['u_tp2']}. Stop raised to TP1 {m['u_tp1']}.")
            b.account.save()
        if beyond(m["u_tp3"]):
            return f"TP3 {m['u_tp3']} hit"
        return None

    def _enter_single(self, b: Book, sig, now: datetime, d: date, scfg: dict, extra: dict | None = None) -> None:
        """Option-buying style: buy one call (up view) or put (down view), index or stock."""
        is_stock = sig.index in self.stocks
        min_dte = b.profile.min_days_to_expiry or scfg["min_days_to_expiry"]
        expiry = pick_expiry(self.inst, sig.index, d, min_dte)
        spot = self.data.index_ltp(sig.index)
        if not expiry or not spot:
            self._note(b.profile.name, sig.index, "skip", "no expiry or spot price")
            return
        contracts = single_candidates(self.inst, sig.index, sig.direction, spot, expiry)
        if not contracts:
            self._note(b.profile.name, sig.index, "skip", "strikes not found in instrument list")
            return
        q = self.data.quotes(contracts)
        max_gap = (self.cfg.get("stocks") or {}).get("max_leg_spread_pct", 8.0) if is_stock else scfg["max_leg_spread_pct"]
        slip = int(self.cfg.get("paper", {}).get("slippage_ticks", 1))
        c, why = choose_single(contracts, q, b.profile, max_gap, slip)
        if not c:
            self._note(b.profile.name, sig.index, "skip", why)
            return
        lots = b.risk.size(c.cost_per_lot, c.cost_per_lot * worst_loss_fraction(b.profile), b.account.cash,
                           b.account.capital_in_use())
        if extra and extra.get("budget") and lots >= 1:   # scalper: about one fixed amount per trade
            lots = max(1, min(lots, int(extra["budget"] // c.cost_per_lot)))
        if lots < 1:
            self._note(b.profile.name, sig.index, "skip", f"size 0 (1 lot costs ₹{c.cost_per_lot:.0f})")
            return
        meta = {"signal": sig.reason, "strength": round(sig.strength, 2), "or_high": sig.or_high,
                "or_low": sig.or_low, "spot": spot, "vix": self.vix, "kind": "stock" if is_stock else "index",
                "trend_ok": True, **(extra or {})}
        pos = self.broker.open_single(b.account, sig.index, sig.direction, c.buy, lots, q, meta)
        if pos and meta.get("scalp"):
            pos.meta["o_tp"] = round(pos.entry_debit * (1 + meta["tp_pct"]), 2)
            pos.meta["o_sl"] = round(pos.entry_debit * (1 - meta["sl_pct"]), 2)
            pos.meta["t_exit"] = (now + timedelta(minutes=meta["time_min"])).isoformat()
            b.account.save()
        if pos:
            b.traded_indices.add(sig.index)
            self.journal.trade(pos)
            self.journal.decision(now, b.profile.name, sig.index, "enter", meta)
            self.notify.send(entry_message(pos, b.profile.stop_pct, worst_loss_fraction(b.profile), None, sig.reason))

    # ------------------------------------------------------------------ split sessions (GitHub Actions)
    def _day_state_path(self):
        return self.cfg.data_dir / "state" / "day.json"

    def save_day_state(self, ended: bool = False) -> None:
        import json
        from dataclasses import asdict
        st = {"day": self.day.isoformat(), "ended": ended,
              "books": {b.profile.name: {"risk": asdict(b.risk.state), "traded": sorted(b.traded_indices)}
                        for b in self.books}}
        self._day_state_path().write_text(json.dumps(st, default=str, indent=1))

    def resume_or_start_day(self, day: date) -> bool:
        """Continue today's session from saved state if it exists. Returns False if today already ended."""
        import json
        from .risk import DayState
        p = self._day_state_path()
        pb = self.cfg.data_dir / "playbooks" / f"{day.isoformat()}.json"
        if p.exists() and pb.exists():
            st = json.loads(p.read_text())
            if st.get("day") == day.isoformat():
                if st.get("ended"):
                    return False
                self.day = day
                self.playbook = json.loads(pb.read_text())
                self.vix = self.playbook.get("vix")
                for b in self.books:
                    bs = st["books"].get(b.profile.name)
                    b.risk.new_day(day)
                    if bs:
                        r = bs["risk"]
                        b.risk.state = DayState(day, float(r["peak_pnl"]), bool(r["locked"]), bool(r["stopped"]),
                                                r.get("stop_reason", ""))
                        b.traded_indices = set(bs.get("traded", []))
                    else:   # a style added since the morning: start its day now
                        self.journal.start_day(day, b.profile.name, b.account.cash, self.playbook)
                log.info("resumed session for %s", day)
                return True
        self.start_day(day)
        self.save_day_state()
        return True

    def run_window(self, day: date, until) -> str | None:
        """Trade from now until `until` (a time) or the close. Returns the report if the day ended."""
        if not self.resume_or_start_day(day):
            log.info("session for %s already ended", day)
            return None
        loop = float(self.cfg.get("loop_seconds", 15))
        open_t = self.market.at(day, "open")
        close_t = self.market.at(day, "close")
        sq = self.market.at(day, "square_off")
        stop_at = min(close_t, datetime.combine(day, until, tzinfo=close_t.tzinfo))
        if self.clock.now() < open_t:
            self.clock.sleep((open_t - self.clock.now()).total_seconds())
        while self.clock.now() < stop_at:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                log.exception("tick failed")
                self.notify.send(f"Error in tick: {e}. Continuing; positions keep their stops.")
            if self.clock.now() > sq and self._carrying():
                break
            self.clock.sleep(loop)
        if self.clock.now() >= sq:
            report = self.end_day()
            self.save_day_state(ended=True)
            return report
        self.save_day_state()
        if until.hour < 13:
            why = self.why_summary(day)
            if why:
                self.notify.send("Midday check, why no new trade so far:\n" + "\n".join("• " + w for w in why))
        return None

    # ------------------------------------------------------------------ main loop
    def run_session(self, day: date) -> str:
        """Run one full trading day from pre-open to close. Returns the day's report."""
        self.start_day(day)
        loop = float(self.cfg.get("loop_seconds", 15))
        open_t = self.market.at(day, "open")
        if self.clock.now() < open_t:
            self.clock.sleep((open_t - self.clock.now()).total_seconds())
        close_t = self.market.at(day, "close")
        sq = self.market.at(day, "square_off")
        while self.clock.now() < close_t:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                log.exception("tick failed")
                self.notify.send(f"Error in tick: {e}. Continuing; positions keep their stops.")
            if self.clock.now() > sq and self._carrying():
                break
            self.clock.sleep(loop)
        return self.end_day()

    def run_forever(self, prepare_day=None, finish_day=None) -> None:
        """Sleep until each trading day's pre-open, prepare (login, instruments), trade, report, repeat."""
        while True:
            now = self.clock.now()
            d = now.date()
            if self.market.is_trading_day(d) and now < self.market.at(d, "close") - timedelta(minutes=5):
                pre = self.market.at(d, "pre_open")
                if now < pre:
                    log.info("sleeping until %s", pre)
                    self.clock.sleep((pre - now).total_seconds())
                try:
                    if prepare_day:
                        prepare_day(self)
                    self.run_session(d)
                except Exception as e:  # noqa: BLE001
                    log.exception("session failed")
                    self.notify.send(f"Session error: {e}. The bot will try again next trading day.")
                finally:
                    if finish_day:
                        finish_day(self)
            nxt = self.market.next_trading_day(self.clock.now().date())
            wake = self.market.at(nxt, "pre_open")
            log.info("market closed; sleeping until %s", wake)
            self.clock.sleep(max(60.0, (wake - self.clock.now()).total_seconds()))
