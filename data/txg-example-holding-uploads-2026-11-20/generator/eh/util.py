"""Small helpers: money in halalas, seeded randomness, dates, timestamps.

Every amount inside the generator is an integer number of halalas (1 SAR = 100 halalas),
so the books balance exactly. Amounts are converted to SAR with two decimals only on export.
"""
import calendar
import hashlib
import math
import random
from datetime import date, datetime, timedelta, timezone

VAT_RATE = 0.15
RIYADH = timezone(timedelta(hours=3))


def H(sar: float) -> int:
    """SAR -> halalas."""
    return int(round(sar * 100))


def S(halalas: int) -> float:
    """halalas -> SAR with two decimals."""
    return round(halalas / 100.0, 2)


def vat_of(net: int) -> int:
    return int(round(net * VAT_RATE))


def rng_for(*parts) -> random.Random:
    """A random generator whose seed depends only on the given parts (stable across runs and machines)."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))


def lognormal(rng: random.Random, mean: float, sd: float) -> float:
    """A positive draw with the given mean and standard deviation."""
    if mean <= 0:
        return 0.0
    if sd <= 0:
        return mean
    s2 = math.log(1 + (sd / mean) ** 2)
    return rng.lognormvariate(math.log(mean) - s2 / 2, math.sqrt(s2))


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def dim(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def month_end(y: int, m: int) -> date:
    return date(y, m, dim(y, m))


def add_months(y: int, m: int, k: int):
    t = y * 12 + (m - 1) + k
    return t // 12, t % 12 + 1


def months(start: date, end: date):
    """(year, month) pairs from start's month to end's month inclusive."""
    y, m = start.year, start.month
    out = []
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = add_months(y, m, 1)
    return out


def stamp(d: date, rng: random.Random, lag_days: int = 0, hour_lo: int = 8, hour_hi: int = 18) -> str:
    """A Zoho-style timestamp (Riyadh time) on day d + lag, in office hours."""
    t = datetime(d.year, d.month, d.day, rng.randint(hour_lo, hour_hi - 1), rng.randint(0, 59), rng.randint(0, 59),
                 tzinfo=RIYADH) + timedelta(days=lag_days)
    return t.strftime("%Y-%m-%dT%H:%M:%S%z")


def split_int(total: int, weights):
    """Split an integer total by weights so the parts sum exactly to the total."""
    wsum = float(sum(weights)) or 1.0
    parts = [int(total * w / wsum) for w in weights]
    parts[-1] += total - sum(parts)
    return parts
