"""S10: the target's asking price (SAR 520m, 11.8× FY2025 EBITDA) is above what the evidence supports; the engines
compute the verdict (§14.3–§14.9). Namesakes are never matched by name (R9, F-16)."""
import csv
from pathlib import Path

import pytest

from txg.acquisition.valuation import decide, equity_bridge, identify, load_peers, load_target, peer_multiples

ACQ = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20" / "acquisition"
ASK = 520_000_000


@pytest.fixture(scope="module")
def target():
    if not ACQ.is_dir():
        pytest.skip("acquisition data not present")
    return load_target(ACQ / "data_room" / "TGT-01", name="Example Cold Chain Logistics Co. (made-up)",
                       cr="TEST-CR-T001")


def test_target_identity_is_by_cr_number_never_by_name(target):
    with open(ACQ / "candidates.csv", encoding="utf-8", newline="") as f:
        candidates = list(csv.DictReader(f))
    result = identify(candidates, cr=target.cr, name=target.name)
    assert result.match is None                      # no candidate carries the target's CR number
    assert "CAND-01" in result.namesakes             # same name, different CR: recorded, not matched


def test_statements_foot_and_peers_are_enough(target):
    assert target.checks_passed                      # CK-20: balance sheet balances every year
    multiples = peer_multiples(load_peers(ACQ / "listed_peers.json"))
    assert len(multiples) >= 5                       # CK-17


def test_s10_verdict_is_computed_and_is_not_a_plain_buy(target):
    multiples = peer_multiples(load_peers(ACQ / "listed_peers.json"))
    bridge = equity_bridge(target, year="2025")
    assert bridge.debt_like > 0 and "End-of-service benefits" in bridge.items
    a = decide(target, multiples, asking_ev=ASK, confidence=0.70, futures=4000)
    b = decide(target, multiples, asking_ev=ASK, confidence=0.70, futures=4000)
    assert a == b                                    # reproducible
    assert a.verdict != "Buy" and a.walk_away_ev < ASK
    assert 0 <= a.chance_at_ask < 0.70
    assert a.synergy_gap > 0 and "synergies" in a.notes[0]
