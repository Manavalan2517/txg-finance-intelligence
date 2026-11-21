"""Task C3: facility terms and covenants (§9.5, §12.14), chance of hitting budget (§12.7, HL-2) and the 13-week
liquidity simulation (§12.8, HL-7). S1 (EH-01) and S2 (EH-08) are the planted stories."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.kpi.context import build_context
from txg.kpi.facts import build_month_facts
from txg.normalise.trial_balance import rebuild_trial_balances
from txg.stats.budget_sim import chance_of_hitting_budget
from txg.stats.cash13 import simulate_13_weeks
from txg.stats.covenants import covenant_results
from txg.uploads.budgets import load_budgets
from txg.uploads.facilities import FacilityCheckError, load_recorded_facilities

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"
AS_OF = "2026-10"


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def _answer(answer_key: Path, company: str, month: str, column: str) -> Decimal:
    with open(answer_key / company / "kpis_monthly.csv", encoding="utf-8", newline="") as f:
        return next(Decimal(r[column]) for r in csv.DictReader(f) if r["month"] == month)


@pytest.fixture(scope="module")
def eh01(zoho_root: Path, answer_key: Path):
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    conn = FileConnector(zoho_root)
    facts = build_month_facts(conn, "EH-01")
    ctx = build_context("EH-01", rebuild_trial_balances(conn, "EH-01"), _truth(answer_key, "EH-01"), facts=facts)
    return conn, ctx, load_recorded_facilities(UPLOADS / "answer-key-additions" / "EH-01" / "facilities.json")


def test_repayment_schedule_must_sum_to_principal(tmp_path: Path):
    bad = tmp_path / "facilities.json"
    bad.write_text('[{"file": "x.pdf", "lender": "B", "facilities": [{"facility": "TL", "type": "term_loan", '
                   '"amount_sar": 100.0, "schedule": [{"date": "2026-03-31", "principal_sar": 40.0}, '
                   '{"date": "2026-06-30", "principal_sar": 50.0}]}], "covenants": [], "definitions": {}}]')
    with pytest.raises(FacilityCheckError):  # CK-11
        load_recorded_facilities(bad)


@pytest.mark.slow
def test_eh01_facility_terms_and_covenants(eh01, answer_key: Path):
    _, ctx, terms = eh01
    assert terms.rcf_limit == Decimal(100_000_000)
    results = {r.name: r for r in covenant_results(ctx, AS_OF, terms)}
    leverage, liquidity = results["Leverage"], results["Minimum liquidity"]
    assert leverage.value == pytest.approx(float(_answer(answer_key, "EH-01", AS_OF, "HL-8_net_debt_to_ebitda_excl_leases")),
                                           abs=1e-4)
    assert leverage.passed and leverage.headroom_sar > 0          # 3.06 against a 3.50 limit
    assert liquidity.value == pytest.approx(float(_answer(answer_key, "EH-01", AS_OF, "liquidity_cash_plus_undrawn")),
                                            abs=0.01)
    assert liquidity.passed and liquidity.headroom_sar < 6_000_000  # SAR 45.8m against SAR 40m
    assert "Debt service cover" in results


@pytest.mark.slow
def test_budget_simulation_is_reproducible_and_flags_eh08(zoho_root: Path, answer_key: Path):
    conn = FileConnector(zoho_root)
    ctx = build_context("EH-08", rebuild_trial_balances(conn, "EH-08"), _truth(answer_key, "EH-08"))
    budgets = load_budgets(UPLOADS / "uploads" / "EH-08" / "budgets")
    a = chance_of_hitting_budget(ctx, budgets, AS_OF, paths=2000)
    b = chance_of_hitting_budget(ctx, budgets, AS_OF, paths=2000)
    assert a == b                                   # CK-16: same seed, same answer
    assert 0 <= a.chance <= 1 and a.chance < 0.30   # S2: HL-2 act (budget out of reach)
    assert a.p10 <= a.p50 <= a.p90


@pytest.mark.slow
def test_payment_delays_are_measured_to_settlement_of_the_main_amount(eh01):
    """Regression: contractor invoices close only when retention is released years later; delays must stop at
    settlement of the main amount, or every collection falls outside the 13 weeks."""
    from datetime import date

    import numpy as np

    from txg.kpi.facts import _docs
    from txg.stats.cash13 import _paid_delays
    conn, _, _ = eh01
    _, pooled = _paid_delays(_docs(conn, "EH-01", "invoices", date(2023, 1, 1)), date(2026, 10, 31))
    assert len(pooled) > 1000 and np.median(pooled) < 120


@pytest.mark.slow
def test_13_week_cash_is_reproducible_and_flags_eh01(eh01):
    conn, ctx, terms = eh01
    a = simulate_13_weeks(conn, ctx, terms, AS_OF, minimum=Decimal(40_000_000), paths=2000)
    b = simulate_13_weeks(conn, ctx, terms, AS_OF, minimum=Decimal(40_000_000), paths=2000)
    assert a == b
    assert len(a.weeks) == 13 and a.weeks[0].start.weekday() == 6  # Sunday-start weeks (B-03)
    assert a.chance_below_minimum >= 0.20                            # S1: HL-7 act
    assert a.low_point_p10 < a.low_point_p50 < a.opening
    assert a.low_point_p50 == pytest.approx(sorted(a.low_points)[len(a.low_points) // 2], rel=1e-9)  # median (B-04)
