"""Cash KPIs from the direct-method cash flows (§11.1 HL-5, §11.2.3 CS-1), last 12 months."""
from decimal import Decimal

from txg.kpi.common import NEEDS_12, _ebitda, _ltm, _ratio
from txg.kpi.context import ZERO, KpiContext
from txg.kpi.registry import Result, kpi

NEEDS_CASH = Result(None, "needs_data", "needs 12 months of cash postings")


def _cash_ltm(ctx: KpiContext, m: str, *kinds: str) -> Decimal | None:
    w = ctx.window(m, 12)
    if w is None or any(x not in ctx.cash_flows for x in w):
        return None
    return sum((getattr(ctx.cash_flows[x], k) for x in w for k in kinds), ZERO)


@kpi("cfo_pre_interest_zakat_ltm")
def cfo_pre_interest_zakat_ltm(ctx: KpiContext, m: str) -> Result:
    v = _cash_ltm(ctx, m, "operating")
    return NEEDS_CASH if v is None else Result(v)


@kpi("kpi_cash_conversion")
def cash_conversion(ctx: KpiContext, m: str) -> Result:
    """Cash from operations before interest and Zakat ÷ EBITDA; n.m. when EBITDA ≤ 0 (§11.1 HL-5)."""
    cfo = _cash_ltm(ctx, m, "operating")
    if cfo is None:
        return NEEDS_CASH if ctx.window(m, 12) else NEEDS_12
    return _ratio(cfo, _ltm(ctx, m, _ebitda))


@kpi("kpi_free_cash_flow")
def free_cash_flow(ctx: KpiContext, m: str) -> Result:
    """Operating cash after Zakat, interest, capex and lease payments (§11.2.3 CS-1)."""
    v = _cash_ltm(ctx, m, "operating", "zakat", "interest", "capex", "leases")
    return NEEDS_CASH if v is None else Result(v)
