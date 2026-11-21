"""Monthly standard-ledger series that every KPI function reads (§10, §11). Built once per company."""
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from txg.ledger.chart import load_standard_chart
from txg.ledger.statements import RETAINED, build_statements
from txg.normalise.trial_balance import TrialBalance

ZERO = Decimal(0)
DA_CODES = ("6600", "6610", "6700")
STAFF_CODES = ("6100", "6110", "6120", "5200")
DEBT_CODES = ("2170", "2175", "2210")
LEASE_CODES = ("2180", "2220")


def previous_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"


@dataclass(frozen=True)
class KpiContext:
    """income: credit positive per month; bs: closing balance sheet, debit positive (RE incl. unclosed profit);
    bs_movement: the month's balance-sheet activity, debit positive; opening_bs: the go-live opening position."""
    company: str
    months: list[str]
    income: Mapping[str, Mapping[str, Decimal]]
    bs: Mapping[str, Mapping[str, Decimal]]
    bs_movement: Mapping[str, Mapping[str, Decimal]]
    opening_bs: Mapping[str, Decimal] = field(default_factory=dict)
    facts: Mapping[str, Any] = field(default_factory=dict)  # month -> MonthFacts (sub-ledger), when available
    cash_flows: Mapping[str, Any] = field(default_factory=dict)  # month -> CashFlows (direct method), when available

    def window(self, month: str, n: int) -> list[str] | None:
        """The n months ending at `month`, or None if any of them is outside the books."""
        out, m = [], month
        for _ in range(n):
            if m not in self.income:
                return None
            out.append(m)
            m = previous_month(m)
        return list(reversed(out))

    def bs_at(self, month: str) -> Mapping[str, Decimal] | None:
        if month in self.bs:
            return self.bs[month]
        return self.opening_bs if self.months and month == previous_month(self.months[0]) else None

    def flow(self, month: str, codes) -> Decimal:
        inc = self.income.get(month, {})
        return sum((inc.get(c, ZERO) for c in codes), ZERO)

    def flow_where(self, month: str, predicate) -> Decimal:
        return sum((v for c, v in self.income.get(month, {}).items() if predicate(c)), ZERO)


def _group(values: Mapping[str, Decimal], mapping: Mapping[str, str]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for acc, v in values.items():
        if v:
            out[mapping[acc]] += v
    return dict(out)


def _opening(first: TrialBalance, mapping: Mapping[str, str]) -> dict[str, Decimal]:
    chart = load_standard_chart()
    before = {a: first.balances.get(a, ZERO) - first.movements.get(a, ZERO) for a in first.balances}
    grouped = _group(before, mapping)
    out = {c: v for c, v in grouped.items() if chart[c].is_balance_sheet}
    out[RETAINED] = out.get(RETAINED, ZERO) + sum((v for c, v in grouped.items() if not chart[c].is_balance_sheet), ZERO)
    return out


def build_context(company: str, tbs: Mapping[str, TrialBalance], mapping: Mapping[str, str],
                  facts: Mapping[str, Any] | None = None,
                  cash_flows: Mapping[str, Any] | None = None) -> KpiContext:
    chart = load_standard_chart()
    stmts = build_statements(tbs, mapping)
    months = sorted(stmts)
    movement = {m: {c: v for c, v in _group(tbs[m].movements, mapping).items() if chart[c].is_balance_sheet}
                for m in months}
    return KpiContext(company, months, {m: stmts[m].income for m in months},
                      {m: stmts[m].balance_sheet for m in months}, movement,
                      _opening(tbs[months[0]], mapping) if months else {}, dict(facts or {}),
                      dict(cash_flows or {}))
