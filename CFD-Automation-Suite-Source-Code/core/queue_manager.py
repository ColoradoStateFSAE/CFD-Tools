"""
Simulation queue manager.
Runs simulations sequentially in a background thread,
emitting callbacks for the GUI to consume.
"""
import threading
import queue
import logging
import traceback
import json
import os
from datetime import datetime
from typing import Callable, Optional, List
from enum import Enum

log = logging.getLogger("sim_queue")


class JobStatus(Enum):
    QUEUED = "Queued"
    RUNNING = "Running"
    DONE = "Done"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class SimJob:
    _id_counter = 0

    def __init__(self, config):
        SimJob._id_counter += 1
        self.job_id = SimJob._id_counter
        self.config = config
        self.status = JobStatus.QUEUED
        self.progress_pct = 0
        self.progress_msg = ""
        self.results = {}
        self.error = ""
        self.queued_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.started_at = ""
        self.finished_at = ""

    @property
    def display_name(self) -> str:
        return f"[{self.job_id}] {self.config.name} ({self.config.sim_type.value})"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.config.name,
            "sim_type": self.config.sim_type.value,
            "status": self.status.value,
            "progress_pct": self.progress_pct,
            "progress_msg": self.progress_msg,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "results": self.results,
            "error": self.error,
        }


class SimulationQueue:
    """
    Thread-safe simulation queue.
    One job runs at a time; others wait.

    Uses a threading.Event (_job_available) to signal the worker thread
    when new jobs are added, eliminating the race condition where the
    worker could exit between checking for a next job and a new job
    being enqueued.
    """

    def __init__(self,
                 on_job_update: Optional[Callable] = None,
                 on_queue_update: Optional[Callable] = None):
        self._queue: List[SimJob] = []
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # Signalled whenever a QUEUED job becomes available, or on shutdown.
        self._job_available = threading.Event()
        self._current_job: Optional[SimJob] = None

        # Callbacks fired on the worker thread; GUI should use .after() etc.
        self.on_job_update = on_job_update    # called(job) on any status change
        self.on_queue_update = on_queue_update  # called() when queue list changes

    # ── Public API ──────────────────────────────────────────────────────────

    def add_job(self, config) -> SimJob:
        job = SimJob(config)
        with self._lock:
            self._queue.append(job)
        self._fire_queue_update()
        self._ensure_worker_running()
        # Signal the worker thread that a job is available.
        self._job_available.set()
        log.info(f"Queued: {job.display_name}")
        return job

    def cancel_job(self, job_id: int):
        with self._lock:
            for job in self._queue:
                if job.job_id == job_id and job.status == JobStatus.QUEUED:
                    job.status = JobStatus.CANCELLED
                    log.info(f"Cancelled: {job.display_name}")
                    self._fire_queue_update()
                    return
        log.warning(f"Cannot cancel job {job_id} - not in QUEUED state.")

    def move_up(self, job_id: int):
        with self._lock:
            queued = [j for j in self._queue if j.status == JobStatus.QUEUED]
            idx = next((i for i, j in enumerate(queued) if j.job_id == job_id), None)
            if idx is not None and idx > 0:
                pos_a = self._queue.index(queued[idx])
                pos_b = self._queue.index(queued[idx - 1])
                self._queue[pos_a], self._queue[pos_b] = (
                    self._queue[pos_b], self._queue[pos_a]
                )
        self._fire_queue_update()

    def move_down(self, job_id: int):
        with self._lock:
            queued = [j for j in self._queue if j.status == JobStatus.QUEUED]
            idx = next((i for i, j in enumerate(queued) if j.job_id == job_id), None)
            if idx is not None and idx < len(queued) - 1:
                pos_a = self._queue.index(queued[idx])
                pos_b = self._queue.index(queued[idx + 1])
                self._queue[pos_a], self._queue[pos_b] = (
                    self._queue[pos_b], self._queue[pos_a]
                )
        self._fire_queue_update()

    def get_jobs(self) -> List[SimJob]:
        with self._lock:
            return list(self._queue)

    def get_current_job(self) -> Optional[SimJob]:
        return self._current_job

    def shutdown(self):
        self._stop_event.set()
        # Wake the worker so it can see the stop event and exit cleanly.
        self._job_available.set()

    def save_log(self, path: str):
        """Save queue history to JSON."""
        with self._lock:
            data = [j.to_dict() for j in self._queue]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        log.info(f"Queue log saved to {path}")

    # ── Internal ────────────────────────────────────────────────────────────

    def _ensure_worker_running(self):
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True
            )
            self._worker_thread.start()

    def _worker_loop(self):
        log.info("Queue worker started.")
        while not self._stop_event.is_set():
            job = self._next_queued_job()
            if job is not None:
                self._run_job(job)
                continue
            # No job available right now — wait for a signal before re-checking.
            # This eliminates the race between "no job found" and "job just added".
            self._job_available.clear()
            # Re-check under the clear to avoid a missed wakeup:
            # if add_job() set the event between our _next_queued_job() call
            # and the clear() above, we'd block forever without this re-check.
            job = self._next_queued_job()
            if job is not None:
                self._run_job(job)
                continue
            self._job_available.wait()
        log.info("Queue worker exited.")

    def _next_queued_job(self) -> Optional[SimJob]:
        with self._lock:
            for job in self._queue:
                if job.status == JobStatus.QUEUED:
                    return job
        return None

    def _run_job(self, job: SimJob):
        self._current_job = job
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._fire_job_update(job)
        log.info(f"Starting: {job.display_name}")

        def progress_cb(msg: str, pct: int):
            job.progress_msg = msg
            job.progress_pct = pct
            self._fire_job_update(job)

        try:
            from core.runner import run_meshing, run_solver
            os.makedirs(job.config.output_dir, exist_ok=True)
            mesh_file, mesh_quality = run_meshing(job.config, progress_cb=progress_cb)
            results = run_solver(job.config, mesh_file,
                                 progress_cb=progress_cb,
                                 mesh_quality=mesh_quality)
            job.results = results
            job.status = JobStatus.DONE
            log.info(f"Completed: {job.display_name}")
        except Exception as e:
            job.error = traceback.format_exc()
            job.status = JobStatus.FAILED
            log.error(f"Failed: {job.display_name}\n{job.error}")
        finally:
            job.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            job.progress_pct = 100
            self._current_job = None
            self._fire_job_update(job)
            self._fire_queue_update()

    def _fire_job_update(self, job: SimJob):
        if self.on_job_update:
            try:
                self.on_job_update(job)
            except Exception:
                pass

    def _fire_queue_update(self):
        if self.on_queue_update:
            try:
                self.on_queue_update()
            except Exception:
                pass
