"""Live updates (§6.3, §16.8). The change feed posts each change here (the client's `replay.py play --post URL`; in
production, Zoho's webhooks). The change processor applies it, only that company's numbers are rebuilt, and every
open screen is told over a server-sent event stream so it can refresh without a reload."""
import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from txg.api.service import EngineService
from txg.changes.processor import ApplyResult, ChangeProcessor
from txg.connector.changefeed import ChangeEvent

log = logging.getLogger("txg.api.live")
Subscriber = Callable[[dict], None]


class ChangeBroker:
    """Fan-out of change notices to every open stream. Thread-safe; a subscriber that fails is dropped."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[int, Subscriber] = {}
        self._next = 0

    @property
    def count(self) -> int:
        return len(self._subscribers)

    def subscribe(self, send: Subscriber) -> Callable[[], None]:
        with self._lock:
            token, self._next = self._next, self._next + 1
            self._subscribers = {**self._subscribers, token: send}

        def leave() -> None:
            with self._lock:
                self._subscribers = {k: v for k, v in self._subscribers.items() if k != token}
        return leave

    def publish(self, message: dict) -> None:
        for token, send in list(self._subscribers.items()):
            try:
                send(message)
            except Exception:  # a closed stream must never stop the others
                log.warning("dropping a live subscriber that failed", exc_info=True)
                with self._lock:
                    self._subscribers = {k: v for k, v in self._subscribers.items() if k != token}


def notice(result: ApplyResult, role: str) -> dict:
    """What a screen is told about a change: which company, months and measures moved. Never figures, and the
    integrity flag (IT-04, "edited after close") only for the CFO (§13)."""
    body = {"seq": result.seq, "company": result.company, "months": list(result.months),
            "kpis": sorted(result.kpis_recomputed), "provisional": result.provisional,
            "period_status": result.period_status}
    if role == "cfo" and result.after_close:
        body["after_close"] = result.after_close
    return body


@dataclass
class LiveFeed:
    service: EngineService
    token: str | None = None
    heartbeat_seconds: float = 15.0
    broker: ChangeBroker = field(default_factory=ChangeBroker)

    def __post_init__(self) -> None:
        if self.service.uploads is None:
            raise ValueError("live updates need the uploads folder (printed trial balances, uploads in the feed)")
        if not hasattr(self.service.conn, "apply_change"):
            raise ValueError("live updates need an overlay connector")
        self.processor = ChangeProcessor(self.service.conn, self.service.log, self.service.mappings,
                                         uploads_root=self.service.uploads)
        self._apply_lock = threading.Lock()

    def accepts(self, token: str | None) -> bool:
        return bool(self.token) and token == self.token

    def gate_printed_months(self, companies: Iterable[str] | None = None) -> None:
        """Tie every closed month that has a printed trial balance and is not yet on the record (CK-03, §7.4). A
        month that does not tie is held automatically (S12). Feed-only corrected uploads are left for the feed."""
        for company in companies or list(self.service.mappings):
            folder = self.service.uploads / "uploads" / company / "trial_balances"
            closed = self.service.closed_through(company)
            for path in sorted(folder.glob("trial_balance_*.csv")) if folder.is_dir() else ():
                month = path.stem.removeprefix("trial_balance_")
                if "corrected" in month or month > closed:
                    continue
                if self.service.gate.status_of(company, month).status == "open":
                    self.processor.close_month(company, month, path)

    def apply(self, event: ChangeEvent) -> ApplyResult:
        """Apply one change in order, rebuild that company's latest closed month so the refresh is fast, then tell
        every open screen."""
        with self._apply_lock:
            result = self.processor.apply(event)
            self.service.forget_stale(event.org)
            period = self.service.closed_through(event.org)
            if self.service.gate.status_of(event.org, period).status != "held":
                self.service.status_trend(event.org, period)
        self.broker.publish(notice(result, "cfo"))  # each stream strips what its viewer may not see (for_role)
        return result


def for_role(message: dict, role: str) -> dict:
    return message if role == "cfo" else {k: v for k, v in message.items() if k != "after_close"}
