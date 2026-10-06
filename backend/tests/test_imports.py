"""Import every titan3d module in a fresh interpreter to catch circular imports."""

import pkgutil
import subprocess
import sys

import pytest

import titan3d


MODULES = sorted(
    m.name for m in pkgutil.walk_packages(titan3d.__path__, prefix="titan3d.")
)


def test_modules_found() -> None:
    assert "titan3d.config" in MODULES


@pytest.mark.parametrize("module", MODULES)
def test_import_in_fresh_interpreter(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
