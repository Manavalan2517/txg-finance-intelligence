"""QUICK_LOOK.md: the headline numbers of each generated company, read from the answer key.

Every figure here is computed from answer-key/<code>/kpis_monthly.csv (itself computed from the books), so
the summary can never drift from the data.
"""
import csv
import json
import os


def _rows(out, code):
    with open(os.path.join(out, "answer-key", code, "kpis_monthly.csv"), encoding="utf-8") as f:
        return {r["month"]: r for r in csv.DictReader(f)}


def _f(r, k):
    v = (r or {}).get(k)
    return None if v in (None, "") else float(v)


def _m(v):
    return "–" if v is None else f"{v / 1e6:,.1f}m"


def _p(v, d=1):
    return "–" if v is None else f"{v * 100:.{d}f}%"


def _x(v, d=1):
    return "–" if v is None else f"{v:.{d}f}"


def quick_look(out, cfg, codes):
    lines = ["# Example Holding – quick look", "",
             f"{len(codes)} companies, books from 1 January 2023 to 19 November 2026 (November open). "
             "Every figure below is computed from the generated books; nothing is typed. All names and numbers are made up.",
             ""]
    comp = {c["code"]: c for c in cfg["companies"]}
    for code in codes:
        c = comp[code]
        R = _rows(out, code)
        man = json.load(open(os.path.join(out, "zoho", code, "manifest.json"), encoding="utf-8"))
        val = json.load(open(os.path.join(out, "answer-key", code, "validation.json"), encoding="utf-8"))
        yrs = {}
        for y in (2023, 2024, 2025, 2026):
            v = [_f(R.get(f"{y}-{m:02d}"), "revenue") for m in range(1, 13 if y < 2026 else 11)]
            yrs[y] = sum(x for x in v if x is not None)
        lines += [f"## {code} {c['name']}", "",
                  f"Chart of accounts layout {c['coa_variant']} · {sum(man['counts'].values()):,} records · "
                  f"{sum(1 for x in val if x['result'] == 'PASS')} of {len(val)} checks pass.", "",
                  "| | 2023 | 2024 | 2025 | 2026 (Jan–Oct) |", "|---|---|---|---|---|",
                  f"| Revenue (SAR) | {_m(yrs[2023])} | {_m(yrs[2024])} | {_m(yrs[2025])} | {_m(yrs[2026])} |",
                  "| EBITDA margin, last 12 months (Dec; Oct for 2026) | " + " | ".join(
                      _p(_f(R.get(m), "HL-3_ebitda_margin_ltm")) for m in ("2023-12", "2024-12", "2025-12", "2026-10")) + " |",
                  "| Gross margin, last 12 months | " + " | ".join(
                      _p(_f(R.get(m), "PF-1_gross_margin_ltm")) for m in ("2023-12", "2024-12", "2025-12", "2026-10")) + " |",
                  ""]
        if code == "EH-01":
            def avg(y, k):
                v = [_f(R.get(f"{y}-{m:02d}"), k) for m in range(1, 11)]
                v = [x for x in v if x is not None]
                return sum(v) / len(v)
            liq26 = min(_f(R.get(f"2026-{m:02d}"), "liquidity_cash_plus_undrawn") for m in range(1, 11))
            lines += ["**S1 and S9 (government customers pay later from January 2026)**", "",
                      "| Measure | 2025 | 2026 |", "|---|---|---|",
                      f"| Days late (3-month basis), average Jan–Oct | {_x(avg(2025, 'RC-1_days_late_3m'))} | {_x(avg(2026, 'RC-1_days_late_3m'))} |",
                      f"| DSO (3-month basis), October | {_x(_f(R.get('2025-10'), 'RC-1_dso_3m'))} | {_x(_f(R.get('2026-10'), 'RC-1_dso_3m'))} |",
                      f"| Cash conversion (cash from operations ÷ EBITDA, 12 months), October | {_x(_f(R.get('2025-10'), 'HL-5_cash_conversion_ltm'), 2)} | {_x(_f(R.get('2026-10'), 'HL-5_cash_conversion_ltm'), 2)} |",
                      f"| Cash plus undrawn facility, October 2025 vs lowest month-end of 2026 | {_m(_f(R.get('2025-10'), 'liquidity_cash_plus_undrawn'))} | {_m(liq26)} |",
                      f"| Net debt ÷ EBITDA (12 months), October | {_x(_f(R.get('2025-10'), 'HL-8_net_debt_to_ebitda_excl_leases'), 2)} | {_x(_f(R.get('2026-10'), 'HL-8_net_debt_to_ebitda_excl_leases'), 2)} |",
                      ""]
        if code == "EH-08":
            eur = [_f(r, "TRD-6_purchases_outside_dollar_m") for r in R.values() if _f(r, "TRD-6_purchases_outside_dollar_m") is not None]
            lines += ["**S2 (purchase prices of 60% of items +4.1% from October 2025, selling prices +1.2%)**", "",
                      "| Measure | Sep 2025 | Oct 2026 |", "|---|---|---|",
                      f"| Gross margin, last 12 months | {_p(_f(R.get('2025-09'), 'PF-1_gross_margin_ltm'))} | {_p(_f(R.get('2026-10'), 'PF-1_gross_margin_ltm'))} |",
                      f"| EBITDA margin, last 12 months | {_p(_f(R.get('2025-09'), 'HL-3_ebitda_margin_ltm'))} | {_p(_f(R.get('2026-10'), 'HL-3_ebitda_margin_ltm'))} |",
                      f"| Price realisation (invoiced ÷ list price), month | {_p(_f(R.get('2025-09'), 'TRD-5_price_realisation_m'))} | {_p(_f(R.get('2026-10'), 'TRD-5_price_realisation_m'))} |",
                      "", f"Stock purchases in euros: {_p(sum(eur) / len(eur))} on average (monthly range {_p(min(eur), 0)}–{_p(max(eur), 0)}). "
                      "Part of the margin fall is the euro's rise in 2025, which the engine should separate from the price change. "
                      "S11 (budgets too high) arrives with the budget files in step 3.", ""]
        if code == "EH-14":
            sales = {}
            with open(os.path.join(out, "answer-key", code, "store_sales_monthly.csv"), encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    sales[r["month"]] = sales.get(r["month"], 0) + float(r["sales_incl_vat_sar"])
            ch = sales["2026-03"] / sales["2025-03"] - 1
            lines += ["**S4 (normal Ramadan effect; nine new stores in 2025 with weak returns)**", "",
                      "| Measure | Value |", "|---|---|",
                      f"| March 2026 sales vs March 2025 | {ch * 100:+.1f}% |",
                      f"| February 2026 sales vs February 2025 | {(sales['2026-02'] / sales['2025-02'] - 1) * 100:+.1f}% |",
                      f"| March 2026 like-for-like, raw | {_p(_f(R.get('2026-03'), 'RET-1_like_for_like_raw_m'))} |",
                      f"| March 2026 like-for-like, holiday effect removed (true effect) | {_p(_f(R.get('2026-03'), 'RET-1_like_for_like_holiday_adjusted_true_m'))} |",
                      f"| Return on invested capital, last 12 months, Dec 2024 → Oct 2026 | {_p(_f(R.get('2024-12'), 'HL-4_roic_ltm'))} → {_p(_f(R.get('2026-10'), 'HL-4_roic_ltm'))} |",
                      ""]
        if code not in ("EH-01", "EH-08", "EH-14"):
            st = [x for x in val if x["check"].startswith("S")]
            if st:
                lines += ["**Stories**", "", "| Check | Result | Measured |", "|---|---|---|"]
                lines += [f"| {x['check']} | {x['result']} | {x['detail']} |" for x in st]
                lines.append("")
    rep = open(os.path.join(out, "validation_report.md"), encoding="utf-8").read()
    if "## Group checks" in rep:
        lines += ["## Across companies", ""] + rep.split("## Group checks", 1)[1].strip().splitlines() + [""]
    with open(os.path.join(out, "QUICK_LOOK.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
