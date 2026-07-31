"""
Main window.

Left: the simulation queue. Right: details of the selected job.
Bottom: the log. Everything the simulations write with the logging module
appears there live.
"""
import logging
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QPlainTextEdit, QFrame,
    QProgressBar, QFormLayout, QMessageBox, QFileDialog, QComboBox,
    QDialog, QDialogButtonBox, QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QAction, QColor, QFont

import simtypes
from core.queue_manager import SimQueue, JobState
from gui.sim_editor import SimEditor
from gui.theme import STATE_COLOURS, TEXT_MUTED, ACCENT, OK, ERROR
from utils.resource_path import resource_path


# =============================================================================
#  Logging bridge
# =============================================================================

class _LogEmitter(QObject):
    """Carries the Qt signal. Kept separate from the logging handler so Qt
    never owns the handler object itself."""
    record = pyqtSignal(str, str)      # level name, formatted message


class LogBridge(logging.Handler):
    """
    Forwards log records to the GUI thread.

    Simulations run on a worker thread, so records must cross to the GUI
    thread before touching a widget. A Qt signal does that; the emitter is a
    separate object so that Qt destroying it cannot leave logging holding a
    dead handler at interpreter shutdown.
    """

    def __init__(self):
        super().__init__()
        self.emitter = _LogEmitter()
        self.setFormatter(logging.Formatter(
            "%(asctime)s  %(message)s", datefmt="%H:%M:%S"))

    @property
    def record(self):
        return self.emitter.record

    def emit(self, record):
        try:
            self.emitter.record.emit(record.levelname, self.format(record))
        except RuntimeError:
            # The window has gone; drop the record rather than raise.
            pass
        except Exception:
            pass


LEVEL_COLOURS = {
    "DEBUG":    TEXT_MUTED,
    "INFO":     "#abb2bf",
    "WARNING":  "#e5c07b",
    "ERROR":    ERROR,
    "CRITICAL": ERROR,
}


# =============================================================================
#  New simulation dialog
# =============================================================================

class NewSimDialog(QDialog):
    """Pick a simulation type before opening the editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Simulation")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        heading = QLabel("New Simulation")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        note = QLabel("Each type is a self-contained setup with its own "
                      "meshing sequence, solver settings and reports.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        self.combo = QComboBox()
        for key, name in simtypes.names():
            self.combo.addItem(name, key)
        self.combo.currentIndexChanged.connect(self._describe)
        form.addRow("Type:", self.combo)
        layout.addLayout(form)

        self.description = QLabel("")
        self.description.setObjectName("muted")
        self.description.setWordWrap(True)
        self.description.setMinimumHeight(60)
        self.description.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.description)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._describe()

    def _describe(self) -> None:
        module = simtypes.get(self.combo.currentData())
        doc = (module.__doc__ or "").strip().splitlines()
        summary = " ".join(line.strip() for line in doc[2:6] if line.strip())
        self.description.setText(summary)

    def selected(self):
        return simtypes.get(self.combo.currentData())


# =============================================================================
#  Main window
# =============================================================================

class MainWindow(QMainWindow):

    job_changed = pyqtSignal()
    job_progress = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ram Racing CFD Automation Suite")
        self.resize(1240, 800)

        self.queue = SimQueue(
            on_change=self.job_changed.emit,
            on_progress=lambda job: self.job_progress.emit(job.job_id),
        )
        self.job_changed.connect(self._refresh_queue)
        self.job_progress.connect(lambda _: self._refresh_queue())

        self._build_menu()
        self._build_ui()
        self._setup_logging()

        # Set the initial button states rather than leaving them all enabled
        self._refresh_queue()

        # Keep elapsed times ticking while a job runs
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)

        logging.getLogger().info("Ram Racing CFD Automation Suite ready")

    # ── Construction ─────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        new_action = QAction("&New Simulation…", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_simulation)
        file_menu.addAction(new_action)

        save_log = QAction("Save &Log…", self)
        save_log.setShortcut("Ctrl+S")
        save_log.triggered.connect(self._save_log)
        file_menu.addAction(save_log)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        settings_action = QAction("&Settings…", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()

        queue_menu = self.menuBar().addMenu("&Queue")
        clear = QAction("Clear &Finished", self)
        clear.triggered.connect(self._clear_finished)
        queue_menu.addAction(clear)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("&About", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, 1)

        # ── Top: queue and detail ────────────────────────────────────────
        top = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(self._queue_pane())
        top.addWidget(self._detail_pane())
        top.setStretchFactor(0, 3)
        top.setStretchFactor(1, 4)
        splitter.addWidget(top)

        # ── Bottom: log ──────────────────────────────────────────────────
        splitter.addWidget(self._log_pane())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.statusBar().showMessage("Ready")

    def _queue_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(14, 12, 8, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel("Queue")
        title.setObjectName("heading")
        header.addWidget(title)
        header.addStretch()
        self.lbl_queue_count = QLabel("")
        self.lbl_queue_count.setObjectName("muted")
        header.addWidget(self.lbl_queue_count)
        layout.addLayout(header)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self._show_detail())
        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        add = QPushButton("＋  Add Simulation")
        add.setObjectName("accent")
        add.clicked.connect(self._new_simulation)
        buttons.addWidget(add)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self._edit_selected)
        buttons.addWidget(self.btn_edit)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self._cancel_selected)
        buttons.addWidget(self.btn_cancel)
        layout.addLayout(buttons)

        order = QHBoxLayout()
        up = QPushButton("▲  Move Up")
        up.clicked.connect(lambda: self._move(-1))
        order.addWidget(up)
        down = QPushButton("▼  Move Down")
        down.clicked.connect(lambda: self._move(1))
        order.addWidget(down)
        layout.addLayout(order)

        # Queue control. Adding a simulation does not start it; nothing runs
        # until Start Queue is pressed.
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        control = QHBoxLayout()
        self.btn_start = QPushButton("▶  Start Queue")
        self.btn_start.setObjectName("accent")
        self.btn_start.setToolTip(
            "Begin running queued simulations, oldest first")
        self.btn_start.clicked.connect(self._start_queue)
        control.addWidget(self.btn_start)

        self.btn_pause = QPushButton("⏸  Pause")
        self.btn_pause.setToolTip(
            "Stop picking up new simulations.\n"
            "The one running now continues; use Kill to stop that too.")
        self.btn_pause.clicked.connect(self._pause_queue)
        control.addWidget(self.btn_pause)

        self.btn_kill = QPushButton("■  Kill")
        self.btn_kill.setObjectName("danger")
        self.btn_kill.setToolTip(
            "Force the running simulation to stop and shut Fluent down")
        self.btn_kill.clicked.connect(self._kill_running)
        control.addWidget(self.btn_kill)
        layout.addLayout(control)

        return pane

    def _detail_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(8, 12, 14, 12)
        layout.setSpacing(9)

        title = QLabel("Details")
        title.setObjectName("heading")
        layout.addWidget(title)

        self.detail_box = QGroupBox("")
        form = QFormLayout(self.detail_box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(7)

        self.d_type    = QLabel("—")
        self.d_state   = QLabel("—")
        self.d_speed   = QLabel("—")
        self.d_iters   = QLabel("—")
        self.d_elapsed = QLabel("—")
        self.d_output  = QLabel("—")
        self.d_output.setWordWrap(True)
        for widget in (self.d_type, self.d_state, self.d_speed,
                       self.d_iters, self.d_elapsed):
            widget.setObjectName("value")

        form.addRow("Type:",       self.d_type)
        form.addRow("State:",      self.d_state)
        form.addRow("Speed:",      self.d_speed)
        form.addRow("Iterations:", self.d_iters)
        form.addRow("Elapsed:",    self.d_elapsed)
        form.addRow("Output:",     self.d_output)
        layout.addWidget(self.detail_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.d_message = QLabel("")
        self.d_message.setObjectName("muted")
        self.d_message.setWordWrap(True)
        layout.addWidget(self.d_message)

        self.results_box = QGroupBox("Results")
        self.results_form = QFormLayout(self.results_box)
        self.results_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.results_box.setVisible(False)
        layout.addWidget(self.results_box)

        layout.addStretch()
        return pane

    def _log_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(14, 8, 14, 12)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("Log")
        title.setObjectName("heading")
        header.addWidget(title)
        header.addStretch()
        clear = QPushButton("Clear")
        clear.setFixedWidth(72)
        clear.clicked.connect(lambda: self.log.clear())
        header.addWidget(clear)
        layout.addLayout(header)

        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(6000)
        layout.addWidget(self.log, 1)
        return pane

    def _setup_logging(self) -> None:
        self._log_bridge = LogBridge()
        self._log_bridge.record.connect(self._append_log)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(self._log_bridge)

    # ── Actions ──────────────────────────────────────────────────────────

    def _new_simulation(self) -> None:
        picker = NewSimDialog(self)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        sim_type = picker.selected()
        settings = sim_type.Settings()

        from gui.settings_dialog import apply_defaults
        apply_defaults(settings)

        editor = SimEditor(sim_type, settings, self, is_new=True)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.queue.add(sim_type, settings)      # queued, not started
            self.statusBar().showMessage(
                "Queued. Press Start Queue to run it.", 6000)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot queue", str(exc))

    def _open_settings(self) -> None:
        from gui.settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

    def _edit_selected(self) -> None:
        job = self._selected_job()
        if job is None:
            return
        if job.state is JobState.RUNNING:
            QMessageBox.information(self, "Running",
                                    "This simulation is running and cannot "
                                    "be edited.")
            return
        editor = SimEditor(job.sim_type, job.settings, self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            self._refresh_queue()

    def _start_queue(self) -> None:
        if self.queue.pending_count == 0 and self.queue.current is None:
            QMessageBox.information(
                self, "Nothing queued",
                "Add a simulation before starting the queue.")
            return
        self.queue.start()
        self.statusBar().showMessage("Queue started", 4000)
        self._refresh_queue()

    def _pause_queue(self) -> None:
        self.queue.pause()
        running = self.queue.current
        message = ("Queue paused. "
                   + (f"{running.name} will finish first."
                      if running else "No simulation is running."))
        self.statusBar().showMessage(message, 6000)
        self._refresh_queue()

    def _kill_running(self) -> None:
        job = self.queue.current
        if job is None:
            QMessageBox.information(self, "Nothing running",
                                    "No simulation is running.")
            return

        answer = QMessageBox.question(
            self, "Stop simulation",
            f"Stop “{job.name}” now?\n\n"
            "Fluent will be shut down and the work so far is lost. "
            "Any case files already written are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return

        if self.queue.kill(job.job_id):
            self.statusBar().showMessage(
                f"Stopping {job.name}; Fluent may take a few seconds "
                f"to close", 8000)
        self._refresh_queue()

    def _cancel_selected(self) -> None:
        job = self._selected_job()
        if job is None:
            return
        if not self.queue.cancel(job.job_id):
            QMessageBox.information(
                self, "Cannot cancel",
                "Only pending simulations can be cancelled.")

    def _move(self, offset: int) -> None:
        job = self._selected_job()
        if job is not None:
            self.queue.move(job.job_id, offset)

    def _clear_finished(self) -> None:
        removed = self.queue.clear_finished()
        self.statusBar().showMessage(f"Removed {removed} finished job(s)", 4000)

    def _save_log(self) -> None:
        default = f"cfd_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", default, "Text Files (*.txt);;All Files (*)")
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.log.toPlainText())
            self.statusBar().showMessage(f"Log saved to {path}", 5000)

    def _about(self) -> None:
        types = "\n".join(f"    {name}" for _, name in simtypes.names())
        QMessageBox.about(
            self, "About",
            "<b>Ram Racing CFD Automation Suite</b><br>"
            "Colorado State University FSAE<br><br>"
            "Automates Ansys Fluent meshing and solving.<br>"
            "Each simulation type is one self-contained file "
            "under simtypes/.<br><br>"
            f"<pre>Available types:\n{types}</pre>")

    # ── Refresh ──────────────────────────────────────────────────────────

    def _selected_job(self):
        item = self.list.currentItem()
        if item is None:
            return None
        return self.queue.get(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_queue(self) -> None:
        jobs = self.queue.jobs()
        selected = self.list.currentItem()
        selected_id = (selected.data(Qt.ItemDataRole.UserRole)
                       if selected else None)

        self.list.blockSignals(True)
        self.list.clear()
        for job in jobs:
            label = f"[{job.job_id}]  {job.name}"
            if job.state is JobState.RUNNING:
                label += f"     {job.progress}%"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, job.job_id)
            item.setForeground(QColor(STATE_COLOURS.get(job.state.value,
                                                        TEXT_MUTED)))
            if job.state is JobState.RUNNING:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            item.setToolTip(f"{job.type_name}\n{job.state.value}\n"
                            f"{job.message}")
            self.list.addItem(item)
            if job.job_id == selected_id:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)

        running = sum(1 for j in jobs if j.state is JobState.RUNNING)
        pending = sum(1 for j in jobs if j.state is JobState.PENDING)
        self.lbl_queue_count.setText(
            f"{len(jobs)} total · {pending} pending"
            + (f" · {running} running" if running else ""))

        worker_live = self.queue.running
        self.btn_start.setEnabled(not worker_live and pending > 0)
        self.btn_pause.setEnabled(worker_live)
        self.btn_kill.setEnabled(running > 0)
        self.btn_start.setText(
            "▶  Start Queue" if not worker_live else "▶  Running…")

        self._show_detail()

    def _show_detail(self) -> None:
        job = self._selected_job()
        if job is None:
            self.detail_box.setTitle("")
            for widget in (self.d_type, self.d_state, self.d_speed,
                           self.d_iters, self.d_elapsed):
                widget.setText("—")
            self.d_output.setText("—")
            self.d_message.setText("")
            self.progress.setValue(0)
            self.results_box.setVisible(False)
            self.btn_edit.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            return

        s = job.settings
        self.detail_box.setTitle(job.name)
        self.d_type.setText(job.type_name)
        self.d_state.setText(job.state.value)
        self.d_state.setStyleSheet(
            f"color: {STATE_COLOURS.get(job.state.value, TEXT_MUTED)};")
        self.d_speed.setText(f"{s.speed_mph:.0f} mph   "
                             f"({s.speed_ms:.2f} m/s)")
        total = s.ramp1_iters + s.ramp2_iters + s.ramp3_iters
        self.d_iters.setText(
            f"{total:,}   ({s.ramp1_iters} / {s.ramp2_iters} / "
            f"{s.ramp3_iters})")

        elapsed = job.elapsed
        self.d_elapsed.setText(
            f"{int(elapsed // 60)}m {int(elapsed % 60):02d}s"
            if elapsed else "—")
        self.d_output.setText(s.output_dir or "—")

        self.progress.setValue(job.progress)
        self.d_message.setText(job.error or job.message)
        self.d_message.setStyleSheet(
            f"color: {ERROR};" if job.error else "")

        self.btn_edit.setEnabled(job.state is not JobState.RUNNING)
        self.btn_cancel.setEnabled(job.state is JobState.PENDING)

        self._show_results(job)

    def _show_results(self, job) -> None:
        while self.results_form.rowCount():
            self.results_form.removeRow(0)

        if job.state is not JobState.COMPLETED or not job.results:
            self.results_box.setVisible(False)
            return

        r = job.results
        rows = [
            ("Downforce Fz", f"{r.get('fz', 0):.1f} N"),
            ("Drag Fx",      f"{r.get('fx', 0):.1f} N"),
            ("L/D",          f"{r.get('ld_ratio', 0):.2f}"),
            ("SCz",          f"{r.get('SCz', 0):.4f} m²"),
            ("SCx",          f"{r.get('SCx', 0):.4f} m²"),
            ("CoP x",        f"{r.get('copx', 0):.4f} m"),
            ("Balance",      f"{r.get('cop_pct', 0):.1f} % forward"),
        ]
        for label, value in rows:
            widget = QLabel(value)
            widget.setObjectName("value")
            self.results_form.addRow(f"{label}:", widget)

        if r.get("result_file"):
            link = QLabel(os.path.basename(r["result_file"]))
            link.setObjectName("muted")
            link.setToolTip(r["result_file"])
            self.results_form.addRow("File:", link)

        self.results_box.setVisible(True)

    def _tick(self) -> None:
        """Keep the elapsed time live for a running job."""
        job = self._selected_job()
        if job and job.state is JobState.RUNNING:
            elapsed = job.elapsed
            self.d_elapsed.setText(
                f"{int(elapsed // 60)}m {int(elapsed % 60):02d}s")

    def _append_log(self, level: str, message: str) -> None:
        colour = LEVEL_COLOURS.get(level, "#abb2bf")
        self.log.appendHtml(
            f'<span style="color:{colour};">{message}</span>')

    # ── Close ────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        job = self.queue.current
        if job is not None:
            answer = QMessageBox.question(
                self, "Simulation running",
                f"“{job.name}” is still running.\n\n"
                "Yes  — stop it and quit\n"
                "No   — leave it running and quit anyway\n"
                "Cancel — stay open",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)

            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Yes:
                self.queue.kill(job.job_id)
        self.queue.stop()

        # Detach the log handler before Qt destroys it. Without this,
        # logging's atexit shutdown reaches a deleted C++ object and
        # prints a traceback after the window has closed.
        handler = getattr(self, "_log_bridge", None)
        if handler is not None:
            logging.getLogger().removeHandler(handler)
            self._log_bridge = None

        event.accept()
