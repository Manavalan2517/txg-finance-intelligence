"""The files that do not come from Zoho Books: printed trial balances, budgets, facility letters, payroll and
headcount, store data and company settings. All are computed from the same simulated books.
"""
import csv
import json
import math
import os
from collections import defaultdict
from datetime import date, timedelta

from .chart import STD_NAMES
from .common import mlabel
from .markets import saibor
from .pdf import PDF, sar
from .util import H, S, add_months, dim, month_end, rng_for

PL = "ICXO"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _closed_months(sim):
    out, (y, m) = [], (sim.go_live.year, sim.go_live.month)
    while sim.closed(y, m):
        out.append((y, m))
        y, m = add_months(y, m, 1)
    return out


# ================================================================= printed trial balances
def trial_balances(sim, up_dir, key_dir):
    """Zoho's Trial Balance report for each closed month: balance-sheet accounts at the month end, income and
    expense accounts for the fiscal year to date, earlier years' profit inside retained earnings."""
    b = sim.b
    st12 = sim.story("S12")
    tdir = os.path.join(up_dir, "trial_balances")
    os.makedirs(tdir, exist_ok=True)
    lines = sorted(b.lines, key=lambda l: l[0])
    cum, ystart, i = defaultdict(int), defaultdict(int), 0
    cur_year = None
    planted = None
    if st12:
        j = next(x for x in b.docs["journals"] if x["reference_number"] == st12["journal_ref"])
        planted = (st12["month"], j["journal_id"])
    records = []
    for (y, m) in _all_months(sim.start, month_end(*_closed_months(sim)[-1])):
        if cur_year != y:
            ystart = dict(cum)
            cur_year = y
        cut = month_end(y, m)
        while i < len(lines) and lines[i][0] <= cut:
            cum[lines[i][1]] += lines[i][2]
            i += 1
        if date(y, m, 1) < sim.go_live:
            continue
        ym = f"{y}-{m:02d}"
        bal = _tb_balances(b, cum, ystart)
        if planted and planted[0] == ym:
            wrong = dict(bal)
            for ln in b.lines:
                if ln[4] == planted[1]:
                    wrong[ln[1]] -= ln[2]
            _write_tb(sim, os.path.join(tdir, f"trial_balance_{ym}.csv"), wrong, cut, "Printed at close")
            _write_tb(sim, os.path.join(tdir, f"trial_balance_{ym}_corrected.csv"), bal, cut, "Reprinted after the late entry")
            records.append({"month": ym, "ties_to_books": False, "difference_accounts": [k for k in bal if bal[k] != wrong[k]],
                            "note": "Printed before the month's depreciation journal was posted (story S12); the corrected "
                                    "file arrives through the change feed."})
        else:
            _write_tb(sim, os.path.join(tdir, f"trial_balance_{ym}.csv"), bal, cut, "Run after the close")
            records.append({"month": ym, "ties_to_books": True})
    with open(os.path.join(key_dir, "trial_balance_ties.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1)


def _all_months(a, b):
    out, (y, m) = [], (a.year, a.month)
    while (y, m) <= (b.year, b.month):
        out.append((y, m))
        y, m = add_months(y, m, 1)
    return out


def _tb_balances(b, cum, ystart):
    bal = {}
    pl_before = sum(v for k, v in ystart.items() if b.chart[k].group in PL)
    for k, a in b.chart.items():
        if a.group in PL:
            bal[k] = cum.get(k, 0) - ystart.get(k, 0)
        else:
            bal[k] = cum.get(k, 0) + (pl_before if k == "retained" else 0)
    return bal


def _write_tb(sim, path, bal, cut, note):
    b = sim.b
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([sim.c["legal_name"]])
        w.writerow(["Trial Balance"])
        w.writerow([f"As of {cut:%d/%m/%Y}", "Basis: Accrual", note])
        w.writerow([])
        w.writerow(["Account", "Account Code", "Account Type", "Net Debit", "Net Credit"])
        td = tc = 0
        for k, a in sorted(b.chart.items(), key=lambda kv: kv[1].code):
            v = bal.get(k, 0)
            if not v:
                continue
            td += max(v, 0)
            tc += max(-v, 0)
            w.writerow([a.name, a.code, a.zoho_type, f"{S(v):.2f}" if v > 0 else "", f"{S(-v):.2f}" if v < 0 else ""])
        w.writerow(["Total", "", "", f"{S(td):.2f}", f"{S(tc):.2f}"])


# ================================================================= budgets
def _monthly_pl(sim):
    b = sim.b
    out = defaultdict(lambda: defaultdict(int))
    for d, k, amt, *_ in b.lines:
        a = b.chart[k]
        if a.group not in PL:
            continue
        s = a.std
        grp = ("revenue" if s == "4100" else "other_income" if s == "4200" else "cost_of_sales" if s.startswith("5")
               else "da" if s in ("6600", "6610", "6700") else "opex" if s.startswith("6")
               else "zakat" if s == "7600" else "finance")
        out[(d.year, d.month)][grp] += amt
    return out


def budgets(sim, up_dir, key_dir):
    """Each year's budget is set in December from the year just ending, with the management's growth plan and,
    where a story says so, optimism (S11)."""
    pl = _monthly_pl(sim)
    r = rng_for(sim.code, "budget")
    st11 = sim.story("S11")
    bdir = os.path.join(up_dir, "budgets")
    os.makedirs(bdir, exist_ok=True)
    plan_growth = sim.p.get("growth", 0.04) + 0.02
    rows_key = []
    for Y in range(sim.go_live.year, sim.data_end.year + 1):
        prev = [pl[(Y - 1, m)] for m in range(1, 13)]
        rev_prev = sum(-x["revenue"] for x in prev)
        gm_prev = (rev_prev - sum(x["cost_of_sales"] for x in prev)) / rev_prev if rev_prev else 0
        year_bias = r.gauss(0.02, 0.03)
        lines = defaultdict(list)
        for m in range(1, 13):
            x = prev[m - 1]
            q = (m - 1) // 3 + 1
            bias = year_bias
            if st11:
                bias = st11["quarter_bias"].get(f"{Y}Q{q}", st11["mean_bias"])
            rev = -x["revenue"] * (1 + plan_growth + bias) * (1 + r.gauss(0, 0.02))
            cos = rev * (1 - gm_prev - 0.003)
            opex = x["opex"] * 1.03 * (1 + r.gauss(0, 0.02))
            oth = -x["other_income"]
            ebitda = rev - cos - opex + oth
            da = x["da"] * 1.04
            fin = x["finance"]
            zak = x["zakat"] * 1.03
            vals = {"Revenue": rev, "Cost of sales": cos, "Gross profit": rev - cos, "Operating expenses": opex,
                    "Other operating income": oth, "EBITDA": ebitda, "Depreciation and amortisation": da,
                    "Operating profit": ebitda - da, "Finance costs (net)": fin, "Zakat": zak,
                    "Net profit": ebitda - da - fin - zak}
            for k, v in vals.items():
                lines[k].append(int(v))
        approved = date(Y - 1, 12, 18)
        with open(os.path.join(bdir, f"budget_{Y}.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([sim.c["legal_name"]])
            w.writerow([f"Budget {Y} (SAR)", f"Approved by the board on {approved:%d/%m/%Y}"])
            w.writerow([])
            w.writerow(["Line"] + [f"{MONTHS[m - 1]} {Y}" for m in range(1, 13)] + ["Total"])
            for k, vs in lines.items():
                w.writerow([k] + [f"{S(v):.2f}" for v in vs] + [f"{S(sum(vs)):.2f}"])
        for q in range(1, 5):
            ms = range(3 * q - 2, 3 * q + 1)
            if month_end(Y, 3 * q) >= sim.first_open:
                continue
            act_rev = sum(-pl[(Y, m)]["revenue"] for m in ms)
            act_e = sum(-pl[(Y, m)]["revenue"] + pl[(Y, m)]["other_income"] * -1 - pl[(Y, m)]["cost_of_sales"]
                        - pl[(Y, m)]["opex"] for m in ms)
            bud_rev = sum(lines["Revenue"][m - 1] for m in ms)
            bud_e = sum(lines["EBITDA"][m - 1] for m in ms)
            rows_key.append({"quarter": f"{Y}Q{q}", "revenue_budget": S(bud_rev), "revenue_actual": S(act_rev),
                             "revenue_error": round(bud_rev / act_rev - 1, 4) if act_rev else None,
                             "ebitda_budget": S(bud_e), "ebitda_actual": S(act_e),
                             "ebitda_error": round(bud_e / act_e - 1, 4) if act_e else None})
    with open(os.path.join(key_dir, "budget_vs_actual.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_key[0]))
        w.writeheader()
        w.writerows(rows_key)
    return rows_key


# ================================================================= facility letters
def facilities(sim, kpi_rows, up_dir, key_dir):
    p, c = sim.p, sim.c
    fdir = os.path.join(up_dir, "facility_letters")
    os.makedirs(fdir, exist_ok=True)
    st = p.get("covenants", {})
    nd = [r.get("HL-8_net_debt_to_ebitda_excl_leases") for r in kpi_rows if r["month"] >= "2024-01"]
    nd = [x for x in nd if x is not None]
    ic = [r.get("FG-1_interest_cover_ltm") for r in kpi_rows if r["month"] >= "2024-01"]
    ic = [x for x in ic if x is not None]
    lev = st.get("leverage") or max(3.0, math.ceil((max(nd + [0]) + 1.0) * 4) / 4)
    cov = [{"name": "Leverage", "test": "net_debt_to_ebitda_max", "threshold": lev, "frequency": "quarterly, last twelve months"}]
    if st.get("dscr"):
        cov.append({"name": "Debt service cover", "test": "dscr_min", "threshold": st["dscr"], "frequency": "quarterly, last twelve months"})
    elif ic and min(ic) > 4.5:
        cov.append({"name": "Interest cover", "test": "interest_cover_min", "threshold": 3.0, "frequency": "quarterly, last twelve months"})
    if st.get("min_liquidity_sar_m"):
        cov.append({"name": "Minimum liquidity", "test": "cash_plus_undrawn_min", "threshold_sar": st["min_liquidity_sar_m"] * 1e6,
                    "frequency": "at all times"})
    pre16 = sim.sector == "retail"
    by_lender = defaultdict(list)
    for ln in p.get("loans", []):
        by_lender[ln["lender"]].append(("term", ln))
    if p.get("rcf"):
        by_lender[p["rcf"]["lender"]].append(("rcf", p["rcf"]))
    truth = []
    for n, (lender, facs) in enumerate(sorted(by_lender.items()), start=1):
        first = min((date.fromisoformat(f["drawn"]) for k, f in facs if k == "term"), default=date(2025, 12, 15))
        dated = min(first - timedelta(days=21), date(2025, 12, 15))
        ref = f"FOL/{c['code']}/{dated.year}/{n:02d}"
        doc = PDF(f"Facility offer letter {ref}")
        doc.heading(lender, 15)
        doc.para("Corporate Banking Group, Riyadh, Kingdom of Saudi Arabia (made-up address)", size=9)
        doc.space(6)
        doc.para(f"Ref: {ref}    Date: {dated:%d %B %Y}", bold=True)
        doc.para(f"To: The Board of Directors, {c['legal_name']}, CR {c['cr_no']}, {c['city']}")
        doc.heading("Facility offer letter", 12)
        doc.para("We are pleased to offer the credit facilities below, subject to the terms and conditions of this letter "
                 "and the Bank's standard terms. This letter replaces any earlier offer for the same facilities.")
        rows = [["Facility", "Type", "Amount (SAR)", "Final maturity"]]
        fac_truth = []
        for kind, f in facs:
            if kind == "term":
                sched = sim.loan_schedule(f)
                rows.append([f["name"].split(" – ")[0], "Amortising term loan", f"{f['amount_sar_m'] * 1e6:,.0f}",
                             f"{sched[-1][0]:%d %b %Y}"])
                fac_truth.append({"facility": f["name"], "type": "term_loan", "amount_sar": f["amount_sar_m"] * 1e6,
                                  "drawn": f["drawn"], "margin_over_saibor": f["margin"],
                                  "schedule": [{"date": d.isoformat(), "principal_sar": S(a)} for d, a in sched]})
            else:
                rows.append(["Revolving credit facility", "Committed, revolving", f"{f['limit_sar_m'] * 1e6:,.0f}",
                             "31 Dec 2027"])
                fac_truth.append({"facility": "Revolving credit facility", "type": "rcf", "limit_sar": f["limit_sar_m"] * 1e6,
                                  "margin_over_saibor": f["margin"], "commitment_fee": f.get("commitment_fee", 0.002),
                                  "available_until": "2027-12-31"})
        doc.table(rows, [26, 22, 16, 15], aligns=["l", "l", "r", "r"])
        doc.heading("1. Pricing", 11)
        for kind, f in facs:
            if kind == "term":
                doc.para(f"{f['name'].split(' – ')[0]}: interest at three-month SAIBOR plus {f['margin'] * 100:.2f}% a year, "
                         "payable monthly in arrears.")
            else:
                doc.para(f"Revolving credit facility: interest at three-month SAIBOR plus {f['margin'] * 100:.2f}% a year on "
                         f"amounts drawn, and a commitment fee of {f.get('commitment_fee', 0.002) * 100:.2f}% a year on the "
                         "undrawn amount, payable monthly.")
        terms = [f for kind, f in facs if kind == "term"]
        for j, f in enumerate(terms, start=1):
            doc.heading(f"2.{j} Repayment – {f['name'].split(' – ')[0]}" if len(terms) > 1 else
                        f"2. Repayment – {f['name'].split(' – ')[0]}", 11)
            doc.para(f"Drawn in full on {date.fromisoformat(f['drawn']):%d %B %Y}. Repayable in {f['instalments']} "
                     f"{f['frequency']} instalments as follows:")
            bal = int(f["amount_sar_m"] * 1e8)
            rows = [["Instalment date", "Principal (SAR)", "Balance after (SAR)"]]
            for d, a in sim.loan_schedule(f):
                bal -= a
                rows.append([f"{d:%d %b %Y}", sar(a), sar(bal)])
            doc.table(rows, [18, 18, 20])
        doc.heading("3. Security", 11)
        doc.para("A corporate guarantee from Example Holding Company (made-up) for the full amount of the facilities, and an "
                 "assignment of the proceeds of the Borrower's receivables.")
        doc.heading("4. Financial covenants", 11)
        k = 1
        for cv in cov:
            if cv["test"] == "net_debt_to_ebitda_max":
                doc.para(f"4.{k} Leverage. The Borrower shall ensure that Net Debt on each Test Date does not exceed "
                         f"{cv['threshold']:.2f} times EBITDA for the Relevant Period ending on that Test Date.")
            elif cv["test"] == "dscr_min":
                doc.para(f"4.{k} Debt service. Cash Flow Available for Debt Service for each Relevant Period shall be at "
                         f"least {cv['threshold']:.2f} times Debt Service for that Relevant Period.")
            elif cv["test"] == "interest_cover_min":
                doc.para(f"4.{k} Interest cover. EBITDA for each Relevant Period shall be at least {cv['threshold']:.2f} "
                         "times Finance Costs for that Relevant Period.")
            else:
                doc.para(f"4.{k} Minimum liquidity. The aggregate of Cash and the undrawn amount of the Revolving Credit "
                         f"Facility shall not at any time be less than SAR {cv['threshold_sar']:,.0f}.")
            k += 1
        doc.heading("5. Definitions", 11)
        defs = ["\"EBITDA\" means, for any Relevant Period, the operating profit of the Borrower before interest, Zakat, "
                "depreciation and amortisation, excluding exceptional and non-recurring items"
                + (", and calculated as if IFRS 16 Leases had not been applied, so that rent paid under leases is deducted "
                   "as an operating expense." if pre16 else "."),
                "\"Net Debt\" means the aggregate of all borrowings of the Borrower" + (", excluding lease liabilities," if pre16 else
                                                                                      ", excluding lease liabilities,")
                + " less Cash.",
                "\"Cash\" means cash in hand and balances with banks in the Kingdom that are freely available.",
                "\"Debt Service\" means interest paid plus scheduled repayments of principal under all borrowings.",
                "\"Cash Flow Available for Debt Service\" means EBITDA less Zakat paid during the Relevant Period.",
                "\"Relevant Period\" means each period of twelve months ending on a Test Date.",
                "\"Test Date\" means 31 March, 30 June, 30 September and 31 December in each year."]
        doc.bullets(defs)
        doc.heading("6. Reporting", 11)
        doc.bullets(["Quarterly management accounts within 45 days of each quarter end, with a compliance certificate "
                     "signed by the Chief Financial Officer showing the covenant calculations.",
                     "Audited financial statements within 120 days of each financial year end."])
        doc.heading("7. Events of default", 11)
        doc.para("Non-payment, breach of a financial covenant not remedied within 30 days, cross-default above SAR 5,000,000, "
                 "insolvency, or a change of control of the Borrower without the Bank's consent.")
        doc.space(10)
        doc.para(f"For {lender}: Relationship Manager, Corporate Banking (signature on file)")
        doc.para(f"Accepted for {c['legal_name']}: Chief Financial Officer (signature on file)")
        fn = f"facility_letter_{n:02d}_{lender.split(' (')[0].replace(' ', '_').lower()}.pdf"
        doc.save(os.path.join(fdir, fn))
        truth.append({"file": fn, "lender": lender, "reference": ref, "dated": dated.isoformat(), "facilities": fac_truth,
                      "covenants": cov, "definitions": {"ebitda_before_ifrs16": pre16, "lease_liabilities_in_net_debt": False,
                                                        "cfads": "EBITDA less Zakat paid"}})
    with open(os.path.join(key_dir, "facilities.json"), "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=1)
    return truth


# ================================================================= people, stores, settings
def people(sim, up_dir):
    go = sim.go_live.isoformat()[:7]
    with open(os.path.join(up_dir, "payroll_gosi.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "department", "employees", "saudi", "non_saudi", "gross_salaries_sar", "gosi_wage_base_sar",
                    "gosi_employee_share_sar", "gosi_employer_share_sar"])
        for x in sim.payroll_log:
            if x["month"] >= go:
                w.writerow([x["month"], x["group"], x["heads"], x["saudi"], x["non_saudi"], f"{S(x['gross']):.2f}",
                            f"{S(x['gosi_base']):.2f}", f"{S(x['gosi_employee']):.2f}", f"{S(x['gosi_employer']):.2f}"])
    with open(os.path.join(up_dir, "headcount.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "department", "headcount", "saudi", "non_saudi", "saudisation_rate"])
        for x in sim.payroll_log:
            if x["month"] >= go:
                w.writerow([x["month"], x["group"], x["heads"], x["saudi"], x["non_saudi"], f"{x['saudi'] / x['heads']:.3f}"])


def stores(sim, up_dir):
    with open(os.path.join(up_dir, "stores.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["store", "location_id", "location_name", "city", "opened", "selling_area_m2"])
        for s in sim.stores:
            w.writerow([s["code"], s["loc"]["location_id"], s["loc"]["location_name"], s["loc"]["address"]["city"],
                        s["opened"].isoformat(), s["area"]])
    agg = defaultdict(lambda: [0, 0])
    code_of = {s["loc"]["location_id"]: s["code"] for s in sim.stores}
    for rc in sim.b.docs["salesreceipts"]:
        if rc["_date"] < sim.go_live:
            continue
        k = (rc["_date"].isoformat()[:7], code_of[rc["location_id"]])
        agg[k][0] += sum(li["quantity"] for li in rc["line_items"])
        agg[k][1] += int(round(rc["sub_total"] * 100))
    with open(os.path.join(up_dir, "pos_monthly.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "store", "transactions", "units_sold", "net_sales_sar"])
        for (ym, code), (units, net) in sorted(agg.items()):
            r = rng_for(sim.code, "ticket", code, ym)
            ticket = 172 * (1.12 if ym[5:] in ("11", "12") else 1.0) * r.lognormvariate(0, 0.05)
            w.writerow([ym, code, int(net / 100 / ticket), units, f"{S(net):.2f}"])


def settings(sim, up_dir):
    st7 = sim.story("S7")
    obj = {"company": sim.code, "legal_name": sim.c["legal_name"], "fiscal_year_end": "12-31", "vat_filing": "monthly",
           "zakat_payer": True, "approval_limit_sar": (st7 or {}).get("limit_sar", 100000),
           "approval_limit_note": "Delegation of authority: a single bill above this amount needs the CFO's approval.",
           "minimum_cash_policy_sar": sim.p["treasury"]["min_cash_sar_m"] * 1e6,
           "note": "Made-up example settings; stands in for the delegation-of-authority document."}
    with open(os.path.join(up_dir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)


def build_uploads(sim, kpi_rows, up_dir, key_dir):
    os.makedirs(up_dir, exist_ok=True)
    trial_balances(sim, up_dir, key_dir)
    bva = budgets(sim, up_dir, key_dir)
    fac = facilities(sim, kpi_rows, up_dir, key_dir)
    people(sim, up_dir)
    if sim.sector == "retail":
        stores(sim, up_dir)
    settings(sim, up_dir)
    return {"budget_vs_actual": bva, "facilities": fac}
