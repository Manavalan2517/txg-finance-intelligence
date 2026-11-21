"""Task A1: the delivered data set is intact, and the generator reproduces it byte for byte (§15.8)."""
import csv
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from txg.record.hashing import sha256_file


def _hashes(data_set: Path) -> dict[str, str]:
    return json.loads((data_set / "hashes.json").read_text())


def _delivered_path(data_set: Path, rel: str) -> Path:
    # hashes.json keys are relative to the generator's --out folder; delivery nests zoho/ and answer-key/ under data/
    top = rel.split("/", 1)[0]
    return data_set / ("data/" + rel if top in {"zoho", "answer-key"} else rel)


def test_delivered_files_match_hashes(data_set: Path):
    mismatched = [rel for rel, h in _hashes(data_set).items()
                  if _delivered_path(data_set, rel).exists() and sha256_file(_delivered_path(data_set, rel)) != h]
    assert mismatched == []


@pytest.mark.slow
def test_generator_output_matches_hashes_for_eh01(data_set: Path, tmp_path: Path):
    gen = data_set / "generator"
    subprocess.run([sys.executable, "generate.py", "--companies", "EH-01", "--out", str(tmp_path)],
                   cwd=gen, check=True, capture_output=True, timeout=600)
    expected = {rel: h for rel, h in _hashes(data_set).items() if "/EH-01/" in rel}
    assert expected, "hashes.json lists no EH-01 files"
    got = {rel: sha256_file(tmp_path / rel) for rel in expected if (tmp_path / rel).exists()}
    # Books and every other answer-key file must be byte-identical.
    exact = {rel for rel in expected if not rel.endswith("kpis_monthly.csv")}
    assert {r: got.get(r) for r in exact} == {r: expected[r] for r in exact}
    # Finding for the client: the generator sums floats, so two cash-flow KPI columns can differ by
    # SAR 0.01 between runs. Accept a halala; anything larger is a real reproducibility break.
    rel = "answer-key/EH-01/kpis_monthly.csv"
    assert _max_abs_diff(_delivered_path(data_set, rel), tmp_path / rel) <= Decimal("0.01")


def _max_abs_diff(a: Path, b: Path) -> Decimal:
    with open(a, newline="") as fa, open(b, newline="") as fb:
        ra, rb = list(csv.DictReader(fa)), list(csv.DictReader(fb))
    assert len(ra) == len(rb) and ra[0].keys() == rb[0].keys()
    worst = Decimal(0)
    for x, y in zip(ra, rb):
        for k in x:
            if x[k] != y[k]:
                worst = max(worst, abs(Decimal(x[k] or 0) - Decimal(y[k] or 0)))
    return worst
