"""Zoho's printed Trial Balance report (upload) and the conversion of our rebuilt ledger to the same basis (CK-03).

The report shows balance-sheet accounts at the month end, income and expense accounts for the financial year to
date, and earlier years' profit inside retained earnings. Accounts are keyed by account code in the report."""
import csv
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from txg.connector.base import Connector
from txg.normalise.trial_balance import TrialBalance

PL_TYPES = {"income", "other_income", "expense", "cost_of_goods_sold", "other_expense"}
_AS_OF = re.compile(r"As of (\d{2}/\d{2}/\d{4})")
ZERO = Decimal(0)


def _accounts(conn: Connector, company: str) -> dict[str, dict]:
    return {r.data["account_code"]: r.data for r in conn.iter_records(company, "chartofaccounts")}


def load_printed_tb(path: Path, conn: Connector, company: str) -> TrialBalance:
    lines = path.read_text(encoding="utf-8").splitlines()
    as_of = next((m.group(1) for ln in lines[:5] if (m := _AS_OF.search(ln))), None)
    if as_of is None:
        raise ValueError(f"{path.name}: no 'As of' date in the report header")
    month = datetime.strptime(as_of, "%d/%m/%Y").strftime("%Y-%m")
    header = next(i for i, ln in enumerate(lines) if ln.startswith("Account,"))
    by_code = _accounts(conn, company)
    balances: dict[str, Decimal] = {}
    for row in csv.DictReader(lines[header:]):
        if row["Account"] == "Total":
            continue
        account = by_code.get(row["Account Code"])
        if account is None:
            raise ValueError(f"{path.name}: account code {row['Account Code']!r} is not in the chart of accounts")
        balances[account["account_id"]] = Decimal(row["Net Debit"] or "0") - Decimal(row["Net Credit"] or "0")
    return TrialBalance(company, month, balances)


def _fiscal_year_months(month: str, fiscal_start_month: int) -> list[str]:
    y, m = map(int, month.split("-"))
    start_y = y if m >= fiscal_start_month else y - 1
    out, cy, cm = [], start_y, fiscal_start_month
    while (cy, cm) <= (y, m):
        out.append(f"{cy:04d}-{cm:02d}")
        cy, cm = (cy + 1, 1) if cm == 12 else (cy, cm + 1)
    return out


def to_printed_basis(conn: Connector, company: str, tbs: Mapping[str, TrialBalance], month: str,
                     retained_accounts: set[str], fiscal_start_month: int = 1) -> TrialBalance:
    """Our ledger on the report's basis: P&L accounts year to date; earlier years' profit in retained earnings."""
    types = {r.data["account_id"]: r.data.get("account_type", "") for r in conn.iter_records(company, "chartofaccounts")}
    if not retained_accounts:
        raise ValueError("no retained-earnings account is mapped (standard line 3300)")
    ytd = [m for m in _fiscal_year_months(month, fiscal_start_month) if m in tbs]
    out: dict[str, Decimal] = {}
    earlier_profit = ZERO
    for acc, bal in tbs[month].balances.items():
        if types.get(acc) in PL_TYPES:
            year = sum((tbs[m].movements.get(acc, ZERO) for m in ytd), ZERO)
            earlier_profit += bal - year
            out[acc] = year
        else:
            out[acc] = bal
    target = min(retained_accounts)
    out[target] = out.get(target, ZERO) + earlier_profit
    return TrialBalance(company, month, {a: v for a, v in out.items() if v})
