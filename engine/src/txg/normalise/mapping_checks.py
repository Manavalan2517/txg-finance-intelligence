"""Code checks on account mappings (§9.3, CK-04, CK-05). A failed check is a finding, never a dead end (R7)."""
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from txg.connector.base import Connector
from txg.ledger.chart import load_standard_chart
from txg.normalise.trial_balance import TrialBalance

# Zoho account type -> first digits of standard codes it can plausibly map to.
_ALLOWED_PREFIXES: dict[str, tuple[str, ...]] = {
    "bank": ("1",), "cash": ("1",), "accounts_receivable": ("1",), "other_current_asset": ("1",),
    "fixed_asset": ("1",), "stock": ("1",), "other_asset": ("1",),
    "accounts_payable": ("2",), "other_current_liability": ("2",), "long_term_liability": ("2",),
    "credit_card": ("2",), "other_liability": ("2",),
    "equity": ("3",),
    "income": ("4",), "other_income": ("4", "7"),
    "cost_of_goods_sold": ("5",), "expense": ("5", "6", "7"), "other_expense": ("6", "7"),
}
_SIGN_WINDOW = 6  # closed months a wrong-signed balance must persist before it is a finding


@dataclass(frozen=True)
class MappingFinding:
    check: str
    account_id: str          # the source account concerned, or "" when the finding is about a standard line
    detail: str
    std_code: str = ""       # set for findings about a whole standard line (SIGN)


def proposal_checks(zoho_type: str, std_code: str) -> list[str]:
    """Checks on one proposal; any message goes back to the model as a finding."""
    chart = load_standard_chart()
    if std_code not in chart:
        return [f"{std_code} is not in the standard chart"]
    allowed = _ALLOWED_PREFIXES.get(zoho_type)
    if allowed and not std_code.startswith(allowed):
        return [f"Zoho type {zoho_type} does not fit standard class {chart[std_code].cls} ({std_code})"]
    return []


def _active_accounts(tbs: Mapping[str, TrialBalance]) -> set[str]:
    active = set()
    for tb in tbs.values():
        active |= {a for a, v in tb.balances.items() if v}
        active |= {a for a, v in tb.movements.items() if v}
    return active


def _sign_findings(tbs: Mapping[str, TrialBalance], mapping: Mapping[str, str]) -> list[MappingFinding]:
    """Assets with a persistent credit balance, or liabilities with a persistent debit balance, by standard line."""
    chart = load_standard_chart()
    closed = sorted(tbs)[:-1][-_SIGN_WINDOW:]
    findings = []
    for code in sorted(set(mapping.values())):
        acc = chart.get(code)
        if acc is None or acc.contra or acc.cls not in ("asset", "liability"):
            continue
        totals = [sum((v for a, v in tbs[m].balances.items() if mapping.get(a) == code), Decimal(0)) for m in closed]
        wrong = all(t < 0 for t in totals) if acc.cls == "asset" else all(t > 0 for t in totals)
        if closed and wrong and any(totals):
            findings.append(MappingFinding("SIGN", "", f"{acc.name} has the wrong sign for {len(closed)} months",
                                           std_code=code))
    return findings


def check_mapping(conn: Connector, company: str, tbs: Mapping[str, TrialBalance],
                  mapping: Mapping[str, str]) -> list[MappingFinding]:
    types = {r.data["account_id"]: r.data.get("account_type", "") for r in conn.iter_records(company, "chartofaccounts")}
    findings = [MappingFinding("CK-04", a, "account with a balance or activity is not mapped")
                for a in sorted(_active_accounts(tbs) - set(mapping))]
    for acc, code in sorted(mapping.items()):
        findings += [MappingFinding("CLASS", acc, msg) for msg in proposal_checks(types.get(acc, ""), code)]
    return findings + _sign_findings(tbs, mapping)
