"""Launches queued jobs as worker processes and reaps finished ones."""

import asyncio
import multiprocessing as mp
from multiprocessing.process import BaseProcess

from loguru import logger

from titan3d.config import Settings
from titan3d.db.repositories import JobRepository
from titan3d.api.workers.runner import worker_main


class Dispatcher:
    """Runs at most ``settings.max_concurrent_runs`` worker processes.

    Workers are daemonic ``spawn`` processes: they stop with the server, and any
    job left ``running`` is marked ``interrupted`` on the next start.
    """

    def __init__(self, settings: Settings, poll_s: float = 1.0):
        self.settings = settings
        self.jobs = JobRepository(settings.db_path)
        self.poll_s = poll_s
        self.procs: dict[str, BaseProcess] = {}
        self._ctx = mp.get_context("spawn")
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()

    # ------------------------------------------------------------- lifecycle
    def recover(self) -> None:
        """Mark jobs orphaned by a previous server process as interrupted."""
        ids = self.jobs.mark_all_running_interrupted()
        if ids:
            logger.warning("marked {} orphaned job(s) interrupted: {}", len(ids), ids)

    def start(self) -> None:
        """Start the polling loop on the running event loop."""
        self._task = asyncio.create_task(self._loop(), name="titan3d-dispatcher")

    async def stop(self) -> None:
        """Stop polling and terminate running workers."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for jid, proc in self.procs.items():
            if proc.is_alive():
                logger.warning("terminating worker for job {}", jid)
                proc.terminate()
                proc.join(5)
            self.jobs.finish(
                jid, "interrupted", "Server stopped while the job was running"
            )
        self.procs.clear()

    def wake(self) -> None:
        """Check the queue now instead of waiting for the next poll."""
        self._wake.set()

    async def _loop(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - keep dispatching after transient errors
                logger.exception("dispatcher tick failed")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_s)
            except TimeoutError:
                pass
            self._wake.clear()

    # ------------------------------------------------------------------ work
    def tick(self) -> None:
        """Reap finished workers, recover orphans, launch queued jobs."""
        for jid, proc in list(self.procs.items()):
            if proc.is_alive():
                continue
            proc.join(0)
            rec = self.jobs.get(jid)
            if rec is not None and rec.status == "running":
                self.jobs.finish(
                    jid, "failed", f"Worker exited unexpectedly (code {proc.exitcode})"
                )
            del self.procs[jid]
        for rec in self.jobs.running():
            if rec.id not in self.procs:
                self.jobs.finish(
                    rec.id, "interrupted", "No worker process for this job"
                )
        free = self.settings.max_concurrent_runs - len(self.procs)
        for jid in self.jobs.queued()[: max(free, 0)]:
            if not self.jobs.claim(jid, pid=0):
                continue
            proc = self._ctx.Process(
                target=worker_main,
                args=(
                    jid,
                    str(self.settings.db_path),
                    str(self.settings.runs_dir),
                    self.settings.log_level,
                ),
                name=f"titan3d-job-{jid}",
                daemon=True,
            )
            proc.start()
            self.procs[jid] = proc
            logger.info("launched job {} (pid {})", jid, proc.pid)

    def kill(self, job_id: str) -> bool:
        """Terminate a worker immediately (hard cancel)."""
        proc = self.procs.get(job_id)
        if proc is None or not proc.is_alive():
            return False
        proc.terminate()
        return True
