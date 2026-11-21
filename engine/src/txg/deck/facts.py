"""Facts for the deck (§17.3). A fact is one number (or a short phrase built from one) computed by the engine, with
an ID; slides only ever show facts. Formats follow §16.7 (SAR in millions, signed percentages with the true minus
sign, whole days); a trailing ".0" is dropped for reading ease, so values match the screens even where the prototype
prints "12.0%"."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Unit = Literal["sar_m", "pct", "pts", "days", "x", "count", "num1", "p", "text"]
MINUS = "−"


def _fixed(value: Decimal, places: int, strip: bool = True) -> str:
    q = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP) if places else value.quantize(
        Decimal(1), rounding=ROUND_HALF_UP)
    text = f"{abs(q):,.{places}f}"
    if strip and "." in text:
        text = text.rstrip("0").rstrip(".")
    return (MINUS if q < 0 else "") + text


@dataclass(frozen=True)
class Fact:
    fact_id: str
    value: Decimal | int | str
    unit: Unit
    source: str = ""  # where the engine computed it, for the manifest reader

    def number(self) -> float | None:
        return None if isinstance(self.value, str) else float(self.value)

    def text(self) -> str:
        v = self.value
        if self.unit == "text" or isinstance(v, str):
            return str(v)
        d = Decimal(v)
        match self.unit:
            case "sar_m":
                return _fixed(d / Decimal(1_000_000), 1) + "m"
            case "pct":
                return _fixed(d * 100, 1) + "%"
            case "pts":
                body = _fixed(d * 100, 2, strip=False)
                return ("+" if d > 0 else "") + body + " pts"
            case "days":
                return _fixed(d, 0)  # whole days, as the prototype shows them
            case "num1":
                return _fixed(d, 1, strip=False)
            case "x":
                return _fixed(d, 1, strip=False) + "x"
            case "count":
                return f"{int(d):,}"
            case "p":
                return "< 0.001" if d < Decimal("0.001") else _fixed(d, 3, strip=False)
        raise ValueError(f"unknown unit {self.unit}")
