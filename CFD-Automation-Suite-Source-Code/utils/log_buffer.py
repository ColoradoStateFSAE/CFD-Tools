"""
Rolling in-memory log buffer.

Keeps the most recent log lines so anything that was not open when a line
was printed -- the phone monitor, in particular -- can still see it. A plain
logging.Handler, so it plugs in next to the GUI's own handler with no extra
wiring.
"""
import logging
import threading
from collections import deque


class LogBuffer(logging.Handler):

    def __init__(self, capacity: int = 2000):
        super().__init__()
        self.setFormatter(logging.Formatter(
            "%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
        self._lines = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record) -> None:
        try:
            line = self.format(record)
        except Exception:
            return
        with self._lock:
            self._lines.append(line)

    def tail(self, n: int = 300) -> list:
        with self._lock:
            return list(self._lines)[-n:]
