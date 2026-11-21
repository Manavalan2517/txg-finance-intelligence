"""Open invoices and bills at any month end, rebuilt from documents and the payments applied to them."""
import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from txg.connector.base import Connector

CENT = Decimal("0.01")
_DOC = {"invoices": ("customer_id", "invoice_id"), "bills": ("vendor_id", "bill_id")}
_APPLIED = {"invoices": (("customerpayments", "invoices"), ("creditnotes", "invoices_credited")),
            "bills": (("vendorpayments", "bills"),)}


def month_end(month: str) -> date:
    y, m = map(int, month.split("-"))
    return date(y, m, calendar.monthrange(y, m)[1])


def _d(value) -> Decimal:
    return Decimal(str(value or 0))


def _go_live_balance(doc: dict) -> Decimal | None:
    """The document's open balance at go-live, if it was migrated. Present but empty is an error, never zero."""
    raw, present = None, False
    if "cf_balance_at_go_live" in doc:
        raw, present = doc["cf_balance_at_go_live"], True
    else:
        for f in doc.get("custom_fields") or []:
            if f.get("api_name") == "cf_balance_at_go_live":
                raw, present = f.get("value"), True
    if not present:
        return None
    if raw is None or raw == "":
        raise ValueError(f"document {doc.get('invoice_id') or doc.get('bill_id')} has an empty go-live balance")
    return Decimal(str(raw))


def _applied_by(conn: Connector, company: str, record_type: str, cutoff: date) -> dict[str, Decimal]:
    _, id_field = _DOC[record_type]
    applied: dict[str, Decimal] = defaultdict(Decimal)
    for source, key in _APPLIED[record_type]:
        for rec in conn.iter_records(company, source):
            if date.fromisoformat(rec.data["date"]) > cutoff:
                continue
            for line in rec.data.get(key) or []:
                applied[line[id_field]] += _d(line.get("amount_applied"))
    return applied


def open_by_contact(conn: Connector, company: str, record_type: str, month: str) -> dict[str, Decimal]:
    """SAR still open per contact at the month end (documents dated on or before it, less amounts applied by then)."""
    contact_field, id_field = _DOC[record_type]
    cutoff = month_end(month)
    applied = _applied_by(conn, company, record_type, cutoff)
    out: dict[str, Decimal] = defaultdict(Decimal)
    for rec in conn.iter_records(company, record_type):
        doc = rec.data
        if date.fromisoformat(doc["date"]) > cutoff:
            continue
        base = _go_live_balance(doc)
        base = _d(doc.get("total")) if base is None else base
        remaining = base - applied.get(doc[id_field], Decimal(0))
        if remaining:
            out[doc[contact_field]] += (remaining * _d(doc.get("exchange_rate") or 1)).quantize(CENT)
    return dict(out)
