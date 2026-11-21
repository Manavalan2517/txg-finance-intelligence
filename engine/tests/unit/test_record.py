"""Task B1: the record is append-only, ULID-keyed and immutable (§6.4, R13)."""
from pathlib import Path

import pydantic
import pytest

from txg.record.events import Actor, Event, Ref
from txg.record.store import EventLog

CODE = Actor(kind="code", id="normaliser", version="0.1.0")


def _event(type_: str = "snapshot.stored", **scope: str) -> Event:
    return Event(type=type_, actor=CODE, scope=scope or {"company": "EH-01", "period": "2026-10"},
                 outputs=[Ref(id="snap_1", hash="ab" * 32)])


def test_append_assigns_sortable_ulid(tmp_path: Path):
    log = EventLog(tmp_path / "record.duckdb")
    first = log.append(_event())
    second = log.append(_event())
    assert len(first) == 26 and len(second) == 26
    assert first < second


def test_events_are_immutable():
    e = _event()
    with pytest.raises(pydantic.ValidationError):
        e.type = "tb.tied"  # type: ignore[misc]


def test_log_exposes_no_update_or_delete():
    public = {n for n in dir(EventLog) if not n.startswith("_")}
    assert not public & {"update", "delete", "remove", "set", "edit"}


def test_by_scope_returns_events_in_order_with_ids(tmp_path: Path):
    log = EventLog(tmp_path / "record.duckdb")
    a = log.append(_event("tb.tied", company="EH-01", period="2026-09"))
    log.append(_event("tb.tied", company="EH-02", period="2026-09"))
    b = log.append(_event("hold.started", company="EH-01", period="2026-10"))
    got = log.by_scope(company="EH-01")
    assert [e.event_id for e in got] == [a, b]
    assert [e.type for e in got] == ["tb.tied", "hold.started"]
    assert got[1].outputs[0].hash == "ab" * 32


def test_record_survives_reopen(tmp_path: Path):
    path = tmp_path / "record.duckdb"
    eid = EventLog(path).append(_event())
    assert [e.event_id for e in EventLog(path).by_scope(company="EH-01")] == [eid]


def test_append_does_not_mutate_input_event(tmp_path: Path):
    e = _event()
    EventLog(tmp_path / "record.duckdb").append(e)
    assert e.event_id is None


def test_log_serves_concurrent_readers_and_writers(tmp_path: Path):
    """The results API answers requests on worker threads; the record must not refuse a parallel call."""
    from concurrent.futures import ThreadPoolExecutor
    log = EventLog(tmp_path / "r.duckdb")

    def work(i: int) -> int:
        log.append(_event(company=f"C{i % 3}"))
        return len(log.by_scope(company=f"C{i % 3}"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, range(200)))
    assert len(results) == 200
    ids = [e.event_id for c in ("C0", "C1", "C2") for e in log.by_scope(company=c)]
    assert len(ids) == len(set(ids)) == 200
