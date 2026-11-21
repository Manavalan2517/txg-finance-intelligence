"""Normal ranges and signals (§12.2): Shewhart individuals (XmR) chart on the adjusted series.

Baseline = the 24 months before the latest 3 (minimum 12), so a new shift does not widen its own limits.
Rule A: latest point outside X̄ ± 2.66·mR̄ (p from σ̂ = mR̄ ÷ 1.128). Rule B: 8 consecutive points on one side."""
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

BASELINE_MONTHS, RECENT_MONTHS, MIN_BASELINE = 24, 3, 12
RULE_B_RUN = 8
D2 = 1.128
Side = Literal["high", "low"]


@dataclass(frozen=True)
class NormalRange:
    centre: float
    mr_bar: float
    lower: float
    upper: float
    n: int

    @property
    def sigma(self) -> float:
        return self.mr_bar / D2


def normal_range(series: Sequence[float], window: int = 1) -> NormalRange | None:
    """`window` = how many months each value covers. For a rolling 12-month figure consecutive values share 11
    months, so moving ranges are taken between non-overlapping windows (lag 12); month-to-month ranges would
    understate the variation and quiet companies would breach their limits."""
    baseline = list(series[:-RECENT_MONTHS])[-BASELINE_MONTHS:]
    if len(baseline) < MIN_BASELINE or len(baseline) - window < MIN_BASELINE // 2:
        return None
    centre = sum(baseline) / len(baseline)
    moves = [abs(baseline[i] - baseline[i - window]) for i in range(window, len(baseline))]
    mr_bar = sum(moves) / len(moves)
    return NormalRange(centre, mr_bar, centre - 2.66 * mr_bar, centre + 2.66 * mr_bar, len(baseline))


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def signal_p(series: Sequence[float], nr: NormalRange, bad_side: Side) -> tuple[float, str]:
    """One-sided p-value of a signal on `bad_side` for the latest point; 1.0 when there is none."""
    x = series[-1]
    sign = 1 if bad_side == "high" else -1
    p_a = 1.0
    if sign * (x - nr.centre) > 0:
        p_a = 1.0 if nr.sigma == 0 else 1 - _phi(abs(x - nr.centre) / nr.sigma)
    run = series[-RULE_B_RUN:]
    p_b = 0.5 ** RULE_B_RUN if len(run) == RULE_B_RUN and all(sign * (v - nr.centre) > 0 for v in run) else 1.0
    return (p_a, "A") if p_a <= p_b else (p_b, "B")


def outside(value: float, nr: NormalRange, bad_side: Side) -> bool:
    return value > nr.upper if bad_side == "high" else value < nr.lower
