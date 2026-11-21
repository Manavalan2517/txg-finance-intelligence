"""Where a KPI stands and where it is heading (§10.3–§10.4). The engine computes the status; screens only show it."""
from collections.abc import Mapping, Sequence
from enum import Enum

from txg.stats.xmr import normal_range, outside

ACT_RUN = 3  # own normal: outside on the bad side for 3 consecutive months → act


class Status(str, Enum):
    HEALTHY = "healthy"
    WATCH = "watch"
    ACT = "act"
    CONTEXT = "context"
    NEEDS_DATA = "needs_data"


def _bad_side(direction: str) -> str:
    return "high" if direction == "lower_better" else "low"


def _hurdle(value: float, y: Mapping) -> Status:
    if y.get("direction", "higher_better") == "higher_better":
        if value < y["act_below"]:
            return Status.ACT
        return Status.WATCH if value < y["watch_below"] else Status.HEALTHY
    if value > y["act_above"]:
        return Status.ACT
    return Status.WATCH if value > y["watch_above"] else Status.HEALTHY


def _own_normal(value: float, y: Mapping, history: Sequence[float]) -> Status:
    series = [*history, value]
    nr = normal_range(series, window=int(y.get("window", 1)))
    if nr is None:
        return Status.NEEDS_DATA
    side = _bad_side(y.get("direction", "higher_better"))
    if not outside(value, nr, side):
        return Status.HEALTHY
    recent = series[-ACT_RUN:]
    return Status.ACT if len(recent) == ACT_RUN and all(outside(v, nr, side) for v in recent) else Status.WATCH


def level_status(value: float | None, yardstick: Mapping, history: Sequence[float]) -> Status:
    """Hard limits and peer bands are added with the simulations (C3) and the peer engine (D4); until a company
    has peers, the spec's fallback is its own normal range (§12.5, CK-17)."""
    if value is None:
        return Status.NEEDS_DATA
    kind = yardstick.get("type", "none")
    if kind == "hurdle":
        return _hurdle(value, yardstick)
    if kind in ("own_normal", "peer_band"):
        return _own_normal(value, yardstick, history)
    return Status.CONTEXT


def trend(kept_bad: bool, kept_good: bool) -> str:
    if kept_bad:
        return "slipping"
    return "improving" if kept_good else "steady"
