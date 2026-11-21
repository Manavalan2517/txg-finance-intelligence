"""Regression tests for the Phase B review findings (one test per fixed finding)."""
import sys
import types
from decimal import Decimal
from pathlib import Path

import pytest

from txg.connector.base import check_org
from txg.ledger.mix import NotMeaningful, performance_mix_split
from txg.ledger.subledger import _go_live_balance
from txg.mapping.briefs import redact
from txg.mapping.runner import attach_findings, fallback_code
from txg.mapping.store import MappingEntry, MappingStore
from txg.modelsteps.client import BudgetExceeded, LiveClient
from txg.normalise.holds import PeriodGate
from txg.normalise.mapping_checks import MappingFinding
from txg.normalise.trial_balance import TrialBalance
from txg.record.store import EventLog


def _entry(acc: str, code: str, zoho_type: str = "other_current_liability") -> MappingEntry:
    return MappingEntry(account_id=acc, account_name=acc, zoho_type=zoho_type, std_code=code, confidence="high",
                        evidence=["x"], first_reading=code)


# Finding 1: SIGN findings (keyed by standard code) and leftovers must not be dropped.
def test_sign_findings_attach_to_every_account_on_that_line_and_leftovers_are_kept():
    entries = {"a1": _entry("a1", "2120"), "a2": _entry("a2", "2120"), "a3": _entry("a3", "2110")}
    findings = [MappingFinding("SIGN", "", "Accrued expenses has the wrong sign", std_code="2120"),
                MappingFinding("CLASS", "a3", "class mismatch"), MappingFinding("CLASS", "a3", "second issue"),
                MappingFinding("CK-04", "zz", "not mapped")]
    out, leftovers = attach_findings(entries, findings)
    assert out["a1"].findings == ["Accrued expenses has the wrong sign"] == out["a2"].findings
    assert out["a3"].findings == ["class mismatch", "second issue"]
    assert leftovers == ["CK-04 zz: not mapped"]
    assert entries["a1"].findings == []  # inputs not mutated


# Finding 2: fallback never turns a balance-sheet account into an expense; unknown types are an error.
@pytest.mark.parametrize(("zoho_type", "code"), [("other_asset", "1290"), ("credit_card", "2170"),
                                                 ("other_liability", "2290")])
def test_fallback_keeps_balance_sheet_types_on_the_balance_sheet(zoho_type: str, code: str):
    assert fallback_code(zoho_type) == code


def test_fallback_for_unknown_type_raises():
    with pytest.raises(ValueError):
        fallback_code("mystery_type")


# Finding 3: personal names never reach the model — account names too, case-insensitively, honorifics too.
def test_redact_is_case_insensitive_and_catches_honorific_names():
    names = ["Ahmed Al-Qahtani"]
    assert redact("Salary advance AHMED AL-QAHTANI", names) == "Salary advance <name>"
    assert redact("Advance – Mr. Khalid", names) == "Advance – Mr. <name>"
    assert redact("سلفة - السيد خالد", names) == "سلفة - السيد <name>"
    assert redact("Trade Debtors", names) == "Trade Debtors"


# Finding 4: the open month is never recorded as closed.
def test_month_after_last_close_stays_open(tmp_path: Path):
    gate = PeriodGate(EventLog(tmp_path / "r.duckdb"))
    tb = TrialBalance("EH-01", "2026-11", {"cash": Decimal(1), "rev": Decimal(-1)})
    status = gate.evaluate(tb, printed=None, closed_through="2026-10")
    assert status.status == "open"
    assert gate.status_of("EH-01", "2026-11").status == "open"


# Finding 5: the live client enforces its own cap and bounds each call.
def test_live_client_enforces_cap_and_bounds_output(monkeypatch):
    calls = []

    class _Resp:
        usage = types.SimpleNamespace(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)
        choices = [types.SimpleNamespace(message=types.SimpleNamespace(content='{"a": 1}'))]

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return _Resp()

    class _OpenAI:
        def __init__(self):
            self.chat = types.SimpleNamespace(completions=_Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_OpenAI))
    monkeypatch.setenv("TXG_LIVE_MODEL", "1")
    monkeypatch.setenv("TXG_PRICE_IN_PER_MTOK", "1000")   # USD 1 per 1k tokens: deliberately expensive
    monkeypatch.setenv("TXG_PRICE_OUT_PER_MTOK", "1000")
    client = LiveClient(model="m", cap_usd=Decimal("2.5"))
    client.complete("s", "p")                              # costs USD 2.00
    assert 0 < calls[0]["max_completion_tokens"] <= 2500
    with pytest.raises(BudgetExceeded):
        client.complete("s", "p2")                         # only USD 0.50 left: not enough for a bounded call


# Finding 6: a present-but-empty go-live balance is an error, not zero.
def test_empty_go_live_balance_raises():
    with pytest.raises(ValueError):
        _go_live_balance({"invoice_id": "1", "cf_balance_at_go_live": None})
    assert _go_live_balance({"invoice_id": "1"}) is None
    assert _go_live_balance({"cf_balance_at_go_live": 12.5}) == Decimal("12.5")


# Finding 9: zero revenue is "not meaningful", never a bare decimal crash.
def test_mix_split_with_zero_revenue_is_not_meaningful():
    with pytest.raises(NotMeaningful):
        performance_mix_split([Decimal(0)], [Decimal(10)], [Decimal("0.1")], [Decimal("0.2")])


# Finding 12: identifiers with a trailing newline are rejected.
def test_identifier_with_trailing_newline_rejected():
    with pytest.raises(ValueError):
        check_org("EH-01\n")


# Finding 14: overrides are checked against the chart and the Zoho type.
def test_override_rejects_unknown_or_misfitting_code(tmp_path: Path):
    store = MappingStore(tmp_path)
    store.save("EH-01", {"a1": _entry("a1", "4100", zoho_type="income")}, Decimal(250000), "test")
    with pytest.raises(ValueError):
        store.override("EH-01", "a1", "9999", reason="typo", person="cfo")
    with pytest.raises(ValueError):
        store.override("EH-01", "a1", "1120", reason="income is not an asset", person="cfo")
