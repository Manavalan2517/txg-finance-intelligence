"""Task B2: one connector interface over Zoho-format files, plus the change feed (§7.3, §15.6, D-16)."""
import json
from pathlib import Path

import pytest

from txg.connector.base import Connector, RecordNotFound
from txg.connector.changefeed import ChangeEvent, ChangeFeed
from txg.connector.files import FileConnector

MANIFEST_TYPES = ["contacts", "projects", "invoices", "customerpayments", "bills", "vendorpayments",
                  "expenses", "journals", "banktransactions"]


def _write_envelope(folder: Path, record_type: str, key: str, records: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    body = {"code": 0, "message": "success", key: records}
    (folder / f"{record_type}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def test_file_connector_satisfies_protocol(zoho_root: Path):
    assert isinstance(FileConnector(zoho_root), Connector)


def test_organisations_lists_companies_with_identifiers(zoho_root: Path):
    orgs = {o.company: o for o in FileConnector(zoho_root).organisations()}
    assert {"EH-01", "EH-02", "EH-21"} <= set(orgs)
    eh01 = orgs["EH-01"]
    assert eh01.organization_id == "700000001"
    assert eh01.vat_number == "TEST-VAT-0001"
    assert eh01.cr_number == "TEST-CR-0001"
    assert eh01.currency == "SAR" and eh01.time_zone == "Asia/Riyadh"


@pytest.mark.parametrize("record_type", MANIFEST_TYPES)
def test_iter_records_counts_match_manifest(zoho_root: Path, record_type: str):
    manifest = json.loads((zoho_root / "EH-01" / "manifest.json").read_text())
    got = sum(1 for _ in FileConnector(zoho_root).iter_records("EH-01", record_type))
    assert got == manifest["counts"][record_type]


def test_records_carry_zoho_id_and_type(zoho_root: Path):
    rec = next(iter(FileConnector(zoho_root).iter_records("EH-01", "invoices")))
    assert rec.record_type == "invoices" and rec.org == "EH-01"
    assert rec.zoho_id == rec.data["invoice_id"]


def test_records_deduplicated_by_zoho_id(tmp_path: Path):
    _write_envelope(tmp_path / "EH-99", "invoices", "invoices",
                    [{"invoice_id": "1", "total": 10}, {"invoice_id": "1", "total": 10}, {"invoice_id": "2"}])
    ids = [r.zoho_id for r in FileConnector(tmp_path).iter_records("EH-99", "invoices")]
    assert ids == ["1", "2"]


def test_missing_record_type_yields_nothing(tmp_path: Path):
    (tmp_path / "EH-99").mkdir()
    assert list(FileConnector(tmp_path).iter_records("EH-99", "salesreceipts")) == []


def test_unknown_record_type_is_rejected(zoho_root: Path):
    with pytest.raises(ValueError):
        list(FileConnector(zoho_root).iter_records("EH-01", "payroll_secrets"))


def test_fetch_one_record_by_id(zoho_root: Path):
    conn = FileConnector(zoho_root)
    first = next(iter(conn.iter_records("EH-01", "bills")))
    assert conn.fetch("EH-01", "bills", first.zoho_id).data == first.data
    with pytest.raises(RecordNotFound):
        conn.fetch("EH-01", "bills", "does-not-exist")


def test_singleton_objects_are_single_records(zoho_root: Path):
    conn = FileConnector(zoho_root)
    org = list(conn.iter_records("EH-01", "organization"))
    ob = list(conn.iter_records("EH-01", "openingbalances"))
    assert len(org) == 1 and org[0].zoho_id == "700000001"
    assert len(ob) == 1 and ob[0].data["date"] == "2023-01-01"


def test_ledger_lines_read_from_account_registers(zoho_root: Path):
    lines = list(FileConnector(zoho_root).iter_ledger_lines("EH-01"))
    assert lines[0].transaction_type == "opening_balance"
    assert sum(ln.debit for ln in lines) == sum(ln.credit for ln in lines)


def test_normalise_keeps_arabic_names_byte_exact(zoho_root: Path):
    names = {r.data["account_name"] for r in FileConnector(zoho_root).iter_records("EH-01", "chartofaccounts")}
    assert "البنك - الحساب الجاري" in names


def test_connector_has_no_write_methods():
    public = {n for n in dir(FileConnector) if not n.startswith("_")}
    assert not {n for n in public if n.split("_")[0] in {"create", "update", "delete", "write", "put", "post"}}


def test_change_feed_reads_the_clients_format_in_sequence_order(tmp_path: Path):
    feed = tmp_path / "changes.jsonl"
    rows = [
        {"seq": 2, "ts": "2026-11-12T09:00:00+0300", "company": "EH-01", "op": "update", "record_type": "invoices",
         "id": "9", "part": "B", "record": {"invoice_id": "9", "total": 1}, "before": {"invoice_id": "9", "total": 2},
         "postings": [{"account_id": "a", "debit": 1.0, "credit": 0.0}]},
        {"seq": 1, "ts": "2026-11-10T09:00:00+0300", "company": "EH-03", "op": "upload", "record_type": "trial_balance",
         "id": "tb-2026-08-corrected", "part": "B", "month": "2026-08", "file": "uploads/x.csv"},
    ]
    feed.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    events = list(ChangeFeed(feed).events())
    assert [e.seq for e in events] == [1, 2]
    upload, update = events
    assert isinstance(upload, ChangeEvent) and upload.op == "upload" and upload.file == "uploads/x.csv"
    assert upload.month == "2026-08" and upload.record == {}
    assert update.zoho_id == "9" and update.before == {"invoice_id": "9", "total": 2} and len(update.postings) == 1


def test_change_feed_rejects_unknown_operations(tmp_path: Path):
    feed = tmp_path / "changes.jsonl"
    feed.write_text(json.dumps({"seq": 1, "ts": "2026-11-10T09:00:00+0300", "company": "EH-01", "op": "drop",
                                "record_type": "invoices", "id": "1", "record": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        list(ChangeFeed(feed).events())


@pytest.mark.slow
def test_real_change_feed_parses_completely():
    path = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20" / "feed" / "changes.jsonl"
    if not path.is_file():
        pytest.skip("step-3 feed not present")
    events = list(ChangeFeed(path).events())
    assert len(events) == 5454
    assert [e.seq for e in events] == sorted(e.seq for e in events)
    assert sum(e.part == "B" for e in events) == 12
