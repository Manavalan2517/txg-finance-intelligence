"""The numbers audit (§17.3, §17.6): recompute every fact from the engine and compare it with what each slide shows.
Fails on any mismatch, on any number a slide shows that no fact accounts for, on a slide without the made-up label,
and on TXG's name anywhere but the cover and the roll-out slide.

    python -m txg.deck.audit [deck_dir]     (default engine/runtime/deck; exit 1 on any finding)
"""
import re
import sys
from collections.abc import Collection, Mapping
from pathlib import Path

from pptx import Presentation

from txg.deck.facts import Fact
from txg.deck.manifest import Manifest
from txg.deck.writer import LABEL, chart_value

TXG_SLIDES = frozenset({1, 22})  # cover and roll-out plan (§17.4)
# Identifiers are names, not numbers: KPI and check IDs, stories, sections, appendices, companies, targets.
IDENTIFIER = re.compile(r"\b(?:[A-Z]{1,4}-\d+[A-Za-z0-9_]*|S\d{1,2}|A[1-5]|D\.\d|R\d{1,2}|C\d{1,2}|L\d{1,2}|W\d{1,2})\b|§\d+(?:\.\d+)*")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
FIXED_SHAPES = {"slide_number"}  # generated, never data


def _texts(slide) -> list[str]:
    out = []
    for shape in slide.shapes:
        if shape.name in FIXED_SHAPES:
            continue
        if shape.has_text_frame:
            out.append(shape.text_frame.text)
        if getattr(shape, "has_table", False) and shape.has_table:
            out += [cell.text for row in shape.table.rows for cell in row.cells]
        if getattr(shape, "has_chart", False) and shape.has_chart:  # titles and category labels are slide text too
            chart = shape.chart
            out.append(chart.chart_title.text_frame.text if chart.has_title else "")
            out += [str(c) for plot in chart.plots for c in plot.categories]
    return out


def _chart_values(slide) -> list[float]:
    return [round(float(v), 6) for shape in slide.shapes if getattr(shape, "has_chart", False) and shape.has_chart
            for plot in shape.chart.plots for series in plot.series for v in series.values]


def _check_entries(manifest: Manifest, facts: Mapping[str, Fact]) -> list[str]:
    findings = []
    for e in manifest.entries:
        now = facts.get(e.fact_id)
        if now is None:
            findings.append(f"slide {e.slide}: fact {e.fact_id} no longer exists in the engine results")
        elif now.text() != e.text or str(now.value) != e.value:
            findings.append(f"slide {e.slide}: {e.fact_id} shows {e.text!r} ({e.value}) but the engine now gives "
                            f"{now.text()!r} ({now.value})")
    return findings


def _check_slide(index: int, slide, manifest: Manifest, facts: Mapping[str, Fact], txg_slides: Collection[int]):
    findings, texts = [], _texts(slide)
    joined = "\n".join(texts)
    if LABEL not in joined:
        findings.append(f"slide {index}: the made-up data label is missing")
    if "TXG" in joined and index not in txg_slides:
        findings.append(f"slide {index}: TXG's name appears on a slide that is not the cover or the roll-out plan")
    shown = [e.text for e in manifest.on_slide(index) if e.where == "text"]
    scrubbed = IDENTIFIER.sub(" ", joined.replace(manifest.run_id, " "))
    for token in NUMBER.findall(scrubbed):
        if not any(token in text for text in shown):
            findings.append(f"slide {index}: the number {token!r} is not traced to any fact")
    charted = [e for e in manifest.on_slide(index) if e.where == "chart"]
    values = _chart_values(slide)
    if len(values) != len(charted):
        findings.append(f"slide {index}: {len(values)} chart values but {len(charted)} chart facts in the manifest")
    for e, v in zip(charted, values):
        if e.fact_id in facts and facts[e.fact_id].number() is not None and chart_value(facts[e.fact_id]) != v:
            findings.append(f"slide {index}: chart value {v} for {e.fact_id} differs from the engine's "
                            f"{chart_value(facts[e.fact_id])}")
    return findings


def audit_deck(path: Path, manifest: Manifest, facts: Mapping[str, Fact],
               txg_slides: Collection[int] = TXG_SLIDES) -> list[str]:
    findings = _check_entries(manifest, facts)
    for index, slide in enumerate(Presentation(str(path)).slides, start=1):
        findings += _check_slide(index, slide, manifest, facts, txg_slides)
    return findings


def main(argv: list[str] | None = None) -> int:
    from txg.deck.engine import DEFAULT_OUT, compute_facts
    folder = Path((argv or sys.argv[1:] or [str(DEFAULT_OUT)])[0])
    manifest = Manifest.load(folder / "manifest.json")
    facts = compute_facts(folder / "audit-record")  # recomputed from scratch, in its own record
    findings = audit_deck(folder / "deck.pptx", manifest, facts)
    for f in findings:
        print(f"FAIL {f}")
    print(f"{len(manifest.entries)} numbers on {len({e.slide for e in manifest.entries})} slides checked; "
          f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
