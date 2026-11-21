"""A home and lifestyle retailer with mall stores.

Each store's point-of-sale system posts one sales receipt a day with three category lines; card and cash
takings sit in a clearing account until the acquirer and the cash-in-transit company settle them, net of
card fees, into the collections account. Cost of sales is posted per store and category at month end.
Store leases follow IFRS 16 (right-of-use asset, lease liability, depreciation and interest); landlords bill
the rent semi-annually in advance. New stores are fitted out over the three months before they open.
"""
from collections import defaultdict
from datetime import date, timedelta

from ..calendar_ksa import in_eid_adha, in_eid_fitr, in_ramadan, is_working_day, next_working, prev_working
from ..common import CompanySim, mlabel
from ..markets import rate_to_sar
from ..names import RET_FITOUT, RET_LANDLORDS, RET_MALLS, RET_VENDORS
from ..util import H, S, add_months, clamp, dim, lognormal, month_end

CATS = [("rev_cat_1", "cogs_cat_1", "Home Décor", 62.0), ("rev_cat_2", "cogs_cat_2", "Kitchen and Dining", 48.0),
        ("rev_cat_3", "cogs_cat_3", "Bed and Bath", 85.0)]
WEEKDAY = [0.86, 0.88, 0.92, 1.22, 1.16, 1.04, 0.92]   # Monday .. Sunday (Thursday and Friday evenings peak)


class RetailSim(CompanySim):
    sector = "retail"
    extra_roles = [("pos", "Point-of-sale integration", "staff")]

    # ------------------------------------------------------------------ setup
    def setup(self):
        p = self.p
        r = self.r("setup")
        n = 0
        self.walkin = self.b.add_contact("Walk-in Customers", "customer", "retail", 0, date(2017, 1, 1))
        self.corporate = []
        for i, name in enumerate(["Bluedune Hospitality Projects", "Amberline Hotels Development", "Oakfield Compounds Co.",
                                  "Cedarline Office Parks", "Sandcrest Residential Developers", "Silverpalm Medical Centres",
                                  "Greenoasis Schools Company", "Northstar Towers Co."]):
            n += 1
            c = self.b.add_contact(name, "customer", "private", r.choice([30, 45, 60]), date(2018 + i % 4, 1 + i, 10),
                                   vat_no=f"TEST-VAT-{self.c['org_num']:02d}{n:04d}", cr_no=f"TEST-CR-{self.c['org_num']:02d}{n:04d}")
            c["_habit"] = clamp(lognormal(r, 1, 0.2), 0.6, 1.6)
            c["_weight"] = r.paretovariate(1.5)
            self.corporate.append(c)
        # suppliers by currency
        self.suppliers = []
        for cur, pool in RET_VENDORS.items():
            for name in pool:
                n += 1
                foreign = cur != "SAR"
                v = self.b.add_contact(name, "vendor", "private", 60 if foreign else 45, date(2015 + n % 6, 2, 1 + n),
                                       currency=cur, vat_no="" if foreign else f"TEST-VAT-{self.c['org_num']:02d}{n:04d}",
                                       cr_no="" if foreign else f"TEST-CR-{self.c['org_num']:02d}{n:04d}",
                                       country={"CNY": "CN", "EUR": "PT", "USD": "TR"}.get(cur, "SA"),
                                       prefix="".join(w[0] for w in name.split()[:2]).upper())
                v["_pay_lag"] = r.randint(0, 6)
                v["_lead"] = (55, 75) if cur == "CNY" else ((35, 50) if foreign else (4, 9))
                self.suppliers.append(v)
        self.sup_share = p["purchase_currency_mix"]
        self.clearing = self.b.add_contact("Gulf Gate Customs Clearing Est.", "vendor", "private", 15, date(2016, 3, 1),
                                           vat_no=f"TEST-VAT-{self.c['org_num']:02d}0998", cr_no=f"TEST-CR-{self.c['org_num']:02d}0998",
                                           prefix="GGC")
        self.fitout = self.b.add_contact(RET_FITOUT, "vendor", "private", 30, date(2016, 5, 1),
                                         vat_no=f"TEST-VAT-{self.c['org_num']:02d}0997", cr_no=f"TEST-CR-{self.c['org_num']:02d}0997",
                                         prefix="BIF")
        self.fitout["_pay_lag"] = 10
        self.landlords = []
        for name in RET_LANDLORDS:
            n += 1
            v = self.b.add_contact(name, "vendor", "private", 10, date(2014 + n % 6, 6, 1),
                                   vat_no=f"TEST-VAT-{self.c['org_num']:02d}{n:04d}", cr_no=f"TEST-CR-{self.c['org_num']:02d}{n:04d}",
                                   prefix="LL")
            v["_pay_lag"] = 0
            self.landlords.append(v)
        # merchandise items (the POS holds the SKUs; the books hold one item per category)
        self.cat_items = []
        for rk, ck, label, price in CATS:
            it = self.b.add_item(f"{label} merchandise", f"RT-{len(self.cat_items) + 1:02d}", "pcs", H(price),
                                 H(price * 0.47), "inventory", rk, ck, family=label)
            self.cat_items.append(it)
        # stores
        self.stores = []
        malls = list(RET_MALLS)
        plan = p["stores"]
        k = 0
        for i in range(plan["existing"]):
            mall, city = malls[k]
            k += 1
            opened = date(2014 + i % 8, 1 + (i * 5) % 12, 1 + (i * 7) % 27)
            self.add_store(r, mall, city, opened, weak=False)
        for ds in plan["normal_openings"]:
            mall, city = malls[k]
            k += 1
            self.add_store(r, mall, city, date.fromisoformat(ds), weak=False)
        st = self.story("S4")
        for ds in (st["new_store_dates"] if st else []):
            mall, city = malls[k]
            k += 1
            self.add_store(r, mall, city, date.fromisoformat(ds), weak=True)
        self._settle = {}
        self.month_sales = defaultdict(int)       # (store code, cat index) -> net sales this month
        self.recent_sales = []
        self.quarter_sales = defaultdict(int)
        self.on_order = 0
        days = [date(2023, 1, 1) + timedelta(days=i) for i in range(365 * 3)]
        self.norm = sum(WEEKDAY[x.weekday()] * p["calendar"]["month"][x.month - 1] * self.holiday(x) for x in days) / len(days)

    def add_store(self, r, mall, city, opened, weak):
        p = self.p
        code = f"S{len(self.stores) + 1:02d}"
        area = int(r.uniform(900, 1650) // 10 * 10)
        loc = self.b.add_location(f"{code} {mall}", code, city, opened, area)
        dens = H(lognormal(r, p["density_sar_m2"], p["density_sar_m2"] * 0.18))
        if weak:
            dens = int(dens * self.story("S4")["mature_density_factor"])
        mature_sales = dens * area
        rent_ratio = (self.story("S4")["rent_to_sales"] if weak else p["rent_to_sales"]) * lognormal(r, 1, 0.12)
        expected = mature_sales * (1 if not weak else 1 / self.story("S4")["mature_density_factor"])
        store = {"code": code, "loc": loc, "area": area, "opened": opened, "density": dens, "weak": weak,
                 "rent": int(expected * rent_ratio), "landlord": r.choice(self.landlords), "leases": [],
                 "fitout": int(H(r.uniform(*p["fitout_sar_m2"])) * area * (1.15 if weak else 1.0)),
                 "noise": clamp(r.gauss(1, 0.05), 0.85, 1.15)}
        self.stores.append(store)
        return store

    # ------------------------------------------------------------------ store sales model
    def ramp(self, s, d) -> float:
        months_open = (d - s["opened"]).days / 30.4
        if months_open < 0:
            return 0.0
        start = self.story("S4")["ramp_start"] if s["weak"] else self.p["ramp_start"]
        return start + (1 - start) * min(1.0, months_open / self.p["ramp_months"])

    def holiday(self, d) -> float:
        cal = self.p["calendar"]
        if in_eid_fitr(d):
            return cal["eid_fitr"]
        if in_eid_adha(d):
            return cal["eid_adha"]
        if in_ramadan(d):
            return cal["ramadan"]
        return 1.0

    def common_noise(self, y, m) -> float:
        """Company-wide monthly shock with AR(1) persistence."""
        if not hasattr(self, "_cn"):
            self._cn = {}
        if (y, m) in self._cn:
            return self._cn[(y, m)]
        py, pm = add_months(y, m, -1)
        prev = self._cn.get((py, pm), 0.0)
        e = self.r("cn", y, m).gauss(0, self.p.get("month_noise", 0.025))
        u = self.p.get("ar1", 0.5) * prev + e
        self._cn[(y, m)] = u
        return u

    def store_sales(self, s, d) -> int:
        if d < s["opened"]:
            return 0
        r = self.r("ss", s["code"], d)
        lfl = (1 + self.p["lfl_growth"]) ** self.years_from_base(d)
        x = s["density"] * s["area"] / 365.0 / self.norm
        x *= self.ramp(s, d) * lfl * s["noise"] * WEEKDAY[d.weekday()] * self.p["calendar"]["month"][d.month - 1]
        x *= self.holiday(d) * (2.718281828 ** self.common_noise(d.year, d.month)) * lognormal(r, 1.0, 0.12)
        return int(x)

    def store_count(self, y, m) -> int:
        return sum(1 for s in self.stores if s["opened"] <= date(y, m, 15))

    def payroll_lines(self, grp, y, m, heads, gross_total):
        if "per_store" not in grp:
            return super().payroll_lines(grp, y, m, heads, gross_total)
        open_ = [s for s in self.stores if s["opened"] <= date(y, m, 15)]
        lines, given = [], 0
        for i, s in enumerate(open_):
            a = gross_total - given if i == len(open_) - 1 else gross_total // len(open_)
            given += a
            lines.append((grp["account"], a, f"Store staff salaries {mlabel(y, m)}", s["loc"]))
        return lines

    # ------------------------------------------------------------------ leases (IFRS 16)
    def new_lease(self, s, start: date, years: int, annual: int, d_post: date, opening=False):
        rate_m = self.p["ibr"] / 12
        n = years * 2
        pay = annual // 2
        pv = sum(pay / (1 + rate_m) ** (6 * i) for i in range(n))
        lease = {"start": start, "end": date(start.year + years, start.month, min(start.day, 28)) - timedelta(days=1),
                 "months": years * 12, "pay": pay, "cost": int(pv), "liab": int(pv), "dep_done": 0, "n": n,
                 "paid": 0, "annual": annual}
        s["leases"].append(lease)
        return lease

    def lease_liability_at(self, lease, d) -> int:
        """Present value at d of the payments not yet made."""
        rate_m = self.p["ibr"] / 12
        out = 0.0
        for i in range(lease["n"]):
            y, m = add_months(lease["start"].year, lease["start"].month, 6 * i)
            due = date(y, m, min(lease["start"].day, 28))
            if due > d:
                months_ahead = (due.year - d.year) * 12 + (due.month - d.month)
                out += lease["pay"] / (1 + rate_m) ** max(0, months_ahead)
        return int(out)

    # ------------------------------------------------------------------ opening
    def opening(self, d0: date):
        p = self.p
        r = self.r("opening")
        rou = rou_dep = liab = 0
        for s in self.stores:
            if s["opened"] > d0:
                continue
            # the current lease began at the last 5-year anniversary of the store
            st = s["opened"]
            while date(st.year + 5, st.month, min(st.day, 28)) <= d0:
                st = date(st.year + 5, st.month, min(st.day, 28))
            lease = self.new_lease(s, st, 5, s["rent"], d0, opening=True)
            months_used = (d0.year - st.year) * 12 + (d0.month - st.month) + 1
            lease["dep_done"] = int(lease["cost"] * months_used / lease["months"])
            lease["liab"] = self.lease_liability_at(lease, d0)
            lease["paid"] = sum(1 for i in range(lease["n"])
                                if date(*add_months(st.year, st.month, 6 * i), min(st.day, 28)) <= d0)
            rou += lease["cost"]
            rou_dep += lease["dep_done"]
            liab += lease["liab"]
        self.b.post(d0, [("rou", rou), ("rou_dep", -rou_dep), ("lease_liab", -liab), ("retained", liab + rou_dep - rou)],
                    "opening", "opening-leases")
        inv = int(H(p["revenue_sar_m"] * 1e6) * self.trend(d0) * (1 - p["gross_margin"]) / 365 * p["stock_days"])
        self.b.post(d0, [("inventory", inv), ("retained", -inv)], "opening", "opening-stock")
        for s in self.stores:
            for lease in s["leases"]:
                self.schedule_lease_bills(s, lease)

    def schedule_lease_bills(self, s, lease):
        for i in range(lease["paid"], lease["n"]):
            y, m = add_months(lease["start"].year, lease["start"].month, 6 * i)
            due = date(y, m, min(lease["start"].day, 28))
            bill_day = prev_working(due - timedelta(days=12))
            if bill_day < self.start:
                bill_day = self.start
            self.b.schedule(bill_day, lambda d, s=s, lease=lease, i=i: self.rent_bill(d, s, lease, i))

    def rent_bill(self, d, s, lease, i):
        lease["paid"] = max(lease["paid"], i + 1)
        lease["liab"] -= lease["pay"]
        self.post_bill(d, s["landlord"], [{"name": "Store rent – six months in advance",
                                           "desc": f"{s['loc']['location_name']}, instalment {i + 1} of {lease['n']}",
                                           "qty": 1, "rate": lease["pay"], "account": "lease_liab"}],
                       location=s["loc"], created_lag=self.r("rlag", s["code"], d).choice([0, 1, 2]))

    # ------------------------------------------------------------------ the day
    def day(self, d: date):
        total_card = total_cash = 0
        for s in self.stores:
            net = self.store_sales(s, d)
            if net <= 0:
                continue
            r = self.r("cat", s["code"], d)
            shares = self.p["category_mix"]
            if in_ramadan(d):
                shares = [shares[0] * 1.05, shares[1] * 1.12, shares[2] * 0.85]
            elif d.month in (6, 7, 8):
                shares = [shares[0] * 0.95, shares[1] * 0.97, shares[2] * 1.1]
            tot = sum(shares)
            lines = []
            for (rk, ck, label, price), sh, it in zip(CATS, shares, self.cat_items):
                v = int(net * sh / tot * lognormal(r, 1, 0.08))
                unit = H(price * lognormal(r, 1, 0.05))
                qty = max(1, int(round(v / unit)))
                lines.append({"name": f"{label} – POS daily sales", "qty": qty, "rate": unit, "account": rk,
                              "item": it})
                self.month_sales[(s["code"], CATS.index((rk, ck, label, price)))] += qty * unit
            rc = self.b.sales_receipt(d, self.walkin, lines, "card_clearing", location=s["loc"], mode="card")
            cash = int(rc["_total"] * self.p["cash_share"])
            total_cash += cash
            total_card += rc["_total"] - cash
            self.truth["store_days"].append((d, s["code"], rc["_total"]))
        if total_card or total_cash:
            key = next_working(d + timedelta(days=1))
            if key not in self._settle:
                self._settle[key] = [0, 0]
                self.b.schedule(key, lambda day, k=key: self.settle(day, k))
            self._settle[key][0] += total_card
            self._settle[key][1] += total_cash

    def settle(self, d, key):
        card, cash = self._settle.pop(key)
        fee = int(card * self.p["card_fee"])
        fee_net = int(round(fee / 1.15))
        fee_vat = fee - fee_net
        self.b.journal(d, [("bank2", card - fee + cash, "Card and cash settlements"),
                           ("bank_charges", fee_net, "Card acquiring fees"), ("vat_in", fee_vat, "VAT on acquiring fees"),
                           ("card_clearing", -(card + cash), "Settled takings")],
                       "Point-of-sale settlement – card acquirer and cash in transit", role="treasury",
                       ref=f"STL-{d:%y%m%d}", kind="bank")

    # ------------------------------------------------------------------ the month
    def month_start(self, d):
        y, m = d.year, d.month
        p = self.p
        r = self.r("rmonth", y, m)
        # merchandise purchases to keep stock near its target cover
        recent = self.recent_sales[-3:] or [H(p["revenue_sar_m"] * 1e6) * self.trend(d) / 12]
        cogs_month = int(sum(recent) / len(recent) * (1 - p["gross_margin"]))
        target = int(cogs_month * 12 / 365 * (p["stock_days"] + 45))   # on hand plus in transit
        need = cogs_month + (target - self.bal("inventory") - self.on_order) * 0.5
        need = max(int(cogs_month * 0.3), int(need))
        for cur, share in self.sup_share.items():
            vs = [v for v in self.suppliers if v["currency_code"] == cur]
            for v in vs:
                amt = int(need * share / len(vs) * lognormal(r, 1, 0.15))
                if amt <= 0:
                    continue
                lead = r.randint(*v["_lead"])
                day = self.pick_working(r, y, m, 2, 12)
                self.b.schedule(day, lambda dd, v=v, amt=amt, lead=lead: self.place_po(dd, v, amt, lead))
        # service charges billed by each landlord for the month
        for s in self.stores:
            if s["opened"] <= d:
                amt = int(s["density"] * s["area"] / 12 * self.ramp(s, d) * p["service_charge_ratio"])
                day = self.pick_working(r, y, m, 1, 10)
                self.b.schedule(day, lambda dd, s=s, a=amt: self.post_bill(
                    dd, s["landlord"], [{"name": "Service charges and marketing levy", "desc": f"{s['loc']['location_name']} {mlabel(dd.year, dd.month)}",
                                         "qty": 1, "rate": a, "account": "rent"}], location=s["loc"], created_lag=2))
        # corporate orders
        for c in self.corporate:
            if r.random() < 0.45:
                amt = int(H(p["revenue_sar_m"] * 1e6) * self.trend(d) * p["corporate_share"] / 12 * c["_weight"]
                          / sum(x["_weight"] for x in self.corporate) / 0.45 * lognormal(r, 1, 0.3))
                day = self.pick_working(r, y, m, 3, 26)
                self.b.schedule(day, lambda dd, c=c, amt=amt: self.corporate_invoice(dd, c, amt))
        # new stores: fit-out during the three months before opening; first lease
        for s in self.stores:
            if s["opened"] >= self.start:
                for k in (3, 2, 1):
                    fy, fm = add_months(s["opened"].year, s["opened"].month, -k)
                    if (fy, fm) == (y, m):
                        part = s["fitout"] * {3: 0.35, 2: 0.4, 1: 0.25}[k]
                        day = self.pick_working(r, y, m, 5, 25)
                        self.b.schedule(day, lambda dd, s=s, a=int(part), k=k: self.post_bill(
                            dd, self.fitout, [{"name": "Store fit-out works", "desc": f"{s['loc']['location_name']} – progress claim {4 - k} of 3",
                                               "qty": 1, "rate": a, "account": "ppe_cost"}], location=s["loc"], created_lag=3))
                if (s["opened"].year, s["opened"].month) == (y, m):
                    self.b.schedule(s["opened"], lambda dd, s=s: self.open_store(dd, s))
        # lease renewals at expiry
        for s in self.stores:
            for lease in list(s["leases"]):
                if (lease["end"].year, lease["end"].month) == (y, m) and not lease.get("renewed"):
                    lease["renewed"] = True
                    nstart = lease["end"] + timedelta(days=1)
                    self.b.schedule(max(d, prev_working(lease["end"])), lambda dd, s=s, old=lease, ns=nstart: self.renew(dd, s, old, ns))
        # shrink found at quarterly stock counts
        if m in (3, 6, 9, 12):
            self.b.schedule(self.pick_working(r, y, m, 24, 28), self.stock_counts)

    def place_po(self, d, v, amt, lead):
        cur = v["currency_code"]
        rate = rate_to_sar(cur, d)
        r = self.r("rpo", v["contact_id"], d)
        lines = []
        weights = self.p["category_mix"]
        for (rk, ck, label, price), w, it in zip(CATS, weights, self.cat_items):
            val = amt * w / sum(weights) / rate
            unit = int(H(price * 0.45) / rate * lognormal(r, 1, 0.08))
            qty = max(1, int(round(val / max(1, unit))))
            lines.append({"name": it["name"], "qty": qty, "rate": unit, "account": "inventory", "item": it})
        expected = next_working(d + timedelta(days=lead))
        po = self.b.purchase_order(d, v, lines, expected, currency=cur, rate=rate)
        self.on_order += amt
        self.b.schedule(expected, lambda dd, po=po, v=v, lines=lines, amt=amt: self.receive(dd, po, v, lines, amt))

    def receive(self, d, po, v, lines, amt):
        cur = v["currency_code"]
        rate = rate_to_sar(cur, d)
        before = self.bal("inventory")
        bill = self.post_bill(d, v, [dict(l) for l in lines], currency=cur, rate=rate, po=po,
                              created_lag=self.r("rrc", po["purchaseorder_id"]).choice([0, 1, 3]),
                              ref=po["purchaseorder_number"])
        value = self.bal("inventory") - before
        self.on_order -= amt
        if cur != "SAR":
            duty = int(value * self.p["duty_rate"])
            clearing = int(value * self.p["clearing_rate"])
            self.post_bill(d, self.clearing,
                           [{"name": "Customs duty", "desc": f"Bill {bill['bill_number']} – {v['contact_name']}", "qty": 1,
                             "rate": duty, "account": "inventory", "vat": False},
                            {"name": "Import VAT paid at customs", "desc": "Recoverable", "qty": 1,
                             "rate": int((value + duty) * 0.15), "account": "vat_in", "vat": False},
                            {"name": "Clearing, port and transport charges", "qty": 1, "rate": clearing,
                             "account": "inventory"}], created_lag=2)

    def corporate_invoice(self, d, c, amt):
        if amt <= 0:
            return
        r = self.r("corp", c["contact_id"], d)
        lines = []
        for (rk, ck, label, price), it in zip(CATS, self.cat_items):
            v = amt * r.uniform(0.2, 0.5)
            unit = H(price)
            lines.append({"name": f"{label} – corporate order", "qty": max(1, int(v / unit)), "rate": unit,
                          "discount_pct": 0.1, "account": rk, "item": it})
        cogs = [(ck, "inventory", int(l["qty"] * l["rate"] * 0.9 * (1 - gm)))
                for l, (rk, ck, label, price), gm in zip(lines, CATS, self.p["category_margin"])]
        inv = self.b.invoice(d, c, lines, cogs=cogs)
        self.schedule_collection(inv, bank="bank1")

    def open_store(self, d, s):
        lease = self.new_lease(s, s["opened"], 5, s["rent"], d)
        self.b.journal(d, [("rou", lease["cost"], "Right-of-use asset at commencement", s["loc"]),
                           ("lease_liab", -lease["cost"], "Lease liability at commencement", s["loc"])],
                       f"New store lease – {s['loc']['location_name']}", created_lag=6, ref=f"LSE-{s['code']}",
                       kind="lease")
        self.schedule_lease_bills(s, lease)

    def renew(self, d, s, old, nstart):
        annual = int(old["annual"] * (1 + self.p["rent_escalation"]))
        lease = self.new_lease(s, nstart, 5, annual, d)
        rest = old["cost"] - old["dep_done"]
        lines = [("rou_dep", old["dep_done"], "Expired lease: accumulated depreciation", s["loc"]),
                 ("rou", -old["cost"], "Expired lease: cost", s["loc"])]
        if rest:
            lines.append(("depr_rou", rest, "Expired lease: remaining depreciation", s["loc"]))
        if old["liab"]:
            lines.append(("lease_liab", old["liab"], "Expired lease: remaining liability", s["loc"]))
            lines.append(("lease_interest", -old["liab"], "Expired lease: remaining liability", s["loc"]))
        lines += [("rou", lease["cost"], "Renewed lease at commencement", s["loc"]),
                  ("lease_liab", -lease["cost"], "Renewed lease liability", s["loc"])]
        self.b.journal(d, lines, f"Lease renewal – {s['loc']['location_name']}", created_lag=5,
                       ref=f"LSR-{s['code']}-{nstart.year}", kind="lease")
        old["liab"] = 0
        old["dep_done"] = old["cost"]
        self.schedule_lease_bills(s, lease)

    def stock_counts(self, d):
        r = self.r("count", d.year, d.month)
        for s in self.stores:
            if s["opened"] > d:
                continue
            q_sales = sum(v for (code, _), v in self.quarter_sales.items() if code == s["code"])
            val = int(q_sales * (1 - self.p["gross_margin"]) * r.uniform(*self.p["shrink"]))
            if val <= 0:
                continue
            it = r.choice(self.cat_items)
            self.b.inventory_adjustment(d, [(it, max(1, int(val / H(30))), val)], "Stock count variance (shrink)",
                                        location=s["loc"])

    # ------------------------------------------------------------------ month end
    def close_sector(self, d, lag):
        y, m = d.year, d.month
        p = self.p
        r = self.r("rclose", y, m)
        # cost of sales per store and category
        lines, tot = [], 0
        for s in self.stores:
            for ci, (rk, ck, label, price) in enumerate(CATS):
                sales = self.month_sales.get((s["code"], ci), 0)
                if not sales:
                    continue
                gm = p["category_margin"][ci] + r.gauss(0, 0.004)
                c = int(sales * (1 - gm))
                lines.append((ck, c, f"Cost of sales {label} {mlabel(y, m)}", s["loc"]))
                tot += c
        if lines:
            self.b.journal(d, lines + [("inventory", -tot, "Inventory relieved")], f"Cost of sales – {mlabel(y, m)}",
                           created_lag=lag, ref=f"COGS-{y}{m:02d}", kind="cogs")
        if m in (1, 4, 7, 10):
            self.quarter_sales = defaultdict(int)
        for k, v in self.month_sales.items():
            self.quarter_sales[k] += v
        self.recent_sales.append(sum(self.month_sales.values()))
        self.truth["store_month"].extend({"month": f"{y}-{m:02d}", "store": code, "category": CATS[ci][2],
                                          "net_sales": v} for (code, ci), v in self.month_sales.items())
        self.month_sales = defaultdict(int)
        # leases: depreciation and interest per store
        dep_lines, int_lines = [], []
        for s in self.stores:
            for lease in s["leases"]:
                if lease["start"] > d or lease["dep_done"] >= lease["cost"]:
                    continue
                dep = min(lease["cost"] // lease["months"], lease["cost"] - lease["dep_done"])
                lease["dep_done"] += dep
                dep_lines.append(("depr_rou", dep, f"Right-of-use depreciation {mlabel(y, m)}", s["loc"]))
                interest = int(max(0, lease["liab"]) * p["ibr"] / 12)
                lease["liab"] += interest
                int_lines.append(("lease_interest", interest, f"Interest on lease liability {mlabel(y, m)}", s["loc"]))
        if dep_lines:
            t = sum(a for _, a, _, _ in dep_lines)
            self.b.journal(d, dep_lines + [("rou_dep", -t, "Accumulated depreciation – right-of-use")],
                           f"Right-of-use depreciation – {mlabel(y, m)}", created_lag=lag, ref=f"ROU-{y}{m:02d}",
                           kind="lease")
        if int_lines:
            t = sum(a for _, a, _, _ in int_lines)
            self.b.journal(d, int_lines + [("lease_liab", -t, "Lease liabilities")],
                           f"Interest on lease liabilities – {mlabel(y, m)}", created_lag=lag, ref=f"LINT-{y}{m:02d}",
                           kind="lease")

