"""Shared test fixtures. The Example Holding data set is client material copied into ../data."""
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_SET = PROJECT_ROOT / "data" / "example-holding-2026-11-20"


@pytest.fixture(scope="session")
def data_set() -> Path:
    root = Path(os.environ.get("TXG_DATA_SET", DEFAULT_DATA_SET))
    if not (root / "data" / "zoho").is_dir():
        pytest.skip(f"Example Holding data set not found at {root}")
    return root


@pytest.fixture(scope="session")
def zoho_root(data_set: Path) -> Path:
    return data_set / "data" / "zoho"


@pytest.fixture(scope="session")
def answer_key(data_set: Path) -> Path:
    return data_set / "data" / "answer-key"
