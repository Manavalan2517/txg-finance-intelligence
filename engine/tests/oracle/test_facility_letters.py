"""The facility letters are read from the PDFs themselves (§9.5): text extracted by code, terms read by the labelled
stand-in reader, every reading checked (CK-11 schedules; covenants read twice). On the delivered letters the readings
equal the structured terms delivered with the data, for every company. Instalments compare to the riyal: the letters
print whole riyals (EH-14: 2,916,666 and 2,916,667) where the structured file carries halalas; both sum to the
principal, and the letter is the legal document."""
from decimal import Decimal
from pathlib import Path

import pytest

from txg.uploads.facilities import FacilityTerms, load_recorded_facilities
from txg.uploads.facility_reader import load_facility_letters

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"
COMPANIES = ["EH-01", "EH-02", "EH-03", "EH-05", "EH-06", "EH-07", "EH-08", "EH-09", "EH-14", "EH-21"]


def _norm(terms: FacilityTerms) -> tuple:
    keys = ("facility", "type", "amount_sar", "limit_sar", "drawn", "margin_over_saibor")
    facilities = sorted(
        (tuple(None if f.get(k) is None else str(Decimal(str(f[k])).normalize()) if isinstance(f[k], float) else f[k]
               for k in keys),
         tuple(s["date"] for s in f.get("schedule") or []))
        for f in terms.facilities)
    covenants = sorted((c.name, c.test, c.threshold.normalize() if c.threshold is not None else None, c.frequency)
                       for c in terms.covenants)
    return facilities, covenants, dict(sorted(terms.definitions.items()))


@pytest.mark.parametrize("company", COMPANIES)
def test_pdf_readings_equal_the_delivered_terms(company: str):
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    read = load_facility_letters(UPLOADS / "uploads" / company / "facility_letters")
    recorded = load_recorded_facilities(UPLOADS / "answer-key-additions" / company / "facilities.json")
    assert _norm(read) == _norm(recorded)
    by_name = {f["facility"]: f.get("schedule") or [] for f in recorded.facilities}
    for f in read.facilities:
        pairs = zip(f.get("schedule") or [], by_name[f["facility"]], strict=True)
        assert all(abs(a["principal_sar"] - b["principal_sar"]) <= 1 for a, b in pairs)
    assert read.markers == () and "PDF" in read.source


def test_the_service_takes_facility_terms_from_the_letters(zoho_root: Path, tmp_path: Path):
    from txg.api.service import EngineService
    from txg.connector.files import FileConnector
    from txg.record.store import EventLog
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    service = EngineService(FileConnector(zoho_root), {"EH-01": {}}, EventLog(tmp_path / "r.duckdb"), uploads_root=UPLOADS)
    terms = service.facility_terms("EH-01")
    assert terms is not None and "PDF" in terms.source
    assert {c.test for c in terms.covenants} == {"net_debt_to_ebitda_max", "dscr_min", "cash_plus_undrawn_min"}
