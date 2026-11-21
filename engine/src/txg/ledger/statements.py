"""Statements from the standard ledger (C9, §7.4): balance sheet (debit positive, retained earnings including
unclosed profit), income statement (credit positive, per month) and an indirect cash flow statement that
explains the change in cash exactly (CK-06)."""
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from txg.ledger.chart import load_standard_chart
from txg.normalise.trial_balance import TrialBalance

ZERO = Decimal(0)
CASH = "1110"
RETAINED = "3300"
_INVESTING = {"1115", "1170", "1210", "1230", "1240", "1250", "1260", "1290"}
_FINANCING = {"1180", "1220", "2170", "2175", "2180", "2185", "2190", "2195", "2210", "2220",
              "3100", "3200", "3400", "3500"}
_DEPRECIATION, _ROU_DEPRECIATION, _AMORTISATION = "6600", "6610", "6700"


@dataclass(frozen=True)
class CashFlow:
    operating: Decimal
    investing: Decimal
    financing: Decimal
    change_in_cash: Decimal


@dataclass(frozen=True)
class Statements:
    company: str
    month: str
    balance_sheet: Mapping[str, Decimal]
    income: Mapping[str, Decimal]
    cash_flow: CashFlow

    @property
    def net_profit(self) -> Decimal:
        return sum(self.income.values(), ZERO)

    @property
    def cash(self) -> Decimal:
        return self.balance_sheet.get(CASH, ZERO)

    @property
    def balance_sheet_imbalance(self) -> Decimal:
        return sum(self.balance_sheet.values(), ZERO)

    @property
    def revenue(self) -> Decimal:
        return self.income.get("4100", ZERO)

    @property
    def gross_profit(self) -> Decimal:
        return self.revenue + sum((v for c, v in self.income.items() if c.startswith("5")), ZERO)


def _group(values: Mapping[str, Decimal], mapping: Mapping[str, str]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for acc, v in values.items():
        if v:
            out[mapping[acc]] += v
    return out


def _cash_flow(bs: Mapping[str, Decimal], prev: Mapping[str, Decimal], income: Mapping[str, Decimal],
               retained_ledger_delta: Decimal) -> CashFlow:
    delta = {c: bs.get(c, ZERO) - prev.get(c, ZERO) for c in set(bs) | set(prev)}
    dep, rou_dep, amort = (-income.get(c, ZERO) for c in (_DEPRECIATION, _ROU_DEPRECIATION, _AMORTISATION))
    net_profit = sum(income.values(), ZERO)
    others = {c: d for c, d in delta.items() if c not in (CASH, RETAINED)}
    investing = -sum((d for c, d in others.items() if c in _INVESTING), ZERO) - dep - amort
    financing = -sum((d for c, d in others.items() if c in _FINANCING), ZERO) - rou_dep - retained_ledger_delta
    operating_lines = -sum((d for c, d in others.items() if c not in _INVESTING | _FINANCING), ZERO)
    operating = net_profit + dep + rou_dep + amort + operating_lines
    return CashFlow(operating, investing, financing, delta.get(CASH, ZERO))


def build_statements(tbs: Mapping[str, TrialBalance], mapping: Mapping[str, str]) -> dict[str, Statements]:
    chart = load_standard_chart()
    unmapped = {a for tb in tbs.values() for a, v in tb.balances.items() if v and a not in mapping}
    if unmapped:
        raise ValueError(f"accounts with balances are not mapped (CK-04): {sorted(unmapped)}")
    out: dict[str, Statements] = {}
    prev_bs: Mapping[str, Decimal] = {}
    prev_retained_ledger = ZERO
    for month in sorted(tbs):
        tb = tbs[month]
        grouped = _group(tb.balances, mapping)
        bs = {c: v for c, v in grouped.items() if chart[c].is_balance_sheet}
        retained_ledger = bs.get(RETAINED, ZERO)
        bs[RETAINED] = retained_ledger + sum((v for c, v in grouped.items() if not chart[c].is_balance_sheet), ZERO)
        income = {c: -v for c, v in _group(tb.movements, mapping).items() if not chart[c].is_balance_sheet}
        cf = _cash_flow(bs, prev_bs, income, retained_ledger - prev_retained_ledger)
        out[month] = Statements(tb.company, month, bs, income, cf)
        prev_bs, prev_retained_ledger = bs, retained_ledger
    return out


def ltm(stmts: Mapping[str, Statements], month: str, metric: str) -> Decimal:
    """Sum of a flow metric over the 12 months ending at `month` ('revenue', 'gross_profit', 'net_profit', or a code)."""
    months = [m for m in sorted(stmts) if m <= month][-12:]

    def value(s: Statements) -> Decimal:
        return getattr(s, metric) if metric in ("revenue", "gross_profit", "net_profit") else s.income.get(metric, ZERO)

    return sum((value(stmts[m]) for m in months), ZERO)
