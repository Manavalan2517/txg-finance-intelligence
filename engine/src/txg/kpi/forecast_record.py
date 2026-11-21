"""Forecast record and calibration (§11.2.8 TR-3, §12.15): % error e = (forecast − actual) ÷ |actual|;
bias = mean e; MAPE = mean |e|, over the last 8 at the same horizon; sign test p = P(X ≥ k), X ~ Binomial(n, ½)."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import comb

from txg.kpi.context import KpiContext
from txg.uploads.budgets import Budgets

ACT_P, WATCH_P, ACT_BIAS = 0.05, 0.10, Decimal("0.05")
_LINE_CODES = {"Revenue": ("4100",)}


def sign_test_p(k: int, n: int) -> float:
    return sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n


@dataclass(frozen=True)
class ForecastRecord:
    n: int
    over: int
    bias: Decimal
    mape: Decimal
    p: float
    status: str


def forecast_record(errors: Sequence[Decimal]) -> ForecastRecord:
    n = len(errors)
    if n == 0:
        return ForecastRecord(0, 0, Decimal(0), Decimal(0), 1.0, "needs_data")
    over = sum(1 for e in errors if e > 0)
    p = sign_test_p(over, n)  # §12.15: one-sided on over-forecasts (budget optimism)
    bias = sum(errors, Decimal(0)) / n
    mape = sum((abs(e) for e in errors), Decimal(0)) / n
    status = "act" if p < ACT_P and abs(bias) > ACT_BIAS else "watch" if p < WATCH_P else "healthy"
    return ForecastRecord(n, over, bias, mape, p, status)


def quarterly_errors(ctx: KpiContext, budgets: Budgets, line: str, closed_through: str) -> dict[str, Decimal]:
    """Budget against actual for every complete closed quarter; the actual comes from the standard ledger."""
    codes = _LINE_CODES[line]
    by_quarter: dict[str, list[str]] = {}
    for m in ctx.months:
        if m <= closed_through:
            y, mo = m.split("-")
            by_quarter.setdefault(f"{y}Q{(int(mo) - 1) // 3 + 1}", []).append(m)
    out = {}
    for quarter, months in by_quarter.items():
        if len(months) != 3 or any(m not in budgets.get(line, {}) for m in months):
            continue
        actual = sum((ctx.flow(m, codes) for m in months), Decimal(0))
        budget = sum((budgets[line][m] for m in months), Decimal(0))
        if actual:
            out[quarter] = (budget - actual) / abs(actual)
    return out


def last(errors: Mapping[str, Decimal], n: int = 8) -> list[Decimal]:
    return [errors[q] for q in sorted(errors)][-n:]
