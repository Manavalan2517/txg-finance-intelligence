"""The change processor (C19, §6.3): apply one change, recompute only the KPIs whose registry inputs it touches,
flag edits into closed or locked months (IT-04), and re-gate a month when a trial balance is uploaded."""
from dataclasses import dataclass, field
from pathlib import Path

from txg import __version__
from txg.connector.changefeed import ChangeEvent
from txg.connector.overlay import OverlayConnector
from txg.kpi.cashflow import build_cash_flows
from txg.kpi.context import build_context
from txg.kpi.facts import build_month_facts
from txg.kpi.registry import KpiValue, load_registry
from txg.normalise.holds import PeriodGate, PeriodStatus
from txg.normalise.printed_tb import load_printed_tb, to_printed_basis
from txg.normalise.trial_balance import rebuild_trial_balances
from txg.record.events import Actor, Event
from txg.record.store import EventLog

_ACTOR = Actor(kind="code", id="change_processor", version=__version__)
CASH_KPIS = frozenset({"HL-5", "CS-1", "CFO_pre_interest_zakat"})  # read the direct-method cash flows
_DOC_FAMILY = {"invoices": {"invoices", "payments", "creditnotes", "tags.retention"},
               "customerpayments": {"invoices", "payments"}, "creditnotes": {"invoices", "creditnotes"},
               "bills": {"bills", "vendorpayments"}, "vendorpayments": {"bills", "vendorpayments"}}
_GROUPS = {"pl.all": "4567", "pl.ebitda": "456", "pl.ebit": "456", "bs.debt": ("2170", "2175", "2210"),
           "bs.leases": ("2180", "2220"), "bs.equity": "3", "bs.invested_capital": "123"}


@dataclass(frozen=True)
class ApplyResult:
    seq: int
    company: str
    months: list[str] = field(default_factory=list)
    kpis_recomputed: frozenset[str] = frozenset()
    values: dict[str, KpiValue] = field(default_factory=dict)
    provisional: bool = False
    after_close: str = ""
    period_status: str = ""


def _token_hits(token: str, codes: set[str], family: set[str]) -> bool:
    if token in family:
        return True
    if token in _GROUPS:
        g = _GROUPS[token]
        return any(c in g for c in codes) if isinstance(g, tuple) else any(c[0] in g for c in codes)
    kind, _, code = token.partition(".")
    if kind in ("pl", "bs") and code:
        return any(c.startswith(code.rstrip("x")) for c in codes) if code.endswith("x") else code in codes
    return False


def affected_kpis(codes: set[str], record_type: str) -> frozenset[str]:
    family = _DOC_FAMILY.get(record_type, set())
    registry = load_registry()
    hit = {k for k, e in registry.items() if any(_token_hits(t, codes, family) for t in e.inputs)}
    changed = True
    while changed:  # KPIs built from other KPIs (e.g. HL-6 from RC-1, CS-3, PY-2_dpo)
        more = {k for k, e in registry.items() if k not in hit and any(t in hit for t in e.inputs)}
        hit |= more
        changed = bool(more)
    return frozenset(hit)


def check_upload_month(event_month: str, report_month: str) -> None:
    if event_month != report_month:
        raise ValueError(f"upload is for {event_month} but the report is as of {report_month}")


class ChangeProcessor:
    def __init__(self, conn: OverlayConnector, log: EventLog, mappings: dict[str, dict[str, str]], uploads_root: Path):
        self.conn, self.log, self.mappings, self.uploads = conn, log, mappings, uploads_root
        self.gate = PeriodGate(log)

    def _locks(self, company: str) -> list[tuple[str, str]]:
        return [(r.data["lock_date"], r.data["locked_on"]) for r in self.conn.iter_records(company, "transactionlocks")]

    def closed_through(self, company: str) -> str:
        return max((d for d, _ in self._locks(company)), default="0000-00")[:7]

    def upload_path(self, event: ChangeEvent) -> Path:
        root = self.uploads.resolve()
        path = (root / event.file).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"upload {event.zoho_id} points outside the uploads folder")
        return path

    def close_month(self, company: str, month: str, printed_path: Path) -> PeriodStatus:
        mapping = self.mappings[company]
        retained = {a for a, c in mapping.items() if c == "3300"}
        tbs = rebuild_trial_balances(self.conn, company)
        printed = load_printed_tb(printed_path, self.conn, company)
        check_upload_month(month, printed.month)
        return self.gate.evaluate(to_printed_basis(self.conn, company, tbs, month, retained), printed,
                                  closed_through=self.closed_through(company))

    def _after_close(self, event: ChangeEvent) -> str:
        dates = sorted({p["date"] for p in (*event.postings, *event.postings_before)})
        if not dates:
            return ""
        when = event.at.date().isoformat()
        if any(lock >= dates[0] and on <= when for lock, on in self._locks(event.org)):
            return "edited despite the lock"
        return "edited after close" if dates[0][:7] <= self.closed_through(event.org) else ""

    def _emit(self, type_: str, event: ChangeEvent, **detail: str) -> None:
        self.log.append(Event(type=type_, actor=_ACTOR, scope={"company": event.org, "seq": str(event.seq)},
                              detail={k: v for k, v in detail.items() if v}))

    def _recheck_closed(self, company: str, tbs: dict, postings) -> None:
        """F-23: a closed month that a change edits is checked again at once. Without a fresh printed trial balance
        from Zoho it is recorded as balanced (closed, not yet tied); a month that no longer balances is held."""
        closed = self.closed_through(company)
        for month in sorted({p["date"][:7] for p in postings}):
            if month <= closed and month in tbs:
                self.gate.evaluate(tbs[month], None, closed_through=closed)

    def apply(self, event: ChangeEvent) -> ApplyResult:
        if event.op == "upload":
            status = self.close_month(event.org, event.month, self.upload_path(event))
            self._emit("upload.applied", event, month=event.month, status=status.status)
            return ApplyResult(event.seq, event.org, [event.month], period_status=status.status)
        after_close = self._after_close(event)
        self.conn.apply_change(event)
        mapping = self.mappings[event.org]
        postings = (*event.postings, *event.postings_before)
        codes = {mapping[p["account_id"]] for p in postings if p["account_id"] in mapping}
        kpis = affected_kpis(codes, event.record_type)
        tbs = rebuild_trial_balances(self.conn, event.org)
        if after_close:
            self._recheck_closed(event.org, tbs, postings)
        first = min(p["date"][:7] for p in postings) if postings else max(tbs)
        months = [m for m in sorted(tbs) if m >= first]
        needs_facts = any(t in _DOC_FAMILY.get(event.record_type, ()) for k in kpis for t in load_registry()[k].inputs)
        needs_cash = bool(kpis & CASH_KPIS)
        ctx = build_context(event.org, tbs, mapping, facts=build_month_facts(self.conn, event.org) if needs_facts else None,
                            cash_flows=build_cash_flows(self.conn, event.org, mapping) if needs_cash else None)
        registry, latest = load_registry(), months[-1]
        values = {}
        for k in kpis:
            r = registry[k].function(ctx, latest)
            values[k] = KpiValue(event.org, latest, k, r.value, registry[k].unit, r.state, r.detail)
        self._emit("change.applied", event, op=event.op, record_type=event.record_type, after_close=after_close,
                   kpis=",".join(sorted(kpis)))
        return ApplyResult(event.seq, event.org, months, kpis, values, latest > self.closed_through(event.org),
                           after_close)
