"""A food distributor: buys from local factories and importers in SAR, EUR and USD, holds stock, and sells
on credit to supermarket chains, hotels, restaurants and cafés, wholesalers, government catering and small
grocers.

Stock is valued first in, first out per item, so a purchase-price rise reaches cost of sales only as the old
stock sells through. Imports carry customs duty and clearing charges (added to stock cost) and import VAT
(recoverable). Every sale is an invoice with item lines, list prices and the customer's discount.
"""
from collections import defaultdict, deque
from datetime import date, timedelta

from ..calendar_ksa import in_eid_adha, in_eid_fitr, in_ramadan, is_working_day, next_working, RAMADAN
from ..common import CompanySim, mlabel
from ..markets import rate_to_sar
from ..intercompany import ic_flows
from ..names import (BM_GOV, BM_VENDORS, CUST_WORDS, IND_BIG, IND_GOV, IND_VENDORS, TRD_CLEARING, TRD_GOV, TRD_HORECA_A,
                     TRD_HORECA_B, TRD_KEY, TRD_SMALL_A, TRD_SMALL_B, TRD_VENDORS_EUR, TRD_VENDORS_SAR, TRD_VENDORS_USD,
                     TRD_WHOLESALE)
from ..util import H, S, clamp, lognormal, month_end

# family, revenue share, currency mix, gross margin target, unit, landed-cost range (SAR), product words
FAMILIES = [
    ("Rice", 0.12, {"USD": 1.0}, 0.18, "bag 10 kg", (42, 98),
     ["Basmati Rice Premium", "Sella Basmati Rice", "Jasmine Rice", "Long Grain Rice", "Calrose Rice", "Brown Rice"]),
    ("Cooking oil", 0.09, {"SAR": 1.0}, 0.15, "carton 4×1.8 L", (55, 92),
     ["Sunflower Oil", "Corn Oil", "Vegetable Oil", "Canola Oil", "Olive Pomace Oil"]),
    ("Dairy and cheese", 0.18, {"EUR": 0.75, "SAR": 0.25}, 0.21, "carton", (48, 250),
     ["UHT Full Cream Milk 12×1 L", "Mozzarella Block 2.3 kg", "Feta Cheese Tin 16 kg", "Cheddar Slices 1 kg",
      "Butter Unsalted 25×200 g", "Cream Cheese Spread 12×500 g", "Gouda Cheese Wheel", "Halloumi 1 kg",
      "Cooking Cream 12×1 L", "Labneh 6×1 kg", "Parmesan Grated 1 kg", "Evaporated Milk 48×170 g"]),
    ("Frozen poultry and meat", 0.14, {"USD": 0.8, "SAR": 0.2}, 0.17, "carton 10 kg", (88, 265),
     ["Whole Frozen Chicken 1 kg", "Chicken Breast Fillet", "Chicken Wings", "Beef Burger Patties",
      "Minced Beef", "Lamb Shoulder", "Chicken Nuggets", "Turkey Breast"]),
    ("Canned food", 0.08, {"SAR": 0.7, "EUR": 0.3}, 0.24, "carton 24 tins", (38, 125),
     ["Chickpeas", "Fava Beans", "Tomato Paste", "Sweet Corn", "Tuna Chunks", "Mushrooms Sliced",
      "Baked Beans", "Peeled Tomatoes", "Green Peas"]),
    ("Pasta and grains", 0.06, {"EUR": 0.6, "SAR": 0.4}, 0.23, "carton 20×400 g", (32, 72),
     ["Spaghetti", "Penne Rigate", "Fusilli", "Vermicelli", "Lentils Red", "Bulgur Wheat", "Freekeh"]),
    ("Beverages", 0.09, {"SAR": 1.0}, 0.14, "carton 24×330 ml", (18, 58),
     ["Mineral Water 24×330 ml", "Orange Juice 6×1 L", "Mango Nectar 24×250 ml", "Laban Drink 24×180 ml",
      "Sparkling Water", "Apple Juice 6×1 L", "Vimto-style Cordial 12×710 ml"]),
    ("Confectionery and snacks", 0.08, {"EUR": 0.5, "SAR": 0.5}, 0.28, "carton", (40, 185),
     ["Milk Chocolate Bars", "Wafer Biscuits", "Butter Cookies Tin", "Potato Chips", "Dates Filled Biscuits",
      "Hazelnut Spread 12×400 g", "Assorted Chocolates Box"]),
    ("Spices and condiments", 0.05, {"SAR": 0.8, "USD": 0.2}, 0.32, "carton", (30, 145),
     ["Black Pepper Ground", "Cumin Powder", "Cardamom Green", "Saffron Strands", "Tahini 12×800 g",
      "Ketchup 12×1 kg", "Mayonnaise 6×1 L", "Hot Sauce 24×88 ml"]),
    ("Tea and coffee", 0.06, {"USD": 0.6, "SAR": 0.4}, 0.27, "carton", (60, 330),
     ["Black Tea Loose 1 kg", "Tea Bags 100s", "Arabic Coffee Ground", "Instant Coffee 12×200 g",
      "Green Tea Bags"]),
    ("Flour and sugar", 0.05, {"SAR": 1.0}, 0.12, "bag 45 kg", (42, 115),
     ["All-purpose Flour", "Patent Flour", "White Sugar", "Brown Sugar", "Semolina"]),
]
BM_FAMILIES = [
    ("Cement and blocks", 0.18, {"SAR": 1.0}, 0.14, "ton", (230, 420),
     ["OPC Cement (ton)", "Sulphate Resistant Cement (ton)", "Concrete Blocks 20 cm (pallet)", "Hollow Blocks 15 cm (pallet)",
      "Ready Mortar 40 kg (pallet)"]),
    ("Steel and rebar", 0.22, {"SAR": 0.7, "USD": 0.3}, 0.12, "ton", (2400, 4200),
     ["Rebar 12 mm", "Rebar 16 mm", "Rebar 25 mm", "Steel Mesh Sheets", "Binding Wire", "Steel Angles"]),
    ("Tiles and sanitary ware", 0.18, {"EUR": 0.4, "CNY": 0.4, "SAR": 0.2}, 0.32, "box", (35, 900),
     ["Porcelain Tiles 60×60", "Ceramic Wall Tiles", "Wash Basin", "Water Closet Set", "Mixer Tap", "Shower Set", "Granite Slab"]),
    ("Pipes and fittings", 0.14, {"SAR": 0.6, "CNY": 0.4}, 0.26, "length", (12, 450),
     ["uPVC Pipe 110 mm", "PPR Pipe 32 mm", "HDPE Pipe 63 mm", "Elbow Fittings Box", "Gate Valve 2 in", "Water Tank 2,000 L"]),
    ("Electrical", 0.14, {"CNY": 0.5, "SAR": 0.3, "EUR": 0.2}, 0.29, "roll", (25, 1200),
     ["Cable 4 mm² (roll)", "Cable 16 mm² (roll)", "Switches and Sockets Box", "Distribution Board", "LED Panel Lights Box",
      "Circuit Breakers Box"]),
    ("Paints and chemicals", 0.14, {"SAR": 0.7, "EUR": 0.3}, 0.34, "pail", (60, 520),
     ["Emulsion Paint 18 L", "Enamel Paint 4 L", "Primer 18 L", "Waterproofing Membrane Roll", "Tile Adhesive 20 kg",
      "Grout 5 kg", "Sealant Cartridges Box"]),
]
IND_FAMILIES = [
    ("Bearings and transmission", 0.18, {"EUR": 0.5, "CNY": 0.5}, 0.09, "box", (40, 900),
     ["Ball Bearings Set", "Taper Roller Bearings", "V-Belts Box", "Chains and Sprockets", "Couplings"]),
    ("Valves and pumps", 0.20, {"EUR": 0.4, "CNY": 0.3, "USD": 0.3}, 0.08, "piece", (300, 9000),
     ["Ball Valve 4 in", "Butterfly Valve 6 in", "Centrifugal Pump 5 kW", "Pressure Gauge", "Check Valve 3 in"]),
    ("Safety equipment", 0.18, {"CNY": 0.7, "SAR": 0.3}, 0.11, "carton", (60, 600),
     ["Safety Helmets Carton", "Safety Shoes Carton", "Hi-vis Vests Carton", "Work Gloves Carton", "Safety Goggles Box"]),
    ("Tools and fasteners", 0.20, {"CNY": 0.6, "SAR": 0.4}, 0.10, "box", (20, 1500),
     ["Bolts and Nuts Box", "Power Drill Set", "Hand Tools Kit", "Welding Rods Box", "Anchor Bolts Box"]),
    ("Lubricants and chemicals", 0.24, {"SAR": 0.6, "USD": 0.4}, 0.07, "drum", (180, 2400),
     ["Hydraulic Oil 208 L", "Gear Oil 20 L", "Grease Pail 18 kg", "Industrial Degreaser 20 L", "Coolant 208 L"]),
]
BM_PLAN = {
    "contractor": (0.55, 60, 60, (5, 10), (3, 8), 0.06),
    "trader": (0.25, 30, 45, (7, 14), (3, 7), 0.08),
    "government": (0.08, 4, 60, (20, 35), (4, 9), 0.03),
    "small": (0.12, 120, 15, (14, 40), (2, 4), 0.0),
}
IND_PLAN = {
    "industrial": (0.60, 40, 60, (7, 14), (3, 7), 0.05),
    "contractor": (0.20, 20, 60, (10, 20), (3, 6), 0.05),
    "government": (0.10, 3, 60, (25, 40), (4, 8), 0.03),
    "small": (0.10, 40, 30, (20, 45), (2, 4), 0.0),
}
CATALOGUES = {"building_materials": (BM_FAMILIES, BM_PLAN, BM_VENDORS, BM_GOV, "BM"),
              "industrial": (IND_FAMILIES, IND_PLAN, IND_VENDORS, IND_GOV, "IN")}
SUFFIX = {"contractor": "Contracting Est.", "trader": "Building Materials Trading", "small": "Hardware Store",
          "industrial": "Industries Co."}

CLASS_PLAN = {
    # class, revenue share, count, terms, (order every min, max days), lines (min, max), discount
    "key_account": (0.44, 10, 75, (5, 8), (16, 26), 0.075),
    "horeca": (0.20, 70, 30, (7, 15), (4, 9), 0.02),
    "wholesale": (0.20, 16, 45, (10, 16), (6, 11), 0.09),
    "government": (0.06, 4, 60, (26, 34), (16, 26), 0.04),
    "small": (0.10, 220, 15, (21, 50), (3, 5), 0.0),
}


class DistributionSim(CompanySim):
    sector = "distribution"

    # ------------------------------------------------------------------ setup
    def setup(self):
        p = self.p
        r = self.r("setup")
        n = 0
        # suppliers
        cat = p.get("catalogue", "food")
        if cat == "food":
            families, class_plan, prefix = FAMILIES, CLASS_PLAN, "FD"
            vspec = (("SAR", TRD_VENDORS_SAR, 50, (3, 7)), ("EUR", TRD_VENDORS_EUR, 60, (35, 50)),
                     ("USD", TRD_VENDORS_USD, 45, (30, 55)))
        else:
            families, class_plan, vpools, gov_pool, prefix = CATALOGUES[cat]
            vspec = tuple((cur, vpools[cur], t, ld) for cur, t, ld in
                          (("SAR", 50, (3, 7)), ("EUR", 60, (35, 50)), ("USD", 45, (30, 55)), ("CNY", 60, (45, 65))))
        self.suppliers = {cur: [] for cur, _, _, _ in vspec}
        for cur, pool, terms, lead in vspec:
            for name in pool:
                n += 1
                foreign = cur != "SAR"
                v = self.b.add_contact(name, "vendor", "private", terms, date(2014 + n % 7, 1 + n % 12, 9), currency=cur,
                                       vat_no="" if foreign else f"TEST-VAT-{self.c['org_num']:02d}{n:04d}",
                                       cr_no="" if foreign else f"TEST-CR-{self.c['org_num']:02d}{n:04d}",
                                       country={"EUR": "DE", "USD": "IN", "CNY": "CN"}.get(cur, "SA"),
                                       prefix="".join(w[0] for w in name.split()[:2]).upper())
                v["_lead"] = lead
                v["_cycle"] = 7 if not foreign else r.randint(21, 35)
                v["_pay_lag"] = r.randint(0, 8)
                v["_items"] = []
                self.suppliers[cur].append(v)
        self.clearing = self.b.add_contact(TRD_CLEARING, "vendor", "private", 15, date(2016, 3, 1),
                                           vat_no=f"TEST-VAT-{self.c['org_num']:02d}0999", cr_no=f"TEST-CR-{self.c['org_num']:02d}0999",
                                           prefix="GGC")
        self.clearing["_pay_lag"] = 0
        # items
        self.items = []
        sku = 0
        for fam, share, curmix, gm, unit, (lo, hi), words in families:
            weights = [r.paretovariate(1.4) for _ in words]
            for word, w in zip(words, weights):
                sku += 1
                cur = r.choices(list(curmix), weights=list(curmix.values()))[0]
                v = r.choice(self.suppliers[cur])
                landed = H(r.uniform(lo, hi))
                extra = 1.07 if cur != "SAR" else 1.0          # duty and clearing on top of the supplier price
                price_fc = int(landed / extra / rate_to_sar(cur, self.start))
                list_price = int(landed / (1 - gm - self.p.get("gm_uplift", 0) - r.uniform(-0.02, 0.02)) / (1 - 0.05))
                it = self.b.add_item(f"{word}", f"{prefix}-{sku:04d}", unit, list_price, landed, "inventory", "rev_sales",
                                     "cogs", family=fam, vendor=v, purchase_currency=cur)
                it["_share"] = share * w / sum(weights)
                it["_cur"] = cur
                it["_vendor"] = v
                it["_price_fc"] = price_fc
                it["_list"] = list_price
                it["_layers"] = deque()
                it["_on_order"] = 0
                it["_s2"] = False
                v["_items"].append(it)
                self.items.append(it)
        st = self.story("S2")
        if st:
            k = int(round(len(self.items) * st["share_of_items"]))
            for it in r.sample(self.items, k):
                it["_s2"] = True
        # customers
        self.customers = []
        if cat == "food":
            names_h = [f"{a} {b}" for a in TRD_HORECA_A for b in TRD_HORECA_B]
            r.shuffle(names_h)
            names_s = [f"{b} {a}" for a in TRD_SMALL_A for b in TRD_SMALL_B]
            r.shuffle(names_s)
            pools = {"key_account": TRD_KEY, "horeca": names_h, "wholesale": TRD_WHOLESALE, "government": TRD_GOV,
                     "small": names_s}
            pay_days = {"key_account": [10, 25], "wholesale": [5, 15, 25], "government": [5, 20]}
            assort = {"key_account": 120, "horeca": 40, "wholesale": 70, "government": 60, "small": 25}
        else:
            words = list(CUST_WORDS)
            r.shuffle(words)
            pools = {seg: (gov_pool if seg == "government" else [f"{w} {SUFFIX[seg]}" for w in words]) for seg in class_plan}
            pay_days = {"contractor": [10, 25], "trader": [5, 20], "industrial": [10, 25], "government": [5, 20]}
            frac = {"contractor": 0.6, "trader": 0.8, "government": 0.5, "small": 0.3, "industrial": 0.5}
            assort = {seg: max(4, int(len(self.items) * frac[seg])) for seg in class_plan}
        cls_map = {seg: ("government" if seg == "government" else "private") for seg in class_plan}
        for cls, (share, count, terms, freq, nlines, disc) in class_plan.items():
            ws = [r.paretovariate(1.2 if cls != "small" else 2.0) for _ in range(count)]
            for i in range(count):
                n += 1
                pool = pools[cls]
                name = pool[i % len(pool)] + (f" – Branch {i // len(pool) + 1}" if i >= len(pool) else "")
                created = date(2015 + n % 8, 1 + n % 12, 1 + n % 27)
                if cls == "small" and r.random() < 0.25:
                    created = date(2022 + r.randint(0, 3), r.randint(1, 12), r.randint(1, 27))
                c = self.b.add_contact(name, "customer", cls_map[cls], terms, created,
                                       vat_no=f"TEST-VAT-{self.c['org_num']:02d}{n:04d}" if cls != "small" or r.random() < 0.5 else "",
                                       cr_no=f"TEST-CR-{self.c['org_num']:02d}{n:04d}" if cls != "government" else "")
                c["_segment"] = cls
                c["_annual"] = share * ws[i] / sum(ws)
                c["_freq"] = freq
                c["_nlines"] = nlines
                c["_disc"] = clamp(disc + r.gauss(0, 0.01), 0, 0.15) if disc else 0.0
                c["_habit"] = clamp(lognormal(r, 1.0, 0.25), 0.5, 1.8)
                c["_start"] = max(self.start, created)
                c["_pay_days"] = pay_days.get(cls)
                c["_next"] = c["_start"] + timedelta(days=r.randint(0, freq[1]))
                fam_pick = r.sample(self.items, min(len(self.items), assort[cls]))
                c["_assort"] = fam_pick
                self.customers.append(c)
        # S8: one new customer that grows to about half of revenue
        st8 = self.story("S8")
        if st8:
            c = self.b.add_contact(IND_BIG, "customer", "private", 60, date(2024, 6, 10),
                                   vat_no=f"TEST-VAT-{self.c['org_num']:02d}0950", cr_no=f"TEST-CR-{self.c['org_num']:02d}0950",
                                   city="Jubail")
            c.update({"_segment": "industrial", "_annual": 0.0, "_freq": (5, 8), "_nlines": (8, 14), "_disc": 0.05,
                      "_habit": 1.0, "_start": date.fromisoformat(st8["start"]), "_pay_days": [10, 25], "_tags": {"S8"},
                      "_ramp": [(date.fromisoformat(a), b_) for a, b_ in st8["ramp"]],
                      "_assort": r.sample(self.items, int(len(self.items) * 0.7))})
            c["_next"] = c["_start"]
            self.customers.append(c)
        # intercompany sales to other group companies
        self.ic = []
        names = {x["code"]: x["legal_name"] for x in self.g["companies"]}
        for spec in self.g.get("intercompany", []):
            if spec["seller"] == self.code:
                c = self.b.add_contact(names.get(spec["buyer"], spec["buyer"]), "customer", "intercompany", spec["terms"],
                                       date(2019, 1, 15), vat_no=f"TEST-VAT-{spec['buyer'][-2:]}0000",
                                       cr_no=f"TEST-CR-{spec['buyer'][-2:]}0000", group_company=spec["buyer"])
                self.ic.append((c, ic_flows(self.g, self.code, spec["buyer"])))
        self.sold_today = defaultdict(int)
        for it in self.items:
            it["_ewma"] = self.planned_units(it, self.start)

    # ------------------------------------------------------------------ prices
    def year_step(self, d: date) -> int:
        return d.year - self.start.year

    def ramp(self, c, d: date) -> float:
        pts = c["_ramp"]
        if d <= pts[0][0]:
            return pts[0][1]
        for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
            if d <= d1:
                return v0 + (v1 - v0) * (d - d0).days / max(1, (d1 - d0).days)
        return pts[-1][1]

    def extra_demand(self, d: date) -> float:
        return sum(self.ramp(c, d) for c in self.customers if "_ramp" in c and c["_start"] <= d)

    def list_price(self, it, d: date) -> int:
        p = it["_list"] * (1 + self.p["sell_inflation"]) ** self.year_step(d)
        st5 = self.story("S5")
        if st5 and d >= date.fromisoformat(st5["start"]):
            p *= 1 + st5["sell_rise"]
        st = self.story("S2")
        if st and it["_s2"] and d >= date.fromisoformat(st["start"]):
            p *= 1 + st["sell_rise"]
        return int(p)

    def purchase_price_fc(self, it, d: date) -> int:
        p = it["_price_fc"] * (1 + self.p["buy_inflation"]) ** self.year_step(d)
        st = self.story("S2")
        if st and it["_s2"] and d >= date.fromisoformat(st["start"]):
            p *= 1 + st["buy_rise"]
        return int(p)

    def planned_units(self, it, d) -> float:
        annual = H(self.p["revenue_sar_m"] * 1e6) * self.trend(d) * it["_share"] * (1 + self.extra_demand(d))
        return annual / 365.0 / max(1, self.list_price(it, d) * 0.95)

    # ------------------------------------------------------------------ demand calendar
    def day_factor(self, d: date) -> float:
        cal = self.p["calendar"]
        f = cal["month"][d.month - 1]
        if in_eid_fitr(d):
            f *= cal["eid_fitr"]
        elif in_eid_adha(d):
            f *= cal["eid_adha"]
        elif in_ramadan(d):
            f *= cal["ramadan"]
        else:
            r_ = RAMADAN.get(d.year if d.month < 11 else d.year + 1)
            if r_ and 0 < (r_[0] - d).days <= 14:
                f *= cal.get("pre_ramadan", 1.0)
        return f

    # ------------------------------------------------------------------ stock
    # Each layer is (date received, quantity, value in halalas); taking part of a layer takes its value pro
    # rata, so the ledger's inventory account always equals the sum of the layers exactly.
    def stock(self, it) -> int:
        return sum(q for _, q, _ in it["_layers"])

    def take(self, it, qty) -> int:
        cost = 0
        while qty > 0 and it["_layers"]:
            dd, q, v = it["_layers"][0]
            k = min(q, qty)
            if k == q:
                cost += v
                it["_layers"].popleft()
            else:
                c = v * k // q
                cost += c
                it["_layers"][0] = (dd, q - k, v - c)
            qty -= k
        return cost

    def demand(self, it, d) -> float:
        """Units a day the buyer plans for: half the plan, half the recent run rate."""
        return 0.5 * self.planned_units(it, d) + 0.5 * it["_ewma"]

    # ------------------------------------------------------------------ opening
    def opening(self, d0: date):
        total = 0
        for it in self.items:
            v = it["_vendor"]
            cover = (v["_lead"][1] if it["_cur"] != "SAR" else 7) + self.p["cover_days"]
            q = int(it["_ewma"] * cover)
            unit = int(self.purchase_price_fc(it, d0) * rate_to_sar(it["_cur"], d0) * (1.07 if it["_cur"] != "SAR" else 1))
            it["_layers"].append((d0 - timedelta(days=cover // 2), q, q * unit))
            total += q * unit
        self.b.post(d0, [("inventory", total), ("retained", -total)], "opening", "opening-stock")
        for c, flows in self.ic:
            for f in flows:
                if f["date"] >= self.start:
                    self.b.schedule(f["date"], lambda d, c=c, f=f: self.ic_invoice(d, c, f))
        # supplier order cycles
        r = self.r("cycles")
        for cur, vs in self.suppliers.items():
            for v in vs:
                first = next_working(self.start + timedelta(days=r.randint(0, v["_cycle"] - 1)))
                self.b.schedule(first, lambda d, v=v: self.vendor_order(d, v))
        # monthly promotional allowances for supermarket chains, quarterly
        self.promo_due = []

    # ------------------------------------------------------------------ the day
    def day(self, d: date):
        if not is_working_day(d):
            return
        for c in self.customers:
            if c["_next"] <= d and c["_start"] <= d:
                self.place_order(d, c)
                r = self.r("next", c["contact_id"], d)
                c["_next"] = d + timedelta(days=r.randint(*c["_freq"]))
        for it in self.items:
            q = self.sold_today.pop(it["item_id"], 0)
            it["_ewma"] = 0.97 * it["_ewma"] + 0.03 * q * 5 / 7

    def place_order(self, d, c):
        r = self.r("order", c["contact_id"], d)
        annual = H(self.p["revenue_sar_m"] * 1e6) * self.trend(d) * (self.ramp(c, d) if "_ramp" in c else c["_annual"])
        freq = sum(c["_freq"]) / 2
        value = annual * freq / 365.0 * self.day_factor(d) * lognormal(r, 1.0, 0.22)
        k = min(len(c["_assort"]), r.randint(*c["_nlines"]))
        weights = [it["_share"] for it in c["_assort"]]
        chosen = []
        pool = list(zip(c["_assort"], weights))
        for _ in range(k):
            tot = sum(w for _, w in pool)
            x = r.random() * tot
            for i, (it, w) in enumerate(pool):
                x -= w
                if x <= 0:
                    chosen.append(it)
                    pool.pop(i)
                    break
        if not chosen:
            return
        wsum = sum(it["_share"] ** 0.6 for it in chosen)
        lines, cogs = [], 0
        for it in chosen:
            v_i = value * it["_share"] ** 0.6 / wsum * lognormal(r, 1.0, 0.3)
            lp = self.list_price(it, d)
            unit_net = lp * (1 - c["_disc"])
            qty = max(1, int(round(v_i / unit_net)))
            avail = self.stock(it)
            qty = min(qty, avail)
            if qty <= 0:
                continue
            cogs += self.take(it, qty)
            self.sold_today[it["item_id"]] += qty
            lines.append({"name": it["name"], "qty": qty, "rate": lp, "discount_pct": round(c["_disc"], 4),
                          "account": "rev_sales", "item": it, "unit": it["unit"]})
        if not lines:
            return
        inv = self.b.invoice(d, c, lines, cogs=[("cogs", "inventory", cogs)], created_lag=r.choice([0, 0, 0, 1]),
                             ref=f"SO-{r.randint(100000, 999999)}")
        self.schedule_collection(inv)
        if r.random() < self.p.get("return_rate", 0.03):
            back = next_working(d + timedelta(days=r.randint(2, 12)))
            frac = r.uniform(0.02, 0.12)
            self.b.schedule(back, lambda day, inv=inv, frac=frac: self.b.credit_note(
                day, c, inv, int(inv["_total"] / 1.15 * frac), "sales_returns", "Damaged or short-dated goods returned"))
        if c["_segment"] == "key_account":
            self.promo_due.append((c, inv))

    def ic_invoice(self, d, c, f):
        """A sale to a group company: one line, the agreed amount, stock taken at cost."""
        r = self.r("ic", f["n"])
        target = int(f["net"] * (1 - self.p.get("ic_margin", 0.12)))
        cost, pool = 0, r.sample(self.items, len(self.items))
        for it in pool:
            if cost >= target:
                break
            unit = it["_layers"][0][2] // max(1, it["_layers"][0][1]) if it["_layers"] else 0
            if unit <= 0:
                continue
            q = min(self.stock(it), max(1, (target - cost) // unit))
            if q > 0:
                cost += self.take(it, q)
        inv = self.b.invoice(d, c, [{"name": f"Building materials as per delivery note {f['dn']}", "qty": 1,
                                     "rate": f["net"], "account": "rev_sales"}],
                             cogs=[("cogs", "inventory", cost)], ref=f["dn"])
        if f["paid"]:
            self.b.schedule(f["paid"], lambda day, inv=inv: self.b.customer_payment(day, c, [(inv, inv["_total"])],
                                                                                  bank="bank2", desc=f"Group settlement {f['dn']}"))

    # ------------------------------------------------------------------ purchasing
    def vendor_order(self, d, v):
        r = self.r("po", v["contact_id"], d)
        cur = v["currency_code"]
        lead = r.randint(*v["_lead"])
        lines, spec = [], []
        for it in v["_items"]:
            cover = lead + v["_cycle"] + self.p["cover_days"]
            dem = self.demand(it, d)
            target = dem * cover
            q = int(target - self.stock(it) - it["_on_order"])
            if q <= max(5, dem * 2):
                continue
            q = int(round(q / 10.0)) * 10 or 10
            price = self.purchase_price_fc(it, d)
            lines.append({"name": it["name"], "qty": q, "rate": price, "account": "inventory", "item": it,
                          "unit": it["unit"]})
            spec.append((it, q, price))
            it["_on_order"] += q
        if lines:
            rate = rate_to_sar(cur, d)
            expected = next_working(d + timedelta(days=lead))
            po = self.b.purchase_order(d, v, lines, expected, currency=cur, rate=rate)
            self.b.schedule(expected, lambda day, po=po, v=v, spec=spec: self.receive(day, po, v, spec))
        nxt = next_working(d + timedelta(days=v["_cycle"]))
        self.b.schedule(nxt, lambda day, v=v: self.vendor_order(day, v))

    def receive(self, d, po, v, spec):
        cur = v["currency_code"]
        rate = rate_to_sar(cur, d)
        r = self.r("rcv", po["purchaseorder_id"])
        lines = []
        for it, q, price in spec:
            lines.append({"name": it["name"], "qty": q, "rate": price, "account": "inventory", "item": it,
                          "unit": it["unit"]})
        before = self.bal("inventory")
        bill = self.post_bill(d, v, lines, currency=cur, rate=rate, po=po, created_lag=r.choice([0, 1, 2, 4]),
                              ref=po["purchaseorder_number"])
        base_value = self.bal("inventory") - before
        landed_extra = 0
        if cur != "SAR":
            duty = int(base_value * self.p["duty_rate"])
            clearing = int(base_value * self.p["clearing_rate"])
            import_vat = int((base_value + duty) * 0.15)
            self.post_bill(d, self.clearing,
                           [{"name": "Customs duty", "desc": f"Bill {bill['bill_number']} – {v['contact_name']}", "qty": 1,
                             "rate": duty, "account": "inventory", "vat": False},
                            {"name": "Import VAT paid at customs", "desc": "Recoverable", "qty": 1, "rate": import_vat,
                             "account": "vat_in", "vat": False},
                            {"name": "Clearing, port and transport charges", "qty": 1, "rate": clearing,
                             "account": "inventory"}], created_lag=r.choice([1, 2, 3]))
            landed_extra = duty + clearing
        total = base_value + landed_extra
        weights = [q * price for _, q, price in spec]
        wsum = sum(weights) or 1
        given = 0
        for i, ((it, q, price), w) in enumerate(zip(spec, weights)):
            val = total - given if i == len(spec) - 1 else total * w // wsum
            given += val
            it["_layers"].append((d, q, val))
            it["_on_order"] -= q

    # ------------------------------------------------------------------ month
    def month_start(self, d: date):
        y, m = d.year, d.month
        r = self.r("dmonth", y, m)
        # quarterly promotional allowance credit notes for the chains (about 1.5% of their purchases)
        if m in (1, 4, 7, 10):
            by_c = defaultdict(list)
            for c, inv in self.promo_due:
                by_c[c["contact_id"]].append((c, inv))
            self.promo_due = []
            for cid, rows in by_c.items():
                c = rows[0][0]
                base = sum(inv["_total"] for _, inv in rows)
                amt = int(base / 1.15 * self.p.get("promo_rate", 0.015) * lognormal(r, 1, 0.15))
                day = self.pick_working(r, y, m, 5, 20)

                def _promo(dd, c=c, rows=rows, amt=amt):
                    left = amt
                    for _, inv in reversed(rows):
                        if left <= 0:
                            break
                        cn = self.b.credit_note(dd, c, inv, left, "sales_returns", "Quarterly promotional allowance")
                        if cn:
                            left -= int(cn["sub_total"] * 100)
                self.b.schedule(day, _promo)
        # expired and damaged stock written off
        self.b.schedule(self.pick_working(r, y, m, 20, 28), self.write_offs)
        # S13: recurring merchandising services billed to the chains, booked to "Miscellaneous income"
        st13 = self.story("S13")
        if st13 and d >= date.fromisoformat(st13["start"]):
            chains = sorted([c for c in self.customers if c.get("_segment") == "key_account"], key=lambda c: -c["_annual"])[:4]
            py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
            for c in chains:
                amt = int(H(self.p["revenue_sar_m"] * 1e6) * self.trend(d) * st13["share_of_revenue"] / 12 / len(chains)
                          * lognormal(r, 1, 0.08))
                day = self.pick_working(r, y, m, 3, 10)
                self.b.schedule(day, lambda dd, c=c, amt=amt, py=py, pm=pm: self.schedule_collection(self.b.invoice(
                    dd, c, [{"name": f"Merchandising and shelf-display services – {mlabel(py, pm)}", "qty": 1,
                             "rate": amt, "account": "misc_income"}], ref=f"SVC-{py}{pm:02d}")))

    def write_offs(self, d):
        r = self.r("wo", d.year, d.month)
        lines = []
        for it in self.items:
            if it["_family"] not in ("Dairy and cheese", "Frozen poultry and meat", "Confectionery and snacks"):
                continue
            if r.random() < 0.25:
                q = max(1, int(self.stock(it) * r.uniform(0.002, 0.012)))
                if q < self.stock(it):
                    lines.append((it, q, self.take(it, q)))
        if lines:
            self.b.inventory_adjustment(d, lines, "Expired and damaged stock written off")

    def close_sector(self, d, lag):
        y, m = d.year, d.month
        self.truth["stock"].append({"month": f"{y}-{m:02d}", "inventory_value": self.bal("inventory"),
                                    "layers_value": sum(v for it in self.items for _, _, v in it["_layers"]),
                                    "older_than_180_days": sum(v for it in self.items for dd, _, v in it["_layers"]
                                                               if (d - dd).days > 180)})
