"""Every fact the deck shows, computed by the same engine functions the results API serves (§17.3). The build and the
audit each call `compute_facts()` from scratch, in a throwaway record, so the audit is an independent recomputation.
Mappings are the latest versions the results API uses (engine/runtime/mappings), read only."""
import tempfile
from decimal import Decimal
from pathlib import Path

from txg.api import screens
from txg.api.live import LiveFeed
from txg.api.main import DEFAULT_RUNTIME, DEFAULT_UPLOADS, DEFAULT_ZOHO
from txg.api.service import EngineService
from txg.connector.files import FileConnector
from txg.connector.overlay import OverlayConnector
from txg.deck.facts import Fact, Unit
from txg.ledger.mix import performance_mix_split
from txg.ledger.statements import build_statements, ltm
from txg.mapping.store import MappingStore
from txg.normalise.trial_balance import rebuild_trial_balances
from txg.record.store import EventLog
from txg.stats.calendar import load_holidays
from txg.stats.fdr import DEFAULT_Q, group_trends
from txg.stats.holiday import fit_holiday_model

DEFAULT_OUT = DEFAULT_RUNTIME / "deck"
UNITS: dict[str, Unit] = {"ratio": "pct", "SAR": "sar_m", "days": "days", "x": "x", "count": "count"}
DIVISION = ("EH-05", "EH-06", "EH-07")  # building materials (S5)
STATUS = {"act": "Act", "watch": "Watch", "healthy": "Healthy", "context": "Context", "needs_data": "Needs data"}
TREND = {"slipping": "slipping", "improving": "improving", "steady": "steady"}
Facts = dict[str, Fact]


def open_service(log: EventLog) -> EngineService:
    conn, store = FileConnector(DEFAULT_ZOHO), MappingStore(DEFAULT_RUNTIME / "mappings")
    mappings = {}
    for org in conn.organisations():
        if (version := store.latest(org.company)) is None:
            raise RuntimeError(f"no mapping for {org.company}; start the results API once so it maps the company")
        mappings[org.company] = version.codes()
    service = EngineService(OverlayConnector(conn), mappings, log, uploads_root=DEFAULT_UPLOADS, store=store)
    LiveFeed(service).gate_printed_months()
    return service


def month_label(period: str) -> str:
    from datetime import date
    y, m = map(int, period.split("-"))
    return date(y, m, 1).strftime("%B %Y")


def _put(facts: Facts, fact_id: str, value, unit: Unit, source: str = "") -> None:
    facts[fact_id] = Fact(fact_id, value, unit, source)


def headline(service: EngineService, company: str, period: str) -> dict[str, tuple]:
    """(value, unit, state, status, trend) per KPI, exactly as /companies/{c}/kpis serves them."""
    st = service.status_trend(company, period)
    out = {v.kpi_id: (v.value, v.unit, v.state, *st[v.kpi_id]) for v in service.kpis(company, period)}
    for v, status in service.simulated(company, period):
        out[v.kpi_id] = (v.value, v.unit, v.state, status, None)
    return out


def _kpi_facts(facts: Facts, service: EngineService, company: str, period: str, ids: list[str]) -> None:
    h = headline(service, company, period)
    for kpi_id in ids:
        value, unit, state, status, trend = h[kpi_id]
        key = f"{company}.{kpi_id}"
        if value is not None and state == "ok":
            _put(facts, key, Decimal(value), UNITS.get(unit, "num1"), f"/companies/{company}/kpis {period}")
        _put(facts, f"{key}.status", STATUS[status], "text")
        if trend:
            _put(facts, f"{key}.trend", TREND[trend], "text")


def alarm_counts(tests: dict) -> tuple[int, int]:
    """Slide 4: alarms a fixed 5% threshold would raise, against signals kept under the group-wide false-alarm limit
    (§12.3) — the kept count is what the screens show as slipping or improving, never the steady measures."""
    naive = sum((bad < 0.05) + (good < 0.05) for bad, good in tests.values())
    return naive, sum(trend != "steady" for trend in group_trends(tests).values())


def _group_facts(facts: Facts, service: EngineService, period: str) -> None:
    held = {c for c in service.mappings if service.gate.status_of(c, period).status == "held"}
    acting = [c for c in service.mappings if c not in held and any(
        h[3] == "act" for k, h in headline(service, c, period).items() if k in screens.HEADLINE)]
    tests: dict = {}
    for c in sorted(set(service.mappings) - held):
        tests |= service.signal_tests(c, period)
    _put(facts, "as_of", month_label(period), "text")
    _put(facts, "companies", len(service.mappings), "count", "data: organisations with books")
    _put(facts, "acting_companies", len(acting), "count", "/group")
    _put(facts, "signal_tests", 2 * len(tests), "count", "§12.3 pool: company × KPI × side")
    naive, kept = alarm_counts(tests)
    _put(facts, "naive_alarms", naive, "count", "fixed p < 5%")
    _put(facts, "kept_signals", kept, "count", "Benjamini–Hochberg, as the screens show it")
    _put(facts, "fdr_q", Decimal(str(DEFAULT_Q)), "pct", "stats/fdr.py")


def _s4_facts(facts: Facts, service: EngineService) -> None:
    ctx = service.context("EH-14")
    revenue = {m: float(ctx.income[m].get("4100", 0)) for m in ctx.months if m <= "2026-10"}
    adjusted = fit_holiday_model(revenue, load_holidays()).adjusted(revenue)
    _put(facts, "s4.raw", Decimal(str(round(revenue["2026-03"] / revenue["2025-03"] - 1, 4))), "pct", "EH-14 4100")
    _put(facts, "s4.adjusted", Decimal(str(round(adjusted["2026-03"] / adjusted["2025-03"] - 1, 4))), "pct",
         "holiday model §12.1")


def _s5_facts(facts: Facts, service: EngineService) -> None:
    rev0, rev1, m0, m1 = [], [], [], []
    for company in DIVISION:
        stmts = build_statements(rebuild_trial_balances(service.conn, company), service.mappings[company])
        for month, revs, margins in (("2025-10", rev0, m0), ("2026-10", rev1, m1)):
            revenue = ltm(stmts, month, "revenue")
            revs.append(revenue)
            margins.append(ltm(stmts, month, "gross_profit") / revenue)
    perf, mix = performance_mix_split(rev0, rev1, m0, m1)
    total0 = sum(r * m for r, m in zip(rev0, m0)) / sum(rev0)
    for i, company in enumerate(DIVISION):
        _put(facts, f"s5.{company}.m0", m0[i].quantize(Decimal("0.0001")), "pct", "gross margin LTM Oct 2025")
        _put(facts, f"s5.{company}.m1", m1[i].quantize(Decimal("0.0001")), "pct", "gross margin LTM Oct 2026")
    _put(facts, "s5.division_m0", total0.quantize(Decimal("0.0001")), "pct", "division gross margin LTM Oct 2025")
    _put(facts, "s5.division_m1", (total0 + perf + mix).quantize(Decimal("0.0001")), "pct", "division LTM Oct 2026")
    _put(facts, "s5.performance", perf.quantize(Decimal("0.0001")), "pts", "§12.17")
    _put(facts, "s5.mix", mix.quantize(Decimal("0.0001")), "pts", "§12.17")


def _s1_facts(facts: Facts, service: EngineService, period: str) -> None:
    _kpi_facts(facts, service, "EH-01", period, ["HL-5", "HL-7", "HL-8", "HL-3", "RC-1_days_late", "HL-2"])
    rec = screens.receivables(service, "EH-01", period)
    _put(facts, "EH-01.retention_held", Decimal(rec["retention_held"]), "sar_m", "/receivables")
    cash = screens.cash13(service, "EH-01", period)
    _put(facts, "EH-01.cash_minimum", Decimal(str(cash["minimum"])), "sar_m", "/cash13")
    _put(facts, "EH-01.cash_low_p10", Decimal(str(cash["low_point_p10"])), "sar_m", "/cash13")
    _put(facts, "EH-01.cash_chance_below", Decimal(str(cash["chance_below_minimum"])), "pct", "/cash13")
    for i, week in enumerate(cash["weeks"], start=1):
        _put(facts, f"EH-01.cash_week{i}_p50", Decimal(str(week["p50"])), "sar_m", "/cash13 median")


def _integrity_facts(facts: Facts, service: EngineService) -> None:
    body = screens.integrity(service, "EH-21", "cfo")
    tests = {t["id"]: t for t in body["tests"]}
    _put(facts, "EH-21.IT-02.below", tests["IT-02"]["below"], "count", "/integrity")
    _put(facts, "EH-21.IT-02.above", tests["IT-02"]["above"], "count", "/integrity")
    _put(facts, "EH-21.IT-02.limit", Decimal(tests["IT-02"]["limit"]), "count", "settings.json")
    _put(facts, "EH-21.IT-03.hits", tests["IT-03"]["hits"], "count", "/integrity")
    _put(facts, "EH-21.IT-06.hits", tests["IT-06"]["hits"], "count", "/integrity")
    _put(facts, "EH-21.IT-01.records", tests["IT-01"]["records"], "count", "/integrity")


def _acquisition_facts(facts: Facts) -> None:
    a = screens.acquisition(DEFAULT_UPLOADS)
    d = a["decision"]
    _put(facts, "tgt.verdict", d["verdict"], "text", "/acquisition")
    for key in ("walk_away_ev", "value_p10", "value_p50", "value_p90"):
        _put(facts, f"tgt.{key}", Decimal(str(d[key])), "sar_m", "/acquisition")
    _put(facts, "tgt.ask", Decimal(str(a["ask_ev"])), "sar_m", "deal_TGT-01.json")
    _put(facts, "tgt.chance_at_ask", Decimal(str(d["chance_at_ask"])), "pct", "/acquisition")
    multiples = [p["ev_ebitda"] for p in a["peers"]]
    _put(facts, "tgt.peers", len(multiples), "count", "listed_peers.json")
    _put(facts, "tgt.peer_low", Decimal(str(round(min(multiples), 4))), "x", "/acquisition")
    _put(facts, "tgt.peer_high", Decimal(str(round(max(multiples), 4))), "x", "/acquisition")
    _put(facts, "tgt.candidates", len(a["candidates"]), "count", "candidates.csv")
    _put(facts, "tgt.namesakes", sum(c["identity"].startswith("namesake") for c in a["candidates"]), "count",
         "identity by CR number")


def _catalogue_facts(facts: Facts) -> None:
    from txg.kpi.registry import load_registry
    for kpi_id, entry in load_registry().items():
        _put(facts, f"kpi.{kpi_id}.name", entry.name, "text", "config/kpi_registry.json")


def build_facts(service: EngineService) -> Facts:
    facts: Facts = {}
    _catalogue_facts(facts)
    period = min(service.closed_through(c) for c in service.mappings)
    _group_facts(facts, service, period)
    _s1_facts(facts, service, period)
    _kpi_facts(facts, service, "EH-08", period, ["HL-3", "HL-2"])
    for company in sorted(service.mappings):
        if service.gate.status_of(company, period).status != "held":
            _kpi_facts(facts, service, company, period, ["HL-4_roic"])
    _s4_facts(facts, service)
    _s5_facts(facts, service)
    _integrity_facts(facts, service)
    _acquisition_facts(facts)
    return facts


def compute_facts(_unused: Path | None = None) -> Facts:
    with tempfile.TemporaryDirectory(prefix="txg-deck-") as tmp:
        return build_facts(open_service(EventLog(Path(tmp) / "record.duckdb")))
