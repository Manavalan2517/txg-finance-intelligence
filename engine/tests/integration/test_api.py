"""Task C8: the results API (C15, Appendix D.1). Screens read only from here (FR-12)."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from txg.api.app import create_app
from txg.api.service import EngineService
from txg.connector.files import FileConnector
from txg.normalise.trial_balance import TrialBalance
from txg.record.store import EventLog

CFO = {"X-TXG-Role": "cfo"}
CEO = {"X-TXG-Role": "ceo"}


def _mapping(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


@pytest.fixture(scope="module")
def api(zoho_root: Path, answer_key: Path, tmp_path_factory):
    log = EventLog(tmp_path_factory.mktemp("api") / "r.duckdb")
    service = EngineService(FileConnector(zoho_root), {c: _mapping(answer_key, c) for c in ("EH-01", "EH-21")}, log)
    return TestClient(create_app(service)), service, log


def test_companies_come_from_data(api):
    client, _, _ = api
    body = client.get("/companies", headers=CEO).json()
    assert {"EH-01", "EH-21"} <= {c["code"] for c in body}


@pytest.mark.slow
def test_kpis_follow_the_d1_contract(api, answer_key: Path):
    client, _, _ = api
    with open(answer_key / "EH-01" / "kpis_monthly.csv", encoding="utf-8", newline="") as f:
        want = next(float(r["HL-8_net_debt_to_ebitda_excl_leases"]) for r in csv.DictReader(f) if r["month"] == "2026-10")
    res = client.get("/companies/EH-01/kpis", params={"period": "2026-10"}, headers=CEO)
    assert res.status_code == 200
    by_id = {k["kpi_id"]: k for k in res.json()}
    hl8 = by_id["HL-8"]
    assert set(hl8) >= {"company", "period", "kpi_id", "name", "value", "unit", "state", "provisional"}
    assert hl8["company"] == "EH-01" and hl8["period"] == "2026-10" and hl8["state"] == "ok"
    assert abs(float(hl8["value"]) - want) < 0.0002
    assert hl8["provisional"] is False


def test_unknown_company_is_a_friendly_404(api):
    client, _, _ = api
    res = client.get("/companies/XX-99/kpis", params={"period": "2026-10"}, headers=CEO)
    assert res.status_code == 404 and res.json()["detail"] == "Unknown company XX-99"


def test_bad_period_is_rejected(api):
    client, _, _ = api
    assert client.get("/companies/EH-01/kpis", params={"period": "Oct 2026"}, headers=CEO).status_code == 422


def test_missing_role_is_refused(api):
    client, _, _ = api
    assert client.get("/companies").status_code == 401


@pytest.mark.slow
def test_integrity_page_is_cfo_only_and_every_view_is_logged(api):
    client, _, log = api
    assert client.get("/companies/EH-21/integrity", headers=CEO).status_code == 403
    res = client.get("/companies/EH-21/integrity", headers=CFO)
    assert res.status_code == 200 and res.json()["framing"] == "worth a look"
    assert [e.type for e in log.by_scope(company="EH-21")].count("integrity.viewed") == 1


def test_held_month_is_never_published(api):
    client, service, _ = api
    d = Decimal
    service.gate.evaluate(TrialBalance("EH-01", "2026-09", {"cash": d(1), "rev": d(-1)}),
                          printed=TrialBalance("EH-01", "2026-09", {"cash": d(2), "rev": d(-2)}))
    res = client.get("/companies/EH-01/kpis", params={"period": "2026-09"}, headers=CEO)
    assert res.status_code == 409
    assert res.json()["detail"]["held"] is True


def test_months_after_a_held_month_say_they_depend_on_it(api):
    """Runs after test_held_month_is_never_published, which holds EH-01 2026-09 in the shared service."""
    client, _, _ = api
    res = client.get("/companies/EH-01/kpis", params={"period": "2026-10"}, headers=CEO)
    assert res.status_code == 200
    assert all(k["depends_on_held_months"] == ["2026-09"] for k in res.json())


@pytest.mark.slow
def test_kpis_carry_status_and_trend_s1(api):
    """S1: EH-01 days late is outside its own normal range for 3+ months → act, and slipping (§10.3–10.4)."""
    client, _, _ = api
    by_id = {k["kpi_id"]: k for k in client.get("/companies/EH-01/kpis", params={"period": "2026-10"},
                                                 headers=CEO).json()}
    assert by_id["RC-1_days_late"]["status"] == "act" and by_id["RC-1_days_late"]["trend"] == "slipping"
    assert by_id["revenue_ltm"]["status"] == "context"
    assert all(k["status"] in {"healthy", "watch", "act", "context", "needs_data"} for k in by_id.values())


@pytest.mark.slow
def test_simulated_headlines_hl2_hl7(zoho_root: Path, answer_key: Path, tmp_path: Path):
    uploads = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"
    if not uploads.is_dir():
        pytest.skip("step-3 uploads not present")
    service = EngineService(FileConnector(zoho_root), {c: _mapping(answer_key, c) for c in ("EH-01", "EH-08")},
                            EventLog(tmp_path / "r.duckdb"), uploads_root=uploads)
    client = TestClient(create_app(service))
    eh08 = {k["kpi_id"]: k for k in client.get("/companies/EH-08/kpis", params={"period": "2026-10"}, headers=CEO).json()}
    assert float(eh08["HL-2"]["value"]) < 0.30 and eh08["HL-2"]["status"] == "act"      # S2: budget out of reach
    eh01 = {k["kpi_id"]: k for k in client.get("/companies/EH-01/kpis", params={"period": "2026-10"}, headers=CEO).json()}
    assert eh01["HL-7"]["unit"] == "SAR" and eh01["HL-7"]["status"] == "act"           # S1: below the SAR 40m minimum


@pytest.mark.slow
def test_cash_conversion_is_served_and_s1_is_act(api, answer_key: Path):
    client, _, _ = api
    body = client.get("/companies/EH-01/kpis", params={"period": "2026-10"}, headers=CEO).json()
    hl5 = next(k for k in body if k["kpi_id"] == "HL-5")
    with open(answer_key / "EH-01" / "kpis_monthly.csv", encoding="utf-8", newline="") as f:
        want = next(r for r in csv.DictReader(f) if r["month"] == "2026-10")["HL-5_cash_conversion_ltm"]
    assert round(Decimal(hl5["value"]), 4) == Decimal(want)  # −29% of EBITDA became cash
    assert hl5["status"] == "act"                              # S1: HL-5 act


@pytest.mark.slow
def test_trends_follow_the_group_false_alarm_limit(api):
    client, service, _ = api
    trends = service.group_trends("2026-10")
    assert {c for c, _ in trends} == {"EH-01", "EH-21"}              # one pool for the whole group
    tests = {**service.signal_tests("EH-01", "2026-10"), **service.signal_tests("EH-21", "2026-10")}
    from txg.stats.fdr import SignalTest, benjamini_hochberg
    pooled = [SignalTest(f"{c}|{k}|{i}", p) for (c, k), ps in tests.items() for i, p in enumerate(ps)]
    kept, _ = benjamini_hochberg(pooled)                              # §12.3 over the pooled tests, q = 10%
    assert sum(1 for t in trends.values() if t != "steady") == len({t.test_id.rsplit("|", 1)[0] for t in kept})
    body = client.get("/companies/EH-21/kpis", params={"period": "2026-10"}, headers=CEO).json()
    for k in body:
        if k["trend"] is not None:
            assert k["trend"] == trends.get(("EH-21", k["kpi_id"]), "steady")



@pytest.mark.slow
def test_a_measure_without_a_value_this_month_has_no_status_from_an_earlier_month(api):
    """Review fix: HL-5 is n.m. in EH-01's open month (EBITDA ≤ 0); it must not be graded on October's value."""
    _, service, _ = api
    assert service.kpis("EH-01", "2026-11") and next(
        v for v in service.kpis("EH-01", "2026-11") if v.kpi_id == "HL-5").value is None
    assert service.status_trend("EH-01", "2026-11")["HL-5"] == ("needs_data", None)
