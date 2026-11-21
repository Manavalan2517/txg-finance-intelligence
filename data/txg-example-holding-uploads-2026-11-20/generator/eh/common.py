"""The common company engine: what every Example Holding company does, whatever its sector.

Payroll with GOSI and end-of-service benefits, overhead bills with accruals and prepayments, petty cash,
government fees, capital spending and depreciation, term loans and a revolving credit facility, a treasury
that sweeps the collections account and pays suppliers twice a week, the monthly VAT return, Zakat,
dividends to the holding company, the expected-credit-loss allowance and the month-end close.

The simulation runs one day at a time from the start of the warm-up year. Sector classes add customers,
suppliers, products and the documents of their trade.
"""
import math
from collections import defaultdict
from datetime import date, timedelta

from .books import Books
from .calendar_ksa import is_working_day, last_working_day, next_working, prev_working
from .markets import rate_to_sar, saibor
from .names import EXPATS, OVERHEAD, SA_FIRST, SA_LAST
from .util import H, S, add_months, clamp, dim, lognormal, month_end, rng_for

MILLION = H(1_000_000)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def mlabel(y, m):
    return f"{MONTHS[m - 1]} {y}"


class CompanySim:
    sector = ""
    extra_roles = []

    def __init__(self, company: dict, group: dict):
        self.c = company
        self.g = group
        self.code = company["code"]
        self.p = company["params"]
        self.start = date.fromisoformat(group["sim_start"])
        self.go_live = date.fromisoformat(group["go_live"])
        self.data_end = date.fromisoformat(group["data_end"])
        self.first_open = date(self.data_end.year, self.data_end.month, 1)
        self.b = Books(company, self.go_live, self.data_end)
        self.rng = rng_for(self.code, "sim")
        self.stories = {}
        for s in group.get("stories", []):
            if self.code in s.get("companies", {}):
                self.stories[s["id"]] = dict(s["companies"][self.code], start=s.get("start"))
        self.truth = defaultdict(list)
        self.warnings = []
        self.payroll_log = []
        self.close_log = []
        self.vendors = {}
        self.open_bills = []
        self.rcf_days = defaultdict(int)
        self.zakat_prov = {}
        self.zakat_accrued = defaultdict(int)
        self.advances = []
        self.heads = {}
        self.next_payroll_net = 0
        self.dividends_due = []
        self.suspense_open = []
        self.loans = []
        self.collect_q = {}
        self.accrued_fee = defaultdict(int)
        self.prepaids = []

    # ================================================================== small helpers
    def story(self, sid):
        return self.stories.get(sid)

    def bal(self, key):
        return self.b.bal[key]

    def years_from_base(self, d: date) -> float:
        return (d - date(2024, 7, 1)).days / 365.25

    def trend(self, d: date) -> float:
        """Underlying growth path, 1.0 in mid-2024."""
        return (1 + self.p.get("growth", 0.04)) ** self.years_from_base(d)

    def r(self, *parts):
        return rng_for(self.code, *parts)

    def working_days(self, y, m):
        return [date(y, m, k) for k in range(1, dim(y, m) + 1) if is_working_day(date(y, m, k))]

    def pick_working(self, rng, y, m, lo=1, hi=31):
        days = [d for d in self.working_days(y, m) if lo <= d.day <= hi] or self.working_days(y, m)
        return rng.choice(days)

    def closed(self, y, m) -> bool:
        return month_end(y, m) < self.first_open

    def vendor(self, key: str, terms: int = 30, cls: str = "private", prefix: str = "") -> dict:
        if key not in self.vendors:
            name = OVERHEAD.get(key, key)
            n = len(self.vendors) + 1
            self.vendors[key] = self.b.add_contact(
                name, "vendor", cls, terms, self.start - timedelta(days=400 + n * 7),
                vat_no=f"TEST-VAT-{self.c['org_num']:02d}{900 + n:04d}", cr_no=f"TEST-CR-{self.c['org_num']:02d}{900 + n:04d}",
                prefix=prefix or "".join(w[0] for w in name.split()[:3]).upper())
        return self.vendors[key]

    # ================================================================== users
    def make_users(self):
        r = self.r("users")
        roles = [("cfo", "Chief Financial Officer", "admin"), ("gl", "Finance Manager", "accountant"),
                 ("ar", "Accountant – Receivables", "staff"), ("ap", "Accountant – Payables", "staff"),
                 ("payroll", "Payroll and HR Officer", "staff"), ("treasury", "Treasury Accountant", "staff")]
        roles += self.extra_roles + [tuple(x) for x in self.c.get("extra_users", [])]
        used = set()
        for role, title, zrole in roles:
            while True:
                if role == "pos":
                    name = "POS Integration"
                elif r.random() < 0.5:
                    name = f"{r.choice(SA_FIRST)} {r.choice(SA_LAST)}"
                else:
                    name = r.choice(EXPATS)
                if name not in used:
                    used.add(name)
                    break
            handle = name.lower().replace(" ", ".").replace("-", "")
            self.b.users.append({
                "user_id": self.b.new_id("user"), "name": name,
                "email": f"{handle}@{self.code.lower().replace('-', '')}.example", "role_name": title,
                "user_role": zrole, "status": "active", "_role": role,
            })

    # ================================================================== run
    def run(self):
        self.b.today = self.start - timedelta(days=1)
        self.make_users()
        self.setup()
        self.opening_common(self.b.today)
        self.opening(self.b.today)
        self.finish_opening(self.b.today)
        d = self.start
        while d <= self.data_end:
            self.b.today = d
            if d.day == 1:
                self.month_start_common(d)
                self.month_start(d)
            self.day(d)
            self.b.run_due(d)
            if is_working_day(d) and d.weekday() in (6, 2):
                self.payment_run(d)
            self.rcf_days[(d.year, d.month)] += -self.bal("rcf")
            if d == month_end(d.year, d.month) and self.closed(d.year, d.month):
                self.close_month(d)
            d += timedelta(days=1)
        self.b.today = self.data_end
        return self

    # sector hooks ---------------------------------------------------------
    def setup(self):
        pass

    def opening(self, d0):
        pass

    def month_start(self, d):
        pass

    def day(self, d):
        pass

    def close_sector(self, d, lag):
        """Sector month-end entries; returns nothing."""

    def activity(self, y, m) -> float:
        return self.trend(date(y, m, 15))

    def revenue_level(self, d: date) -> int:
        """Expected monthly revenue (halalas) around day d, for sizing costs."""
        return int(H(self.p["revenue_sar_m"] * 1e6) / 12 * self.trend(d))

    # ================================================================== opening position
    def opening_common(self, d0: date):
        o = self.p["opening"]
        m = lambda k: H(o.get(k, 0) * 1e6)
        entries = [("bank1", m("bank1")), ("bank2", m("bank2")), ("cash", m("cash")), ("ppe_cost", m("ppe_cost")),
                   ("ppe_dep", -m("ppe_dep")), ("eosb", -m("eosb")), ("rcf", -m("rcf")),
                   ("vat_payable", -m("vat_payable")), ("gosi_payable", -m("gosi_payable")),
                   ("zakat_payable", -m("zakat_payable")), ("accrued", -m("accrued_audit"))]
        for ln in self.p.get("loans", []):
            out = self.loan_outstanding_at(ln, d0)
            if out:
                entries.append(("loan", -out))
        plug = -sum(a for _, a in entries)
        entries.append(("retained", plug))
        self.b.post(d0, entries, "opening", "opening-common", desc="Position before the warm-up year")
        sc, sr = m("share_capital"), m("stat_reserve")
        self.b.post(d0, [("retained", sc + sr), ("share_capital", -sc), ("stat_reserve", -sr)], "opening",
                    "opening-equity")
        self.zakat_prov[d0.year] = m("zakat_payable")
        for oh in self.p.get("overheads", []):
            if oh["freq"] == "annual_accrued":
                self.accrued_fee[(oh["key"], d0.year)] = m("accrued_audit")
        self.next_payroll_net = 0
        for ln in self.p.get("loans", []):
            self.loans.append(dict(ln, _out=self.loan_outstanding_at(ln, d0)))
        # liabilities brought forward are paid in the first months of the warm-up year
        self.b.schedule(next_working(date(d0.year + 1, 1, 10)), self.pay_gosi)
        self.b.schedule(self.vat_payment_day(d0.year, d0.month), self.pay_vat)
        self.b.schedule(prev_working(date(d0.year + 1, 4, 30)), lambda dd, y=d0.year: self.pay_zakat(dd, y))

    def finish_opening(self, d0: date):
        """Retained earnings is the plug of the opening position; it must come out positive."""
        if -self.bal("retained") <= 0:
            self.warnings.append(f"opening retained earnings not positive: {S(-self.bal('retained'))}")

    # ================================================================== loans
    def loan_schedule(self, ln):
        """[(date, principal)] of the term loan's repayments."""
        first = date.fromisoformat(ln["first_repayment"])
        amt = H(ln["amount_sar_m"] * 1e6)
        n = ln["instalments"]
        step = {"quarterly": 3, "semiannual": 6, "monthly": 1}[ln["frequency"]]
        balloon = ln.get("balloon_pct", 0)
        regular = int(amt * (1 - balloon) / n)
        out = []
        for i in range(n):
            y, mm = add_months(first.year, first.month, i * step)
            p = regular if i < n - 1 else amt - regular * (n - 1)
            out.append((month_end(y, mm), p))
        return out

    def loan_outstanding_at(self, ln, d: date) -> int:
        if date.fromisoformat(ln["drawn"]) > d:
            return 0
        amt = H(ln["amount_sar_m"] * 1e6)
        return amt - sum(p for dd, p in self.loan_schedule(ln) if dd <= d)

    # ================================================================== month start
    def month_start_common(self, d: date):
        y, m = d.year, d.month
        r = self.r("month", y, m)
        # term loans: drawdowns and repayments
        for ln in self.loans:
            dd = date.fromisoformat(ln["drawn"])
            if dd.year == y and dd.month == m and dd >= self.start:
                self.b.schedule(dd, lambda day, ln=ln: self.loan_draw(day, ln))
            for due, p in self.loan_schedule(ln):
                if due.year == y and due.month == m and due > self.start and date.fromisoformat(ln["drawn"]) < due:
                    self.b.schedule(prev_working(due), lambda day, ln=ln, p=p: self.loan_repay(day, ln, p))
        # payroll on the 25th (or the working day before)
        self.b.schedule(prev_working(date(y, m, 25)), self.payroll)
        # government fees for expatriate staff
        self.b.schedule(self.pick_working(r, y, m, 3, 15), self.government_fees)
        # overheads
        for oh in self.p.get("overheads", []):
            self.plan_overhead(oh, y, m, r)
        # petty cash
        self.b.schedule(next_working(date(y, m, 1)), self.petty_cash)
        # capital spending
        cx = self.p.get("capex")
        if cx and m in cx.get("months", list(range(1, 13))):
            self.b.schedule(self.pick_working(r, y, m, 5, 26), self.capex)
        # bank charges on the last working day
        self.b.schedule(last_working_day(y, m), self.bank_charges)
        # employee advances
        self.b.schedule(self.pick_working(r, y, m, 1, 20), self.employee_advances)
        # dividends: declared at the general assembly, paid in June
        if m == 5:
            self.b.schedule(prev_working(date(y, 5, 20)), self.declare_dividend)
        if m in (6, 9, 12):
            self.b.schedule(next_working(date(y, m, 10)), self.pay_dividend)
        # an occasional unidentified receipt in the collections account
        if r.random() < self.p.get("suspense_rate", 0.15):
            self.b.schedule(self.pick_working(r, y, m), self.suspense_receipt)

    # ================================================================== payroll
    def staff_heads(self, grp, y, m) -> int:
        key = (grp["group"], y, m)
        prev = self.heads.get((grp["group"],) + add_months(y, m, -1))
        base = grp["heads"] * (1 + grp.get("growth", self.p.get("growth", 0.04) * 0.6)) ** self.years_from_base(date(y, m, 15))
        target = base * (1 + grp.get("flex", 0) * (self.activity(y, m) / self.trend(date(y, m, 15)) - 1))
        if "per_store" in grp:
            target = grp["per_store"] * self.store_count(y, m)
        h = target if prev is None else 0.55 * prev + 0.45 * target
        h = max(1, int(round(h * (1 + self.r("heads", grp["group"], y, m).gauss(0, 0.006)))))
        self.heads[key] = h
        return h

    def store_count(self, y, m) -> int:
        return 0

    def payroll_lines(self, grp, y, m, heads, gross_total):
        """One or more (account, amount, description[, location]) lines for a staff group's gross pay."""
        return [(grp["account"], gross_total, f"Salaries and allowances {mlabel(y, m)} – {grp['label']}")]

    def payroll(self, d: date):
        y, m = d.year, d.month
        r = self.r("payroll", y, m)
        lines, emp_gosi_total, er_gosi_total, gross_all = [], 0, 0, 0
        for grp in self.p["staff"]:
            heads = self.staff_heads(grp, y, m)
            saudi = int(round(heads * grp["saudi"]))
            pay = grp["gross"] * (1 + self.p.get("pay_rise", 0.03)) ** max(0, y - 2024)
            pay *= 1 + r.gauss(0, 0.004)
            gross_non = H((heads - saudi) * pay)
            gross_sa = H(saudi * pay * grp.get("saudi_pay", 1.25))
            gross = gross_non + gross_sa
            base_sa = int(gross_sa * 0.75)
            base_non = int(gross_non * 0.75)
            emp = int(round(base_sa * 0.0975))
            er = int(round(base_sa * 0.1175 + base_non * 0.02))
            emp_gosi_total += emp
            er_gosi_total += er
            gross_all += gross
            lines += self.payroll_lines(grp, y, m, heads, gross)
            self.payroll_log.append({"month": f"{y}-{m:02d}", "group": grp["label"], "heads": heads, "saudi": saudi,
                                     "non_saudi": heads - saudi, "gross": gross, "gosi_base": base_sa + base_non,
                                     "gosi_employee": emp, "gosi_employer": er})
        recover = 0
        for adv in self.advances:
            if adv["left"] > 0:
                k = min(adv["left"], adv["instalment"])
                adv["left"] -= k
                recover += k
        net = gross_all - emp_gosi_total - recover
        lines += [("gosi_exp", er_gosi_total, f"Employer GOSI {mlabel(y, m)}"),
                  ("gosi_payable", -(er_gosi_total + emp_gosi_total), f"GOSI {mlabel(y, m)}"),
                  ("emp_adv", -recover, "Recovery of salary advances"),
                  ("salaries_payable", -net, f"Net salaries {mlabel(y, m)}")]
        self.b.journal(d, lines, f"Payroll {mlabel(y, m)}", role="payroll", created_lag=r.choice([0, 0, 1]),
                       ref=f"PAY-{y}{m:02d}", kind="payroll")
        self.next_payroll_net = net
        pay_day = d if r.random() < 0.7 else next_working(d + timedelta(days=1))
        self.b.schedule(pay_day, lambda day, net=net, y=y, m=m: self.pay_salaries(day, net, y, m))
        self.b.schedule(next_working(date(*add_months(y, m, 1), 10)), self.pay_gosi)
        self.month_gross = gross_all

    def pay_salaries(self, d, net, y, m):
        self.ensure_cash(d, net, mandatory=True)
        self.b.journal(d, [("salaries_payable", net, "Salary transfer (WPS)"), ("bank1", -net, "Salary transfer (WPS)")],
                       f"Salary payment {mlabel(y, m)} – wage protection system", role="treasury",
                       ref=f"WPS-{y}{m:02d}", kind="bank")

    def pay_gosi(self, d):
        amt = -self.bal("gosi_payable")
        if amt <= 0:
            return
        self.ensure_cash(d, amt, mandatory=True)
        self.b.journal(d, [("gosi_payable", amt, "GOSI contributions"), ("bank1", -amt, "GOSI payment (SADAD)")],
                       "GOSI monthly contributions", role="treasury", ref=f"GOSI-{d:%Y%m}", kind="bank")

    def government_fees(self, d):
        y, m = d.year, d.month
        r = self.r("govfees", y, m)
        for grp in self.p["staff"]:
            h = self.heads.get((grp["group"],) + add_months(y, m, -1)) or grp["heads"]
            expats = int(round(h * (1 - grp["saudi"])))
            if not expats:
                continue
            amt = H(expats * (800 + r.uniform(60, 140)))
            acct = grp.get("levy_account", "ga")
            self.ensure_cash(d, amt, mandatory=True)
            self.b.expense(d, acct, amt, vat=False,
                           desc=f"Expat levy, work permits and iqama renewals {mlabel(y, m)} – {grp['label']}",
                           ref=f"SADAD-{r.randint(10**8, 10**9 - 1)}", role="payroll")

    def employee_advances(self, d):
        r = self.r("advances", d.year, d.month)
        total_heads = sum(self.heads.get((g["group"],) + add_months(d.year, d.month, -1), g["heads"]) for g in self.p["staff"])
        n = sum(1 for _ in range(int(total_heads)) if r.random() < 0.0025)
        for i in range(n):
            amt = H(r.choice([1500, 2000, 2500, 3000, 4000, 5000]))
            self.advances.append({"left": amt, "instalment": amt // r.choice([2, 3, 4])})
            self.b.journal(d, [("emp_adv", amt, "Salary advance"), ("bank1", -amt, "Salary advance")],
                           "Salary advance to employee", role="payroll", ref=f"ADV-{d:%y%m}{i + 1:02d}", kind="bank")
        self.advances = [a for a in self.advances if a["left"] > 0]

    # ================================================================== overheads
    def plan_overhead(self, oh, y, m, r):
        freq = oh["freq"]
        annual = H(oh["annual_sar_m"] * 1e6) * self.trend(date(y, m, 15)) ** oh.get("scale", 0.6)
        v = self.vendor(oh["vendor"], terms=oh.get("terms", 30))
        if freq == "monthly":
            amt = int(lognormal(r, annual / 12, annual / 12 * oh.get("noise", 0.15)))
            self.b.schedule(self.pick_working(r, y, m, 2, 26),
                            lambda day, a=amt: self.overhead_bill(day, oh, v, a, oh["account"]))
        elif freq == "monthly_arrears":
            # this month's bill is for last month's consumption, which was accrued at last month's close
            py, pm = add_months(y, m, -1)
            amt = self.overhead_usage(oh, py, pm)
            if amt:
                self.b.schedule(self.pick_working(r, y, m, 6, 14),
                                lambda day, a=amt, py=py, pm=pm: self.overhead_bill(day, oh, v, a, oh["account"],
                                                                                     f"Consumption {mlabel(py, pm)}"))
        elif freq == "quarterly_advance" and m in (1, 4, 7, 10):
            amt = int(annual / 4)
            self.b.schedule(next_working(date(y, m, 1)),
                            lambda day, a=amt: self.overhead_bill(day, oh, v, a, "prepaid",
                                                                  f"Rent {mlabel(y, m)} to {mlabel(*add_months(y, m, 2))} in advance"))
            self.prepaid_plan(oh["key"], y, m, 3, amt, oh["account"])
        elif freq == "annual_prepaid" and m == oh.get("month", 1):
            amt = int(lognormal(r, annual, annual * 0.04))
            self.b.schedule(self.pick_working(r, y, m, 2, 12),
                            lambda day, a=amt: self.overhead_bill(day, oh, v, a, "prepaid", f"Annual policy {y}"))
            self.prepaid_plan(oh["key"], y, m, 12, amt, oh["account"])
        elif freq == "annual_accrued" and m == oh.get("month", 3):
            # the bill for last year's work, accrued month by month during last year
            amt = self.accrued_fee.get((oh["key"], y - 1)) or int(annual)
            self.b.schedule(self.pick_working(r, y, m, 5, 25),
                            lambda day, a=amt: self.overhead_bill(day, oh, v, a, "accrued", f"Fee for {y - 1}"))

    def overhead_usage(self, oh, y, m) -> int:
        """Consumption-based overhead (utilities) for month y-m: the same draw at accrual and at billing."""
        annual = H(oh["annual_sar_m"] * 1e6) * self.trend(date(y, m, 15)) ** oh.get("scale", 0.6)
        season = oh.get("season", [1.0] * 12)[m - 1]
        return int(lognormal(self.r("usage", oh["key"], y, m), annual / 12 * season, annual / 12 * 0.06))

    def overhead_bill(self, d, oh, v, amt, account, desc=""):
        if amt <= 0:
            return
        self.post_bill(d, v, [{"name": oh["label"], "desc": desc, "qty": 1, "rate": amt, "account": account}],
                       vat=oh.get("vat", True), created_lag=self.r("lag", oh["key"], d).choice([0, 1, 2, 3, 5, 8]))

    def prepaid_plan(self, key, y, m, months, amount, account):
        per = amount // months
        for i in range(months):
            yy, mm = add_months(y, m, i)
            self.prepaids.append({"y": yy, "m": mm, "amount": per if i < months - 1 else amount - per * (months - 1),
                                  "account": account, "key": key})

    def petty_cash(self, d):
        y, m = d.year, d.month
        r = self.r("petty", y, m)
        pc = self.p.get("petty_cash", {"float": 0.05, "items": 8})
        flt = H(pc["float"] * 1e6)
        top = flt - self.bal("cash")
        if top > 0:
            self.b.journal(d, [("cash", top, "Petty cash top-up"), ("bank1", -top, "Cash withdrawal")],
                           "Petty cash replenishment", role="treasury", ref=f"PC-{y}{m:02d}", kind="bank")
        n = max(1, int(lognormal(r, pc["items"], pc["items"] * 0.3)))
        accts = pc.get("accounts", ["ga"])
        spend_cap = int(flt * 0.85)
        for i in range(n):
            dd = self.pick_working(r, y, m, 2, 28)
            amt = H(round(lognormal(r, pc.get("avg", 350), pc.get("avg", 350) * 0.9), 2))
            amt = min(amt, spend_cap // n)
            vat = r.random() < 0.7
            acct = r.choice(accts)
            desc = r.choice(["Refreshments for site meeting", "Taxi and transport", "Stationery", "Minor repairs",
                             "Courier charges", "Fuel", "Cleaning supplies", "Tools and consumables",
                             "Water and ice", "Printing"])
            self.b.schedule(dd, lambda day, a=amt, v=vat, ac=acct, ds=desc: self.b.expense(
                day, ac, int(a / 1.15) if v else a, paid_through="cash", vat=v, desc=ds, role="ap"))

    def bank_charges(self, d):
        r = self.r("bankch", d.year, d.month)
        n_tx = sum(1 for ln in self.b.lines[-4000:] if ln[0].year == d.year and ln[0].month == d.month
                   and ln[1] in ("bank1", "bank2"))
        amt = H(self.p.get("bank_fee_base", 900) + n_tx * r.uniform(2.5, 4.0))
        self.b.expense(d, "bank_charges", amt, desc=f"Bank charges and transfer fees {mlabel(d.year, d.month)}",
                       ref=f"BNK-{d:%Y%m}", role="treasury")

    # ================================================================== capital spending
    def capex(self, d):
        cx = self.p["capex"]
        r = self.r("capex", d.year, d.month)
        months = len(cx.get("months", list(range(1, 13))))
        annual = self.revenue_level(d) * 12 * cx["pct_revenue"]
        amt = int(lognormal(r, annual / months, annual / months * 0.5))
        v = self.vendor(cx.get("vendor", "equipment"), terms=45)
        self.post_bill(d, v, [{"name": cx.get("label", "Equipment"), "desc": r.choice(cx.get("items", ["Equipment"])),
                               "qty": 1, "rate": amt, "account": "ppe_cost"}], created_lag=r.choice([0, 1, 2]))

    # ================================================================== bills and the treasury
    def post_bill(self, d, vendor, lines, **kw):
        b = self.b.bill(d, vendor, lines, **kw)
        self.open_bills.append(b)
        return b

    def bill_payable_fc(self, b) -> int:
        open_fc = self.b.bill_open_fc(b)
        return open_fc - min(b["_retention"], open_fc)

    def headroom(self) -> int:
        lim = H(self.p.get("rcf", {}).get("limit_sar_m", 0) * 1e6)
        return max(0, lim + self.bal("rcf"))

    def sweep(self, d):
        amt = self.bal("bank2")
        if amt > H(50_000):
            self.b.journal(d, [("bank1", amt, "Transfer from collections account"),
                               ("bank2", -amt, "Transfer to operating account")],
                           "Sweep of collections account", role="treasury", ref=f"SWP-{d:%y%m%d}", kind="bank")

    def ensure_cash(self, d, amount, mandatory=False) -> bool:
        tr = self.p["treasury"]
        floor = H(tr["min_cash_sar_m"] * 1e6)
        if self.bal("bank1") - amount < floor:
            self.sweep(d)
        short = floor - (self.bal("bank1") - amount)
        if short > 0:
            draw = min(self.headroom(), int(math.ceil(short / MILLION)) * MILLION)
            if draw > 0:
                self.rcf_move(d, draw)
        if self.bal("bank1") >= amount:
            return True
        if mandatory:
            rest = min(self.headroom(), int(math.ceil((amount - self.bal("bank1")) / MILLION)) * MILLION)
            if rest > 0:
                self.rcf_move(d, rest)
            if self.bal("bank1") < amount:
                self.warnings.append(f"{d}: cash short by {S(amount - self.bal('bank1'))} for a mandatory payment")
        return self.bal("bank1") >= amount

    def rcf_move(self, d, amount):
        """Draw (amount > 0) or repay (amount < 0) the revolving credit facility."""
        if amount == 0:
            return
        word = "drawdown" if amount > 0 else "repayment"
        self.b.journal(d, [("bank1", amount, f"RCF {word}"), ("rcf", -amount, f"RCF {word}")],
                       f"Revolving credit facility {word}", role="treasury", ref=f"RCF-{d:%y%m%d}", kind="bank")

    def can_afford(self, amount, reserve=0) -> bool:
        tr = self.p["treasury"]
        floor = H(tr["min_cash_sar_m"] * 1e6)
        return self.bal("bank1") + self.bal("bank2") + self.headroom() - floor - reserve >= amount

    def payment_run(self, d):
        self.sweep(d)
        reserve = self.next_payroll_net if 18 <= d.day <= 26 else 0
        stress = self.p["treasury"].get("stretch_when_short", True)
        due = []
        for b in self.open_bills:
            if b["_date"] > d or b.get("_fixed_pay"):
                continue
            pay_fc = self.bill_payable_fc(b)
            if pay_fc <= 0:
                continue
            lag = b["_vendor"].get("_pay_lag", 0)
            if b["_due"] + timedelta(days=lag) <= d + timedelta(days=2):
                due.append(b)
        due.sort(key=lambda b: (b["_due"], b["bill_id"]))
        by_vendor = defaultdict(list)
        order = []
        for b in due:
            vid = b["_vendor"]["contact_id"]
            if vid not in by_vendor:
                order.append(vid)
            by_vendor[vid].append(b)
        for vid in order:
            bills = by_vendor[vid]
            cur = bills[0]["currency_code"]
            same = [b for b in bills if b["currency_code"] == cur]
            rate_now = rate_to_sar(cur, d)
            need = sum(int(round(self.bill_payable_fc(b) * rate_now)) for b in same)
            if not self.can_afford(need, reserve):
                if not stress:
                    continue
                # short of cash: pay the oldest bills that fit, leave the rest overdue
                fit, run = [], 0
                for b in same:
                    a_ = int(round(self.bill_payable_fc(b) * rate_now))
                    if self.can_afford(run + a_, reserve):
                        fit.append(b)
                        run += a_
                    else:
                        break
                if not fit:
                    continue
                same, need = fit, run
            self.ensure_cash(d, need)
            if self.bal("bank1") < need:
                continue
            self.b.vendor_payment(d, same[0]["_vendor"], [(b, self.bill_payable_fc(b)) for b in same],
                                  rate_now=rate_now if cur != "SAR" else None)
        self.open_bills = [b for b in self.open_bills if self.b.bill_open_fc(b) > 0]
        # repay the revolving facility when cash is comfortably above target
        tr = self.p["treasury"]
        ceiling, target = H(tr["ceiling_sar_m"] * 1e6), H(tr["target_sar_m"] * 1e6)
        drawn = -self.bal("rcf")
        if drawn > 0 and self.bal("bank1") > ceiling:
            rep = min(drawn, (self.bal("bank1") - target) // MILLION * MILLION)
            if rep > 0:
                self.rcf_move(d, -rep)

    def release_bill_retention(self, d, bills, fraction=1.0):
        for b in bills:
            new = int(b["_retention"] * (1 - fraction)) if fraction < 1 else 0
            if new != b["_retention"]:
                b["_ret_hist"].append((d, b["_retention"] - new))
            b["_retention"] = new

    # ================================================================== collections
    def pay_delay(self, cust, due: date, rng) -> int:
        """Days after the due date: lognormal by customer class, scaled by the customer's habit, plus any
        planted story shift."""
        mu, sd = self.p["pay_delay"][cust["_class"]]
        base = lognormal(rng, (mu + 12) * cust.get("_habit", 1.0), sd) - 12
        return int(round(base + self.story_shift(cust, due + timedelta(days=int(base)))))

    def story_shift(self, cust, when: date) -> float:
        extra = 0.0
        for sid, st in self.stories.items():
            if st.get("kind") != "payment_delay" or when < date.fromisoformat(st["start"]):
                continue
            sel = st["selector"]
            hit = (sel == "tagged" and sid in cust.get("_tags", ())) or (sel.startswith("class:") and cust["_class"] == sel[6:])
            if hit:
                extra = max(extra, st["extra_days"])
        return extra

    def schedule_collection(self, inv, amount=None, bank="bank2", rng=None, when=None):
        cust = inv["_cust"]
        rng = rng or self.r("coll", inv["invoice_id"])
        if when is None:
            when = inv["_due"] + timedelta(days=self.pay_delay(cust, inv["_due"], rng))
            when = max(when, inv["_date"] + timedelta(days=rng.randint(3, 12)))
            pay_days = cust.get("_pay_days") or self.p.get("pay_days", {}).get(cust["_class"])
            if pay_days:
                while when.day not in pay_days:
                    when += timedelta(days=1)
            when = next_working(when)
        amt = inv["_total"] - inv["_retention"] if amount is None else amount
        if rng.random() < self.p.get("partial_p", {}).get(cust["_class"], 0.04):
            first = int(amt * rng.uniform(0.4, 0.85))
            self.b.schedule(when, lambda d, a=first: self.collect(d, inv, a, bank))
            later = next_working(when + timedelta(days=rng.randint(12, 55)))
            self.b.schedule(later, lambda d, a=amt - first: self.collect(d, inv, a, bank))
        else:
            self.b.schedule(when, lambda d, a=amt: self.collect(d, inv, a, bank))
        return when

    def collect(self, d, inv, amt, bank):
        key = (d, inv["_cust"]["contact_id"], bank)
        q = self.collect_q.setdefault(key, [])
        if not q:
            self.b.schedule(d, lambda day, key=key: self.flush_collect(day, key))
        q.append((inv, amt))

    def flush_collect(self, d, key):
        apps = []
        for inv, amt in self.collect_q.pop(key, []):
            a = min(amt, self.b.inv_open(inv) - min(inv["_retention"], self.b.inv_open(inv)))
            if a > 0:
                apps.append((inv, a))
        if apps:
            self.b.customer_payment(d, apps[0][0]["_cust"], apps, bank=key[2])

    def release_retention(self, d, invoices, fraction):
        """The customer releases part of the retention it holds on these invoices and pays it."""
        for inv in invoices:
            rel = min(inv["_retention"], int(round(inv["_retention_orig"] * fraction)))
            if fraction >= 1:
                rel = inv["_retention"]
            if rel <= 0:
                continue
            inv["_retention"] -= rel
            inv["_ret_hist"].append((d, rel))
            self.collect(d, inv, rel, "bank2")

    # ================================================================== loans in the run
    def loan_draw(self, d, ln):
        amt = H(ln["amount_sar_m"] * 1e6)
        self.b.journal(d, [("bank1", amt, f"{ln['name']} drawdown"), ("loan", -amt, f"{ln['name']} drawdown")],
                       f"{ln['name']} – drawdown", role="treasury", ref=f"LN-{d:%y%m%d}", kind="bank")
        ln["_out"] = amt

    def loan_repay(self, d, ln, p):
        p = min(p, ln["_out"])
        if p <= 0:
            return
        self.ensure_cash(d, p, mandatory=True)
        self.b.journal(d, [("loan", p, f"{ln['name']} instalment"), ("bank1", -p, f"{ln['name']} instalment")],
                       f"{ln['name']} – principal instalment", role="treasury", ref=f"LN-{d:%y%m%d}", kind="bank")
        ln["_out"] -= p

    # ================================================================== VAT, Zakat, dividends
    def vat_payment_day(self, y, m):
        ny, nm = add_months(y, m, 1)
        d = last_working_day(ny, nm)
        for _ in range(2):
            d = prev_working(d - timedelta(days=1))
        return d

    def pay_vat(self, d):
        amt = -self.bal("vat_payable")
        if amt <= 0:
            return
        self.ensure_cash(d, amt, mandatory=True)
        self.b.journal(d, [("vat_payable", amt, "VAT return payment"), ("bank1", -amt, "VAT payment (SADAD)")],
                       f"VAT return payment – {mlabel(*add_months(d.year, d.month, -1))}", role="treasury",
                       ref=f"VAT-{d:%Y%m}", kind="bank")

    def pay_zakat(self, d, year):
        amt = min(self.zakat_prov.get(year, 0), -self.bal("zakat_payable"))
        if amt <= 0:
            return
        self.ensure_cash(d, amt, mandatory=True)
        self.b.journal(d, [("zakat_payable", amt, f"Zakat for {year}"), ("bank1", -amt, "Zakat payment (SADAD)")],
                       f"Zakat payment for the year {year}", role="treasury", ref=f"ZKT-{year}", kind="bank")

    def year_profit(self, year) -> int:
        """Net profit after Zakat for a calendar year, from the ledger (credit-positive)."""
        pl = 0
        for ln in self.b.lines:
            if ln[0].year == year and self.b.chart[ln[1]].group in "ICXO":
                pl -= ln[2]
        return pl

    def declare_dividend(self, d):
        payout = self.p.get("dividend_payout", 0)
        prof = self.year_profit(d.year - 1)
        amt = int(prof * payout)
        sweep = self.p.get("excess_cash_dividend")
        if sweep:
            # cash well above what the business needs goes up to the holding company
            spare = self.bal("bank1") + self.bal("bank2") - H(self.p["treasury"]["ceiling_sar_m"] * 1e6) * sweep["keep_ceilings"]
            amt = max(amt, int(spare * sweep["share"]))
        amt = amt // H(100_000) * H(100_000)
        if amt <= 0:
            return
        self.b.journal(d, [("retained", amt, f"Dividend declared out of {d.year - 1} profit"),
                           ("dividends_payable", -amt, "Dividend payable to the shareholders")],
                       f"Dividend declared by the general assembly – {d.year - 1}", role="gl",
                       created_lag=self.r("divlag", d.year).choice([1, 2, 4]), ref=f"DIV-{d.year}", kind="dividend")

    def pay_dividend(self, d):
        amt = -self.bal("dividends_payable")
        if amt <= 0:
            return
        lim = H(self.p.get("rcf", {}).get("limit_sar_m", 0) * 1e6)
        drawn = -self.bal("rcf")
        if lim and drawn > 0.6 * lim:
            return  # deferred while the facility is heavily used
        if not self.can_afford(amt):
            return
        self.ensure_cash(d, amt, mandatory=True)
        self.b.journal(d, [("dividends_payable", amt, "Dividend paid"), ("bank1", -amt, "Dividend paid")],
                       "Dividend paid to the shareholders", role="treasury", ref=f"DIVP-{d:%Y%m}", kind="bank")

    # ================================================================== suspense
    def suspense_receipt(self, d):
        r = self.r("susp", d)
        amt = H(round(lognormal(r, 18_000, 15_000), 2))
        self.b.journal(d, [("bank2", amt, "Unidentified receipt"), ("suspense", -amt, "Unidentified receipt")],
                       "Unidentified bank receipt held in suspense", role="treasury", ref=f"SUS-{d:%y%m%d}",
                       kind="bank")
        clear = next_working(d + timedelta(days=r.randint(20, 110)))
        item = {"amount": amt, "clear": clear, "to": r.choice(["other_income", "other_income", "prepaid"])}
        self.suspense_open.append(item)
        self.b.schedule(clear, lambda day, it=item: self.suspense_clear(day, it))

    def suspense_clear(self, d, item):
        if item not in self.suspense_open:
            return
        self.suspense_open.remove(item)
        what = "Refund of tender bond deposit" if item["to"] == "other_income" else "Supplier refund applied to advance"
        self.b.journal(d, [("suspense", item["amount"], what), (item["to"], -item["amount"], what)],
                       f"Suspense cleared – {what.lower()}", role="gl", created_lag=2, ref="SUS-CLR", kind="adjustment")

    # ================================================================== month-end close
    def close_month(self, d: date):
        y, m = d.year, d.month
        r = self.r("close", y, m)
        lo, hi = self.p.get("close_days", (5, 10))
        lag = r.randint(lo, hi)
        self.close_log.append({"month": f"{y}-{m:02d}", "close_date": (d + timedelta(days=lag)).isoformat(),
                               "lag_days": lag})
        L = lambda: max(1, lag + r.choice([-1, 0, 0, 1]))
        self.close_sector(d, lag)
        # accruals: consumption overheads (reversed next month) and annual fees (cleared by the bill)
        acc = []
        for oh in self.p.get("overheads", []):
            if oh["freq"] == "monthly_arrears":
                acc.append((oh["account"], self.overhead_usage(oh, y, m), f"Accrual: {oh['label']} {mlabel(y, m)}"))
        if acc:
            total = sum(a for _, a, _ in acc)
            self.b.journal(d, acc + [("accrued", -total, "Accrued expenses")], f"Month-end accruals – {mlabel(y, m)}",
                           created_lag=L(), ref=f"ACR-{y}{m:02d}", kind="accrual")
            rev = [(k, -a, ds.replace("Accrual", "Reversal")) for k, a, ds in acc] + [("accrued", total, "Reversal")]
            ny, nm = add_months(y, m, 1)
            lag1 = L() - 1
            self.b.schedule(date(ny, nm, 1), lambda day, rev=rev, lag1=lag1, y=y, m=m: self.b.journal(
                day, rev, f"Reversal of month-end accruals – {mlabel(y, m)}", created_lag=max(0, lag1),
                ref=f"ACR-{y}{m:02d}-R", kind="reversal"))
        fees = []
        for oh in self.p.get("overheads", []):
            if oh["freq"] == "annual_accrued":
                a = int(H(oh["annual_sar_m"] * 1e6) * self.trend(d) ** oh.get("scale", 0.3) / 12)
                self.accrued_fee[(oh["key"], y)] += a
                fees.append((oh["account"], a, f"Accrual: {oh['label']} {y}"))
        if fees:
            self.b.journal(d, fees + [("accrued", -sum(a for _, a, _ in fees), "Accrued fees")],
                           f"Accrued professional fees – {mlabel(y, m)}", created_lag=L(), ref=f"FEE-{y}{m:02d}",
                           kind="accrual")
        # prepayments released
        pre = [x for x in self.prepaids if x["y"] == y and x["m"] == m]
        if pre:
            lines = [(x["account"], x["amount"], f"Release of prepaid {x['key'].replace('_', ' ')}") for x in pre]
            self.b.journal(d, lines + [("prepaid", -sum(x["amount"] for x in pre), "Prepayments released")],
                           f"Prepayments released – {mlabel(y, m)}", created_lag=L(), ref=f"PRE-{y}{m:02d}",
                           kind="prepaid")
        # depreciation
        dep = int(self.bal("ppe_cost") * self.p.get("dep_rate", 0.12) / 12)
        nbv = self.bal("ppe_cost") + self.bal("ppe_dep")
        dep = max(0, min(dep, nbv))
        self.b.journal(d, [("depr", dep, "Depreciation for the month"), ("ppe_dep", -dep, "Accumulated depreciation")],
                       f"Depreciation – {mlabel(y, m)}", created_lag=L(), ref=f"DEP-{y}{m:02d}", kind="depreciation")
        # end-of-service benefits: accrual and payments to leavers
        gross = getattr(self, "month_gross", 0)
        eos = int(gross * self.p.get("eosb_rate", 0.045))
        self.b.journal(d, [("eosb_exp", eos, "End-of-service accrual"), ("eosb", -eos, "End-of-service provision")],
                       f"End-of-service benefits accrual – {mlabel(y, m)}", created_lag=L(), ref=f"EOS-{y}{m:02d}",
                       kind="accrual")
        leavers = int(-self.bal("eosb") * self.p.get("leaver_rate", 0.11) / 12 * clamp(r.gauss(1, 0.25), 0.3, 1.8))
        if leavers > 0:
            self.ensure_cash(d, leavers, mandatory=True)
            self.b.journal(d, [("eosb", leavers, "Final settlements"), ("bank1", -leavers, "Final settlements")],
                           f"End-of-service final settlements – {mlabel(y, m)}", role="payroll", created_lag=1,
                           ref=f"EOSP-{y}{m:02d}", kind="bank")
        # interest debited by the banks
        lines = []
        for ln in self.loans:
            if ln["_out"] > 0:
                i = int(ln["_out"] * (saibor(d) + ln["margin"]) * dim(y, m) / 360)
                lines.append(("interest", i, f"{ln['name']} interest"))
        rc = self.p.get("rcf")
        if rc:
            avg = self.rcf_days[(y, m)] / dim(y, m)
            i = int(avg * (saibor(d) + rc["margin"]) * dim(y, m) / 360)
            fee = int((H(rc["limit_sar_m"] * 1e6) - avg) * rc.get("commitment_fee", 0.002) * dim(y, m) / 360)
            lines += [("interest", i, "RCF interest"), ("interest", max(0, fee), "RCF commitment fee")]
        tot = sum(a for _, a, _ in lines)
        if tot > 0:
            self.ensure_cash(d, tot, mandatory=True)
            self.b.journal(d, lines + [("bank1", -tot, "Interest debited by the bank")],
                           f"Bank interest – {mlabel(y, m)}", role="treasury", created_lag=r.choice([1, 2, 3]),
                           ref=f"INT-{y}{m:02d}", kind="bank")
        # VAT return
        out_, in_ = -self.bal("vat_out"), self.bal("vat_in")
        net = out_ - in_
        self.b.journal(d, [("vat_out", out_, "Output VAT for the period"), ("vat_in", -in_, "Input VAT for the period"),
                           ("vat_payable", -net, "Net VAT for the period")],
                       f"VAT return – {mlabel(y, m)}", created_lag=L(), ref=f"VATR-{y}{m:02d}", kind="vat")
        self.b.schedule(self.vat_payment_day(y, m), self.pay_vat)
        # Zakat
        self.close_zakat(d, L())
        # expected credit losses, quarterly
        if m in (3, 6, 9, 12):
            self.close_ecl(d, L())

    def zakat_base(self) -> int:
        bal = self.b.bal
        equity = -(bal["share_capital"] + bal["stat_reserve"] + bal["retained"])
        equity -= sum(v for k, v in bal.items() if self.b.chart[k].group in "ICXO")
        noncur = -(bal["loan"] + bal["eosb"] + bal.get("lease_liab", 0))
        fixed = bal["ppe_cost"] + bal["ppe_dep"] + bal.get("rou", 0) + bal.get("rou_dep", 0)
        return max(0, equity + noncur - fixed)

    def close_zakat(self, d, lag):
        y, m = d.year, d.month
        fy_end = self.p.get("year_end_month", 12)
        base = self.zakat_base()
        acc = int(base * 0.025 / 12)
        self.zakat_accrued[y] += acc
        lines = [("zakat_exp", acc, "Zakat provision for the month"), ("zakat_payable", -acc, "Zakat provision")]
        note = f"Zakat provision – {mlabel(y, m)}"
        if m == fy_end:
            profit = self.year_profit(y) + (self.zakat_accrued[y] - acc)
            need = int(max(base, profit) * 0.025)
            true_up = need - self.zakat_accrued[y]
            lines = [("zakat_exp", acc + true_up, "Zakat provision incl. year-end true-up"),
                     ("zakat_payable", -(acc + true_up), "Zakat provision")]
            self.zakat_prov[y] = need
            self.zakat_accrued[y] = need
            note = f"Zakat provision – {mlabel(y, m)} with year-end true-up"
            self.b.schedule(prev_working(date(y + 1, 4, 30)), lambda dd, yy=y: self.pay_zakat(dd, yy))
        self.b.journal(d, lines, note, created_lag=lag, ref=f"ZKP-{y}{m:02d}", kind="zakat")

    def ecl_target(self, d) -> int:
        rates = self.p.get("ecl_rates", [0.004, 0.015, 0.05, 0.15, 0.35, 0.6])
        bounds = [0, 30, 90, 180, 365, 730]
        tot = 0
        for inv in self.b.docs["invoices"]:
            o = self.b.inv_open(inv)
            if o <= 0 or inv["_date"] > d:
                continue
            held = min(o, inv["_retention"])
            tot += int(held * rates[0] * 0.5)
            o -= held
            past = (d - inv["_due"]).days
            i = 0
            for k, bd in enumerate(bounds):
                if past > bd:
                    i = k
            tot += int(o * rates[min(i, len(rates) - 1)] * (1 if past > 0 else 0.5))
        return tot

    def close_ecl(self, d, lag):
        target = self.ecl_target(d)
        delta = target - (-self.bal("ecl_allow"))
        if delta:
            self.b.journal(d, [("ecl_exp", delta, "Movement in the loss allowance"),
                               ("ecl_allow", -delta, "Allowance for expected credit losses")],
                           f"Expected credit loss allowance – {mlabel(d.year, d.month)}", created_lag=lag,
                           ref=f"ECL-{d:%Y%m}", kind="ecl")
