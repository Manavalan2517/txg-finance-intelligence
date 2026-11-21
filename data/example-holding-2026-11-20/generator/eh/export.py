"""Write one company's books as files in Zoho Books' API format.

Records follow the field names of Zoho Books' API documentation (each list file is wrapped the way a list
call returns it, for example {"invoices": [...]}); fields we could not confirm against a live organisation
are listed in the README as VERIFY. Every record is written on its own line so the files stream and diff
well. Internal simulation fields (names starting with "_") never leave the generator.

What is exported:
- documents dated on or after the go-live date, plus earlier invoices and bills still open at go-live
  (migrated with their balance at go-live in the custom field cf_balance_at_go_live);
- the opening balances of every balance-sheet account at go-live;
- account_transactions.csv: every posting from go-live, as Zoho's account registers list them.
"""
import csv
import hashlib
import json
import os
from collections import defaultdict
from datetime import date, timedelta

from .util import S, rng_for, stamp

LIST_FILES = ["contacts", "items", "locations", "projects", "invoices", "creditnotes", "customerpayments",
              "salesreceipts", "purchaseorders", "bills", "vendorpayments", "expenses", "inventoryadjustments",
              "journals"]


def clean(obj):
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def slim(rec):
    """Line items keep the account ID but not its name (the chart of accounts has it), and drop empty text."""
    for li in rec.get("line_items", []):
        li.pop("account_name", None)
        for k in [k for k, v in li.items() if v == ""]:
            li.pop(k)
    return rec


def write_list(path, key, records):
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"code": 0, "message": "success", "' + key + '": [\n')
        for i, r in enumerate(records):
            f.write(json.dumps(slim(clean(r)), ensure_ascii=False, separators=(",", ":")))
            f.write(",\n" if i < len(records) - 1 else "\n")
        f.write("]}\n")


def write_obj(path, key, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"code": 0, "message": "success", key: clean(obj)}, f, ensure_ascii=False, indent=1)
        f.write("\n")


def inv_status(b, inv, at):
    bal = b.inv_open(inv, at)
    paid = sum(a for d, a in inv["_paid"] if d <= at)
    if bal == 0:
        return "paid", bal, paid
    if inv["_due"] < at:
        return "overdue", bal, paid
    return ("partially_paid" if paid else "sent"), bal, paid


def bill_status(b, bill, at):
    bal = b.bill_open_fc(bill, at)
    paid = bill["_total_fc"] - bal
    if bal == 0:
        return "paid", bal, paid
    if bill["_due"] < at:
        return "overdue", bal, paid
    return ("partially_paid" if paid else "open"), bal, paid


def export_company(sim, out_dir):
    b, c = sim.b, sim.c
    go, end = sim.go_live, sim.data_end
    os.makedirs(out_dir, exist_ok=True)
    r = rng_for(sim.code, "export")
    pre = go - timedelta(days=1)
    counts = {}

    # ---------------------------------------------------------------- organisation, settings, users
    org = {
        "organization_id": f"{700000000 + c['org_num']}", "name": c["legal_name"], "contact_name": b.user_for("cfo")["name"],
        "email": f"finance@{c['code'].lower().replace('-', '')}.example", "is_default_org": False, "language_code": "en",
        "fiscal_year_start_month": (c.get("year_end_month", 12) % 12), "account_created_date": "2022-11-20",
        "time_zone": "Asia/Riyadh", "date_format": "yyyy-MM-dd", "currency_code": "SAR", "currency_symbol": "SAR",
        "country": "Saudi Arabia", "is_org_active": True, "tax_reg_no": c["vat_no"],
        "custom_fields": [{"label": "CR Number", "value": c["cr_no"]}],
        "address": {"city": c["city"], "country": "Saudi Arabia"},
        "note": "Made-up example company. Every name, number and identifier is invented.",
        "go_live_date": go.isoformat(),
    }
    write_obj(os.path.join(out_dir, "organization.json"), "organization", org)
    write_list(os.path.join(out_dir, "users.json"), "users", b.users)
    write_list(os.path.join(out_dir, "taxes.json"), "taxes", [b.tax_vat, b.tax_zero])
    curs = sorted({x.get("currency_code", "SAR") for x in b.docs["bills"]} | {"SAR"})
    write_list(os.path.join(out_dir, "currencies.json"), "currencies",
               [{"currency_id": f"cur-{k}", "currency_code": k, "is_base_currency": k == "SAR"} for k in curs])

    # ---------------------------------------------------------------- chart of accounts and banks
    accts = []
    for key, a in b.chart.items():
        accts.append({"account_id": a.account_id, "account_name": a.name, "account_code": a.code,
                      "account_type": a.zoho_type, "is_active": True, "is_user_created": True,
                      "currency_code": "SAR", "created_time": stamp(date(2022, 11, 21), r)})
    write_list(os.path.join(out_dir, "chartofaccounts.json"), "chartofaccounts", accts)
    banks = []
    for i, key in enumerate(("bank1", "bank2")):
        a = b.acct(key)
        banks.append({"account_id": a.account_id, "account_name": a.name, "account_code": a.code,
                      "account_type": "bank", "bank_name": "Example Bank A (made-up)" if i == 0 else "Example Bank B (made-up)",
                      "account_number": f"SA00TEST{c['org_num']:02d}{i + 1:014d}", "currency_code": "SAR",
                      "balance": S(b.bal[key]), "is_active": True})
    write_list(os.path.join(out_dir, "bankaccounts.json"), "bankaccounts", banks)

    # ---------------------------------------------------------------- documents
    def keep_dated(doc):
        return doc["_date"] >= go

    inv_out, mig_inv = [], 0
    for inv in b.docs["invoices"]:
        if inv["_date"] < go:
            open_go = b.inv_open(inv, pre)
            if open_go <= 0:
                continue
            mig_inv += open_go
            inv["custom_fields"] = [{"label": "Balance at go-live", "api_name": "cf_balance_at_go_live",
                                     "value": S(open_go)}, {"label": "Migrated", "api_name": "cf_migrated", "value": True}]
        st, bal, paid = inv_status(b, inv, end)
        inv["status"], inv["balance"] = st, S(bal)
        inv["payment_made"] = S(sum(a for d, a in inv["_paid"] if go <= d <= end))
        inv["credits_applied"] = S(sum(a for d, a in inv["_credits"] if go <= d <= end))
        inv_out.append(inv)
    bill_out, mig_bill = [], 0
    for bl in b.docs["bills"]:
        if bl["_date"] < go:
            open_go = b.bill_open_b(bl, pre)
            if open_go <= 0:
                continue
            mig_bill += open_go
            bl["custom_fields"] = [{"label": "Balance at go-live", "api_name": "cf_balance_at_go_live",
                                    "value": S(b.bill_open_fc(bl, pre))}, {"label": "Migrated", "api_name": "cf_migrated", "value": True}]
        st, bal, paid = bill_status(b, bl, end)
        bl["status"], bl["balance"] = st, S(bal)
        bl["payment_made"] = S(sum(a for d, a in bl["_paid"] if go <= d <= end))
        bill_out.append(bl)
    pos = []
    for po in b.docs["purchaseorders"]:
        if po["_date"] >= go or (po["_billed"] is None or po["_billed"] >= go):
            po["status"] = "billed" if po["_billed"] and po["_billed"] <= end else "open"
            pos.append(po)
    projects = []
    if hasattr(sim, "project_records"):
        live_ids = {i["_project_id"] for i in inv_out if i["_project_id"]}
        for pr in sim.project_records():
            if pr["project_id"] in live_ids or not pr["_complete"] or pr["_complete"] >= go:
                projects.append(pr)
    contacts = b.docs["contacts"]
    for ct in contacts:
        recv = sum(b.inv_open(i, end) for i in b.docs["invoices"] if i["_cust"] is ct) if ct["contact_type"] == "customer" else 0
        ct["outstanding_receivable_amount"] = S(recv)
    for bl in b.docs["bills"]:
        pass
    vend_open = defaultdict(int)
    for bl in b.docs["bills"]:
        vend_open[bl["_vendor"]["contact_id"]] += b.bill_open_b(bl, end)
    for ct in contacts:
        if ct["contact_type"] == "vendor":
            ct["outstanding_payable_amount"] = S(vend_open.get(ct["contact_id"], 0))

    files = {
        "contacts": contacts, "items": b.docs["items"], "locations": b.docs["locations"], "projects": projects,
        "invoices": inv_out, "creditnotes": [x for x in b.docs["creditnotes"] if keep_dated(x)],
        "customerpayments": [x for x in b.docs["customerpayments"] if keep_dated(x)],
        "salesreceipts": [x for x in b.docs["salesreceipts"] if keep_dated(x)],
        "purchaseorders": pos, "bills": bill_out,
        "vendorpayments": [x for x in b.docs["vendorpayments"] if keep_dated(x)],
        "expenses": [x for x in b.docs["expenses"] if keep_dated(x)],
        "inventoryadjustments": [x for x in b.docs["inventoryadjustments"] if keep_dated(x)],
        "journals": [x for x in b.docs["journals"] if keep_dated(x)],
    }
    for key in LIST_FILES:
        recs = files[key]
        if not recs:
            continue
        write_list(os.path.join(out_dir, f"{key}.json"), key, recs)
        counts[key] = len(recs)

    # ---------------------------------------------------------------- opening balances at go-live
    bal = defaultdict(int)
    for ln in b.lines:
        if ln[0] < go:
            bal[ln[1]] += ln[2]
    pl = sum(v for k, v in bal.items() if b.chart[k].group in "ICXO")
    ob = []
    for key, a in b.chart.items():
        if a.group in "ICXO":
            continue
        v = bal.get(key, 0) + (pl if key == "retained" else 0)
        if v:
            ob.append({"account_id": a.account_id, "account_name": a.name, "debit_or_credit": "debit" if v > 0 else "credit",
                       "exchange_rate": 1.0, "currency_code": "SAR", "amount": S(abs(v))})
    write_obj(os.path.join(out_dir, "openingbalances.json"), "opening_balance",
              {"date": go.isoformat(), "accounts": ob,
               "note": "Accounts receivable and payable at go-live equal the balances at go-live of the migrated "
                       "invoices and bills (custom field cf_balance_at_go_live)."})

    # ---------------------------------------------------------------- general ledger (account registers)
    gl_path = os.path.join(out_dir, "account_transactions.csv")
    with open(gl_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "account_id", "account_code", "transaction_type", "transaction_id",
                    "reference_number", "contact_name", "location_name", "description", "debit", "credit"])
        for key, a in b.chart.items():
            if a.group in "ICXO":
                continue
            v = bal.get(key, 0) + (pl if key == "retained" else 0)
            if v:
                w.writerow([go.isoformat(), a.account_id, a.code, "opening_balance", "opening-balance", "", "", "",
                            "Opening balance at go-live", f"{S(v):.2f}" if v > 0 else "0.00",
                            f"{S(-v):.2f}" if v < 0 else "0.00"])
        n = 0
        for ln in sorted((x for x in b.lines if go <= x[0] <= end), key=lambda x: x[0]):
            d, key, amt, ttype, tid, ref, desc, contact, loc = ln
            a = b.chart[key]
            w.writerow([d.isoformat(), a.account_id, a.code, ttype, tid, ref, contact, loc, desc,
                        f"{S(amt):.2f}" if amt > 0 else "0.00", f"{S(-amt):.2f}" if amt < 0 else "0.00"])
            n += 1
    counts["account_transactions"] = n

    # ---------------------------------------------------------------- bank statement lines
    btx = []
    for ln in sorted((x for x in b.lines if go <= x[0] <= end and x[1] in ("bank1", "bank2")), key=lambda x: x[0]):
        d, key, amt, ttype, tid, ref, desc, contact, loc = ln
        btx.append({"transaction_id": f"bt-{tid}-{key}", "account_id": b.acct(key).account_id, "date": d.isoformat(),
                    "amount": S(abs(amt)), "debit_or_credit": "debit" if amt > 0 else "credit",
                    "transaction_type": {"customer_payment": "customer_payment", "vendor_payment": "vendor_payment",
                                         "expense": "expense", "journal": "journal"}.get(ttype, ttype),
                    "reference_number": ref, "payee": contact, "description": desc, "status": "categorized",
                    "imported_transaction_id": f"imp-{tid}-{key}"})
    # statement lines the books have not yet picked up (unreconciled)
    unrec = []
    for i in range(r.randint(5, 9)):
        d = end - timedelta(days=r.choice([1, 2, 4, 6, 9, 13, 18, 26, 41, 75]))
        kind = r.choice([("credit", "Unidentified incoming transfer"), ("debit", "Bank charge not yet booked"),
                         ("credit", "Card settlement adjustment"), ("debit", "Returned transfer fee"),
                         ("credit", "Incoming transfer – reference missing")])
        amt = round(r.lognormvariate(8.5, 1.2), 2)
        unrec.append({"transaction_id": f"bt-unrec-{sim.code}-{i + 1}", "account_id": b.acct("bank2" if kind[0] == "credit" else "bank1").account_id,
                      "date": d.isoformat(), "amount": amt, "debit_or_credit": "debit" if kind[0] == "credit" else "credit",
                      "transaction_type": "deposit" if kind[0] == "credit" else "expense", "reference_number": "",
                      "payee": "", "description": kind[1], "status": "uncategorized",
                      "imported_transaction_id": f"imp-unrec-{sim.code}-{i + 1}"})
    btx += sorted(unrec, key=lambda x: x["date"])
    write_list(os.path.join(out_dir, "banktransactions.json"), "banktransactions", btx)
    counts["banktransactions"] = len(btx)
    sim._unreconciled = unrec

    # ---------------------------------------------------------------- transaction locking history
    locks = [{"lock_date": x["month"] + "-" + f"{month_days(x['month']):02d}", "locked_on": x["close_date"],
              "module": "all", "reason": "Month-end close"} for x in sim.close_log if x["month"] >= go.isoformat()[:7]
             and x["close_date"] <= end.isoformat()]
    write_list(os.path.join(out_dir, "transactionlocks.json"), "transaction_locks", locks)

    # ---------------------------------------------------------------- manifest
    man = {"company": sim.code, "name": c["name"], "go_live": go.isoformat(), "data_end": end.isoformat(),
           "counts": counts, "migrated_receivables_at_go_live": S(mig_inv), "migrated_payables_at_go_live": S(mig_bill),
           "files": {}}
    for fn in sorted(os.listdir(out_dir)):
        if fn == "manifest.json":
            continue
        with open(os.path.join(out_dir, fn), "rb") as f:
            data = f.read()
        man["files"][fn] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    return man


def month_days(ym: str) -> int:
    import calendar
    y, m = int(ym[:4]), int(ym[5:7])
    return calendar.monthrange(y, m)[1]
