"""Alerts and remote control over Telegram (falls back to the log when not configured).

Commands (only accepted from your own chat id):
  /status  positions and today's P&L per profile
  /report  today's report now
  /pause   stop new entries (open trades keep their exits)
  /resume  allow new entries again (also clears the kill switch)
  /kill    close every position now and block all new trades until /resume
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

import requests

log = logging.getLogger(__name__)


class Notifier:
    def send(self, text: str) -> None:
        log.info("NOTIFY: %s", text)

    def start_commands(self, handlers: dict[str, Callable[[], str]]) -> None:
        pass


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id)
        self._offset = 0

    def send(self, text: str) -> None:
        log.info("NOTIFY: %s", text)
        for chunk in [text[i : i + 3900] for i in range(0, len(text), 3900)] or [""]:
            try:
                requests.post(f"{self.base}/sendMessage", json={"chat_id": self.chat_id, "text": chunk}, timeout=15)
            except Exception as e:  # noqa: BLE001
                log.warning("telegram send failed: %s", e)

    def start_commands(self, handlers: dict[str, Callable[[], str]]) -> None:
        def loop() -> None:
            while True:
                try:
                    r = requests.get(f"{self.base}/getUpdates", params={"offset": self._offset, "timeout": 30}, timeout=40)
                    for upd in r.json().get("result", []):
                        self._offset = upd["update_id"] + 1
                        msg = upd.get("message") or {}
                        if str((msg.get("chat") or {}).get("id")) != self.chat_id:
                            continue  # ignore anyone else
                        cmd = (msg.get("text") or "").strip().split()[0].lower() if msg.get("text") else ""
                        cmd = cmd.split("@")[0]
                        fn = handlers.get(cmd)
                        self.send(fn() if fn else "Commands: " + " ".join(sorted(handlers)))
                except Exception as e:  # noqa: BLE001
                    log.warning("telegram poll failed: %s", e)
                    time.sleep(5)

        threading.Thread(target=loop, daemon=True, name="telegram").start()


def discover_chat_id(token: str) -> str | None:
    """Find the chat of whoever pressed Start on the bot, so the user doesn't have to look up an id."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
    except Exception as e:  # noqa: BLE001
        log.warning("telegram getUpdates failed: %s", e)
        return None
    if not r.get("ok"):
        log.warning("Telegram rejected the bot token (%s). Check the TELEGRAM_BOT_TOKEN value.", r.get("description"))
        return None
    log.warning("Telegram: %d recent message(s) to the bot", len(r.get("result", [])))
    try:
        me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20).json().get("result", {})
        log.warning("Telegram bot is @%s", me.get("username"))
    except Exception:  # noqa: BLE001
        pass
    for upd in r.get("result", []):
        chat = (upd.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private" and chat.get("id"):
            return str(chat["id"])
    return None


def _save_env_value(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    lines = [l for l in lines if not l.startswith(f"{key}=")] + [f"{key}={value}"]
    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)


def make_notifier(cfg, secrets: dict, env_path: Path | None = None) -> Notifier:
    if not (cfg.get("notify") or {}).get("telegram") or not secrets.get("TELEGRAM_BOT_TOKEN"):
        return Notifier()
    chat_id = secrets.get("TELEGRAM_CHAT_ID")
    saved = Path(cfg.data_dir) / "telegram_chat_id"
    if not chat_id and saved.exists():
        chat_id = saved.read_text().strip()
    if not chat_id:
        chat_id = discover_chat_id(secrets["TELEGRAM_BOT_TOKEN"])
        if chat_id:
            secrets["TELEGRAM_CHAT_ID"] = chat_id
            saved.write_text(chat_id)
            if env_path and env_path.exists():
                _save_env_value(env_path, "TELEGRAM_CHAT_ID", chat_id)
        else:
            log.warning("Telegram: no chat found. Open your bot in Telegram and press Start.")
            return Notifier()
    return TelegramNotifier(secrets["TELEGRAM_BOT_TOKEN"], chat_id)
