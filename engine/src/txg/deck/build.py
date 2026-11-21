"""Build the deck from the engine's results (§17): `python -m txg.deck.build [out_dir]` (default
engine/runtime/deck; screens are read from <out_dir>/screens, captured by `npm run deck:screens` in prototype/).
Writes deck.pptx, manifest.json (every number with its fact) and facts.json. Regenerate after any data or
configuration change; never edit the deck by hand."""
import hashlib
import json
import sys
from pathlib import Path

from txg.deck.engine import DEFAULT_OUT, Facts, compute_facts
from txg.deck.manifest import Manifest
from txg.deck.slides import SECTIONS
from txg.deck.writer import DeckWriter

__all__ = ["DeckWriter", "build_deck", "run_id"]


def run_id(facts: Facts) -> str:
    """The engine run the deck shows, as a short hash of every fact: the same results give the same ID (CK-18)."""
    body = json.dumps(sorted((k, str(f.value)) for k, f in facts.items()), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def build_deck(facts: Facts, out: Path, screens: Path) -> Manifest:
    w = DeckWriter(run_id(facts))
    w.screens = screens
    for section in SECTIONS:
        section(w, facts)
    out.mkdir(parents=True, exist_ok=True)
    w.save(out / "deck.pptx")
    w.manifest.save(out / "manifest.json")
    (out / "facts.json").write_text(json.dumps({k: {"value": str(f.value), "unit": f.unit, "text": f.text(),
                                                    "source": f.source} for k, f in sorted(facts.items())},
                                               indent=1, ensure_ascii=False), encoding="utf-8")
    return w.manifest


def main(argv: list[str] | None = None) -> int:
    out = Path((argv or sys.argv[1:] or [str(DEFAULT_OUT)])[0])
    manifest = build_deck(compute_facts(), out, out / "screens")
    slides = max(e.slide for e in manifest.entries)
    print(f"deck.pptx written: {len(manifest.entries)} numbers on {len({e.slide for e in manifest.entries})} "
          f"slides (last numbered slide {slides}); run {manifest.run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
