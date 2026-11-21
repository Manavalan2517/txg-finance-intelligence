"""S7 (EH-21): bills bunched below the SAR 50,000 approval limit, ~40 journals entered 30+ days late into closed
months, and Friday postings by a rarely-posting user — "worth a look", CFO only (§11.5 IT-01/02/03/06)."""
import json
import math
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.integrity.tests import back_dated, benford_first_two, bunching_below_limit, unusual_postings

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"


def _limit(company: str) -> float:
    return json.loads((UPLOADS / "uploads" / company / "settings.json").read_text())["approval_limit_sar"]


def test_benford_on_benford_distributed_amounts_conforms():
    amounts = [10 ** (1 + (i + 0.5) / 20000 * 4) for i in range(20000)]  # log-uniform over 4 decades
    result = benford_first_two(amounts)
    assert result.suitable and result.mad < 0.0012


def test_benford_refuses_small_populations():
    assert not benford_first_two([123.0] * 999).suitable


def test_bunching_hand_example():
    amounts = [49_000.0] * 30 + [51_000.0] * 10
    hit = bunching_below_limit(amounts, 50_000)
    assert (hit.below, hit.above) == (30, 10)
    assert hit.p == pytest.approx(sum(math.comb(40, i) for i in range(30, 41)) / 2 ** 40)


def test_late_entry_into_an_open_month_is_not_back_dating(tmp_path: Path):
    folder = tmp_path / "EH-99"
    folder.mkdir()
    journals = [{"journal_id": str(i), "journal_date": "2026-01-10", "created_time": "2026-01-11T09:00:00+0300",
                 "created_by_id": "u1"} for i in range(40)]
    journals += [{"journal_id": "late-open", "journal_date": "2026-03-01", "created_time": "2026-04-20T09:00:00+0300",
                  "created_by_id": "u1"},
                 {"journal_id": "late-closed", "journal_date": "2026-01-05", "created_time": "2026-03-20T09:00:00+0300",
                  "created_by_id": "u1"}]
    locks = [{"lock_date": "2026-01-31", "locked_on": "2026-02-08", "module": "all", "reason": "close"}]
    (folder / "journals.json").write_text(json.dumps({"code": 0, "journals": journals}), encoding="utf-8")
    (folder / "transactionlocks.json").write_text(json.dumps({"code": 0, "transaction_locks": locks}), encoding="utf-8")
    hits = back_dated(FileConnector(tmp_path), "EH-99", "journals")
    assert [h.record_id for h in hits] == ["late-closed"]


@pytest.fixture(scope="module")
def conn(zoho_root: Path) -> FileConnector:
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    return FileConnector(zoho_root)


def _bill_totals(conn: FileConnector, company: str) -> list[float]:
    return [r.data["total"] * (r.data.get("exchange_rate") or 1) for r in conn.iter_records(company, "bills")]


@pytest.mark.slow
def test_s7_bills_bunch_below_the_approval_limit(conn: FileConnector):
    hit = bunching_below_limit(_bill_totals(conn, "EH-21"), _limit("EH-21"))
    assert hit.flagged and hit.p < 0.001
    quiet = bunching_below_limit(_bill_totals(conn, "EH-05"), _limit("EH-05"))
    assert not quiet.flagged


@pytest.mark.slow
def test_s7_benford_nonconformity_on_bills(conn: FileConnector):
    assert benford_first_two(_bill_totals(conn, "EH-21")).mad > 0.0022


@pytest.mark.slow
def test_s7_back_dated_journals_into_closed_months(conn: FileConnector):
    hits = back_dated(conn, "EH-21", "journals")
    assert sum(1 for h in hits if h.lag_days >= 30) >= 40
    assert all(h.into_closed_month for h in hits)


@pytest.mark.slow
def test_s7_friday_postings_by_a_rare_user(conn: FileConnector):
    hits = unusual_postings(conn, "EH-21")
    by_user = {}
    for h in hits:
        by_user[h.user_id] = by_user.get(h.user_id, 0) + 1
    assert max(by_user.values()) >= 25
    assert all(h.reason in {"weekend", "late night"} for h in hits)
