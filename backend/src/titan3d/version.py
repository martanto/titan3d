"""Package version and source revision, recorded in run provenance."""

import os
import subprocess
from pathlib import Path
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version


def package_version() -> str:
    """Return the installed ``titan3d`` version."""
    try:
        return version("titan3d")
    except PackageNotFoundError:
        return "0+unknown"


@lru_cache
def git_commit() -> str:
    """Return the short git commit of the source tree.

    ``TITAN3D_GIT_COMMIT`` overrides the lookup (used in Docker images, which
    have no ``.git`` directory).
    """
    env = os.environ.get("TITAN3D_GIT_COMMIT")
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
