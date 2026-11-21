"""Task C1: the KPI registry and the statement-based common KPIs, checked against the client's answer key.

The engine computes from the books; the answer key (`kpis_monthly.csv`) is the oracle. Ratios must agree to the
answer key's 4 decimals, money to the halala. A mismatch is a definition question, never something to fudge."""
import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.kpi.context import build_context
from txg.kpi.registry import compute_all, load_registry
from txg.ledger.chart import CONFIG_DIR
from txg.normalise.trial_balance import rebuild_trial_balances

COMPANIES = ["EH-01", "EH-02", "EH-03", "EH-05", "EH-06", "EH-07", "EH-08", "EH-09", "EH-14", "EH-21"]
# answer-key column -> (kpi id, field of the KPI value)
ORACLE = {
    "revenue_ltm": ("revenue_ltm", "value"),
    "ebitda_ltm": ("ebitda_ltm", "value"),
    "PF-1_gross_margin_ltm": ("PF-1", "value"),
    "HL-3_ebitda_margin_ltm": ("HL-3", "value"),
    "PF-2_opex_ratio_ltm": ("PF-2", "value"),
    "PF-3_net_margin_ltm": ("PF-3", "value"),
    "PF-4_staff_cost_ratio_ltm": ("PF-4", "value"),
    "FG-1_interest_cover_ltm": ("FG-1", "value"),
    "net_debt_excl_leases": ("net_debt_excl_leases", "value"),
    "HL-8_net_debt_to_ebitda_excl_leases": ("HL-8", "value"),
    "HL-8_net_debt_to_ebitda_incl_leases": ("HL-8_incl_leases", "value"),
    "HL-1_growth_raw_3m": ("HL-1_raw", "value"),
    "HL-4_roic_ltm": ("HL-4_roic", "value"),
    "invested_capital_avg": ("invested_capital_avg", "value"),
    "CS-4_working_capital_to_revenue": ("CS-4", "value"),
    "CS-2_capex_to_depreciation_ltm": ("CS-2", "value"),
}
MONEY = {"revenue_ltm", "ebitda_ltm", "net_debt_excl_leases", "invested_capital_avg"}


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def _oracle_rows(answer_key: Path, company: str) -> list[dict[str, str]]:
    with open(answer_key / company / "kpis_monthly.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_movements_exclude_go_live_opening_balances(zoho_root: Path):
    conn = FileConnector(zoho_root)
    tbs = rebuild_trial_balances(conn, "EH-01")
    ob = next(conn.iter_records("EH-01", "openingbalances")).data["accounts"]
    cash = next(a for a in ob if a["debit_or_credit"] == "debit")
    jan = tbs["2023-01"]
    opening = jan.balances[cash["account_id"]] - jan.movements.get(cash["account_id"], Decimal(0))
    assert opening == Decimal(str(cash["amount"]))


def test_registry_entries_are_complete_and_have_functions():
    registry = load_registry()
    assert {"HL-3", "PF-1", "HL-8", "HL-4_roic", "CS-4"} <= set(registry)
    for kpi_id, entry in registry.items():
        assert entry.name and entry.unit and entry.direction, kpi_id
        assert entry.function is not None, f"{kpi_id} has no engine function"
    raw = json.loads((CONFIG_DIR / "kpi_registry.json").read_text(encoding="utf-8"))
    assert raw["version"]


def _close(got: Decimal | None, want: str, money: bool) -> bool:
    if got is None:
        return False
    tol = Decimal("0.01") if money else Decimal("0.00011")
    return abs(got - Decimal(want)) <= tol


@pytest.mark.slow
@pytest.mark.parametrize("company", COMPANIES)
def test_statement_kpis_match_answer_key(zoho_root: Path, answer_key: Path, company: str):
    conn = FileConnector(zoho_root)
    ctx = build_context(company, rebuild_trial_balances(conn, company), _truth(answer_key, company))
    mismatches = {}
    for row in _oracle_rows(answer_key, company):
        values = compute_all(ctx, row["month"])
        for column, (kpi_id, _) in ORACLE.items():
            want = row.get(column, "")
            if want == "":
                continue
            got = values[kpi_id].value
            if not _close(got, want, column in MONEY):
                mismatches.setdefault(column, []).append((row["month"], got, want))
    assert {k: v[:3] for k, v in mismatches.items()} == {}


def test_edge_case_states():
    """EBITDA ≤ 0 → n.m.; no interest → interest cover not applicable; never a crash (Review Focus 4)."""
    from txg.kpi.context import KpiContext
    from txg.kpi.registry import compute_all as run

    months = [f"2024-{m:02d}" for m in range(1, 13)]
    flat = {m: {} for m in months}
    income = {m: {"4100": Decimal(100), "5100": Decimal(-120)} for m in months}  # loss-making, no interest
    bs = {m: {"1110": Decimal(50), "3300": Decimal(-50)} for m in months}
    ctx = KpiContext("EH-99", months, income, bs, flat, opening_bs={"1110": Decimal(50), "3300": Decimal(-50)})
    out = run(ctx, "2024-12")
    assert out["HL-3"].value == Decimal("-0.2") and out["HL-3"].state == "ok"
    assert out["HL-8"].state == "n.m." and out["HL-8"].value is None
    assert out["FG-1"].state == "not_applicable"
