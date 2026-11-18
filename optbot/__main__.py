"""Command line.

  python -m optbot check      log in to SmartAPI and print live prices (verifies your setup)
  python -m optbot run        run forever: wake before each session, paper trade, report, sleep
  python -m optbot report     print the latest report from the journal
  python -m optbot simulate   run on a synthetic market (no network, no keys) to test the pipeline
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from .clock import IST, Clock, MarketCalendar, SimClock
from .config import load_config
from .instruments import Instruments, download_scrip_master
from .journal import Journal
from .notify import Notifier, make_notifier


def _stdout_handler() -> logging.Handler:
    h = logging.StreamHandler(sys.stdout)
    if os.environ.get("OPTBOT_QUIET"):  # public CI logs: keep trade details out of them
        h.setLevel(logging.WARNING)
    return h


def _setup_logging(data_dir: Path, verbose: bool) -> None:
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[_stdout_handler(),
                  logging.FileHandler(data_dir / "logs" / "optbot.log")],
    )


def _load_instruments(cfg) -> Instruments:
    path = cfg.data_dir / "instruments.json"
    fresh = path.exists() and datetime.fromtimestamp(path.stat().st_mtime).date() == date.today()
    if not fresh:
        download_scrip_master(path)
    return Instruments.from_file(path, cfg["indices"], cfg["vix"]["names"],
                                 (cfg.get("stocks") or {}).get("names") or [])


def cmd_check(args) -> int:
    cfg = load_config(args.config)
    _setup_logging(cfg.data_dir, args.verbose)
    from .marketdata import AngelData

    n = make_notifier(cfg, cfg.secrets, Path(args.config).resolve().parent / ".env")
    try:
        inst = _load_instruments(cfg)
        data = AngelData(cfg.secrets, inst, Clock())
    except BaseException as e:  # noqa: BLE001
        n.send(f"optbot setup check FAILED: {e}. Most likely a wrong client code, PIN, API key or TOTP key.")
        raise
    print("Login OK.")
    print(f"VIX: {data.vix()}")
    for idx in cfg["indices"]:
        if idx not in inst.spot_tokens:
            print(f"{idx}: spot token not found (check spot_names in config)")
            continue
        exps = inst.expiries(idx)
        print(f"{idx}: spot {data.index_ltp(idx)}, lot {inst.lot_size(idx)}, next expiries {[e.isoformat() for e in exps[:3]]}")
    n.send("optbot is set up. Angel One login and live prices work: "
           + ", ".join(f"{i} {data.index_ltp(i)}" for i in cfg["indices"] if i in inst.spot_tokens)
           + ". Paper trading starts at 8:45 AM on the next trading day.")
    data.logout()
    return 0


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    _setup_logging(cfg.data_dir, args.verbose)
    from .engine import Engine
    from .marketdata import AngelData

    notifier = make_notifier(cfg, cfg.secrets, Path(args.config).resolve().parent / '.env')
    journal = Journal(cfg.data_dir / "journal.sqlite")
    clock = Clock()
    holder: dict = {}

    def prepare(engine: "Engine") -> None:
        inst = _load_instruments(cfg)
        data = AngelData(cfg.secrets, inst, clock, record_dir=cfg.data_dir / "market")
        engine.inst, engine.data = inst, data
        holder["data"] = data

    def finish(engine: "Engine") -> None:
        if holder.get("data"):
            holder["data"].logout()

    engine = Engine(cfg, None, None, clock, notifier, journal)
    notifier.start_commands(engine.command_handlers())
    notifier.send("optbot started (paper mode). Commands: /status /report /pause /resume /kill")
    engine.run_forever(prepare_day=prepare, finish_day=finish)
    return 0


def cmd_session(args) -> int:
    """Run part of today's session and exit (for schedulers like GitHub Actions)."""
    cfg = load_config(args.config)
    _setup_logging(cfg.data_dir, args.verbose)
    from .clock import parse_hhmm
    from .engine import Engine
    from .marketdata import AngelData

    clock = Clock()
    cal = MarketCalendar(cfg["market"])
    now = clock.now()
    if not cal.is_trading_day(now.date()):
        print(f"{now.date()} is not a trading day.")
        return 0
    pre = cal.at(now.date(), "pre_open")
    if now < pre:
        clock.sleep((pre - now).total_seconds())
    notifier = make_notifier(cfg, cfg.secrets, None)
    journal = Journal(cfg.data_dir / "journal.sqlite")
    inst = _load_instruments(cfg)
    try:
        data = AngelData(cfg.secrets, inst, clock,
                         record_dir=None if os.environ.get("OPTBOT_NO_RECORD") else cfg.data_dir / "market")
    except BaseException as e:  # noqa: BLE001
        notifier.send(f"Could not log in to Angel One today: {e}")
        raise
    engine = Engine(cfg, data, inst, clock, notifier, journal)
    notifier.start_commands(engine.command_handlers())
    try:
        engine.run_window(clock.now().date(), parse_hhmm(args.until))
    finally:
        data.logout()
    return 0


def cmd_report(args) -> int:
    cfg = load_config(args.config)
    journal = Journal(cfg.data_dir / "journal.sqlite")
    for p in cfg.profiles:
        print(p.name, journal.summary(p.name))
        for t in journal.day_trades(p.name, date.fromisoformat(args.day) if args.day else date.today()):
            print("  ", t)
    return 0


def cmd_simulate(args) -> int:
    from .engine import Engine
    from .sim import SimMarket, synthetic_rows

    cfg = load_config(args.config)
    tmp = Path(tempfile.mkdtemp(prefix="optbot-sim-"))
    cfg.data_dir = tmp
    (tmp / "state").mkdir()
    _setup_logging(tmp, args.verbose)
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.setLevel(logging.WARNING)
    cal = MarketCalendar(cfg["market"])
    d = date.fromisoformat(args.start) if args.start else date.today()
    while not cal.is_trading_day(d):
        d += timedelta(days=1)
    clock = SimClock(datetime.combine(d, datetime.min.time(), tzinfo=IST).replace(hour=8, minute=45))
    journal = Journal(tmp / "journal.sqlite")
    engine = Engine(cfg, None, None, clock, Notifier(), journal)
    for i in range(args.days):
        inst = Instruments(synthetic_rows(cfg["indices"], d), cfg["indices"], cfg["vix"]["names"])
        engine.inst = inst
        engine.data = SimMarket(clock, inst, seed=args.seed + i)
        clock._now = datetime.combine(d, datetime.min.time(), tzinfo=IST).replace(hour=8, minute=45)
        print(engine.run_session(d))
        print("-" * 60)
        d = cal.next_trading_day(d)
    print(f"Simulation data in {tmp}")
    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="optbot")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("run")
    se = sub.add_parser("session")
    se.add_argument("--until", default="15:40")
    r = sub.add_parser("report")
    r.add_argument("--day")
    s = sub.add_parser("simulate")
    s.add_argument("--days", type=int, default=3)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--start")
    s.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    return {"check": cmd_check, "run": cmd_run, "session": cmd_session, "report": cmd_report, "simulate": cmd_simulate}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
