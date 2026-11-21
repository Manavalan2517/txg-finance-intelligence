"""Deliberate breaks (§18.4): each break is applied to a copy of the code, and the tests that own that code MUST
fail. A break that passes means a missing test. Run with `pytest -m slow tests/breaks` (about 15 minutes).

Each break runs the tests that own the broken code rather than the whole suite (the whole suite × 14 would take
hours); the control case proves the copy is what the tests import and that the same tests pass when nothing is
broken. The copy mirrors the project layout (engine/src, with engine/config and data linked in), because the code
finds its configuration and data relative to its own files: a copy without them fails for the wrong reason."""
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Break:
    id: str
    what: str
    edits: tuple[tuple[str, str, str], ...]  # (file under src/txg, exact text, replacement)
    tests: tuple[str, ...]


BREAKS = (
    Break("B-01", "swap numerator and denominator in DSO",
          (("kpi/receivables.py", "return Result(numerator(ctx.facts[m]) / cs3 * _days(w))",
            "return Result(cs3 / numerator(ctx.facts[m]) * _days(w))"),),
          ("tests/oracle/test_kpis_receivables.py",)),
    Break("B-02", "drop the Ramadan regressor",
          (("stats/holiday.py", 'EFFECTS = ("ramadan", "eid_fitr", "eid_adha")', 'EFFECTS = ("eid_fitr", "eid_adha")'),
           ("stats/holiday.py", "*dummies, s.ramadan, s.eid_fitr, s.eid_adha]", "*dummies, s.eid_fitr, s.eid_adha]")),
          ("tests/stories/test_s4_ramadan.py",)),
    Break("B-03", "use a 14-week window for the cash view",
          (("stats/cash13.py", "PATHS, WEEKS, MIN_OWN_HISTORY, HISTORY_DAYS = 10_000, 13, 10, 730",
            "PATHS, WEEKS, MIN_OWN_HISTORY, HISTORY_DAYS = 10_000, 14, 10, 730"),),
          ("tests/integration/test_api_screens.py::test_cash13_fan_has_13_ordered_weeks",)),
    Break("B-04", "use the mean instead of the median for the liquidity low point",
          (("stats/cash13.py", "return float(np.sort(low)[len(low) // 2])", "return float(np.mean(low))"),),
          ("tests/unit/test_cash13_low_point.py",)),
    Break("B-05", "replace the false-alarm limit with a fixed 5% threshold",
          (("stats/fdr.py", "k = max((i for i, t in enumerate(ordered, start=1) if t.p <= i / m * q), default=0)",
            "k = sum(1 for t in ordered if t.p < 0.05)"),),
          ("tests/unit/test_stats.py",)),
    Break("B-06", "flip the sign of the mix term",
          (("ledger/mix.py", "mix = sum(((a - b) * m0 for a, b, m0 in zip(w1, w0, margin0)), Decimal(0))",
            "mix = sum(((b - a) * m0 for a, b, m0 in zip(w1, w0, margin0)), Decimal(0))"),),
          ("tests/stories/test_s5_s6.py::test_perf_mix_hand_example",)),
    Break("B-07", "match intercompany contacts by name instead of identifiers",
          (("ledger/intercompany.py",
            "hit = next((by_id[i] for i in _identifiers(contact) if i in by_id), None)",
            ("hit = next((o.company for o in others if o.name.casefold().removesuffix(' (made-up)') in "
             "contact.get('contact_name', '').casefold()), None)")),),
          ("tests/stories/test_s5_s6.py::test_identifier_disagreement_is_reported_ck19",
           "tests/stories/test_s5_s6.py::test_intercompany_matched_by_identifiers_not_names")),
    Break("B-08", "skip the trial-balance tie-out gate",
          (("normalise/holds.py", "            if not result.tied:", "            if False:"),),
          ("tests/faults/test_holds.py",)),
    Break("B-09", "let a model-typed number through the explanation check",
          (("explain/explainer.py", 'typed = _DIGIT.findall(_REF.sub("", text))', "typed = []"),),
          ("tests/unit/test_explain.py",)),
    Break("B-10", "reuse one seed across companies",
          (("stats/seed.py", 'f"{company}|{period}|{kpi}|{config_version}"', 'f"GROUP|{period}|{kpi}|{config_version}"'),),
          ("tests/unit/test_seed.py",)),
    Break("B-11", "use a peer set below the minimum size",
          (("acquisition/valuation.py", "    if len(out) < MIN_PEERS:", "    if len(out) < 1:"),),
          ("tests/faults/test_faults.py::test_f13_fewer_than_five_peers_are_refused_by_ck17",)),
    Break("B-12", "compute the purchase-price index on unmatched items",
          (("stats/drivers.py", "    matched = [k for k in a if k in b and a[k][1] and b[k][1]]",
            ("    return (sum(v[0] for v in b.values()) / sum(v[1] for v in b.values())) / (sum(v[0] for v in "
             "a.values()) / sum(v[1] for v in a.values())) - 1\n    matched = []")),),
          ("tests/stories/test_s2_purchase_prices.py",)),
    Break("B-13", "apply a material mapping on a single reading",
          (("mapping/runner.py", "    if second is None:\n        return MappingEntry(",
            "    if True:\n        return MappingEntry("),),
          ("tests/stories/test_s13_misc_income.py",)),
    Break("B-14", "publish a held company-month",
          (("api/app.py", '''    def _company_kpis(code: str, period: str) -> list[KpiOut]:
        if (held_detail := _held(code, period)) is not None:''', '''    def _company_kpis(code: str, period: str) -> list[KpiOut]:
        if False and (held_detail := _held(code, period)) is not None:'''),),
          ("tests/integration/test_api.py::test_held_month_is_never_published",)),
)


NOT_A_CATCH = ("FileNotFoundError", "ModuleNotFoundError", "ImportError", "SyntaxError", "IndentationError")


def _copy_with(edits: tuple[tuple[str, str, str], ...], root: Path) -> Path:
    src = root / "engine" / "src"
    shutil.copytree(ENGINE / "src", src, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "engine" / "config").symlink_to(ENGINE / "config", target_is_directory=True)
    (root / "data").symlink_to(ENGINE.parent / "data", target_is_directory=True)
    for rel, old, new in edits:
        path = src / "txg" / rel
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, f"{rel}: the text to break must occur exactly once"
        path.write_text(text.replace(old, new), encoding="utf-8")
    return src


def _run(src: Path, tests: tuple[str, ...]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(src), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(check=False, args=[sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "-p", "no:warnings",
                           "-m", "slow or not slow", *tests], cwd=ENGINE, env=env, capture_output=True, text=True,
                          timeout=1800)


def test_every_break_in_the_spec_is_listed():
    assert [b.id for b in BREAKS] == [f"B-{i:02d}" for i in range(1, 15)]


@pytest.mark.slow
def test_control_the_copy_is_what_the_tests_import_and_unbroken_it_passes(tmp_path: Path):
    src = _copy_with((), tmp_path)
    env = {**os.environ, "PYTHONPATH": str(src)}
    where = subprocess.run([sys.executable, "-c", "import txg; print(txg.__file__)"], env=env, capture_output=True,
                           text=True, check=True).stdout.strip()
    assert where.startswith(str(src))
    every_target = tuple(dict.fromkeys(t for b in BREAKS for t in b.tests))
    result = _run(src, every_target)  # unbroken, every break's tests pass: a failure below is the break's doing
    assert result.returncode == 0, result.stdout[-3000:]


@pytest.mark.slow
@pytest.mark.parametrize("brk", BREAKS, ids=[b.id for b in BREAKS])
def test_the_break_is_caught(brk: Break, tmp_path: Path):
    result = _run(_copy_with(brk.edits, tmp_path), brk.tests)
    assert result.returncode == 1, f"{brk.id} ({brk.what}) was not caught:\n{result.stdout[-3000:]}"
    assert not any(e in result.stdout for e in NOT_A_CATCH), f"{brk.id} failed for another reason:\n{result.stdout[-3000:]}"
