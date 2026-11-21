"""Payloads for the prototype screens (§11, §13, §14, §16): group grid, KPI series, 13-week cash, receivables,
integrity, mapping review and the acquisition workspace. Code computes everything; screens only display it."""
import csv
import json
import math
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from txg.acquisition.valuation import (
    decide,
    equity_bridge,
    identify,
    load_peers,
    load_target,
    peer_multiples,
    price_refusal,
)
from txg.api.service import EngineService
from txg.integrity.tests import back_dated, benford_first_two, bunching_below_limit, unusual_postings
from txg.kpi.facts import receivable_ageing
from txg.kpi.registry import load_registry
from txg.ledger.chart import CONFIG_DIR
from txg.record.events import Event
from txg.stats.xmr import normal_range

HEADLINE = ("HL-1_raw", "HL-2", "HL-3", "HL-4_roic", "HL-5", "HL-6", "HL-7", "HL-8")
TOP_CUSTOMERS = 10
LIST_LIMIT = 50


def series(service: EngineService, company: str, kpi_id: str, period: str) -> dict:
    """A KPI's last 27 months with the normal range from the same series the status uses (§12.2)."""
    entry = load_registry()[kpi_id]
    ctx = service.context(company)
    months = [m for m in ctx.months if m <= period][-27:]
    values = [entry.function(ctx, m).value for m in months]
    nr = normal_range([float(v) for v in values if v is not None], window=int(entry.extra.get("window", 1)))
    return {"kpi_id": kpi_id, "name": entry.name, "unit": entry.unit, "direction": entry.direction,
            "months": months, "values": [None if v is None else float(v) for v in values],
            "centre": nr.centre if nr else None, "lower": nr.lower if nr else None, "upper": nr.upper if nr else None}


def cash13(service: EngineService, company: str, period: str) -> dict | None:
    forecast = service.cash_forecast(company, period)
    if forecast is None:
        return None
    return {"opening": forecast.opening, "minimum": forecast.minimum,
            "weeks": [{"start": w.start.isoformat(), "p10": w.p10, "p50": w.p50, "p90": w.p90} for w in forecast.weeks],
            "low_point_p50": forecast.low_point_p50, "low_point_p10": forecast.low_point_p10,
            "chance_below_minimum": forecast.chance_below_minimum}


def _contact_names(service: EngineService, company: str) -> dict[str, str]:
    return {r.data["contact_id"]: r.data.get("contact_name", "") for r in service.conn.iter_records(company, "contacts")}


def receivables(service: EngineService, company: str, period: str) -> dict:
    buckets, held, _ = receivable_ageing(service.conn, company, period)
    ctx = service.context(company)
    window = ctx.window(period, 12) or []
    sales: dict[str, Decimal] = defaultdict(Decimal)
    for m in window:
        for c, v in (ctx.facts[m].customer_sales.items() if m in ctx.facts else ()):
            sales[c] += v
    total = sum((v for v in sales.values() if v > 0), Decimal(0))
    names = _contact_names(service, company)
    cent = Decimal("0.01")
    top = sorted(((c, v) for c, v in sales.items() if v > 0), key=lambda cv: (-cv[1], cv[0]))[:TOP_CUSTOMERS]
    customers = [{"customer_id": c, "name": names.get(c, c), "sales_sar": str(v.quantize(cent)),
                  "share": float(v / total)} for c, v in top]
    return {"ageing": [{"bucket": b, "sar": str(v.quantize(cent))} for b, v in buckets.items()],
            "retention_held": str(held.quantize(cent)), "customers": customers,
            "customers_total_sar": str(total.quantize(cent))}


def _approval_limit(service: EngineService, company: str) -> float | None:
    if service.uploads is None:
        return None
    path = service.uploads / "uploads" / company / "settings.json"
    return float(json.loads(path.read_text(encoding="utf-8"))["approval_limit_sar"]) if path.is_file() else None


def integrity(service: EngineService, company: str, viewer_role: str) -> dict:
    """The CFO integrity page (§13): 'worth a look', never an accusation. Every view is logged (§6.6)."""
    service.log.append(Event(type="integrity.viewed", actor=service.actor, scope={"company": company},
                             detail={"role": viewer_role}))
    bills = [float(r.data["total"]) * float(r.data.get("exchange_rate") or 1)
             for r in service.conn.iter_records(company, "bills")]
    benford = benford_first_two(bills)
    digits = Counter(int(f"{a:.15e}".replace(".", "")[:2]) for a in bills if a >= 10)
    n = sum(digits.values()) or 1
    late = sorted(back_dated(service.conn, company, "journals"), key=lambda x: (-x.lag_days, x.record_id))
    unusual = unusual_postings(service.conn, company)
    tests = [{"id": "IT-01", "name": "Benford first-two digits (bills)", "mad": round(benford.mad, 5),
              "records": benford.n, "result": benford.conformity}]
    limit = _approval_limit(service, company)
    if limit:
        b = bunching_below_limit(bills, limit)
        tests.append({"id": "IT-02", "name": "Bills just below the approval limit", "limit": int(limit),
                      "below": b.below, "above": b.above, "p": b.p, "flagged": b.flagged})
    tests += [{"id": "IT-03", "name": "Back-dated into closed months (journals)", "hits": len(late)},
              {"id": "IT-06", "name": "Weekend or late-night postings by rarely-posting users", "hits": len(unusual)}]
    return {"company": company, "framing": "worth a look", "tests": tests,
            "benford": [{"digits": d, "actual": digits.get(d, 0) / n, "expected": math.log10(1 + 1 / d)}
                        for d in range(10, 100)],
            "back_dated": [{"record_id": x.record_id, "dated": x.dated.isoformat(), "created": x.created.isoformat(),
                            "lag_days": x.lag_days} for x in late[:LIST_LIMIT]],
            "unusual": [{"record_id": x.record_id, "user_id": x.user_id, "created": x.created.isoformat(),
                         "reason": x.reason} for x in unusual[:LIST_LIMIT]]}


def mappings(service: EngineService, company: str) -> dict:
    version = service.mapping_version(company)
    entries = version.unreviewed_first()
    return {"company": company, "version": version.version, "reason": version.reason,
            "unreviewed": sum(1 for e in entries if e.unreviewed),
            "entries": [e.model_dump(mode="json") for e in entries[:LIST_LIMIT]]}


def acquisition(uploads: Path) -> dict:
    deal = json.loads((CONFIG_DIR / "deal_TGT-01.json").read_text(encoding="utf-8"))
    room = uploads / "acquisition"
    target = load_target(room / "data_room" / deal["target_id"], name=deal["name"], cr=deal["cr_number"])
    peers = load_peers(room / "listed_peers.json")
    multiples = peer_multiples(peers, deal["year"])
    decision = decide(target, multiples, asking_ev=deal["ask_ev_sar"], confidence=deal["board_confidence"],
                      year=deal["year"])
    with open(room / "candidates.csv", encoding="utf-8", newline="") as f:
        candidates = list(csv.DictReader(f))
    who = identify(candidates, cr=target.cr, name=target.name)
    if (refusal := price_refusal(target, offered_cr=deal["cr_number"])) is not None:
        decision = decision.__class__(refusal, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, (refusal,))
    bridge = equity_bridge(target, deal["year"])
    return {
        "target": {"id": target.id, "name": target.name, "cr_number": target.cr, "checks_passed": target.checks_passed,
                   "ebitda": {y: target.years[y]["ebitda"] for y in sorted(target.years)}},
        "ask_ev": deal["ask_ev_sar"], "board_confidence": deal["board_confidence"],
        "decision": {"verdict": decision.verdict, "walk_away_ev": decision.walk_away_ev,
                     "chance_at_ask": decision.chance_at_ask, "value_p10": decision.value_p10,
                     "value_p50": decision.value_p50, "value_p90": decision.value_p90,
                     "synergy_gap": decision.synergy_gap, "notes": list(decision.notes)},
        "bridge": {"debt_like": bridge.debt_like, "cash": bridge.cash, "items": bridge.items},
        "peers": [{"name": p["name"], "ticker": p["ticker"],
                   "ev_ebitda": (p["share_price_sar"] * p["shares_outstanding"] + p["net_debt_excl_leases_sar"])
                   / p["statements"][deal["year"]]["ebitda"]} for p in peers
                  if p["statements"][deal["year"]]["ebitda"] > 0],
        "candidates": [{"candidate_id": c["candidate_id"], "name": c["name"], "city": c["city"],
                        "region": c["region"], "revenue_band_sar_m": c["revenue_band_sar_m"],
                        "cr_number": c["cr_number"],
                        "identity": ("match by CR number" if c["candidate_id"] == who.match else
                                     "namesake: different CR number" if c["candidate_id"] in who.namesakes else
                                     "")} for c in candidates]}
