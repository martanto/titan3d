"""Typed data access for DEMs and simulation jobs (the only module that writes SQL)."""

import json
import sqlite3
from typing import Any, Literal
from pathlib import Path
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass

from titan3d.db.database import connect, session


DemSource = Literal["builtin", "upload"]
DemStatus = Literal["processing", "ready", "failed"]
JobStatus = Literal[
    "queued", "running", "completed", "failed", "cancelled", "interrupted"
]

ACTIVE = ("queued", "running")
FINISHED = ("completed", "failed", "cancelled", "interrupted")


def now_iso() -> str:
    """Current UTC time as ISO-8601 with seconds."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _loads(text: str | None) -> Any:
    return None if text is None else json.loads(text)


@dataclass(frozen=True)
class DemRecord:
    """A registered DEM."""

    id: str
    name: str
    source: DemSource
    status: DemStatus
    mosaic_path: str | None
    files: list[str]
    info: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "DemRecord":
        """Build from a database row."""
        return cls(
            id=r["id"],
            name=r["name"],
            source=r["source"],
            status=r["status"],
            mosaic_path=r["mosaic_path"],
            files=_loads(r["files_json"]) or [],
            info=_loads(r["info_json"]),
            error=r["error"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )


class DemRepository:
    """CRUD for the ``dems`` table."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def create(
        self, dem_id: str, name: str, source: str, files: list[str]
    ) -> DemRecord:
        """Insert a DEM in ``processing`` state."""
        ts = now_iso()
        with session(self.db_path) as c:
            c.execute(
                "INSERT INTO dems (id, name, source, status, files_json, created_at, "
                "updated_at) VALUES (?, ?, ?, 'processing', ?, ?, ?)",
                (dem_id, name, source, json.dumps(files), ts, ts),
            )
        rec = self.get(dem_id)
        assert rec is not None
        return rec

    def get(self, dem_id: str) -> DemRecord | None:
        """Fetch one DEM."""
        conn = connect(self.db_path)
        try:
            r = conn.execute("SELECT * FROM dems WHERE id = ?", (dem_id,)).fetchone()
        finally:
            conn.close()
        return None if r is None else DemRecord.from_row(r)

    def list_all(self) -> list[DemRecord]:
        """All DEMs, built-in first, then newest first."""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM dems ORDER BY source = 'builtin' DESC, created_at DESC"
            ).fetchall()
        finally:
            conn.close()
        return [DemRecord.from_row(r) for r in rows]

    def set_processing(self, dem_id: str) -> None:
        """Return a DEM to ``processing`` (e.g. re-stitching)."""
        with session(self.db_path) as c:
            c.execute(
                "UPDATE dems SET status = 'processing', error = NULL, updated_at = ? "
                "WHERE id = ?",
                (now_iso(), dem_id),
            )

    def set_ready(self, dem_id: str, mosaic_path: str, info: dict[str, Any]) -> None:
        """Mark a DEM stitched and usable."""
        with session(self.db_path) as c:
            c.execute(
                "UPDATE dems SET status = 'ready', mosaic_path = ?, info_json = ?, "
                "error = NULL, updated_at = ? WHERE id = ?",
                (mosaic_path, json.dumps(info), now_iso(), dem_id),
            )

    def set_failed(self, dem_id: str, error: str) -> None:
        """Mark a DEM unusable."""
        with session(self.db_path) as c:
            c.execute(
                "UPDATE dems SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                (error, now_iso(), dem_id),
            )

    def delete(self, dem_id: str) -> None:
        """Remove a DEM row (jobs referencing it block deletion)."""
        with session(self.db_path) as c:
            c.execute("DELETE FROM dems WHERE id = ?", (dem_id,))

    def job_count(self, dem_id: str) -> int:
        """Number of jobs that used this DEM."""
        conn = connect(self.db_path)
        try:
            r = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE dem_id = ?", (dem_id,)
            ).fetchone()
        finally:
            conn.close()
        return int(r["n"])


@dataclass(frozen=True)
class JobRecord:
    """A simulation job and its latest progress."""

    id: str
    name: str
    dem_id: str
    status: JobStatus
    scenario: dict[str, Any]
    provenance: dict[str, Any] | None
    grid: dict[str, Any] | None
    parent_job_id: str | None
    pid: int | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    heartbeat_at: str | None
    sim_t: float
    t_end: float
    steps: int
    frames: int
    elapsed_s: float
    eta_s: float | None
    hmax: float | None
    umax: float | None
    runout: float | None
    area: float | None
    vol_in_domain: float | None
    vol_out: float | None
    released_m3: float | None
    error: str | None
    cancel_requested: bool

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "JobRecord":
        """Build from a database row."""
        d = dict(r)
        d["scenario"] = json.loads(d.pop("scenario_json"))
        d["provenance"] = _loads(d.pop("provenance_json"))
        d["grid"] = _loads(d.pop("grid_json"))
        d["cancel_requested"] = bool(d["cancel_requested"])
        return cls(**d)

    @property
    def progress(self) -> float:
        """Completed fraction of simulated time."""
        if self.status == "completed":
            return 1.0
        return min(self.sim_t / self.t_end, 1.0) if self.t_end > 0 else 0.0


PROGRESS_FIELDS = (
    "sim_t",
    "steps",
    "frames",
    "elapsed_s",
    "eta_s",
    "hmax",
    "umax",
    "runout",
    "area",
    "vol_in_domain",
    "vol_out",
    "released_m3",
)


class JobRepository:
    """CRUD and state transitions for the ``jobs`` table."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _one(self, sql: str, args: tuple[Any, ...]) -> sqlite3.Row | None:
        conn = connect(self.db_path)
        try:
            return conn.execute(sql, args).fetchone()
        finally:
            conn.close()

    def create(
        self,
        job_id: str,
        name: str,
        dem_id: str,
        scenario: dict[str, Any],
        t_end: float,
        parent_job_id: str | None = None,
    ) -> JobRecord:
        """Insert a queued job."""
        with session(self.db_path) as c:
            c.execute(
                "INSERT INTO jobs (id, name, dem_id, status, scenario_json, t_end, "
                "parent_job_id, created_at) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?)",
                (
                    job_id,
                    name,
                    dem_id,
                    json.dumps(scenario),
                    t_end,
                    parent_job_id,
                    now_iso(),
                ),
            )
        rec = self.get(job_id)
        assert rec is not None
        return rec

    def get(self, job_id: str) -> JobRecord | None:
        """Fetch one job."""
        r = self._one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return None if r is None else JobRecord.from_row(r)

    def list_recent(self, limit: int = 200) -> list[JobRecord]:
        """Most recent jobs first."""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [JobRecord.from_row(r) for r in rows]

    def queued(self) -> list[str]:
        """Ids of queued jobs, oldest first."""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at, rowid"
            ).fetchall()
        finally:
            conn.close()
        return [r["id"] for r in rows]

    def running(self) -> list[JobRecord]:
        """Jobs currently marked running."""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = 'running'"
            ).fetchall()
        finally:
            conn.close()
        return [JobRecord.from_row(r) for r in rows]

    def claim(self, job_id: str, pid: int) -> bool:
        """Atomically move a queued job to running; ``False`` if it was not queued."""
        ts = now_iso()
        with session(self.db_path) as c:
            cur = c.execute(
                "UPDATE jobs SET status = 'running', pid = ?, started_at = ?, "
                "heartbeat_at = ? WHERE id = ? AND status = 'queued'",
                (pid, ts, ts, job_id),
            )
            return cur.rowcount == 1

    def set_pid(self, job_id: str, pid: int) -> None:
        """Record the worker process id."""
        with session(self.db_path) as c:
            c.execute("UPDATE jobs SET pid = ? WHERE id = ?", (pid, job_id))

    def set_started(
        self, job_id: str, provenance: dict[str, Any], grid: dict[str, Any]
    ) -> None:
        """Store provenance and grid description once the domain is built."""
        with session(self.db_path) as c:
            c.execute(
                "UPDATE jobs SET provenance_json = ?, grid_json = ?, heartbeat_at = ? "
                "WHERE id = ?",
                (json.dumps(provenance), json.dumps(grid), now_iso(), job_id),
            )

    def update_progress(self, job_id: str, values: dict[str, Any]) -> None:
        """Write progress fields and refresh the heartbeat."""
        cols = [k for k in PROGRESS_FIELDS if k in values]
        sets = ", ".join(f"{k} = ?" for k in cols)
        args = [values[k] for k in cols]
        with session(self.db_path) as c:
            c.execute(
                f"UPDATE jobs SET {sets + ', ' if sets else ''}heartbeat_at = ? "
                "WHERE id = ?",
                (*args, now_iso(), job_id),
            )

    def add_frame(self, job_id: str, k: int, stats: dict[str, Any]) -> None:
        """Store one frame's statistics."""
        with session(self.db_path) as c:
            c.execute(
                "INSERT OR REPLACE INTO job_frames (job_id, k, stats_json) VALUES (?, ?, ?)",
                (job_id, k, json.dumps(stats)),
            )

    def frames(self, job_id: str) -> list[dict[str, Any]]:
        """All frame statistics of a job, in order."""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT stats_json FROM job_frames WHERE job_id = ? ORDER BY k",
                (job_id,),
            ).fetchall()
        finally:
            conn.close()
        return [json.loads(r["stats_json"]) for r in rows]

    def finish(self, job_id: str, status: str, error: str | None = None) -> None:
        """Move a job to a finished state."""
        assert status in FINISHED
        with session(self.db_path) as c:
            c.execute(
                "UPDATE jobs SET status = ?, error = ?, finished_at = ?, pid = NULL "
                "WHERE id = ? AND status IN ('queued', 'running')",
                (status, error, now_iso(), job_id),
            )

    def request_cancel(self, job_id: str) -> str | None:
        """Cancel a queued job now, or flag a running one. Returns the new status."""
        with session(self.db_path) as c:
            r = c.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if r is None:
                return None
            if r["status"] == "queued":
                c.execute(
                    "UPDATE jobs SET status = 'cancelled', finished_at = ? WHERE id = ?",
                    (now_iso(), job_id),
                )
                return "cancelled"
            if r["status"] == "running":
                c.execute(
                    "UPDATE jobs SET cancel_requested = 1 WHERE id = ?", (job_id,)
                )
            return r["status"]

    def cancel_requested(self, job_id: str) -> bool:
        """Whether cancellation was requested."""
        r = self._one("SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,))
        return bool(r and r["cancel_requested"])

    def mark_stale_interrupted(self, max_age_s: float) -> list[str]:
        """Mark running jobs whose heartbeat is older than ``max_age_s`` as interrupted."""
        cutoff = (datetime.now(UTC) - timedelta(seconds=max_age_s)).isoformat(
            timespec="seconds"
        )
        with session(self.db_path) as c:
            rows = c.execute(
                "SELECT id FROM jobs WHERE status = 'running' AND "
                "(heartbeat_at IS NULL OR heartbeat_at < ?)",
                (cutoff,),
            ).fetchall()
            ids = [r["id"] for r in rows]
            for jid in ids:
                c.execute(
                    "UPDATE jobs SET status = 'interrupted', finished_at = ?, pid = NULL, "
                    "error = 'Worker stopped without finishing (server restart?)' "
                    "WHERE id = ?",
                    (now_iso(), jid),
                )
        return ids

    def mark_all_running_interrupted(self) -> list[str]:
        """On startup no worker is alive yet: every running job was interrupted."""
        return self.mark_stale_interrupted(max_age_s=-1e9)

    def delete(self, job_id: str) -> None:
        """Delete a job and its frame statistics."""
        with session(self.db_path) as c:
            c.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
