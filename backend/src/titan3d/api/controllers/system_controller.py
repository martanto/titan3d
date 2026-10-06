"""System health: server resources, application services and storage."""

import os
import sys
import time
import platform
import threading
from pathlib import Path
from datetime import UTC, datetime

import psutil

from titan3d.config import Settings
from titan3d.version import git_commit, package_version
from titan3d.db.database import connect
from titan3d.api.schemas.system import (
    Health,
    SystemOut,
    ServiceOut,
    Thresholds,
    ResourceOut,
    ServiceItem,
    StorageItem,
    CacheClearOut,
)
from titan3d.api.workers.dispatcher import Dispatcher


CACHE_SECONDS = 300  # not realtime: one reading is reused for 5 minutes
SLOW_PROBE_MS = 250.0
DISK_MEMORY = Thresholds(warning=0.80, critical=0.90)
CPU = Thresholds(warning=0.80, critical=0.95)
_RANK = {"normal": 0, "warning": 1, "critical": 2}
_STARTED = time.time()
# regenerable caches: terrain previews and playback bundles are rebuilt on request
_CACHE_GLOBS = (("dems", "preview_*.json.gz"), ("runs", "bundle_*.json.gz"))


def human_bytes(n: float) -> str:
    """Bytes as a short decimal string (kB, MB, GB, TB)."""
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if abs(n) < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} TB"


def _status(fraction: float, t: Thresholds) -> Health:
    if fraction >= t.critical:
        return "critical"
    if fraction >= t.warning:
        return "warning"
    return "normal"


def _worst(states: list[Health]) -> Health:
    return max(states, key=lambda s: _RANK[s], default="normal")


def _tree(path: Path, skip_globs: tuple[str, ...] = ()) -> tuple[int, int]:
    files = size = 0
    if not path.exists():
        return 0, 0
    for p in path.rglob("*"):
        if p.is_file() and not any(p.match(g) for g in skip_globs):
            files += 1
            size += p.stat().st_size
    return files, size


def _os_name() -> str:
    if sys.platform == "win32":
        build = int(platform.version().split(".")[-1] or 0)
        return f"Windows {'11' if build >= 22000 else platform.release()} · {build}"
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]}"
    try:
        info = platform.freedesktop_os_release()
        return info.get("PRETTY_NAME", f"Linux {platform.release()}")
    except OSError:
        return f"Linux {platform.release()}"


class SystemController:
    """Collects health readings (cached briefly) and manages regenerable caches."""

    def __init__(self, settings: Settings, dispatcher: Dispatcher):
        self.settings = settings
        self.dispatcher = dispatcher
        self._cache: tuple[float, SystemOut] | None = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------- resources
    def _resources(self) -> list[ResourceOut]:
        s = self.settings
        disk = psutil.disk_usage(str(s.data_dir))
        disk_f = disk.used / disk.total
        mem = psutil.virtual_memory()
        mem_used = mem.total - mem.available  # excludes reclaimable page cache
        mem_f = mem_used / mem.total
        cores = psutil.cpu_count(logical=True) or 1
        cpu_f = psutil.cpu_percent(interval=0.3) / 100.0
        try:
            load = psutil.getloadavg()
        except (AttributeError, OSError):
            load = (0.0, 0.0, 0.0)
        load_txt = " · ".join(f"{v:.2f}" for v in load) if any(load) else "not reported"
        return [
            ResourceOut(
                key="disk",
                label="Disk",
                detail=f"Partition holding the data folder ({s.data_dir})",
                fraction=disk_f,
                used=human_bytes(disk.used),
                capacity=human_bytes(disk.total),
                free=human_bytes(disk.free),
                status=_status(disk_f, DISK_MEMORY),
                thresholds=DISK_MEMORY,
            ),
            ResourceOut(
                key="memory",
                label="Memory",
                detail="Physical RAM, excluding reclaimable cache",
                fraction=mem_f,
                used=human_bytes(mem_used),
                capacity=human_bytes(mem.total),
                free=human_bytes(mem.available),
                status=_status(mem_f, DISK_MEMORY),
                thresholds=DISK_MEMORY,
            ),
            ResourceOut(
                key="cpu",
                label="CPU",
                detail=f"{cores} logical cores · load {load_txt}",
                fraction=cpu_f,
                used=f"{cpu_f * cores:.1f} cores busy",
                capacity=f"{cores} cores",
                free=f"{(1 - cpu_f) * cores:.1f} cores idle",
                status=_status(cpu_f, CPU),
                thresholds=CPU,
            ),
        ]

    # ----------------------------------------------------------- services
    def _sqlite(self) -> ServiceOut:
        path = self.settings.db_path
        t0 = time.perf_counter()
        conn = connect(path)
        try:
            conn.execute("SELECT 1").fetchone()
            ms = (time.perf_counter() - t0) * 1000
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            counts = {
                r["status"]: r["n"]
                for r in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
                )
            }
            n_dems = conn.execute("SELECT COUNT(*) AS n FROM dems").fetchone()["n"]
        finally:
            conn.close()
        size = sum(
            p.stat().st_size for p in path.parent.glob(path.name + "*") if p.is_file()
        )
        import sqlite3

        return ServiceOut(
            key="sqlite",
            name="SQLite",
            version=f"v{sqlite3.sqlite_version}",
            status="warning" if ms > SLOW_PROBE_MS else "normal",
            response_ms=round(ms, 2),
            details=[
                ServiceItem(label="Database", value=path.name),
                ServiceItem(label="Size", value=human_bytes(size)),
                ServiceItem(label="Journal", value=str(mode).upper()),
                ServiceItem(label="Runs", value=str(sum(counts.values()))),
                ServiceItem(label="DEMs", value=str(n_dems)),
            ],
        )

    def _queue(self) -> ServiceOut:
        conn = connect(self.settings.db_path)
        try:
            counts = {
                r["status"]: r["n"]
                for r in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
                )
            }
            day_ago = datetime.fromtimestamp(time.time() - 86400, UTC).isoformat(
                timespec="seconds"
            )
            failed_24h = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE status IN ('failed', 'interrupted') "
                "AND COALESCE(finished_at, created_at) >= ?",
                (day_ago,),
            ).fetchone()["n"]
        finally:
            conn.close()
        alive = sum(1 for p in self.dispatcher.procs.values() if p.is_alive())
        status: Health = "warning" if failed_24h else "normal"
        return ServiceOut(
            key="queue",
            name="Job queue",
            version=f"{self.settings.max_concurrent_runs} worker slot{'s' if self.settings.max_concurrent_runs > 1 else ''}",
            status=status,
            details=[
                ServiceItem(label="Running", value=str(counts.get("running", 0))),
                ServiceItem(label="Queued", value=str(counts.get("queued", 0))),
                ServiceItem(label="Worker processes", value=str(alive)),
                ServiceItem(label="Completed", value=str(counts.get("completed", 0))),
                ServiceItem(label="Failed (24 h)", value=str(failed_24h)),
            ],
            note="Warning while a run failed or was interrupted in the last 24 h."
            if failed_24h
            else None,
        )

    def _numba(self) -> ServiceOut:
        try:
            import numba
            import numpy as np

            layer = os.environ.get("NUMBA_THREADING_LAYER", "default")
            return ServiceOut(
                key="numba",
                name="Solver kernels (Numba)",
                version=f"v{numba.__version__} · NumPy {np.__version__}",
                status="normal",
                details=[
                    ServiceItem(label="Threads", value=str(numba.get_num_threads())),
                    ServiceItem(label="Threading layer", value=layer),
                    ServiceItem(
                        label="Cache dir",
                        value=os.environ.get("NUMBA_CACHE_DIR", "package __pycache__"),
                    ),
                ],
            )
        except ImportError as exc:
            return ServiceOut(
                key="numba",
                name="Solver kernels (Numba)",
                status="warning",
                details=[
                    ServiceItem(label="Fallback", value="NumPy reference kernels")
                ],
                note=f"Numba unavailable: {exc}",
            )

    def _dem_store(self) -> ServiceOut:
        conn = connect(self.settings.db_path)
        try:
            counts = {
                r["status"]: r["n"]
                for r in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM dems GROUP BY status"
                )
            }
            builtin = conn.execute(
                "SELECT status FROM dems WHERE source = 'builtin'"
            ).fetchone()
        finally:
            conn.close()
        status: Health = "warning" if counts.get("failed") else "normal"
        tiles = (
            list(self.settings.builtin_dem_dir.glob("*.tif"))
            if self.settings.builtin_dem_dir.exists()
            else []
        )
        return ServiceOut(
            key="dems",
            name="DEM store",
            version=None,
            status=status,
            details=[
                ServiceItem(label="Ready", value=str(counts.get("ready", 0))),
                ServiceItem(label="Stitching", value=str(counts.get("processing", 0))),
                ServiceItem(label="Failed", value=str(counts.get("failed", 0))),
                ServiceItem(
                    label="Built-in",
                    value=f"{builtin['status']} · {len(tiles)} tiles"
                    if builtin
                    else f"none · {len(tiles)} tiles in dem/",
                ),
            ],
            note="Warning while an uploaded DEM failed to stitch."
            if counts.get("failed")
            else None,
        )

    # ------------------------------------------------------------ storage
    def _storage(self) -> list[StorageItem]:
        s = self.settings
        cache_patterns = tuple(g for _, g in _CACHE_GLOBS)
        dem_files, dem_bytes = _tree(s.dems_dir, cache_patterns)
        run_files, run_bytes = _tree(s.runs_dir, cache_patterns)
        cache_files = cache_bytes = 0
        for sub, pattern in _CACHE_GLOBS:
            for p in (s.data_dir / sub).rglob(pattern):
                cache_files += 1
                cache_bytes += p.stat().st_size
        log_files, log_bytes = _tree(s.logs_dir)
        db_bytes = sum(
            p.stat().st_size
            for p in s.db_path.parent.glob(s.db_path.name + "*")
            if p.is_file()
        )
        return [
            StorageItem(
                key="runs",
                label="Run outputs",
                description="Frames, GeoTIFFs, outlines, configs and logs per run",
                files=run_files,
                bytes=run_bytes,
                size=human_bytes(run_bytes),
                regenerable=False,
            ),
            StorageItem(
                key="dems",
                label="DEMs",
                description="Uploaded tiles and stitched mosaics",
                files=dem_files,
                bytes=dem_bytes,
                size=human_bytes(dem_bytes),
                regenerable=False,
            ),
            StorageItem(
                key="caches",
                label="Playback and preview caches",
                description="Terrain previews and playback bundles, rebuilt on request",
                files=cache_files,
                bytes=cache_bytes,
                size=human_bytes(cache_bytes),
                regenerable=True,
            ),
            StorageItem(
                key="database",
                label="Database",
                description="SQLite job and DEM records",
                files=1,
                bytes=db_bytes,
                size=human_bytes(db_bytes),
                regenerable=False,
            ),
            StorageItem(
                key="logs",
                label="Server logs",
                description="Rotating server log files",
                files=log_files,
                bytes=log_bytes,
                size=human_bytes(log_bytes),
                regenerable=False,
            ),
        ]

    def _environment(self) -> str:
        s = self.settings
        built = (s.frontend_dist / "index.html").exists()
        mode = "Production build" if built else "API only (dev UI)"
        return f"{mode}{' · basic auth' if s.basic_auth_enabled else ''}"

    # ------------------------------------------------------------ public
    def snapshot(self, refresh: bool = False) -> SystemOut:
        """Health reading, reused for ``CACHE_SECONDS`` unless ``refresh``."""
        with self._lock:
            if (
                not refresh
                and self._cache
                and time.time() - self._cache[0] < CACHE_SECONDS
            ):
                return self._cache[1]
            resources = self._resources()
            services = [self._sqlite(), self._queue(), self._numba(), self._dem_store()]
            out = SystemOut(
                condition=_worst(
                    [r.status for r in resources] + [sv.status for sv in services]
                ),
                measured_at=datetime.now(UTC).isoformat(timespec="seconds"),
                cache_seconds=CACHE_SECONDS,
                host=platform.node(),
                os=_os_name(),
                environment=self._environment(),
                python=platform.python_version(),
                titan3d=package_version(),
                commit=git_commit(),
                data_dir=str(self.settings.data_dir),
                server_uptime_s=time.time() - psutil.boot_time(),
                app_uptime_s=time.time() - _STARTED,
                resources=resources,
                services=services,
                storage=self._storage(),
                notes=[
                    "Disk and memory: warning from 80 %, critical from 90 % used. "
                    "CPU: warning from 80 %, critical from 95 % busy (one simulation uses every core). "
                    "Memory used excludes reclaimable page cache.",
                    f"Service response = time of one light probe; above {SLOW_PROBE_MS:.0f} ms is a warning.",
                ],
            )
            self._cache = (time.time(), out)
            return out

    def clear_caches(self) -> CacheClearOut:
        """Delete terrain previews and playback bundles (rebuilt on next request)."""
        files = size = 0
        for sub, pattern in _CACHE_GLOBS:
            for p in (self.settings.data_dir / sub).rglob(pattern):
                try:
                    size += p.stat().st_size
                    p.unlink()
                    files += 1
                except OSError:
                    continue
        self._cache = None
        return CacheClearOut(files=files, bytes=size, size=human_bytes(size))
