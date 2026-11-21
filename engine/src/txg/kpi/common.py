"""Statement-based common KPIs (§11.1–11.2). Each function reads the standard-ledger context and returns a Result;
it never raises on thin data, it returns a state instead ("n.m.", "not applicable", "needs data")."""
from decimal import Decimal

from txg.kpi.context import DA_CODES, DEBT_CODES, LEASE_CODES, STAFF_CODES, ZERO, KpiContext
from txg.kpi.registry import Result, kpi

NEEDS_12 = Result(None, "needs_data", "needs 12 closed months")


def _revenue(ctx: KpiContext, m: str) -> Decimal:
    return ctx.flow(m, ("4100",))


def _ebitda(ctx: KpiContext, m: str) -> Decimal:
    """Revenue + other operating income − cost of sales − operating expenses excluding D&A (§11.1 HL-3)."""
    return (ctx.flow(m, ("4100", "4200")) + ctx.flow_where(m, lambda c: c.startswith("5"))
            + ctx.flow_where(m, lambda c: c.startswith("6") and c not in DA_CODES))


def _da(ctx: KpiContext, m: str) -> Decimal:
    return -ctx.flow(m, DA_CODES)


def _sum(ctx: KpiContext, months: list[str], fn) -> Decimal:
    return sum((fn(ctx, m) for m in months), ZERO)


def _ltm(ctx: KpiContext, m: str, fn) -> Decimal | None:
    w = ctx.window(m, 12)
    return None if w is None else _sum(ctx, w, fn)


def _ratio(num: Decimal | None, den: Decimal | None) -> Result:
    if num is None or den is None:
        return NEEDS_12
    if den <= 0:
        return Result(None, "n.m.", "denominator is zero or negative")
    return Result(num / den)


def _net_debt(ctx: KpiContext, m: str, leases: bool) -> Decimal:
    bs = ctx.bs[m]
    codes = DEBT_CODES + (LEASE_CODES if leases else ())
    return -sum((bs.get(c, ZERO) for c in codes), ZERO) - bs.get("1110", ZERO)


@kpi("revenue_ltm")
def revenue_ltm(ctx: KpiContext, m: str) -> Result:
    v = _ltm(ctx, m, _revenue)
    return NEEDS_12 if v is None else Result(v)


@kpi("ebitda_ltm")
def ebitda_ltm(ctx: KpiContext, m: str) -> Result:
    v = _ltm(ctx, m, _ebitda)
    return NEEDS_12 if v is None else Result(v)


@kpi("kpi_gross_margin")
def gross_margin(ctx: KpiContext, m: str) -> Result:
    gross = _ltm(ctx, m, lambda c, x: _revenue(c, x) + c.flow_where(x, lambda s: s.startswith("5")))
    return _ratio(gross, _ltm(ctx, m, _revenue))


@kpi("kpi_ebitda_margin")
def ebitda_margin(ctx: KpiContext, m: str) -> Result:
    return _ratio(_ltm(ctx, m, _ebitda), _ltm(ctx, m, _revenue))


@kpi("kpi_opex_ratio")
def opex_ratio(ctx: KpiContext, m: str) -> Result:
    opex = _ltm(ctx, m, lambda c, x: -c.flow_where(x, lambda s: s.startswith("6") and s not in DA_CODES))
    return _ratio(opex, _ltm(ctx, m, _revenue))


@kpi("kpi_net_margin")
def net_margin(ctx: KpiContext, m: str) -> Result:
    return _ratio(_ltm(ctx, m, lambda c, x: c.flow_where(x, lambda s: True)), _ltm(ctx, m, _revenue))


@kpi("kpi_staff_cost_ratio")
def staff_cost_ratio(ctx: KpiContext, m: str) -> Result:
    return _ratio(_ltm(ctx, m, lambda c, x: -c.flow(x, STAFF_CODES)), _ltm(ctx, m, _revenue))


@kpi("kpi_interest_cover")
def interest_cover(ctx: KpiContext, m: str) -> Result:
    ebit = _ltm(ctx, m, lambda c, x: _ebitda(c, x) - _da(c, x))
    interest = _ltm(ctx, m, lambda c, x: -c.flow(x, ("7200", "7210")))
    if ebit is None or interest is None:
        return NEEDS_12
    if interest == 0:
        return Result(None, "not_applicable", "no interest expense in the last 12 months")
    return Result(ebit / interest)


@kpi("net_debt_excl_leases")
def net_debt_excl_leases(ctx: KpiContext, m: str) -> Result:
    return Result(_net_debt(ctx, m, leases=False)) if m in ctx.bs else Result(None, "needs_data")


def _net_debt_to_ebitda(ctx: KpiContext, m: str, leases: bool) -> Result:
    e12 = _ltm(ctx, m, _ebitda)
    if e12 is None:
        return NEEDS_12
    if e12 <= 0:
        return Result(None, "n.m.", "EBITDA is zero or negative")  # §10.2 edge case
    return Result(_net_debt(ctx, m, leases) / e12)


@kpi("kpi_net_debt_to_ebitda")
def net_debt_to_ebitda(ctx: KpiContext, m: str) -> Result:
    return _net_debt_to_ebitda(ctx, m, leases=False)


@kpi("kpi_net_debt_to_ebitda_incl_leases")
def net_debt_to_ebitda_incl_leases(ctx: KpiContext, m: str) -> Result:
    return _net_debt_to_ebitda(ctx, m, leases=True)


@kpi("kpi_growth_raw_3m")
def growth_raw_3m(ctx: KpiContext, m: str) -> Result:
    now = ctx.window(m, 3)
    then = ctx.window(_months_back(m, 12), 3)
    if now is None or then is None:
        return Result(None, "needs_data", "needs the same 3 months a year earlier")
    base = _sum(ctx, then, _revenue)
    return Result(_sum(ctx, now, _revenue) / base - 1) if base > 0 else Result(None, "n.m.")


def _months_back(m: str, n: int) -> str:
    y, mo = map(int, m.split("-"))
    total = y * 12 + (mo - 1) - n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _invested_capital(bs) -> Decimal:
    equity = -sum((v for c, v in bs.items() if c.startswith("3")), ZERO)
    debt = -sum((bs.get(c, ZERO) for c in DEBT_CODES + LEASE_CODES), ZERO)
    return equity + debt - bs.get("1110", ZERO)


def _avg_invested_capital(ctx: KpiContext, m: str) -> Decimal | None:
    points = [ctx.bs_at(_months_back(m, k)) for k in range(13)]
    if any(p is None for p in points):
        return None
    return sum((_invested_capital(p) for p in points), ZERO) / len(points)


@kpi("invested_capital_avg")
def invested_capital_avg(ctx: KpiContext, m: str) -> Result:
    if ctx.window(m, 12) is None:
        return NEEDS_12
    avg = _avg_invested_capital(ctx, m)
    return Result(avg) if avg is not None else Result(None, "needs_data", "needs 13 month-ends")


@kpi("kpi_roic")
def roic(ctx: KpiContext, m: str) -> Result:
    """NOPAT ÷ average invested capital, NOPAT = EBIT − Zakat (the answer key's convention; §12.9 approximation)."""
    nopat = _ltm(ctx, m, lambda c, x: _ebitda(c, x) - _da(c, x) + c.flow(x, ("7600",)))
    avg = _avg_invested_capital(ctx, m) if nopat is not None else None
    if nopat is None or avg is None:
        return NEEDS_12
    return Result(nopat / avg) if avg > 0 else Result(None, "n.m.", "invested capital is zero or negative")


@kpi("kpi_working_capital_to_revenue")
def working_capital_to_revenue(ctx: KpiContext, m: str) -> Result:
    if m not in ctx.bs:
        return Result(None, "needs_data")
    bs = ctx.bs[m]
    wc = sum((bs.get(c, ZERO) for c in ("1120", "1130", "1140", "2110")), ZERO)
    return _ratio(wc, _ltm(ctx, m, _revenue))


@kpi("kpi_capex_to_depreciation")
def capex_to_depreciation(ctx: KpiContext, m: str) -> Result:
    """Capex = movement in net PP&E plus depreciation charged (no disposals in the books)."""
    capex = _ltm(ctx, m, lambda c, x: c.bs_movement.get(x, {}).get("1210", ZERO) - c.flow(x, ("6600",)))
    return _ratio(capex, _ltm(ctx, m, _da))
