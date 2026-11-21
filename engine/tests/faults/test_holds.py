"""Task B3: data problems hold only the affected company-month and release by themselves (§9.10, F-05, F-06)."""
from decimal import Decimal
from pathlib import Path

from txg.normalise.holds import PeriodGate
from txg.normalise.trial_balance import TrialBalance, months_missing, tie_out
from txg.record.store import EventLog


def _tb(month: str, **balances: str) -> TrialBalance:
    bal = {k: Decimal(v) for k, v in balances.items()}
    return TrialBalance(company="EH-22", month=month, balances=bal, movements=bal)


GOOD = dict(cash="100.00", revenue="-100.00")


def test_tie_out_is_exact_to_the_halala():
    assert tie_out(_tb("2026-09", **GOOD), _tb("2026-09", **GOOD)).tied
    off = tie_out(_tb("2026-09", **GOOD), _tb("2026-09", cash="100.01", revenue="-100.00"))
    assert not off.tied and off.differences == {"cash": Decimal("-0.01")}


def test_tie_out_reports_accounts_missing_on_either_side():
    res = tie_out(_tb("2026-09", **GOOD), _tb("2026-09", cash="100.00", revenue="-100.00", other="0.50"))
    assert res.differences == {"other": Decimal("-0.50")}


def test_tie_mismatch_holds_month(tmp_path: Path):
    log = EventLog(tmp_path / "r.duckdb")
    gate = PeriodGate(log)
    assert gate.evaluate(_tb("2026-08", **GOOD), printed=_tb("2026-08", **GOOD)).status == "tied"
    printed_off = _tb("2026-09", cash="101.00", revenue="-101.00")
    status = gate.evaluate(_tb("2026-09", **GOOD), printed=printed_off)
    assert status.status == "held" and status.reason == "trial balance does not tie to the printed trial balance"
    assert [e.type for e in log.by_scope(company="EH-22", period="2026-09")] == ["tb.mismatch", "hold.started"]
    assert gate.status_of("EH-22", "2026-08").status == "tied"
    assert gate.last_good_month("EH-22", before="2026-10") == "2026-08"


def test_hold_releases_when_corrected(tmp_path: Path):
    log = EventLog(tmp_path / "r.duckdb")
    gate = PeriodGate(log)
    gate.evaluate(_tb("2026-09", **GOOD), printed=_tb("2026-09", cash="1.00", revenue="-1.00"))
    assert gate.evaluate(_tb("2026-09", **GOOD), printed=_tb("2026-09", **GOOD)).status == "tied"
    events = log.by_scope(company="EH-22", period="2026-09")
    assert [e.type for e in events][-2:] == ["tb.tied", "hold.released"]
    assert all(e.actor.kind == "code" for e in events)


def test_unbalanced_ledger_holds_even_without_printed_tb(tmp_path: Path):
    gate = PeriodGate(EventLog(tmp_path / "r.duckdb"))
    status = gate.evaluate(_tb("2026-09", cash="100.00", revenue="-99.00"), printed=None)
    assert status.status == "held" and status.reason == "trial balance does not balance"


def test_balanced_month_without_printed_tb_is_closed_untied(tmp_path: Path):
    gate = PeriodGate(EventLog(tmp_path / "r.duckdb"))
    status = gate.evaluate(_tb("2026-09", **GOOD), printed=None)
    assert status.status == "closed" and status.tie_source == "none"


def test_missing_month_pauses_trends():
    assert months_missing(["2026-07", "2026-09", "2026-10"]) == ["2026-08"]
    assert months_missing(["2025-12", "2026-01"]) == []
