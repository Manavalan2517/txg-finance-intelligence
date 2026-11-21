"""Seasonal and Hijri holiday adjustment (§12.1).

log(y_t) = α + β·t + Σ γ_m·Month_m + δ_R·R_t + δ_F·F_t + δ_A·A_t + u_t, u_t AR(1), fitted by GLS (statsmodels
GLSAR). A holiday effect is used only when its 90% confidence interval excludes zero; signs are estimated, never
assumed. holiday-adjusted y_t = y_t × exp(−(δ_R·R_t + δ_F·F_t + δ_A·A_t))."""
import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
from statsmodels.regression.linear_model import GLSAR

from txg.stats.calendar import holiday_shares

MIN_MONTHS = 24
EFFECTS = ("ramadan", "eid_fitr", "eid_adha")
ALPHA = 0.10


@dataclass(frozen=True)
class HolidayModel:
    effects_used: dict[str, float] = field(default_factory=dict)
    effects_rejected: dict[str, tuple[float, float]] = field(default_factory=dict)  # name -> 90% CI
    note: str = ""
    cal: Mapping = field(default_factory=dict, repr=False)

    def factor(self, month: str) -> float:
        if not self.effects_used:
            return 1.0
        s = holiday_shares(self.cal, month)
        return math.exp(sum(coef * getattr(s, name) for name, coef in self.effects_used.items()))

    def adjusted(self, series: Mapping[str, float]) -> dict[str, float]:
        return {m: v / self.factor(m) for m, v in series.items()}


def _design(months: list[str], cal: Mapping) -> np.ndarray:
    rows = []
    for t, m in enumerate(months):
        month_no = int(m[5:7])
        dummies = [1.0 if month_no == k else 0.0 for k in range(2, 13)]
        s = holiday_shares(cal, m)
        rows.append([1.0, float(t), *dummies, s.ramadan, s.eid_fitr, s.eid_adha])
    return np.array(rows)


def fit_holiday_model(series: Mapping[str, float], cal: Mapping) -> HolidayModel:
    months = sorted(m for m, v in series.items() if v > 0)
    if len(months) < MIN_MONTHS:
        return HolidayModel(note=f"needs {MIN_MONTHS} months of positive values; effects borrowed later (§12.19)",
                            cal=cal)
    y = np.log(np.array([series[m] for m in months]))
    x = _design(months, cal)
    fit = GLSAR(y, x, rho=1).iterative_fit(maxiter=20)
    ci = fit.conf_int(alpha=ALPHA)
    used, rejected = {}, {}
    for i, name in enumerate(EFFECTS, start=x.shape[1] - len(EFFECTS)):
        lo, hi = float(ci[i][0]), float(ci[i][1])
        if lo > 0 or hi < 0:
            used[name] = float(fit.params[i])
        else:
            rejected[name] = (lo, hi)
    return HolidayModel(used, rejected, cal=cal)
