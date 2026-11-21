"""Performance versus mix (§12.17): m₁ − m₀ = Σ w₁(m₁ − m₀) [performance] + Σ (w₁ − w₀)·m₀ [mix]. Exact."""
from collections.abc import Sequence
from decimal import Decimal


class NotMeaningful(ValueError):
    """The figure cannot be computed meaningfully (shown as "n.m." on screen)."""


def performance_mix_split(revenue0: Sequence[Decimal], revenue1: Sequence[Decimal], margin0: Sequence[Decimal],
                          margin1: Sequence[Decimal]) -> tuple[Decimal, Decimal]:
    if not (len(revenue0) == len(revenue1) == len(margin0) == len(margin1)) or not revenue0:
        raise ValueError("performance/mix split needs one revenue and margin per company in both periods")
    total0, total1 = sum(revenue0), sum(revenue1)
    if total0 <= 0 or total1 <= 0:
        raise NotMeaningful("performance/mix split needs positive total revenue in both periods")
    w0 = [r / total0 for r in revenue0]
    w1 = [r / total1 for r in revenue1]
    performance = sum((a * (m1 - m0) for a, m0, m1 in zip(w1, margin0, margin1)), Decimal(0))
    mix = sum(((a - b) * m0 for a, b, m0 in zip(w1, w0, margin0)), Decimal(0))
    return performance, mix
