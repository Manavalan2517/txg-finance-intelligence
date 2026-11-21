"""Rebuild the trial balance from the account registers and tie it out (C5; §7.4; CK-02, CK-03, CK-07, CK-08)."""
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from txg.connector.base import Connector

ZERO = Decimal(0)
CENT = Decimal("0.01")
OPENING_BALANCE = "opening_balance"


@dataclass(frozen=True)
class TrialBalance:
    """Closing balances and the month's movements per source account, debit positive."""
    company: str
    month: str
    balances: Mapping[str, Decimal]
    movements: Mapping[str, Decimal] = field(default_factory=dict)

    @property
    def imbalance(self) -> Decimal:
        return sum(self.balances.values(), ZERO)

    @property
    def is_balanced(self) -> bool:
        return self.imbalance.quantize(CENT) == ZERO


@dataclass(frozen=True)
class TieResult:
    tied: bool
    differences: Mapping[str, Decimal]  # ours − printed, per account, non-zero only


@dataclass(frozen=True)
class Finding:
    check: str
    company: str
    detail: str
    amount: Decimal


def _month(d) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_range(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def months_missing(months: list[str]) -> list[str]:
    if not months:
        return []
    present = set(months)
    return [m for m in _month_range(min(months), max(months)) if m not in present]


def rebuild_trial_balances(conn: Connector, company: str) -> dict[str, TrialBalance]:
    """One trial balance per month from the first to the last posting month (open month included).

    Balances include the go-live opening balances; `movements` are the month's activity only, so opening-balance
    postings are not counted as activity of the go-live month."""
    posted: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    activity: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for line in conn.iter_ledger_lines(company):
        month, amount = _month(line.date), line.debit - line.credit
        posted[month][line.account_id] += amount
        if line.transaction_type != OPENING_BALANCE:
            activity[month][line.account_id] += amount
    if not posted:
        return {}
    running: dict[str, Decimal] = defaultdict(Decimal)
    out = {}
    for month in _month_range(min(posted), max(posted)):
        for acc, mv in posted.get(month, {}).items():
            running[acc] += mv
        out[month] = TrialBalance(company, month, dict(running), dict(activity.get(month, {})))
    return out


def tie_out(ours: TrialBalance, printed: TrialBalance) -> TieResult:
    """CK-03: tolerance SAR 0.00 per account at two decimals."""
    diffs = {}
    for acc in set(ours.balances) | set(printed.balances):
        d = (ours.balances.get(acc, ZERO) - printed.balances.get(acc, ZERO)).quantize(CENT)
        if d != ZERO:
            diffs[acc] = d
    return TieResult(tied=not diffs, differences=diffs)


def _open_documents_sar(conn: Connector, company: str, record_type: str) -> Decimal:
    total = ZERO
    for rec in conn.iter_records(company, record_type):
        rate = Decimal(str(rec.data.get("exchange_rate") or 1))
        total += (Decimal(str(rec.data.get("balance") or 0)) * rate).quantize(CENT)
    return total


def _control_balance(conn: Connector, company: str, account_type: str) -> Decimal:
    accounts = {r.data["account_id"] for r in conn.iter_records(company, "chartofaccounts")
                if r.data.get("account_type") == account_type}
    return sum((ln.debit - ln.credit for ln in conn.iter_ledger_lines(company) if ln.account_id in accounts), ZERO)


def subledger_vs_control(conn: Connector, company: str) -> list[Finding]:
    """CK-07 at the data cut-off: open invoices = receivables control; open bills = payables control (in SAR)."""
    findings = []
    receivable = _open_documents_sar(conn, company, "invoices") - _open_documents_sar(conn, company, "creditnotes")
    payable = _open_documents_sar(conn, company, "bills")
    for label, sub, control in (
        ("open invoices vs receivables control", receivable, _control_balance(conn, company, "accounts_receivable")),
        ("open bills vs payables control", payable, -_control_balance(conn, company, "accounts_payable")),
    ):
        diff = (sub - control).quantize(CENT)
        if diff != ZERO:
            findings.append(Finding("CK-07", company, label, diff))
    return findings
