"""13-week liquidity simulation (§12.8, HL-7). Weeks run Sunday–Saturday from the as-of date. Start: bank balances
plus undrawn committed lines. Each open invoice is collected at its due date plus a delay drawn from that customer's
own record of days paid after due (pooled across the company when it has fewer than 10). Bills follow the company's
paying habit; payroll, interest, scheduled principal and VAT follow their calendars; new billing and purchases
continue at the recent run rate. HL-7 = median low point; also its week, the 10th percentile and the chance of
falling below the minimum in any week."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

import numpy as np

from txg.connector.base import Connector
from txg.kpi.context import STAFF_CODES, ZERO, KpiContext
from txg.kpi.facts import Doc, _docs
from txg.ledger.subledger import month_end
from txg.stats.covenants import liquidity
from txg.stats.seed import seed_for
from txg.uploads.facilities import FacilityTerms

PATHS, WEEKS, MIN_OWN_HISTORY, HISTORY_DAYS = 10_000, 13, 10, 730


@dataclass(frozen=True)
class Week:
    start: date
    p10: float
    p50: float
    p90: float


@dataclass(frozen=True)
class CashForecast:
    opening: float
    minimum: float
    weeks: tuple[Week, ...]
    low_points: tuple[float, ...]
    low_point_p50: float
    low_point_p10: float
    chance_below_minimum: float


def principal_in_horizon(terms: FacilityTerms, t0: date, end: date) -> list[tuple[date, Decimal]]:
    """Scheduled principal after the as-of date and within the horizon (including days before the first Sunday)."""
    return terms.principal_due(t0, end)


def _paid_delays(docs: list[Doc], t0: date) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Days from due date to settlement of the main amount (retention, which is released later, excluded)."""
    per: dict[str, list[int]] = {}
    for d in docs:
        settled = next((t for t in d.app_dates
                        if d.open_at(t) <= d.retention_held_at(t) + Decimal("0.01")), None)
        if settled and settled <= t0 and (t0 - settled).days <= HISTORY_DAYS:
            per.setdefault(d.contact, []).append((settled - d.due).days)
    pooled = np.array([x for v in per.values() for x in v] or [0])
    return {k: np.array(v) for k, v in per.items()}, pooled


def _add(matrix: np.ndarray, offsets: np.ndarray, amount: float) -> None:
    weeks = np.clip(offsets // 7, 0, None)
    rows = np.nonzero(weeks < WEEKS)[0]
    np.add.at(matrix, (rows, weeks[rows]), amount)


def _collections(rng, invoices: list[Doc], t0: date, start: date, paths: int) -> np.ndarray:
    per, pooled = _paid_delays(invoices, t0)
    inflow = np.zeros((paths, WEEKS))
    for d in invoices:
        if d.issued > t0:
            continue
        amount = float((d.open_at(t0) - d.retention_held_at(t0)) * d.rate)
        if amount <= 0:
            continue
        hist = per.get(d.contact)
        hist = hist if hist is not None and len(hist) >= MIN_OWN_HISTORY else pooled
        overdue = (t0 - d.due).days
        eligible = hist[hist > overdue] if overdue > 0 else hist
        if len(eligible) == 0:
            continue  # later than anything in its record: not expected within 13 weeks
        _add(inflow, (d.due - start).days + rng.choice(eligible, size=paths), amount)
    return inflow


def _scheduled(ctx: KpiContext, terms: FacilityTerms, bills: list[Doc], as_of: str, t0: date,
               start: date) -> np.ndarray:
    out = np.zeros(WEEKS)
    end = start + timedelta(days=7 * WEEKS)
    _, pooled = _paid_delays(bills, t0)
    habit = int(np.median(pooled))

    def put(day: date, amount: float) -> None:
        offset = (day - start).days
        if offset < 7 * WEEKS and amount > 0:
            out[max(0, offset // 7)] += amount

    for d in bills:
        if d.issued <= t0:
            put(d.due + timedelta(days=habit), float((d.open_at(t0) - d.retention_held_at(t0)) * d.rate))
    staff, interest = float(-ctx.flow(as_of, STAFF_CODES)), float(-ctx.flow(as_of, ("7200",)))
    m, day = as_of, start
    while day < end:
        y, mo = map(int, m.split("-"))
        m = f"{y + mo // 12:04d}-{mo % 12 + 1:02d}"
        put(date(int(m[:4]), int(m[5:]), 27), staff)
        put(month_end(m), interest)
        day = month_end(m)
    for when, principal in principal_in_horizon(terms, t0, end):
        put(when, float(principal))
    put(month_end(f"{t0.year}-{t0.month:02d}") + timedelta(days=30), float(-ctx.bs[as_of].get("2140", ZERO)))
    return out


def _run_rate(ctx: KpiContext, docs: list[Doc], as_of: str, t0: date, start: date, rng, paths: int,
              kind: str) -> np.ndarray:
    """New invoices (or bills) at the last-3-month average, issued mid-month, with the usual terms and delays."""
    months = [m for m in ctx.months if m <= as_of][-3:]
    monthly = float(sum((getattr(ctx.facts[m], kind) for m in months if m in ctx.facts), ZERO)) / 3
    terms = int(median([(d.due - d.issued).days for d in docs if not d.opening] or [30]))
    _, pooled = _paid_delays(docs, t0)
    out = np.zeros((paths, WEEKS))
    for k in range(3):
        issue = date(start.year + (start.month - 1 + k) // 12, (start.month - 1 + k) % 12 + 1, 15)
        base = (issue - start).days + terms
        offsets = base + (rng.choice(pooled, size=paths) if kind == "credit_sales" else np.full(paths, int(np.median(pooled))))
        _add(out, offsets, monthly)
    return out


def median_low_point(low: np.ndarray) -> float:
    """HL-7: the median of the paths' low points (§12.8), never the mean, so a few very bad paths do not set it."""
    return float(np.sort(low)[len(low) // 2])


def simulate_13_weeks(conn: Connector, ctx: KpiContext, terms: FacilityTerms, as_of: str, minimum: Decimal,
                      paths: int = PATHS) -> CashForecast:
    t0 = month_end(as_of)
    start = t0 + timedelta(days=(6 - t0.weekday()) % 7 or 7)
    go_live = date.fromisoformat(next(conn.iter_records(ctx.company, "openingbalances")).data["date"])
    invoices, bills = _docs(conn, ctx.company, "invoices", go_live), _docs(conn, ctx.company, "bills", go_live)
    rng = np.random.default_rng(seed_for(ctx.company, as_of, "HL-7"))
    inflow = _collections(rng, invoices, t0, start, paths) + _run_rate(ctx, invoices, as_of, t0, start, rng, paths,
                                                                       "credit_sales")
    outflow = _scheduled(ctx, terms, bills, as_of, t0, start) + _run_rate(ctx, bills, as_of, t0, start, rng, paths,
                                                                          "purchases")
    opening = float(liquidity(ctx, as_of, terms))
    balances = opening + np.cumsum(inflow - outflow, axis=1)
    low = balances.min(axis=1)
    weeks = tuple(Week(start + timedelta(days=7 * w), *(float(np.percentile(balances[:, w], q)) for q in (10, 50, 90)))
                  for w in range(WEEKS))
    return CashForecast(opening, float(minimum), weeks, tuple(float(x) for x in low),
                        median_low_point(low), float(np.percentile(low, 10)),
                        float(np.mean(low < float(minimum))))
