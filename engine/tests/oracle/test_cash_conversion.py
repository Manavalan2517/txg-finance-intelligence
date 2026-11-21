"""HL-5 cash conversion and CS-1 free cash flow (§11.1, §11.2.3) against the answer key.

Cash from operations is built with the direct method: every cash posting is classed by the standard codes on the
other side of its transaction (vendor payments by the bills they settle). Same rule for every company (R2)."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.kpi.cashflow import build_cash_flows
from txg.kpi.context import build_context
from txg.kpi.registry import compute_all
from txg.normalise.trial_balance import rebuild_trial_balances

COMPANIES = ["EH-01", "EH-02", "EH-03", "EH-05", "EH-06", "EH-07", "EH-08", "EH-09", "EH-14", "EH-21"]
MONEY = {"cash_from_operations_pre_interest_zakat_ltm": "CFO_pre_interest_zakat", "CS-1_free_cash_flow_ltm": "CS-1"}
RATIO = {"HL-5_cash_conversion_ltm": "HL-5"}
# The generator splits a vendor payment across bill lines in whole halalas (int truncation); SAR 1 per 12 months
# is far below anything the page shows (SAR 0.1m).
MONEY_TOLERANCE = Decimal(1)


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def _rows(answer_key: Path, company: str) -> list[dict[str, str]]:
    with open(answer_key / company / "kpis_monthly.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_cash_conversion_and_free_cash_flow_match_the_answer_key(zoho_root: Path, answer_key: Path, company: str):
    conn = FileConnector(zoho_root)
    mapping = _truth(answer_key, company)
    ctx = build_context(company, rebuild_trial_balances(conn, company), mapping,
                        cash_flows=build_cash_flows(conn, company, mapping))
    checked = 0
    for row in _rows(answer_key, company):
        month = row["month"]
        got = compute_all(ctx, month)
        for column, kpi_id in (MONEY | RATIO).items():
            want = row[column]
            if not want:
                continue
            value = got[kpi_id].value
            assert value is not None, f"{company} {month} {kpi_id}: {got[kpi_id].state}"
            if column in MONEY:
                assert abs(value - Decimal(want)) <= MONEY_TOLERANCE, f"{company} {month} {kpi_id}: {value} vs {want}"
            else:
                assert round(value, 4) == Decimal(want), f"{company} {month} {kpi_id}: {value} vs {want}"
            checked += 1
    assert checked > 0


def test_cash_conversion_is_not_meaningful_when_ebitda_is_not_positive():
    from txg.kpi.cashflow import CashFlows
    from txg.kpi.context import KpiContext

    months = [f"2025-{m:02d}" for m in range(1, 13)]
    income = {m: {"4100": Decimal(100), "6200": Decimal(-120)} for m in months}  # EBITDA −20 a month
    flows = {m: CashFlows(operating=Decimal(5)) for m in months}
    ctx = KpiContext("X", months, income, {m: {} for m in months}, {m: {} for m in months}, cash_flows=flows)
    hl5 = compute_all(ctx, "2025-12")["HL-5"]
    assert hl5.state == "n.m." and hl5.value is None


def test_cash_conversion_needs_twelve_months_of_cash_flows():
    from txg.kpi.cashflow import CashFlows
    from txg.kpi.context import KpiContext

    months = [f"2025-{m:02d}" for m in range(1, 13)]
    income = {m: {"4100": Decimal(100), "6200": Decimal(-80)} for m in months}
    flows = {m: CashFlows(operating=Decimal(5)) for m in months[1:]}  # January missing
    ctx = KpiContext("X", months, income, {m: {} for m in months}, {m: {} for m in months}, cash_flows=flows)
    hl5 = compute_all(ctx, "2025-12")["HL-5"]
    assert hl5.state == "needs_data"
