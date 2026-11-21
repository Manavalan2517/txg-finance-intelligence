"""Task B5: account mapping to the standard chart, checked by code and applied automatically (§9.3, CK-04/05)."""
import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.ledger.chart import load_standard_chart
from txg.mapping.briefs import build_briefs, render_brief
from txg.mapping.runner import map_company, mapping_accuracy
from txg.mapping.standins import first_reader, second_reader
from txg.mapping.store import MappingStore
from txg.modelsteps.client import ScriptedClient
from txg.normalise.mapping_checks import check_mapping, proposal_checks
from txg.normalise.trial_balance import rebuild_trial_balances

COMPANIES = ["EH-01", "EH-02", "EH-03", "EH-05", "EH-06", "EH-07", "EH-08", "EH-09", "EH-14", "EH-21"]


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


@pytest.fixture(scope="module")
def conn(zoho_root: Path) -> FileConnector:
    return FileConnector(zoho_root)


def test_standard_chart_has_appendix_c_accounts():
    chart = load_standard_chart()
    assert len(chart) == 72  # Appendix C lists 72 standard accounts
    assert chart["1120"].name == "Trade receivables" and chart["1120"].cls == "asset"
    assert chart["1135"].contra and chart["7600"].role == "tax"


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_answer_key_mapping_passes_all_checks(conn: FileConnector, answer_key: Path, company: str):
    """The true mapping must not trip any check: no false findings."""
    tbs = rebuild_trial_balances(conn, company)
    assert check_mapping(conn, company, tbs, _truth(answer_key, company)) == []


@pytest.mark.slow
def test_every_account_with_balance_mapped(conn: FileConnector, answer_key: Path):
    truth = _truth(answer_key, "EH-01")
    dropped = next(acc for acc, code in truth.items() if code == "1120")
    partial = {k: v for k, v in truth.items() if k != dropped}
    findings = check_mapping(conn, "EH-01", rebuild_trial_balances(conn, "EH-01"), partial)
    assert [(f.check, f.account_id) for f in findings] == [("CK-04", dropped)]


def test_revenue_mapped_to_asset_is_a_finding(conn: FileConnector):
    assert proposal_checks(zoho_type="income", std_code="1120")
    assert proposal_checks(zoho_type="income", std_code="4100") == []
    assert proposal_checks(zoho_type="bank", std_code="9999") == ["9999 is not in the standard chart"]


@pytest.mark.slow
def test_brief_carries_evidence_but_no_personal_names(conn: FileConnector):
    briefs = build_briefs(conn, "EH-01", rebuild_trial_balances(conn, "EH-01"), as_of="2026-10")
    text = "\n".join(render_brief(b) for b in briefs)
    assert "Sara Al-Mutairi" not in text and "Faisal Al-Rashidi" not in text
    one = next(b for b in briefs if b.zoho_type == "accounts_receivable")
    assert len(one.monthly_closing) == 24 and one.counterpart_types


@pytest.mark.slow
def test_mapping_with_stand_ins_reaches_accuracy_floor(conn: FileConnector, answer_key: Path, tmp_path: Path):
    """Labelled stand-ins (§9.9) must map at least 95% of material balance correctly; the report is written."""
    report = {}
    for company in COMPANIES:
        version = map_company(conn, company, ScriptedClient(first_reader), ScriptedClient(second_reader),
                              MappingStore(tmp_path / "mappings"), as_of="2026-10")
        report[company] = mapping_accuracy(conn, company, version, _truth(answer_key, company))
    (tmp_path / "accuracy.json").write_text(json.dumps({k: str(v) for k, v in report.items()}, indent=1))
    low = {c: a for c, a in report.items() if a < Decimal("0.95")}
    assert low == {}, f"stand-in accuracy below floor: {low}"


@pytest.mark.slow
def test_override_creates_version_and_recomputes(conn: FileConnector, tmp_path: Path):
    store = MappingStore(tmp_path / "mappings")
    v1 = map_company(conn, "EH-02", ScriptedClient(first_reader), ScriptedClient(second_reader), store,
                     as_of="2026-10")
    acc = next(a for a, e in v1.entries.items() if e.zoho_type == "expense" and e.std_code != "6900")
    v2 = store.override("EH-02", acc, "6900", reason="reviewer: belongs in other opex", person="cfo@example")
    assert v2.version == v1.version + 1 and v2.entries[acc].std_code == "6900"
    assert v2.entries[acc].reviewed_by == "cfo@example"
    assert store.get("EH-02", v1.version).entries[acc] == v1.entries[acc]  # both versions stay on the record
    assert store.latest("EH-02").version == v2.version


@pytest.mark.slow
def test_pipeline_maps_every_account_with_a_balance_in_any_month(conn: FileConnector, tmp_path: Path):
    """Regression (found in the live prototype): accounts active only before the 24-month window or only in the
    open month were skipped, so statements refused the mapping (CK-04)."""
    version = map_company(conn, "EH-01", ScriptedClient(first_reader), ScriptedClient(second_reader),
                          MappingStore(tmp_path), as_of="2026-10")
    tbs = rebuild_trial_balances(conn, "EH-01")
    active = {a for tb in tbs.values() for a, v in {**tb.balances, **tb.movements}.items() if v}
    assert active <= set(version.entries)
