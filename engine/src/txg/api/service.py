"""The engine behind the results API: builds and caches each company's context; never serves a held month."""
import json
import threading
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from txg.connector.base import Connector, OrgRef
from txg.kpi.cashflow import build_cash_flows
from txg.kpi.context import KpiContext, build_context
from txg.kpi.facts import build_month_facts
from txg.kpi.registry import KpiValue, compute_all, load_registry
from txg.mapping.store import MappingStore, MappingVersion, VersionConflict
from txg.normalise.holds import PeriodGate
from txg.normalise.trial_balance import rebuild_trial_balances
from txg.record.events import Actor, Event
from txg.record.store import EventLog
from txg.stats.cash13 import CashForecast, simulate_13_weeks
from txg.stats.fdr import group_trends
from txg.stats.status import level_status
from txg.stats.xmr import normal_range, signal_p

_ACTOR = Actor(kind="code", id="results_api", version="0.1.0")


def _graded(entry, ctx: KpiContext, months: list[str]) -> list[float]:
    values = [entry.function(ctx, m).value for m in months]
    return [] if values[-1] is None else [float(v) for v in values if v is not None]


class OverrideRejected(ValueError):
    """A reviewer's override fails the mapping checks; the message is safe to show."""


class EngineService:
    def __init__(self, conn: Connector, mappings: Mapping[str, Mapping[str, str]], log: EventLog,
                 uploads_root: Path | None = None, store: MappingStore | None = None):
        self.conn, self.log, self.uploads, self.store = conn, log, uploads_root, store
        self.mappings: dict[str, Mapping[str, str]] = dict(mappings)
        self.actor = _ACTOR
        self._sims: dict[tuple, list] = {}
        self._forecasts: dict[tuple, CashForecast | None] = {}
        self.gate = PeriodGate(log)
        self._contexts: dict[tuple, KpiContext] = {}
        self._generation: dict[str, int] = {}  # bumped by each mapping override
        self._lock = threading.RLock()
        self._series_cache: dict[tuple, dict[str, list[float]]] = {}
        self._trends: dict[tuple, dict[tuple[str, str], str]] = {}

    def companies(self) -> list[OrgRef]:
        return [o for o in self.conn.organisations() if o.company in self.mappings]

    def knows(self, company: str) -> bool:
        return company in self.mappings

    def _data_key(self, company: str) -> tuple[int, int]:
        """What a company's numbers depend on: the books' version and the company's mapping generation. Every
        cache key carries it, so a build that started before a change can never be served after it. A live overlay
        counts versions per company, so a change to one company leaves the others' caches valid."""
        version_of = getattr(self.conn, "version_of", None)
        books = version_of(company) if version_of else getattr(self.conn, "version", 0)
        return books, self._generation.get(company, 0)

    def _context_key(self, company: str) -> tuple:
        return (company, *self._data_key(company))

    def context(self, company: str) -> KpiContext:
        with self._lock:  # read the mapping and its generation together
            key, mapping = self._context_key(company), self.mappings[company]
        if key not in self._contexts:
            tbs = rebuild_trial_balances(self.conn, company)
            self._contexts[key] = build_context(company, tbs, mapping, facts=build_month_facts(self.conn, company),
                                                cash_flows=build_cash_flows(self.conn, company, mapping))
        return self._contexts[key]

    def forget_stale(self, company: str) -> None:
        """Drop the company's cache entries built on older data, and the group trends, after a change (§6.3): the
        caches are keyed by data version, so old entries are never served, but they would otherwise pile up."""
        current = self._data_key(company)
        with self._lock:
            for cache in (self._contexts, self._series_cache, self._sims, self._forecasts):
                for key in [k for k in list(cache) if k[0] == company and tuple(k[-2:]) != current]:
                    cache.pop(key, None)
            self._trends.clear()

    def closed_through(self, company: str) -> str:
        locks = [r.data["lock_date"] for r in self.conn.iter_records(company, "transactionlocks")]
        return max(locks, default="0000-00")[:7]

    def kpis(self, company: str, period: str) -> list[KpiValue]:
        return list(compute_all(self.context(company), period).values())

    def _series(self, company: str, period: str) -> dict[str, list[float]]:
        """Each KPI's values over the 27 months ending at `period`, months without a value left out; empty for a
        KPI whose `period` value is missing (n.m. or needs data), so it is never graded on an earlier month."""
        key = (company, period, *self._data_key(company))
        if key not in self._series_cache:
            ctx = self.context(company)
            months = [m for m in ctx.months if m <= period][-27:]
            self._series_cache[key] = {} if not months or months[-1] != period else {
                kpi_id: _graded(entry, ctx, months) for kpi_id, entry in load_registry().items()}
        return self._series_cache[key]

    def signal_tests(self, company: str, period: str) -> dict[tuple[str, str], tuple[float, float]]:
        """Bad-side and good-side signal p-values for every trend KPI of one company in one month (§12.3)."""
        out = {}
        for kpi_id, series in self._series(company, period).items():
            entry = load_registry()[kpi_id]
            window = int(entry.extra.get("window", 1))
            if not entry.extra.get("trend") or (nr := normal_range(series, window=window)) is None:
                continue
            bad, good = ("high", "low") if entry.direction == "lower_better" else ("low", "high")
            out[(company, kpi_id)] = (signal_p(series, nr, bad)[0], signal_p(series, nr, good)[0])
        return out

    def group_trends(self, period: str) -> dict[tuple[str, str], str]:
        """Trends for the month under the group-wide false-alarm limit (§12.3, q = 10%): every company's tests
        together, held months left out (B-14)."""
        key = (period, tuple((c, *self._data_key(c)) for c in sorted(self.mappings)))
        if key not in self._trends:
            tests: dict[tuple[str, str], tuple[float, float]] = {}
            for company in self.mappings:
                if self.gate.status_of(company, period).status != "held":
                    tests |= self.signal_tests(company, period)
            self._trends[key] = group_trends(tests)
        return self._trends[key]

    def status_trend(self, company: str, period: str) -> dict[str, tuple[str, str | None]]:
        """Where each KPI stands and where it is heading (§10.3–10.4). Until peer bands exist, peer-band and
        hard-limit KPIs fall back to their own normal range (§12.5, CK-17); trends survive the group-wide
        false-alarm limit."""
        all_series, trends, out = self._series(company, period), self.group_trends(period), {}
        for kpi_id, entry in load_registry().items():
            series = all_series.get(kpi_id)
            kind = (entry.extra.get("level_yardstick") or {}).get("type", "none")
            if not series:
                out[kpi_id] = ("needs_data", None)
                continue
            if kind in ("own_normal", "peer_band", "hard_limit"):
                yardstick = {"type": "own_normal", "direction": entry.direction,
                             "window": entry.extra.get("window", 1)}
                status = level_status(series[-1], yardstick, series[:-1]).value
            else:
                status = "context"
            has_trend = entry.extra.get("trend") and normal_range(
                series, window=int(entry.extra.get("window", 1))) is not None
            out[kpi_id] = (status, trends.get((company, kpi_id), "steady") if has_trend else None)
        return out

    def simulated(self, company: str, period: str) -> list[tuple[KpiValue, str]]:
        """HL-2 and HL-7 (§12.7, §12.8) for the latest closed month, when the uploads exist. 2,000 paths keep the
        page fast; the deck and month close use the full 10,000."""
        if self.uploads is None or period != self.closed_through(company):
            return []
        key = (company, period, *self._data_key(company))
        if key not in self._sims:
            self._sims[key] = self._simulate(company, period)
        return self._sims[key]

    def _simulate(self, company: str, period: str) -> list[tuple[KpiValue, str]]:
        from txg.stats.budget_sim import chance_of_hitting_budget
        from txg.uploads.budgets import load_budgets
        ctx, out = self.context(company), []
        budgets = self.uploads / "uploads" / company / "budgets"
        if budgets.is_dir():
            b = chance_of_hitting_budget(ctx, load_budgets(budgets), period, paths=2000)
            status = "act" if b.chance < 0.30 else "watch" if b.chance < 0.60 else "healthy"
            out.append((KpiValue(company, period, "HL-2", Decimal(str(b.chance)), "ratio", "ok"), status))
        cf = self.cash_forecast(company, period)
        if cf is not None:
            p = cf.chance_below_minimum
            status = "act" if p >= 0.20 else "watch" if p >= 0.05 else "healthy"
            out.append((KpiValue(company, period, "HL-7", Decimal(str(cf.low_point_p50)), "SAR", "ok"), status))
        return out

    def facility_terms(self, company: str):
        """Facility terms read from the company's facility letters (PDF), checked (CK-11, covenants read twice); the
        client's structured terms only where a company has no letters. None when neither exists."""
        from txg.uploads.facilities import load_recorded_facilities
        from txg.uploads.facility_reader import load_facility_letters
        if self.uploads is None:
            return None
        letters = self.uploads / "uploads" / company / "facility_letters"
        if letters.is_dir() and any(letters.glob("*.pdf")):
            return load_facility_letters(letters)
        recorded = self.uploads / "answer-key-additions" / company / "facilities.json"
        return load_recorded_facilities(recorded) if recorded.is_file() else None

    def cash_forecast(self, company: str, period: str) -> CashForecast | None:
        """The 13-week cash forecast (§12.8) for the latest closed month, when facility terms exist. 2,000 paths."""
        if self.uploads is None or period != self.closed_through(company):
            return None
        key = (company, period, *self._data_key(company))
        if key not in self._forecasts:
            terms = self.facility_terms(company)
            if terms is None:
                self._forecasts[key] = None
            else:
                settings = self.uploads / "uploads" / company / "settings.json"
                policy = json.loads(settings.read_text())["minimum_cash_policy_sar"] if settings.is_file() else 0
                minimum = next((c.threshold for c in terms.covenants if c.test == "cash_plus_undrawn_min"),
                               Decimal(str(policy)))
                self._forecasts[key] = simulate_13_weeks(self.conn, self.context(company), terms, period,
                                                         minimum=minimum, paths=2000)
        return self._forecasts[key]

    def mapping_version(self, company: str) -> MappingVersion:
        if self.store is None or (version := self.store.latest(company)) is None:
            raise LookupError(f"no mapping versions for {company}")
        return version

    def override_mapping(self, company: str, account_id: str, std_code: str, reason: str,
                         person: str) -> MappingVersion:
        """A reviewer's override (§9.10): a new mapping version; the company's numbers are rebuilt on it."""
        if self.store is None:
            raise LookupError("no mapping store")
        with self._lock:  # one override at a time; the record and the generation move together with the save
            try:
                version = self.store.override(company, account_id, std_code, reason, person)
            except ValueError as e:  # the standard-chart and Zoho-type checks (§9.5)
                raise OverrideRejected(str(e)) from None
            except VersionConflict:
                raise OverrideRejected("Another change to this mapping was saved at the same moment; reload the "
                                       "page and try again.") from None
            self.log.append(Event(type="mapping.overridden",
                                  actor=Actor(kind="person", id=person, version="prototype"), scope={"company": company},
                                  detail={"account_id": account_id, "std_code": std_code,
                                          "version": str(version.version)}))
            self.mappings[company] = version.codes()
            self._generation[company] = self._generation.get(company, 0) + 1
        return version

