"""Ranking by riyals at stake (§12.4): score = (1 − q) × impact in SAR; ties by impact, then by distance outside the
normal range. Signals below materiality stay on their KPI but not in the attention list."""
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Candidate:
    signal_id: str
    q_value: float
    impact_sar: Decimal
    distance: float

    @property
    def score(self) -> Decimal:
        return (Decimal(1) - Decimal(str(self.q_value))) * self.impact_sar


@dataclass(frozen=True)
class Ranked:
    attention: list[Candidate]
    below_materiality: list[Candidate]


def rank_signals(candidates: Sequence[Candidate], materiality: Decimal) -> Ranked:
    ordered = sorted(candidates, key=lambda c: (-c.score, -c.impact_sar, -c.distance, c.signal_id))
    return Ranked([c for c in ordered if c.impact_sar >= materiality],
                  [c for c in ordered if c.impact_sar < materiality])
