"""CK-18, the replay check (§6.5, §9.8): results are keyed by (company, period, snapshot set, mapping version,
configuration version, seed). The first run records the result hash; a re-run with the same key must give the same
hash. A different hash is a CK-18 alert and the run is marked non-reproducible until explained (F-18)."""
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from txg import __version__
from txg.ledger.chart import CONFIG_DIR
from txg.record.events import Actor, Event
from txg.record.store import EventLog

_ACTOR = Actor(kind="code", id="replay_check", version=__version__)
Status = Literal["recorded", "reproducible", "non_reproducible"]


@dataclass(frozen=True)
class ReplayKey:
    company: str
    period: str
    snapshots: str
    mapping_version: str
    config_version: str
    seed: str


@dataclass(frozen=True)
class ReplayOutcome:
    status: Status
    expected: str
    got: str


def result_hash(values: Mapping) -> str:
    """SHA-256 of the results in a canonical form: sorted by KPI, values as exact decimal strings."""
    rows = sorted((k, None if v.value is None else str(v.value), v.unit, v.state) for k, v in values.items())
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode("utf-8")).hexdigest()


def config_version(folder: Path = CONFIG_DIR) -> str:
    """A short hash of every configuration file, so a configuration change is a new key, never a mismatch."""
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(path.relative_to(folder).as_posix().encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def _scope(key: ReplayKey) -> dict[str, str]:
    return {k: v for k, v in asdict(key).items()}


def check_replay(log: EventLog, key: ReplayKey, digest: str) -> ReplayOutcome:
    scope = _scope(key)
    events = [e for e in log.by_scope(company=key.company, period=key.period) if e.scope == scope]
    recorded = next((e.params["hash"] for e in events if e.type == "replay.recorded"), None)
    flagged = any(e.type == "run.non_reproducible" for e in events) and not any(
        e.type == "run.explained" for e in events)
    if recorded is None:
        log.append(Event(type="replay.recorded", actor=_ACTOR, scope=scope, params={"hash": digest}))
        return ReplayOutcome("recorded", digest, digest)
    if recorded != digest:
        log.append(Event(type="ck18.alert", actor=_ACTOR, scope=scope, params={"expected": recorded, "got": digest}))
        log.append(Event(type="run.non_reproducible", actor=_ACTOR, scope=scope, params={"got": digest}))
        return ReplayOutcome("non_reproducible", recorded, digest)
    return ReplayOutcome("non_reproducible" if flagged else "reproducible", recorded, digest)
