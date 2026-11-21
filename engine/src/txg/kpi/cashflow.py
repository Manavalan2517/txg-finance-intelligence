"""Direct-method cash flows by month (§11.1 HL-5, §11.2.3 CS-1): every cash posting is classed by the standard codes
on the other side of its transaction. Vendor payments are split across the bill lines they settle (capex, lease
or operating). Journals: borrowings → debt, dividends payable → dividends, interest → interest, Zakat payable →
Zakat, anything else → operating. Every other document type is operating. One rule for every company (R2)."""
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal

from txg.connector.base import Connector

ZERO = Decimal(0)
CASH = "1110"
CAPEX = frozenset({"1210", "1230"})
LEASES = frozenset({"2180", "2220"})
DEBT = frozenset({"2170", "2175", "2210"})
DIVIDENDS = frozenset({"2185"})
INTEREST = frozenset({"7200", "7210"})
ZAKAT = frozenset({"2150"})
_JOURNAL_ORDER = (("debt", DEBT), ("dividends", DIVIDENDS), ("interest", INTEREST), ("zakat", ZAKAT))


@dataclass(frozen=True)
class CashFlows:
    """Cash in (+) and out (−) for one month, SAR, by kind."""
    operating: Decimal = ZERO
    zakat: Decimal = ZERO
    interest: Decimal = ZERO
    capex: Decimal = ZERO
    leases: Decimal = ZERO
    debt: Decimal = ZERO
    dividends: Decimal = ZERO


def _bill_split(conn: Connector, company: str, mapping: Mapping[str, str]) -> dict[str, dict[str, Decimal]]:
    """Per bill: the share of its lines that is capex, leases or operating."""
    out = {}
    for rec in conn.iter_records(company, "bills"):
        parts: dict[str, Decimal] = defaultdict(Decimal)
        for li in rec.data.get("line_items") or []:
            code = mapping.get(li.get("account_id", ""), "")
            kind = "capex" if code in CAPEX else "leases" if code in LEASES else "operating"
            parts[kind] += Decimal(str(li.get("item_total") or 0))
        total = sum(parts.values(), ZERO)
        out[rec.data["bill_id"]] = {k: v / total for k, v in parts.items()} if total else {"operating": Decimal(1)}
    return out


def _payment_split(conn: Connector, company: str, mapping: Mapping[str, str]) -> dict[str, dict[str, Decimal]]:
    """Per vendor payment: shares by kind, weighted by the amount applied to each bill."""
    bills = _bill_split(conn, company, mapping)
    out = {}
    for rec in conn.iter_records(company, "vendorpayments"):
        parts: dict[str, Decimal] = defaultdict(Decimal)
        for app in rec.data.get("bills") or []:
            applied = Decimal(str(app.get("amount_applied") or 0))
            for kind, share in bills.get(app["bill_id"], {"operating": Decimal(1)}).items():
                parts[kind] += share * applied
        total = sum(parts.values(), ZERO)
        out[rec.data["payment_id"]] = {k: v / total for k, v in parts.items()} if total else {"operating": Decimal(1)}
    return out


def _journal_kind(codes: set[str]) -> str:
    return next((kind for kind, group in _JOURNAL_ORDER if codes & group), "operating")


def build_cash_flows(conn: Connector, company: str, mapping: Mapping[str, str]) -> dict[str, CashFlows]:
    by_txn: dict[tuple[str, str], list] = defaultdict(list)
    for ln in conn.iter_ledger_lines(company):
        if ln.transaction_type != "opening_balance":
            by_txn[(ln.transaction_type, ln.transaction_id)].append(ln)
    payments = _payment_split(conn, company, mapping)
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for (ttype, tid), lines in by_txn.items():
        codes = [mapping.get(ln.account_id, "") for ln in lines]
        cash = sum((ln.debit - ln.credit for ln, c in zip(lines, codes) if c == CASH), ZERO)
        others = {c for c in codes if c != CASH}
        if not cash or not others:
            continue  # no cash, or a transfer between the company's own cash accounts
        month = min(ln.date for ln in lines).strftime("%Y-%m")
        if ttype == "vendor_payment":
            for kind, share in payments.get(tid, {"operating": Decimal(1)}).items():
                totals[month][kind] += cash * share
        elif ttype == "journal":
            totals[month][_journal_kind(others)] += cash
        else:
            totals[month]["operating"] += cash
    names = {f.name for f in fields(CashFlows)}
    months = sorted({ln[0].date.strftime("%Y-%m") for ln in by_txn.values()})
    return {m: CashFlows(**{k: v for k, v in totals.get(m, {}).items() if k in names})
            for m in _month_range(months[0], months[-1])} if months else {}


def _month_range(first: str, last: str) -> list[str]:
    """Every month from first to last, so a month with no cash movement reads as zero, not missing."""
    out, (y, m) = [], map(int, first.split("-"))
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
