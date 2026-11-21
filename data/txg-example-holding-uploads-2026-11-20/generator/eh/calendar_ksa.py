"""Saudi calendar facts used by the generator.

Hijri holiday dates are the dates announced in Saudi Arabia, as recorded here. They move about 11 days
earlier each Gregorian year, which is what lets the engine separate holiday effects from calendar months.
Check them against the official announcements before relying on them outside Example Holding.
"""
from datetime import date, timedelta

from .util import dim

# First and last day of Ramadan (inclusive).
RAMADAN = {
    2021: (date(2021, 4, 13), date(2021, 5, 12)),
    2022: (date(2022, 4, 2), date(2022, 5, 1)),
    2023: (date(2023, 3, 23), date(2023, 4, 20)),
    2024: (date(2024, 3, 11), date(2024, 4, 9)),
    2025: (date(2025, 3, 1), date(2025, 3, 29)),
    2026: (date(2026, 2, 18), date(2026, 3, 19)),
}
# First day of Eid al-Fitr.
EID_FITR = {2021: date(2021, 5, 13), 2022: date(2022, 5, 2), 2023: date(2023, 4, 21), 2024: date(2024, 4, 10), 2025: date(2025, 3, 30),
            2026: date(2026, 3, 20)}
# Day of Arafah (Eid al-Adha starts the next day).
ARAFAH = {2021: date(2021, 7, 19), 2022: date(2022, 7, 8), 2023: date(2023, 6, 27), 2024: date(2024, 6, 15), 2025: date(2025, 6, 5),
          2026: date(2026, 5, 26)}

EID_DAYS = 4  # private-sector holiday length used for both Eids


def in_ramadan(d: date) -> bool:
    r = RAMADAN.get(d.year)
    return bool(r and r[0] <= d <= r[1])


def ramadan_days_left(d: date) -> int:
    """Days until the end of Ramadan (0 on the last day); -1 outside Ramadan."""
    r = RAMADAN.get(d.year)
    if not r or not (r[0] <= d <= r[1]):
        return -1
    return (r[1] - d).days


def in_eid_fitr(d: date) -> bool:
    e = EID_FITR.get(d.year)
    return bool(e and e <= d < e + timedelta(days=EID_DAYS))


def in_eid_adha(d: date) -> bool:
    a = ARAFAH.get(d.year)
    return bool(a and a <= d < a + timedelta(days=EID_DAYS))


def public_holidays(y: int):
    s = set()
    if y in EID_FITR:
        s.update(EID_FITR[y] + timedelta(days=i) for i in range(EID_DAYS))
    if y in ARAFAH:
        s.update(ARAFAH[y] + timedelta(days=i) for i in range(EID_DAYS))
    s.add(date(y, 9, 23))       # National Day
    if y >= 2022:
        s.add(date(y, 2, 22))   # Founding Day
    return s


def is_weekend(d: date) -> bool:
    return d.weekday() in (4, 5)  # Friday, Saturday


def working_days(y: int, m: int):
    hol = public_holidays(y)
    return [date(y, m, k) for k in range(1, dim(y, m) + 1)
            if not is_weekend(date(y, m, k)) and date(y, m, k) not in hol]


def month_shares(y: int, m: int):
    """Share of the month's days in Ramadan, Eid al-Fitr and Eid al-Adha."""
    n = dim(y, m)
    days = [date(y, m, k) for k in range(1, n + 1)]
    return {
        "ramadan": sum(in_ramadan(d) for d in days) / n,
        "eid_fitr": sum(in_eid_fitr(d) for d in days) / n,
        "eid_adha": sum(in_eid_adha(d) for d in days) / n,
    }


def pre_ramadan_share(y: int, m: int, window_days: int = 21):
    """Share of the month's days that fall in the `window_days` before Ramadan starts (pre-stocking)."""
    n = dim(y, m)
    count = 0
    for k in range(1, n + 1):
        d = date(y, m, k)
        for yy in (d.year, d.year + 1):
            r = RAMADAN.get(yy)
            if r and 0 < (r[0] - d).days <= window_days:
                count += 1
                break
    return count / n


def is_working_day(d: date) -> bool:
    return not is_weekend(d) and d not in public_holidays(d.year)


def prev_working(d: date) -> date:
    while not is_working_day(d):
        d -= timedelta(days=1)
    return d


def next_working(d: date) -> date:
    while not is_working_day(d):
        d += timedelta(days=1)
    return d


def last_working_day(y: int, m: int) -> date:
    return prev_working(date(y, m, dim(y, m)))


def day_kind(d: date) -> str:
    """'ramadan', 'eid_fitr', 'eid_adha' or 'normal' for one day."""
    if in_eid_fitr(d):
        return "eid_fitr"
    if in_eid_adha(d):
        return "eid_adha"
    if in_ramadan(d):
        return "ramadan"
    return "normal"
