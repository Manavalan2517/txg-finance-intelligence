"""The standard chart of accounts (Appendix C): the one fixed vocabulary in the system (R4, §8.2)."""
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("TXG_CONFIG_DIR", Path(__file__).resolve().parents[3] / "config"))

BALANCE_SHEET_CLASSES = ("asset", "liability", "equity")


@dataclass(frozen=True)
class StdAccount:
    code: str
    name: str
    cls: str
    role: str
    contra: bool = False

    @property
    def is_balance_sheet(self) -> bool:
        return self.cls in BALANCE_SHEET_CLASSES


@lru_cache(maxsize=1)
def load_standard_chart() -> dict[str, StdAccount]:
    body = json.loads((CONFIG_DIR / "standard_chart.json").read_text(encoding="utf-8"))
    return {a["code"]: StdAccount(a["code"], a["name"], a["class"], a["role"], bool(a.get("contra")))
            for a in body["accounts"]}
