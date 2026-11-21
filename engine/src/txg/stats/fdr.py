"""The false-alarm limit (§12.3): Benjamini–Hochberg across every signal test of the month (company × KPI × side).
Suppressed candidates are kept, with their reason, for the "not alarmed" log (§13.3)."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

DEFAULT_Q = 0.10


@dataclass(frozen=True)
class SignalTest:
    test_id: str
    p: float
    q_value: float = 1.0
    reason: str = ""


def benjamini_hochberg(tests: Sequence[SignalTest], q: float = DEFAULT_Q) -> tuple[list[SignalTest], list[SignalTest]]:
    m = len(tests)
    if m == 0:
        return [], []
    ordered = sorted(tests, key=lambda t: (t.p, t.test_id))
    k = max((i for i, t in enumerate(ordered, start=1) if t.p <= i / m * q), default=0)
    q_values, running = [0.0] * m, 1.0
    for i in range(m, 0, -1):  # adjusted q-value: min over j ≥ i of p(j)·m/j, capped at 1
        running = min(running, ordered[i - 1].p * m / i)
        q_values[i - 1] = running
    kept = [replace(t, q_value=q_values[i]) for i, t in enumerate(ordered[:k])]
    suppressed = [replace(t, q_value=q_values[k + i], reason=t.reason or "false-alarm limit")
                  for i, t in enumerate(ordered[k:])]
    return kept, suppressed


def group_trends(tests: Mapping[tuple[str, str], tuple[float, float]], q: float = DEFAULT_Q) -> dict[tuple[str, str], str]:
    """Where each KPI is heading (§10.4) under the group-wide false-alarm limit (§12.3).
    tests: (company, kpi) → (p on the bad side, p on the good side) for the month. Slipping = a kept bad-side
    signal; improving = a kept good-side signal; steady otherwise."""
    candidates = [SignalTest(f"{c}\x1f{k}\x1f{side}", p)
                  for (c, k), (p_bad, p_good) in tests.items() for side, p in (("bad", p_bad), ("good", p_good))]
    kept, _ = benjamini_hochberg(candidates, q)
    sides = {tuple(t.test_id.split("\x1f")) for t in kept}
    return {(c, k): "slipping" if (c, k, "bad") in sides else "improving" if (c, k, "good") in sides else "steady"
            for c, k in tests}
