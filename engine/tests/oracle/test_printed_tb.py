"""CK-03 with the client's printed trial balances (step-3 uploads): every month ties to the halala except S12
(EH-03, August 2026, printed before the depreciation journal), which is held automatically (§7.4, §9.10)."""
import csv
import json
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.normalise.holds import PeriodGate
from txg.normalise.printed_tb import load_printed_tb, to_printed_basis
from txg.normalise.trial_balance import rebuild_trial_balances, tie_out
from txg.record.store import EventLog

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"
COMPANIES = ["EH-01", "EH-02", "EH-03", "EH-05", "EH-06", "EH-07", "EH-08", "EH-09", "EH-14", "EH-21"]


def _retained(answer_key: Path, company: str) -> set[str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"] for r in csv.DictReader(f) if r["standard_code"] == "3300"}


def _expected_ties(company: str) -> dict[str, bool]:
    rows = json.loads((UPLOADS / "answer-key-additions" / company / "trial_balance_ties.json").read_text())
    return {r["month"]: r["ties_to_books"] for r in rows}


@pytest.fixture(scope="module")
def conn(zoho_root: Path) -> FileConnector:
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    return FileConnector(zoho_root)


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_printed_trial_balances_tie_except_s12(conn: FileConnector, answer_key: Path, company: str):
    tbs = rebuild_trial_balances(conn, company)
    retained = _retained(answer_key, company)
    got = {}
    folder = UPLOADS / "uploads" / company / "trial_balances"
    for path in sorted(p for p in folder.glob("trial_balance_*.csv") if "corrected" not in p.stem):  # feed-only
        printed = load_printed_tb(path, conn, company)
        got[printed.month] = tie_out(to_printed_basis(conn, company, tbs, printed.month, retained), printed).tied
    assert got == _expected_ties(company)


@pytest.mark.slow
def test_s12_month_is_held_and_its_neighbours_are_tied(conn: FileConnector, answer_key: Path, tmp_path: Path):
    tbs = rebuild_trial_balances(conn, "EH-03")
    retained = _retained(answer_key, "EH-03")
    gate = PeriodGate(EventLog(tmp_path / "r.duckdb"))
    folder = UPLOADS / "uploads" / "EH-03" / "trial_balances"
    for month in ("2026-07", "2026-08", "2026-09"):
        printed = load_printed_tb(folder / f"trial_balance_{month}.csv", conn, "EH-03")
        gate.evaluate(to_printed_basis(conn, "EH-03", tbs, month, retained), printed, closed_through="2026-10")
    assert gate.status_of("EH-03", "2026-08").status == "held"
    assert gate.status_of("EH-03", "2026-07").status == "tied"
    assert gate.last_good_month("EH-03", before="2026-09") == "2026-07"
    # the corrected upload arrives through the change feed (seq 5450): it ties and the hold lifts by itself
    corrected = load_printed_tb(folder / "trial_balance_2026-08_corrected.csv", conn, "EH-03")
    status = gate.evaluate(to_printed_basis(conn, "EH-03", tbs, "2026-08", retained), corrected,
                           closed_through="2026-10")
    assert status.status == "tied"
    events = [e.type for e in gate._log.by_scope(company="EH-03", period="2026-08")]
    assert events[-2:] == ["tb.tied", "hold.released"]


def test_unknown_account_code_in_printed_tb_is_an_error(conn: FileConnector, tmp_path: Path):
    bad = tmp_path / "trial_balance_2026-01.csv"
    bad.write_text("X\nTrial Balance\nAs of 31/01/2026,Basis: Accrual\n\nAccount,Account Code,Account Type,"
                   "Net Debit,Net Credit\nMystery,999999,bank,1.00,\nTotal,,,1.00,0.00\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_printed_tb(bad, conn, "EH-03")
