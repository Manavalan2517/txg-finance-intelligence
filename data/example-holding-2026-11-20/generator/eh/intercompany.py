"""Sales between group companies, generated once from the group configuration so that both companies
post the same invoices on the same dates. A planted story can leave one invoice unbooked by the buyer."""
from datetime import date, timedelta

from .calendar_ksa import is_working_day, next_working
from .util import H, add_months, dim, lognormal, rng_for


def ic_flows(group: dict, seller: str, buyer: str):
    spec = next((f for f in group.get("intercompany", []) if f["seller"] == seller and f["buyer"] == buyer), None)
    if not spec:
        return []
    r = rng_for("intercompany", seller, buyer)
    start, end = date.fromisoformat(spec["start"]), date.fromisoformat(group["data_end"])
    lo, hi = spec["invoices_per_month"]
    per = spec["monthly_sar_m"] * 1e6 / ((lo + hi) / 2)
    out, (y, m), n = [], (start.year, start.month), 0
    while date(y, m, 1) <= end:
        days = [date(y, m, k) for k in range(1, dim(y, m) + 1) if is_working_day(date(y, m, k))]
        for d in sorted(r.sample(days, min(len(days), r.randint(lo, hi)))):
            n += 1
            due = d + timedelta(days=spec["terms"])
            paid = next_working(due + timedelta(days=r.randint(*spec["pay_lag_days"])))
            out.append({"n": n, "date": d, "net": H(lognormal(r, per, per * 0.3)), "due": due,
                        "paid": paid if paid <= end else None, "unbooked": False, "dn": f"DN-{seller[-2:]}-{n:05d}"})
        y, m = add_months(y, m, 1)
    ub = spec.get("unbooked")
    if ub:
        d = date.fromisoformat(ub["date"])
        out.append({"n": n + 1, "date": d, "net": H(ub["net_sar"]), "due": d + timedelta(days=spec["terms"]),
                    "paid": None, "unbooked": True, "dn": f"DN-{seller[-2:]}-{n + 1:05d}"})
    return sorted([f for f in out if f["date"] <= end], key=lambda f: (f["date"], f["n"]))
