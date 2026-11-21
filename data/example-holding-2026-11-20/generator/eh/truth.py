"""The answer key: what the engine should find, computed from the generator's own ledger.

Nothing here is typed in. The true account mapping, the monthly statements by standard account and the
KPI values are all computed from the simulated books (which hold more than the Zoho files: the true class
of every counterparty, which part of a receivable is retention, the true holiday effects). Values that need
history from before go-live are left blank, because the engine cannot compute them either.
"""
import csv
import json
import os
from collections import defaultdict
from datetime import date, timedelta

from .calendar_ksa import in_eid_adha, in_eid_fitr, in_ramadan
from .chart import STD_NAMES
from .util import S, add_months, dim, month_end

PL_GROUPS = "ICXO"
DA = {"6600", "6610", "6700"}


def ym_list(a: date, b: date):
    out, (y, m) = [], (a.year, a.month)
    while (y, m) <= (b.year, b.month):
        out.append((y, m))
        y, m = add_months(y, m, 1)
    return out


def r4(x):
    return None if x is None else round(x, 4)


def build_truth(sim, out_dir):
    b, c = sim.b, sim.c
    os.makedirs(out_dir, exist_ok=True)
    sim._truth_dir = out_dir
    go, end = sim.go_live, sim.data_end
    chart = b.chart
    months_all = ym_list(sim.start, end)
    months = ym_list(go, end)
    closed = {ym for ym in months if sim.closed(*ym)}

    # ------------------------------------------------------------- the true mapping
    with open(os.path.join(out_dir, "chart_mapping.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "account_code", "account_name", "zoho_account_type", "standard_code", "standard_name", "role"])
        for key, a in chart.items():
            w.writerow([a.account_id, a.code, a.name, a.zoho_type, a.std, STD_NAMES.get(a.std, ""), a.role])

    # ------------------------------------------------------------- movements and balances by month
    mov = defaultdict(lambda: defaultdict(int))
    for ln in b.lines:
        mov[(ln[0].year, ln[0].month)][ln[1]] += ln[2]
    opening = defaultdict(int)
    for ln in b.lines:
        if ln[0] < sim.start:
            opening[ln[1]] += ln[2]
    bal_at = {}
    run = defaultdict(int, opening)
    for ym in months_all:
        for k, v in mov[ym].items():
            run[k] += v
        bal_at[ym] = dict(run)
    # remove the pre-start opening postings from the first month's movement (they are dated before start)

    def std_sum(d, codes):
        return sum(v for k, v in d.items() if chart[k].std in codes)

    def pl(ym, pred):
        return sum(v for k, v in mov[ym].items() if chart[k].group in PL_GROUPS and pred(chart[k].std))

    def bs(ym, keys):
        return sum(bal_at[ym].get(k, 0) for k in keys)

    # ------------------------------------------------------------- monthly statements by standard code
    stds = sorted({a.std for a in chart.values()})
    with open(os.path.join(out_dir, "monthly_statements.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "standard_code", "standard_name", "statement", "amount_sar", "status"])
        for ym in months:
            status = "closed" if ym in closed else "open (provisional)"
            for sc in stds:
                keys = [k for k, a in chart.items() if a.std == sc]
                grp = chart[keys[0]].group
                if grp in PL_GROUPS:
                    v = -sum(mov[ym].get(k, 0) for k in keys)
                    st = "income statement (credit positive)"
                else:
                    v = sum(bal_at[ym].get(k, 0) for k in keys)
                    if sc == "3300":
                        # retained earnings include the profit not yet closed into the account
                        v += sum(x for k2, x in bal_at[ym].items() if chart[k2].group in PL_GROUPS)
                    st = "balance sheet (debit positive)"
                w.writerow([f"{ym[0]}-{ym[1]:02d}", sc, STD_NAMES.get(sc, ""), st, f"{S(v):.2f}", status])

    # ------------------------------------------------------------- per-month building blocks
    rev = {ym: -pl(ym, lambda s: s == "4100") for ym in months_all}
    cogs = {ym: pl(ym, lambda s: s.startswith("5")) for ym in months_all}
    opex = {ym: pl(ym, lambda s: s.startswith("6") and s not in DA) for ym in months_all}
    oth = {ym: -pl(ym, lambda s: s == "4200") for ym in months_all}
    da = {ym: pl(ym, lambda s: s in DA) for ym in months_all}
    staff = {ym: pl(ym, lambda s: s in ("6100", "6110", "6120", "5200")) for ym in months_all}
    interest = {ym: pl(ym, lambda s: s in ("7200", "7210")) for ym in months_all}
    zakat = {ym: pl(ym, lambda s: s == "7600") for ym in months_all}
    net = {ym: -sum(v for k, v in mov[ym].items() if chart[k].group in PL_GROUPS) for ym in months_all}
    ebitda = {ym: rev[ym] - cogs[ym] - opex[ym] + oth[ym] for ym in months_all}
    ebit = {ym: ebitda[ym] - da[ym] for ym in months_all}
    capex = {ym: sum(v for k, v in mov[ym].items() if k == "ppe_cost" and v > 0) for ym in months_all}

    invoices = [i for i in b.docs["invoices"]]
    bills = [x for x in b.docs["bills"]]
    credit_sales = defaultdict(int)
    for i in invoices:
        if not i["_opening"]:
            credit_sales[(i["_date"].year, i["_date"].month)] += i["_total"]
    purchases = defaultdict(int)
    for x in bills:
        if not x["_opening"]:
            purchases[(x["_date"].year, x["_date"].month)] += x["_total_b"]

    def held_ret(inv, at):
        rel = sum(a for d, a in inv["_ret_hist"] if d <= at)
        return max(0, min(b.inv_open(inv, at), inv["_ret0"] - rel))

    def bill_held(bl, at):
        rel = sum(a for d, a in bl["_ret_hist"] if d <= at)
        return max(0, min(b.bill_open_fc(bl, at), bl["_ret0"] - rel))

    # ------------------------------------------------------------- cash flows by kind (direct method)
    by_tid = defaultdict(list)
    for ln in b.lines:
        by_tid[ln[4]].append(ln)
    bill_by_id = {x["bill_id"]: x for x in bills}
    key_of = {a.account_id: k for k, a in chart.items()}
    vp_by_id = {x["payment_id"]: x for x in b.docs["vendorpayments"]}
    cash_keys = {"bank1", "bank2", "cash"}
    flows = defaultdict(lambda: defaultdict(int))
    for tid, lns in by_tid.items():
        cash = sum(l[2] for l in lns if l[1] in cash_keys)
        if not cash or lns[0][0] < sim.start:
            continue
        ym = (lns[0][0].year, lns[0][0].month)
        others = {l[1] for l in lns if l[1] not in cash_keys}
        if not others:
            continue        # transfer between our own cash accounts
        tt = lns[0][3]
        if tt == "vendor_payment":
            vp = vp_by_id[tid]
            parts = defaultdict(float)
            for app in vp["bills"]:
                bl = bill_by_id[app["bill_id"]]
                tot = sum(li["item_total"] for li in bl["line_items"]) or 1
                for li in bl["line_items"]:
                    acc = key_of[li["account_id"]]
                    kind = "capex" if acc == "ppe_cost" else ("leases" if acc == "lease_liab" else "operating")
                    parts[kind] += li["item_total"] / tot * app["amount_applied"]
            ptot = sum(parts.values()) or 1
            for kind, v in parts.items():
                flows[ym][kind] += int(cash * v / ptot)
            continue
        if tt == "journal":
            if others & {"loan", "rcf"}:
                flows[ym]["debt"] += cash
            elif "dividends_payable" in others:
                flows[ym]["dividends"] += cash
            elif "interest" in others:
                flows[ym]["interest"] += cash
            elif "zakat_payable" in others:
                flows[ym]["zakat"] += cash
            else:
                flows[ym]["operating"] += cash
            continue
        flows[ym]["operating"] += cash

    # ------------------------------------------------------------- counterparties
    cls_of = {ct["contact_id"]: ct["_class"] for ct in b.docs["contacts"]}
    with open(os.path.join(out_dir, "counterparties.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["contact_id", "contact_name", "contact_type", "true_class", "segment", "story_tags", "currency"])
        for ct in b.docs["contacts"]:
            w.writerow([ct["contact_id"], ct["contact_name"], ct["contact_type"], ct["_class"], ct.get("_segment", ""),
                        " ".join(sorted(ct.get("_tags", ()))), ct["currency_code"]])

    # ------------------------------------------------------------- holiday index (the generator's own effect)
    def holiday_index(y, m):
        n = dim(y, m)
        if sim.sector == "retail":
            return sum(sim.holiday(date(y, m, k)) for k in range(1, n + 1)) / n
        if sim.sector == "distribution":
            cal = sim.p["calendar"]
            return sum(sim.day_factor(date(y, m, k)) / cal["month"][m - 1] for k in range(1, n + 1)) / n
        if sim.sector == "contracting":
            return sim.calendar_factor(y, m)
        return 1.0

    # ------------------------------------------------------------- the KPI table
    rows = []
    lim = sim.p.get("rcf", {}).get("limit_sar_m", 0) * 1e8
    first_ok = go

    def window(ym, n):
        out, (y, m) = [], ym
        for _ in range(n):
            out.append((y, m))
            y, m = add_months(y, m, -1)
        return out

    def in_export(ws):
        return all(date(y, m, 1) >= first_ok for y, m in ws)

    for ym in months:
        if ym not in closed:
            continue
        y, m = ym
        t = month_end(y, m)
        w12, w3 = window(ym, 12), window(ym, 3)
        ok12, ok3 = in_export(w12), in_export(w3)
        days3 = sum(dim(*x) for x in w3)
        row = {"month": f"{y}-{m:02d}"}
        R = lambda d, ws: sum(d[x] for x in ws)
        row["revenue"] = S(rev[ym])
        row["gross_margin_m"] = r4((rev[ym] - cogs[ym]) / rev[ym]) if rev[ym] else None
        row["ebitda"] = S(ebitda[ym])
        row["holiday_index_true"] = r4(holiday_index(y, m))
        if ok12:
            rv = R(rev, w12)
            row["revenue_ltm"] = S(rv)
            row["PF-1_gross_margin_ltm"] = r4((rv - R(cogs, w12)) / rv)
            row["HL-3_ebitda_margin_ltm"] = r4(R(ebitda, w12) / rv)
            row["PF-2_opex_ratio_ltm"] = r4(R(opex, w12) / rv)
            row["PF-3_net_margin_ltm"] = r4(R(net, w12) / rv)
            row["PF-4_staff_cost_ratio_ltm"] = r4(R(staff, w12) / rv)
            row["ebitda_ltm"] = S(R(ebitda, w12))
            row["FG-1_interest_cover_ltm"] = r4(R(ebit, w12) / R(interest, w12)) if R(interest, w12) else None
        yb = window(add_months(y, m, -12), 3)
        if ok3 and in_export(yb):
            row["HL-1_growth_raw_3m"] = r4(R(rev, w3) / R(rev, yb) - 1)
            adj_now = sum(rev[x] / holiday_index(*x) for x in w3)
            adj_then = sum(rev[x] / holiday_index(*x) for x in yb)
            row["HL-1_growth_holiday_adjusted_true_3m"] = r4(adj_now / adj_then - 1) if adj_then else None
        # receivables
        ar = bal_at[ym].get("ar", 0)
        cs3 = R(credit_sales, w3)
        not_due = held = past90_g = past90_p = 0
        for i in invoices:
            if i["_date"] > t:
                continue
            o = b.inv_open(i, t)
            if o <= 0:
                continue
            h = held_ret(i, t)
            held += h
            if i["_due"] >= t:
                not_due += o
            else:
                not_due += h
                if (t - i["_due"]).days > 90:
                    if cls_of.get(i["_cust"]["contact_id"]) == "government":
                        past90_g += o - h
                    else:
                        past90_p += o - h
        row["trade_receivables"] = S(ar)
        row["retention_receivable_held"] = S(held)
        if ok3 and cs3:
            row["RC-1_dso_3m"] = r4(ar / cs3 * days3)
            row["RC-1_best_dso_3m"] = r4(not_due / cs3 * days3)
            row["RC-1_days_late_3m"] = r4((ar - not_due) / cs3 * days3)
            row["RC-1_dso_excl_retention_3m"] = r4((ar - held) / cs3 * days3)
        if ar:
            row["RC-2_over90_share"] = r4((past90_g + past90_p) / ar)
            row["RC-2_over90_government_sar"] = S(past90_g)
            row["RC-2_over90_private_sar"] = S(past90_p)
        prev = add_months(y, m, -1)
        if date(*prev, 1) >= first_ok and credit_sales[ym]:
            ar0 = bal_at[prev].get("ar", 0)
            denom = ar0 + credit_sales[ym] - not_due
            row["RC-3_collection_effectiveness_m"] = r4((ar0 + credit_sales[ym] - ar) / denom * 100) if denom else None
        row["RC-4_booked_loss_allowance"] = S(-bal_at[ym].get("ecl_allow", 0))
        # inventory and payables
        inv_bal = bal_at[ym].get("inventory", 0)
        ap = -bal_at[ym].get("ap", 0)
        row["inventory"] = S(inv_bal)
        row["trade_payables"] = S(ap)
        if ok3:
            c3 = R(cogs, w3)
            p3 = R(purchases, w3)
            inv0 = bal_at[window(ym, 4)[-1]].get("inventory", 0)
            row["CS-3_inventory_days_3m"] = r4((inv0 + inv_bal) / 2 / c3 * days3) if c3 and (inv0 or inv_bal) else None
            row["PY-2_dpo_3m"] = r4(ap / p3 * days3) if p3 else None
            if row.get("RC-1_dso_3m") is not None and row.get("PY-2_dpo_3m") is not None:
                row["HL-6_cash_conversion_cycle"] = r4(row["RC-1_dso_3m"] + (row.get("CS-3_inventory_days_3m") or 0)
                                                       - row["PY-2_dpo_3m"])
        ov = op = 0
        for bl in bills:
            if bl["_date"] > t:
                continue
            o = b.bill_open_b(bl, t)
            if o <= 0:
                continue
            h = int(bill_held(bl, t) * bl["_rate"])
            op += o
            if bl["_due"] < t:
                ov += o - h
        row["PY-2_overdue_share"] = r4(ov / op) if op else None
        # cash, debt, liquidity
        cash = bs(ym, ["bank1", "bank2", "cash"])
        loan = -bal_at[ym].get("loan", 0)
        rcf = -bal_at[ym].get("rcf", 0)
        lease = -bal_at[ym].get("lease_liab", 0)
        row["cash"] = S(cash)
        row["borrowings"] = S(loan + rcf)
        row["rcf_drawn"] = S(rcf)
        row["rcf_undrawn"] = S(max(0, lim - rcf)) if lim else 0
        row["liquidity_cash_plus_undrawn"] = S(cash + max(0, lim - rcf))
        row["lease_liabilities"] = S(lease)
        row["net_debt_excl_leases"] = S(loan + rcf - cash)
        if ok12:
            e12 = R(ebitda, w12)
            row["HL-8_net_debt_to_ebitda_excl_leases"] = r4((loan + rcf - cash) / e12) if e12 else None
            row["HL-8_net_debt_to_ebitda_incl_leases"] = r4((loan + rcf + lease - cash) / e12) if e12 else None
            fl = {k: sum(flows[x][k] for x in w12) for k in ("operating", "zakat", "interest", "capex", "leases", "debt", "dividends")}
            row["cash_from_operations_pre_interest_zakat_ltm"] = S(fl["operating"])
            row["HL-5_cash_conversion_ltm"] = r4(fl["operating"] / e12) if e12 else None
            row["CS-1_free_cash_flow_ltm"] = S(fl["operating"] + fl["zakat"] + fl["interest"] + fl["capex"] + fl["leases"])
            row["capex_paid_ltm"] = S(-fl["capex"])
            row["lease_payments_ltm"] = S(-fl["leases"])
            row["zakat_paid_ltm"] = S(-fl["zakat"])
            row["interest_paid_ltm"] = S(-fl["interest"])
            row["dividends_paid_ltm"] = S(-fl["dividends"])
            d12 = R(da, w12)
            row["CS-2_capex_to_depreciation_ltm"] = r4(R(capex, w12) / d12) if d12 else None
            # invested capital and returns
            eq = lambda x: -(bs(x, ["share_capital", "stat_reserve", "retained"])
                             + sum(v for k, v in bal_at[x].items() if chart[k].group in PL_GROUPS))
            ic = lambda x: eq(x) - bs(x, ["loan", "rcf", "lease_liab"]) - bs(x, ["bank1", "bank2", "cash"])
            pts = [ic(x) for x in window(ym, 13)]
            avg_ic = sum(pts) / len(pts)
            nopat = R(ebit, w12) - R(zakat, w12)
            row["HL-4_roic_ltm"] = r4(nopat / avg_ic) if avg_ic > 0 else None
            row["invested_capital_avg"] = S(avg_ic)
            ta = sum(v for k, v in bal_at[ym].items() if chart[k].group == "A")
            tl = -sum(v for k, v in bal_at[ym].items() if chart[k].group == "L")
            ca = sum(v for k, v in bal_at[ym].items() if chart[k].group == "A" and chart[k].std < "1200")
            cl = -sum(v for k, v in bal_at[ym].items() if chart[k].group == "L" and chart[k].std < "2200")
            cur_loan = sum(p for ln in sim.loans for dd, p in sim.loan_schedule(ln) if t < dd <= t + timedelta(days=365))
            cl += cur_loan
            re_ = eq(ym) + bs(ym, ["share_capital"])
            row["FG-2_current_ratio"] = r4(ca / cl) if cl else None
            row["FG-2_quick_ratio"] = r4((ca - inv_bal) / cl) if cl else None
            row["FG-3_altman_z2"] = r4(6.56 * (ca - cl) / ta + 3.26 * (re_ - 0) / ta + 6.72 * R(ebit, w12) / ta
                                       + 1.05 * eq(ym) / tl) if ta and tl else None
            ta0 = sum(v for k, v in bal_at[window(ym, 13)[-1]].items() if chart[k].group == "A")
            cfo = fl["operating"] + fl["zakat"]
            row["FG-4_accruals_ratio_ltm"] = r4((R(net, w12) - cfo) / ((ta + ta0) / 2)) if ta else None
            wc = ar + bs(ym, ["contract_assets"]) + inv_bal - ap
            row["CS-4_working_capital_to_revenue"] = r4(wc / R(rev, w12)) if R(rev, w12) else None
        rows.append(row)

    # customer concentration (RC-5) on the last 12 months' invoiced revenue, net of credit notes
    by_cm = defaultdict(lambda: defaultdict(int))
    for i in invoices:
        if not i["_opening"] and i["_cust"]["_class"] != "retail":
            by_cm[(i["_date"].year, i["_date"].month)][i["_cust"]["contact_id"]] += int(round(i["sub_total"] * 100))
    for cn in b.docs["creditnotes"]:
        by_cm[(cn["_date"].year, cn["_date"].month)][cn["customer_id"]] -= int(round(cn["sub_total"] * 100))
    for row in rows:
        y, m = int(row["month"][:4]), int(row["month"][5:7])
        ws = window((y, m), 12)
        if not in_export(ws):
            continue
        tot = defaultdict(int)
        for x in ws:
            for k, v in by_cm[x].items():
                tot[k] += v
        T = sum(v for v in tot.values() if v > 0)
        if T <= 0:
            continue
        sh = sorted((v / T for v in tot.values() if v > 0), reverse=True)
        hhi = sum(x * x for x in sh)
        row["RC-5_top_customer_share_ltm"] = r4(sh[0])
        row["RC-5_top5_share_ltm"] = r4(sum(sh[:5]))
        row["RC-5_effective_number_of_customers_ltm"] = r4(1 / hhi)
    # intercompany balances at each month end, by group company
    with open(os.path.join(out_dir, "intercompany_open.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "counterparty_company", "receivable_open_sar", "payable_open_sar"])
        ics = [c for c in b.docs["contacts"] if c["_class"] == "intercompany"]
        for ym in months:
            t = min(month_end(*ym), end)
            for c in ics:
                rec = sum(b.inv_open(i, t) for i in invoices if i["_cust"] is c and i["_date"] <= t)
                pay = sum(b.bill_open_b(x, t) for x in bills if x["_vendor"] is c and x["_date"] <= t)
                w.writerow([f"{ym[0]}-{ym[1]:02d}", c["_group_company"], f"{S(rec):.2f}", f"{S(pay):.2f}"])
    # sector KPIs
    sector_rows = sim_sector_truth(sim, rows, rev, cogs, bal_at, closed, months, credit_sales, purchases, mov)
    cols = []
    for rw in rows:
        for k in rw:
            if k not in cols:
                cols.append(k)
    with open(os.path.join(out_dir, "kpis_monthly.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for rw in rows:
            w.writerow(rw)
    with open(os.path.join(out_dir, "payroll_register.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "group", "heads", "saudi", "non_saudi", "gross_sar", "gosi_base_sar", "gosi_employee_sar",
                    "gosi_employer_sar"])
        for x in sim.payroll_log:
            if x["month"] >= go.isoformat()[:7]:
                w.writerow([x["month"], x["group"], x["heads"], x["saudi"], x["non_saudi"], f"{S(x['gross']):.2f}",
                            f"{S(x['gosi_base']):.2f}", f"{S(x['gosi_employee']):.2f}", f"{S(x['gosi_employer']):.2f}"])
    with open(os.path.join(out_dir, "close_calendar.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "close_date", "days_to_close"])
        for x in sim.close_log:
            if x["month"] >= go.isoformat()[:7]:
                w.writerow([x["month"], x["close_date"], x["lag_days"]])
    return rows


def sim_sector_truth(sim, rows, rev, cogs, bal_at, closed, months, credit_sales, purchases, mov):
    b = sim.b
    by_month = {r["month"]: r for r in rows}
    if sim.sector == "contracting":
        bl = {x["month"]: x for x in sim.truth["backlog"]}
        awards = defaultdict(int)
        for a in sim.truth["awards"]:
            awards[a["award"][:7]] += a["value"]
        for r in rows:
            x = bl.get(r["month"])
            if not x:
                continue
            y, m = int(r["month"][:4]), int(r["month"][5:7])
            w3 = [(y, m), add_months(y, m, -1), add_months(y, m, -2)]
            rv3 = sum(rev[k] for k in w3) / 3
            r["CON-1_months_of_backlog"] = r4(x["backlog"] / rv3) if rv3 else None
            r["backlog"] = S(x["backlog"])
            r["PD-3_unbilled_days_3m"] = r4(x["unbilled"] / (rv3 * 3) * sum(dim(*k) for k in w3)) if rv3 else None
            new = sum(awards.get(f"{a}-{b_:02d}", 0) for a, b_ in w3)
            r["PD-2_book_to_bill_3m"] = r4(new / (rv3 * 3)) if rv3 else None
            projs = x["projects"]
            wsum = sum(p["value"] for p in projs) or 1
            r["CON-4_margin_fade_weighted"] = r4(sum((p["margin_estimate"] - p["margin_bid"]) * p["value"] for p in projs) / wsum)
        out = os.path.join(sim._truth_dir, "projects_monthly.csv")
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["month", "project", "contract_value", "work_to_date", "billed_net_to_date", "progress",
                        "margin_at_bid", "margin_estimate_at_completion"])
            for x in sim.truth["backlog"]:
                if x["month"] < sim.go_live.isoformat()[:7]:
                    continue
                for p in x["projects"]:
                    w.writerow([x["month"], p["project"], f"{S(p['value']):.2f}", f"{S(p['work_to_date']):.2f}",
                                f"{S(p['billed_net']):.2f}", p["progress"], p["margin_bid"], p["margin_estimate"]])
    if sim.sector == "distribution":
        st = {x["month"]: x for x in sim.truth["stock"]}
        list_val, net_val = defaultdict(int), defaultdict(int)
        for i in b.docs["invoices"]:
            k = i["_date"].isoformat()[:7]
            for li in i["line_items"]:
                list_val[k] += int(round(li["quantity"] * li["rate"] * 100))
                net_val[k] += int(round(li["item_total"] * 100))
        # purchases of stock (net of VAT, at the bill's rate); customs, overhead and capital bills excluded
        eur = defaultdict(int)
        allp = defaultdict(int)
        inv_id = b.acct("inventory").account_id
        for x in b.docs["bills"]:
            if x["_opening"] or x["_vendor"] is getattr(sim, "clearing", None):
                continue
            goods = sum(li["item_total"] for li in x["line_items"] if li["account_id"] == inv_id)
            if not goods:
                continue
            k = x["_date"].isoformat()[:7]
            v = int(round(goods * 100 * x["_rate"]))
            allp[k] += v
            if x["currency_code"] not in ("SAR", "USD"):
                eur[k] += v
        for r in rows:
            x = st.get(r["month"])
            if x:
                r["TRD-3_stock_older_than_180_days_share"] = r4(x["older_than_180_days"] / x["layers_value"]) if x["layers_value"] else None
            if list_val.get(r["month"]):
                r["TRD-5_price_realisation_m"] = r4(net_val[r["month"]] / list_val[r["month"]])
            if allp.get(r["month"]):
                r["TRD-6_purchases_outside_dollar_m"] = r4(eur[r["month"]] / allp[r["month"]])
            if r.get("revenue_ltm"):
                y, m = int(r["month"][:4]), int(r["month"][5:7])
                w12 = [add_months(y, m, -i) for i in range(12)]
                avg_inv = sum(bal_at[k].get("inventory", 0) for k in w12) / 12
                gm = sum(rev[k] - cogs[k] for k in w12)
                r["TRD-1_gmroi_ltm"] = r4(gm / avg_inv) if avg_inv else None
                r["TRD-2_stock_turns_ltm"] = r4(sum(cogs[k] for k in w12) / avg_inv) if avg_inv else None
        # price indices for the S2 story: purchase and selling prices per item, month by month
        out = os.path.join(sim._truth_dir, "item_prices_monthly.csv")
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["month", "item_id", "item_name", "family", "purchase_currency", "s2_affected",
                        "purchase_price_fc", "list_price_sar"])
            for (y, m) in months:
                d = date(y, m, 15)
                for it in sim.items:
                    w.writerow([f"{y}-{m:02d}", it["item_id"], it["name"], it["_family"], it["_cur"], int(it["_s2"]),
                                f"{sim.purchase_price_fc(it, d) / 100:.2f}", f"{sim.list_price(it, d) / 100:.2f}"])
    if sim.sector == "retail":
        sales = defaultdict(int)
        for d, code, tot in sim.truth["store_days"]:
            sales[(code, d.year, d.month)] += tot
        opened = {s["code"]: s["opened"] for s in sim.stores}
        area = {s["code"]: s["area"] for s in sim.stores}
        for r in rows:
            y, m = int(r["month"][:4]), int(r["month"][5:7])
            if date(y - 1, m, 1) < sim.go_live:
                continue
            both = [k for k, o in opened.items() if o < date(y - 1, m, 1)]
            a = sum(sales[(k, y, m)] for k in both)
            bb = sum(sales[(k, y - 1, m)] for k in both)
            if bb:
                hi_now = sum(sim.holiday(date(y, m, k)) for k in range(1, dim(y, m) + 1)) / dim(y, m)
                hi_then = sum(sim.holiday(date(y - 1, m, k)) for k in range(1, dim(y - 1, m) + 1)) / dim(y - 1, m)
                r["RET-1_like_for_like_raw_m"] = r4(a / bb - 1)
                r["RET-1_like_for_like_holiday_adjusted_true_m"] = r4((a / hi_now) / (bb / hi_then) - 1)
            tot = sum(sales[(k, y, m)] for k in opened)
            ar_ = sum(area[k] for k, o in opened.items() if o <= month_end(y, m))
            r["RET-2_sales_per_m2_annualised"] = round(S(tot) / 1.15 * 12 / ar_, 2) if ar_ else None
        out = os.path.join(sim._truth_dir, "stores.csv")
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["store", "location_id", "location_name", "city", "opened", "area_m2", "story_weak_new_store",
                        "annual_rent_sar", "fit_out_capex_sar"])
            for s in sim.stores:
                w.writerow([s["code"], s["loc"]["location_id"], s["loc"]["location_name"], s["loc"]["address"]["city"],
                            s["opened"].isoformat(), s["area"], int(s["weak"]), f"{S(s['rent']):.2f}",
                            f"{S(s['fitout']):.2f}" if s["opened"] >= sim.start else ""])
        out = os.path.join(sim._truth_dir, "store_sales_monthly.csv")
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["month", "store", "sales_incl_vat_sar"])
            for (code, y, m), v in sorted(sales.items(), key=lambda x: (x[0][1], x[0][2], x[0][0])):
                if date(y, m, 1) >= sim.go_live:
                    w.writerow([f"{y}-{m:02d}", code, f"{S(v):.2f}"])
    return rows
