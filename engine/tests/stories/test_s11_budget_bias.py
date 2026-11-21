"""S11 (EH-08): revenue budgets above actual in 7 of the last 8 quarters → TR-3 act (sign test p ≈ 0.035) (§12.15)."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.kpi.context import build_context
from txg.kpi.forecast_record import forecast_record, quarterly_errors, sign_test_p
from txg.normalise.trial_balance import rebuild_trial_balances
from txg.uploads.budgets import load_budgets

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def test_sign_test_hand_example():
    """§18.2: 7 of 8 budgets too high → p = 9 ÷ 256 ≈ 0.035."""
    assert sign_test_p(7, 8) == pytest.approx(9 / 256)
    assert sign_test_p(4, 8) == pytest.approx(163 / 256)


def test_forecast_record_status_follows_spec_tolerances():
    errors = [Decimal("0.10")] * 7 + [Decimal("-0.02")]
    rec = forecast_record(errors)
    assert rec.over == 7 and rec.n == 8 and rec.p == pytest.approx(9 / 256)
    assert rec.status == "act"  # p < 0.05 and bias beyond ±5%
    assert forecast_record([Decimal("0.01")] * 7 + [Decimal("-0.02")]).status == "watch"  # p < 0.10, small bias


@pytest.mark.slow
@pytest.mark.parametrize("company", ["EH-08", "EH-01", "EH-14"])
def test_quarterly_revenue_errors_match_answer_key(zoho_root: Path, answer_key: Path, company: str):
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    ctx = build_context(company, rebuild_trial_balances(FileConnector(zoho_root), company), _truth(answer_key, company))
    budgets = load_budgets(UPLOADS / "uploads" / company / "budgets")
    got = quarterly_errors(ctx, budgets, line="Revenue", closed_through="2026-10")
    with open(UPLOADS / "answer-key-additions" / company / "budget_vs_actual.csv", encoding="utf-8") as f:
        want = {r["quarter"]: Decimal(r["revenue_error"]) for r in csv.DictReader(f)}
    assert set(got) == set(want)
    assert all(abs(got[q] - want[q]) <= Decimal("0.00011") for q in want)


@pytest.mark.slow
def test_s11_eh08_budget_bias_is_act(zoho_root: Path, answer_key: Path):
    ctx = build_context("EH-08", rebuild_trial_balances(FileConnector(zoho_root), "EH-08"), _truth(answer_key, "EH-08"))
    errors = quarterly_errors(ctx, load_budgets(UPLOADS / "uploads" / "EH-08" / "budgets"), "Revenue", "2026-10")
    rec = forecast_record([errors[q] for q in sorted(errors)][-8:])
    assert rec.over == 7 and rec.p == pytest.approx(9 / 256) and rec.status == "act"
