"""Fault injection (§18.3) for faults that had no test of their own. The full map from every fault ID to the tests
that exercise it is tests/faults/matrix.py, checked by test_fault_matrix.py."""
import csv
import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from txg.acquisition.valuation import Target, price_refusal
from txg.api.app import create_app
from txg.api.live import LiveFeed
from txg.api.service import EngineService
from txg.changes.processor import ChangeProcessor
from txg.connector.changefeed import parse_event
from txg.connector.files import FileConnector
from txg.connector.overlay import OverlayConnector
from txg.record.store import EventLog
from txg.stats.calendar import MissingHolidayYear, holiday_shares, load_holidays
from txg.stats.holiday import fit_holiday_model

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"
BALANCED_YEAR = {"assets": {"Cash and cash equivalents": 10.0, "Other": 90.0}, "liabilities": {"Loans": 40.0},
                 "equity": {"Capital": 60.0}, "ebitda": 20.0}


def _raw(seq: int) -> dict:
    with open(UPLOADS / "feed" / "changes.jsonl", encoding="utf-8") as f:
        return next(e for e in map(json.loads, f) if e["seq"] == seq)


def _mapping(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


# F-14 ------------------------------------------------------------------------------------------------------------
def test_f14_a_missing_holiday_year_is_refused_never_a_silent_zero():
    full = load_holidays()
    cal = full | {"years": {y: v for y, v in full["years"].items() if y != "2026"}}
    with pytest.raises(MissingHolidayYear):
        holiday_shares(cal, "2026-03")
    series = {f"{y}-{m:02d}": 100.0 + m for y in (2024, 2025, 2026) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-10"}
    with pytest.raises(MissingHolidayYear):
        fit_holiday_model(series, cal)


# F-15, F-16 ------------------------------------------------------------------------------------------------------
def _target(checks_passed: bool = True) -> Target:
    return Target("TGT-01", "Example Cold Chain Co.", "TEST-CR-T001", {"2025": BALANCED_YEAR}, checks_passed)


def test_f15_a_target_whose_statements_do_not_foot_gets_no_price():
    reason = price_refusal(_target(checks_passed=False), offered_cr="TEST-CR-T001")
    assert reason is not None and "CK-20" in reason


def test_f16_a_namesake_offered_as_the_target_gets_no_price():
    """CAND-01 has the target's name but its own CR number: offered for pricing as the target, it gets no price."""
    reason = price_refusal(_target(), offered_cr="TEST-CR-C001")
    assert reason is not None and "namesake" in reason


def test_the_named_target_with_footing_statements_is_priced_even_with_a_namesake_in_the_universe():
    assert price_refusal(_target(), offered_cr="TEST-CR-T001") is None


# F-17 (prototype intake) -------------------------------------------------------------------------------------------
def test_f17_a_change_with_a_bad_token_is_discarded_and_logged(zoho_root: Path, tmp_path: Path, caplog):
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    service = EngineService(OverlayConnector(FileConnector(zoho_root)), {"EH-01": {}}, EventLog(tmp_path / "r.duckdb"),
                            uploads_root=UPLOADS)
    client = TestClient(create_app(service, live=LiveFeed(service, token="right")))
    with caplog.at_level(logging.WARNING, logger="txg.api"):
        assert client.post("/changes", params={"token": "forged"}, json=_raw(5444)).status_code == 403
    assert service.conn.version_of("EH-01") == 0
    assert any("refused a change with a bad feed token" in r.getMessage() for r in caplog.records)


# F-23 -------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def eh21(zoho_root: Path, answer_key: Path, tmp_path: Path):
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    conn = OverlayConnector(FileConnector(zoho_root))
    return ChangeProcessor(conn, EventLog(tmp_path / "r.duckdb"), {"EH-21": _mapping(answer_key, "EH-21")},
                           uploads_root=UPLOADS)


@pytest.mark.slow
def test_f23_an_edit_in_a_closed_month_re_checks_that_month(eh21: ChangeProcessor):
    event = parse_event(_raw(5454))
    month = min(p["date"] for p in event.postings)[:7]
    result = eh21.apply(event)
    assert result.after_close in ("edited after close", "edited despite the lock")
    status = eh21.gate.status_of("EH-21", month)
    assert status.status == "closed" and status.tie_source == "none"  # balanced; Zoho's fresh report not yet tied
    types = [e.type for e in eh21.log.by_scope(company="EH-21", period=month)]
    assert types[-1] == "tb.balanced"


@pytest.mark.slow
def test_f23_an_edit_that_unbalances_a_closed_month_holds_it(eh21: ChangeProcessor):
    raw = _raw(5454)
    broken = raw | {"postings": [dict(raw["postings"][0], debit="1.00", credit="0")] + raw["postings"][1:]}
    event = parse_event(broken)
    month = min(p["date"] for p in event.postings)[:7]
    assert replace(event).postings != parse_event(raw).postings
    eh21.apply(event)
    assert eh21.gate.status_of("EH-21", month).status == "held"


# F-13 ------------------------------------------------------------------------------------------------------------
def test_f13_fewer_than_five_peers_are_refused_by_ck17():
    from txg.acquisition.valuation import MIN_PEERS, peer_multiples
    peer = {"share_price_sar": 10.0, "shares_outstanding": 1e6, "net_debt_excl_leases_sar": 0.0,
            "statements": {"2025": {"ebitda": 1e6}}}
    assert len(peer_multiples([peer] * MIN_PEERS)) == MIN_PEERS
    with pytest.raises(ValueError, match="CK-17"):
        peer_multiples([peer] * (MIN_PEERS - 1))
