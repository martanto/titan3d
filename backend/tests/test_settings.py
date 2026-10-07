"""Storage defaults and explicit overrides."""

from pathlib import Path

from titan3d.config import Settings


def test_default_storage_is_project_root(monkeypatch) -> None:
    monkeypatch.delenv("TITAN3D_DATA_DIR", raising=False)
    settings = Settings(_env_file=None)
    root = Path(__file__).resolve().parents[2] / "data"
    assert settings.data_dir == root
    assert settings.db_path == root / "titan3d.db"
    assert settings.dems_dir == root / "dems"
    assert settings.runs_dir == root / "runs"
    assert settings.logs_dir == root / "logs"


def test_storage_environment_override(monkeypatch, out_path) -> None:
    custom = out_path("custom-data")
    monkeypatch.setenv("TITAN3D_DATA_DIR", str(custom))
    settings = Settings(_env_file=None)
    settings.ensure_dirs()
    assert settings.data_dir == custom
    assert settings.db_path == custom / "titan3d.db"
    assert all(
        p.is_dir() for p in (settings.dems_dir, settings.runs_dir, settings.logs_dir)
    )
