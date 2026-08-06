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


class SimulationKilled(Exception):
    """Raised inside a simulation when the user kills it."""


class RunControl:
    """
    Lets a running simulation be stopped.

    A simulation spends most of its time blocked inside a Fluent call, so a
    flag alone cannot interrupt it. Killing therefore does two things:

      1. sets the flag, which the simulation checks at every progress step
      2. forces the Fluent sessions down, so whatever call is in flight
         fails immediately rather than running to completion

    Simulation types register each session as they launch it and call
    check() at every step; both are one line each.
    """

    def __init__(self):
        self._killed = threading.Event()
        self._sessions = []
        self._lock = threading.Lock()

    # ── Used by the simulation ───────────────────────────────────────────

    def register(self, session) -> None:
        """Register a Fluent session so it can be forced down."""
        with self._lock:
            self._sessions.append(session)

    def release(self, session) -> None:
        """Forget a session that has exited normally."""
        with self._lock:
            if session in self._sessions:
                self._sessions.remove(session)

    def check(self) -> None:
        """Raise if a kill has been requested. Call between steps."""
        if self._killed.is_set():
            raise SimulationKilled("Stopped by user")

    @property
    def killed(self) -> bool:
        return self._killed.is_set()

    # ── Used by the queue ────────────────────────────────────────────────

    def kill(self) -> int:
        """
        Request a stop and force every registered session down.
        Returns how many sessions were signalled.
        """
        self._killed.set()
        with self._lock:
            sessions = list(self._sessions)
            self._sessions.clear()

        for session in sessions:
            # force_exit is the hard stop; exit() is the graceful one and is
            # tried second in case this build lacks force_exit.
            for method in ("force_exit", "exit"):
                closer = getattr(session, method, None)
                if closer is None:
                    continue
                try:
                    closer()
                    break
                except Exception as exc:
                    log.debug(f"  {method}(): {exc}")
        return len(sessions)


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
    control:     RunControl = field(default_factory=RunControl)

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

    def add(self, sim_type, settings, start_now: bool = False) -> Job:
        """
        Validate and queue a simulation.

        Queuing does not start it. Call start() when you are ready, or pass
        start_now=True. Raises ValueError if the settings are unusable.
        """
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

        if start_now:
            self.start()
        return job

    def kill(self, job_id: int) -> bool:
        """
        Stop a running simulation.

        Forces its Fluent sessions down, so the call it is blocked in fails
        and the simulation unwinds. Fluent may take a few seconds to close.
        """
        job = self.get(job_id)
        if job is None or job.state is not JobState.RUNNING:
            return False

        log.warning(f"Killing [{job.job_id}] {job.name}")
        count = job.control.kill()
        log.warning(f"  Signalled {count} Fluent session(s); "
                    f"the job will stop shortly")
        return True

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
        """Ask the worker to finish the current job, then stop."""
        self._stop.set()

    def pause(self) -> None:
        """
        Stop picking up new jobs. The current job runs to completion; use
        kill() to stop that as well.
        """
        self._stop.set()
        log.info("Queue paused; it will stop after the current job")

    @property
    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs if j.state is JobState.PENDING)

    @property
    def current(self) -> Optional[Job]:
        """The job being run, if any."""
        with self._lock:
            return next((j for j in self._jobs
                         if j.state is JobState.RUNNING), None)

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
            job.results = job.sim_type.run(job.settings, log, progress,
                                           job.control)
            job.state = JobState.COMPLETED
            job.progress = 100
            job.message = "Complete"
            log.info(f"Completed [{job.job_id}] {job.name} "
                     f"in {job.elapsed / 60:.1f} min")

        except SimulationKilled:
            job.state = JobState.CANCELLED
            job.message = "Stopped by user"
            log.warning(f"Stopped [{job.job_id}] {job.name} "
                        f"after {job.elapsed / 60:.1f} min")

        except Exception as exc:
            # A forced session shutdown surfaces as a connection error rather
            # than SimulationKilled, so treat anything after a kill request
            # as a stop rather than a failure.
            if job.control.killed:
                job.state = JobState.CANCELLED
                job.message = "Stopped by user"
                log.warning(f"Stopped [{job.job_id}] {job.name} "
                            f"after {job.elapsed / 60:.1f} min")
                job.finished_at = time.time()
                self._changed()
                return
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
