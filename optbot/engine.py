"""The trading loop: wakes before the open, trades the session on paper, reports, then sleeps."""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta

from .clock import Clock, MarketCalendar
from .config import Config
from .instruments import Instruments
from .journal import Journal
from .models import Position, Quote
from .notify import Notifier
from .paper import PaperAccount, PaperBroker, liquidation_value
from .playbook import make_playbook
from .risk import RiskManager
from .strategy import (build_candidates, candidate_contracts, choose_for_profile, exit_reason, pick_expiry,
                       signal)

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
        self.playbook: dict = {}
        self.day: date | None = None
        self.vix: float | None = None
        self.lock = threading.RLock()
        self._last_reason: dict[tuple, str] = {}

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
                total += (v - p.entry_debit) * p.qty - p.entry_charges
        return total

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
            self.notify.send(f"[{book.profile.name}] EXIT {pos.index} {pos.direction} x{pos.lots} lot: "
                             f"₹{pnl:+,.0f} ({reason})")

    # ------------------------------------------------------------------ day lifecycle
    def start_day(self, day: date) -> None:
        self.day = day
        self.playbook = make_playbook(day, self.data, self.indices, self.cfg, self.market)
        self.vix = self.playbook.get("vix")
        for b in self.books:
            b.risk.new_day(day)
            b.traded_indices = set()
            self.journal.start_day(day, b.profile.name, b.account.cash + sum(p.cost for p in b.account.open), self.playbook)
        (self.cfg.data_dir / "playbooks").mkdir(exist_ok=True)
        import json
        (self.cfg.data_dir / "playbooks" / f"{day.isoformat()}.json").write_text(json.dumps(self.playbook, indent=1, default=str))
        self.notify.send(f"Good morning. Playbook {day:%d %b}: {self.playbook.get('summary')}")

    def end_day(self) -> str:
        with self.lock:
            quotes = self._quotes_for(self._all_open())
            for b in self.books:
                for p in list(b.account.open):
                    self._close(b, p, quotes, "end of day")
                self.journal.end_day(self.day, b.profile.name, b.account.cash)
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
            lines.append(f"  to date: {s['trades']} trades, net ₹{s['net_pnl']:+,.0f}, win rate {s['win_rate']}%, "
                         f"charges ₹{s['charges']:,.0f}, max drawdown ₹{s['max_drawdown']:,.0f}")
        return "\n".join(lines)

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

    def command_handlers(self) -> dict:
        return {"/status": self.cmd_status, "/pause": self.cmd_pause, "/resume": self.cmd_resume,
                "/kill": self.cmd_kill, "/report": self.cmd_report}

    # ------------------------------------------------------------------ the tick
    def tick(self) -> None:
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
                for p in list(b.account.open):
                    v = liquidation_value(p, quotes)
                    if v is None:
                        self._note(b.profile.name, p.index, "no-quote", "missing quote for open position")
                        continue
                    reason = forced or exit_reason(p, v, now, b.profile, self.market, get_candles(p.index), scfg)
                    if reason:
                        self._close(b, p, quotes, reason)
                    else:
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
            if not ready:
                return

            signals = []
            for idx in self.indices:
                if not self.inst.options.get(idx) or idx not in self.inst.spot_tokens:
                    continue
                sig, why = signal(idx, get_candles(idx), d, scfg, self.playbook.get("indices", {}).get(idx))
                if sig:
                    signals.append(sig)
                else:
                    self._note("*", idx, "no-signal", why)
            signals.sort(key=lambda s: -s.strength)

            for sig in signals:
                books = [b for b in ready if sig.index not in b.traded_indices
                         and not any(p.index == sig.index for p in b.account.open)
                         and len(b.account.open) < b.profile.max_open_positions]
                if not books:
                    continue
                expiry = pick_expiry(self.inst, sig.index, d, scfg["min_days_to_expiry"])
                spot = self.data.index_ltp(sig.index)
                if not expiry or not spot:
                    self._note("*", sig.index, "skip", "no expiry or spot price")
                    continue
                step = self.cfg["indices"][sig.index]["strike_step"]
                buy, sells = candidate_contracts(self.inst, sig.index, sig.direction, spot, expiry, step,
                                                 scfg["max_spread_width_steps"])
                if not buy or not sells:
                    self._note("*", sig.index, "skip", "strikes not found in instrument list")
                    continue
                q = self.data.quotes([buy, *sells])
                cands = build_candidates(buy, sells, q, scfg, int(self.cfg.get("paper", {}).get("slippage_ticks", 1)))
                if not cands:
                    self._note("*", sig.index, "skip", "no liquid spread with enough reward")
                    continue
                for b in books:
                    c = choose_for_profile(cands, b.profile)
                    if not c:
                        self._note(b.profile.name, sig.index, "skip", "every spread costs more than the per-lot cap")
                        continue
                    lots = b.risk.size(c.cost_per_lot, c.cost_per_lot * b.profile.stop_pct, b.account.cash,
                                       b.account.capital_in_use())
                    if lots < 1:
                        self._note(b.profile.name, sig.index, "skip", f"size 0 (1 lot costs ₹{c.cost_per_lot:.0f})")
                        continue
                    meta = {"signal": sig.reason, "strength": round(sig.strength, 2), "or_high": sig.or_high,
                            "or_low": sig.or_low, "spot": spot, "vix": self.vix,
                            "playbook_bias": self.playbook.get("indices", {}).get(sig.index, {}).get("bias")}
                    pos = self.broker.open_spread(b.account, sig.index, sig.direction, c.buy, c.sell, lots, q, meta)
                    if pos:
                        b.traded_indices.add(sig.index)
                        self.journal.trade(pos)
                        self.journal.decision(now, b.profile.name, sig.index, "enter", meta)
                        kind = "bull call" if sig.direction == "long" else "bear put"
                        self.notify.send(
                            f"[{b.profile.name}] ENTER {sig.index} {kind} spread x{lots} lot: "
                            f"buy {c.buy.symbol} / sell {c.sell.symbol}, paid {pos.entry_debit:.1f} "
                            f"(₹{pos.cost:,.0f}, max loss at stop ≈ ₹{pos.cost * b.profile.stop_pct:,.0f}). {sig.reason}")

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
            if self.clock.now() > sq and not self._all_open():
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
