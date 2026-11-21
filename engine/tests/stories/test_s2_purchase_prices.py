"""S2 (EH-08): purchase prices of most items rise ~4.1% from October 2025 while selling prices rise ~1.2%.
Expected: HL-3 slipping (early warning) and DR-3 names purchase prices (§11.2.6, §12.13, §15.4)."""
import csv
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.kpi.common import ebitda_margin
from txg.kpi.context import build_context
from txg.normalise.trial_balance import rebuild_trial_balances
from txg.stats.drivers import driver_at_risk, price_change
from txg.stats.xmr import normal_range, signal_p

BEFORE, AFTER = ("2024-10", "2025-09"), ("2025-10", "2026-09")


def _truth(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


@pytest.mark.slow
def test_s2_purchase_prices_outrun_selling_prices(zoho_root: Path):
    conn = FileConnector(zoho_root)
    ppi = price_change(conn, "EH-08", "bills", BEFORE, AFTER)
    spi = price_change(conn, "EH-08", "invoices", BEFORE, AFTER)
    assert ppi > spi + 0.01                       # purchase prices rose clearly faster
    assert driver_at_risk(ppi, spi) == "purchase prices"
    quiet_ppi = price_change(conn, "EH-09", "bills", BEFORE, AFTER)
    quiet_spi = price_change(conn, "EH-09", "invoices", BEFORE, AFTER)
    assert driver_at_risk(quiet_ppi, quiet_spi) is None


@pytest.mark.slow
def test_s2_ebitda_margin_is_slipping(zoho_root: Path, answer_key: Path):
    ctx = build_context("EH-08", rebuild_trial_balances(FileConnector(zoho_root), "EH-08"), _truth(answer_key, "EH-08"))
    months = [m for m in ctx.months if "2023-12" <= m <= "2026-10"]
    series = [float(ebitda_margin(ctx, m).value) for m in months]
    p, _ = signal_p(series, normal_range(series), bad_side="low")
    assert p < 0.01
