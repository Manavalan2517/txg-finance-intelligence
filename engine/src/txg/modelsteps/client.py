"""Model clients. Default is recorded or scripted answers (R14, §9.9): tests and the prototype never call a
paid model. A live client exists but refuses to start without explicit opt-in and a spending cap (§20.1)."""
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from txg.record.hashing import sha256_bytes

_STEP = re.compile(r"[a-z0-9_]{1,64}")
_MTOK = Decimal(1_000_000)
_CHARS_PER_TOKEN = 3          # conservative estimate for mixed Arabic/English prompts
_MIN_OUTPUT_TOKENS = 1024     # a call that cannot afford this much output is refused, not truncated
_MAX_OUTPUT_TOKENS = 4096


@dataclass(frozen=True)
class Completion:
    text: str
    tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    model: str = ""
    stand_in: bool = False


class ModelClient(Protocol):
    def complete(self, step: str, prompt: str) -> Completion: ...


class MissingRecording(LookupError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class LiveCallsDisabled(RuntimeError):
    pass


def _check_step(step: str) -> str:
    if not _STEP.fullmatch(step):
        raise ValueError(f"invalid step name: {step!r}")
    return step


class ScriptedClient:
    """A labelled stand-in (§9.9): answers come from a deterministic function, never from a model."""

    def __init__(self, answer: Callable[[str, str], str]):
        self._answer = answer

    def complete(self, step: str, prompt: str) -> Completion:
        return Completion(self._answer(step, prompt), model="scripted-stand-in", stand_in=True)


class RecordedClient:
    """Replays stored responses keyed by (step, prompt hash). Never touches the network."""

    def __init__(self, root: Path):
        self._root = root

    def _path(self, step: str, prompt: str) -> Path:
        key = sha256_bytes(f"{_check_step(step)}\n{prompt}".encode())
        return self._root / step / f"{key}.json"

    def has(self, step: str, prompt: str) -> bool:
        return self._path(step, prompt).is_file()

    def complete(self, step: str, prompt: str) -> Completion:
        path = self._path(step, prompt)
        if not path.is_file():
            raise MissingRecording(f"no recorded response for step {step!r}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Completion(raw["text"], raw.get("tokens", 0), Decimal(0), raw.get("model", ""),
                          raw.get("stand_in", False))

    def save(self, step: str, prompt: str, completion: Completion) -> None:
        path = self._path(step, prompt)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {"text": completion.text, "tokens": completion.tokens, "cost_usd": str(completion.cost_usd),
                "model": completion.model, "stand_in": completion.stand_in}
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


class BudgetedClient:
    """Wraps a paid client: replays anything already recorded (a finished paid step is never repeated),
    and stops before a new call once the run's spend reaches the cap (F-20)."""

    def __init__(self, inner: ModelClient, store: RecordedClient, cap_usd: Decimal):
        self._inner, self._store, self._cap = inner, store, cap_usd
        self.spent_usd = Decimal(0)

    def complete(self, step: str, prompt: str) -> Completion:
        if self._store.has(step, prompt):
            return self._store.complete(step, prompt)
        if self.spent_usd >= self._cap:
            raise BudgetExceeded(f"model budget USD {self._cap} reached at step {step!r}; resume later")
        completion = self._inner.complete(step, prompt)
        self.spent_usd += completion.cost_usd
        self._store.save(step, prompt, completion)
        return completion


class LiveClient:
    """OpenAI-compatible live client. Off unless TXG_LIVE_MODEL=1 and token prices are configured, so a
    budget cap can actually be enforced. Never used by tests."""

    def __init__(self, model: str, cap_usd: Decimal):
        if os.environ.get("TXG_LIVE_MODEL") != "1":
            raise LiveCallsDisabled("live model calls need TXG_LIVE_MODEL=1 and the product lead's go-ahead")
        price_in, price_out = os.environ.get("TXG_PRICE_IN_PER_MTOK"), os.environ.get("TXG_PRICE_OUT_PER_MTOK")
        if not price_in or not price_out:
            raise LiveCallsDisabled("set TXG_PRICE_IN_PER_MTOK and TXG_PRICE_OUT_PER_MTOK to enforce the cap")
        from openai import OpenAI  # optional dependency, imported only when live calls are enabled

        self._client = OpenAI()
        self._model, self.cap_usd = model, cap_usd
        self._price_in, self._price_out = Decimal(price_in), Decimal(price_out)
        self.spent_usd = Decimal(0)

    def _output_budget(self, prompt: str) -> int:
        """Largest output this call may produce without passing the cap; refuses calls too small to be useful."""
        est_input_cost = Decimal(len(prompt) // _CHARS_PER_TOKEN + 1) * self._price_in / _MTOK
        remaining = self.cap_usd - self.spent_usd - est_input_cost
        tokens = int(remaining * _MTOK / self._price_out) if remaining > 0 else 0
        if tokens < _MIN_OUTPUT_TOKENS:
            raise BudgetExceeded(f"model budget USD {self.cap_usd} nearly spent (USD {self.spent_usd}); resume later")
        return min(tokens, _MAX_OUTPUT_TOKENS)

    def complete(self, step: str, prompt: str) -> Completion:
        resp = self._client.chat.completions.create(
            model=self._model, messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, max_completion_tokens=self._output_budget(prompt))
        usage = resp.usage
        cost = (Decimal(usage.prompt_tokens) * self._price_in + Decimal(usage.completion_tokens) * self._price_out) / _MTOK
        self.spent_usd += cost
        return Completion(resp.choices[0].message.content or "", usage.total_tokens, cost, self._model)
