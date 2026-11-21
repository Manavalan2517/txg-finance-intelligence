"""The deck's numbers audit (§17.3, §17.6): every number on every slide is a fact reference, recomputed and compared;
a number on a slide that no fact accounts for fails the build; every slide carries the made-up label; TXG's name
appears only on the cover and the roll-out slide."""
from decimal import Decimal
from pathlib import Path

import pytest

from txg.deck.audit import audit_deck
from txg.deck.build import DeckWriter
from txg.deck.facts import Fact
from txg.deck.manifest import Manifest

FACTS = {
    "walk_away": Fact("walk_away", Decimal("401000000"), "sar_m"),
    "chance_at_ask": Fact("chance_at_ask", Decimal("0.12"), "pct"),
    "eh01_days_late": Fact("eh01_days_late", Decimal("41.27"), "days"),
}


def _deck(tmp_path: Path, extra_text: str = "", txg_on: int = 1, label: bool = True) -> tuple[Path, Manifest]:
    w = DeckWriter(run_id="test", label=label)
    s = w.slide(f"The price that still creates value: SAR {w.n(FACTS['walk_away'])}", txg=txg_on == 1)
    w.text(s, f"A {w.n(FACTS['chance_at_ask'])} chance that paying the ask creates value. {extra_text}")
    w.bar_chart(s, "Days late", ["EH-01"], [FACTS["eh01_days_late"]])
    s2 = w.slide("How we roll out", txg=txg_on == 2)
    w.text(s2, "Pilot of three companies, then all, then acquisitions (HL-1, S12, §12.3, EH-01, A1).")
    path = tmp_path / "deck.pptx"
    w.save(path)
    return path, w.manifest


def test_a_clean_deck_passes(tmp_path: Path):
    path, manifest = _deck(tmp_path)
    assert audit_deck(path, manifest, FACTS) == []


def test_every_number_is_recorded_with_its_fact_and_text(tmp_path: Path):
    _, manifest = _deck(tmp_path)
    assert {(e.slide, e.fact_id, e.text) for e in manifest.entries} >= {
        (1, "walk_away", "401m"), (1, "chance_at_ask", "12%"), (1, "eh01_days_late", "41")}


def test_a_recomputed_fact_that_differs_fails(tmp_path: Path):
    path, manifest = _deck(tmp_path)
    now = FACTS | {"walk_away": Fact("walk_away", Decimal("399000000"), "sar_m")}
    findings = audit_deck(path, manifest, now)
    assert any("walk_away" in f and "slide 1" in f for f in findings)


def test_a_fact_that_no_longer_exists_fails(tmp_path: Path):
    path, manifest = _deck(tmp_path)
    now = {k: v for k, v in FACTS.items() if k != "chance_at_ask"}
    assert any("chance_at_ask" in f for f in audit_deck(path, manifest, now))


def test_a_typed_number_without_a_fact_fails(tmp_path: Path):
    path, manifest = _deck(tmp_path, extra_text="Revenue grew 7.5% last year.")
    findings = audit_deck(path, manifest, FACTS)
    assert any("7.5" in f and "slide 1" in f for f in findings)


def test_a_chart_value_that_differs_from_its_fact_fails(tmp_path: Path):
    path, manifest = _deck(tmp_path)
    now = FACTS | {"eh01_days_late": Fact("eh01_days_late", Decimal("12.00"), "days")}
    assert any("eh01_days_late" in f for f in audit_deck(path, manifest, now))


def test_a_slide_without_the_made_up_label_fails(tmp_path: Path):
    path, manifest = _deck(tmp_path, label=False)
    assert any("made-up" in f for f in audit_deck(path, manifest, FACTS))


def test_txg_named_on_a_number_slide_fails(tmp_path: Path):
    path, manifest = _deck(tmp_path, txg_on=1)
    assert audit_deck(path, manifest, FACTS, txg_slides={1}) == []
    assert any("TXG" in f for f in audit_deck(path, manifest, FACTS, txg_slides={2}))


@pytest.mark.parametrize(("fact", "text"), [
    (Fact("a", Decimal("401000000"), "sar_m"), "401m"),
    (Fact("a", Decimal("17312345.6"), "sar_m"), "17.3m"),
    (Fact("a", Decimal("-0.293"), "pct"), "−29.3%"),
    (Fact("a", Decimal("0.12"), "pct"), "12%"),
    (Fact("a", Decimal("11.8"), "x"), "11.8x"),
    (Fact("a", 29, "count"), "29"),
    (Fact("a", Decimal("41.6"), "days"), "42"),
    (Fact("a", "October 2026", "text"), "October 2026"),
])
def test_facts_use_the_deck_number_style(fact: Fact, text: str):
    assert fact.text() == text


def test_slide_4_counts_kept_signals_not_every_measure():
    from txg.deck.engine import alarm_counts
    # 500 measures × 2 sides = 1,000 tests: the §18.2 worked example's five smallest p-values on the bad side, the rest noise above 5%
    small = [0.00002, 0.0001, 0.0002, 0.004, 0.02]
    tests = {("EH-01", f"K{i}"): (p, 0.9) for i, p in enumerate(small)}
    tests |= {("EH-02", f"K{i}"): (0.06 + i / 10_000, 0.9) for i in range(495)}
    naive, kept = alarm_counts(tests)
    assert (naive, kept) == (5, 3)


def test_bar_charts_draw_negative_values_below_zero_and_positive_charts_start_at_zero(tmp_path: Path):
    """Render check finding: without an explicit invertIfNegative=0, LibreOffice draws a negative bar above zero
    (EH-14's −10.9% showed as +10.87) and PowerPoint draws it hollow; and a truncated axis exaggerates differences."""
    w = DeckWriter(run_id="test")
    s = w.slide("Charts")
    mixed = w.bar_chart(s, "Mixed", ["a", "b"], [Fact("a", Decimal("-0.1087"), "pct"), Fact("b", Decimal("0.1066"), "pct")])
    counts = w.bar_chart(s, "Counts", ["a", "b"], [Fact("c", 84, "count"), Fact("d", 76, "count")])
    assert mixed.plots[0].series[0].invert_if_negative is False
    assert counts.value_axis.minimum_scale == 0
