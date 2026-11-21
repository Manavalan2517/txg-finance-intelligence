"""The change feed: the record changes a live Zoho connection would deliver, as a time-ordered list of events.

Part A replays everything entered from the cut (1 November 2026, 00:00 Riyadh time) to the data end: new
documents, payments, the October close entries. The state before the cut is the delivered files minus these
records (replay.py builds it). Part B adds live edits after the data end: an invoice amount changed, a
back-dated journal into a closed month, an edit to a journal in a closed month, a missing intercompany bill
finally booked, a corrected trial balance uploaded, and ordinary new activity.

Each event carries the full record (Zoho's webhooks send the record), its general-ledger postings and its
bank statement lines, so a consumer can apply it without another call.
"""
import copy
import csv
import json
import os
from collections import defaultdict

from .chart import build_chart
from .intercompany import ic_flows

CUT = "2026-11-01T00:00:00+0300"
TYPES = {"contacts": "contact_id", "projects": "project_id", "invoices": "invoice_id", "creditnotes": "creditnote_id",
         "customerpayments": "payment_id", "salesreceipts": "sales_receipt_id", "purchaseorders": "purchaseorder_id",
         "bills": "bill_id", "vendorpayments": "payment_id", "expenses": "expense_id",
         "inventoryadjustments": "inventory_adjustment_id", "journals": "journal_id"}
GL_COLS = ["date", "account_id", "account_code", "transaction_type", "transaction_id", "reference_number", "contact_name",
           "location_name", "description", "debit", "credit"]


def _load(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    return next(v for v in obj.values() if isinstance(v, list))


def _chart(cfg, code):
    comp = next(c for c in cfg["companies"] if c["code"] == code)
    n = [0]

    def nid(kind=""):
        n[0] += 1
        return f"46{comp['org_num']:04d}{n[0]:09d}"
    return build_chart(comp, nid)


class Company:
    def __init__(self, out, cfg, code):
        self.code, self.dir = code, os.path.join(out, "zoho", code)
        self.recs = {t: (_load(os.path.join(self.dir, f"{t}.json")) if os.path.exists(os.path.join(self.dir, f"{t}.json")) else [])
                     for t in TYPES}
        self.gl = defaultdict(list)
        with open(os.path.join(self.dir, "account_transactions.csv"), encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.gl[row["transaction_id"]].append(row)
        self.bank = defaultdict(list)
        for x in _load(os.path.join(self.dir, "banktransactions.json")):
            if x["transaction_id"].startswith("bt-") and not x["transaction_id"].startswith("bt-unrec"):
                self.bank[x["transaction_id"][3:].rsplit("-", 1)[0]].append(x)
        self.chart = _chart(cfg, code)
        self.users = _load(os.path.join(self.dir, "users.json"))
        self.seq = 0
        self.org = next(c for c in cfg["companies"] if c["code"] == code)["org_num"]

    def new_id(self):
        self.seq += 1
        return f"46{self.org:04d}9{self.seq:08d}"

    def acc(self, key):
        return self.chart[key]

    def user(self, title):
        return next(u for u in self.users if u["role_name"] == title)


def _row(date, a, ttype, tid, ref, desc, amt, contact="", loc=""):
    return {"date": date, "account_id": a.account_id, "account_code": a.code, "transaction_type": ttype,
            "transaction_id": tid, "reference_number": ref, "contact_name": contact, "location_name": loc,
            "description": desc, "debit": f"{amt / 100:.2f}" if amt > 0 else "0.00",
            "credit": f"{-amt / 100:.2f}" if amt < 0 else "0.00"}


def build_feed(out, cfg, codes):
    comps = {c: Company(out, cfg, c) for c in codes}
    events = []
    # ------------------------------------------------------------ part A: activity after the cut
    for code, co in comps.items():
        for t, key in TYPES.items():
            for r in co.recs[t]:
                ts = r.get("created_time", "")
                if ts >= CUT:
                    rid = r[key]
                    events.append({"ts": ts, "company": code, "op": "create", "record_type": t, "id": rid, "record": r,
                                   "postings": co.gl.get(rid, []), "bank_lines": co.bank.get(rid, []), "part": "A"})
    # ------------------------------------------------------------ part B: live edits after the data end
    b = []
    if "EH-01" in comps:
        co = comps["EH-01"]
        inv = sorted([r for r in co.recs["invoices"] if r["status"] in ("sent",) and "Interim" in r["line_items"][0]["name"]],
                     key=lambda r: r["date"])[-1]
        new = copy.deepcopy(inv)
        li = new["line_items"][0]
        net = int(round(li["rate"] * 100 * 0.96))
        vat = int(round(net * 0.15))
        li["rate"] = li["item_total"] = net / 100
        new.update({"sub_total": net / 100, "tax_total": vat / 100, "total": (net + vat) / 100, "balance": (net + vat) / 100,
                    "last_modified_time": "2026-11-20T10:21:44+0300",
                    "notes": f"Retention 10% (SAR {net * 0.1 / 100:,.2f}) withheld per contract. Revised: consultant certified 4% less."})
        tid = inv["invoice_id"]
        rows = [_row(inv["date"], co.acc("ar"), "invoice", tid, inv["invoice_number"], "", net + vat, inv["customer_name"]),
                _row(inv["date"], co.acc("rev_contract"), "invoice", tid, inv["invoice_number"], "", -net, inv["customer_name"]),
                _row(inv["date"], co.acc("vat_out"), "invoice", tid, inv["invoice_number"], "", -vat, inv["customer_name"])]
        b.append({"ts": new["last_modified_time"], "company": "EH-01", "op": "update", "record_type": "invoices", "id": tid,
                  "before": inv, "record": new, "postings_before": co.gl[tid], "postings": rows, "bank_lines": [],
                  "why": "The consultant reduced a certificate after it was invoiced; revenue and receivables fall."})
        proj = next(p for p in co.recs["projects"] if p.get("status") == "active")
        jid, amt, ts = co.new_id(), 125_000_000, "2026-11-20T09:42:11+0300"
        u = co.user("Finance Manager")
        jr = {"journal_id": jid, "entry_number": "JV-B00001", "journal_date": "2026-09-30", "reference_number": "LDP-202609",
              "notes": f"Provision for liquidated damages – delayed handover, {proj['project_code']}", "journal_type": "both",
              "line_items": [{"line_id": co.new_id(), "account_id": co.acc("other_direct").account_id,
                              "description": "Liquidated damages provision", "debit_or_credit": "debit", "amount": amt / 100},
                             {"line_id": co.new_id(), "account_id": co.acc("accrued").account_id,
                              "description": "Liquidated damages provision", "debit_or_credit": "credit", "amount": amt / 100}],
              "total": amt / 100, "created_time": ts, "last_modified_time": ts, "created_by_id": u["user_id"],
              "created_by_name": u["name"]}
        b.append({"ts": ts, "company": "EH-01", "op": "create", "record_type": "journals", "id": jid, "record": jr,
                  "postings": [_row("2026-09-30", co.acc("other_direct"), "journal", jid, "JV-B00001", jr["notes"], amt),
                               _row("2026-09-30", co.acc("accrued"), "journal", jid, "JV-B00001", jr["notes"], -amt)],
                  "bank_lines": [], "why": "A back-dated journal into September, a month already closed and locked."})
    if "EH-02" in comps and "EH-05" in comps:
        co = comps["EH-02"]
        spec = next(f for f in cfg.get("intercompany", []) if f["seller"] == "EH-05" and f["buyer"] == "EH-02")
        f = next(x for x in ic_flows(cfg, "EH-05", "EH-02") if x["unbooked"])
        v = next(c for c in co.recs["contacts"] if c["contact_name"].startswith("Example Building Materials A"))
        net, vat = f["net"], int(round(f["net"] * 0.15))
        bid, ts = co.new_id(), "2026-11-20T13:05:09+0300"
        u = co.user("Accountant – Payables")
        bill = {"bill_id": bid, "bill_number": f["dn"], "date": f["date"].isoformat(), "due_date": f["due"].isoformat(),
                "payment_terms": spec["terms"], "payment_terms_label": f"Net {spec['terms']}", "vendor_id": v["contact_id"],
                "vendor_name": v["contact_name"], "currency_code": "SAR", "exchange_rate": 1.0, "reference_number": f["dn"],
                "line_items": [{"line_item_id": co.new_id(), "name": f"Building materials as per delivery note {f['dn']}",
                                "quantity": 1, "rate": net / 100, "tax_id": "", "tax_percentage": 15, "item_total": net / 100,
                                "account_id": co.acc("direct_materials").account_id}],
                "sub_total": net / 100, "tax_total": vat / 100, "total": (net + vat) / 100, "status": "overdue",
                "balance": (net + vat) / 100, "payment_made": 0.0, "created_time": ts, "last_modified_time": ts,
                "created_by_id": u["user_id"], "created_by_name": u["name"]}
        d = f["date"].isoformat()
        b.append({"ts": ts, "company": "EH-02", "op": "create", "record_type": "bills", "id": bid, "record": bill,
                  "postings": [_row(d, co.acc("direct_materials"), "bill", bid, f["dn"], "", net, v["contact_name"]),
                               _row(d, co.acc("vat_in"), "bill", bid, f["dn"], "", vat, v["contact_name"]),
                               _row(d, co.acc("ap"), "bill", bid, f["dn"], "", -(net + vat), v["contact_name"])],
                  "bank_lines": [], "why": "EH-02 books the intercompany invoice it had missed (story S6): the mismatch with EH-05 clears."})
    if "EH-21" in comps:
        co = comps["EH-21"]
        jr = sorted([j for j in co.recs["journals"] if j["reference_number"].startswith("RCL-")], key=lambda j: j["journal_date"])[3]
        new = copy.deepcopy(jr)
        amt = int(round(jr["total"] * 100 * 1.5))
        for li in new["line_items"]:
            li["amount"] = amt / 100
        new["total"] = amt / 100
        new["last_modified_time"] = "2026-11-21T20:47:03+0300"
        tid = jr["journal_id"]
        rows = [_row(jr["journal_date"], co.acc("ga"), "journal", tid, jr["entry_number"], jr["notes"], amt),
                _row(jr["journal_date"], co.acc("other_direct"), "journal", tid, jr["entry_number"], jr["notes"], -amt)]
        b.append({"ts": new["last_modified_time"], "company": "EH-21", "op": "update", "record_type": "journals", "id": tid,
                  "before": jr, "record": new, "postings_before": co.gl[tid], "postings": rows, "bank_lines": [],
                  "why": "A journal in a closed month is edited on a Friday evening (story S7)."})
    if "EH-03" in comps:
        b.append({"ts": "2026-11-20T15:30:00+0300", "company": "EH-03", "op": "upload", "record_type": "trial_balance",
                  "id": "tb-2026-08-corrected", "month": "2026-08",
                  "file": "uploads/EH-03/trial_balances/trial_balance_2026-08_corrected.csv",
                  "why": "The corrected trial balance for August 2026 is uploaded; it ties, so the hold lifts (story S12)."})
    if "EH-08" in comps:
        co = comps["EH-08"]
        src = sorted(co.recs["invoices"], key=lambda r: (r["date"], r["invoice_number"]))[-1]
        nums = max(int(r["invoice_number"].split("-")[1]) for r in co.recs["invoices"] if r["invoice_number"].startswith("INV-"))
        iid, ts = co.new_id(), "2026-11-20T11:05:37+0300"
        inv = copy.deepcopy(src)
        inv.update({"invoice_id": iid, "invoice_number": f"INV-{nums + 1:06d}", "date": "2026-11-20",
                    "status": "sent", "balance": inv["total"], "payment_made": 0.0, "credits_applied": 0.0,
                    "created_time": ts, "last_modified_time": ts})
        for li in inv["line_items"]:
            li["line_item_id"] = co.new_id()
        rows = []
        for rr in co.gl[src["invoice_id"]]:
            x = dict(rr, date="2026-11-20", transaction_id=iid, reference_number=inv["invoice_number"])
            rows.append(x)
        b.append({"ts": ts, "company": "EH-08", "op": "create", "record_type": "invoices", "id": iid, "record": inv,
                  "postings": rows, "bank_lines": [], "why": "A new sales invoice."})
        by_c = defaultdict(list)
        for r in co.recs["invoices"]:
            if r["status"] in ("sent", "overdue") and r["balance"] > 0 and r["balance"] == r["total"]:
                by_c[r["customer_id"]].append(r)
        cid = max(by_c, key=lambda k: sum(r["balance"] for r in by_c[k]))
        pays = sorted(by_c[cid], key=lambda r: r["date"])[:2]
        pid, ts = co.new_id(), "2026-11-20T12:40:15+0300"
        tot = int(round(sum(r["balance"] for r in pays) * 100))
        pay = {"payment_id": pid, "payment_number": "PMT-B00001", "customer_id": cid, "customer_name": pays[0]["customer_name"],
               "payment_mode": "banktransfer", "date": "2026-11-20", "amount": tot / 100, "bank_charges": 0,
               "account_id": co.acc("bank2").account_id, "account_name": co.acc("bank2").name, "reference_number": "TRF20261120",
               "invoices": [{"invoice_id": r["invoice_id"], "invoice_number": r["invoice_number"], "amount_applied": r["balance"]}
                            for r in pays], "created_time": ts, "last_modified_time": ts}
        b.append({"ts": ts, "company": "EH-08", "op": "create", "record_type": "customerpayments", "id": pid, "record": pay,
                  "postings": [_row("2026-11-20", co.acc("bank2"), "customer_payment", pid, "PMT-B00001", "", tot, pay["customer_name"]),
                               _row("2026-11-20", co.acc("ar"), "customer_payment", pid, "PMT-B00001", "", -tot, pay["customer_name"])],
                  "bank_lines": [{"transaction_id": f"bt-{pid}-bank2", "account_id": co.acc("bank2").account_id, "date": "2026-11-20",
                                  "amount": tot / 100, "debit_or_credit": "debit", "transaction_type": "customer_payment",
                                  "reference_number": "PMT-B00001", "payee": pay["customer_name"], "status": "categorized"}],
                  "why": "A supermarket chain pays two invoices."})
        for r in pays:
            new = dict(r, balance=0.0, status="paid", payment_made=r["total"], last_modified_time=ts)
            b.append({"ts": ts, "company": "EH-08", "op": "update", "record_type": "invoices", "id": r["invoice_id"],
                      "before": r, "record": new, "postings": co.gl[r["invoice_id"]], "postings_before": co.gl[r["invoice_id"]],
                      "bank_lines": [], "why": "Invoice settled by the payment above."})
    if "EH-14" in comps:
        co = comps["EH-14"]
        last = [r for r in co.recs["salesreceipts"] if r["date"] == "2026-11-19"][:3]
        for k, src in enumerate(last):
            rid, ts = co.new_id(), f"2026-11-21T03:{12 + k:02d}:05+0300"
            rc = copy.deepcopy(src)
            rc.update({"sales_receipt_id": rid, "receipt_number": f"SR-B{k + 1:06d}", "date": "2026-11-20", "created_time": ts,
                       "last_modified_time": ts})
            for li in rc["line_items"]:
                li["line_item_id"] = co.new_id()
            rows = [dict(rr, date="2026-11-20", transaction_id=rid, reference_number=rc["receipt_number"])
                    for rr in co.gl[src["sales_receipt_id"]]]
            b.append({"ts": ts, "company": "EH-14", "op": "create", "record_type": "salesreceipts", "id": rid, "record": rc,
                      "postings": rows, "bank_lines": [], "why": "A store's takings for 20 November, posted overnight."})
    for e in b:
        e["part"] = "B"
    events += b
    events.sort(key=lambda e: (e["ts"], e["company"], e["id"]))
    for i, e in enumerate(events, start=1):
        e["seq"] = i
    fdir = os.path.join(out, "feed")
    os.makedirs(fdir, exist_ok=True)
    with open(os.path.join(fdir, "changes.jsonl"), "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps({k: e[k] for k in ["seq", "ts", "company", "op", "record_type", "id", "part"] + [
                k for k in e if k not in ("seq", "ts", "company", "op", "record_type", "id", "part")]},
                ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = defaultdict(lambda: defaultdict(int))
    for e in events:
        summary[f"{e['company']} part {e['part']}"][f"{e['op']} {e['record_type']}"] += 1
    with open(os.path.join(fdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"cut": CUT, "events": len(events), "by_company": summary,
                   "part_b": [{"seq": e["seq"], "ts": e["ts"], "company": e["company"], "op": e["op"],
                               "record_type": e["record_type"], "why": e.get("why", "")} for e in events if e["part"] == "B"]},
                  f, indent=1, ensure_ascii=False)
    return events
