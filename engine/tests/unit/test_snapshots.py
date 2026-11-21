"""Task B1: snapshots are untouched, content-addressed copies (§7.3, C4)."""
import hashlib
from pathlib import Path

from txg.snapshots.store import SnapshotStore


def test_snapshot_hash_is_sha256_of_bytes(tmp_path: Path):
    payload = b'{"invoice_id":"1","total":115.0}'
    snap = SnapshotStore(tmp_path).put("files", "invoices", "EH-01", payload)
    assert snap.sha256 == hashlib.sha256(payload).hexdigest()
    assert snap.snapshot_id == f"snap_{snap.sha256}"


def test_snapshot_put_is_idempotent(tmp_path: Path):
    store = SnapshotStore(tmp_path)
    a = store.put("files", "invoices", "EH-01", b"same bytes")
    b = store.put("files", "invoices", "EH-01", b"same bytes")
    assert a.snapshot_id == b.snapshot_id
    assert len([p for p in tmp_path.rglob("*") if p.is_file() and p.suffix != ".json"]) == 1


def test_snapshot_round_trips_bytes_exactly(tmp_path: Path):
    payload = "البنك - الحساب الجاري".encode()
    store = SnapshotStore(tmp_path)
    assert store.get(store.put("files", "chartofaccounts", "EH-01", payload).snapshot_id) == payload


def test_snapshot_records_metadata(tmp_path: Path):
    snap = SnapshotStore(tmp_path).put("files", "bills", "EH-21", b"x")
    assert (snap.source, snap.record_type, snap.org) == ("files", "bills", "EH-21")
    assert snap.size == 1
