"""Price drivers (§12.13, DR-3): change in purchase and selling prices over matched items (same item and unit),
weighted by spend in the earlier window, in document currency so FX is kept apart. A driver is "at risk" when
purchase prices rise faster than selling prices (§11.2.6)."""
from collections import defaultdict
from collections.abc import Iterable

from txg.connector.base import Connector

MIN_GAP = 0.005  # half a point: smaller gaps are noise, not a driver trending against the company


def _rates(records: Iterable[dict], window: tuple[str, str]) -> dict[tuple[str, str], list[float]]:
    """(item, unit) -> [spend, quantity] within the window (months inclusive)."""
    out: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for d in records:
        if window[0] <= d["date"][:7] <= window[1]:
            for li in d.get("line_items") or []:
                if li.get("item_id") and li.get("quantity"):
                    acc = out[(li["item_id"], li.get("unit", ""))]
                    acc[0] += float(li["rate"]) * float(li["quantity"])
                    acc[1] += float(li["quantity"])
    return out


def price_change(conn: Connector, company: str, record_type: str, before: tuple[str, str],
                 after: tuple[str, str]) -> float:
    """Spend-weighted average change in unit price for items bought (bills) or sold (invoices) in both windows."""
    records = [r.data for r in conn.iter_records(company, record_type)]
    a, b = _rates(records, before), _rates(records, after)
    matched = [k for k in a if k in b and a[k][1] and b[k][1]]
    weight = sum(a[k][0] for k in matched)
    if not weight:
        return 0.0
    return sum(a[k][0] * ((b[k][0] / b[k][1]) / (a[k][0] / a[k][1]) - 1) for k in matched) / weight


def driver_at_risk(purchase_change: float, selling_change: float) -> str | None:
    return "purchase prices" if purchase_change - selling_change > MIN_GAP else None
