"""Quiet companies stay quiet on margins (§15.8: no act-level flag on the quiet majority without a cause), while S2's
early warning reads as the spec states it (EH-08 EBITDA margin healthy but slipping). Margins are 12-month figures, so their normal
range uses moving ranges between non-overlapping windows (registry "window": 12)."""
import csv
from pathlib import Path

import pytest

from txg.api.service import EngineService
from txg.connector.files import FileConnector
from txg.record.store import EventLog

MARGINS = ("HL-3", "PF-1", "PF-2", "PF-3", "PF-4")
QUIET_ON_MARGINS = ("EH-09", "EH-21")  # no planted margin story


def _mapping(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


@pytest.fixture(scope="module")
def service(zoho_root: Path, answer_key: Path, tmp_path_factory) -> EngineService:
    companies = ("EH-08", *QUIET_ON_MARGINS)
    return EngineService(FileConnector(zoho_root), {c: _mapping(answer_key, c) for c in companies},
                         EventLog(tmp_path_factory.mktemp("quiet") / "r.duckdb"))


@pytest.mark.slow
@pytest.mark.parametrize("company", QUIET_ON_MARGINS)
def test_quiet_companies_raise_no_margin_act(service: EngineService, company: str):
    st = service.status_trend(company, "2026-10")
    assert {k: st[k][0] for k in MARGINS if st[k][0] == "act"} == {}


@pytest.mark.slow
def test_s2_reads_as_the_spec_says_healthy_but_slipping(service: EngineService):
    """§15.4 S2: "HL-3 healthy but slipping (early warning)." The old month-to-month ranges showed act. ("PF-1 watch"
    is judged against peer bands, which do not exist yet; on its own normal range PF-1 reads healthy — a finding.)"""
    assert service.status_trend("EH-08", "2026-10")["HL-3"] == ("healthy", "slipping")
