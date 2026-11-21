"""The contract every model step follows (§9.2): typed brief in, schema-validated JSON out, code checks before
anything uses it, one retry carrying the exact finding (R7), and no silent defaults."""
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from txg.modelsteps.client import ModelClient
from txg.record.hashing import sha256_bytes

Out = TypeVar("Out", bound=BaseModel)
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class StepResult(Generic[Out]):
    step: str
    output: Out
    prompt_hash: str
    response_hash: str
    model: str
    tokens: int
    cost_usd: Decimal
    attempts: int
    stand_in: bool
    findings: tuple[str, ...] = ()

    @property
    def confidence(self) -> str:
        return str(getattr(self.output, "confidence", "medium"))


class StepFailed(RuntimeError):
    def __init__(self, step: str, attempts: int, findings: list[str]):
        super().__init__(f"model step {step!r} failed after {attempts} attempts: {findings[-1]}")
        self.step, self.attempts, self.findings = step, attempts, findings


@dataclass
class ModelStep(Generic[Out]):
    name: str
    schema: type[Out]
    model: str
    prompt_version: str
    render: Callable[[Any], str]
    client: ModelClient
    checks: Callable[[Out], list[str]] | None = None

    def run(self, brief: Any) -> StepResult[Out]:
        base = self.render(brief)
        prompt, findings = base, []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            completion = self.client.complete(self.name, prompt)
            try:
                output = self.schema.model_validate_json(completion.text)
                problems = self.checks(output) if self.checks else []
            except ValidationError as exc:
                output, problems = None, [f"output did not match the schema: {exc.errors()[0]['msg']}"]
            if output is not None and not problems:
                return StepResult(self.name, output, sha256_bytes(prompt.encode()),
                                  sha256_bytes(completion.text.encode()), completion.model, completion.tokens,
                                  completion.cost_usd, attempt, completion.stand_in, tuple(findings))
            findings.extend(problems)
            prompt = f"{base}\n\nFINDING (from code checks): {'; '.join(problems)}\nPropose again, with evidence."
        raise StepFailed(self.name, MAX_ATTEMPTS, findings)
