"""Event types for the record (§6.4). Events are immutable; corrections are new events pointing at old ones."""
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Actor(_Frozen):
    kind: Literal["code", "model", "person"]
    id: str
    version: str


class Ref(_Frozen):
    id: str
    hash: str


class ModelCall(_Frozen):
    name: str
    prompt_hash: str
    response_hash: str
    tokens: int = 0
    cost_usd: float = 0.0


class Event(_Frozen):
    type: str = Field(min_length=1)
    actor: Actor
    scope: dict[str, str] = Field(default_factory=dict)
    inputs: list[Ref] = Field(default_factory=list)
    outputs: list[Ref] = Field(default_factory=list)
    params: dict[str, str] = Field(default_factory=dict)
    model: ModelCall | None = None
    parents: list[str] = Field(default_factory=list)
    detail: dict[str, str] = Field(default_factory=dict)
    event_id: str | None = None
    at: datetime | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)
