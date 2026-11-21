"""Facility letters read from the PDFs (§9.5, Appendix D.6). Code extracts the text (pypdf); a labelled stand-in
reader finds the terms in it, in place of the model, until recorded model readings exist. Every reading is checked
by code: repayment schedules must sum to the principal and run in date order (CK-11), and covenants are read twice.

- A schedule that does not sum is re-read from the balance column; if it still does not, the schedule is not used
  and the facility carries a marker (F-12): the ledger balance stands, with no scheduled repayments projected.
- Two covenant readings that disagree trigger one re-read with the finding; if they still disagree, the first
  reading is applied with a "not verified" marker (F-11). Nothing waits for a person.
"""
import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from pypdf import PdfReader

from txg.uploads.facilities import Covenant, FacilityTerms

FOOTER = "Made-up example"
TABLE_ROW = re.compile(r"^(Term Loan(?: \d)?|Revolving credit facility)\s{2,}(.+?)\s{2,}([\d,]+)\s+(\d{1,2} \w{3} \d{4})$")
PRICING = re.compile(r"^(Term Loan(?: \d)?|Revolving credit facility): interest at three-month SAIBOR plus ([\d.]+)%")
REPAYMENT = re.compile(r"^\d+(?:\.\d*)?\s+Repayment – (.+)$")
DRAWN = re.compile(r"^Drawn in full on (\d{1,2} \w+ \d{4})")
INSTALMENT = re.compile(r"^(\d{1,2} \w{3} \d{4})\s+([\d,]+)\s+([\d,]+)$")
HEADING = re.compile(r"^\d+\.(?:\d+)?\s+[A-Z]")
COVENANT = re.compile(r"^\d+\.\d+ ([A-Z][a-z]+(?: [a-z]+)?)\. (.*)$")
TERMS = {"Leverage": ("Leverage", "net_debt_to_ebitda_max", r"does not exceed\s+([\d.]+)\s+times"),
         "Debt service": ("Debt service cover", "dscr_min", r"at least\s+([\d.]+)\s+times\s+Debt Service"),
         "Interest cover": ("Interest cover", "interest_cover_min", r"at least\s+([\d.]+)\s+times"),
         "Minimum liquidity": ("Minimum liquidity", "cash_plus_undrawn_min", r"less than SAR\s+([\d,]+)")}
Reader = Callable[..., list[dict]]


def pdf_pages(path: Path) -> list[str]:
    return [page.extract_text() or "" for page in PdfReader(str(path)).pages]


def _date(text: str) -> date:
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"not a date: {text!r}")


def _amount(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def _lines(pages: list[str]) -> list[tuple[int, str]]:
    return [(i, ln.strip()) for i, page in enumerate(pages, start=1) for ln in page.splitlines()
            if ln.strip() and not ln.strip().startswith(FOOTER)]


def _section(lines: list[tuple[int, str]], title: str) -> list[tuple[int, str]]:
    start = next((k for k, (_, ln) in enumerate(lines) if re.match(rf"^\d+\.\s+{title}$", ln)), None)
    if start is None:
        return []
    end = next((k for k in range(start + 1, len(lines)) if re.match(r"^\d+\.\s+[A-Z]", lines[k][1])), len(lines))
    return lines[start + 1:end]


def covenant_paragraphs(lines: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """(page, title, text) for each numbered paragraph of the financial covenants section."""
    out: list[tuple[int, str, str]] = []
    for page, ln in _section(lines, "Financial covenants"):
        if m := COVENANT.match(ln):
            out.append((page, m.group(1), m.group(2)))
        elif out:
            out[-1] = (out[-1][0], out[-1][1], f"{out[-1][2]} {ln}")
    return out


def covenant_reading(paragraphs: list[tuple[int, str, str]], finding: str | None = None) -> list[dict]:
    """First reading (stand-in): the covenant named by each paragraph title, its threshold from the operative words."""
    out = []
    for page, title, text in paragraphs:
        if title not in TERMS:
            continue
        name, test, pattern = TERMS[title]
        if (m := re.search(pattern, text)) is None:
            continue
        frequency = "at all times" if "at any time" in text else "quarterly, last twelve months"
        out.append({"name": name, "test": test, "threshold": float(_amount(m.group(1))), "frequency": frequency,
                    "page": page, "quote": text})
    return out


def covenant_second_reading(paragraphs: list[tuple[int, str, str]], finding: str | None = None) -> list[dict]:
    """Second, independent reading (stand-in): the kind of test from the defined terms used, the threshold as the
    first figure in the paragraph. It never sees the first reading."""
    out = []
    for _page, _title, text in paragraphs:
        kind = ("dscr_min" if "Debt Service" in text else "interest_cover_min" if "Finance" in text else
                "cash_plus_undrawn_min" if "SAR" in text else "net_debt_to_ebitda_max" if "Net Debt" in text else None)
        figure = re.search(r"(\d[\d,]*(?:\.\d+)?)", text)
        if kind and figure:
            out.append({"test": kind, "threshold": float(_amount(figure.group(1)))})
    return out


def _covenants(paragraphs, first: Reader, second: Reader, markers: list[str]) -> list[dict]:
    seconds = {c["test"]: c["threshold"] for c in second(paragraphs)}
    out = []
    for c in first(paragraphs):
        if seconds.get(c["test"]) == c["threshold"]:
            out.append(c | {"verified": True})
            continue
        finding = f"{c['name']}: readings {c['threshold']} and {seconds.get(c['test'])} disagree"
        again = next((r for r in first(paragraphs, finding=finding) if r["test"] == c["test"]), c)
        if seconds.get(c["test"]) == again["threshold"]:
            out.append(again | {"verified": True})
        else:
            out.append(c | {"verified": False})
            markers.append(f"{c['name']} covenant not verified ({finding}); the first reading is applied (F-11)")
    return out


def _schedule(name: str, amount: Decimal, rows: list[tuple[date, Decimal, Decimal]], markers: list[str]):
    """CK-11 on the principal column; else re-read from the balance column; else no schedule, with a marker."""
    def ok(principals: list[Decimal]) -> bool:
        dates = [d for d, _, _ in rows]
        return bool(rows) and sum(principals) == amount and all(p > 0 for p in principals) and dates == sorted(dates)

    principals = [p for _, p, _ in rows]
    if not ok(principals):
        balances = [amount, *(b for _, _, b in rows)]
        principals = [a - b for a, b in pairwise(balances)]
        if not ok(principals):
            markers.append(f"{name}: repayment schedule not verified (CK-11); the ledger balance is used and no "
                           "scheduled repayments are projected (F-12)")
            return [], False
    return [{"date": d.isoformat(), "principal_sar": float(p)} for (d, _, _), p in zip(rows, principals)], True


def _repayments(lines: list[tuple[int, str]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    current = None
    for _, ln in lines:
        if m := REPAYMENT.match(ln):
            current = out.setdefault(m.group(1), {"drawn": None, "rows": []})
        elif current is not None and (m := DRAWN.match(ln)):
            current["drawn"] = _date(m.group(1))
        elif current is not None and (m := INSTALMENT.match(ln)):
            current["rows"].append((_date(m.group(1)), _amount(m.group(2)), _amount(m.group(3))))
        elif HEADING.match(ln):
            current = None
    return out


def _definitions(lines: list[tuple[int, str]]) -> dict:
    text = " ".join(ln for _, ln in _section(lines, "Definitions"))
    ebitda = re.search(r'"EBITDA" means,? (.*?)(?= - "|$)', text)
    net_debt = re.search(r'"Net Debt" means,? (.*?)(?= - "|$)', text)
    cfads = re.search(r'"Cash Flow Available for Debt Service" means (.*?) (?:during|for) ', text)
    return {"ebitda_before_ifrs16": bool(ebitda and "IFRS 16" in ebitda.group(1) and "not been applied" in ebitda.group(1)),
            "lease_liabilities_in_net_debt": bool(net_debt and "excluding lease liabilities" not in net_debt.group(1)),
            "cfads": cfads.group(1) if cfads else ""}


def _facilities(lines, lender_short: str, markers: list[str]) -> list[dict]:
    margins = {m.group(1): float(Decimal(m.group(2)) / 100) for _, ln in lines if (m := PRICING.match(ln))}
    repayments = _repayments(lines)
    out = []
    for _, ln in lines:
        if (m := TABLE_ROW.match(ln)) is None:
            continue
        name, kind, amount, maturity = m.group(1), m.group(2), _amount(m.group(3)), _date(m.group(4))
        if "revolving" in kind.lower():
            out.append({"facility": name, "type": "rcf", "limit_sar": float(amount), "margin_over_saibor":
                        margins.get(name), "available_until": maturity.isoformat(), "schedule": []})
            continue
        full = f"{name} – {lender_short}"
        rep = repayments.get(name, {"drawn": None, "rows": []})
        schedule, verified = _schedule(full, amount, rep["rows"], markers)
        out.append({"facility": full, "type": "term_loan", "amount_sar": float(amount),
                    "drawn": rep["drawn"].isoformat() if rep["drawn"] else None, "margin_over_saibor": margins.get(name),
                    "maturity": maturity.isoformat(), "schedule": schedule, "schedule_verified": verified})
    return out


def read_letter(pages: list[str], file: str, first: Reader = covenant_reading,
                second: Reader = covenant_second_reading) -> dict:
    lines = _lines(pages)
    lender = lines[0][1]
    head = " ".join(ln for _, ln in lines[:6])
    ref = re.search(r"Ref: (\S+)", head)
    dated = re.search(r"Date: (\d{1,2} \w+ \d{4})", head)
    markers: list[str] = []
    return {"file": file, "lender": lender, "reference": ref.group(1) if ref else "",
            "dated": _date(dated.group(1)).isoformat() if dated else None,
            "facilities": _facilities(lines, lender.removesuffix(" (made-up)"), markers),
            "covenants": _covenants(covenant_paragraphs(lines), first, second, markers),
            "definitions": _definitions(lines), "markers": markers}


def load_facility_letters(folder: Path) -> FacilityTerms:
    facilities, covenants, definitions, markers, seen = [], [], {}, [], set()
    for path in sorted(folder.glob("*.pdf")):
        letter = read_letter(pdf_pages(path), path.name)
        facilities += letter["facilities"]
        for c in letter["covenants"]:
            if (c["name"], c["test"]) not in seen:
                seen.add((c["name"], c["test"]))
                covenants.append(Covenant(c["name"], c["test"], Decimal(str(c["threshold"])), c["frequency"]))
        definitions.update(letter["definitions"])
        markers += [f"{path.name}: {m}" for m in letter["markers"]]
    return FacilityTerms(tuple(facilities), tuple(covenants), definitions,
                         source="facility letters (PDF), read by the stand-in reader", markers=tuple(markers))
