"""Covenants and headroom (§12.14): definitions come from the facility terms; code computes them at each test date.
Leverage: net debt ÷ EBITDA ≤ L, headroom = EBITDA − net debt ÷ L. DSCR: CFADS ÷ debt service ≥ d, headroom =
CFADS − d × debt service. Liquidity: cash + undrawn committed lines ≥ minimum, headroom = value − minimum."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from txg.kpi.common import _ebitda, _ltm, _months_back
from txg.kpi.context import DEBT_CODES, LEASE_CODES, ZERO, KpiContext
from txg.ledger.subledger import month_end
from txg.uploads.facilities import Covenant, FacilityTerms


@dataclass(frozen=True)
class CovenantResult:
    name: str
    test: str
    value: float | None
    threshold: float
    passed: bool | None
    headroom_sar: float | None
    note: str = ""


def _covenant_ebitda(ctx: KpiContext, m: str, terms: FacilityTerms) -> Decimal | None:
    e = _ltm(ctx, m, _ebitda)
    if e is not None and terms.definitions.get("ebitda_before_ifrs16"):
        e += _ltm(ctx, m, lambda c, x: c.flow(x, ("6610", "7210")))  # remove the IFRS 16 uplift (lease costs back in)
    return e


def _net_debt(ctx: KpiContext, m: str, terms: FacilityTerms) -> Decimal:
    bs = ctx.bs[m]
    codes = DEBT_CODES + (LEASE_CODES if terms.definitions.get("lease_liabilities_in_net_debt") else ())
    return -sum((bs.get(c, ZERO) for c in codes), ZERO) - bs.get("1110", ZERO)


def liquidity(ctx: KpiContext, m: str, terms: FacilityTerms) -> Decimal:
    bs = ctx.bs[m]
    drawn = -bs.get("2170", ZERO)
    return bs.get("1110", ZERO) + max(ZERO, terms.rcf_limit - drawn)


def _leverage(ctx, m, terms, c: Covenant) -> CovenantResult:
    e, nd = _covenant_ebitda(ctx, m, terms), _net_debt(ctx, m, terms)
    if e is None or e <= 0:
        return CovenantResult(c.name, c.test, None, float(c.threshold), None, None, "EBITDA not meaningful")
    value = nd / e
    return CovenantResult(c.name, c.test, float(value), float(c.threshold), value <= c.threshold,
                          float(e - nd / c.threshold))


def _dscr(ctx, m, terms, c: Covenant) -> CovenantResult:
    e = _covenant_ebitda(ctx, m, terms)
    zakat_paid = _ltm(ctx, m, lambda cx, x: -cx.flow(x, ("7600",)) + cx.bs_movement.get(x, {}).get("2150", ZERO))
    interest = _ltm(ctx, m, lambda cx, x: -cx.flow(x, ("7200",)))
    start = month_end(_months_back(m, 12))
    principal = sum((p for _, p in terms.principal_due(start, month_end(m))), ZERO)
    if e is None or interest is None:
        return CovenantResult(c.name, c.test, None, float(c.threshold), None, None, "needs 12 closed months")
    service = interest + principal
    cfads = e - zakat_paid
    if service <= 0:
        return CovenantResult(c.name, c.test, None, float(c.threshold), None, None, "no debt service")
    return CovenantResult(c.name, c.test, float(cfads / service), float(c.threshold),
                          cfads / service >= c.threshold, float(cfads - c.threshold * service))


def _liquidity(ctx, m, terms, c: Covenant) -> CovenantResult:
    value = liquidity(ctx, m, terms)
    return CovenantResult(c.name, c.test, float(value), float(c.threshold), value >= c.threshold,
                          float(value - c.threshold))


def _interest_cover(ctx, m, terms, c: Covenant) -> CovenantResult:
    ebit = _ltm(ctx, m, lambda cx, x: _ebitda(cx, x) + cx.flow(x, ("6600", "6610", "6700")))
    interest = _ltm(ctx, m, lambda cx, x: -cx.flow(x, ("7200", "7210")))
    if ebit is None or interest is None:
        return CovenantResult(c.name, c.test, None, float(c.threshold), None, None, "needs 12 closed months")
    if interest <= 0:
        return CovenantResult(c.name, c.test, None, float(c.threshold), True, None, "no interest expense")
    return CovenantResult(c.name, c.test, float(ebit / interest), float(c.threshold), ebit / interest >= c.threshold,
                          float(ebit - c.threshold * interest))


_TESTS = {"net_debt_to_ebitda_max": _leverage, "dscr_min": _dscr, "cash_plus_undrawn_min": _liquidity,
          "interest_cover_min": _interest_cover}


def covenant_results(ctx: KpiContext, m: str, terms: FacilityTerms) -> list[CovenantResult]:
    out = []
    for c in terms.covenants:
        if c.threshold is None:
            out.append(CovenantResult(c.name, c.test, None, 0.0, None, None, "no threshold read from the letter"))
            continue
        fn = _TESTS.get(c.test)
        out.append(fn(ctx, m, terms, c) if fn else
                   CovenantResult(c.name, c.test, None, float(c.threshold or 0), None, None, "unknown covenant test"))
    return out


def as_of_date(m: str) -> date:
    return month_end(m)
