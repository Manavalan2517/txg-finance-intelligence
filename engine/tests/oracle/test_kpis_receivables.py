"""Task C1 (part 2): receivables, payables, inventory and concentration KPIs against the answer key (§11.2, §12.10)."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.kpi.context import build_context
from txg.kpi.facts import build_month_facts, retention_from_notes
from txg.kpi.registry import compute_all
from txg.normalise.trial_balance import rebuild_trial_balances

COMPANIES = ["EH-01", "EH-02", "EH-03", "EH-05", "EH-06", "EH-07", "EH-08", "EH-09", "EH-14", "EH-21"]
ORACLE = {
    "retention_receivable_held": "retention_held",
    "RC-1_dso_3m": "RC-1",
    "RC-1_best_dso_3m": "RC-1_best",
    "RC-1_days_late_3m": "RC-1_days_late",
    "RC-1_dso_excl_retention_3m": "RC-1_excl_retention",
    "RC-2_over90_share": "RC-2",
    "RC-3_collection_effectiveness_m": "RC-3",
    "CS-3_inventory_days_3m": "CS-3",
    "PY-2_dpo_3m": "PY-2_dpo",
    "PY-2_overdue_share": "PY-2",
    "HL-6_cash_conversion_cycle": "HL-6",
    "RC-5_top_customer_share_ltm": "RC-5_top1",
    "RC-5_top5_share_ltm": "RC-5_top5",
    "RC-5_effective_number_of_customers_ltm": "RC-5",
}
MONEY = {"retention_receivable_held"}
CONTRACTORS = {"EH-01", "EH-02", "EH-03"}


def _tolerance(company: str, column: str, want: Decimal) -> Decimal:
    """Exact (answer-key rounding) everywhere, with three documented limits of what the books can show:
    - HL-6 sums three answer-key values that are each rounded to 4 dp before adding.
    - Subcontractor retention becomes payable at handover, before it is paid; the books show only the payment,
      so supplier overdue share at contractors can differ in a few months (finding reported to the client).
    - Retention released before go-live is not in the books, so the go-live month's held retention is approximate.
    """
    if column == "HL-6_cash_conversion_cycle":
        return Decimal("0.0003")
    if company in CONTRACTORS and column == "PY-2_overdue_share":
        return Decimal("0.03")
    if column in MONEY:
        return max(Decimal("0.01"), abs(want) * Decimal("0.005")) if company in CONTRACTORS else Decimal("0.01")
    return Decimal("0.00011")


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def test_retention_stand_in_reads_invoice_and_bill_notes():
    assert retention_from_notes("Retention 10% (SAR 155,354.03) withheld per contract.", Decimal(1)) \
        == Decimal("155354.03")
    assert retention_from_notes("Retention 5% withheld (SAR 12,000.50).", Decimal(1)) == Decimal("12000.50")
    assert retention_from_notes("Migrated balance: retention withheld by the client on earlier certificates.",
                                Decimal(880000)) == Decimal(880000)
    assert retention_from_notes("", Decimal(500)) == Decimal(0)


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_receivable_kpis_match_answer_key(zoho_root: Path, answer_key: Path, company: str):
    conn = FileConnector(zoho_root)
    facts = build_month_facts(conn, company)
    ctx = build_context(company, rebuild_trial_balances(conn, company), _truth(answer_key, company), facts=facts)
    mismatches = {}
    with open(answer_key / company / "kpis_monthly.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        values = compute_all(ctx, row["month"])
        for column, kpi_id in ORACLE.items():
            want = row.get(column, "")
            if want == "":
                continue
            got = values[kpi_id].value
            tol = _tolerance(company, column, Decimal(want))
            if got is None or abs(got - Decimal(want)) > tol:
                mismatches.setdefault(column, []).append((row["month"], got, want))
    assert {k: v[:3] for k, v in mismatches.items()} == {}
