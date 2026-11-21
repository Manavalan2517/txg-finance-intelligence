"""Generate Example Holding: Zoho-format books, the answer key and the validation report.

    python3 generate.py                       # every company in config/group.json
    python3 generate.py --companies EH-01,EH-08 --out out

Standard library only (Python 3.9 or later). The same configuration gives byte-identical files.
"""
import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eh.acquisition import build_acquisition  # noqa: E402
from eh.export import export_company  # noqa: E402
from eh.feed import build_feed  # noqa: E402
from eh.uploads import build_uploads  # noqa: E402
from eh.quicklook import quick_look  # noqa: E402
from eh.sectors.contracting import ContractingSim  # noqa: E402
from eh.sectors.distribution import DistributionSim  # noqa: E402
from eh.sectors.retail import RetailSim  # noqa: E402
from eh.truth import build_truth  # noqa: E402
from eh.validate import validate_company, validate_uploads  # noqa: E402

SIMS = {"contracting": ContractingSim, "distribution": DistributionSim, "retail": RetailSim}


def group_checks(out, codes):
    """Checks that need more than one company: the S5 mix effect and the S6 intercompany mismatch."""
    import csv
    lines = []

    def kpis(code):
        with open(os.path.join(out, "answer-key", code, "kpis_monthly.csv"), encoding="utf-8") as f:
            return {r["month"]: r for r in csv.DictReader(f)}
    div = [c for c in ("EH-05", "EH-06", "EH-07") if c in codes]
    if len(div) == 3:
        def ltm(code, month):
            R = kpis(code)
            y, m = int(month[:4]), int(month[5:7])
            ms = []
            for _ in range(12):
                ms.append(f"{y}-{m:02d}")
                y, m = (y, m - 1) if m > 1 else (y - 1, 12)
            rev = sum(float(R[x]["revenue"]) for x in ms)
            gm = float(R[month]["PF-1_gross_margin_ltm"])
            return rev, gm
        rows, ok_each = [], True
        tot = {}
        for when in ("2025-10", "2026-10"):
            r_ = [ltm(c, when) for c in div]
            tot[when] = sum(rv * gm for rv, gm in r_) / sum(rv for rv, _ in r_)
        for c in div:
            (rv0, g0), (rv1, g1) = ltm(c, "2025-10"), ltm(c, "2026-10")
            ok_each &= g1 > g0
            rows.append(f"{c} {g0 * 100:.1f}% → {g1 * 100:.1f}% on revenue {rv0 / 1e6:.0f}m → {rv1 / 1e6:.0f}m")
        ok = ok_each and tot["2026-10"] < tot["2025-10"]
        lines += ["## Group checks", "", "| Check | Result | Detail |", "|---|---|---|",
                  f"| S5: every trading company's gross margin rises, the division's falls (last 12 months, Oct 2025 → Oct 2026) "
                  f"| {'PASS' if ok else 'FAIL'} | {'; '.join(rows)}; division {tot['2025-10'] * 100:.2f}% → {tot['2026-10'] * 100:.2f}% |"]
    if "EH-05" in codes and "EH-02" in codes:
        def ic(code, other, month):
            with open(os.path.join(out, "answer-key", code, "intercompany_open.csv"), encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["month"] == month and r["counterparty_company"] == other:
                        return float(r["receivable_open_sar"]), float(r["payable_open_sar"])
            return 0.0, 0.0
        rec, _ = ic("EH-05", "EH-02", "2026-10")
        _, pay = ic("EH-02", "EH-05", "2026-10")
        if not lines:
            lines += ["## Group checks", "", "| Check | Result | Detail |", "|---|---|---|"]
        lines.append(f"| S6: EH-05's receivable from EH-02 exceeds EH-02's payable to EH-05 by one unbooked invoice (31 Oct 2026) "
                     f"| {'PASS' if 0.9e6 < rec - pay < 1.3e6 else 'FAIL'} | EH-05 SAR {rec / 1e6:.2f}m, EH-02 SAR {pay / 1e6:.2f}m, "
                     f"difference SAR {(rec - pay) / 1e6:.2f}m |")
    return lines + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/group.json")
    ap.add_argument("--companies", default="")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    want = [x.strip() for x in a.companies.split(",") if x.strip()]
    report = ["# Example Holding – validation report", "",
              f"Generator {cfg['generator_version']} · data from {cfg['go_live']} to {cfg['data_end']} "
              f"(warm-up from {cfg['sim_start']}, not exported) · every figure made up.", ""]
    summary = {}
    for c in cfg["companies"]:
        if want and c["code"] not in want:
            continue
        t = time.time()
        sim = SIMS[c["sector"]](c, cfg).run()
        zdir = os.path.join(a.out, "zoho", c["code"])
        tdir = os.path.join(a.out, "answer-key", c["code"])
        man = export_company(sim, zdir)
        rows = build_truth(sim, tdir)
        udir = os.path.join(a.out, "uploads", c["code"])
        up = build_uploads(sim, rows, udir, tdir)
        checks = validate_company(sim, zdir, rows) + validate_uploads(sim, zdir, udir, up)
        with open(os.path.join(tdir, "validation.json"), "w", encoding="utf-8") as f:
            json.dump(checks, f, indent=1, ensure_ascii=False)
        npass = sum(1 for x in checks if x["result"] == "PASS")
        report += [f"## {c['code']} {c['name']}", "", f"{npass} of {len(checks)} checks pass.", "",
                   "| Check | Result | Detail |", "|---|---|---|"]
        report += [f"| {x['check']} | {x['result']} | {x['detail']} |" for x in checks]
        if sim.warnings:
            report += ["", "Generator warnings: " + "; ".join(sim.warnings[:10])]
        report.append("")
        summary[c["code"]] = {"checks_passed": npass, "checks": len(checks), "counts": man["counts"],
                              "seconds": round(time.time() - t, 1)}
        print(f"{c['code']}: {npass}/{len(checks)} checks pass, {sum(man['counts'].values()):,} records, "
              f"{time.time() - t:.1f}s", flush=True)
    os.makedirs(a.out, exist_ok=True)
    report += group_checks(a.out, list(summary))
    events = build_feed(a.out, cfg, list(summary))
    acq = build_acquisition(a.out, os.path.join(a.out, "answer-key", "acquisition"))
    report += ["## Change feed and acquisition data", "",
               f"- Change feed: {len(events)} events ({sum(1 for e in events if e['part'] == 'A')} replaying activity from "
               f"1 November 2026, {sum(1 for e in events if e['part'] == 'B')} live edits after the data end).",
               "- Target statements: " + "; ".join(f"FY{x['year']} balance sheet {'balances' if x['balance_sheet_balances'] else 'DOES NOT BALANCE'}, "
                                                  f"cash flow {'ties' if x['cash_flow_ties'] else 'DOES NOT TIE'}, cash SAR {x['cash'] / 1e6:.1f}m"
                                                  for x in acq), ""]
    with open(os.path.join(a.out, "validation_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    quick_look(a.out, cfg, list(summary))
    hashes = {}
    for root, _, files in os.walk(a.out):
        for fn in sorted(files):
            pth = os.path.join(root, fn)
            if fn in ("hashes.json",):
                continue
            with open(pth, "rb") as f:
                hashes[os.path.relpath(pth, a.out)] = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(a.out, "hashes.json"), "w", encoding="utf-8") as f:
        json.dump(dict(sorted(hashes.items())), f, indent=1)
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
