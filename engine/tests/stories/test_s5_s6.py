"""S5 (performance vs mix) and S6 (intercompany mismatch); identity by identifiers only (§12.17, R9, CK-09, CK-19)."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.ledger.intercompany import identify_group_contacts, match_intercompany
from txg.ledger.mix import performance_mix_split
from txg.ledger.statements import build_statements, ltm
from txg.normalise.trial_balance import rebuild_trial_balances


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def _answer_ic(answer_key: Path, company: str, month: str) -> dict[str, tuple[Decimal, Decimal]]:
    with open(answer_key / company / "intercompany_open.csv", encoding="utf-8", newline="") as f:
        return {r["counterparty_company"]: (Decimal(r["receivable_open_sar"]), Decimal(r["payable_open_sar"]))
                for r in csv.DictReader(f) if r["month"] == month}


def _name_resolver(contact: dict, company) -> tuple[bool, str]:
    """Labelled stand-in for the same-company reader (§9.9): judges on name evidence and records why."""
    same = company.name.casefold().removesuffix(" (made-up)") in contact["contact_name"].casefold()
    return same, f"name evidence: '{contact['contact_name']}' vs '{company.name}'"


def test_perf_mix_hand_example():
    """§18.2: A 100→200 at 8%→9%, B 100→100 at 30%→31%: performance +1.00 pt, mix −3.67 pts, total −2.67."""
    perf, mix = performance_mix_split(revenue0=[Decimal(100), Decimal(100)], revenue1=[Decimal(200), Decimal(100)],
                                      margin0=[Decimal("0.08"), Decimal("0.30")], margin1=[Decimal("0.09"), Decimal("0.31")])
    assert perf.quantize(Decimal("0.0001")) == Decimal("0.0100")
    assert mix.quantize(Decimal("0.0001")) == Decimal("-0.0367")


@pytest.mark.slow
def test_s5_division_margin_falls_while_each_rises(zoho_root: Path, answer_key: Path):
    conn = FileConnector(zoho_root)
    rev0, rev1, m0, m1 = [], [], [], []
    for company in ["EH-05", "EH-06", "EH-07"]:
        stmts = build_statements(rebuild_trial_balances(conn, company), _truth(answer_key, company))
        for month, revs, margins in (("2025-10", rev0, m0), ("2026-10", rev1, m1)):
            revenue, gross = ltm(stmts, month, "revenue"), ltm(stmts, month, "gross_profit")
            revs.append(revenue)
            margins.append(gross / revenue)
    assert all(b > a for a, b in zip(m0, m1))  # every company's gross margin rises
    perf, mix = performance_mix_split(rev0, rev1, m0, m1)
    assert perf > 0 and mix < 0 and perf + mix < 0  # …and the division's falls (21.41% → 21.15%)


@pytest.mark.slow
def test_s6_mismatch_is_1_10m(zoho_root: Path, answer_key: Path):
    conn = FileConnector(zoho_root)
    pairs, _ = match_intercompany(conn, ["EH-02", "EH-05"], "2026-10", resolver=_name_resolver)
    pair = next(p for p in pairs if {p.creditor, p.debtor} == {"EH-05", "EH-02"})
    assert pair.creditor == "EH-05" and pair.debtor == "EH-02"
    assert pair.receivable == _answer_ic(answer_key, "EH-05", "2026-10")["EH-02"][0]
    assert pair.payable == _answer_ic(answer_key, "EH-02", "2026-10")["EH-05"][1]
    assert (pair.difference / Decimal(1_000_000)).quantize(Decimal("0.01")) == Decimal("1.10")  # SAR 1.10m


@pytest.mark.slow
def test_identifier_disagreement_is_reported_ck19(zoho_root: Path):
    """Client-data finding: a contact for a group company carries identifiers that differ from that company's own."""
    conn = FileConnector(zoho_root)
    _, findings = identify_group_contacts(conn, "EH-02", conn.organisations(), resolver=_name_resolver)
    eh05 = [f for f in findings if f.check == "CK-19" and "EH-05" in f.detail]
    assert eh05 and "TEST-VAT-050000" in eh05[0].detail


def test_intercompany_matched_by_identifiers_not_names():
    from txg.connector.base import OrgRef
    group = [OrgRef("EH-05", "700000005", "Example Building Materials A Co. (made-up)", "SAR", "Asia/Riyadh", 0,
                    "TEST-VAT-0005", "TEST-CR-0005")]
    contacts = [
        {"contact_id": "1", "contact_name": "Totally Different Name", "tax_reg_no": "TEST-VAT-0005", "custom_fields": []},
        {"contact_id": "2", "contact_name": "Example Building Materials A Co. (made-up)", "tax_reg_no": "X-1",
         "custom_fields": [{"label": "CR Number", "value": "X-CR"}]},
    ]
    from txg.ledger.intercompany import classify_contacts
    never = lambda contact, company: (False, "reader: different company")
    matches, _ = classify_contacts("EH-02", contacts, group, resolver=never)
    assert matches == {"1": "EH-05"}  # identifier match wins; the namesake is not matched by code
