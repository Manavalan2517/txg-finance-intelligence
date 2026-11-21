"""Content-addressed snapshot store (C4): every record stored exactly as received, with its hash."""
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from txg.record.hashing import sha256_bytes


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot_id: str
    sha256: str
    source: str
    record_type: str
    org: str
    size: int
    stored_at: datetime


def _sha_of(snapshot_id: str) -> str:
    sha = snapshot_id.removeprefix("snap_")
    if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
        raise ValueError("invalid snapshot id")
    return sha


class SnapshotStore:
    def __init__(self, root: Path):
        self._root = root
        root.mkdir(parents=True, exist_ok=True)

    def _blob(self, sha: str) -> Path:
        return self._root / sha[:2] / sha

    def put(self, source: str, record_type: str, org: str, payload: bytes) -> Snapshot:
        sha = sha256_bytes(payload)
        blob = self._blob(sha)
        meta_path = blob.with_suffix(".json")
        if meta_path.exists():
            return Snapshot.model_validate_json(meta_path.read_text(encoding="utf-8"))
        blob.parent.mkdir(parents=True, exist_ok=True)
        tmp = blob.with_suffix(".tmp")
        tmp.write_bytes(payload)
        tmp.replace(blob)
        snap = Snapshot(snapshot_id=f"snap_{sha}", sha256=sha, source=source, record_type=record_type, org=org,
                        size=len(payload), stored_at=datetime.now(UTC))
        meta_path.write_text(snap.model_dump_json(), encoding="utf-8")
        return snap

    def get(self, snapshot_id: str) -> bytes:
        return self._blob(_sha_of(snapshot_id)).read_bytes()

    def meta(self, snapshot_id: str) -> Snapshot:
        path = self._blob(_sha_of(snapshot_id)).with_suffix(".json")
        return Snapshot.model_validate_json(path.read_text(encoding="utf-8"))
