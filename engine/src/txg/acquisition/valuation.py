"""Acquisition workspace, first slice (§14): identity by identifiers, the target's statements (recorded reading of the
data room as a labelled stand-in for the document reader), trading comps from listed peers, the equity bridge and
the decision maths (chance of creating value at a price, walk-away price at the board's confidence, verdict).
Synergies are model views with evidence (§14.6); until that step runs they are left out and the verdict says so."""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from txg.stats.seed import seed_for

MIN_PEERS = 5
DEBT_LIKE = ("Borrowings", "Lease liabilities", "End-of-service benefits", "Zakat payable")


@dataclass(frozen=True)
class Target:
    id: str
    name: str
    cr: str
    years: dict
    checks_passed: bool


@dataclass(frozen=True)
class Identity:
    match: str | None
    namesakes: tuple[str, ...]


@dataclass(frozen=True)
class Bridge:
    debt_like: float
    cash: float
    items: dict


@dataclass(frozen=True)
class Decision:
    verdict: str
    walk_away_ev: float
    chance_at_ask: float
    value_p10: float
    value_p50: float
    value_p90: float
    synergy_gap: float
    notes: tuple[str, ...]


def _balances(year: dict) -> bool:
    assets = sum(year["assets"].values())
    claims = sum(year["liabilities"].values()) + sum(year["equity"].values())
    return abs(assets - claims) <= 1.0


def load_target(room: Path, name: str, cr: str) -> Target:
    """The deal team names the target and its CR number (§14.2); statements come from the data room."""
    years = json.loads((room / "06_statements_structured.json").read_text(encoding="utf-8"))
    return Target(room.name, name, cr, years, all(_balances(y) for y in years.values()))


def identify(candidates: list[dict], cr: str, name: str) -> Identity:
    match = next((c["candidate_id"] for c in candidates if c.get("cr_number") == cr), None)
    namesakes = tuple(c["candidate_id"] for c in candidates
                      if c["name"].casefold() == name.casefold() and c.get("cr_number") != cr)
    return Identity(match, namesakes)


def price_refusal(target: Target, offered_cr: str) -> str | None:
    """Why the company offered for pricing must not be priced, or None. Statements that do not foot get no price
    (CK-20, F-15); nor does a company whose CR number is not the named target's, however alike the names (a namesake
    offered as the target, F-16, R9). A namesake elsewhere in the search universe does not stop the real target."""
    if not target.checks_passed:
        return "No price: the target's statements do not foot (CK-20); the pages are being re-read"
    if offered_cr != target.cr:
        return ("No price: the company offered matches only a namesake (same name, different CR number); "
                "the same-company reader's verdict is recorded")
    return None


def load_peers(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["peers"]


def peer_multiples(peers: list[dict], year: str = "2025") -> list[float]:
    """EV ÷ EBITDA computed by code: EV = price × shares + net debt (leases excluded on both sides)."""
    out = []
    for p in peers:
        ebitda = p["statements"][year]["ebitda"]
        if ebitda > 0:
            out.append((p["share_price_sar"] * p["shares_outstanding"] + p["net_debt_excl_leases_sar"]) / ebitda)
    if len(out) < MIN_PEERS:
        raise ValueError(f"only {len(out)} peers; at least {MIN_PEERS} are needed (CK-17)")
    return sorted(out)


def equity_bridge(target: Target, year: str) -> Bridge:
    liabilities = target.years[year]["liabilities"]
    items = {k: v for k, v in liabilities.items() if k in DEBT_LIKE}
    return Bridge(sum(items.values()), target.years[year]["assets"]["Cash and cash equivalents"], items)


def decide(target: Target, multiples: list[float], asking_ev: float, confidence: float = 0.70,
           futures: int = 4000, year: str = "2025") -> Decision:
    """Futures: a peer multiple (bootstrap) × target EBITDA with the target's own year-on-year EBITDA variability."""
    rng = np.random.default_rng(seed_for(target.id, year, "acquisition"))
    ebitda = [target.years[y]["ebitda"] for y in sorted(target.years)]
    growth = np.diff(np.log(ebitda)) if len(ebitda) > 1 else np.array([0.0])
    shock = rng.normal(0.0, float(np.std(growth)) if len(growth) > 1 else 0.05, futures)
    values = rng.choice(np.array(multiples), futures) * ebitda[-1] * np.exp(shock)
    chance = float(np.mean(values >= asking_ev))
    walk_away = float(np.quantile(values, 1 - confidence))
    verdict = ("Buy" if chance >= confidence else
               f"Buy at or below SAR {walk_away / 1e6:.0f}m" if walk_away > 0 else "Walk away")
    notes = ("synergies not yet assessed (model view with evidence pending, §14.6); standalone value only",
             "Zakat assessment under appeal is in the notes, not the structured statements: needs the document reader")
    p10, p50, p90 = (float(np.percentile(values, q)) for q in (10, 50, 90))
    return Decision(verdict, walk_away, chance, p10, p50, p90, asking_ev - walk_away, notes)
