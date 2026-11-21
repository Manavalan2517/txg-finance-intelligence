"""Replay the Example Holding change feed.

    python3 replay.py base --data data/zoho --feed feed/changes.jsonl --out live
        Builds the state before the feed: the delivered files minus every record the feed creates (part A),
        with the general ledger and bank lines of those records removed.

    python3 replay.py play --feed feed/changes.jsonl --live live [--speed 0] [--post URL] [--upto SEQ]
        Applies the events in order to the files in `live`. With --post, each event is also sent as JSON to URL
        (for example the engine's connector). --speed N replays N times faster than the timestamps (0 = no
        waiting; each wait is capped at 2 seconds).

Standard library only.
"""
import argparse
import csv
import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime

KEYS = {"contacts": "contact_id", "projects": "project_id", "invoices": "invoice_id", "creditnotes": "creditnote_id",
        "customerpayments": "payment_id", "salesreceipts": "sales_receipt_id", "purchaseorders": "purchaseorder_id",
        "bills": "bill_id", "vendorpayments": "payment_id", "expenses": "expense_id",
        "inventoryadjustments": "inventory_adjustment_id", "journals": "journal_id"}


def read_events(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_list(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    key = next(k for k, v in obj.items() if isinstance(v, list))
    return key, obj[key]


def write_list(path, key, recs):
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"code": 0, "message": "success", "' + key + '": [\n')
        for i, r in enumerate(recs):
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + (",\n" if i < len(recs) - 1 else "\n"))
        f.write("]}\n")


def base(a):
    events = read_events(a.feed)
    created = {}
    for e in events:
        if e["part"] == "A" and e["op"] == "create":
            created.setdefault(e["company"], set()).add(e["id"])
    for company in sorted(os.listdir(a.data)):
        src, dst = os.path.join(a.data, company), os.path.join(a.out, company)
        if not os.path.isdir(src):
            continue
        os.makedirs(dst, exist_ok=True)
        gone = created.get(company, set())
        for fn in os.listdir(src):
            p = os.path.join(src, fn)
            if fn == "account_transactions.csv":
                with open(p, encoding="utf-8") as f, open(os.path.join(dst, fn), "w", encoding="utf-8", newline="") as g:
                    r, w = csv.reader(f), csv.writer(g)
                    head = next(r)
                    w.writerow(head)
                    ti = head.index("transaction_id")
                    for row in r:
                        if row[ti] not in gone:
                            w.writerow(row)
            elif fn == "banktransactions.json":
                key, recs = load_list(p)
                write_list(os.path.join(dst, fn), key, [x for x in recs if x["transaction_id"][3:].rsplit("-", 1)[0] not in gone])
            elif fn.endswith(".json") and fn[:-5] in KEYS:
                key, recs = load_list(p)
                write_list(os.path.join(dst, fn), key, [x for x in recs if x[KEYS[fn[:-5]]] not in gone])
            else:
                shutil.copy2(p, os.path.join(dst, fn))
        print(f"{company}: {len(gone)} records held back for the feed")


def play(a):
    events = read_events(a.feed)
    store, gl, bank = {}, {}, {}

    def lst(company, t):
        k = (company, t)
        if k not in store:
            p = os.path.join(a.live, company, f"{t}.json")
            store[k] = load_list(p) if os.path.exists(p) else (t, [])
        return store[k][1]

    def ledger(company):
        if company not in gl:
            with open(os.path.join(a.live, company, "account_transactions.csv"), encoding="utf-8") as f:
                r = csv.DictReader(f)
                gl[company] = (r.fieldnames, list(r))
        return gl[company]

    prev = None
    for e in events:
        if a.upto and e["seq"] > a.upto:
            break
        if a.speed and prev:
            gap = (datetime.strptime(e["ts"], "%Y-%m-%dT%H:%M:%S%z") - prev).total_seconds() / a.speed
            time.sleep(min(2.0, max(0.0, gap)))
        prev = datetime.strptime(e["ts"], "%Y-%m-%dT%H:%M:%S%z")
        c, t = e["company"], e["record_type"]
        if e["op"] in ("create", "update"):
            recs = lst(c, t)
            k = KEYS[t]
            recs[:] = [x for x in recs if x[k] != e["id"]] + [e["record"]]
            head, rows = ledger(c)
            if e.get("postings") is not None:
                rows[:] = [x for x in rows if x["transaction_id"] != e["id"]] + e["postings"]
            if e.get("bank_lines"):
                bank.setdefault(c, []).extend(e["bank_lines"])
        elif e["op"] == "upload":
            dst = os.path.join(a.live, c, "uploads")
            os.makedirs(dst, exist_ok=True)
            src = os.path.join(a.root, e["file"])
            if os.path.exists(src):
                shutil.copy2(src, dst)
        print(f"{e['seq']:>5} {e['ts']} {c} {e['op']:<6} {t:<16} {e['id']}  {e.get('why', '')}")
        if a.post:
            req = urllib.request.Request(a.post, data=json.dumps(e).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
    for (c, t), (key, recs) in store.items():
        write_list(os.path.join(a.live, c, f"{t}.json"), key, recs)
    for c, (head, rows) in gl.items():
        with open(os.path.join(a.live, c, "account_transactions.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=head)
            w.writeheader()
            w.writerows(rows)
    for c, lines in bank.items():
        p = os.path.join(a.live, c, "banktransactions.json")
        key, recs = load_list(p)
        write_list(p, key, recs + lines)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("base")
    b.add_argument("--data", required=True)
    b.add_argument("--feed", required=True)
    b.add_argument("--out", required=True)
    p = sub.add_parser("play")
    p.add_argument("--feed", required=True)
    p.add_argument("--live", required=True)
    p.add_argument("--root", default=".", help="folder that holds uploads/ (for upload events)")
    p.add_argument("--speed", type=float, default=0)
    p.add_argument("--post", default="")
    p.add_argument("--upto", type=int, default=0)
    a = ap.parse_args()
    base(a) if a.cmd == "base" else play(a)


if __name__ == "__main__":
    sys.exit(main())
