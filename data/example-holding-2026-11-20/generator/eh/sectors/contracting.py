"""A building and infrastructure contractor.

Revenue is the work done on projects (progress on an S-curve, slowed by Ramadan hours, Eid shutdowns and
the summer midday work ban). Work not yet certified at month end is accrued as unbilled revenue and
reversed on the first of the next month; the consultant certifies each month's work 2 to 8 weeks later and
the company raises an interim payment certificate (IPC) invoice. The customer withholds 10% retention, half
released at handover and half after the 12-month defects period. Costs: material deliveries, subcontractor
IPCs (with 10% retention withheld), plant hire, and site staff through payroll.
"""
import math
from datetime import date, timedelta

from ..calendar_ksa import (in_eid_adha, in_eid_fitr, in_ramadan, is_working_day, next_working)
from ..common import CompanySim, mlabel
from ..intercompany import ic_flows
from ..names import CON_GOV, CON_PRIVATE, CON_SEMI, CON_VENDORS, FM_VENDORS
from ..util import H, S, add_months, clamp, dim, lognormal, month_end, months, stamp

MATERIALS = [("Reinforcement steel bars 16 mm", "t", 2750), ("Reinforcement steel bars 25 mm", "t", 2690),
             ("Ready-mix concrete C40", "m³", 265), ("Ready-mix concrete C30", "m³", 238),
             ("Cement OPC 50 kg", "bag", 16.5), ("Concrete blocks 20 cm", "pc", 3.2),
             ("Ductile iron pipes DN300", "m", 410), ("uPVC pipes 160 mm", "m", 62),
             ("Electrical cables 4C×95 mm²", "m", 185), ("Cable trays 300 mm", "m", 96),
             ("Aluminium windows", "m²", 640), ("Gypsum boards 12.5 mm", "m²", 28),
             ("Porcelain tiles 60×60", "m²", 48), ("Emulsion paint", "drum", 165),
             ("Waterproofing membrane", "roll", 420), ("Timber formwork", "m²", 75),
             ("Structural steel sections", "t", 4150), ("Insulation boards 50 mm", "m²", 39)]
PLANT = [("Mobile crane 50 t hire", "day", 2400), ("Excavator hire", "day", 1350), ("Tower crane rental", "month", 48000),
         ("Concrete pump hire", "day", 3100), ("Generator 500 kVA rental", "month", 16500),
         ("Scaffolding rental", "m²·month", 11)]
TRADES = ["MEP", "earthworks", "façade", "finishing", "piling", "HVAC", "waterproofing", "steel erection",
          "landscaping", "electrical"]
GOV_WORKS = ["Primary Health Care Centre", "School Building", "Water Network Rehabilitation", "Municipal Roads Upgrade",
             "Storm Water Drainage", "Government Housing Units", "Public Park and Walkway", "Sports Complex",
             "Pumping Station", "Hospital Extension Wing"]
FM_WORKS = ["Integrated Facility Management – Hospitals Cluster", "Cleaning and Housekeeping – Schools Package",
            "MEP Maintenance – Government Offices", "Security and Guarding Services", "Soft Services – Business Park",
            "Operation and Maintenance – Housing Compound", "Pest Control and Waste Management",
            "HVAC Operation and Maintenance – Mall"]
FM_MATERIALS = [("Cleaning chemicals", "drum", 210), ("HVAC spare parts", "set", 1450), ("Electrical spares", "box", 380),
                ("Plumbing spares", "box", 260), ("Lamps and fittings", "box", 320), ("Paper and hygiene supplies", "carton", 145),
                ("Staff uniforms", "set", 95), ("Pest control chemicals", "pail", 340)]
FM_PLANT = [("Pickup vehicle rental", "month", 3800), ("Cherry picker hire", "day", 900), ("Floor scrubber rental", "month", 2600)]
FM_TRADES = ["lift maintenance", "pest control", "landscaping", "waste collection", "fire systems maintenance"]
PRIV_WORKS = ["Mixed-use Tower", "Warehouse Complex", "Residential Compound", "Shopping Centre Extension",
              "Office Building", "Hotel Fit-out and Structure", "Private School Campus", "Medical Centre",
              "Logistics Park Phase", "Villas Community"]


def scurve(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


class ContractingSim(CompanySim):
    sector = "contracting"

    # ------------------------------------------------------------------ setup
    def prog(self, t: float) -> float:
        return clamp(t, 0.0, 1.0) if self.p.get("profile") == "flat" else scurve(t)

    def setup(self):
        p = self.p
        r = self.r("setup")
        fm = p.get("variant") == "fm"
        self.L = {"materials": FM_MATERIALS if fm else MATERIALS, "plant": FM_PLANT if fm else PLANT,
                  "trades": FM_TRADES if fm else TRADES, "gov": FM_WORKS if fm else GOV_WORKS,
                  "priv": FM_WORKS if fm else PRIV_WORKS, "word": "Service contract" if fm else "Lump-sum contract"}
        self.customers = []
        n = 0
        for cls, pool in (("government", CON_GOV), ("semi", CON_SEMI), ("private", CON_PRIVATE)):
            for name in pool[:p["customers"][cls]]:
                n += 1
                c = self.b.add_contact(
                    name, "customer", cls, p["terms"][cls], date(2016 + n % 6, 1 + n % 12, 5 + n % 20),
                    vat_no=f"TEST-VAT-{self.c['org_num']:02d}{n:04d}",
                    cr_no="" if cls == "government" else f"TEST-CR-{self.c['org_num']:02d}{n:04d}",
                    city=r.choice(["Riyadh", "Riyadh", "Jeddah", "Dammam", "Makkah", "Madinah", "Qassim", "Abha", "Tabuk"]))
                c["_habit"] = clamp(lognormal(r, 1.0, 0.22), 0.6, 1.6)
                c["_weight"] = r.paretovariate(1.3)
                c["_tags"] = set()
                self.customers.append(c)
        st = self.story("S1")
        if st:
            gov = sorted([c for c in self.customers if c["_class"] == "government"], key=lambda c: -c["_weight"])
            for c in gov[:st.get("customers", 2)]:
                c["_tags"].add("S1")
                c["_weight"] *= st.get("weight_boost", 1.0)
        self.mat_vendors, self.sub_vendors, self.plant_vendors = [], [], []
        for kind, pool, terms, lag in (("materials", self.mat_vendors, 60, (0, 12)),
                                       ("subcontract", self.sub_vendors, 45, (5, 25)),
                                       ("plant", self.plant_vendors, 30, (0, 8))):
            for name in (FM_VENDORS if fm else CON_VENDORS)[kind]:
                n += 1
                v = self.b.add_contact(name, "vendor", "private", terms, date(2015 + n % 7, 1 + n % 12, 3),
                                       vat_no=f"TEST-VAT-{self.c['org_num']:02d}{n:04d}",
                                       cr_no=f"TEST-CR-{self.c['org_num']:02d}{n:04d}",
                                       prefix="".join(w[0] for w in name.split()[:2]).upper())
                v["_pay_lag"] = r.randint(*lag)
                v["_weight"] = r.paretovariate(1.6)
                pool.append(v)
        # intercompany purchases from group companies (paid on the agreed schedule, outside the payment runs)
        self.ic = []
        names = {x["code"]: x["legal_name"] for x in self.g["companies"]}
        for spec in self.g.get("intercompany", []):
            if spec["buyer"] == self.code:
                v = self.b.add_contact(names.get(spec["seller"], spec["seller"]), "vendor", "intercompany", spec["terms"],
                                       date(2019, 1, 15), vat_no=f"TEST-VAT-{spec['seller'][-2:]}0000",
                                       cr_no=f"TEST-CR-{spec['seller'][-2:]}0000", group_company=spec["seller"], prefix="EBM")
                v["_pay_lag"] = 0
                self.ic.append((v, spec, ic_flows(self.g, spec["seller"], self.code)))
        # S7: integrity patterns planted in the ledger
        st7 = self.story("S7")
        self.s7 = None
        if st7:
            r7 = self.r("s7")
            start = date.fromisoformat(st7["start"])
            days = [start + timedelta(days=i) for i in range((date.fromisoformat(st7["late_until"]) - start).days)]
            late = sorted(r7.sample([x for x in days if is_working_day(x) and x.day >= 20], st7["late_journals"]))
            thu = [x for x in days + [days[-1] + timedelta(days=i) for i in range(1, (self.data_end - days[-1]).days - 1)]
                   if x.weekday() == 3 and is_working_day(x)]
            fri = sorted(r7.sample(thu, min(len(thu), st7["friday_postings"])))
            self.s7 = {"start": start, "late": late, "fri": fri, "vendor": self.mat_vendors[0], "st": st7}
        self.projects = []
        self.pending = []          # uncertified work: dicts(project, y, m, work, cert_date)
        self.cal_norm = self.calendar_norm()
        self.person_adv_open = 0

    def calendar_raw(self, y, m) -> float:
        w = 0.0
        summer_lo, summer_hi = date(y, 6, 15), date(y, 9, 15)
        cal = self.p["calendar"]
        for k in range(1, dim(y, m) + 1):
            d = date(y, m, k)
            x = 0.3 if d.weekday() == 4 else 1.0          # Friday is a light day on site
            if in_eid_fitr(d) or in_eid_adha(d):
                x *= cal["eid"]
            elif in_ramadan(d):
                x *= cal["ramadan"]
            if summer_lo <= d <= summer_hi:
                x *= cal["summer"]
            w += x
        return w / dim(y, m) * 30.4

    def calendar_norm(self) -> float:
        vals = [self.calendar_raw(y, m) for y in range(2021, 2027) for m in range(1, 13)]
        return sum(vals) / len(vals)

    def calendar_factor(self, y, m) -> float:
        return self.calendar_raw(y, m) / self.cal_norm

    def choose_customer(self, r, cls):
        pool = [c for c in self.customers if c["_class"] == cls]
        tot = sum(c["_weight"] for c in pool)
        x = r.random() * tot
        for c in pool:
            x -= c["_weight"]
            if x <= 0:
                return c
        return pool[-1]

    # ------------------------------------------------------------------ projects
    def new_project(self, award: date, cust, value: int, months_: int, start: date, done: float = 0.0):
        r = self.r("project", len(self.projects))
        p = self.p
        bid = clamp(r.gauss(*p["bid_margin"]), 0.09, 0.28)
        fade = r.gauss(*p["margin_fade"])
        works = self.L["gov"] if cust["_class"] != "private" else self.L["priv"]
        code = f"P{award.year % 100:02d}-{len(self.projects) + 1:03d}"
        name = f"{r.choice(works)} – {r.choice(['Package', 'Phase', 'Lot', 'Contract'])} {r.randint(1, 14)}"
        pid = self.b.new_id("project")
        proj = {
            "project_id": pid, "project_name": f"{code} {name}", "project_code": code,
            "customer_id": cust["contact_id"], "customer_name": cust["contact_name"],
            "description": f"{self.L['word']} for {name.lower()} for {cust['contact_name']}.",
            "billing_type": "fixed_cost_for_project", "currency_code": "SAR",
            "created_time": stamp(award, r), "_award": award, "_start": start, "_months": months_,
            "_value": value, "_orig": value, "_bid": bid, "_fade": fade, "_done": done, "_pace": clamp(r.gauss(0.97, 0.07), 0.8, 1.1),
            "_cust": cust, "_invoices": [], "_subbills": [], "_complete": None, "_ipc": 0, "_sub_ipc": 0,
            "_subs": r.sample(self.sub_vendors, 2), "_mats": r.sample(self.mat_vendors, 4),
            "_plant": r.choice(self.plant_vendors), "_trades": r.sample(self.L["trades"], 2), "_billed": 0, "_work": 0,
        }
        self.projects.append(proj)
        self.b.docs["projects"].append(proj)
        self.truth["awards"].append({"project": code, "award": award.isoformat(), "start": start.isoformat(),
                                     "value": value, "customer": cust["contact_name"], "class": cust["_class"],
                                     "bid_margin": round(bid, 4), "months": months_})
        return proj

    def margin_now(self, proj) -> float:
        return proj["_bid"] + proj["_fade"] * min(1.0, proj["_done"] * 1.3)

    def plan_progress(self, proj, y, m, cal) -> int:
        st = proj["_start"]
        if (y, m) < (st.year, st.month) or proj["_complete"]:
            return 0
        k = (y - st.year) * 12 + (m - st.month)
        T = proj["_months"]
        if k < T:
            planned = self.prog((k + 1) / T) - self.prog(k / T)
        else:
            planned = max(0.03, 1.2 / T)
        r = self.r("prog", proj["project_id"], y, m)
        frac = planned * cal * proj["_pace"] * lognormal(r, 1.0, 0.13)
        left = 1.0 - proj["_done"]
        frac = min(frac, left)
        if left - frac < 0.006:
            frac = left
        proj["_done"] += frac
        work = int(frac * proj["_value"])
        if proj["_done"] >= 1.0 - 1e-9:
            proj["_complete"] = month_end(y, m)
        return work

    # ------------------------------------------------------------------ opening position
    def opening(self, d0: date):
        """The order book at the opening date comes from three years of awards run through the same
        process, so running projects, recently finished ones (open certificates, retention) and awarded
        but not started ones appear in their steady-state proportions."""
        p = self.p
        r = self.r("opening")
        for i in range(36, 0, -1):
            y, m = add_months(d0.year, d0.month, -i + 1)
            lam = p["awards_per_month"] * self.trend(date(y, m, 15)) ** 0.5
            for _ in range(self.poisson(r, lam)):
                cls = r.choices(list(p["award_mix"]), weights=list(p["award_mix"].values()))[0]
                cust = self.choose_customer(r, cls)
                value = H(clamp(lognormal(r, *p["project_size_sar_m"]), *p["project_size_clamp"]) * 1e6
                          * self.trend(date(y, m, 15)) ** 0.5)
                months_ = r.randint(*p["duration_months"])
                award = date(y, m, r.randint(1, 28))
                sy, sm = add_months(y, m, r.randint(1, 3))
                start = date(sy, sm, 1)
                if start > d0:
                    self.new_project(award, cust, value, months_, start)
                    continue
                k = (d0.year - sy) * 12 + (d0.month - sm) + 1
                if k >= months_:
                    ended = month_end(*add_months(sy, sm, months_ - 1))
                    if (d0 - ended).days > 365 + 150:
                        continue
                    proj = self.new_project(award, cust, value, months_, start, done=1.0)
                    proj["_complete"] = ended
                    self.open_history(proj, d0, months_, r, ended=ended)
                else:
                    proj = self.new_project(award, cust, value, months_, start, done=self.prog(k / months_))
                    self.open_history(proj, d0, k, r)
        for v, spec, flows in self.ic:
            for f in flows:
                if f["date"] >= self.start and not f["unbooked"]:
                    self.b.schedule(f["date"], lambda d, v=v, spec=spec, f=f: self.ic_bill(d, v, spec, f))
        if self.s7:
            for d in self.s7["late"]:
                self.b.schedule(d, self.s7_late_journal)
            for d in self.s7["fri"]:
                self.b.schedule(d, self.s7_friday_journal)
        # unbilled work at the opening date, reversed on 1 January
        acc = sum(x["work"] for x in self.pending)
        self.b.post(d0, [("contract_assets", acc), ("retained", -acc)], "opening", "opening-wip")
        self.b.schedule(self.start, lambda d, a=acc: self.b.journal(
            d, [("rev_contract", a, "Reversal of unbilled work"), ("contract_assets", -a, "Reversal of unbilled work")],
            f"Reversal of unbilled revenue accrual – {mlabel(d0.year, d0.month)}", created_lag=8, kind="reversal"))

    def open_history(self, proj, d0, k, r, ended=None):
        """Create the documents of a project that are still open at the opening date: certificates not yet
        paid, retention withheld on the paid ones, the last supplier bills and subcontract retention."""
        p = self.p
        cls = proj["_cust"]["_class"]
        T = proj["_months"]
        st = proj["_start"]
        paid_net = 0
        for j in range(k):
            y, m = add_months(st.year, st.month, j)
            work = int((self.prog((j + 1) / T) - self.prog(j / T)) * proj["_value"])
            proj["_work"] += work
            cert = next_working(month_end(y, m) + timedelta(days=int(lognormal(r, *p["certify_lag_days"][cls]))))
            if cert > d0:
                item = {"project": proj, "y": y, "m": m, "work": work, "cert": cert}
                self.pending.append(item)
                self.b.schedule(cert, lambda day, it=item: self.certify(day, it))
                continue
            due = cert + timedelta(days=p["terms"][cls])
            pay = due + timedelta(days=self.pay_delay(proj["_cust"], due, r))
            net = work
            proj["_billed"] += net
            proj["_ipc"] += 1
            if pay <= d0:
                paid_net += net
                continue
            ret = int(net * p["retention"])
            inv = self.b.invoice(cert, proj["_cust"], [{"name": f"Interim Payment Certificate No. {proj['_ipc']}",
                                                        "desc": f"Work done to {mlabel(y, m)}, {proj['project_code']}",
                                                        "qty": 1, "rate": net, "account": "rev_contract"}],
                                 project_id=proj["project_id"], opening=True, retention=ret,
                                 ref=f"{proj['project_code']}/IPC-{proj['_ipc']:02d}",
                                 notes=f"Retention {int(p['retention'] * 100)}% (SAR {S(ret):,.2f}) withheld per contract.")
            proj["_invoices"].append(inv)
            self.schedule_collection(inv, rng=r, when=next_working(pay))
        first_done = bool(ended and (d0 - ended).days > 120)
        if paid_net and p["retention"] > 0:
            held = int(paid_net * p["retention"] * (0.5 if first_done else 1.0))
            inv = self.b.invoice(min(st + timedelta(days=45), d0), proj["_cust"],
                                 [{"name": "Retention brought forward", "desc": f"Retention held on certified works, {proj['project_code']}",
                                   "qty": 1, "rate": held, "account": "rev_contract", "vat": False}],
                                 project_id=proj["project_id"], opening=True, retention=held,
                                 number=f"RET-BF-{proj['project_code']}",
                                 notes="Migrated balance: retention withheld by the client on earlier certificates.")
            inv["_retention_orig"] = int(held / (0.5 if first_done else 1.0))
            proj["_invoices"].append(inv)
        if ended:
            self.schedule_releases(proj, first_done=first_done)
        # suppliers: bills of the last two months are still open
        for j in range(max(0, k - 2), k):
            y, m = add_months(st.year, st.month, j)
            if month_end(y, m) < d0 - timedelta(days=75):
                continue
            work = int((self.prog((j + 1) / T) - self.prog(j / T)) * proj["_value"])
            self.month_costs(proj, y, m, work, opening_date=min(d0, month_end(y, m)))
        if ended and (d0 - ended).days > 100:
            return
        sub_hist = int(proj["_work"] * self.cost_split(proj)["subcontract"] * 0.85)
        if sub_hist > 0 and p["retention"] > 0:
            v = proj["_subs"][0]
            held = int(sub_hist * p["retention"])
            b = self.post_bill(min(st + timedelta(days=60), d0), v, [{"name": "Subcontract retention brought forward",
                                                              "desc": f"Retention withheld on earlier subcontract IPCs, {proj['project_code']}",
                                                              "qty": 1, "rate": held, "account": "subcontract", "vat": False}],
                               opening=True, retention=held, number=f"SRET-BF-{proj['project_code']}", project_id=proj["project_id"])
            proj["_subbills"].append(b)

    # ------------------------------------------------------------------ costs
    def cost_split(self, proj) -> dict:
        p = self.p
        bills_share = 1.0 - self.margin_now(proj) - p["labour_share"]
        mix = p["cost_mix"]
        tot = sum(mix.values())
        return {k: bills_share * v / tot for k, v in mix.items()}

    def month_costs(self, proj, y, m, work, opening_date=None):
        """Bills for one project-month: material deliveries, subcontractor IPCs and plant hire."""
        if work <= 0:
            return
        r = self.r("costs", proj["project_id"], y, m)
        split = self.cost_split(proj)
        noise = lambda: lognormal(r, 1.0, 0.08)
        days = [d for d in self.working_days(y, m)] or [date(y, m, 15)]
        if opening_date:
            days = [d for d in days if d <= opening_date] or [opening_date]
        op = opening_date is not None

        # materials: one to five deliveries
        mat = int(work * split["direct_materials"] * noise() * self.p.get("materials_scale", 1.0))
        n = min(5, 1 + int(r.expovariate(1.0) * mat / H(1_800_000)))
        parts = [r.random() + 0.3 for _ in range(n)]
        for share in parts:
            amt = int(mat * share / sum(parts))
            if amt < H(500):
                continue
            v = r.choices(proj["_mats"], weights=[x["_weight"] for x in proj["_mats"]])[0]
            lines = []
            picks = r.sample(self.L["materials"], r.randint(1, 3))
            sub_parts = [r.random() + 0.2 for _ in picks]
            for (nm, unit, price), sp in zip(picks, sub_parts):
                val = amt * sp / sum(sub_parts)
                rate = H(price * lognormal(r, 1.0, 0.04))
                qty = max(1, int(round(val / rate)))
                lines.append({"name": nm, "desc": f"Delivered to site, {proj['project_code']}", "qty": qty,
                              "rate": rate, "unit": unit, "account": "direct_materials"})
            self.later(r.choice(days), proj, False, v, lines, opening=op, project_id=proj["project_id"],
                       created_lag=r.choice([0, 1, 2, 3, 6, 10]), ref=f"DN-{r.randint(10000, 99999)}")
        # subcontractors: monthly IPC with retention
        sub = int(work * split["subcontract"] * noise())
        if sub > 0:
            for i, v in enumerate(proj["_subs"]):
                amt = int(sub * (0.62 if i == 0 else 0.38))
                proj["_sub_ipc"] += 1
                held = int(amt * self.p["retention"])
                day = max([d for d in days if d.day >= 22] or days[-1:])
                self.later(day, proj, True, v, [{"name": f"Subcontract IPC No. {proj['_sub_ipc']}",
                                                 "desc": f"{proj['_trades'][i].capitalize()} works {mlabel(y, m)}, {proj['project_code']}",
                                                 "qty": 1, "rate": amt, "account": "subcontract"}],
                           opening=op, retention=held, project_id=proj["project_id"],
                           created_lag=r.choice([2, 4, 6, 9, 14]),
                           notes=f"Retention {int(self.p['retention'] * 100)}% withheld (SAR {S(held):,.2f})." if held else "")
        # plant hire
        pl = int(work * split["other_direct"] * noise())
        if pl > H(1000):
            nm, unit, price = r.choice(self.L["plant"])
            rate = H(price)
            qty = max(1, int(round(pl / rate)))
            self.later(days[-1], proj, False, proj["_plant"], [{"name": nm, "desc": f"{mlabel(y, m)}, {proj['project_code']}",
                                                                "qty": qty, "rate": rate, "unit": unit, "account": "other_direct"}],
                       opening=op, project_id=proj["project_id"], created_lag=r.choice([1, 3, 5]))

    def later(self, day, proj, is_sub, vendor, lines, **kw):
        """Post a bill on its own date: now for the opening position, otherwise on the day it arrives."""
        def _post(d, day=day):
            b = self.post_bill(day if kw.get("opening") else d, vendor, lines, **kw)
            if is_sub:
                proj["_subbills"].append(b)
        if kw.get("opening"):
            _post(day)
        else:
            self.b.schedule(day, _post)

    # ------------------------------------------------------------------ the month
    def activity(self, y, m) -> float:
        w = getattr(self, "_activity", {}).get((y, m))
        if w is None:
            return self.trend(date(y, m, 15))
        return w

    def month_start(self, d: date):
        y, m = d.year, d.month
        p = self.p
        r = self.r("cmonth", y, m)
        cal = self.calendar_factor(y, m)
        base = H(p["revenue_sar_m"] * 1e6) / 12
        total = 0
        self.month_work = []
        for proj in self.projects:
            if proj["_complete"]:
                continue
            # occasional approved variation
            if proj["_done"] > 0.15 and r.random() < p.get("variation_rate", 0.025):
                add = int(proj["_value"] * r.uniform(0.02, 0.08))
                before = proj["_value"]
                proj["_value"] += add
                proj["_done"] = proj["_done"] * before / proj["_value"]
            work = self.plan_progress(proj, y, m, cal)
            if work <= 0:
                continue
            proj["_work"] += work
            total += work
            self.month_work.append((proj, work))
            self.month_costs(proj, y, m, work)
            if proj["_complete"]:
                self.schedule_releases(proj)
        if not hasattr(self, "_activity"):
            self._activity = {}
        self._activity[(y, m)] = total / base if base else 1.0
        self.truth["work"].append({"month": f"{y}-{m:02d}", "work": total, "calendar_factor": round(cal, 4),
                                   "active_projects": len(self.month_work)})
        # new awards keep the order book near its target
        backlog = sum(pr["_value"] - pr["_work"] for pr in self.projects if not pr["_complete"])
        target = H(p["revenue_sar_m"] * 1e6) * self.trend(d) * p["backlog_years"]
        lam = p["awards_per_month"] * self.trend(d) ** 0.5 * clamp((target / max(backlog, 1)) ** 2, 0.25, 2.5)
        k = self.poisson(r, lam)
        for _ in range(k):
            cls = r.choices(list(p["award_mix"]), weights=list(p["award_mix"].values()))[0]
            cust = self.choose_customer(r, cls)
            value = H(clamp(lognormal(r, *p["project_size_sar_m"]), *p["project_size_clamp"]) * 1e6 * self.trend(d) ** 0.5)
            months_ = r.randint(*p["duration_months"])
            award = self.pick_working(r, y, m)
            sy, sm = add_months(y, m, r.randint(1, 3))
            self.b.schedule(award, lambda day, c=cust, v=value, mo=months_, s=date(sy, sm, 1):
                            self.new_project(day, c, v, mo, s))
        if self.s7 and d >= self.s7["start"]:
            self.s7_split_bills(d)
        # a cash advance to the site manager every few months, settled later with receipts
        if r.random() < p.get("person_advance_rate", 0.3):
            self.b.schedule(self.pick_working(r, y, m), self.person_advance)

    @staticmethod
    def poisson(r, lam) -> int:
        L, k, x = math.exp(-lam), 0, 1.0
        while True:
            x *= r.random()
            if x <= L:
                return k
            k += 1

    def person_advance(self, d):
        r = self.r("padv", d)
        amt = H(r.choice([20000, 25000, 30000, 40000, 50000, 60000, 75000]))
        self.b.journal(d, [("person_adv", amt, "Cash advance for site expenses"), ("bank1", -amt, "Cash advance")],
                       "Cash advance – site expenses", role="treasury", ref=f"CA-{d:%y%m%d}", kind="bank")
        settle = next_working(d + timedelta(days=r.randint(25, 80)))
        used = int(amt * r.uniform(0.75, 0.98))

        def _settle(day, used=used):
            a1 = int(used * 0.8)
            self.b.journal(day, [("other_direct", a1, "Site expenses per receipts"), ("ga", used - a1, "Office expenses per receipts"),
                                 ("person_adv", -used, "Settlement of cash advance")],
                           "Settlement of cash advance – site expenses", role="gl", created_lag=r.choice([1, 3, 7]),
                           ref=f"CAS-{day:%y%m%d}", kind="adjustment")
        self.b.schedule(settle, _settle)

    # ------------------------------------------------------------------ intercompany and S7
    def ic_bill(self, d, v, spec, f):
        b = self.b.bill(d, v, [{"name": f"Building materials as per delivery note {f['dn']}", "qty": 1, "rate": f["net"],
                                "account": "direct_materials"}], terms=spec["terms"], number=f["dn"], ref=f["dn"],
                        created_lag=self.r("iclag", f["n"]).choice([1, 2, 4, 7]))
        b["_fixed_pay"] = True
        if f["paid"]:
            def _pay(day, b=b):
                amt = self.b.bill_open_fc(b)
                self.ensure_cash(day, amt, mandatory=True)
                self.b.vendor_payment(day, v, [(b, amt)])
            self.b.schedule(f["paid"], _pay)

    def s7_split_bills(self, d):
        """Purchases split into bills just below the approval limit."""
        r = self.r("s7split", d)
        lim = self.s7["st"]["limit_sar"]
        for _ in range(r.randint(*self.s7["st"]["split_bills_per_month"])):
            total = H(r.uniform(lim * 0.9, lim - 50))
            net = int(round(total / 1.15))
            day = self.pick_working(r, d.year, d.month, d.day, 28)
            self.b.schedule(day, lambda dd, net=net: self.post_bill(
                dd, self.s7["vendor"], [{"name": "Maintenance materials and spares", "desc": "Urgent site purchase",
                                         "qty": 1, "rate": net, "account": "direct_materials"}],
                created_lag=r.choice([0, 1, 2])))

    def s7_late_journal(self, d):
        """A reclassification dated in a month that is already closed when it is entered."""
        r = self.r("s7late", d)
        amt = H(round(r.uniform(30_000, 150_000), -2))
        lag = max(31, (month_end(d.year, d.month) - d).days + r.randint(20, 50))
        self.b.journal(d, [("ga", amt, "Reclassification of site costs to overheads"),
                           ("other_direct", -amt, "Reclassification of site costs to overheads")],
                       "Reclassification of site costs", role="gl", created_lag=lag, ref=f"RCL-{d:%y%m%d}", kind="adjustment")

    def s7_friday_journal(self, d):
        """A payment journal entered on a Friday evening by a user who rarely posts."""
        r = self.r("s7fri", d)
        amt = H(round(r.uniform(8_000, 60_000), -1))
        self.b.journal(d, [("other_direct", amt, "Site expenses paid"), ("bank1", -amt, "Payment – site expenses")],
                       "Site expenses payment", role="adhoc", ref=f"SE-{d:%y%m%d}", kind="bank",
                       created_on=d + timedelta(days=1))

    # ------------------------------------------------------------------ certification and invoicing
    def certify(self, d, item):
        if item not in self.pending:
            return
        self.pending.remove(item)
        proj, p = item["project"], self.p
        r = self.r("cert", proj["project_id"], item["y"], item["m"])
        net = int(item["work"] * clamp(r.gauss(*p["certify_ratio"]), 0.9, 1.06))
        proj["_ipc"] += 1
        proj["_billed"] += net
        ret = int(net * p["retention"])
        inv = self.b.invoice(d, proj["_cust"], [{"name": f"Interim Payment Certificate No. {proj['_ipc']}",
                                                 "desc": f"Work done to {mlabel(item['y'], item['m'])}, {proj['project_code']}",
                                                 "qty": 1, "rate": net, "account": "rev_contract"}],
                             project_id=proj["project_id"], retention=ret, created_lag=r.choice([0, 1, 2, 4]),
                             ref=f"{proj['project_code']}/IPC-{proj['_ipc']:02d}",
                             notes=f"Retention {int(p['retention'] * 100)}% (SAR {S(ret):,.2f}) withheld per contract." if ret else "")
        proj["_invoices"].append(inv)
        self.schedule_collection(inv)

    def schedule_releases(self, proj, first_done=False):
        r = self.r("release", proj["project_id"])
        cls = proj["_cust"]["_class"]
        slow = 1.6 if cls == "government" else 1.0
        done = proj["_complete"]
        if not first_done:
            self.b.schedule(next_working(done + timedelta(days=int(r.uniform(60, 130) * slow))),
                            lambda d, pr=proj: self.release_retention(d, pr["_invoices"], 0.5))
        self.b.schedule(next_working(done + timedelta(days=365 + int(r.uniform(45, 160) * slow))),
                        lambda d, pr=proj: self.release_retention(d, pr["_invoices"], 1.0))
        self.b.schedule(next_working(done + timedelta(days=int(r.uniform(90, 160)))),
                        lambda d, pr=proj: self.release_bill_retention(d, pr["_subbills"]))

    # ------------------------------------------------------------------ month end
    def close_sector(self, d, lag):
        y, m = d.year, d.month
        p = self.p
        for proj, work in self.month_work:
            r = self.r("certlag", proj["project_id"], y, m)
            cls = proj["_cust"]["_class"]
            cert = next_working(d + timedelta(days=int(lognormal(r, *p["certify_lag_days"][cls]))))
            item = {"project": proj, "y": y, "m": m, "work": work, "cert": cert}
            self.pending.append(item)
            self.b.schedule(cert, lambda day, it=item: self.certify(day, it))
        acc = sum(x["work"] for x in self.pending)
        if acc:
            self.b.journal(d, [("contract_assets", acc, "Work done not yet certified"),
                               ("rev_contract", -acc, "Unbilled revenue at month end")],
                           f"Unbilled revenue accrual – {mlabel(y, m)}", created_lag=lag, ref=f"WIP-{y}{m:02d}",
                           kind="accrual")
            ny, nm = add_months(y, m, 1)
            self.b.schedule(date(ny, nm, 1), lambda day, a=acc, y=y, m=m: self.b.journal(
                day, [("rev_contract", a, "Reversal of unbilled work"), ("contract_assets", -a, "Reversal of unbilled work")],
                f"Reversal of unbilled revenue accrual – {mlabel(y, m)}", created_lag=max(0, lag - 1),
                ref=f"WIP-{y}{m:02d}-R", kind="reversal"))
        backlog = sum(pr["_value"] - pr["_work"] for pr in self.projects if not pr["_complete"] and pr["_start"] <= d + timedelta(days=400))
        self.truth["backlog"].append({"month": f"{y}-{m:02d}", "backlog": backlog, "unbilled": acc,
                                      "projects": [{"project": pr["project_code"], "value": pr["_value"],
                                                    "work_to_date": pr["_work"], "billed_net": pr["_billed"],
                                                    "progress": round(pr["_done"], 4),
                                                    "margin_bid": round(pr["_bid"], 4),
                                                    "margin_estimate": round(self.margin_now(pr), 4)}
                                                   for pr in self.projects if pr["_start"] <= d and
                                                   (not pr["_complete"] or pr["_complete"] >= date(y, m, 1))]})

    # ------------------------------------------------------------------ export helpers
    def project_records(self):
        out = []
        for pr in self.projects:
            status = "active"
            if pr["_complete"] and pr["_complete"] <= self.data_end:
                status = "completed"
            if pr["_start"] > self.data_end:
                status = "not_started"
            out.append(pr)
            pr["status"] = status
            pr["custom_fields"] = [
                {"label": "Contract Value (SAR)", "value": S(pr["_value"])},
                {"label": "Original Contract Value (SAR)", "value": S(pr["_orig"])},
                {"label": "Approved Variations (SAR)", "value": S(pr["_value"] - pr["_orig"])},
                {"label": "Award Date", "value": pr["_award"].isoformat()},
                {"label": "Start Date", "value": pr["_start"].isoformat()},
                {"label": "Planned Completion", "value": month_end(*add_months(pr["_start"].year, pr["_start"].month, pr["_months"] - 1)).isoformat()},
                {"label": "Retention %", "value": int(self.p["retention"] * 100)},
            ]
        return out
