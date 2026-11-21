"""Phase E: the results API behind the prototype screens (§16.2, Appendix D.1). Screens read only from here (FR-12)."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from txg.api.app import create_app
from txg.api.service import EngineService
from txg.connector.files import FileConnector
from txg.mapping.store import MappingEntry, MappingStore
from txg.record.store import EventLog

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"
CEO, CFO, REVIEWER = {"X-TXG-Role": "ceo"}, {"X-TXG-Role": "cfo"}, {"X-TXG-Role": "reviewer"}
COMPANIES = ("EH-01", "EH-09", "EH-21")
MISC_INCOME = "460009000000030"  # EH-09 "Miscellaneous Income / إيرادات متنوعة" (S13)


def _rows(answer_key: Path, company: str) -> list[dict[str, str]]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _store(answer_key: Path, root: Path) -> MappingStore:
    """Mapping versions from the answer key, with S13's account as the readers would leave it: other income,
    unreviewed (the two readers disagreed)."""
    store = MappingStore(root)
    for company in COMPANIES:
        entries = {}
        for r in _rows(answer_key, company):
            disputed = r["account_id"] == MISC_INCOME
            entries[r["account_id"]] = MappingEntry(
                account_id=r["account_id"], account_name=r["account_name"], zoho_type=r["zoho_account_type"],
                std_code="4200" if disputed else r["standard_code"], confidence="medium" if disputed else "high",
                evidence=["answer key"], first_reading="4200" if disputed else r["standard_code"],
                second_reading="4100" if disputed else None, agreed=not disputed, unreviewed=disputed,
                effect_sar=Decimal(9_000_000) if disputed else Decimal(0))
        store.save(company, entries, Decimal(250_000), "test set-up")
    return store


@pytest.fixture(scope="module")
def api(zoho_root: Path, answer_key: Path, tmp_path_factory):
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    root = tmp_path_factory.mktemp("screens")
    store = _store(answer_key, root / "mappings")
    service = EngineService(FileConnector(zoho_root), {c: store.latest(c).codes() for c in COMPANIES},
                            EventLog(root / "r.duckdb"), uploads_root=UPLOADS, store=store)
    return TestClient(create_app(service)), service


@pytest.mark.slow
def test_group_grid_has_every_company_with_its_headline_measures(api):
    client, _ = api
    body = client.get("/group", params={"period": "2026-10"}, headers=CEO).json()
    assert [row["code"] for row in body] == list(COMPANIES)
    eh01 = next(row for row in body if row["code"] == "EH-01")
    ids = {k["kpi_id"] for k in eh01["kpis"]}
    assert {"HL-1_raw", "HL-3", "HL-5", "HL-6", "HL-8"} <= ids
    assert next(k for k in eh01["kpis"] if k["kpi_id"] == "HL-5")["status"] == "act"   # S1
    assert all(not row["held"] for row in body)


@pytest.mark.slow
def test_series_carries_the_normal_range(api):
    client, _ = api
    body = client.get("/companies/EH-01/series/RC-1_days_late", params={"period": "2026-10"}, headers=CEO).json()
    assert body["months"][-1] == "2026-10" and len(body["months"]) == len(body["values"])
    assert body["lower"] < body["centre"] < body["upper"]
    assert body["values"][-1] > body["upper"]                         # S1: days late above the normal range


def test_series_of_unknown_kpi_is_404(api):
    client, _ = api
    assert client.get("/companies/EH-01/series/NOPE", params={"period": "2026-10"}, headers=CEO).status_code == 404


@pytest.mark.slow
def test_cash13_fan_has_13_ordered_weeks(api):
    client, _ = api
    body = client.get("/companies/EH-01/cash13", params={"period": "2026-10"}, headers=CEO).json()
    assert len(body["weeks"]) == 13
    assert all(w["p10"] <= w["p50"] <= w["p90"] for w in body["weeks"])
    assert body["minimum"] == pytest.approx(40_000_000)
    assert body["chance_below_minimum"] >= 0.20                        # S1: HL-7 act


@pytest.mark.slow
def test_receivables_ageing_ties_to_the_ledger_and_concentration_is_ranked(api):
    client, service = api
    body = client.get("/companies/EH-01/receivables", params={"period": "2026-10"}, headers=CEO).json()
    total = sum(Decimal(b["sar"]) for b in body["ageing"])
    ar = service.context("EH-01").bs["2026-10"].get("1120", Decimal(0))
    assert abs(total - ar) <= Decimal(1)                               # open invoices = trade receivables
    shares = [c["share"] for c in body["customers"]]
    assert shares == sorted(shares, reverse=True) and 0 < sum(shares) <= 1.0001
    assert {"Not yet due", "1–30 days", "31–60 days", "61–90 days", "Over 90 days"} == {b["bucket"] for b in body["ageing"]}


@pytest.mark.slow
def test_integrity_shows_the_s7_findings(api):
    client, _ = api
    assert client.get("/companies/EH-21/integrity", headers=CEO).status_code == 403
    body = client.get("/companies/EH-21/integrity", headers=CFO).json()
    tests = {t["id"]: t for t in body["tests"]}
    assert tests["IT-02"]["flagged"] and tests["IT-02"]["limit"] == 50000      # bills bunched below the limit
    assert tests["IT-03"]["hits"] >= 30                                          # journals late into closed months
    assert tests["IT-06"]["hits"] >= 1                                           # Friday postings by a rare user
    assert len(body["benford"]) == 90 and body["benford"][0]["digits"] == 10
    assert body["back_dated"] and body["unusual"]


@pytest.mark.slow
def test_review_lists_the_disputed_account_first_and_an_override_makes_a_new_version(api):
    client, service = api
    assert client.get("/companies/EH-09/mappings", headers=CEO).status_code == 403
    body = client.get("/companies/EH-09/mappings", headers=REVIEWER).json()
    first = body["entries"][0]
    assert first["account_id"] == MISC_INCOME and first["unreviewed"]
    before = service.kpis("EH-09", "2026-10")
    revenue_before = next(v for v in before if v.kpi_id == "revenue_ltm").value
    res = client.post(f"/companies/EH-09/mappings/{MISC_INCOME}", headers=REVIEWER,
                      json={"std_code": "4100", "reason": "recurring service contracts (S13)"})
    assert res.status_code == 200, res.text
    assert res.json()["version"] == body["version"] + 1
    revenue_after = next(v for v in service.kpis("EH-09", "2026-10") if v.kpi_id == "revenue_ltm").value
    assert revenue_after > revenue_before                              # statements recomputed on the new version
    bad = client.post(f"/companies/EH-09/mappings/{MISC_INCOME}", headers=REVIEWER,
                      json={"std_code": "1110", "reason": "wrong"})
    assert bad.status_code == 422                                      # an income account cannot become cash


def test_acquisition_workspace_shows_the_verdict_and_the_namesake(api):
    client, _ = api
    body = client.get("/acquisition", headers=CEO).json()
    assert body["decision"]["verdict"].startswith("Buy at or below SAR")
    assert body["ask_ev"] == 520_000_000 and body["decision"]["walk_away_ev"] < 520_000_000
    assert len(body["peers"]) >= 5
    cand = {c["candidate_id"]: c for c in body["candidates"]}
    assert len(cand) == 29                                             # the delivered candidates.csv
    assert cand["CAND-01"]["identity"] == "namesake: different CR number"


def test_standard_chart_lists_codes_and_names(api):
    client, _ = api
    body = client.get("/standard-chart", headers=REVIEWER).json()
    codes = {r["code"]: r["name"] for r in body}
    assert len(codes) == 72 and codes["4100"].startswith("Revenue")


def test_cash13_is_never_published_for_a_held_month(api, monkeypatch):
    client, service = api
    from types import SimpleNamespace
    real = service.gate.status_of
    monkeypatch.setattr(service.gate, "status_of", lambda c, m: SimpleNamespace(status="held", reason="does not tie")
                        if (c, m) == ("EH-01", "2026-10") else real(c, m))
    assert client.get("/companies/EH-01/cash13", params={"period": "2026-10"}, headers=CEO).status_code == 409


@pytest.mark.slow
def test_a_context_built_before_an_override_is_never_served_after_it(api):
    """Review fix: a build that started on the old mapping and finishes after the override must not be reused."""
    client, service = api
    stale_key = service._context_key("EH-21")
    entry = service.mapping_version("EH-21").entries
    account = next(a for a, e in entry.items() if e.std_code == "6200")
    service.override_mapping("EH-21", account, "6200", "confirmed as is", person="reviewer")
    service._contexts[stale_key] = "STALE"                  # the late-finishing build lands under its old key
    assert service.context("EH-21") != "STALE"
    kinds = [e.type for e in service.log.by_scope(company="EH-21")]
    assert "mapping.overridden" in kinds


@pytest.mark.slow
def test_customer_sales_are_exact_decimal_strings(api):
    """Review fix: money stays Decimal end to end (sums in Decimal, sent as strings)."""
    client, service = api
    body = client.get("/companies/EH-01/receivables", params={"period": "2026-10"}, headers=CEO).json()
    assert all(isinstance(c["sales_sar"], str) for c in body["customers"])
    ctx = service.context("EH-01")
    top = body["customers"][0]
    want = sum((ctx.facts[m].customer_sales.get(top["customer_id"], Decimal(0)) for m in ctx.window("2026-10", 12)),
               Decimal(0))
    assert Decimal(top["sales_sar"]) == want.quantize(Decimal("0.01"))
    assert isinstance(body["customers_total_sar"], str)
