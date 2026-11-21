"""Budget uploads (§7.7): one CSV per year, lines down the side, months across ("Jan 2023" … "Dec 2023", "Total").
Checked on load: every month present and each line's months sum to its Total (to the halala)."""
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

Budgets = dict[str, dict[str, Decimal]]  # line -> month (YYYY-MM) -> amount


def _load_year(path: Path) -> Budgets:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = next(i for i, ln in enumerate(lines) if ln.startswith("Line,"))
    out: Budgets = {}
    for row in csv.DictReader(lines[header:]):
        months = {datetime.strptime(k, "%b %Y").strftime("%Y-%m"): Decimal(v)
                  for k, v in row.items() if k not in ("Line", "Total") and v}
        if len(months) != 12:
            raise ValueError(f"{path.name}: line {row['Line']!r} does not have 12 months")
        if (sum(months.values()) - Decimal(row["Total"])).copy_abs() > Decimal("0.01"):
            raise ValueError(f"{path.name}: line {row['Line']!r} months do not sum to its total")
        out[row["Line"]] = months
    return out


def load_budgets(folder: Path) -> Budgets:
    merged: Budgets = {}
    for path in sorted(folder.glob("budget_*.csv")):
        for line, months in _load_year(path).items():
            merged.setdefault(line, {}).update(months)
    return merged
