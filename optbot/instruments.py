"""Angel One instrument master: lot sizes, strikes, expiries and tokens, loaded fresh each morning."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

import requests

from .models import Contract

log = logging.getLogger(__name__)

FALLBACK_SPOT = {
    "NIFTY": ("NSE", "99926000"),
    "BANKNIFTY": ("NSE", "99926009"),
    "FINNIFTY": ("NSE", "99926037"),
    "SENSEX": ("BSE", "99919000"),
    "BANKEX": ("BSE", "99919012"),
}

SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"


def download_scrip_master(dest: Path, timeout: int = 120) -> Path:
    r = requests.get(SCRIP_MASTER_URL, timeout=timeout)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def _parse_expiry(s: str) -> date | None:
    if not s:
        return None
    for fmt in ("%d%b%Y", "%d%b%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.upper(), fmt).date()
        except ValueError:
            continue
    return None


class Instruments:
    """Index option chains and spot tokens built from the scrip master rows."""

    def __init__(self, rows: list[dict], index_cfg: dict, vix_names: list[str]):
        self.index_cfg = index_cfg
        self.options: dict[str, list[Contract]] = {k: [] for k in index_cfg}
        self.spot_tokens: dict[str, tuple[str, str]] = {}  # index -> (exchange, token)
        self.vix_token: tuple[str, str] | None = None
        wanted_spot = {}
        for idx, c in index_cfg.items():
            for n in c["spot_names"]:
                wanted_spot[(c["spot_exchange"], n.upper())] = idx
        vix_upper = {n.upper() for n in vix_names}

        for r in rows:
            seg = r.get("exch_seg")
            itype = r.get("instrumenttype", "")
            name = (r.get("name") or "").upper()
            if itype == "OPTIDX" and seg in ("NFO", "BFO") and name in self.options:
                if index_cfg[name]["segment"] != seg:
                    continue
                exp = _parse_expiry(r.get("expiry", ""))
                if exp is None:
                    continue
                sym = r.get("symbol", "")
                right = "CE" if sym.endswith("CE") else "PE" if sym.endswith("PE") else None
                if right is None:
                    continue
                self.options[name].append(
                    Contract(
                        token=str(r["token"]),
                        symbol=sym,
                        index=name,
                        segment=seg,
                        expiry=exp,
                        strike=float(r["strike"]) / 100.0,
                        right=right,
                        lot_size=int(float(r["lotsize"])),
                        tick=float(r.get("tick_size") or 5) / 100.0,
                    )
                )
            elif seg in ("NSE", "BSE") and itype in ("AMXIDX", "INDEX", ""):
                sym_u = (r.get("symbol") or "").upper()
                for key in ((seg, sym_u), (seg, name)):
                    if key in wanted_spot and wanted_spot[key] not in self.spot_tokens:
                        self.spot_tokens[wanted_spot[key]] = (seg, str(r["token"]))
                if seg == "NSE" and (sym_u in vix_upper or name in vix_upper) and self.vix_token is None:
                    self.vix_token = (seg, str(r["token"]))
        # Well-known Angel One index tokens, used only if the names above weren't found.
        for idx, (ex, tok) in FALLBACK_SPOT.items():
            if idx in index_cfg and idx not in self.spot_tokens:
                self.spot_tokens[idx] = (ex, tok)
        if self.vix_token is None:
            self.vix_token = ("NSE", "99926017")
        for k, v in self.options.items():
            log.info("instruments: %s %d option contracts, spot=%s", k, len(v), self.spot_tokens.get(k))

    @classmethod
    def from_file(cls, path: Path, index_cfg: dict, vix_names: list[str]) -> "Instruments":
        return cls(json.loads(path.read_text()), index_cfg, vix_names)

    def expiries(self, index: str) -> list[date]:
        return sorted({c.expiry for c in self.options[index]})

    def chain(self, index: str, expiry: date) -> list[Contract]:
        return [c for c in self.options[index] if c.expiry == expiry]

    def lot_size(self, index: str) -> int | None:
        return self.options[index][0].lot_size if self.options[index] else None

    def find(self, index: str, expiry: date, strike: float, right: str) -> Contract | None:
        for c in self.options[index]:
            if c.expiry == expiry and c.right == right and abs(c.strike - strike) < 1e-6:
                return c
        return None
