"""Live state = the books plus every change applied since (C19). Same connector contract, so everything downstream is
unchanged (R14). A created or updated record replaces its Zoho copy; its general-ledger postings replace the
postings of the same transaction.

Each change builds new containers and swaps them in, so a reader iterating on another thread never sees one change
half applied. `version` counts every change; `version_of(org)` counts one company's, so a change to one company
leaves every other company's cached numbers valid."""
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from txg.connector.base import RECORD_TYPES, Connector, LedgerLine, OrgRef, RawRecord
from txg.connector.changefeed import ChangeEvent


def _line(p: dict) -> LedgerLine:
    return LedgerLine(date.fromisoformat(p["date"]), p["account_id"], p.get("account_code", ""),
                      p["transaction_type"], p["transaction_id"], p.get("reference_number", ""),
                      p.get("description", ""), Decimal(str(p.get("debit") or "0")), Decimal(str(p.get("credit") or "0")))


class OverlayConnector:
    def __init__(self, base: Connector):
        self._base = base
        self.version = 0
        self._versions: dict[str, int] = {}
        self._records: dict[tuple[str, str, str], RawRecord] = {}
        self._replaced: set[tuple[str, str, str]] = set()  # (org, transaction_type, transaction_id)
        self._lines: dict[str, list[LedgerLine]] = {}

    def apply_change(self, event: ChangeEvent) -> None:
        if event.op == "upload":
            return
        if event.record_type in RECORD_TYPES:
            key = (event.org, event.record_type, event.zoho_id)
            self._records = {**self._records, key: RawRecord(event.record_type, event.org, event.zoho_id, event.record)}
        touched = {(event.org, p["transaction_type"], p["transaction_id"])
                   for p in (*event.postings, *event.postings_before)}
        self._replaced = self._replaced | touched
        kept = [ln for ln in self._lines.get(event.org, [])
                if (event.org, ln.transaction_type, ln.transaction_id) not in touched]
        self._lines = {**self._lines, event.org: kept + [_line(p) for p in event.postings]}
        self._versions = {**self._versions, event.org: self._versions.get(event.org, 0) + 1}
        self.version += 1

    def version_of(self, org: str) -> int:
        return self._versions.get(org, 0)

    def organisations(self) -> list[OrgRef]:
        return self._base.organisations()

    def iter_records(self, org: str, record_type: str) -> Iterator[RawRecord]:
        seen = set()
        for rec in self._base.iter_records(org, record_type):
            seen.add(rec.zoho_id)
            yield self._records.get((org, record_type, rec.zoho_id), rec)
        for (o, t, zid), rec in self._records.items():
            if o == org and t == record_type and zid not in seen:
                yield rec

    def fetch(self, org: str, record_type: str, zoho_id: str) -> RawRecord:
        hit = self._records.get((org, record_type, zoho_id))
        return hit if hit is not None else self._base.fetch(org, record_type, zoho_id)

    def iter_ledger_lines(self, org: str) -> Iterator[LedgerLine]:
        for ln in self._base.iter_ledger_lines(org):
            if (org, ln.transaction_type, ln.transaction_id) not in self._replaced:
                yield ln
        yield from self._lines.get(org, [])
