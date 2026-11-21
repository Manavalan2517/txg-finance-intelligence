"""Second readings instead of approvals (§9.10, R16, D-15).

Consequential calls are read twice by independent steps; the second never sees the first. If they disagree,
code measures the effect in riyals: below materiality the higher-confidence reading is applied quietly; above
it the higher-confidence reading is applied and the affected numbers carry an "unreviewed" marker."""
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from txg.modelsteps.contract import ModelStep, StepResult

_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass(frozen=True)
class Decision:
    chosen: Any
    first: StepResult
    second: StepResult | None
    agreed: bool
    unreviewed: bool
    effect_sar: Decimal


def read_twice(first: ModelStep, second: ModelStep, brief: Any) -> tuple[StepResult, StepResult]:
    """Both steps get the same brief; nothing from the first reading reaches the second."""
    return first.run(brief), second.run(brief)


def reconcile(first: StepResult, second: StepResult, key: Callable[[Any], Any],
              effect_sar: Callable[[Any, Any], Decimal], materiality: Decimal) -> Decision:
    if key(first.output) == key(second.output):
        return Decision(first.output, first, second, True, False, Decimal(0))
    winner = second if _RANK.get(second.confidence, 0) > _RANK.get(first.confidence, 0) else first
    effect = abs(effect_sar(first.output, second.output))
    return Decision(winner.output, first, second, False, effect >= materiality, effect)
