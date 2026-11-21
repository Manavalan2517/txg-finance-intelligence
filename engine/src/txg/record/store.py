"""The append-only record (C18). The public API has no update or delete: corrections are new events."""
import re
import threading
from pathlib import Path

import duckdb
from ulid import ULID

from txg.record.events import Event, utc_now

_SCOPE_KEY = re.compile(r"[a-z_]{1,32}")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR PRIMARY KEY,
    type VARCHAR NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    scope JSON NOT NULL,
    body JSON NOT NULL
)
"""


class EventLog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = duckdb.connect(str(path))
        self._lock = threading.Lock()  # the API answers on worker threads; one connection serves one call at a time
        self._db.execute(_SCHEMA)
        row = self._db.execute("SELECT max(event_id) FROM events").fetchone()
        self._last = row[0] if row and row[0] else ""

    def _next_id(self) -> str:
        candidate = str(ULID())
        if candidate <= self._last:  # same millisecond: keep ids strictly increasing
            candidate = str(ULID.from_int(int(ULID.from_str(self._last)) + 1))
        self._last = candidate
        return candidate

    def append(self, event: Event) -> str:
        with self._lock:
            stored = event.model_copy(update={"event_id": self._next_id(), "at": event.at or utc_now()})
            self._db.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                [stored.event_id, stored.type, stored.at, stored.model_dump_json(include={"scope"}),
                 stored.model_dump_json()],
            )
        return stored.event_id

    def by_scope(self, **scope: str) -> list[Event]:
        clauses, params = [], []
        for key, value in scope.items():
            if not _SCOPE_KEY.fullmatch(key):
                raise ValueError(f"invalid scope key: {key!r}")
            clauses.append(f"json_extract_string(scope, '$.scope.{key}') = ?")
            params.append(value)
        where = " AND ".join(clauses) if clauses else "TRUE"
        with self._lock:
            rows = self._db.execute(f"SELECT body FROM events WHERE {where} ORDER BY event_id", params).fetchall()
        return [Event.model_validate_json(r[0]) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
