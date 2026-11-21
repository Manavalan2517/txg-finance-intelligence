"""The KPI registry (§10.1): one config entry plus one tested engine function per KPI. Screens and the deck render
from the registry, so adding a KPI never touches screen code (R10)."""
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from txg.kpi.context import KpiContext
from txg.ledger.chart import CONFIG_DIR

State = Literal["ok", "n.m.", "not_applicable", "needs_data"]


@dataclass(frozen=True)
class Result:
    value: Decimal | None
    state: State = "ok"
    detail: str = ""


@dataclass(frozen=True)
class KpiValue:
    company: str
    period: str
    kpi_id: str
    value: Decimal | None
    unit: str
    state: State
    detail: str = ""


@dataclass(frozen=True)
class KpiEntry:
    id: str
    name: str
    unit: str
    direction: str
    tier: str
    question: str
    inputs: tuple[str, ...]
    function: Callable[[KpiContext, str], Result] | None
    extra: dict = field(default_factory=dict, compare=False)


_FUNCTIONS: dict[str, Callable[[KpiContext, str], Result]] = {}


def kpi(function_name: str):
    """Register an engine function under the name the registry config refers to."""
    def register(fn: Callable[[KpiContext, str], Result]):
        if function_name in _FUNCTIONS:
            raise ValueError(f"duplicate KPI function {function_name}")
        _FUNCTIONS[function_name] = fn
        return fn
    return register


@lru_cache(maxsize=1)
def load_registry() -> dict[str, KpiEntry]:
    import txg.kpi.cash
    import txg.kpi.common
    import txg.kpi.receivables  # noqa: F401

    body = json.loads((CONFIG_DIR / "kpi_registry.json").read_text(encoding="utf-8"))
    entries = {}
    for e in body["kpis"]:
        known = {"id", "name", "unit", "direction", "tier", "question", "inputs", "function"}
        entries[e["id"]] = KpiEntry(e["id"], e["name"], e["unit"], e["direction"], e.get("tier", "supporting"),
                                    e.get("question", ""), tuple(e.get("inputs", [])), _FUNCTIONS.get(e["function"]),
                                    {k: v for k, v in e.items() if k not in known})
    return entries


def compute_all(ctx: KpiContext, period: str) -> dict[str, KpiValue]:
    out = {}
    for kpi_id, entry in load_registry().items():
        if entry.function is None:
            out[kpi_id] = KpiValue(ctx.company, period, kpi_id, None, entry.unit, "needs_data", "no engine function")
            continue
        r = entry.function(ctx, period)
        out[kpi_id] = KpiValue(ctx.company, period, kpi_id, r.value, entry.unit, r.state, r.detail)
    return out
