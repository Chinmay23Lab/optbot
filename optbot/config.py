"""Configuration loading. Settings come from config.yaml; secrets come from the environment (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Profile:
    name: str
    capital: float
    max_lots: int
    max_debit_per_lot: float
    max_risk_per_trade: float
    stop_pct: float
    exit_mode: str  # "target" or "trail"
    target_pct_of_max_profit: float | None
    trail_trigger_pct: float
    trail_giveback_pct: float
    daily_profit_target: float
    daily_profit_lock_pct: float
    daily_loss_cap: float
    max_losing_trades_per_day: int
    weekly_loss_cap: float
    account_floor: float
    max_open_positions: int
    max_trades_per_day: int
    continue_after_target: bool = False
    max_capital_in_use_pct: float = 1.0

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> "Profile":
        if d.get("exit_mode") not in ("target", "trail"):
            raise ValueError(f"profile {name}: exit_mode must be 'target' or 'trail'")
        return cls(name=name, **d)


@dataclass
class Config:
    raw: dict[str, Any]
    profiles: list[Profile]
    data_dir: Path
    secrets: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)


SECRET_KEYS = [
    "ANGEL_API_KEY",
    "ANGEL_CLIENT_CODE",
    "ANGEL_PIN",
    "ANGEL_TOTP_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "ANTHROPIC_API_KEY",
]


def load_env_file(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines). Existing environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path: str | Path = "config.yaml", env_path: str | Path | None = None) -> Config:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if raw.get("mode", "paper") != "paper":
        raise SystemExit("This build only supports mode: paper. Live trading is not implemented.")
    load_env_file(Path(env_path) if env_path else path.parent / ".env")
    profiles = [Profile.from_dict(n, d) for n, d in raw["profiles"].items()]
    data_dir = Path(raw.get("data_dir", "./data"))
    if not data_dir.is_absolute():
        data_dir = (path.parent / data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    # Tolerate copy-paste extras: surrounding spaces or quotes.
    secrets = {k: os.environ[k].strip().strip('"').strip("'").strip() for k in SECRET_KEYS if os.environ.get(k, "").strip()}
    return Config(raw=raw, profiles=profiles, data_dir=data_dir, secrets=secrets)
