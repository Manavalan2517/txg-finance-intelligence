"""Receivable, payable, inventory and concentration KPIs (§11.2.2, §11.2.4, §11.2.5; §12.10–§12.11).
DSO and days late follow the Credit Research Foundation definitions on a 3-month basis."""
import calendar
from collections import defaultdict
from decimal import Decimal

from txg.kpi.common import _months_back
from txg.kpi.context import ZERO, KpiContext, previous_month
from txg.kpi.registry import Result, kpi

NEEDS_FACTS = Result(None, "needs_data", "needs invoices, bills and payments (data tier 2)")


def _days(months: list[str]) -> Decimal:
    return Decimal(sum(calendar.monthrange(*map(int, m.split("-")))[1] for m in months))


def _three_month_sales(ctx: KpiContext, m: str):
    w = ctx.window(m, 3)
    if w is None or any(x not in ctx.facts for x in w):
        return None, None
    return w, sum((ctx.facts[x].credit_sales for x in w), ZERO)


def _ar(ctx: KpiContext, m: str) -> Decimal:
    return ctx.bs[m].get("1120", ZERO)


def _days_of_sales(ctx: KpiContext, m: str, numerator) -> Result:
    w, cs3 = _three_month_sales(ctx, m)
    if w is None:
        return NEEDS_FACTS
    if not cs3:
        return Result(None, "n.m.", "no credit sales in the last 3 months")
    return Result(numerator(ctx.facts[m]) / cs3 * _days(w))


@kpi("kpi_dso")
def dso(ctx: KpiContext, m: str) -> Result:
    return _days_of_sales(ctx, m, lambda f: _ar(ctx, m))


@kpi("kpi_best_dso")
def best_dso(ctx: KpiContext, m: str) -> Result:
    return _days_of_sales(ctx, m, lambda f: f.not_due)


@kpi("kpi_days_late")
def days_late(ctx: KpiContext, m: str) -> Result:
    return _days_of_sales(ctx, m, lambda f: _ar(ctx, m) - f.not_due)


@kpi("kpi_dso_excl_retention")
def dso_excl_retention(ctx: KpiContext, m: str) -> Result:
    return _days_of_sales(ctx, m, lambda f: _ar(ctx, m) - f.retention_held)


@kpi("retention_held")
def retention_held(ctx: KpiContext, m: str) -> Result:
    return Result(ctx.facts[m].retention_held) if m in ctx.facts else NEEDS_FACTS


@kpi("kpi_over_90_share")
def over_90_share(ctx: KpiContext, m: str) -> Result:
    if m not in ctx.facts:
        return NEEDS_FACTS
    ar = _ar(ctx, m)
    return Result(ctx.facts[m].past90 / ar) if ar else Result(None, "n.m.", "no receivables")


@kpi("kpi_collection_effectiveness")
def collection_effectiveness(ctx: KpiContext, m: str) -> Result:
    prev = previous_month(m)
    if m not in ctx.facts or prev not in ctx.bs:
        return NEEDS_FACTS
    f = ctx.facts[m]
    if not f.credit_sales:
        return Result(None, "n.m.", "no credit sales this month")
    opening = ctx.bs[prev].get("1120", ZERO)
    denom = opening + f.credit_sales - f.not_due
    if not denom:
        return Result(None, "n.m.")
    return Result((opening + f.credit_sales - _ar(ctx, m)) / denom * 100)


def _inventory_days(ctx: KpiContext, m: str) -> Result:
    w = ctx.window(m, 3)
    start = ctx.bs_at(_months_back(m, 3))
    if w is None or start is None:
        return Result(None, "needs_data", "needs 3 closed months")
    cogs = -sum((ctx.flow_where(x, lambda c: c.startswith("5")) for x in w), ZERO)
    inv0, inv = start.get("1140", ZERO), ctx.bs[m].get("1140", ZERO)
    if not cogs or not (inv0 or inv):
        return Result(None, "not_applicable", "no inventory")
    return Result((inv0 + inv) / 2 / cogs * _days(w))


@kpi("kpi_inventory_days")
def inventory_days(ctx: KpiContext, m: str) -> Result:
    return _inventory_days(ctx, m)


def _dpo(ctx: KpiContext, m: str) -> Result:
    w = ctx.window(m, 3)
    if w is None or any(x not in ctx.facts for x in w):
        return NEEDS_FACTS
    purchases = sum((ctx.facts[x].purchases for x in w), ZERO)
    if not purchases:
        return Result(None, "n.m.", "no purchases in the last 3 months")
    return Result(-ctx.bs[m].get("2110", ZERO) / purchases * _days(w))


@kpi("kpi_dpo")
def dpo(ctx: KpiContext, m: str) -> Result:
    return _dpo(ctx, m)


@kpi("kpi_supplier_overdue_share")
def supplier_overdue_share(ctx: KpiContext, m: str) -> Result:
    if m not in ctx.facts:
        return NEEDS_FACTS
    f = ctx.facts[m]
    return Result(f.overdue_bills / f.open_bills) if f.open_bills else Result(None, "n.m.", "no open bills")


@kpi("kpi_cash_conversion_cycle")
def cash_conversion_cycle(ctx: KpiContext, m: str) -> Result:
    d, p, i = dso(ctx, m), _dpo(ctx, m), _inventory_days(ctx, m)
    if d.value is None or p.value is None:
        return Result(None, "needs_data", "needs DSO and DPO")
    return Result(d.value + (i.value or ZERO) - p.value)


def _customer_shares(ctx: KpiContext, m: str) -> list[Decimal] | None:
    w = ctx.window(m, 12)
    if w is None or any(x not in ctx.facts for x in w):
        return None
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for x in w:
        for customer, v in ctx.facts[x].customer_sales.items():
            totals[customer] += v
    positive = [v for v in totals.values() if v > 0]
    total = sum(positive, ZERO)
    return sorted((v / total for v in positive), reverse=True) if total > 0 else []


def _concentration(ctx: KpiContext, m: str, pick) -> Result:
    shares = _customer_shares(ctx, m)
    if shares is None:
        return NEEDS_FACTS
    return Result(pick(shares)) if shares else Result(None, "n.m.", "no customer sales")


@kpi("kpi_top_customer_share")
def top_customer_share(ctx: KpiContext, m: str) -> Result:
    return _concentration(ctx, m, lambda s: s[0])


@kpi("kpi_top5_share")
def top5_share(ctx: KpiContext, m: str) -> Result:
    return _concentration(ctx, m, lambda s: sum(s[:5], ZERO))


@kpi("kpi_effective_customers")
def effective_customers(ctx: KpiContext, m: str) -> Result:
    """Effective number of customers = 1 ÷ HHI (§12.11)."""
    return _concentration(ctx, m, lambda s: 1 / sum((x * x for x in s), ZERO))
