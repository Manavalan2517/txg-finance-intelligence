"""Explanations (C13, §9.7, §13.1): the model writes verdict lines and signal texts from computed facts; code checks
every number (CK-14). A number typed by the model is refused; the finding goes back once; if it fails again the
card shows numbers only and the record notes it. Integrity texts must stay "worth a look" (§11.5)."""
import json
import re
from dataclasses import dataclass

from pydantic import BaseModel

from txg.modelsteps.client import ModelClient
from txg.modelsteps.contract import ModelStep, StepFailed

_REF = re.compile(r"\{(f:[^{}\s]+)\}")
_DIGIT = re.compile(r"\d[\d,.%]*")
# Stand-in for the second small model that reviews integrity wording (§9.7); a word list, labelled as such.
_ACCUSATION = re.compile(r"\b(fraud\w*|theft|stole|steal\w*|embezzl\w*|corrupt\w*|crime|criminal)\b", re.IGNORECASE)
INSTRUCTIONS = ("Write one or two plain-English sentences from these facts. Never type a number: refer to a fact as "
                "{f:id}. Answer JSON: {\"text\": ...}.")


@dataclass(frozen=True)
class Fact:
    id: str
    label: str
    display: str


@dataclass(frozen=True)
class Card:
    text: str
    numbers_only: bool
    attempts: int
    findings: tuple[str, ...] = ()


class Explanation(BaseModel):
    text: str


def check_text(text: str, facts: list[Fact], integrity: bool = False) -> list[str]:
    known = {f.id for f in facts}
    problems = [f"unknown fact reference {ref}" for ref in _REF.findall(text) if ref not in known]
    typed = _DIGIT.findall(_REF.sub("", text))
    if typed:
        problems.append(f"numbers typed instead of fact references: {', '.join(typed)}")
    if integrity and _ACCUSATION.search(text):
        problems.append("integrity texts must say 'worth a look' and never accuse")
    return problems


def render(text: str, facts: list[Fact]) -> str:
    by_id = {f.id: f.display for f in facts}
    return _REF.sub(lambda m: by_id[m.group(1)], text)


def numbers_only(facts: list[Fact]) -> str:
    return " · ".join(f"{f.label}: {f.display}" for f in facts)


def explain(facts: list[Fact], client: ModelClient, integrity: bool = False) -> Card:
    brief = json.dumps({"instructions": INSTRUCTIONS, "integrity": integrity,
                        "facts": [{"id": f.id, "label": f.label, "display": f.display} for f in facts]},
                       ensure_ascii=False)
    step = ModelStep(name="explain", schema=Explanation, model="writer", prompt_version="explain-v1",
                     render=lambda b: b, client=client, checks=lambda out: check_text(out.text, facts, integrity))
    try:
        result = step.run(brief)
    except StepFailed as failure:
        return Card(numbers_only(facts), True, failure.attempts, tuple(failure.findings))
    return Card(render(result.output.text, facts), False, result.attempts, result.findings)
