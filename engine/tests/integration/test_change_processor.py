"""Task C7: real time. A change reaches the numbers by recomputing only what it affects (§6.3, FR-14, D-17).
Part B of the client's feed: S6 clears, S12's hold lifts, an edit lands in a locked month (IT-04, F-23)."""
import csv
import time
from decimal import Decimal
from pathlib import Path

import pytest

from txg.changes.processor import ChangeProcessor
from txg.connector.changefeed import ChangeFeed
from txg.connector.files import FileConnector
from txg.connector.overlay import OverlayConnector
from txg.ledger.intercompany import match_intercompany
from txg.record.store import EventLog

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"


def _mapping(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def _name_resolver(contact: dict, company) -> tuple[bool, str]:
    same = company.name.casefold().removesuffix(" (made-up)") in contact["contact_name"].casefold()
    return same, "name evidence (stand-in reader)"


@pytest.fixture()
def setup(zoho_root: Path, answer_key: Path, tmp_path: Path):
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    conn = OverlayConnector(FileConnector(zoho_root))
    mappings = {c: _mapping(answer_key, c) for c in ("EH-01", "EH-02", "EH-03", "EH-05", "EH-14", "EH-21")}
    proc = ChangeProcessor(conn, EventLog(tmp_path / "r.duckdb"), mappings, uploads_root=UPLOADS)
    part_b = [e for e in ChangeFeed(UPLOADS / "feed" / "changes.jsonl").events() if e.part == "B"]
    return conn, proc, part_b


def _ic_gap(conn) -> Decimal:
    pairs, _ = match_intercompany(conn, ["EH-02", "EH-05"], "2026-10", resolver=_name_resolver)
    return next(p.difference for p in pairs if p.creditor == "EH-05")


@pytest.mark.slow
def test_s6_mismatch_clears_when_the_missing_bill_is_booked(setup):
    conn, proc, part_b = setup
    assert _ic_gap(conn) > Decimal(1_000_000)
    proc.apply(next(e for e in part_b if e.org == "EH-02" and e.record_type == "bills"))
    assert abs(_ic_gap(conn)) <= Decimal("0.01")


@pytest.mark.slow
def test_s12_corrected_upload_lifts_the_hold(setup):
    _, proc, part_b = setup
    proc.close_month("EH-03", "2026-08", UPLOADS / "uploads" / "EH-03" / "trial_balances" / "trial_balance_2026-08.csv")
    assert proc.gate.status_of("EH-03", "2026-08").status == "held"
    result = proc.apply(next(e for e in part_b if e.op == "upload"))
    assert result.period_status == "tied"
    assert proc.gate.status_of("EH-03", "2026-08").status == "tied"


@pytest.mark.slow
def test_edit_in_a_locked_month_is_flagged(setup):
    _, proc, part_b = setup
    edits = [proc.apply(e) for e in part_b if e.org == "EH-21" and e.record_type == "journals"]
    assert any(r.after_close == "edited despite the lock" for r in edits)


@pytest.mark.slow
def test_only_affected_kpis_are_recomputed_and_fast(setup):
    conn, proc, part_b = setup
    event = next(e for e in part_b if e.org == "EH-01" and e.op == "update" and e.record_type == "invoices")
    started = time.perf_counter()
    result = proc.apply(event)
    elapsed = time.perf_counter() - started
    assert elapsed < 10                                     # §3.5: a change reaches the numbers within 10 s
    assert {"HL-3", "RC-1", "revenue_ltm"} <= result.kpis_recomputed
    assert "PY-2" not in result.kpis_recomputed             # bills-based KPIs are untouched by an invoice
    assert result.months == ["2026-11"] and result.provisional  # the open month: provisional until close
    assert result.values["revenue_ltm"].value is not None


@pytest.mark.slow
def test_an_invoice_change_recomputes_cash_conversion(setup):
    _, proc, part_b = setup
    event = next(e for e in part_b if e.org == "EH-01" and e.op == "update" and e.record_type == "invoices")
    result = proc.apply(event)
    assert "HL-5" in result.kpis_recomputed                 # EBITDA changed, so cash conversion is stale
    assert result.values["HL-5"].state != "needs_data"      # cash flows reached the recompute (Nov EBITDA ≤ 0 → n.m.)
