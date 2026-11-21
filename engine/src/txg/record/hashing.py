"""Content hashing used by snapshots, replay checks and the data-set integrity test."""
import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    """Stable bytes for a JSON value: sorted keys, no whitespace, UTF-8 kept as-is (Arabic stays readable)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
