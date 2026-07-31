"""
Fluent transcript capture.

Everything Fluent prints -- mesh statistics, per-iteration residuals, warnings
-- goes into the application log so it appears in the GUI rather than only in
the terminal.

PyFluent streams the transcript over gRPC and prints it to stdout, which is
why it shows up in a VS Code console but not in the GUI. The transcript
service exposes a callback, so this registers one and forwards each line to
the logger. Two fallbacks follow if that API is not available on this build:
capture stdout, then tail the transcript file.
"""
import glob
import logging
import os
import sys
import threading
import time

# Lines Fluent repeats constantly that add nothing to a run log.
NOISE = (
    "Fast-loading",
    "Auto-Transcript",
    "Opening input/output transcript",
    "ANSYS Product Improvement Program",
    "Loaded module",
)


def _worth_logging(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    return not any(token in line for token in NOISE)


class FluentLogCapture:
    """
    Routes a Fluent session's transcript into a logger.

    Use as a context manager around the work:

        with FluentLogCapture(session, log):
            ...run the workflow...

    `method` reports which mechanism ended up being used, which is worth
    knowing if the log comes back empty.
    """

    def __init__(self, session, log, prefix: str = "  | ",
                 output_dir: str = "", tag: str = "fluent"):
        self.session = session
        self.log = log
        self.prefix = prefix
        self.output_dir = output_dir
        self.tag = tag

        self.method = "none"
        self._callback_id = None
        self._stdout_saved = None
        self._stop = threading.Event()
        self._thread = None
        self._path = ""

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self) -> "FluentLogCapture":
        if self._try_callback():
            self.method = "callback"
        elif self._try_stdout():
            self.method = "stdout"
        elif self._try_file():
            self.method = "file"
        else:
            self.log.debug("  Fluent transcript could not be captured")
            return self

        self.log.debug(f"  Fluent transcript via {self.method}")
        return self

    def stop(self) -> None:
        if self.method == "callback":
            for attempt in (
                lambda: self.session.transcript.unregister_callback(
                    self._callback_id),
                lambda: self.session.transcript.stop(),
            ):
                try:
                    attempt()
                    break
                except Exception:
                    continue

        elif self.method == "stdout":
            if self._stdout_saved is not None:
                sys.stdout = self._stdout_saved
                self._stdout_saved = None

        elif self.method == "file":
            self._stop.set()
            if self._thread:
                self._thread.join(timeout=3.0)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    # ── Emit ─────────────────────────────────────────────────────────────

    def _emit(self, text: str) -> None:
        """Split a transcript chunk into lines and log the useful ones."""
        try:
            for line in str(text).splitlines():
                if _worth_logging(line):
                    self.log.info(f"{self.prefix}{line.rstrip()}")
        except Exception:
            pass

    # ── 1. Transcript callback -- the intended API ───────────────────────

    def _try_callback(self) -> bool:
        transcript = getattr(self.session, "transcript", None)
        if transcript is None:
            return False

        # The callback receives a chunk of transcript text. Signatures differ
        # slightly between versions, so accept whatever arrives.
        def on_transcript(*args, **kwargs):
            for arg in args:
                if isinstance(arg, str):
                    self._emit(arg)
                    return
            if args:
                self._emit(args[0])

        register = getattr(transcript, "register_callback", None)
        if register is None:
            return False

        try:
            self._callback_id = register(on_transcript)
        except Exception:
            return False

        # The stream may need starting explicitly on some builds. Ask it not
        # to duplicate to stdout, since the log now carries it.
        for attempt in (
            lambda: transcript.start(write_to_stdout=False),
            lambda: transcript.start(),
        ):
            try:
                attempt()
                break
            except Exception:
                continue

        return True

    # ── 2. Capture stdout -- PyFluent prints the transcript there ────────

    def _try_stdout(self) -> bool:
        """
        Replace stdout with a tee that copies into the logger.

        The real stdout still receives everything, so a terminal-launched run
        looks unchanged.
        """
        capture = self

        class _Tee:
            def __init__(self, wrapped):
                self.wrapped = wrapped
                self.buffer = ""

            def write(self, text):
                try:
                    self.wrapped.write(text)
                except Exception:
                    pass
                self.buffer += text
                while "\n" in self.buffer:
                    line, self.buffer = self.buffer.split("\n", 1)
                    if _worth_logging(line):
                        capture.log.info(f"{capture.prefix}{line.rstrip()}")

            def flush(self):
                try:
                    self.wrapped.flush()
                except Exception:
                    pass

            def __getattr__(self, name):
                return getattr(self.wrapped, name)

        try:
            self._stdout_saved = sys.stdout
            sys.stdout = _Tee(sys.stdout)
            return True
        except Exception:
            self._stdout_saved = None
            return False

    # ── 3. Tail the transcript file ──────────────────────────────────────

    def _try_file(self) -> bool:
        """
        Last resort. Fluent names its transcript solution.trn, usually in the
        working directory.
        """
        candidates = [
            os.path.join(os.getcwd(), "solution.trn"),
            os.path.join(self.output_dir, "solution.trn") if self.output_dir
            else "",
        ]
        candidates += sorted(
            glob.glob(os.path.join(os.getcwd(), "*.trn")),
            key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
            reverse=True)

        self._path = next((p for p in candidates if p and os.path.exists(p)),
                          candidates[0])

        self._thread = threading.Thread(target=self._tail, daemon=True,
                                        name=f"trn-{self.tag}")
        self._thread.start()
        return True

    def _tail(self) -> None:
        handle = None
        deadline = time.time() + 30.0
        try:
            while not self._stop.is_set():
                if handle is None:
                    if os.path.exists(self._path):
                        handle = open(self._path, "r", encoding="utf-8",
                                      errors="replace")
                        handle.seek(0, os.SEEK_END)
                    elif time.time() > deadline:
                        return
                    else:
                        time.sleep(0.25)
                        continue

                line = handle.readline()
                if not line:
                    time.sleep(0.2)
                    continue
                if _worth_logging(line):
                    self.log.info(f"{self.prefix}{line.rstrip()}")

            if handle:
                for line in handle:
                    if _worth_logging(line):
                        self.log.info(f"{self.prefix}{line.rstrip()}")
        except Exception as exc:
            self.log.debug(f"  Transcript tail stopped: {exc}")
        finally:
            if handle:
                try:
                    handle.close()
                except Exception:
                    pass


# Backwards-compatible alias
TranscriptTail = FluentLogCapture
