"""Chance of hitting budget (§12.7, HL-2). Forecast each remaining month as seasonal profile × recent level
(exponentially weighted, half-life 6 months); measure the same method's % errors by rolling back-test; draw whole
error vectors across horizons (keeping their correlation) 10,000 times; add actual year-to-date EBITDA."""
from dataclasses import dataclass

import numpy as np

from txg.kpi.common import _ebitda
from txg.kpi.context import KpiContext
from txg.stats.seed import seed_for
from txg.uploads.budgets import Budgets

HALF_LIFE = 6.0
PATHS = 10_000


@dataclass(frozen=True)
class BudgetSim:
    budget: float
    year_to_date: float
    chance: float
    p10: float
    p50: float
    p90: float
    origins: int


def _profile(months: list[str], e: dict[str, float]) -> dict[int, float]:
    """Average share of each calendar month in its year's monthly mean, over complete years."""
    by_year: dict[str, list[str]] = {}
    for m in months:
        by_year.setdefault(m[:4], []).append(m)
    ratios: dict[int, list[float]] = {}
    for ms in by_year.values():
        if len(ms) == 12:
            mean = sum(e[m] for m in ms) / 12
            for m in ms:
                ratios.setdefault(int(m[5:]), []).append(e[m] / mean if mean else 1.0)
    return {k: sum(v) / len(v) for k, v in ratios.items()} if len(ratios) == 12 else {k: 1.0 for k in range(1, 13)}


def _forecast(history: list[str], e: dict[str, float], prof: dict[int, float], targets: list[str]) -> list[float]:
    weights = [0.5 ** (i / HALF_LIFE) for i in range(len(history))][::-1]
    level = sum(w * e[m] / prof[int(m[5:])] for w, m in zip(weights, history)) / sum(weights)
    return [level * prof[int(t[5:])] for t in targets]


def chance_of_hitting_budget(ctx: KpiContext, budgets: Budgets, as_of: str, paths: int = PATHS,
                             line: str = "EBITDA") -> BudgetSim:
    year = as_of[:4]
    months = [m for m in ctx.months if m <= as_of]
    e = {m: float(_ebitda(ctx, m)) for m in months}
    targets = [f"{year}-{k:02d}" for k in range(int(as_of[5:]) + 1, 13)]
    budget = float(sum(budgets[line][f"{year}-{k:02d}"] for k in range(1, 13)))
    ytd = sum(e[m] for m in months if m.startswith(year))
    prof = _profile(months, e)
    h = len(targets)
    errors = []
    for i in range(12, len(months) - h):  # rolling back-test of the same method at horizons 1..h
        fc = _forecast(months[: i + 1], e, prof, months[i + 1: i + 1 + h])
        actual = [e[m] for m in months[i + 1: i + 1 + h]]
        if all(a != 0 for a in actual):
            errors.append([(f - a) / abs(a) for f, a in zip(fc, actual)])
    forecast = np.array(_forecast(months, e, prof, targets))
    rng = np.random.default_rng(seed_for(ctx.company, as_of, "HL-2"))
    err = np.array(errors) if errors else np.zeros((1, h))
    draws = err[rng.integers(0, len(err), size=paths)]
    remaining = (forecast / np.clip(1 + draws, 0.05, None)).sum(axis=1) if h else np.zeros(paths)
    full_year = ytd + remaining
    p10, p50, p90 = (float(np.percentile(full_year, q)) for q in (10, 50, 90))
    return BudgetSim(budget, ytd, float(np.mean(full_year >= budget)), p10, p50, p90, len(errors))
