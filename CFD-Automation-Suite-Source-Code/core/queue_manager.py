"""
Simulation queue.

Runs queued simulations one at a time on a background thread so the GUI stays
responsive. Each job holds a simulation type module and its settings; the
queue calls module.run(settings, log, progress) and records the result.
"""
import logging
import threading
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue, Empty
from typing import Callable, Optional

log = logging.getLogger("queue")


class JobState(Enum):
    PENDING   = "Pending"
    RUNNING   = "Running"
    COMPLETED = "Completed"
    FAILED    = "Failed"
    CANCELLED = "Cancelled"


@dataclass
class Job:
    """One queued simulation."""
    job_id:     int
    sim_type:   object          # a module from simtypes
    settings:   object          # that module's Settings instance
    state:      JobState = JobState.PENDING
    progress:   int = 0
    message:    str = ""
    error:      str = ""
    results:    dict = field(default_factory=dict)
    started_at:  Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def type_name(self) -> str:
        return self.sim_type.NAME

    @property
    def elapsed(self) -> float:
        """Seconds spent running, live while in progress."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at else time.time()
        return end - self.started_at


class SimQueue:
    """
    Thread-safe FIFO queue with a single worker.

    Callbacks fire on the worker thread. Qt callers should marshal to the GUI
    thread with a signal.
    """

    def __init__(self,
                 on_change: Optional[Callable] = None,
                 on_progress: Optional[Callable] = None):
        self._jobs: list = []
        self._queue: Queue = Queue()
        self._lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._next_id = 1

        self.on_change = on_change       # called when the job list changes
        self.on_progress = on_progress   # called as a job reports progress

    # ── Queue contents ───────────────────────────────────────────────────

    def add(self, sim_type, settings) -> Job:
        """Validate and queue a simulation. Raises ValueError if unusable."""
        problems = settings.validate()
        if problems:
            raise ValueError("\n".join(problems))

        with self._lock:
            job = Job(self._next_id, sim_type, settings)
            self._next_id += 1
            self._jobs.append(job)

        self._queue.put(job)
        log.info(f"Queued [{job.job_id}] {job.name} ({job.type_name})")
        self._changed()
        self.start()
        return job

    def jobs(self) -> list:
        with self._lock:
            return list(self._jobs)

    def get(self, job_id: int) -> Optional[Job]:
        with self._lock:
            return next((j for j in self._jobs if j.job_id == job_id), None)

    def cancel(self, job_id: int) -> bool:
        """Cancel a pending job. A running job cannot be cancelled."""
        job = self.get(job_id)
        if job is None or job.state is not JobState.PENDING:
            return False
        job.state = JobState.CANCELLED
        log.info(f"Cancelled [{job.job_id}] {job.name}")
        self._changed()
        return True

    def remove(self, job_id: int) -> bool:
        """Remove a job that is not running."""
        with self._lock:
            job = next((j for j in self._jobs if j.job_id == job_id), None)
            if job is None or job.state is JobState.RUNNING:
                return False
            self._jobs.remove(job)
        self._changed()
        return True

    def move(self, job_id: int, offset: int) -> bool:
        """Reorder a pending job. Only affects display order of pending work."""
        with self._lock:
            index = next((i for i, j in enumerate(self._jobs)
                          if j.job_id == job_id), None)
            if index is None:
                return False
            target = index + offset
            if not 0 <= target < len(self._jobs):
                return False
            if self._jobs[index].state is not JobState.PENDING:
                return False
            if self._jobs[target].state is not JobState.PENDING:
                return False
            self._jobs[index], self._jobs[target] = \
                self._jobs[target], self._jobs[index]
        self._changed()
        return True

    def clear_finished(self) -> int:
        """Drop completed, failed and cancelled jobs. Returns how many."""
        with self._lock:
            before = len(self._jobs)
            self._jobs = [j for j in self._jobs
                          if j.state in (JobState.PENDING, JobState.RUNNING)]
            removed = before - len(self._jobs)
        if removed:
            self._changed()
        return removed

    # ── Worker ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the worker if it is not already running."""
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._work, daemon=True,
                                        name="sim-queue")
        self._worker.start()
        log.info("Queue worker started")

    def stop(self) -> None:
        """Ask the worker to finish after the current job."""
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._worker and self._worker.is_alive())

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=1.0)
            except Empty:
                continue

            if job.state is JobState.CANCELLED:
                continue

            self._run(job)

        log.info("Queue worker stopped")

    def _run(self, job: Job) -> None:
        job.state = JobState.RUNNING
        job.started_at = time.time()
        job.progress = 0
        self._changed()

        log.info(f"Starting [{job.job_id}] {job.name} ({job.type_name})")

        def progress(message: str, percent: int) -> None:
            job.progress = percent
            job.message = message
            if self.on_progress:
                self.on_progress(job)

        try:
            job.results = job.sim_type.run(job.settings, log, progress)
            job.state = JobState.COMPLETED
            job.progress = 100
            job.message = "Complete"
            log.info(f"Completed [{job.job_id}] {job.name} "
                     f"in {job.elapsed / 60:.1f} min")

        except Exception as exc:
            job.state = JobState.FAILED
            job.error = str(exc)
            job.message = f"Failed: {exc}"
            log.error(f"Failed [{job.job_id}] {job.name}: {exc}")
            log.debug(traceback.format_exc())

        finally:
            job.finished_at = time.time()
            self._changed()

    # ── Internal ─────────────────────────────────────────────────────────

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception as exc:
                log.debug(f"on_change callback: {exc}")