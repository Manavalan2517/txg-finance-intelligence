"""Facility terms (§9.5, Appendix D.6). The real source is the model reading the facility letters (PDF, prose) twice;
until that reader runs, a labelled stand-in loads recorded readings (the structured terms delivered with the data).
Code checks every reading: a repayment schedule must sum to the principal and run in date order (CK-11)."""
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path


class FacilityCheckError(ValueError):
    pass


@dataclass(frozen=True)
class Covenant:
    name: str
    test: str
    threshold: Decimal | None
    frequency: str


@dataclass(frozen=True)
class FacilityTerms:
    facilities: tuple[dict, ...]
    covenants: tuple[Covenant, ...]
    definitions: dict = field(default_factory=dict, hash=False)
    source: str = "recorded reading (stand-in for the document reader)"
    markers: tuple[str, ...] = ()  # readings applied without full verification (F-11, F-12)

    @property
    def rcf_limit(self) -> Decimal:
        return sum((Decimal(str(f["limit_sar"])) for f in self.facilities if f.get("type") == "rcf"), Decimal(0))

    def principal_due(self, start: date, end: date) -> list[tuple[date, Decimal]]:
        """Scheduled principal repayments with start < date <= end."""
        out = []
        for f in self.facilities:
            for s in f.get("schedule") or []:
                d = date.fromisoformat(s["date"])
                if start < d <= end:
                    out.append((d, Decimal(str(s["principal_sar"]))))
        return sorted(out)


def _check_schedule(f: dict) -> None:
    schedule = f.get("schedule")
    if not schedule:
        return
    total = sum((Decimal(str(s["principal_sar"])) for s in schedule), Decimal(0))
    if abs(total - Decimal(str(f["amount_sar"]))) > Decimal("0.01"):
        raise FacilityCheckError(f"{f['facility']}: schedule sums to {total}, principal is {f['amount_sar']}")
    dates = [s["date"] for s in schedule]
    if dates != sorted(dates):
        raise FacilityCheckError(f"{f['facility']}: repayment dates are not in order")


def load_recorded_facilities(path: Path) -> FacilityTerms:
    letters = json.loads(path.read_text(encoding="utf-8"))
    facilities, covenants, definitions, seen = [], [], {}, set()
    for letter in letters:
        for f in letter.get("facilities", []):
            _check_schedule(f)
            facilities.append(f)
        for c in letter.get("covenants", []):
            key = (c["name"], c["test"])
            if key in seen:
                continue
            seen.add(key)
            raw = c.get("threshold", c.get("threshold_sar"))
            covenants.append(Covenant(c["name"], c["test"], None if raw is None else Decimal(str(raw)),
                                      c.get("frequency", "")))
        definitions.update(letter.get("definitions", {}))
    return FacilityTerms(tuple(facilities), tuple(covenants), definitions)
