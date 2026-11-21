"""Every fault in §18.3 is handled: each ID maps to tests that exist, or to a stated reason it is out of scope."""
import ast
from pathlib import Path

from tests.faults.matrix import LATER, MATRIX

ENGINE = Path(__file__).resolve().parents[2]


def _defined(node_id: str) -> bool:
    path, _, name = node_id.partition("::")
    file = ENGINE / path
    if not file.is_file():
        return False
    tree = ast.parse(file.read_text(encoding="utf-8"))
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in tree.body)


def test_the_matrix_lists_every_fault_in_the_spec():
    assert sorted(MATRIX) == [f"F-{i:02d}" for i in range(1, 24)]


def test_every_mapped_test_exists():
    missing = [n for tests in MATRIX.values() if isinstance(tests, list) for n in tests if not _defined(n)]
    assert missing == []


def test_only_the_production_connector_faults_are_out_of_scope():
    assert {f for f, tests in MATRIX.items() if isinstance(tests, str)} == {"F-01", "F-02", "F-04"}
    assert all(tests == LATER for tests in MATRIX.values() if isinstance(tests, str))
