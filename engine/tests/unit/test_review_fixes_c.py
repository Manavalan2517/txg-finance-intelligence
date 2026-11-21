"""Regression tests for the Phase C review findings."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from txg.changes.processor import ChangeProcessor
from txg.connector.changefeed import ChangeEvent
from txg.kpi.facts import customer_sales
from txg.kpi.forecast_record import forecast_record
from txg.stats.cash13 import principal_in_horizon
from txg.stats.covenants import covenant_results
from txg.uploads.facilities import Covenant, FacilityTerms


def test_principal_between_month_end_and_first_sunday_is_kept():
    terms = FacilityTerms(({"type": "term_loan", "amount_sar": 10.0,
                            "schedule": [{"date": "2025-02-01", "principal_sar": 10.0}]},), ())
    got = principal_in_horizon(terms, t0=date(2025, 1, 31), end=date(2025, 5, 4))
    assert got == [(date(2025, 2, 1), Decimal(10))]


def test_customer_sales_convert_currency_and_skip_pre_go_live_credit_notes():
    invoices = [{"date": "2026-01-10", "customer_id": "c1", "sub_total": 100, "exchange_rate": 3.75},
                {"date": "2022-12-10", "customer_id": "c1", "sub_total": 999, "exchange_rate": 1}]
    credits = [{"date": "2022-12-20", "customer_id": "c1", "sub_total": 50, "exchange_rate": 1},
               {"date": "2026-01-20", "customer_id": "c1", "sub_total": 10, "exchange_rate": 3.75}]
    got = customer_sales(invoices, credits, go_live=date(2023, 1, 1))
    assert got == {"2026-01": {"c1": Decimal("337.50")}}


def test_upload_outside_the_uploads_folder_is_refused(tmp_path: Path):
    proc = ChangeProcessor(conn=None, log=None, mappings={}, uploads_root=tmp_path)  # type: ignore[arg-type]
    event = ChangeEvent(seq=1, at=None, org="EH-03", op="upload", record_type="trial_balance",  # type: ignore[arg-type]
                        zoho_id="x", file="../../etc/passwd", month="2026-08")
    with pytest.raises(ValueError):
        proc.upload_path(event)


def test_upload_month_must_match_the_report(tmp_path: Path):
    from txg.changes.processor import check_upload_month
    with pytest.raises(ValueError):
        check_upload_month(event_month="2026-08", report_month="2026-09")


def test_covenant_without_a_threshold_is_reported_not_crashed():
    ctx = SimpleNamespace(bs={"2026-10": {}}, months=["2026-10"])
    terms = FacilityTerms((), (Covenant("Leverage", "net_debt_to_ebitda_max", None, "quarterly"),))
    [result] = covenant_results(ctx, "2026-10", terms)  # type: ignore[arg-type]
    assert result.passed is None and "threshold" in result.note


def test_sign_test_follows_the_spec_one_sided_on_over_forecasts():
    under = forecast_record([Decimal("-0.10")] * 7 + [Decimal("0.02")])  # budgets too low, not optimism
    assert under.over == 1 and under.status == "healthy"


def test_service_context_is_rebuilt_after_a_change(monkeypatch):
    import txg.api.service as service_mod
    calls = []
    monkeypatch.setattr(service_mod, "rebuild_trial_balances", lambda conn, c: {})
    monkeypatch.setattr(service_mod, "build_month_facts", lambda conn, c: {})
    monkeypatch.setattr(service_mod, "build_cash_flows", lambda conn, c, m: {})
    monkeypatch.setattr(service_mod, "build_context", lambda *a, **k: calls.append(1) or object())
    conn = SimpleNamespace(version=0)
    svc = service_mod.EngineService(conn, {"EH-01": {}}, log=None)  # type: ignore[arg-type]
    svc.context("EH-01")
    svc.context("EH-01")
    conn.version = 1
    svc.context("EH-01")
    assert len(calls) == 2


def test_mapping_store_never_overwrites_an_existing_version(tmp_path, monkeypatch):
    """Review fix: two overrides built on the same version must not both write v(N+1)."""
    from decimal import Decimal

    import pytest

    from txg.mapping.store import MappingStore, VersionConflict
    store = MappingStore(tmp_path)
    store.save("EH-01", {}, Decimal(0), "first")
    monkeypatch.setattr(store, "_versions", lambda company: [])      # a second writer that read the old state
    with pytest.raises(VersionConflict):
        store.save("EH-01", {}, Decimal(0), "second")
    assert store.get("EH-01", 1).reason == "first"                   # v1 untouched
