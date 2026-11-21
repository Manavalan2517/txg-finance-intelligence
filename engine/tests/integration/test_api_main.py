"""The API entry point: builds mappings with the labelled stand-in readers and allows only the prototype's origin."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from txg.api.main import build_app


@pytest.mark.slow
def test_entry_point_maps_companies_and_allows_only_the_prototype_origin(zoho_root: Path, tmp_path: Path):
    app = build_app(zoho_root, tmp_path / "runtime", companies=["EH-21"])
    client = TestClient(app)
    ok = client.get("/companies", headers={"X-TXG-Role": "ceo", "Origin": "http://localhost:3000"})
    assert ok.status_code == 200 and [c["code"] for c in ok.json()] == ["EH-21"]
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = client.get("/companies", headers={"X-TXG-Role": "ceo", "Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


@pytest.mark.slow
def test_warm_up_builds_each_company_for_its_latest_closed_month(zoho_root: Path, tmp_path: Path):
    from txg.api.main import warm_up
    app = build_app(zoho_root, tmp_path / "runtime", companies=["EH-21"])
    service = app.state.service
    warm_up(service)
    period = service.closed_through("EH-21")
    assert ("EH-21", period, *service._data_key("EH-21")) in service._series_cache
    assert any(k[0] == period for k in service._trends)


@pytest.mark.slow
def test_entry_point_serves_live_books_with_printed_months_tied_before_serving(zoho_root: Path, tmp_path: Path,
                                                                                monkeypatch):
    monkeypatch.setenv("TXG_FEED_TOKEN", "abc")
    app = build_app(zoho_root, tmp_path / "runtime", companies=["EH-03"])
    service, live = app.state.service, app.state.live
    assert hasattr(service.conn, "version_of") and live.accepts("abc") and not live.accepts("")
    assert service.gate.status_of("EH-03", "2026-08").status == "held"  # S12, before the first request


@pytest.mark.slow
def test_entry_point_keeps_the_change_feed_off_without_a_token(zoho_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TXG_FEED_TOKEN", raising=False)
    app = build_app(zoho_root, tmp_path / "runtime", companies=["EH-21"])
    assert not app.state.live.accepts(None) and not app.state.live.accepts("")
