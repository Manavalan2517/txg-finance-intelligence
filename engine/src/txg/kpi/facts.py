"""Month-end sub-ledger facts for the receivable and payable KPIs (§11.2.5, §12.10): open amounts by due date,
retention held, credit sales and purchases, and sales by customer. Built once per company from the documents."""
import re
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from txg.connector.base import Connector
from txg.ledger.subledger import _go_live_balance, month_end

ZERO = Decimal(0)
_RETENTION_SAR = re.compile(r"retention[^()]*?\(SAR\s*([\d,]+(?:\.\d+)?)\)|retention.*?withheld\s*\(SAR\s*([\d,]+(?:\.\d+)?)\)",
                            re.IGNORECASE)
_MIGRATED_RETENTION = re.compile(r"migrated balance:\s*retention", re.IGNORECASE)


def retention_from_notes(notes: str, migrated_open: Decimal) -> Decimal:
    """Labelled stand-in for the tagger (§9.4 "retentions"): reads the retention a document's notes declare.
    A migrated retention-only balance is retention in full. The real tagger is a model step (Task C7)."""
    if not notes:
        return ZERO
    if _MIGRATED_RETENTION.search(notes):
        return migrated_open
    m = _RETENTION_SAR.search(notes)
    return Decimal((m.group(1) or m.group(2)).replace(",", "")) if m else ZERO


@dataclass(frozen=True)
class Doc:
    contact: str
    issued: date
    due: date
    base: Decimal          # amount open at issue (or at go-live for migrated documents), document currency
    rate: Decimal
    retention: Decimal
    opening: bool
    app_dates: tuple[date, ...]
    app_cumulative: tuple[Decimal, ...]
    release_dates: tuple[date, ...] = ()
    release_cumulative: tuple[Decimal, ...] = ()

    def open_at(self, t: date) -> Decimal:
        i = bisect_right(self.app_dates, t)
        return self.base - (self.app_cumulative[i - 1] if i else ZERO)

    def retention_held_at(self, t: date) -> Decimal:
        """Retention still withheld at t (document currency): declared retention less releases paid by then."""
        i = bisect_right(self.release_dates, t)
        released = self.release_cumulative[i - 1] if i else ZERO
        return max(ZERO, min(self.open_at(t), self.retention - released))


@dataclass(frozen=True)
class MonthFacts:
    credit_sales: Decimal = ZERO
    purchases: Decimal = ZERO
    not_due: Decimal = ZERO
    retention_held: Decimal = ZERO
    past90: Decimal = ZERO
    open_bills: Decimal = ZERO
    overdue_bills: Decimal = ZERO
    customer_sales: dict[str, Decimal] = field(default_factory=dict)


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _applications(conn: Connector, company: str, sources) -> dict[str, list[tuple[date, Decimal]]]:
    apps: dict[str, list[tuple[date, Decimal]]] = defaultdict(list)
    for source, key, id_field in sources:
        for rec in conn.iter_records(company, source):
            when = date.fromisoformat(rec.data["date"])
            for line in rec.data.get(key) or []:
                apps[line[id_field]].append((when, _d(line.get("amount_applied"))))
    return apps


def _docs(conn: Connector, company: str, kind: str, go_live: date) -> list[Doc]:
    contact_field, id_field = ("customer_id", "invoice_id") if kind == "invoices" else ("vendor_id", "bill_id")
    sources = ([("customerpayments", "invoices", "invoice_id"), ("creditnotes", "invoices_credited", "invoice_id")]
               if kind == "invoices" else [("vendorpayments", "bills", "bill_id")])
    apps = _applications(conn, company, sources)
    docs = []
    for rec in conn.iter_records(company, kind):
        d = rec.data
        issued = date.fromisoformat(d["date"])
        migrated = _go_live_balance(d)
        opening = issued < go_live
        base = migrated if (opening and migrated is not None) else _d(d.get("total"))
        timeline = sorted(a for a in apps.get(d[id_field], []) if a[0] >= go_live or not opening)
        retention = retention_from_notes(d.get("notes", ""), base)
        releases = _releases(timeline, retention)
        docs.append(Doc(d[contact_field], issued, date.fromisoformat(d.get("due_date") or d["date"]), base,
                        _d(d.get("exchange_rate") or 1), retention, opening,
                        tuple(t for t, _ in timeline), _cumulative(timeline),
                        tuple(t for t, _ in releases), _cumulative(releases)))
    return docs


def _cumulative(items: list[tuple[date, Decimal]]) -> tuple[Decimal, ...]:
    out, running = [], ZERO
    for _, amount in items:
        running += amount
        out.append(running)
    return tuple(out)


def _releases(timeline: list[tuple[date, Decimal]], retention: Decimal) -> list[tuple[date, Decimal]]:
    """Retention is released in halves (handover, then end of the defects period) or in full: an application of
    exactly half or all of the declared retention is taken as a release. Same rule for every company (R2)."""
    if not retention:
        return []
    targets = (retention / 2, retention)
    return [(t, a) for t, a in timeline if any(abs(a - x) <= Decimal("0.01") for x in targets)]


def _receivable_position(invoices: list[Doc], t: date) -> tuple[Decimal, Decimal, Decimal]:
    not_due = held = past90 = ZERO
    for doc in invoices:
        if doc.issued > t:
            continue
        o = doc.open_at(t) * doc.rate
        if o <= 0:
            continue
        h = doc.retention_held_at(t) * doc.rate
        held += h
        if doc.due >= t:
            not_due += o
        else:
            not_due += h
            if (t - doc.due).days > 90:
                past90 += o - h
    return not_due, held, past90


def _payable_position(bills: list[Doc], t: date) -> tuple[Decimal, Decimal]:
    open_total = overdue = ZERO
    for doc in bills:
        if doc.issued > t:
            continue
        o_fc = doc.open_at(t)
        if o_fc <= 0:
            continue
        o = o_fc * doc.rate
        open_total += o
        if doc.due < t:
            overdue += o - doc.retention_held_at(t) * doc.rate
    return open_total, overdue


def _flows(conn: Connector, company: str, invoices: list[Doc], bills: list[Doc], go_live: date):
    credit, purchases = defaultdict(Decimal), defaultdict(Decimal)
    for doc in invoices:
        if not doc.opening:
            credit[doc.issued.strftime("%Y-%m")] += doc.base * doc.rate
    for doc in bills:
        if not doc.opening:
            purchases[doc.issued.strftime("%Y-%m")] += doc.base * doc.rate
    by_customer = customer_sales([r.data for r in conn.iter_records(company, "invoices")],
                                 [r.data for r in conn.iter_records(company, "creditnotes")], go_live)
    return credit, purchases, by_customer


def customer_sales(invoices: list[dict], credit_notes: list[dict], go_live: date) -> dict[str, dict[str, Decimal]]:
    """Sales by month and customer in SAR, excluding tax, net of credit notes; migrated pre-go-live documents excluded."""
    out: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for docs, sign in ((invoices, 1), (credit_notes, -1)):
        for d in docs:
            if date.fromisoformat(d["date"]) >= go_live:
                out[d["date"][:7]][d["customer_id"]] += sign * _d(d.get("sub_total")) * _d(d.get("exchange_rate") or 1)
    return {m: dict(v) for m, v in out.items()}


def build_month_facts(conn: Connector, company: str) -> dict[str, MonthFacts]:
    go_live = date.fromisoformat(next(conn.iter_records(company, "openingbalances")).data["date"])
    invoices, bills = _docs(conn, company, "invoices", go_live), _docs(conn, company, "bills", go_live)
    credit, purchases, by_customer = _flows(conn, company, invoices, bills, go_live)
    last = max(ln.date for ln in conn.iter_ledger_lines(company)).strftime("%Y-%m")
    out, (y, m) = {}, (go_live.year, go_live.month)
    while f"{y:04d}-{m:02d}" <= last:
        key = f"{y:04d}-{m:02d}"
        t = month_end(key)
        not_due, held, past90 = _receivable_position(invoices, t)
        open_bills, overdue = _payable_position(bills, t)
        out[key] = MonthFacts(credit[key], purchases[key], not_due, held, past90, open_bills, overdue,
                              dict(by_customer.get(key, {})))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


AGEING_BUCKETS = ("Not yet due", "1–30 days", "31–60 days", "61–90 days", "Over 90 days")


def _bucket(days_past_due: int) -> str:
    if days_past_due <= 0:
        return AGEING_BUCKETS[0]
    return AGEING_BUCKETS[1] if days_past_due <= 30 else AGEING_BUCKETS[2] if days_past_due <= 60 else \
        AGEING_BUCKETS[3] if days_past_due <= 90 else AGEING_BUCKETS[4]


def receivable_ageing(conn: Connector, company: str, month: str) -> tuple[dict[str, Decimal], Decimal,
                                                                          dict[str, Decimal]]:
    """Open invoices at month end in SAR by days past due, the retention held inside them, and open amount by
    customer. Retention is held under contract, so it ages as not yet due (§12.10)."""
    go_live = date.fromisoformat(next(conn.iter_records(company, "openingbalances")).data["date"])
    t = month_end(month)
    buckets = dict.fromkeys(AGEING_BUCKETS, ZERO)
    held, by_customer = ZERO, defaultdict(Decimal)
    for doc in _docs(conn, company, "invoices", go_live):
        if doc.issued > t or (o := doc.open_at(t)) <= 0:
            continue
        h = doc.retention_held_at(t) * doc.rate
        buckets[AGEING_BUCKETS[0]] += h
        buckets[_bucket((t - doc.due).days)] += o * doc.rate - h
        held += h
        by_customer[doc.contact] += o * doc.rate
    return buckets, held, dict(by_customer)
