"""File source for the connector: Example Holding's books in Zoho Books' API format (§15.6). Read-only."""
import csv
import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

from txg.connector.base import LedgerLine, OrgRef, RawRecord, RecordNotFound, check_org, check_record_type


def _custom_field(fields: list[dict], label: str) -> str | None:
    return next((f.get("value") for f in fields or [] if f.get("label") == label), None)


class FileConnector:
    def __init__(self, root: Path):
        self._root = root
        self._index: dict[tuple[str, str], dict[str, RawRecord]] = {}

    def _folder(self, org: str) -> Path:
        return self._root / check_org(org)

    def organisations(self) -> list[OrgRef]:
        orgs = []
        for folder in sorted(p for p in self._root.iterdir() if (p / "organization.json").is_file()):
            o = next(self.iter_records(folder.name, "organization")).data
            orgs.append(OrgRef(
                company=folder.name, organization_id=str(o["organization_id"]), name=o["name"],
                currency=o.get("currency_code", "SAR"), time_zone=o.get("time_zone", "Asia/Riyadh"),
                fiscal_year_start_month=int(o.get("fiscal_year_start_month", 0)),
                vat_number=o.get("tax_reg_no"), cr_number=_custom_field(o.get("custom_fields"), "CR Number"),
            ))
        return orgs

    def _load(self, org: str, record_type: str) -> dict[str, RawRecord]:
        key = (org, record_type)
        if key not in self._index:
            envelope_key, id_field = check_record_type(record_type)
            path = self._folder(org) / f"{record_type}.json"
            records: dict[str, RawRecord] = {}
            if path.is_file():
                body = json.loads(path.read_text(encoding="utf-8"))
                payload = body.get(envelope_key)
                items = [payload] if isinstance(payload, dict) else (payload or [])
                for item in items:
                    zoho_id = str(item.get(id_field, ""))
                    if zoho_id and zoho_id not in records:  # de-duplicate by Zoho ID (F-03)
                        records[zoho_id] = RawRecord(record_type, org, zoho_id, item)
            self._index[key] = records
        return self._index[key]

    def iter_records(self, org: str, record_type: str) -> Iterator[RawRecord]:
        yield from self._load(org, record_type).values()

    def fetch(self, org: str, record_type: str, zoho_id: str) -> RawRecord:
        try:
            return self._load(org, record_type)[zoho_id]
        except KeyError:
            raise RecordNotFound(f"{record_type} {zoho_id} not found for {org}") from None

    def iter_ledger_lines(self, org: str) -> Iterator[LedgerLine]:
        path = self._folder(org) / "account_transactions.csv"
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                yield LedgerLine(
                    date=date.fromisoformat(row["date"]), account_id=row["account_id"],
                    account_code=row["account_code"], transaction_type=row["transaction_type"],
                    transaction_id=row["transaction_id"], reference_number=row["reference_number"],
                    description=row["description"], debit=Decimal(row["debit"] or "0"),
                    credit=Decimal(row["credit"] or "0"),
                )
