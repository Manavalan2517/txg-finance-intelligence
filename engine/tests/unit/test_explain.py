"""Task C6: explanations are written from facts; every number must be a fact reference (§9.7, CK-14, F-10)."""
import json

from txg.explain.explainer import Fact, check_text, explain, render
from txg.modelsteps.client import ScriptedClient

FACTS = [Fact("f:kpi.HL-5.EH-01.2026-10", "cash conversion", "-29%"),
         Fact("f:sig.RC-1.EH-01.2026-10", "days late, government clients", "53 days"),
         Fact("f:imp.RC-1.EH-01.2026-10", "cash held", "SAR 23.0m")]


def test_text_with_only_fact_references_passes():
    text = "Profitable, but cash is tightening: customers pay {f:sig.RC-1.EH-01.2026-10} late, {f:imp.RC-1.EH-01.2026-10} held."
    assert check_text(text, FACTS) == []
    assert render(text, FACTS) == "Profitable, but cash is tightening: customers pay 53 days late, SAR 23.0m held."


def test_free_typed_numbers_and_unknown_facts_are_refused():
    problems = check_text("Customers pay 38 days late; see {f:missing}.", FACTS)
    assert any("38" in p for p in problems) and any("f:missing" in p for p in problems)


def test_integrity_wording_never_accuses():
    assert check_text("This looks like fraud by the clerk.", [], integrity=True)
    assert check_text("Worth a look: bills bunch below the approval limit.", [], integrity=True) == []


def _answer(text: str) -> str:
    return json.dumps({"text": text})


def test_writer_retries_once_with_the_finding_then_passes():
    prompts = []

    def writer(step, prompt):
        prompts.append(prompt)
        return _answer("Cash conversion is 38%." if len(prompts) == 1 else "Cash conversion is {f:kpi.HL-5.EH-01.2026-10}.")

    card = explain(FACTS, ScriptedClient(writer))
    assert card.text == "Cash conversion is -29%." and not card.numbers_only and card.attempts == 2
    assert "FINDING" in prompts[1]


def test_writer_that_keeps_typing_numbers_falls_back_to_a_numbers_only_card():
    card = explain(FACTS, ScriptedClient(lambda s, p: _answer("It is 38 days.")))
    assert card.numbers_only
    assert card.text == "cash conversion: -29% · days late, government clients: 53 days · cash held: SAR 23.0m"
