"""The connector contract (C1). The file source (prototype) and the Zoho API (production) both implement it,
so everything downstream is identical (R14, D-16). There is no write path."""
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

# record type -> (envelope key in Zoho's response, id field). Singletons use a dict, not a list.
RECORD_TYPES: dict[str, tuple[str, str]] = {
    "organization": ("organization", "organization_id"),
    "openingbalances": ("opening_balance", "date"),
    "chartofaccounts": ("chartofaccounts", "account_id"),
    "contacts": ("contacts", "contact_id"),
    "items": ("items", "item_id"),
    "invoices": ("invoices", "invoice_id"),
    "creditnotes": ("creditnotes", "creditnote_id"),
    "customerpayments": ("customerpayments", "payment_id"),
    "salesreceipts": ("salesreceipts", "sales_receipt_id"),
    "bills": ("bills", "bill_id"),
    "vendorpayments": ("vendorpayments", "payment_id"),
    "expenses": ("expenses", "expense_id"),
    "journals": ("journals", "journal_id"),
    "bankaccounts": ("bankaccounts", "account_id"),
    "banktransactions": ("banktransactions", "transaction_id"),
    "purchaseorders": ("purchaseorders", "purchaseorder_id"),
    "salesorders": ("salesorders", "salesorder_id"),
    "projects": ("projects", "project_id"),
    "locations": ("locations", "location_id"),
    "inventoryadjustments": ("inventoryadjustments", "inventory_adjustment_id"),
    "transactionlocks": ("transaction_locks", "lock_date"),
    "users": ("users", "user_id"),
    "taxes": ("taxes", "tax_id"),
    "currencies": ("currencies", "currency_id"),
}

_ORG_CODE = re.compile(r"[A-Za-z0-9_-]{1,32}")


class RecordNotFound(LookupError):
    pass


def check_record_type(record_type: str) -> tuple[str, str]:
    if record_type not in RECORD_TYPES:
        raise ValueError(f"unknown record type: {record_type!r}")
    return RECORD_TYPES[record_type]


def check_org(org: str) -> str:
    if not _ORG_CODE.fullmatch(org):
        raise ValueError(f"invalid organisation code: {org!r}")
    return org


@dataclass(frozen=True)
class OrgRef:
    company: str
    organization_id: str
    name: str
    currency: str
    time_zone: str
    fiscal_year_start_month: int
    vat_number: str | None
    cr_number: str | None


@dataclass(frozen=True)
class RawRecord:
    record_type: str
    org: str
    zoho_id: str
    data: dict[str, Any] = field(hash=False, compare=True)


@dataclass(frozen=True)
class LedgerLine:
    """One posting from an account register (Zoho: GET /registers/{account_id}/transactions)."""
    date: date
    account_id: str
    account_code: str
    transaction_type: str
    transaction_id: str
    reference_number: str
    description: str
    debit: Decimal
    credit: Decimal


@runtime_checkable
class Connector(Protocol):
    def organisations(self) -> list[OrgRef]: ...

    def iter_records(self, org: str, record_type: str) -> Iterator[RawRecord]: ...

    def fetch(self, org: str, record_type: str, zoho_id: str) -> RawRecord: ...

    def iter_ledger_lines(self, org: str) -> Iterator[LedgerLine]: ...
