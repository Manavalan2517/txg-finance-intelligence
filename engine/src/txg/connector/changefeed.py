"""The change feed (§15.6), in the client's format: one JSON object per line with `seq`, `ts` (Riyadh time),
`company`, `op` (create | update | upload), `record_type`, `id`, the full `record` in Zoho's format, its
general-ledger `postings` and `bank_lines`, and for updates the `before` record and `postings_before`.
Uploads (e.g. a corrected trial balance) carry `file` and `month` instead of a record."""
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from txg.connector.base import check_org

Op = Literal["create", "update", "upload"]
_OPS = ("create", "update", "upload")


@dataclass(frozen=True)
class ChangeEvent:
    seq: int
    at: datetime
    org: str
    op: Op
    record_type: str
    zoho_id: str
    part: str = ""
    record: dict[str, Any] = field(default_factory=dict, hash=False)
    before: dict[str, Any] | None = field(default=None, hash=False)
    postings: tuple[dict[str, Any], ...] = ()
    postings_before: tuple[dict[str, Any], ...] = ()
    bank_lines: tuple[dict[str, Any], ...] = ()
    file: str = ""
    month: str = ""


def parse_event(raw: dict[str, Any]) -> ChangeEvent:
    """One change in the client's feed format. Raises ValueError (or KeyError/TypeError) on a malformed event."""
    op = raw["op"]
    if op not in _OPS:
        raise ValueError(f"unknown change operation {op!r} at seq {raw.get('seq')}")
    if op != "upload" and not isinstance(raw.get("record"), dict):
        raise ValueError(f"change {raw.get('seq')} has no record")
    return ChangeEvent(
        seq=int(raw["seq"]), at=datetime.strptime(raw["ts"], "%Y-%m-%dT%H:%M:%S%z"), org=check_org(raw["company"]),
        op=op, record_type=raw["record_type"], zoho_id=str(raw["id"]), part=raw.get("part", ""),
        record=raw.get("record") or {}, before=raw.get("before"), postings=tuple(raw.get("postings") or ()),
        postings_before=tuple(raw.get("postings_before") or ()), bank_lines=tuple(raw.get("bank_lines") or ()),
        file=raw.get("file", ""), month=raw.get("month", ""))


class ChangeFeed:
    def __init__(self, path: Path):
        self._path = path

    def events(self) -> Iterator[ChangeEvent]:
        with open(self._path, encoding="utf-8") as f:
            parsed = [parse_event(json.loads(ln)) for ln in f if ln.strip()]
        yield from sorted(parsed, key=lambda e: e.seq)
