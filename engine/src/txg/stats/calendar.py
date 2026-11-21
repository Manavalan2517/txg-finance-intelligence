"""The Hijri holiday table (§8.4): share of each Gregorian month taken by Ramadan, Eid al-Fitr and Eid al-Adha/Hajj.
Announced dates are stored as configuration; a month whose year is missing is refused, never zero (F-14)."""
import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from txg.ledger.chart import CONFIG_DIR


class MissingHolidayYear(LookupError):
    pass


@dataclass(frozen=True)
class HolidayShares:
    ramadan: float
    eid_fitr: float
    eid_adha: float


@lru_cache(maxsize=1)
def load_holidays() -> dict:
    return json.loads((CONFIG_DIR / "hijri_holidays.json").read_text(encoding="utf-8"))


def _days(start: date, n: int) -> set[date]:
    return {start + timedelta(days=i) for i in range(n)}


def _holiday_days(cal: dict, year: int) -> tuple[set[date], set[date], set[date]]:
    y = cal["years"].get(str(year))
    if y is None:
        raise MissingHolidayYear(f"no Hijri holiday dates for {year}")
    r0, r1 = (date.fromisoformat(d) for d in y["ramadan"])
    ramadan = _days(r0, (r1 - r0).days + 1)
    fitr = _days(date.fromisoformat(y["eid_fitr"]), cal["eid_days"])
    adha = _days(date.fromisoformat(y["arafah"]), cal["eid_days"] + 1)  # Arafah plus the Eid holiday
    return ramadan, fitr, adha


def holiday_shares(cal: dict, month: str) -> HolidayShares:
    y, m = map(int, month.split("-"))
    n = calendar.monthrange(y, m)[1]
    in_month = {date(y, m, d) for d in range(1, n + 1)}
    ramadan, fitr, adha = _holiday_days(cal, y)
    return HolidayShares(len(ramadan & in_month) / n, len(fitr & in_month) / n, len(adha & in_month) / n)
