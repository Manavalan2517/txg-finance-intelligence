"""CK-18 and F-18 (§6.5 replay rule, §18.3): results are keyed by (company, period, snapshot set, mapping version,
configuration version, seed); re-running with the same key must give the same result hash. A different hash raises
a CK-18 alert and marks the run non-reproducible until explained."""
import csv
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.kpi.cashflow import build_cash_flows
from txg.kpi.context import build_context
from txg.kpi.facts import build_month_facts
from txg.kpi.registry import KpiValue, compute_all
from txg.normalise.trial_balance import rebuild_trial_balances
from txg.record.replay import ReplayKey, check_replay, config_version, result_hash
from txg.record.store import EventLog

KEY = ReplayKey(company="EH-21", period="2026-10", snapshots="books-2026-11-20", mapping_version="1",
                config_version="cfg", seed="0")


def _values(hl3: str = "0.0812") -> dict[str, KpiValue]:
    return {"HL-3": KpiValue("EH-21", "2026-10", "HL-3", Decimal(hl3), "ratio", "ok"),
            "HL-8": KpiValue("EH-21", "2026-10", "HL-8", None, "x", "n.m.")}


def test_the_hash_ignores_order_but_not_values():
    a, b = _values(), dict(reversed(list(_values().items())))
    assert result_hash(a) == result_hash(b)
    assert result_hash(_values("0.0813")) != result_hash(a)


def test_first_run_records_and_a_same_result_replay_is_reproducible(tmp_path: Path):
    log = EventLog(tmp_path / "r.duckdb")
    assert check_replay(log, KEY, result_hash(_values())).status == "recorded"
    assert check_replay(log, KEY, result_hash(_values())).status == "reproducible"


def test_f18_a_different_hash_alerts_and_marks_the_run_non_reproducible(tmp_path: Path):
    log = EventLog(tmp_path / "r.duckdb")
    check_replay(log, KEY, result_hash(_values()))
    outcome = check_replay(log, KEY, result_hash(_values("0.0900")))
    assert outcome.status == "non_reproducible" and outcome.expected != outcome.got
    types = [e.type for e in log.by_scope(company="EH-21", period="2026-10")]
    assert types[-2:] == ["ck18.alert", "run.non_reproducible"]
    # it stays non-reproducible until explained, even if a later replay matches again
    assert check_replay(log, KEY, result_hash(_values())).status == "non_reproducible"


def test_a_different_key_is_a_different_result_not_a_mismatch(tmp_path: Path):
    log = EventLog(tmp_path / "r.duckdb")
    check_replay(log, KEY, result_hash(_values()))
    other = ReplayKey(**{**KEY.__dict__, "mapping_version": "2"})
    assert check_replay(log, other, result_hash(_values("0.0900"))).status == "recorded"


def test_configuration_version_changes_when_a_config_file_changes(tmp_path: Path):
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    before = config_version(tmp_path)
    (tmp_path / "a.json").write_text('{"q": 0.1}', encoding="utf-8")
    assert config_version(tmp_path) != before and len(before) == 16


@pytest.mark.slow
def test_ck18_two_independent_runs_of_a_company_month_hash_the_same(zoho_root: Path, answer_key: Path, tmp_path: Path):
    with open(answer_key / "EH-21" / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        mapping = {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}

    def run() -> str:
        conn = FileConnector(zoho_root)  # a fresh read of the books each time
        ctx = build_context("EH-21", rebuild_trial_balances(conn, "EH-21"), mapping,
                            facts=build_month_facts(conn, "EH-21"), cash_flows=build_cash_flows(conn, "EH-21", mapping))
        return result_hash(compute_all(ctx, "2026-10"))

    log = EventLog(tmp_path / "r.duckdb")
    key = ReplayKey("EH-21", "2026-10", "books-2026-11-20", "answer-key", config_version(), "0")
    assert check_replay(log, key, run()).status == "recorded"
    assert check_replay(log, key, run()).status == "reproducible"
