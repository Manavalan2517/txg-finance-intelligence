"""F-11 and F-12 (§18.3) on the facility-letter reader: a misread covenant is read again, then applied with a
"not verified" marker; a repayment schedule that does not sum is re-read from the balance column, and if it still
does not sum the schedule is not used and the facility carries a marker."""
import re
from decimal import Decimal
from pathlib import Path

import pytest

from txg.uploads.facility_reader import covenant_reading, pdf_pages, read_letter

LETTER = (Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20" / "uploads" / "EH-01"
          / "facility_letters" / "facility_letter_01_example_bank_a.pdf")


@pytest.fixture(scope="module")
def pages() -> list[str]:
    if not LETTER.is_file():
        pytest.skip("step-3 uploads not present")
    return pdf_pages(LETTER)


def _term_loan_1(letter: dict) -> dict:
    return next(f for f in letter["facilities"] if f["facility"].startswith("Term Loan 1"))


def test_a_clean_letter_is_read_without_markers(pages):
    letter = read_letter(pages, LETTER.name)
    assert letter["markers"] == []
    assert sum(Decimal(str(s["principal_sar"])) for s in _term_loan_1(letter)["schedule"]) == Decimal(75_000_000)
    leverage = next(c for c in letter["covenants"] if c["test"] == "net_debt_to_ebitda_max")
    assert leverage["threshold"] == 3.5 and leverage["verified"] is True and leverage["page"] == 2


def test_f11_a_misread_covenant_is_re_read_then_marked_not_verified(pages):
    def misreading(paragraphs, finding=None):  # a second reading that keeps reading leverage as 3.0
        return [c | {"threshold": 3.0} if c["test"] == "net_debt_to_ebitda_max" else c
                for c in covenant_reading(paragraphs)]
    letter = read_letter(pages, LETTER.name, second=misreading)
    leverage = next(c for c in letter["covenants"] if c["test"] == "net_debt_to_ebitda_max")
    assert leverage["threshold"] == 3.5 and leverage["verified"] is False  # applied, never waiting
    assert any("Leverage" in m and "not verified" in m for m in letter["markers"])
    dscr = next(c for c in letter["covenants"] if c["test"] == "dscr_min")
    assert dscr["verified"] is True


def _misread(pages: list[str], final_balance: str = "0") -> list[str]:
    """The first instalment misread as 3.0m; optionally the last balance too, so the balance column cannot repair it."""
    first = re.compile(r"^30 Jun 2021\s+3,750,000\s+71,250,000$", re.MULTILINE)
    last = re.compile(r"^31 Mar 2026\s+3,750,000\s+0$", re.MULTILINE)
    assert first.search(pages[0]) and last.search(pages[0])
    page = first.sub("30 Jun 2021                 3,000,000           71,250,000", pages[0])
    page = last.sub(f"31 Mar 2026                 3,750,000           {final_balance}", page)
    return [page, *pages[1:]]


def test_a_schedule_misread_is_re_read_from_the_balance_column(pages):
    letter = read_letter(_misread(pages), LETTER.name)
    schedule = _term_loan_1(letter)["schedule"]
    assert schedule[0]["principal_sar"] == 3_750_000 and letter["markers"] == []


def test_f12_a_schedule_that_does_not_sum_falls_back_with_a_marker(pages):
    letter = read_letter(_misread(pages, final_balance="750,000"), LETTER.name)
    loan = _term_loan_1(letter)
    assert loan["schedule"] == [] and loan["schedule_verified"] is False
    assert any("Term Loan 1" in m and "CK-11" in m and "ledger balance" in m for m in letter["markers"])
