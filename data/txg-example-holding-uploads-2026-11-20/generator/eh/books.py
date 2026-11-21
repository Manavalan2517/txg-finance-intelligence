"""The books of one company: a double-entry ledger plus Zoho-shaped documents.

Every document posts balanced lines to the ledger at the moment it is created, so the trial balance,
the sub-ledgers and the bank always agree by construction. The simulation runs day by day and nothing is
ever posted with a date after the current simulated day, so any balance read during the run is the
balance as at that day. Internal fields start with "_" and are never exported.
"""
import heapq
from collections import defaultdict
from datetime import date, timedelta

from .chart import build_chart
from .util import S, rng_for, stamp, vat_of


class Books:
    def __init__(self, company: dict, go_live: date, data_end: date):
        self.c = company
        self.code = company["code"]
        self.go_live = go_live
        self.data_end = data_end
        self.today = None
        self._seq = 0
        self._num = defaultdict(int)
        self.rng = rng_for(self.code, "books")
        self.chart = build_chart(company, self.new_id)
        self.lines = []           # (date, key, amount, ttype, tid, ref, desc, contact, location_name)
        self.bal = defaultdict(int)
        self.docs = defaultdict(list)
        self._heap = []
        self._pseq = 0
        self.users = []
        self.tax_vat = {"tax_id": self.new_id("tax"), "tax_name": "VAT 15%", "tax_percentage": 15,
                        "tax_type": "tax", "is_default_tax": True}
        self.tax_zero = {"tax_id": self.new_id("tax"), "tax_name": "Out of Scope", "tax_percentage": 0,
                         "tax_type": "tax", "is_default_tax": False}

    # ------------------------------------------------------------------ ids and numbers
    def new_id(self, kind: str = "") -> str:
        self._seq += 1
        return f"46{self.c['org_num']:04d}{self._seq:09d}"

    def next_number(self, prefix: str, width: int = 6) -> str:
        self._num[prefix] += 1
        return f"{prefix}-{self._num[prefix]:0{width}d}"

    def acct(self, key: str):
        return self.chart[key]

    # ------------------------------------------------------------------ ledger
    def post(self, d: date, entries, ttype: str, tid: str, ref: str = "", desc: str = "", contact: str = "",
             location: str = ""):
        """entries: (account key, signed amount) or (account key, signed amount, location name)."""
        if self.today is not None and d > self.today:
            raise ValueError(f"{self.code}: {ttype} {ref} dated {d} is after the simulated day {self.today}")
        total = 0
        for e in entries:
            if e[0] not in self.chart:
                raise KeyError(f"{self.code}: no account '{e[0]}' for {ttype} {ref}")
            total += e[1]
        if total != 0:
            raise ValueError(f"{self.code}: unbalanced {ttype} {ref} on {d}: {entries}")
        for e in entries:
            key, amt = e[0], e[1]
            if amt:
                self.bal[key] += amt
                self.lines.append((d, key, amt, ttype, tid, ref, desc, contact,
                                   e[2] if len(e) > 2 and e[2] else location))

    # ------------------------------------------------------------------ scheduling
    def schedule(self, d: date, fn):
        """Run fn(day) on day d (or on the current day if d has already passed)."""
        self._pseq += 1
        heapq.heappush(self._heap, (d, self._pseq, fn))

    def run_due(self, d: date):
        while self._heap and self._heap[0][0] <= d:
            _, _, fn = heapq.heappop(self._heap)
            fn(d)

    # ------------------------------------------------------------------ users, contacts, items, locations
    def user_for(self, role: str) -> dict:
        for u in self.users:
            if u["_role"] == role:
                return u
        return self.users[0]

    def add_contact(self, name: str, ctype: str, cls: str, terms: int, created: date, currency: str = "SAR",
                    vat_no: str = "", cr_no: str = "", group_company: str = "", prefix: str = "",
                    city: str = "", country: str = "SA") -> dict:
        cid = self.new_id("contact")
        c = {
            "contact_id": cid, "contact_name": name, "company_name": name, "contact_type": ctype,
            "customer_sub_type": "business", "status": "active", "currency_code": currency,
            "payment_terms": terms, "payment_terms_label": f"Net {terms}" if terms else "Due on Receipt",
            "tax_treatment": "vat_registered" if vat_no else ("non_gcc" if country != "SA" else "vat_not_registered"),
            "tax_reg_no": vat_no,
            "billing_address": {"city": city, "country": country},
            "custom_fields": ([{"label": "CR Number", "value": cr_no}] if cr_no else []),
            "created_time": stamp(created, self.rng), "_class": cls, "_group_company": group_company,
            "_prefix": prefix, "_created": created,
        }
        c["last_modified_time"] = c["created_time"]
        self.docs["contacts"].append(c)
        return c

    def add_item(self, name: str, sku: str, unit: str, rate: int, purchase_rate: int, item_type: str,
                 sales_key: str, purchase_key: str, family: str = "", vendor: dict = None,
                 purchase_currency: str = "SAR") -> dict:
        it = {
            "item_id": self.new_id("item"), "name": name, "sku": sku, "unit": unit, "rate": S(rate),
            "purchase_rate": S(purchase_rate), "item_type": item_type,
            "product_type": "goods" if item_type in ("inventory", "sales_and_purchases") else "service",
            "account_id": self.acct(sales_key).account_id,
            "purchase_account_id": self.acct(purchase_key).account_id if purchase_key else "",
            "inventory_account_id": self.acct("inventory").account_id if item_type == "inventory" else "",
            "tax_id": self.tax_vat["tax_id"], "status": "active", "group_name": family,
            "vendor_id": vendor["contact_id"] if vendor else "", "vendor_name": vendor["contact_name"] if vendor else "",
            "_family": family, "_rate": rate, "_purchase_rate": purchase_rate, "_currency": purchase_currency,
        }
        self.docs["items"].append(it)
        return it

    def add_location(self, name: str, code: str, city: str, opened: date, area_m2: int = 0) -> dict:
        loc = {"location_id": self.new_id("location"), "location_name": name, "type": "business",
               "is_primary": False, "status": "active", "address": {"city": city, "country": "SA"},
               "_code": code, "_opened": opened, "_area": area_m2, "_closed": None}
        self.docs["locations"].append(loc)
        return loc

    # ------------------------------------------------------------------ helpers for documents
    def _tag(self, loc):
        return [{"tag_name": "Store", "tag_option_id": loc["location_id"], "tag_option_name": loc["location_name"]}]

    def _line_item(self, l: dict, gross: int, net: int, tax: int, project_id: str = "") -> dict:
        a = self.acct(l["account"])
        li = {
            "line_item_id": self.new_id("line"), "item_id": l["item"]["item_id"] if l.get("item") else "",
            "name": l["name"], "description": l.get("desc", ""), "quantity": l["qty"], "rate": S(l["rate"]),
            "tax_id": self.tax_vat["tax_id"] if tax else self.tax_zero["tax_id"],
            "tax_percentage": 15 if tax else 0, "item_total": S(net), "account_id": a.account_id,
            "account_name": a.name,
        }
        if l.get("unit"):
            li["unit"] = l["unit"]
        if gross != net:
            li["discount"] = f"{l.get('discount_pct', 0) * 100:.2f}%"
            li["discount_amount"] = S(gross - net)
        if project_id:
            li["project_id"] = project_id
        if l.get("tag"):
            li["tags"] = self._tag(l["tag"])
        return li

    def _lines(self, lines, taxable_default=True, opening=False, project_id=""):
        """Price the lines: returns (line_items, sub, tax, net_by_account)."""
        items, sub, tax, by_acct = [], 0, 0, defaultdict(int)
        for l in lines:
            gross = int(round(l["qty"] * l["rate"]))
            net = int(round(gross * (1 - l.get("discount_pct", 0))))
            t = vat_of(net) if l.get("vat", taxable_default) else 0
            sub += net
            tax += t
            by_acct[l["account"]] += net
            items.append(self._line_item(l, gross, net, t, project_id))
        return items, sub, tax, by_acct

    def _stamp_doc(self, doc, d, role, lag=0):
        lag = min(lag, max(0, (self.data_end - d).days))
        doc["created_time"] = stamp(d, self.rng, lag_days=lag)
        doc["last_modified_time"] = doc["created_time"]
        u = self.user_for(role)
        doc["created_by_id"] = u["user_id"]
        doc["created_by_name"] = u["name"]

    def _loc(self, doc, loc):
        if loc:
            doc["location_id"] = loc["location_id"]
            doc["location_name"] = loc["location_name"]

    # ------------------------------------------------------------------ sales side
    def invoice(self, d: date, cust: dict, lines: list, terms: int = None, ref: str = "", project_id: str = "",
                opening: bool = False, created_lag: int = 0, cogs: list = None, number: str = "",
                retention: int = 0, notes: str = "", location: dict = None, role: str = "ar") -> dict:
        """lines: dicts with name, desc, qty, rate (halalas per unit, before discount), discount_pct, account,
        item, vat (bool). cogs: list of (cogs_key, inventory_key, amount) posted with the invoice.
        retention: amount of the total the customer withholds until release."""
        terms = cust["payment_terms"] if terms is None else terms
        iid = self.new_id("invoice")
        num = number or self.next_number("INV")
        items, sub, tax, rev = self._lines(lines, opening=opening, project_id=project_id)
        total = sub + tax
        if opening:
            entries = [("ar", total), ("retained", -total)]
        else:
            entries = [("ar", total)] + [(k, -v) for k, v in rev.items()]
            if tax:
                entries.append(("vat_out", -tax))
            for ck, ik, amt in (cogs or []):
                if amt:
                    entries += [(ck, amt), (ik, -amt)]
        self.post(d, entries, "invoice", iid, ref=num, contact=cust["contact_name"],
                  location=location["location_name"] if location else "")
        doc = {
            "invoice_id": iid, "invoice_number": num, "date": d.isoformat(),
            "due_date": (d + timedelta(days=terms)).isoformat(), "payment_terms": terms,
            "payment_terms_label": f"Net {terms}" if terms else "Due on Receipt",
            "customer_id": cust["contact_id"], "customer_name": cust["contact_name"], "currency_code": "SAR",
            "exchange_rate": 1.0, "reference_number": ref, "line_items": items, "sub_total": S(sub),
            "tax_total": S(tax), "total": S(total), "notes": notes,
            "_date": d, "_due": d + timedelta(days=terms), "_total": total, "_paid": [], "_credits": [],
            "_cust": cust, "_opening": opening, "_project_id": project_id, "_retention": retention,
            "_retention_orig": retention, "_ret0": retention, "_ret_hist": [],
        }
        if project_id:
            doc["project_id"] = project_id
        self._loc(doc, location)
        self._stamp_doc(doc, d, role, created_lag)
        self.docs["invoices"].append(doc)
        return doc

    def inv_open(self, inv: dict, at: date = None) -> int:
        paid = sum(a for dd, a in inv["_paid"] if at is None or dd <= at)
        cred = sum(a for dd, a in inv["_credits"] if at is None or dd <= at)
        return inv["_total"] - paid - cred

    def customer_payment(self, d: date, cust: dict, apps: list, bank: str = "bank1", mode: str = "banktransfer",
                         ref: str = "", desc: str = ""):
        """apps: list of (invoice, amount). Amounts are capped at what is still open."""
        clean = []
        for inv, a in apps:
            a = min(a, self.inv_open(inv))
            if a > 0:
                clean.append((inv, a))
        if not clean:
            return None
        total = sum(a for _, a in clean)
        pid = self.new_id("customerpayment")
        num = self.next_number("PMT")
        self.post(d, [(bank, total), ("ar", -total)], "customer_payment", pid, ref=num, contact=cust["contact_name"])
        for inv, a in clean:
            inv["_paid"].append((d, a))
        a_bank = self.acct(bank)
        doc = {
            "payment_id": pid, "payment_number": num, "customer_id": cust["contact_id"],
            "customer_name": cust["contact_name"], "payment_mode": mode, "date": d.isoformat(), "amount": S(total),
            "bank_charges": 0, "account_id": a_bank.account_id, "account_name": a_bank.name,
            "reference_number": ref or f"TRF{self.rng.randint(10**7, 10**8 - 1)}", "description": desc,
            "invoices": [{"invoice_id": inv["invoice_id"], "invoice_number": inv["invoice_number"],
                          "amount_applied": S(a)} for inv, a in clean],
            "_date": d,
        }
        self._stamp_doc(doc, d, "ar", self.rng.choice([0, 0, 0, 1, 1, 2]))
        self.docs["customerpayments"].append(doc)
        return doc

    def credit_note(self, d: date, cust: dict, inv: dict, net: int, returns_key: str, reason: str):
        net = min(net, max(0, int((self.inv_open(inv) - inv["_retention"]) / 1.15)))
        if net <= 0:
            return None
        tax = vat_of(net)
        total = net + tax
        cid = self.new_id("creditnote")
        num = self.next_number("CN")
        self.post(d, [(returns_key, net), ("vat_out", tax), ("ar", -total)], "creditnote", cid, ref=num,
                  contact=cust["contact_name"])
        inv["_credits"].append((d, total))
        a = self.acct(returns_key)
        doc = {
            "creditnote_id": cid, "creditnote_number": num, "date": d.isoformat(), "customer_id": cust["contact_id"],
            "customer_name": cust["contact_name"], "currency_code": "SAR", "reference_number": inv["invoice_number"],
            "line_items": [{"line_item_id": self.new_id("line"), "name": "Credit", "description": reason,
                            "quantity": 1, "rate": S(net), "tax_id": self.tax_vat["tax_id"], "tax_percentage": 15,
                            "item_total": S(net), "account_id": a.account_id, "account_name": a.name}],
            "sub_total": S(net), "tax_total": S(tax), "total": S(total), "balance": 0, "status": "closed",
            "invoices_credited": [{"invoice_id": inv["invoice_id"], "invoice_number": inv["invoice_number"],
                                   "amount_applied": S(total)}],
            "_date": d,
        }
        self._stamp_doc(doc, d, "ar", self.rng.choice([0, 1, 2, 3]))
        self.docs["creditnotes"].append(doc)
        return doc

    def sales_receipt(self, d: date, cust: dict, lines: list, deposit_key: str, location: dict = None,
                      mode: str = "card", role: str = "pos") -> dict:
        rid = self.new_id("salesreceipt")
        num = self.next_number("SR", 7)
        items, sub, tax, rev = self._lines(lines)
        total = sub + tax
        entries = [(deposit_key, total)] + [(k, -v) for k, v in rev.items()]
        if tax:
            entries.append(("vat_out", -tax))
        self.post(d, entries, "sales_receipt", rid, ref=num, contact=cust["contact_name"],
                  location=location["location_name"] if location else "")
        dep = self.acct(deposit_key)
        doc = {
            "sales_receipt_id": rid, "receipt_number": num, "date": d.isoformat(),
            "customer_id": cust["contact_id"], "customer_name": cust["contact_name"], "currency_code": "SAR",
            "payment_mode": mode, "deposit_to_account_id": dep.account_id, "deposit_to_account_name": dep.name,
            "line_items": items, "sub_total": S(sub), "tax_total": S(tax), "total": S(total), "_date": d,
            "_total": total,
        }
        self._loc(doc, location)
        doc["created_time"] = stamp(d, self.rng, lag_days=1 if d < self.data_end else 0, hour_lo=1, hour_hi=4)
        doc["last_modified_time"] = doc["created_time"]
        u = self.user_for(role)
        doc["created_by_id"], doc["created_by_name"] = u["user_id"], u["name"]
        self.docs["salesreceipts"].append(doc)
        return doc

    # ------------------------------------------------------------------ purchase side
    def purchase_order(self, d: date, vendor: dict, lines: list, expected: date, currency: str = "SAR",
                       rate: float = 1.0, location: dict = None) -> dict:
        pid = self.new_id("purchaseorder")
        num = self.next_number("PO")
        vat = currency == "SAR"
        items, sub, tax, _ = self._lines(lines, taxable_default=vat)
        doc = {
            "purchaseorder_id": pid, "purchaseorder_number": num, "date": d.isoformat(),
            "delivery_date": expected.isoformat(), "vendor_id": vendor["contact_id"],
            "vendor_name": vendor["contact_name"], "currency_code": currency, "exchange_rate": rate,
            "line_items": items, "sub_total": S(sub), "tax_total": S(tax), "total": S(sub + tax), "_date": d,
            "_expected": expected, "_billed": None, "_total_fc": sub + tax, "_rate": rate,
        }
        self._loc(doc, location)
        self._stamp_doc(doc, d, "ap", 0)
        self.docs["purchaseorders"].append(doc)
        return doc

    def bill(self, d: date, vendor: dict, lines: list, terms: int = None, currency: str = "SAR", rate: float = 1.0,
             vat: bool = True, created_lag: int = 0, opening: bool = False, number: str = "", retention: int = 0,
             location: dict = None, po: dict = None, ref: str = "", notes: str = "", project_id: str = "") -> dict:
        """lines: dicts with name, desc, qty, rate (minor units of the bill currency per unit), account, item.
        retention: amount (bill currency) withheld from payment until released."""
        terms = vendor["payment_terms"] if terms is None else terms
        bid = self.new_id("bill")
        num = number or f"{vendor['_prefix'] or 'BL'}-{self.rng.randint(1000, 99999)}"
        items, sub_fc, tax_fc, debit_fc = self._lines(lines, taxable_default=vat and currency == "SAR",
                                                      opening=opening, project_id=project_id)
        total_fc = sub_fc + tax_fc
        debit = {k: int(round(v * rate)) for k, v in debit_fc.items()}
        tax_b = int(round(tax_fc * rate))
        total_b = sum(debit.values()) + tax_b
        if opening:
            entries = [("retained", total_b), ("ap", -total_b)]
        else:
            entries = [(k, v) for k, v in debit.items()]
            if tax_b:
                entries.append(("vat_in", tax_b))
            entries.append(("ap", -total_b))
        self.post(d, entries, "bill", bid, ref=num, contact=vendor["contact_name"],
                  location=location["location_name"] if location else "")
        doc = {
            "bill_id": bid, "bill_number": num, "date": d.isoformat(),
            "due_date": (d + timedelta(days=terms)).isoformat(), "payment_terms": terms,
            "payment_terms_label": f"Net {terms}" if terms else "Due on Receipt", "vendor_id": vendor["contact_id"],
            "vendor_name": vendor["contact_name"], "currency_code": currency, "exchange_rate": rate,
            "reference_number": ref, "line_items": items, "sub_total": S(sub_fc), "tax_total": S(tax_fc),
            "total": S(total_fc), "notes": notes, "_date": d, "_due": d + timedelta(days=terms),
            "_total_fc": total_fc, "_total_b": total_b, "_rate": rate, "_paid": [], "_vendor": vendor,
            "_opening": opening, "_retention": retention, "_retention_orig": retention, "_project_id": project_id,
            "_ret0": retention, "_ret_hist": [],
        }
        if po:
            doc["purchaseorder_ids"] = [po["purchaseorder_id"]]
            po["_billed"] = d
        if project_id:
            doc["project_id"] = project_id
        self._loc(doc, location)
        self._stamp_doc(doc, d, "ap", created_lag)
        self.docs["bills"].append(doc)
        return doc

    def bill_open_fc(self, b: dict, at: date = None) -> int:
        return b["_total_fc"] - sum(a for dd, a in b["_paid"] if at is None or dd <= at)

    def bill_open_b(self, b: dict, at: date = None) -> int:
        """Open amount in SAR at the bill's own rate (how payables are carried)."""
        if self.bill_open_fc(b, at) == 0:
            return 0
        paid_b = sum(int(round(a * b["_rate"])) for dd, a in b["_paid"] if at is None or dd <= at)
        return b["_total_b"] - paid_b

    def vendor_payment(self, d: date, vendor: dict, apps: list, bank: str = "bank1", rate_now: float = None,
                       mode: str = "banktransfer"):
        """apps: list of (bill, amount in bill currency). A payment that clears a bill clears its SAR carrying
        amount exactly; any difference to the SAR actually paid is an exchange gain or loss."""
        clean = []
        for b, a in apps:
            a = min(a, self.bill_open_fc(b))
            if a > 0:
                clean.append((b, a))
        if not clean:
            return None
        cleared = paid = 0
        for b, a in clean:
            c = self.bill_open_b(b) if a == self.bill_open_fc(b) else int(round(a * b["_rate"]))
            cleared += c
            paid += int(round(a * (rate_now if rate_now else b["_rate"])))
        fx = paid - cleared
        pid = self.new_id("vendorpayment")
        num = self.next_number("VP")
        entries = [("ap", cleared), (bank, -paid)]
        if fx:
            entries.append(("fx", fx))
        self.post(d, entries, "vendor_payment", pid, ref=num, contact=vendor["contact_name"])
        for b, a in clean:
            b["_paid"].append((d, a))
        a_bank = self.acct(bank)
        cur = clean[0][0]["currency_code"]
        doc = {
            "payment_id": pid, "payment_number": num, "vendor_id": vendor["contact_id"],
            "vendor_name": vendor["contact_name"], "payment_mode": mode, "date": d.isoformat(),
            "amount": S(sum(a for _, a in clean)), "currency_code": cur,
            "exchange_rate": rate_now if rate_now else clean[0][0]["_rate"],
            "paid_through_account_id": a_bank.account_id, "paid_through_account_name": a_bank.name,
            "reference_number": f"OUT{self.rng.randint(10**7, 10**8 - 1)}",
            "bills": [{"bill_id": b["bill_id"], "bill_number": b["bill_number"], "amount_applied": S(a)}
                      for b, a in clean],
            "_date": d, "_paid_b": paid,
        }
        self._stamp_doc(doc, d, "ap", 0)
        self.docs["vendorpayments"].append(doc)
        return doc

    def expense(self, d: date, account_key: str, net: int, paid_through: str = "bank1", vat: bool = True,
                vendor: dict = None, desc: str = "", location: dict = None, ref: str = "", role: str = "ap"):
        if net <= 0:
            return None
        tax = vat_of(net) if vat else 0
        eid = self.new_id("expense")
        entries = [(account_key, net), (paid_through, -(net + tax))]
        if tax:
            entries.append(("vat_in", tax))
        self.post(d, entries, "expense", eid, ref=ref, desc=desc, contact=vendor["contact_name"] if vendor else "",
                  location=location["location_name"] if location else "")
        a, p = self.acct(account_key), self.acct(paid_through)
        doc = {
            "expense_id": eid, "date": d.isoformat(), "account_id": a.account_id, "account_name": a.name,
            "paid_through_account_id": p.account_id, "paid_through_account_name": p.name,
            "sub_total": S(net), "tax_id": self.tax_vat["tax_id"] if tax else self.tax_zero["tax_id"],
            "tax_amount": S(tax), "total": S(net + tax), "currency_code": "SAR", "description": desc,
            "reference_number": ref, "vendor_id": vendor["contact_id"] if vendor else "",
            "vendor_name": vendor["contact_name"] if vendor else "", "is_billable": False, "_date": d,
        }
        if location:
            doc["tags"] = self._tag(location)
        self._loc(doc, location)
        self._stamp_doc(doc, d, role, self.rng.choice([0, 0, 1, 2, 4]))
        self.docs["expenses"].append(doc)
        return doc

    def inventory_adjustment(self, d: date, lines: list, reason: str, account_key: str = "inv_adjust",
                             location: dict = None) -> dict:
        """lines: (item, quantity removed, cost value in halalas)."""
        total = sum(v for _, _, v in lines)
        if total <= 0:
            return None
        aid = self.new_id("inventoryadjustment")
        num = self.next_number("ADJ", 5)
        self.post(d, [(account_key, total), ("inventory", -total)], "inventory_adjustment", aid, ref=num,
                  desc=reason, location=location["location_name"] if location else "")
        a = self.acct(account_key)
        doc = {
            "inventory_adjustment_id": aid, "reference_number": num, "date": d.isoformat(), "reason": reason,
            "adjustment_type": "quantity", "account_id": a.account_id, "account_name": a.name,
            "line_items": [{"line_item_id": self.new_id("line"), "item_id": it["item_id"], "name": it["name"],
                            "quantity_adjusted": -q, "value_adjusted": -S(v)} for it, q, v in lines],
            "total": S(total), "_date": d,
        }
        self._loc(doc, location)
        self._stamp_doc(doc, d, "gl", self.rng.choice([1, 2, 3, 5]))
        self.docs["inventoryadjustments"].append(doc)
        return doc

    # ------------------------------------------------------------------ journals
    def journal(self, d: date, lines: list, notes: str, role: str = "gl", created_lag: int = 0, ref: str = "",
                kind: str = "", created_on: date = None) -> dict:
        """lines: (account key, signed amount (debit +), description[, location dict])."""
        lines = [(l[0], l[1], l[2], l[3] if len(l) > 3 else None) for l in lines if l[1]]
        if not lines:
            return None
        jid = self.new_id("journal")
        num = self.next_number("JV")
        self.post(d, [(k, a, loc["location_name"] if loc else "") for k, a, _, loc in lines], "journal", jid,
                  ref=num, desc=notes)
        doc = {
            "journal_id": jid, "entry_number": num, "journal_date": d.isoformat(), "reference_number": ref,
            "notes": notes, "journal_type": "both", "line_items": [],
            "total": S(sum(a for _, a, _, _ in lines if a > 0)), "_date": d, "_kind": kind,
        }
        for k, a, ds, loc in lines:
            li = {"line_id": self.new_id("line"), "account_id": self.acct(k).account_id,
                  "account_name": self.acct(k).name, "description": ds,
                  "debit_or_credit": "debit" if a > 0 else "credit", "amount": S(abs(a))}
            if loc:
                li["tags"] = self._tag(loc)
            doc["line_items"].append(li)
        self._stamp_doc(doc, d, role, created_lag)
        if created_on:
            doc["created_time"] = stamp(created_on, self.rng, hour_lo=19, hour_hi=23)
            doc["last_modified_time"] = doc["created_time"]
        self.docs["journals"].append(doc)
        return doc
