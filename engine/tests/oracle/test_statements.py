"""Task B6: statements from the standard ledger tie to the answer key; cash flow ties to cash (§7.4, CK-05, CK-06)."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.ledger.statements import build_statements
from txg.normalise.trial_balance import rebuild_trial_balances

COMPANIES = ["EH-01", "EH-02", "EH-03", "EH-05", "EH-06", "EH-07", "EH-08", "EH-09", "EH-14", "EH-21"]


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def _expected(answer_key: Path, company: str) -> dict[tuple[str, str], Decimal]:
    with open(answer_key / company / "monthly_statements.csv", encoding="utf-8", newline="") as f:
        return {(r["month"], r["standard_code"]): Decimal(r["amount_sar"]) for r in csv.DictReader(f)
                if r["status"] == "closed"}


@pytest.fixture(scope="module")
def conn(zoho_root: Path) -> FileConnector:
    return FileConnector(zoho_root)


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_statements_match_answer_key(conn: FileConnector, answer_key: Path, company: str):
    stmts = build_statements(rebuild_trial_balances(conn, company), _truth(answer_key, company))
    diffs = {}
    for (month, code), amount in _expected(answer_key, company).items():
        s = stmts[month]
        got = s.balance_sheet.get(code, Decimal(0)) if code < "4000" else s.income.get(code, Decimal(0))
        if got != amount:
            diffs[(month, code)] = (got, amount)
    assert diffs == {}


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_balance_sheet_identity_and_cash_flow_tie_every_month(conn: FileConnector, answer_key: Path, company: str):
    stmts = build_statements(rebuild_trial_balances(conn, company), _truth(answer_key, company))
    assert all(s.balance_sheet_imbalance == 0 for s in stmts.values())  # CK-05
    months = sorted(stmts)
    for prev, cur in zip(months, months[1:]):  # CK-06: cash flow statement explains the change in cash
        cf = stmts[cur].cash_flow
        assert cf.operating + cf.investing + cf.financing == cf.change_in_cash
        assert cf.change_in_cash == stmts[cur].cash - stmts[prev].cash


def test_retained_earnings_include_unclosed_profit():
    from txg.normalise.trial_balance import TrialBalance
    tb = TrialBalance("EH-99", "2026-01", {"cash": Decimal(130), "re": Decimal(-100), "sales": Decimal(-30)},
                      {"cash": Decimal(30), "sales": Decimal(-30)})
    s = build_statements({"2026-01": tb}, {"cash": "1110", "re": "3300", "sales": "4100"})["2026-01"]
    assert s.balance_sheet["3300"] == Decimal(-130)
    assert s.income["4100"] == Decimal(30)
    assert s.net_profit == Decimal(30)
