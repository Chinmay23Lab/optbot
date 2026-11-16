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


def make_notifier(cfg, secrets: dict) -> Notifier:
    if (cfg.get("notify") or {}).get("telegram") and secrets.get("TELEGRAM_BOT_TOKEN") and secrets.get("TELEGRAM_CHAT_ID"):
        return TelegramNotifier(secrets["TELEGRAM_BOT_TOKEN"], secrets["TELEGRAM_CHAT_ID"])
    return Notifier()
