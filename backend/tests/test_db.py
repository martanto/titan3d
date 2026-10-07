"""SQLite repositories: job lifecycle, concurrency, recovery, DEM records."""

import threading
from pathlib import Path

import pytest

from titan3d.db.database import init_db
from titan3d.db.repositories import DemRepository, JobRepository


@pytest.fixture
def db(out_path) -> Path:
    p = out_path("test.db")
    for suffix in ("-wal", "-shm"):
        Path(str(p) + suffix).unlink(missing_ok=True)
    init_db(p)
    DemRepository(p).create("d1", "Test DEM", "upload", ["a.tif"])
    return p


def test_dem_lifecycle(db: Path) -> None:
    repo = DemRepository(db)
    rec = repo.get("d1")
    assert rec is not None and rec.status == "processing" and rec.files == ["a.tif"]
    repo.set_ready("d1", "/x/mosaic.tif", {"sha256": "abc"})
    rec = repo.get("d1")
    assert rec is not None and rec.status == "ready" and rec.info == {"sha256": "abc"}
    repo.set_failed("d1", "bad tile")
    assert repo.get("d1").status == "failed"  # type: ignore[union-attr]
    assert [r.id for r in repo.list_all()] == ["d1"]


def test_relocate_dem_paths(db: Path) -> None:
    repo = DemRepository(db)
    old = db.parent / "legacy-data"
    new = db.parent / "moved-data"
    external = db.parent / "legacy-data-other" / "mosaic.tif"
    repo.create("inside", "Inside", "upload", [str(old / "tiles/a.tif"), "b.tif"])
    repo.set_ready("inside", str(old / "dems/inside/mosaic.tif"), {"sha256": "abc"})
    repo.create("outside", "Outside", "upload", [str(external)])
    repo.set_ready("outside", str(external), {})
    assert repo.relocate_paths(old, new) == 1
    moved = repo.get("inside")
    assert moved is not None
    assert moved.mosaic_path == str(new / "dems/inside/mosaic.tif")
    assert moved.files == [str(new / "tiles/a.tif"), "b.tif"]
    assert moved.info == {"sha256": "abc"} and moved.status == "ready"
    assert repo.get("outside").mosaic_path == str(external)  # type: ignore[union-attr]
    assert repo.get("d1").files == ["a.tif"]  # type: ignore[union-attr]
    assert repo.relocate_paths(old, new) == 0


def test_job_lifecycle_and_provenance(db: Path) -> None:
    jobs = JobRepository(db)
    jobs.create("j1", "run", "d1", {"name": "run"}, t_end=100.0)
    assert jobs.queued() == ["j1"]
    assert jobs.claim("j1", pid=123)
    assert not jobs.claim("j1", pid=456), "a job is claimed once"
    jobs.set_started("j1", {"git_commit": "abc", "backend": "numba"}, {"nx": 10})
    jobs.update_progress("j1", {"sim_t": 50.0, "steps": 10, "hmax": 3.0})
    jobs.add_frame("j1", 0, {"t": 0.0})
    jobs.add_frame("j1", 1, {"t": 2.0})
    rec = jobs.get("j1")
    assert rec is not None
    assert rec.status == "running" and rec.progress == 0.5 and rec.hmax == 3.0
    assert rec.provenance == {"git_commit": "abc", "backend": "numba"}
    assert [f["t"] for f in jobs.frames("j1")] == [0.0, 2.0]
    jobs.finish("j1", "completed")
    rec = jobs.get("j1")
    assert rec is not None and rec.status == "completed" and rec.progress == 1.0
    jobs.finish("j1", "failed", "late")  # finished jobs do not change state
    assert jobs.get("j1").status == "completed"  # type: ignore[union-attr]


def test_cancel_queued_and_running(db: Path) -> None:
    jobs = JobRepository(db)
    jobs.create("q", "queued", "d1", {}, 10.0)
    assert jobs.request_cancel("q") == "cancelled"
    jobs.create("r", "running", "d1", {}, 10.0)
    jobs.claim("r", 1)
    assert jobs.request_cancel("r") == "running"
    assert jobs.cancel_requested("r")
    assert jobs.request_cancel("missing") is None


def test_duplicate_parent_link(db: Path) -> None:
    jobs = JobRepository(db)
    jobs.create("a", "a", "d1", {}, 10.0)
    jobs.create("b", "b", "d1", {}, 10.0, parent_job_id="a")
    assert jobs.get("b").parent_job_id == "a"  # type: ignore[union-attr]
    jobs.delete("a")
    assert jobs.get("b").parent_job_id is None  # type: ignore[union-attr]


def test_interrupted_recovery(db: Path) -> None:
    jobs = JobRepository(db)
    jobs.create("x", "x", "d1", {}, 10.0)
    jobs.claim("x", 1)
    assert jobs.mark_stale_interrupted(max_age_s=3600) == []
    assert jobs.mark_all_running_interrupted() == ["x"]
    rec = jobs.get("x")
    assert rec is not None and rec.status == "interrupted" and rec.error


def test_concurrent_reads_during_writes(db: Path) -> None:
    jobs = JobRepository(db)
    jobs.create("w", "w", "d1", {}, 1000.0)
    jobs.claim("w", 1)
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            for k in range(200):
                jobs.update_progress("w", {"sim_t": float(k), "steps": k})
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=writer)
    t.start()
    seen = 0
    while t.is_alive():
        rec = jobs.get("w")
        assert rec is not None
        seen = max(seen, rec.steps)
    t.join()
    assert not errors
    assert jobs.get("w").steps == 199  # type: ignore[union-attr]
