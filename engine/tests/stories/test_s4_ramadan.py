"""S4 (EH-14): March 2026 sales are about 11% below March 2025 because Ramadan moved; after the holiday adjustment
the business is growing, and the drop is logged as "not alarmed" (§12.1, §13.3, §15.4)."""
import csv
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.kpi.context import build_context
from txg.normalise.trial_balance import rebuild_trial_balances
from txg.stats.calendar import holiday_shares, load_holidays
from txg.stats.holiday import fit_holiday_model


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def test_holiday_shares_split_ramadan_across_months():
    cal = load_holidays()
    feb, mar = holiday_shares(cal, "2026-02"), holiday_shares(cal, "2026-03")
    assert feb.ramadan == pytest.approx(11 / 28)      # 18–28 Feb 2026
    assert mar.ramadan == pytest.approx(19 / 31)      # 1–19 Mar 2026
    assert mar.eid_fitr == pytest.approx(4 / 31)      # 20–23 Mar 2026
    assert holiday_shares(cal, "2025-03").ramadan == pytest.approx(29 / 31)


@pytest.mark.slow
def test_s4_march_drop_is_the_calendar_not_the_business(zoho_root: Path, answer_key: Path):
    conn = FileConnector(zoho_root)
    ctx = build_context("EH-14", rebuild_trial_balances(conn, "EH-14"), _truth(answer_key, "EH-14"))
    closed = [m for m in ctx.months if m <= "2026-10"]
    revenue = {m: float(ctx.income[m].get("4100", 0)) for m in closed}
    raw = revenue["2026-03"] / revenue["2025-03"] - 1
    assert raw == pytest.approx(-0.109, abs=0.002)
    model = fit_holiday_model(revenue, load_holidays())
    assert model.effects_used, "a significant Ramadan/Eid effect should be found in retail sales"
    adjusted = model.adjusted(revenue)
    adj_growth = adjusted["2026-03"] / adjusted["2025-03"] - 1
    assert adj_growth > 0  # the business grew once the holiday is removed (true effect ≈ +3.9%)
