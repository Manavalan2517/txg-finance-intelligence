"""Ledger integrity tests (§11.5), CFO only. Every hit is "worth a look", with evidence, never an accusation."""
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from txg.connector.base import Connector

NIGRINI_NONCONFORMITY, NIGRINI_MARGINAL = 0.0022, 0.0018
MIN_BENFORD_RECORDS = 1000
BUNCHING_BAND = 0.05
BUNCHING_ALPHA = 0.001
RARE_USER_SHARE = 0.05
WEEKEND = {4, 5}  # Friday, Saturday (Python weekday numbers)
_DATE_FIELD = {"journals": "journal_date", "bills": "date", "invoices": "date"}
_ID_FIELD = {"journals": "journal_id", "bills": "bill_id", "invoices": "invoice_id"}


@dataclass(frozen=True)
class BenfordResult:
    mad: float
    n: int
    suitable: bool
    conformity: str


def benford_first_two(amounts: Sequence[float]) -> BenfordResult:
    """IT-01: MAD between actual and expected first-two-digit shares, expected log10(1 + 1/d), d = 10…99."""
    digits = [int(f"{a:.15e}".replace(".", "")[:2]) for a in amounts if a >= 10]
    n = len(digits)
    if n < MIN_BENFORD_RECORDS:
        return BenfordResult(0.0, n, False, "population too small")
    counts = Counter(digits)
    mad = sum(abs(counts.get(d, 0) / n - math.log10(1 + 1 / d)) for d in range(10, 100)) / 90
    label = ("nonconformity" if mad > NIGRINI_NONCONFORMITY else
             "marginal" if mad >= NIGRINI_MARGINAL else "acceptable")
    return BenfordResult(mad, n, True, label)


@dataclass(frozen=True)
class BunchingHit:
    limit: float
    below: int
    above: int
    p: float

    @property
    def flagged(self) -> bool:
        return self.p < BUNCHING_ALPHA


def bunching_below_limit(amounts: Sequence[float], limit: float) -> BunchingHit:
    """IT-02: count in [0.95 L, L) against [L, 1.05 L); one-sided binomial test against an even split."""
    below = sum(1 for a in amounts if limit * (1 - BUNCHING_BAND) <= a < limit)
    above = sum(1 for a in amounts if limit <= a < limit * (1 + BUNCHING_BAND))
    n = below + above
    p = sum(math.comb(n, i) for i in range(below, n + 1)) / 2 ** n if n else 1.0
    return BunchingHit(limit, below, above, p)


@dataclass(frozen=True)
class BackDated:
    record_id: str
    dated: date
    created: datetime
    lag_days: int
    into_closed_month: bool


def _locks(conn: Connector, company: str) -> list[tuple[date, date]]:
    return [(date.fromisoformat(r.data["lock_date"]), date.fromisoformat(r.data["locked_on"]))
            for r in conn.iter_records(company, "transactionlocks")]


def _closed_at(locks: list[tuple[date, date]], dated: date, created: date) -> bool:
    return any(locked_on <= created and lock_date >= dated for lock_date, locked_on in locks)


def back_dated(conn: Connector, company: str, record_type: str) -> list[BackDated]:
    """IT-03: created − dated beyond the company's normal posting lag (95th percentile), into a closed month."""
    locks = _locks(conn, company)
    rows = []
    for rec in conn.iter_records(company, record_type):
        dated = date.fromisoformat(rec.data[_DATE_FIELD[record_type]])
        created = datetime.fromisoformat(rec.data["created_time"])
        rows.append((rec.data[_ID_FIELD[record_type]], dated, created, (created.date() - dated).days))
    if not rows:
        return []
    lags = sorted(r[3] for r in rows)
    p95 = lags[min(len(lags) - 1, int(0.95 * len(lags)))]
    return [BackDated(i, d, c, lag, True) for i, d, c, lag in rows
            if lag > p95 and _closed_at(locks, d, c.date())]


@dataclass(frozen=True)
class UnusualPosting:
    record_id: str
    user_id: str
    created: datetime
    reason: str


def unusual_postings(conn: Connector, company: str) -> list[UnusualPosting]:
    """IT-06: entries by rarely-posting users (under 5% of postings) on Fridays, Saturdays or late at night."""
    journals = [r.data for r in conn.iter_records(company, "journals")]
    counts = Counter(j["created_by_id"] for j in journals)
    total = sum(counts.values()) or 1
    rare = {u for u, c in counts.items() if c / total < RARE_USER_SHARE}
    hits = []
    for j in journals:
        if j["created_by_id"] not in rare:
            continue
        created = datetime.fromisoformat(j["created_time"])
        reason = "weekend" if created.weekday() in WEEKEND else "late night" if created.hour >= 22 or created.hour < 5 else ""
        if reason:
            hits.append(UnusualPosting(j["journal_id"], j["created_by_id"], created, reason))
    return hits
