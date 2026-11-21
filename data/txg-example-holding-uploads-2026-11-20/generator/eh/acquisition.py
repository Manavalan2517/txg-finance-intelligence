"""The acquisition universe: a made-up target with a data room, a list of candidates, and listed peers.

The target's statements come from a small annual model in which the balance sheet balances and the cash-flow
statement reconciles by construction. Planted facts the engines should find: debt-like items (end-of-service
benefits, a Zakat assessment under appeal, a change-of-control prepayment clause), related-party rent,
customer concentration, and an asking price above what credible synergies support (story S10).
"""
import csv
import json
import os

from .pdf import PDF, sar
from .util import H, S, rng_for

TARGET = {"id": "TGT-01", "name": "Example Cold Chain Logistics Co. (made-up)", "city": "Dammam", "region": "Eastern Province",
          "cr": "TEST-CR-T001", "vat": "TEST-VAT-T001", "founded": 2009}
ASK_EV = 520_000_000  # asking enterprise value, SAR, cash-free and debt-free


def target_model():
    """Annual statements FY2022–FY2025 (SAR halalas). FY2022 only provides the opening balance sheet."""
    rev = {2022: 138e6, 2023: 152e6, 2024: 166e6, 2025: 181e6}
    out = {}
    prev = {"ppe": H(188e6), "rou": H(44e6), "debt": H(78e6), "lease": H(48e6), "eosb": H(9.4e6), "share": H(60e6),
            "reserve": H(18e6), "retained": H(60e6), "zakat_pay": H(1.9e6)}
    for y in (2022, 2023, 2024, 2025):
        R = H(rev[y])
        seg = {"Refrigerated transport": int(R * 0.62), "Cold storage": int(R * 0.30)}
        seg["Value-added services"] = R - sum(seg.values())
        cor = int(R * 0.618)
        ga = int(R * 0.142)
        oth = int(R * 0.004)
        ebitda = R - cor - ga + oth
        capex = int(R * (0.085 if y != 2024 else 0.15))
        dep = int(prev["ppe"] * 0.085)
        new_leases = H({2022: 4e6, 2023: 3e6, 2024: 9e6, 2025: 4e6}[y])
        rou_dep = int((prev["rou"] + new_leases) * 0.11)
        borrow = H({2022: 0, 2023: 0, 2024: 25e6, 2025: 0}[y])
        repay = H({2022: 10e6, 2023: 10e6, 2024: 10e6, 2025: 12e6}[y])
        debt = prev["debt"] + borrow - repay
        int_b = int((prev["debt"] + debt) / 2 * 0.066)
        int_l = int(prev["lease"] * 0.06)
        lease_pay = int(prev["lease"] * 0.21)
        lease = prev["lease"] + new_leases + int_l - lease_pay
        pbz = ebitda - dep - rou_dep - int_b - int_l
        zakat = int(max(pbz, H(70e6)) * 0.025)
        ni = pbz - zakat
        div = H({2022: 2e6, 2023: 3e6, 2024: 0, 2025: 4e6}[y])
        ppe = prev["ppe"] + capex - dep
        rou = prev["rou"] + new_leases - rou_dep
        eosb = prev["eosb"] + H(1.1e6)
        bs = {"Property, vehicles and equipment": ppe, "Right-of-use assets": rou,
              "Trade receivables": int(R * 76 / 365 * 1.15), "Inventories (spares and fuel)": int(R * 0.015),
              "Prepayments and other receivables": int(R * 0.03)}
        liab = {"Borrowings": debt, "Lease liabilities": lease, "End-of-service benefits": eosb,
                "Trade payables": int(cor * 0.6 * 50 / 365 * 1.15), "Accruals and other payables": int(R * 0.04),
                "VAT payable": int(R * 0.009), "Zakat payable": zakat}
        retained = prev["retained"] + ni - div
        equity = {"Share capital": prev["share"], "Statutory reserve": prev["reserve"], "Retained earnings": retained}
        cash = sum(liab.values()) + sum(equity.values()) - sum(bs.values())
        bs = dict({"Cash and cash equivalents": cash}, **bs)
        out[y] = {"revenue": R, "segments": seg, "cost_of_revenue": cor, "ga": ga, "other_income": oth, "ebitda": ebitda,
                  "dep": dep, "rou_dep": rou_dep, "int_b": int_b, "int_l": int_l, "zakat": zakat, "ni": ni, "div": div,
                  "capex": capex, "new_leases": new_leases, "borrow": borrow, "repay": repay, "lease_pay": lease_pay,
                  "assets": bs, "liabilities": liab, "equity": equity, "current_debt": H(12e6)}
        prev = {"ppe": ppe, "rou": rou, "debt": debt, "lease": lease, "eosb": eosb, "share": prev["share"],
                "reserve": prev["reserve"], "retained": retained, "zakat_pay": zakat, "bs": bs, "liab": liab}
    for y in (2023, 2024, 2025):
        a, p = out[y], out[y - 1]
        wc = lambda d, k: d[k]
        d_rec = a["assets"]["Trade receivables"] - p["assets"]["Trade receivables"]
        d_inv = a["assets"]["Inventories (spares and fuel)"] - p["assets"]["Inventories (spares and fuel)"]
        d_pre = a["assets"]["Prepayments and other receivables"] - p["assets"]["Prepayments and other receivables"]
        d_pay = sum(a["liabilities"][k] - p["liabilities"][k] for k in ("Trade payables", "Accruals and other payables", "VAT payable"))
        zakat_paid = p["liabilities"]["Zakat payable"]
        eosb_exp = a["liabilities"]["End-of-service benefits"] - p["liabilities"]["End-of-service benefits"]
        cfo = (a["ni"] + a["zakat"] + a["dep"] + a["rou_dep"] + a["int_b"] + a["int_l"] + eosb_exp
               - d_rec - d_inv - d_pre + d_pay - zakat_paid)
        cfi = -a["capex"]
        cff = a["borrow"] - a["repay"] - a["int_b"] - a["lease_pay"] - a["div"]
        a["cash_flow"] = {"Profit before Zakat": a["ni"] + a["zakat"], "Depreciation": a["dep"] + a["rou_dep"],
                          "Finance costs": a["int_b"] + a["int_l"], "End-of-service benefits charge": eosb_exp,
                          "Change in trade receivables": -d_rec, "Change in inventories": -d_inv,
                          "Change in prepayments": -d_pre, "Change in payables and accruals": d_pay,
                          "Zakat paid": -zakat_paid, "Net cash from operating activities": cfo,
                          "Purchase of property, vehicles and equipment": cfi, "Net cash used in investing activities": cfi,
                          "Proceeds from borrowings": a["borrow"], "Repayment of borrowings": -a["repay"],
                          "Interest paid": -a["int_b"], "Lease payments": -a["lease_pay"], "Dividends paid": -a["div"],
                          "Net cash used in financing activities": cff, "Net change in cash": cfo + cfi + cff,
                          "Cash at the beginning of the year": p["assets"]["Cash and cash equivalents"],
                          "Cash at the end of the year": p["assets"]["Cash and cash equivalents"] + cfo + cfi + cff}
    return out


def statements_pdf(path, y, a):
    doc = PDF(f"{TARGET['name']} – financial statements {y}")
    doc.heading(TARGET["name"], 14)
    doc.para(f"Financial statements for the year ended 31 December {y} (Saudi riyals)", bold=True)
    doc.heading("Independent auditor's report", 11)
    doc.para(f"To the shareholders of {TARGET['name']}. We have audited the financial statements, which comprise the "
             f"statement of financial position as at 31 December {y}, and the statements of profit or loss, changes in "
             "equity and cash flows for the year, and notes. In our opinion they present fairly, in all material respects, "
             "the financial position of the Company and its financial performance and cash flows in accordance with "
             "International Financial Reporting Standards as endorsed in the Kingdom of Saudi Arabia. Without modifying "
             "our opinion, we draw attention to note 8 on the Zakat assessment under appeal.")
    doc.para("Example Audit and Advisory (Chartered Accountants) (made-up), Al-Khobar", size=9)
    doc.heading("Statement of profit or loss", 11)
    rows = [["", "SAR"], ["Revenue", sar(a["revenue"])], ["Cost of revenue (excluding depreciation)", sar(-a["cost_of_revenue"])],
            ["General and administrative expenses", sar(-a["ga"])], ["Other income", sar(a["other_income"])],
            ["Depreciation of property, vehicles and equipment", sar(-a["dep"])],
            ["Depreciation of right-of-use assets", sar(-a["rou_dep"])],
            ["Operating profit", sar(a["ebitda"] - a["dep"] - a["rou_dep"])],
            ["Finance costs on borrowings", sar(-a["int_b"])], ["Finance costs on lease liabilities", sar(-a["int_l"])],
            ["Profit before Zakat", sar(a["ni"] + a["zakat"])], ["Zakat", sar(-a["zakat"])], ["Total profit for the year", sar(a["ni"])]]
    doc.table(rows, [56, 20])
    doc.heading("Statement of financial position", 11)
    rows = [["Assets", "SAR"]] + [[k, sar(v)] for k, v in a["assets"].items()] + [["Total assets", sar(sum(a["assets"].values()))]]
    doc.table(rows, [56, 20])
    rows = [["Liabilities and equity", "SAR"]] + [[k, sar(v)] for k, v in a["liabilities"].items()] + \
           [[k, sar(v)] for k, v in a["equity"].items()] + \
           [["Total liabilities and equity", sar(sum(a["liabilities"].values()) + sum(a["equity"].values()))]]
    doc.table(rows, [56, 20])
    doc.heading("Statement of cash flows", 11)
    doc.table([["", "SAR"]] + [[k, sar(v)] for k, v in a["cash_flow"].items()], [56, 20])
    doc.heading("Notes (extract)", 11)
    seg = a["segments"]
    doc.para("1. Revenue by service line: " + "; ".join(f"{k} SAR {sar(v)}" for k, v in seg.items()) + ".")
    doc.para("2. Customers: the largest customer accounted for 14% of revenue and the five largest for 47%. The contract "
             "with the largest customer runs to 31 March 2027.")
    doc.para(f"3. Borrowings: secured term loans from Example Bank E (made-up) at three-month SAIBOR plus 2.4%; SAR "
             f"{sar(a['current_debt'])} is due within twelve months. The facility agreement requires prepayment in full on "
             "a change of control of the Company.")
    doc.para("4. Leases: warehouses in Dammam, Riyadh and Jeddah and part of the truck fleet are leased. The Dammam "
             "warehouse is leased from Al-Ufuq Real Estate Co. (made-up), owned by the Company's main shareholder, for "
             "SAR 4,200,000 a year (note 7).")
    doc.para(f"5. End-of-service benefits: SAR {sar(a['liabilities']['End-of-service benefits'])}, unfunded, measured by an "
             "actuarial valuation.")
    doc.para("6. Fleet and capacity: 214 refrigerated trucks and 96 reefer trailers; 42,000 pallet positions in three cold stores.")
    doc.para("7. Related parties: rent paid to Al-Ufuq Real Estate Co. (made-up), SAR 4,200,000; no other transactions.")
    doc.para("8. Contingent liability: ZATCA has assessed additional Zakat of SAR 3,100,000 for 2021. The Company has appealed "
             "and, on its advisers' view, has made no provision.")
    doc.save(path)


def build_acquisition(out, key_dir):
    adir = os.path.join(out, "acquisition")
    room = os.path.join(adir, "data_room", TARGET["id"])
    os.makedirs(room, exist_ok=True)
    os.makedirs(key_dir, exist_ok=True)
    m = target_model()
    checks = []
    for y in (2023, 2024, 2025):
        a = m[y]
        statements_pdf(os.path.join(room, f"02_audited_financial_statements_FY{y}.pdf"), y, a)
        bal = sum(a["assets"].values()) - sum(a["liabilities"].values()) - sum(a["equity"].values())
        tie = a["cash_flow"]["Cash at the end of the year"] - a["assets"]["Cash and cash equivalents"]
        checks.append({"year": y, "balance_sheet_balances": bal == 0, "cash_flow_ties": tie == 0,
                       "cash": S(a["assets"]["Cash and cash equivalents"])})
    # process letter with the asking price
    doc = PDF("Project Frost – process letter")
    doc.heading("Project Frost – sale of a cold-chain logistics business", 14)
    doc.para("Strictly private and confidential. Process letter issued by the seller's adviser, Example Capital (made-up).", size=9)
    doc.para(f"The shareholders of {TARGET['name']} ('the Company'), a cold-chain logistics provider based in "
             f"{TARGET['city']} serving food manufacturers, distributors and restaurant chains across the Kingdom, invite "
             "non-binding offers for 100% of the Company's shares.")
    doc.para(f"Indicative valuation expectation: an enterprise value of SAR {ASK_EV:,.0f} on a cash-free, debt-free basis, "
             "with a normal level of working capital. Offers should state the enterprise value, the bridge to equity value "
             "and all assumptions on debt and debt-like items.", bold=True)
    doc.bullets(["Data room opens: 1 November 2026", "Non-binding offers due: 15 January 2027",
                 "Management presentations: February 2027", "Binding offers: April 2027"])
    doc.save(os.path.join(room, "01_process_letter.pdf"))
    # company profile
    doc = PDF("Company profile")
    doc.heading(f"{TARGET['name']} – company profile", 14)
    doc.para(f"Founded in {TARGET['founded']} in {TARGET['city']}. CR {TARGET['cr']}, VAT {TARGET['vat']}.")
    doc.bullets(["Refrigerated transport across the Eastern, Central and Western regions; 214 trucks, 96 reefer trailers.",
                 "Cold stores: Dammam 18,000 pallet positions (leased from a shareholder company), Riyadh 14,000, Jeddah 10,000.",
                 "Customers: food manufacturers (41% of revenue), food distributors (27%), restaurant chains (22%), pharmaceutical (10%).",
                 "Employees: 1,180, of which 21% Saudi nationals.",
                 "Routes overlap heavily with food distributors' delivery routes in the Eastern Province and Riyadh."])
    doc.save(os.path.join(room, "05_company_profile.pdf"))
    # facility letter
    doc = PDF("Facility letter – target")
    doc.heading("Example Bank E (made-up) – facility letter", 14)
    a = m[2025]
    doc.para(f"Borrower: {TARGET['name']}. Secured term loans; outstanding at 31 December 2025: SAR {sar(a['liabilities']['Borrowings'])}. "
             "Interest at three-month SAIBOR plus 2.40% a year. Repayable in equal quarterly instalments of SAR 3,000,000.")
    doc.para("Change of control: if any person other than the current shareholders acquires control of the Borrower, all "
             "amounts outstanding become due and payable within 30 days.", bold=True)
    doc.para("Financial covenants: net debt (excluding lease liabilities) not more than 3.0 times EBITDA; debt service cover "
             "at least 1.3 times; tested on 30 June and 31 December.")
    doc.save(os.path.join(room, "04_facility_letter.pdf"))
    # management accounts 2026 to date
    r = rng_for("target", "mgmt")
    with open(os.path.join(room, "03_management_accounts_2026_ytd.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([TARGET["name"], "Management accounts 2026 (unaudited, SAR)"])
        w.writerow(["month", "revenue", "cost_of_revenue", "general_and_administrative", "ebitda"])
        for mo in range(1, 11):
            rv = 181e6 / 12 * 1.07 * (1.0 + 0.04 * (mo in (6, 7, 8)) - 0.03 * (mo in (2, 3))) * r.lognormvariate(0, 0.03)
            cr_ = rv * 0.628 * r.lognormvariate(0, 0.01)
            ga = 181e6 * 0.142 / 12 * 1.05
            w.writerow([f"2026-{mo:02d}", f"{rv:.2f}", f"{cr_:.2f}", f"{ga:.2f}", f"{rv - cr_ - ga:.2f}"])
    # structured copy of the statements (as filed)
    with open(os.path.join(room, "06_statements_structured.json"), "w", encoding="utf-8") as f:
        json.dump({str(y): {"revenue": S(m[y]["revenue"]), "ebitda": S(m[y]["ebitda"]),
                            "operating_profit": S(m[y]["ebitda"] - m[y]["dep"] - m[y]["rou_dep"]), "net_profit": S(m[y]["ni"]),
                            "assets": {k: S(v) for k, v in m[y]["assets"].items()},
                            "liabilities": {k: S(v) for k, v in m[y]["liabilities"].items()},
                            "equity": {k: S(v) for k, v in m[y]["equity"].items()},
                            "cash_flow": {k: S(v) for k, v in m[y].get("cash_flow", {}).items()}}
                   for y in (2023, 2024, 2025)}, f, indent=1)
    cands = candidates()
    with open(os.path.join(adir, "candidates.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["candidate_id", "name", "region", "city", "revenue_band_sar_m", "listed", "cr_number", "description"])
        for c in cands:
            w.writerow([c["id"], c["name"], c["region"], c["city"], c["band"], c["listed"], c["cr"], c["description"]])
    peers = listed_peers()
    with open(os.path.join(adir, "listed_peers.json"), "w", encoding="utf-8") as f:
        json.dump({"as_of": "2026-11-19", "note": "Made-up listed companies on a made-up exchange.", "peers": peers}, f, indent=1)
    with open(os.path.join(key_dir, "target_truth.json"), "w", encoding="utf-8") as f:
        json.dump({"target": TARGET, "asking_enterprise_value_sar": ASK_EV,
                   "ebitda_fy2025_sar": S(m[2025]["ebitda"]), "asking_multiple_fy2025_ebitda": round(ASK_EV / S(m[2025]["ebitda"]), 2),
                   "debt_like_items": ["borrowings repayable on change of control", "lease liabilities", "end-of-service benefits",
                                       "Zakat assessment under appeal SAR 3.1m (not provided)", "Zakat payable"],
                   "planted_facts": ["related-party rent for the Dammam warehouse", "largest customer 14%, top five 47%, "
                                     "largest contract ends 31 March 2027", "route overlap with EH-08 and EH-09 deliveries"],
                   "statement_checks": checks,
                   "story": "S10: the asking price is above what credible synergies support; the verdict is the engines' to compute."},
                  f, indent=1)
    with open(os.path.join(key_dir, "candidates_truth.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["candidate_id", "name", "true_sector", "comparable_to_target", "note"])
        for c in cands:
            w.writerow([c["id"], c["name"], c["sector"], c["peer"], c.get("note", "")])
    return checks


def candidates():
    r = rng_for("acq", "candidates")
    rows = []
    cities = {"Eastern Province": ["Dammam", "Khobar", "Jubail", "Al-Ahsa"], "Central": ["Riyadh", "Al-Kharj", "Buraidah"],
              "Western": ["Jeddah", "Makkah", "Madinah"], "Southern": ["Abha", "Jazan"]}

    def add(name, sector, region, band, listed, desc, peer, note=""):
        n = len(rows) + 1
        rows.append({"id": f"CAND-{n:02d}", "name": name, "sector": sector, "region": region,
                     "city": r.choice(cities[region]), "band": band, "listed": listed, "cr": f"TEST-CR-C{n:03d}",
                     "description": desc, "peer": peer, "note": note})
    add(TARGET["name"], "cold chain", "Eastern Province", "150–200", False,
        "We move and store chilled and frozen food for manufacturers, distributors and restaurant chains. Our 214 refrigerated "
        "trucks and three cold stores in Dammam, Riyadh and Jeddah run around the clock.", True, "the deep-dive target")
    for name, region, band, desc in [
        ("Polar Line Transport Co.", "Central", "200–300", "Temperature-controlled trucking for dairy, poultry and frozen foods, with a fleet of 260 reefer trucks and cross-docks in Riyadh and Al-Kharj."),
        ("Frostway Cold Stores Est.", "Western", "50–100", "Public cold storage in Jeddah with 22,000 pallet positions, blast freezing and order picking for importers."),
        ("Najd Chilled Distribution Co.", "Central", "100–150", "Last-mile delivery of chilled and frozen products to supermarkets and restaurants across Riyadh."),
        ("Gulf Reefer Services Co.", "Eastern Province", "100–150", "Refrigerated haulage between the Eastern Province ports and inland cities, plus a 9,000-pallet cold store in Dammam."),
        ("Coldchain Pharma Logistics Co.", "Central", "50–100", "Good-distribution-practice storage and delivery of vaccines and medicines for hospitals and pharmacies."),
        ("Red Sea Cold Logistics Co.", "Western", "100–150", "Port-side cold storage and reefer transport for seafood and fruit importers on the Red Sea coast."),
        ("Ice Route Transport Est.", "Southern", "20–50", "A regional fleet of 45 refrigerated vans serving bakeries, dairies and restaurants in the south."),
    ]:
        add(name, "cold chain", region, band, False, desc, True)
    add("Polar Trading Co.", "HVAC retail", "Eastern Province", "50–100", False,
        "We sell and install air conditioners, chillers and refrigeration units for homes and shops.", False,
        "namesake: 'polar' and 'refrigeration' in its words, but it sells equipment and is not a logistics company")
    add("Frost Line Contracting Est.", "MEP contracting", "Central", "20–50", False,
        "MEP contractor specialising in cold-room construction and HVAC installation for warehouses.", False,
        "namesake: builds cold rooms for others; a contractor, not a cold-chain operator")
    for name, region, band, desc in [
        ("Sanabel Food Distribution Co.", "Central", "300–500", "Distributes rice, oils, dairy and frozen foods to supermarkets and caterers nationwide."),
        ("Golden Basket Trading Co.", "Western", "200–300", "Wholesale and modern-trade distribution of packaged food brands in the Western region."),
        ("Al-Reef Provisions Co.", "Eastern Province", "100–150", "Food service distribution to hotels, restaurants and hospital caterers."),
        ("Tamr Foodstuff Trading Est.", "Central", "50–100", "Distribution of dates, nuts and confectionery to retailers."),
        ("Bayside Frozen Foods Co.", "Western", "100–150", "Imports and distributes frozen poultry, meat and seafood."),
        ("Desert Rose Catering Supplies", "Southern", "20–50", "Supplies dry goods and disposables to restaurants and canteens."),
    ]:
        add(name, "food distribution", region, band, False, desc, False)
    for name, region, band, desc in [
        ("Rimal Building Materials Co.", "Central", "300–500", "Cement, steel and blocks for contractors, with six yards around Riyadh."),
        ("Coastline Tiles and Sanitary Co.", "Western", "100–150", "Showrooms and project sales of tiles, sanitary ware and fittings."),
        ("Ironbridge Steel Trading Co.", "Eastern Province", "200–300", "Rebar and structural steel trading for contractors and fabricators."),
        ("Brightwall Paints Trading Est.", "Central", "50–100", "Distribution of paints, coatings and construction chemicals."),
        ("Palmyard Building Supplies", "Southern", "20–50", "General building materials for small contractors and homeowners."),
        ("Granite House Co.", "Western", "50–100", "Imports and processes granite and marble for projects."),
        ("Pipeline Supplies Co.", "Eastern Province", "100–150", "Pipes, valves and fittings for contractors and industry."),
    ]:
        add(name, "building materials", region, band, False, desc, False)
    for name, region, band, desc in [
        ("Shifa Medical Centres Co.", "Central", "150–200", "Five polyclinics in Riyadh with dental, paediatrics and family medicine."),
        ("Al-Afiya Pharmacies Co.", "Western", "100–150", "A chain of 48 community pharmacies in Jeddah and Makkah."),
        ("Coastal Diagnostic Labs Co.", "Eastern Province", "50–100", "Laboratory testing and radiology for clinics and insurers."),
        ("Najd Home Care Est.", "Central", "20–50", "Home nursing and physiotherapy services."),
        ("Al-Salama Day Surgery Co.", "Western", "50–100", "Day-surgery centres for ophthalmology and orthopaedics."),
        ("Summit Dental Clinics Co.", "Southern", "20–50", "Dental clinics in Abha and Khamis Mushait."),
    ]:
        add(name, "healthcare", region, band, False, desc, False)
    return rows


def listed_peers():
    r = rng_for("acq", "peers")
    out = []
    for i, (name, sector, rev0, margin, mult) in enumerate([
        ("Gulf Reefer Logistics Co.", "cold chain and logistics", 610e6, 0.205, 9.6),
        ("Polar Freight Holding Co.", "cold chain and logistics", 1240e6, 0.17, 8.4),
        ("Coastline Freight Services Co.", "logistics", 890e6, 0.15, 7.9),
        ("Najd Cold Stores Co.", "cold chain and logistics", 330e6, 0.27, 10.8),
        ("Oasis Provisions Co.", "food distribution", 2100e6, 0.075, 11.5),
        ("Red Sea Foods Distribution Co.", "food distribution", 1460e6, 0.069, 10.2),
        ("Golden Crescent Foods Co.", "food distribution", 980e6, 0.081, 12.4),
        ("Al-Bayan Food Services Co.", "food distribution", 760e6, 0.064, 9.1)], start=1):
        years = {}
        rev = rev0
        for y in (2023, 2024, 2025):
            rev *= 1 + r.uniform(0.03, 0.09)
            e = rev * margin * r.lognormvariate(0, 0.04)
            years[str(y)] = {"revenue": round(rev, -3), "ebitda": round(e, -3), "ebit": round(e * 0.55, -3),
                             "net_profit": round(e * 0.38, -3)}
        ebitda = years["2025"]["ebitda"]
        nd = round(ebitda * r.uniform(0.8, 2.4), -3)
        ev = ebitda * mult
        shares = round(r.uniform(40, 160)) * 1e6
        price = round((ev - nd) / shares, 2)
        out.append({"name": name, "ticker": f"TEST.{4100 + i}", "exchange": "Example Exchange (made-up)", "sector": sector,
                    "share_price_sar": price, "shares_outstanding": shares, "net_debt_excl_leases_sar": nd,
                    "lease_liabilities_sar": round(ebitda * r.uniform(0.3, 0.9), -3), "statements": years})
    return out
