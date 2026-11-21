"""The correctness gate (§3.5, §9.10): a company-month whose data fails a check is held automatically and
released automatically when it passes. No person is ever needed to release a hold."""
from dataclasses import dataclass
from typing import Literal

from txg import __version__
from txg.normalise.trial_balance import TrialBalance, tie_out
from txg.record.events import Actor, Event
from txg.record.store import EventLog

Status = Literal["open", "closed", "tied", "held"]
_GATE = Actor(kind="code", id="period_gate", version=__version__)
_STATUS_BY_EVENT: dict[str, Status] = {"tb.tied": "tied", "tb.balanced": "closed", "hold.started": "held"}

NOT_BALANCED = "trial balance does not balance"
NOT_TIED = "trial balance does not tie to the printed trial balance"


@dataclass(frozen=True)
class PeriodStatus:
    company: str
    month: str
    status: Status
    reason: str = ""
    tie_source: Literal["printed_tb", "none"] = "none"


class PeriodGate:
    def __init__(self, log: EventLog):
        self._log = log

    def _emit(self, type_: str, company: str, month: str, **detail: str) -> None:
        self._log.append(Event(type=type_, actor=_GATE, scope={"company": company, "period": month}, detail=detail))

    def status_of(self, company: str, month: str) -> PeriodStatus:
        status: Status = "open"
        reason, source = "", "none"
        for e in self._log.by_scope(company=company, period=month):
            if e.type in _STATUS_BY_EVENT:
                status = _STATUS_BY_EVENT[e.type]
                reason = e.detail.get("reason", "")
                source = "printed_tb" if e.type == "tb.tied" else "none"
        return PeriodStatus(company, month, status, reason, source)  # type: ignore[arg-type]

    def evaluate(self, tb: TrialBalance, printed: TrialBalance | None,
                 closed_through: str | None = None) -> PeriodStatus:
        """Gate one company-month. Months after `closed_through` (the last locked month) stay open: their figures
        are live and provisional, and they are never recorded as closed (§6.3)."""
        company, month = tb.company, tb.month
        was_held = self.status_of(company, month).status == "held"
        if not tb.is_balanced:
            return self._hold(company, month, "tb.unbalanced", NOT_BALANCED, was_held, str(tb.imbalance))
        if closed_through is not None and month > closed_through:
            return PeriodStatus(company, month, "open")
        if printed is not None:
            result = tie_out(tb, printed)
            if not result.tied:
                worst = max(result.differences.values(), key=abs)
                return self._hold(company, month, "tb.mismatch", NOT_TIED, was_held, str(worst))
            self._emit("tb.tied", company, month)
            outcome = PeriodStatus(company, month, "tied", tie_source="printed_tb")
        else:
            self._emit("tb.balanced", company, month)
            outcome = PeriodStatus(company, month, "closed")
        if was_held:
            self._emit("hold.released", company, month)
        return outcome

    def _hold(self, company: str, month: str, finding: str, reason: str, was_held: bool, amount: str) -> PeriodStatus:
        self._emit(finding, company, month, amount=amount)
        if not was_held:
            self._emit("hold.started", company, month, reason=reason)
        return PeriodStatus(company, month, "held", reason)

    def last_good_month(self, company: str, before: str) -> str | None:
        months = sorted({e.scope["period"] for e in self._log.by_scope(company=company)
                         if e.scope.get("period", "") < before}, reverse=True)
        return next((m for m in months if self.status_of(company, m).status in ("tied", "closed")), None)
