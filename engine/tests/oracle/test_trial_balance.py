"""Task B3: rebuild the trial balance from the account registers and check it against the answer key (§7.4)."""
import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.normalise.trial_balance import rebuild_trial_balances, subledger_vs_control

COMPANIES = ["EH-01", "EH-02", "EH-03", "EH-05", "EH-06", "EH-07", "EH-08", "EH-09", "EH-14", "EH-21"]


def _answer_statements(answer_key: Path, company: str) -> dict[tuple[str, str], Decimal]:
    with open(answer_key / company / "monthly_statements.csv", encoding="utf-8", newline="") as f:
        return {(r["month"], r["standard_code"]): Decimal(r["amount_sar"])
                for r in csv.DictReader(f) if r["status"] == "closed"}


def _answer_mapping(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


@pytest.fixture(scope="module")
def conn(zoho_root: Path) -> FileConnector:
    return FileConnector(zoho_root)


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_tb_balances_every_month_all_companies(conn: FileConnector, company: str):
    tbs = rebuild_trial_balances(conn, company)
    assert "2023-01" in tbs and "2026-10" in tbs
    unbalanced = {m: tb.imbalance for m, tb in tbs.items() if not tb.is_balanced}
    assert unbalanced == {}


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_tb_matches_answer_key_balance_sheet_lines(conn: FileConnector, answer_key: Path, company: str):
    """Closing balances grouped by the true standard account equal the answer key, to SAR 0.00.

    Retained earnings (3300) is excluded here: the answer key rolls unclosed profit into it, which is the
    statements builder's job (Task B6), not the trial balance's.
    """
    expected = _answer_statements(answer_key, company)
    mapping = _answer_mapping(answer_key, company)
    tbs = rebuild_trial_balances(conn, company)
    diffs = {}
    for (month, code), amount in expected.items():
        if code >= "4000" or code == "3300":
            continue
        got = sum((bal for acc, bal in tbs[month].balances.items() if mapping[acc] == code), Decimal(0))
        if got != amount:
            diffs[(month, code)] = (got, amount)
    assert diffs == {}


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_monthly_movements_match_answer_key_income_statement(conn: FileConnector, answer_key: Path,
                                                             company: str):
    expected = _answer_statements(answer_key, company)
    mapping = _answer_mapping(answer_key, company)
    tbs = rebuild_trial_balances(conn, company)
    diffs = {}
    for (month, code), amount in expected.items():
        if code < "4000":
            continue
        movement = defaultdict(Decimal)
        for acc, mv in tbs[month].movements.items():
            movement[mapping[acc]] += mv
        got = -movement[code]  # income statement is credit positive
        if got != amount:
            diffs[(month, code)] = (got, amount)
    assert diffs == {}


@pytest.mark.slow
@pytest.mark.parametrize("company", ["EH-01", "EH-08"])
def test_fx_and_go_live_balances_in_subledger(conn: FileConnector, company: str):
    """CK-07 at the data cut-off: open invoices and bills (in SAR, incl. go-live balances) equal control accounts.

    EH-08 buys in EUR and USD, so its bills only tie when converted at each bill's exchange rate.
    """
    findings = subledger_vs_control(conn, company)
    assert findings == []
