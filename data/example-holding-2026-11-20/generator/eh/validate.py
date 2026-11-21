"""Checks run on every generated company: the books themselves, the exported files read back from disk,
and the planted stories. Every check reports PASS or FAIL with the figures behind it.
"""
import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

from .util import S, add_months, dim, month_end


def _ym_list(a, b):
    out, (y, m) = [], (a.year, a.month)
    while (y, m) <= (b.year, b.month):
        out.append((y, m))
        y, m = add_months(y, m, 1)
    return out


def load_list(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    for k, v in obj.items():
        if isinstance(v, list):
            return v
    return []


def validate_company(sim, zoho_dir, truth_rows):
    b = sim.b
    go, end = sim.go_live, sim.data_end
    res = []

    def check(name, ok, detail):
        res.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    lines = sorted(b.lines, key=lambda l: l[0])
    months = _ym_list(go, end)
    # ------------------------------------------------------------ the books
    bal = defaultdict(int)
    i = 0
    worst_tb = 0
    month_bal = {}
    for (y, m) in _ym_list(sim.start - timedelta(days=1), end):
        cut = min(month_end(y, m), end)
        while i < len(lines) and lines[i][0] <= cut:
            bal[lines[i][1]] += lines[i][2]
            i += 1
        worst_tb = max(worst_tb, abs(sum(bal.values())))
        month_bal[(y, m)] = dict(bal)
    check("Trial balance balances at every month end", worst_tb == 0, f"largest imbalance SAR {S(worst_tb):,.2f}")

    worst_ar = worst_ap = 0
    for (y, m) in months:
        t = min(month_end(y, m), end)
        ar = sum(b.inv_open(x, t) for x in b.docs["invoices"] if x["_date"] <= t)
        ap = sum(b.bill_open_b(x, t) for x in b.docs["bills"] if x["_date"] <= t)
        worst_ar = max(worst_ar, abs(ar - month_bal[(y, m)].get("ar", 0)))
        worst_ap = max(worst_ap, abs(ap + month_bal[(y, m)].get("ap", 0)))
    check("Receivables control account equals open invoices, every month", worst_ar == 0,
          f"largest difference SAR {S(worst_ar):,.2f}")
    check("Payables control account equals open bills, every month", worst_ap == 0,
          f"largest difference SAR {S(worst_ap):,.2f}")

    worst_vat = 0
    for (y, m) in months:
        if sim.closed(y, m):
            worst_vat = max(worst_vat, abs(month_bal[(y, m)].get("vat_out", 0)), abs(month_bal[(y, m)].get("vat_in", 0)))
    check("VAT input and output accounts are cleared to VAT payable at every close", worst_vat == 0,
          f"largest residue SAR {S(worst_vat):,.2f}")

    run = defaultdict(int)
    lows = {"bank1": (0, None), "bank2": (0, None), "cash": (0, None)}
    j = 0
    while j < len(lines):
        d = lines[j][0]
        while j < len(lines) and lines[j][0] == d:
            run[lines[j][1]] += lines[j][2]
            j += 1
        for k in lows:
            if run[k] < lows[k][0]:
                lows[k] = (run[k], d)
    neg = {k: v for k, v in lows.items() if v[0] < 0}
    check("No bank or cash account is overdrawn at the end of any day", not neg,
          "; ".join(f"{k} lowest SAR {S(v[0]):,.2f} on {v[1]}" for k, v in neg.items()) or "lowest end-of-day balances all ≥ 0")

    neg_inv = [ym for ym, bb in month_bal.items() if bb.get("inventory", 0) < 0]
    check("Inventory is never negative at a month end", not neg_inv, f"months below zero: {neg_inv[:5]}" if neg_inv else "all ≥ 0")
    if sim.sector == "distribution":
        layers = sum(v for it in sim.items for _, _, v in it["_layers"])
        check("Stock ledger equals the sum of the stock layers (first in, first out)", layers == b.bal["inventory"],
              f"ledger SAR {S(b.bal['inventory']):,.2f}, layers SAR {S(layers):,.2f}")

    bad_pay = 0
    inv_by = {x["invoice_id"]: x for x in b.docs["invoices"]}
    bill_by = {x["bill_id"]: x for x in b.docs["bills"]}
    for p in b.docs["customerpayments"]:
        for app in p["invoices"]:
            if inv_by[app["invoice_id"]]["_date"] > p["_date"]:
                bad_pay += 1
    for p in b.docs["vendorpayments"]:
        for app in p["bills"]:
            if bill_by[app["bill_id"]]["_date"] > p["_date"]:
                bad_pay += 1
    check("No payment is dated before the invoice or bill it settles", bad_pay == 0, f"{bad_pay} payments out of order")

    # ------------------------------------------------------------ the exported files
    ok_parse, docs = True, {}
    for fn in sorted(os.listdir(zoho_dir)):
        if fn.endswith(".json") and fn != "manifest.json":
            try:
                with open(os.path.join(zoho_dir, fn), encoding="utf-8") as f:
                    docs[fn[:-5]] = json.load(f)
            except Exception as e:  # noqa
                ok_parse = False
    check("Every exported JSON file parses", ok_parse, f"{len(docs)} files read back")

    def recs(name):
        o = docs.get(name)
        if not o:
            return []
        for k, v in o.items():
            if isinstance(v, list):
                return v
        return []

    # document arithmetic
    bad_math = 0
    for name in ("invoices", "bills", "salesreceipts", "creditnotes"):
        for d in recs(name):
            sub = round(sum(li["item_total"] for li in d["line_items"]), 2)
            tax = round(sum(round(li["item_total"] * li.get("tax_percentage", 0) / 100, 2) for li in d["line_items"]), 2)
            if abs(sub - d["sub_total"]) > 0.011 * len(d["line_items"]) or abs(round(d["sub_total"] + d["tax_total"], 2) - d["total"]) > 0.011 \
                    or abs(tax - d["tax_total"]) > 0.011 * len(d["line_items"]):
                bad_math += 1
    check("Line items, VAT and totals add up on every invoice, bill, receipt and credit note", bad_math == 0,
          f"{bad_math} documents off by more than rounding")

    # references
    inv_ids = {d["invoice_id"] for d in recs("invoices")}
    bill_ids = {d["bill_id"] for d in recs("bills")}
    contact_ids = {d["contact_id"] for d in recs("contacts")}
    acct_ids = {d["account_id"] for d in recs("chartofaccounts")}
    missing = 0
    for p in recs("customerpayments"):
        missing += sum(1 for a in p["invoices"] if a["invoice_id"] not in inv_ids)
    for p in recs("vendorpayments"):
        missing += sum(1 for a in p["bills"] if a["bill_id"] not in bill_ids)
    for cn in recs("creditnotes"):
        missing += sum(1 for a in cn["invoices_credited"] if a["invoice_id"] not in inv_ids)
    for d in recs("invoices"):
        missing += d["customer_id"] not in contact_ids
        missing += sum(1 for li in d["line_items"] if li["account_id"] not in acct_ids)
    for d in recs("bills"):
        missing += d["vendor_id"] not in contact_ids
        missing += sum(1 for li in d["line_items"] if li["account_id"] not in acct_ids)
    for jn in recs("journals"):
        missing += sum(1 for li in jn["line_items"] if li["account_id"] not in acct_ids)
    check("Every payment, credit note, contact and account reference resolves to an exported record", missing == 0,
          f"{missing} unresolved references")

    ids = []
    for name, key in (("invoices", "invoice_id"), ("bills", "bill_id"), ("customerpayments", "payment_id"),
                      ("vendorpayments", "payment_id"), ("journals", "journal_id"), ("expenses", "expense_id"),
                      ("salesreceipts", "sales_receipt_id"), ("creditnotes", "creditnote_id"), ("contacts", "contact_id")):
        ids += [d[key] for d in recs(name)]
    check("Record IDs are unique", len(ids) == len(set(ids)), f"{len(ids)} IDs, {len(ids) - len(set(ids))} duplicates")

    # the general ledger file replays to the books
    gl = defaultdict(int)
    by_tx = defaultdict(int)
    gl_month = defaultdict(lambda: defaultdict(int))
    deb = cre = 0
    with open(os.path.join(zoho_dir, "account_transactions.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dv = int(round(float(row["debit"]) * 100))
            cv = int(round(float(row["credit"]) * 100))
            deb += dv
            cre += cv
            gl[row["account_id"]] += dv - cv
            by_tx[row["transaction_id"]] += dv - cv
            gl_month[row["date"][:7]][row["account_id"]] += dv - cv
    check("General ledger file: debits equal credits, and every transaction balances",
          deb == cre and not [k for k, v in by_tx.items() if v],
          f"debits SAR {S(deb):,.2f}, credits SAR {S(cre):,.2f}, unbalanced transactions {len([k for k, v in by_tx.items() if v])}")
    key_by_id = {a.account_id: k for k, a in b.chart.items()}
    worst = 0
    cum = defaultdict(int)
    pl_keys = {k for k, a in b.chart.items() if a.group in "ICXO"}
    for (y, m) in months:
        ym = f"{y}-{m:02d}"
        for aid, v in gl_month[ym].items():
            cum[aid] += v
        internal = month_bal[(y, m)]
        pre = month_bal[add_months(go.year, go.month, -1)]
        for aid, k in key_by_id.items():
            want = internal.get(k, 0)
            if k in pl_keys:
                want -= pre.get(k, 0)
            if k == "retained":
                want += sum(pre.get(x, 0) for x in pl_keys)
            worst = max(worst, abs(cum[aid] - want))
    check("Opening balances plus the general ledger file reproduce every account at every month end", worst == 0,
          f"largest difference SAR {S(worst):,.2f}")

    # opening receivables and payables equal the migrated documents
    ob = {a["account_id"]: (a["amount"] if a["debit_or_credit"] == "debit" else -a["amount"])
          for a in docs["openingbalances"]["opening_balance"]["accounts"]}
    mig = round(sum(next((cf["value"] for cf in d.get("custom_fields", []) if cf.get("api_name") == "cf_balance_at_go_live"), 0)
                    for d in recs("invoices")), 2)
    ar_ob = ob.get(b.acct("ar").account_id, 0)
    check("Opening receivables equal the go-live balances of the migrated invoices", abs(mig - ar_ob) < 0.01,
          f"opening SAR {ar_ob:,.2f}, migrated invoices SAR {mig:,.2f}")

    # bank statement lines match the bank accounts in the ledger
    bt = defaultdict(int)
    for x in recs("banktransactions"):
        if x["status"] == "categorized":
            bt[x["account_id"]] += int(round(x["amount"] * 100)) * (1 if x["debit_or_credit"] == "debit" else -1)
    worst_b = 0
    for key in ("bank1", "bank2"):
        aid = b.acct(key).account_id
        worst_b = max(worst_b, abs(bt[aid] - (gl[aid] - int(round(ob.get(aid, 0) * 100)))))
    unrec = [x for x in recs("banktransactions") if x["status"] == "uncategorized"]
    check("Categorised bank lines equal the bank accounts' movements in the ledger", worst_b == 0,
          f"largest difference SAR {S(worst_b):,.2f}; {len(unrec)} statement lines left uncategorised on purpose")

    late = 0
    for name, dk in (("invoices", "date"), ("bills", "date"), ("journals", "journal_date"), ("customerpayments", "date")):
        for d in recs(name):
            if d[dk] > end.isoformat():
                late += 1
    check("No document is dated after the data end", late == 0, f"{late} documents after {end}")

    res += story_checks(sim, truth_rows)
    return res


def story_checks(sim, rows):
    out = []
    by = {r["month"]: r for r in rows}

    def check(name, ok, detail):
        out.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    def g(month, key):
        r = by.get(month) or {}
        return r.get(key)

    def avg(year, key):
        v = [g(f"{year}-{m:02d}", key) for m in range(1, 11)]
        v = [x for x in v if x is not None]
        return sum(v) / len(v) if v else None

    if "S9" in sim.stories and "S1" not in sim.stories:
        a, b_ = avg(2025, "RC-1_days_late_3m"), avg(2026, "RC-1_days_late_3m")
        check("S9: days late higher in January–October 2026 than a year earlier", a is not None and b_ is not None and b_ > a,
              f"average days late (3-month basis) 2025 {a:.1f}, 2026 {b_:.1f}, change {b_ - a:+.1f}")
    if "S7" in sim.stories:
        st = sim.s7
        lim = st["st"]["limit_sar"] * 100

        def ratio(lo_d, hi_d):
            below = sum(1 for b in sim.b.docs["bills"] if lim * 0.9 <= b["_total_b"] < lim and lo_d <= b["_date"] < hi_d)
            above = sum(1 for b in sim.b.docs["bills"] if lim <= b["_total_b"] < lim * 1.1 and lo_d <= b["_date"] < hi_d)
            return below, above
        b0, a0 = ratio(sim.go_live, st["start"])
        b1, a1 = ratio(st["start"], sim.data_end + timedelta(days=1))
        r0, r1 = b0 / max(1, a0), b1 / max(1, a1)
        check("S7: bills bunch just below the SAR 50,000 approval limit after June 2025", r1 > 2 * r0,
              f"bills SAR 45,000–50,000 for each bill SAR 50,000–55,000: {r0:.1f} before ({b0} vs {a0}), "
              f"{r1:.1f} after ({b1} vs {a1})")
        closes = {x["month"]: x["close_date"] for x in sim.close_log}
        late = 0
        for j in sim.b.docs["journals"]:
            jd = j["_date"]
            ct = j["created_time"][:10]
            cd = closes.get(f"{jd.year}-{jd.month:02d}")
            if cd and ct > cd and (date.fromisoformat(ct) - jd).days >= 30:
                late += 1
        check("S7: about 40 journals entered 30 or more days after their date, into months already closed", late >= 40,
              f"{late} such journals")
        fri = sum(1 for j in sim.b.docs["journals"] if j.get("created_by_name") == sim.b.user_for("adhoc")["name"]
                  and date.fromisoformat(j["created_time"][:10]).weekday() == 4)
        check("S7: Friday postings by a rarely-posting user", fri >= 20, f"{fri} journals entered on Fridays by "
              f"{sim.b.user_for('adhoc')['name']} ({sim.b.user_for('adhoc')['role_name']})")
    if "S8" in sim.stories:
        a, b_ = g("2025-06", "RC-5_top_customer_share_ltm"), g("2026-10", "RC-5_top_customer_share_ltm")
        check("S8: the new customer grows from under a fifth to about half of revenue (last 12 months)",
              a is not None and b_ is not None and 0.1 <= a <= 0.25 and b_ >= 0.4,
              f"top customer share Jun 2025 {a}, Oct 2026 {b_}; effective number of customers "
              f"{g('2025-06', 'RC-5_effective_number_of_customers_ltm')} → {g('2026-10', 'RC-5_effective_number_of_customers_ltm')}")
    if "S13" in sim.stories:
        mi = [l for l in sim.b.lines if l[1] == "misc_income" and l[0] >= sim.go_live]
        months_hit = len({(l[0].year, l[0].month) for l in mi})
        tot = -sum(l[2] for l in mi)
        rev = sum(r_["revenue"] for r_ in rows if r_["month"] >= sim.go_live.isoformat()[:7]) * 100
        check("S13: \"Miscellaneous income\" receives service revenue every month (true standard account: revenue)",
              months_hit >= 44 and sim.b.chart["misc_income"].std == "4100",
              f"booked in {months_hit} months, SAR {S(tot) / 1e6:.1f}m since go-live, {tot / rev * 100:.1f}% of revenue")
    if "S1" in sim.stories:
        a, b_ = avg(2025, "RC-1_days_late_3m"), avg(2026, "RC-1_days_late_3m")
        check("S1/S9: days late higher in January–October 2026 than a year earlier (by 8 days or more)",
              a is not None and b_ is not None and b_ - a >= 8,
              f"average days late (3-month basis) 2025 {a:.1f}, 2026 {b_:.1f}, change {b_ - a:+.1f}")
        a, b_ = g("2025-10", "RC-1_dso_3m"), g("2026-10", "RC-1_dso_3m")
        check("S1/S9: DSO higher in October 2026 than a year earlier", a is not None and b_ is not None and b_ > a,
              f"DSO Oct 2025 {a}, Oct 2026 {b_}")
        a, b_ = g("2025-10", "liquidity_cash_plus_undrawn"), g("2026-10", "liquidity_cash_plus_undrawn")
        check("S1/S9: liquidity (cash plus undrawn facility) lower than a year earlier", a is not None and b_ is not None and b_ < a,
              f"SAR m: Oct 2025 {a / 1e6 if a else a:.1f}, Oct 2026 {b_ / 1e6 if b_ else b_:.1f}")
        a, b_ = g("2025-10", "HL-5_cash_conversion_ltm"), g("2026-10", "HL-5_cash_conversion_ltm")
        check("S1/S9: cash conversion (LTM) lower than a year earlier", a is not None and b_ is not None and b_ < a,
              f"Oct 2025 {a}, Oct 2026 {b_}")
    if "S2" in sim.stories:
        a, b_ = g("2025-09", "PF-1_gross_margin_ltm"), g("2026-10", "PF-1_gross_margin_ltm")
        check("S2: gross margin (LTM) falls after the October 2025 price change", a is not None and b_ is not None and a - b_ >= 0.006,
              f"Sep 2025 {a}, Oct 2026 {b_}")
        eur = [r.get("TRD-6_purchases_outside_dollar_m") for r in rows if r.get("TRD-6_purchases_outside_dollar_m") is not None]
        avg = sum(eur) / len(eur) if eur else None
        check("S2: about 23% of stock purchases are in euros", avg is not None and 0.19 <= avg <= 0.27,
              f"average monthly share {avg:.3f} (range {min(eur):.2f}–{max(eur):.2f})" if avg else "n/a")
        rise = [it for it in sim.items if it["_s2"]]
        check("S2: 60% of items carry the purchase-price rise", abs(len(rise) / len(sim.items) - 0.6) < 0.02,
              f"{len(rise)} of {len(sim.items)} items")
    if "S4" in sim.stories:
        import collections
        m = collections.defaultdict(int)
        for d, code, tot in sim.truth["store_days"]:
            m[(d.year, d.month)] += tot
        ch = m[(2026, 3)] / m[(2025, 3)] - 1
        check("S4: March 2026 sales about 11% below March 2025 (calendar only)", -0.14 <= ch <= -0.08, f"change {ch * 100:+.1f}%")
        a = g("2026-03", "RET-1_like_for_like_holiday_adjusted_true_m")
        check("S4: like-for-like growth is positive once the holiday effect is removed", a is not None and a > 0,
              f"March 2026 holiday-adjusted like-for-like {a}; raw {g('2026-03', 'RET-1_like_for_like_raw_m')}")
        a, b_ = g("2024-12", "HL-4_roic_ltm"), g("2026-10", "HL-4_roic_ltm")
        check("S4: return on invested capital falls with the nine new stores", a is not None and b_ is not None and b_ < a,
              f"ROIC (LTM, after Zakat) Dec 2024 {a}, Oct 2026 {b_}")
    return out
