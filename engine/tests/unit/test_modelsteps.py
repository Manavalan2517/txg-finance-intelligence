"""Task B4: every model step is typed, checked by code, recorded, replayable and budget-capped (§9.2, §9.9, §9.10)."""
import json
import socket
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

from txg.modelsteps.client import (
    BudgetedClient,
    BudgetExceeded,
    Completion,
    LiveCallsDisabled,
    LiveClient,
    MissingRecording,
    RecordedClient,
    ScriptedClient,
)
from txg.modelsteps.contract import ModelStep, StepFailed
from txg.modelsteps.second_reading import read_twice, reconcile


class Label(BaseModel):
    code: str
    confidence: str


def _render(brief: dict) -> str:
    return json.dumps(brief, sort_keys=True)


def _step(client, name="label", checks=None) -> ModelStep:
    return ModelStep(name=name, schema=Label, model="small", prompt_version="v1", render=_render,
                     client=client, checks=checks)


def test_valid_output_is_parsed_and_hashed():
    client = ScriptedClient(lambda step, prompt: '{"code": "1120", "confidence": "high"}')
    res = _step(client).run({"account": "Debtors"})
    assert res.output == Label(code="1120", confidence="high")
    assert len(res.prompt_hash) == 64 and len(res.response_hash) == 64
    assert res.attempts == 1 and res.stand_in is True


def test_invalid_json_rejected_and_finding_sent_once():
    prompts = []

    def answer(step, prompt):
        prompts.append(prompt)
        return "not json" if len(prompts) == 1 else '{"code": "1120", "confidence": "low"}'

    res = _step(ScriptedClient(answer)).run({"account": "Debtors"})
    assert res.attempts == 2 and res.output.code == "1120"
    assert "FINDING" in prompts[1] and "FINDING" not in prompts[0]


def test_second_failure_raises_and_never_silently_defaults():
    with pytest.raises(StepFailed) as err:
        _step(ScriptedClient(lambda s, p: "still not json")).run({"account": "Debtors"})
    assert err.value.attempts == 2


def test_code_check_failure_goes_back_as_a_finding():
    answers = iter(['{"code": "9999", "confidence": "high"}', '{"code": "1120", "confidence": "high"}'])
    seen = []

    def answer(step, prompt):
        seen.append(prompt)
        return next(answers)

    def checks(out: Label) -> list[str]:
        return [] if out.code != "9999" else ["9999 is not in the standard chart"]

    res = _step(ScriptedClient(answer), checks=checks).run({"account": "Debtors"})
    assert res.output.code == "1120"
    assert "9999 is not in the standard chart" in seen[1]


def test_recorded_client_never_hits_network(tmp_path: Path, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(socket, "create_connection", no_network)
    store = RecordedClient(tmp_path)
    prompt = _render({"account": "Debtors"})
    store.save("label", prompt, Completion('{"code": "1120", "confidence": "high"}'))
    assert _step(store).run({"account": "Debtors"}).output.code == "1120"
    with pytest.raises(MissingRecording):
        _step(store).run({"account": "Something else"})


def test_live_client_refuses_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("TXG_LIVE_MODEL", raising=False)
    with pytest.raises(LiveCallsDisabled):
        LiveClient(model="gpt-small", cap_usd=Decimal(5))


class _PaidFake:
    def __init__(self):
        self.calls = 0

    def complete(self, step: str, prompt: str) -> Completion:
        self.calls += 1
        return Completion('{"code": "1120", "confidence": "high"}', tokens=100, cost_usd=Decimal("1.00"))


def test_budget_cap_stops_and_resumes_without_repeat(tmp_path: Path):
    inner = _PaidFake()
    capped = BudgetedClient(inner, RecordedClient(tmp_path), cap_usd=Decimal("2.00"))
    _step(capped).run({"a": 1})
    _step(capped).run({"a": 2})
    with pytest.raises(BudgetExceeded):
        _step(capped).run({"a": 3})
    assert inner.calls == 2
    resumed = BudgetedClient(inner, RecordedClient(tmp_path), cap_usd=Decimal("5.00"))
    for i in (1, 2, 3):
        _step(resumed).run({"a": i})
    assert inner.calls == 3  # steps 1 and 2 replayed from the record; only step 3 was paid for


def test_second_reading_never_sees_first():
    seen: dict[str, str] = {}

    def first(step, prompt):
        seen["first"] = prompt
        return '{"code": "4200", "confidence": "medium"}'

    def second(step, prompt):
        seen["second"] = prompt
        return '{"code": "4100", "confidence": "high"}'

    a, b = read_twice(_step(ScriptedClient(first), "map"), _step(ScriptedClient(second), "map_second"),
                      {"account": "Miscellaneous income"})
    assert a.output.code == "4200" and b.output.code == "4100"
    assert "4200" not in seen["second"]


def _res(code: str, confidence: str):
    client = ScriptedClient(lambda s, p: json.dumps({"code": code, "confidence": confidence}))
    return _step(client).run({"x": code + confidence})


def test_reconcile_agreement_applies_without_marker():
    d = reconcile(_res("1120", "high"), _res("1120", "medium"), key=lambda o: o.code,
                  effect_sar=lambda a, b: Decimal(0), materiality=Decimal(250000))
    assert d.agreed and not d.unreviewed and d.chosen.code == "1120"


def test_reconcile_disagreement_above_materiality_marks_unreviewed():
    d = reconcile(_res("4200", "medium"), _res("4100", "high"), key=lambda o: o.code,
                  effect_sar=lambda a, b: Decimal(15500000), materiality=Decimal(250000))
    assert not d.agreed and d.unreviewed and d.chosen.code == "4100"
    assert d.effect_sar == Decimal(15500000)


def test_reconcile_disagreement_below_materiality_applies_quietly_first_on_tie():
    d = reconcile(_res("6500", "high"), _res("6900", "high"), key=lambda o: o.code,
                  effect_sar=lambda a, b: Decimal(1000), materiality=Decimal(250000))
    assert not d.agreed and not d.unreviewed and d.chosen.code == "6500"
