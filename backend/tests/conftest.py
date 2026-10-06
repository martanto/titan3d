"""Shared fixtures. Test outputs are written next to the test files as ``out_*``."""

from pathlib import Path
from collections.abc import Callable

import pytest


TESTS_DIR = Path(__file__).resolve().parent


@pytest.fixture
def out_path() -> Callable[[str], Path]:
    """Return a factory for output paths ``tests/out_<name>`` (old file removed)."""

    def make(name: str) -> Path:
        p = TESTS_DIR / f"out_{name}"
        if p.is_file():
            p.unlink()
        return p

    return make
