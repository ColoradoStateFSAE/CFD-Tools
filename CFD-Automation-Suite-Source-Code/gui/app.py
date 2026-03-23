"""
Ram Racing CFD Automation Tool — Main Window (PyQt6).
"""
import os
import sys
import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QFrame, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QPlainTextEdit, QProgressBar, QStatusBar,
    QFileDialog, QMessageBox, QHeaderView, QAbstractItemView,
    QGroupBox, QFormLayout, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QAction, QIcon

from core.queue_manager import SimulationQueue, JobStatus
from simtypes.configs import SimType, SIM_TYPE_REGISTRY
from gui.theme import STATUS_COLORS, ACCENT, GREEN, RED, YELLOW, TEXT, ACCENT2


# ── Logging → QPlainTextEdit ──────────────────────────────────────────────────

class _QtLogHandler(logging.Handler, QObject):
    new_record = pyqtSignal(str)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter(
            "%(asctime)s  [%(levelname)s]  %(name)s — %(message)s",
            datefmt="%H:%M:%S"
        ))

    def emit(self, record):
        self.new_record.emit(self.format(record))


# ── Sim-type chooser dialog ───────────────────────────────────────────────────

class SimTypeChooserDialog(QWidget):
    """Popup that lets the user pick a sim type, then opens the editor."""

    def __init__(self, parent):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QRadioButton,
            QButtonGroup, QDialogButtonBox, QLabel, QFrame
        )
        self._dialog = QDialog(parent)
        self._dialog.setWindowTitle("Choose Simulation Type")
        self._dialog.setMinimumWidth(460)
        self._dialog.setModal(True)

        root = QVBoxLayout(self._dialog)
        root.setSpacing(12)
        root.setContentsMargins(24, 20, 24, 20)

        title = QLabel("Select simulation type")
        title.setObjectName("subheading")
        root.addWidget(title)

        descriptions = {
            SimType.HALF_CAR:
                "Symmetry plane at Z=0 — 2 wheels. Forces doubled automatically.",
            SimType.FULL_CAR:
                "Full 4-wheel simulation — no symmetry.",
            SimType.FRONT_WING_ONLY:
                "Isolated front wing element study.",
            SimType.REAR_WING_ONLY:
                "Isolated rear wing element study.",
            SimType.QUARTER_MODEL:
                "Quarter model — two symmetry planes.",
        }

        self._group = QButtonGroup(self._dialog)
        self._type_map = {}

        for sim_type, desc in descriptions.items():
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #282c34; border: 1px solid #3e4451;"
                " border-radius: 6px; padding: 4px; }"
                "QFrame:hover { border-color: #00b4a0; }"
                "QRadioButton { background: transparent; border: none; }"
                "QLabel { background: transparent; border: none; }"
            )
            card_l = QVBoxLayout(card)
            card_l.setContentsMargins(10, 8, 10, 8)
            card_l.setSpacing(2)

            rb = QRadioButton(sim_type.value)
            rb.setStyleSheet("font-weight: bold; font-size: 10pt;")
            if sim_type == SimType.HALF_CAR:
                rb.setChecked(True)
            self._group.addButton(rb)
            self._type_map[rb] = sim_type
            card_l.addWidget(rb)

            desc_lbl = QLabel(desc)
            desc_lbl.setObjectName("muted")
            desc_lbl.setContentsMargins(22, 0, 0, 0)
            card_l.addWidget(desc_lbl)

            root.addWidget(card)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Continue →")
        btns.button(QDialogButtonBox.StandardButton.Ok).setObjectName("accent")
        btns.accepted.connect(self._dialog.accept)
        btns.rejected.connect(self._dialog.reject)
        root.addWidget(btns)

        self.chosen_type = None

    def exec(self):
        from PyQt6.QtWidgets import QDialog
        if self._dialog.exec() == QDialog.DialogCode.Accepted:
            for btn, sim_type in self._type_map.items():
                if btn.isChecked():
                    self.chosen_type = sim_type
                    return True
        return False


# ── Main window ───────────────────────────────────────────────────────────────

class RamRacingCFDWindow(QMainWindow):
    # Signals fired from background thread → UI thread
    _job_update_signal  = pyqtSignal(object)
    _queue_update_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ram Racing | CFD Automation Tool")
        self.resize(1380, 860)
        self.setMinimumSize(960, 620)

        self._job_map: dict = {}   # job_id → QTreeWidgetItem

        # Queue
        self.sim_queue = SimulationQueue(
            on_job_update=self._job_update_signal.emit,
            on_queue_update=self._queue_update_signal.emit,
        )
        self._job_update_signal.connect(self._on_job_update)
        self._queue_update_signal.connect(self._on_queue_update)

        self._build_menu()
        self._build_ui()
        self._setup_logging()

        # Status bar clock
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)

        logging.info("Ram Racing CFD Automation Tool started.")

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        settings_act = QAction("Car Settings…", self)
        settings_act.setShortcut("Ctrl+,")
        settings_act.setToolTip("Set wheelbase, CoP geometry constants, reference area")
        settings_act.triggered.connect(self._open_car_settings)
        file_menu.addAction(settings_act)
        file_menu.addSeparator()
        save_log = QAction("Save Queue Log…", self)
        save_log.setShortcut("Ctrl+S")
        save_log.triggered.connect(self._save_log)
        file_menu.addAction(save_log)
        file_menu.addSeparator()
        quit_act = QAction("Exit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = mb.addMenu("&Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # ── Central UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ──
        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet(
            "QFrame { background-color: #282c34;"
            " border-bottom: 2px solid #00b4a0; }"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)

        import os
        from PyQt6.QtGui import QPixmap

        def _resource_path(relative):
            import sys
            if hasattr(sys, '_MEIPASS'):
                return os.path.join(sys._MEIPASS, relative)
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)

        icon_path = _resource_path(os.path.join("assets", "logo.png"))

        logo = QLabel("Ram Racing  |  CFD Automation")
        logo.setStyleSheet(
            "font-size: 15pt; font-weight: bold; color: #00b4a0;"
            " background: transparent;"
        )
        h_layout.addWidget(logo)
        h_layout.addStretch()

        sub = QLabel("Fluent 2024R2  •  PyFluent  •  PyQt6")
        sub.setStyleSheet("color: #abb2bf; background: transparent; font-size: 9pt;")
        h_layout.addWidget(sub)
        root.addWidget(header)

        # ── Main splitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        root.addWidget(splitter)

        # Left pane — queue
        left = QWidget()
        left.setMinimumWidth(580)
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(10, 10, 6, 10)
        left_v.setSpacing(8)
        self._build_queue_pane(left_v)
        splitter.addWidget(left)

        # Right pane — detail + log
        right = QWidget()
        right.setMinimumWidth(340)
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(6, 10, 10, 10)
        right_v.setSpacing(0)
        self._build_detail_pane(right_v)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # ── Status bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._clock_label = QLabel("--:--:--")
        self._clock_label.setStyleSheet("color: #abb2bf; padding-right: 8px;")
        self.status_bar.addPermanentWidget(self._clock_label)
        self.status_bar.showMessage("Ready")

    # ── Queue pane ────────────────────────────────────────────────────────────

    def _build_queue_pane(self, layout):
        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Simulation Queue")
        title.setObjectName("subheading")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.btn_add = QPushButton("＋  Add Simulation")
        self.btn_add.setObjectName("accent")
        self.btn_add.setFixedHeight(32)
        self.btn_add.clicked.connect(self._add_simulation)
        toolbar.addWidget(self.btn_add)

        for label, slot, danger in [
            ("▲", self._move_up, False),
            ("▼", self._move_down, False),
            ("✎  Edit", self._edit_job, False),
            ("✕  Cancel", self._cancel_job, True),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            if danger:
                btn.setObjectName("danger")
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)

        layout.addLayout(toolbar)

        # Queue tree
        cols = ["#", "Name", "Type", "Status", "Progress", "Queued At"]
        self.queue_tree = QTreeWidget()
        self.queue_tree.setHeaderLabels(cols)
        self.queue_tree.setRootIsDecorated(False)
        self.queue_tree.setAlternatingRowColors(True)
        self.queue_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.queue_tree.setUniformRowHeights(True)

        hdr = self.queue_tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.queue_tree.itemSelectionChanged.connect(self._on_tree_select)
        self.queue_tree.itemDoubleClicked.connect(lambda: self._edit_job())
        layout.addWidget(self.queue_tree)

    # ── Detail pane ───────────────────────────────────────────────────────────

    def _build_detail_pane(self, layout):
        self.detail_tabs = QTabWidget()
        layout.addWidget(self.detail_tabs)

        # Tab 1 — Job Detail
        detail_page = QScrollArea()
        detail_page.setWidgetResizable(True)
        detail_page.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        detail_page.setWidget(inner)
        detail_v = QVBoxLayout(inner)
        detail_v.setContentsMargins(14, 14, 14, 14)
        detail_v.setSpacing(12)
        self.detail_tabs.addTab(detail_page, "  Job Detail  ")
        self._build_detail_fields(detail_v)

        # Tab 2 — Log
        log_page = QWidget()
        log_v = QVBoxLayout(log_page)
        log_v.setContentsMargins(0, 0, 0, 0)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        log_v.addWidget(self.log_view)
        self.detail_tabs.addTab(log_page, "  Log  ")

    def _build_detail_fields(self, layout):
        # Info group
        info_group = QGroupBox("Selected Job")
        info_form = QFormLayout(info_group)
        info_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        info_form.setSpacing(6)

        self._detail_labels = {}
        fields = [
            ("job_id",      "Job ID"),
            ("name",        "Name"),
            ("sim_type",    "Type"),
            ("status",      "Status"),
            ("speed",       "Speed [mph]"),
            ("procs",       "Processes"),
            ("queued_at",   "Queued At"),
            ("started_at",  "Started At"),
            ("finished_at", "Finished At"),
            ("geometry",    "Geometry File"),
            ("output",      "Sim Output"),
            ("results_dir", "Results Dir"),
        ]
        for key, label in fields:
            val = QLabel("—")
            val.setWordWrap(True)
            if key == "status":
                val.setObjectName("status_queued")
            self._detail_labels[key] = val
            info_form.addRow(label + ":", val)
        layout.addWidget(info_group)

        # Progress group
        prog_group = QGroupBox("Progress")
        prog_v = QVBoxLayout(prog_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        prog_v.addWidget(self.progress_bar)
        self.progress_msg = QLabel("")
        self.progress_msg.setObjectName("muted")
        prog_v.addWidget(self.progress_msg)
        layout.addWidget(prog_group)

        # Results group
        res_group = QGroupBox("Results")
        res_v = QVBoxLayout(res_group)
        self.results_display = QPlainTextEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setFixedHeight(180)
        font = QFont("Consolas", 9)
        self.results_display.setFont(font)
        res_v.addWidget(self.results_display)
        layout.addWidget(res_group)

        layout.addStretch()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _add_simulation(self):
        chooser = SimTypeChooserDialog(self)
        if not chooser.exec():
            return
        config_cls = SIM_TYPE_REGISTRY[chooser.chosen_type]
        config = config_cls()
        self._open_editor(config, new=True)

    def _edit_job(self):
        job = self._selected_job()
        if job is None:
            return
        if job.status != JobStatus.QUEUED:
            QMessageBox.information(
                self, "Cannot Edit",
                "Only queued jobs can be edited.\n"
                f"This job is currently: {job.status.value}"
            )
            return
        self._open_editor(job.config, new=False, job=job)

    def _open_editor(self, config, new=False, job=None):
        from gui.sim_editor import SimEditorDialog
        dlg = SimEditorDialog(self, config)
        if dlg.exec() == SimEditorDialog.DialogCode.Accepted and dlg.accepted_ok:
            if new:
                self.sim_queue.add_job(dlg.config)
            else:
                job.config = dlg.config
                self._refresh_queue_tree()

    def _cancel_job(self):
        job = self._selected_job()
        if job:
            self.sim_queue.cancel_job(job.job_id)

    def _move_up(self):
        job = self._selected_job()
        if job:
            self.sim_queue.move_up(job.job_id)

    def _move_down(self):
        job = self._selected_job()
        if job:
            self.sim_queue.move_down(job.job_id)

    def _selected_job(self):
        items = self.queue_tree.selectedItems()
        if not items:
            return None
        job_id = int(items[0].text(0))
        for job in self.sim_queue.get_jobs():
            if job.job_id == job_id:
                return job
        return None

    def _open_car_settings(self):
        from gui.settings_dialog import CarSettingsDialog
        CarSettingsDialog(self).exec()

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Queue Log", "",
            "JSON (*.json);;All Files (*)"
        )
        if path:
            self.sim_queue.save_log(path)
            self.status_bar.showMessage(f"Log saved → {path}", 4000)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About",
            "<b>Ram Racing CFD Automation Tool</b><br>"
            "Aerodynamic Subteam<br><br>"
            "Built on PyFluent (Ansys Fluent 2024R2)<br>"
            "GUI: PyQt6<br><br>"
            "Based on Ram Racing Fluent Procedure documentation."
        )

    # ── Queue / job update callbacks (fire from worker → GUI thread) ──────────

    def _on_job_update(self, job):
        self._upsert_tree_item(job)
        sel = self._selected_job()
        if sel and sel.job_id == job.job_id:
            self._populate_detail(job)
        self.status_bar.showMessage(
            f"[{job.job_id}] {job.config.name}  →  {job.status.value}"
            + (f"  {job.progress_pct}%" if job.status == JobStatus.RUNNING else ""),
            0 if job.status == JobStatus.RUNNING else 5000
        )

    def _on_queue_update(self):
        self._refresh_queue_tree()

    def _refresh_queue_tree(self):
        sel_id = None
        sel = self._selected_job()
        if sel:
            sel_id = sel.job_id

        self.queue_tree.clear()
        self._job_map.clear()

        for job in self.sim_queue.get_jobs():
            self._upsert_tree_item(job)

        if sel_id:
            for i in range(self.queue_tree.topLevelItemCount()):
                item = self.queue_tree.topLevelItem(i)
                if item and int(item.text(0)) == sel_id:
                    self.queue_tree.setCurrentItem(item)
                    break

    def _upsert_tree_item(self, job):
        pct = f"{job.progress_pct}%" if job.status == JobStatus.RUNNING else ""
        values = [
            str(job.job_id),
            job.config.name,
            job.config.sim_type.value,
            job.status.value,
            pct,
            job.queued_at,
        ]
        color_hex = STATUS_COLORS.get(job.status.value, TEXT)
        color = QColor(color_hex)

        item = self._job_map.get(job.job_id)
        if item is None:
            item = QTreeWidgetItem(self.queue_tree, values)
            self._job_map[job.job_id] = item
        else:
            for c, v in enumerate(values):
                item.setText(c, v)

        for col in range(len(values)):
            item.setForeground(col, color)

        # Align center for all but name
        for col in [0, 2, 3, 4, 5]:
            item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)

    def _on_tree_select(self):
        job = self._selected_job()
        if job:
            self._populate_detail(job)

    def _populate_detail(self, job):
        d = self._detail_labels
        d["job_id"].setText(str(job.job_id))
        d["name"].setText(job.config.name)
        d["sim_type"].setText(job.config.sim_type.value)
        d["status"].setText(job.status.value)
        d["speed"].setText(f"{job.config.vehicle_speed_mph} mph")
        d["procs"].setText(str(job.config.num_processes))
        d["queued_at"].setText(job.queued_at)
        d["started_at"].setText(job.started_at or "—")
        d["finished_at"].setText(job.finished_at or "—")
        d["geometry"].setText(os.path.basename(job.config.geometry_path) or "—")
        d["output"].setText(job.config.output_dir or "—")
        d["results_dir"].setText(job.config.results_dir or "—")

        # Status label colour
        status_obj = {
            "Queued":    "status_queued",
            "Running":   "status_running",
            "Done":      "status_done",
            "Failed":    "status_failed",
            "Cancelled": "status_cancelled",
        }.get(job.status.value, "")
        d["status"].setObjectName(status_obj)
        d["status"].style().unpolish(d["status"])
        d["status"].style().polish(d["status"])

        # Progress
        self.progress_bar.setValue(job.progress_pct)
        self.progress_msg.setText(job.progress_msg)

        # Results
        self.results_display.clear()
        mult = 2.0 if job.config.is_half_symmetry else 1.0
        if job.status == JobStatus.DONE and job.results:
            r = job.results
            lines = [
                f"Front Wing Df  : {r.get('downforce_fw_lbf', 0) * mult:>8.2f} lbf",
                f"Rear Wing Df   : {r.get('downforce_rw_lbf', 0) * mult:>8.2f} lbf",
                f"Undertray Df   : {r.get('downforce_ut_lbf', 0) * mult:>8.2f} lbf",
                f"Total Df       : {r.get('downforce_lbf', 0):>8.2f} lbf",
                f"Total Drag     : {r.get('drag_lbf', 0):>8.2f} lbf",
                f"Aero Drag      : {r.get('drag_aero_lbf', 0) * mult:>8.2f} lbf",
                f"L/D Ratio      : {r.get('ld_ratio', 0):>8.3f}",
            ]
            if "note" in r:
                lines += ["", r["note"]]
            if "result_file" in r:
                lines += ["", f"Results → {r['result_file']}"]
            self.results_display.setPlainText("\n".join(lines))
        elif job.status == JobStatus.FAILED:
            self.results_display.setPlainText(
                f"FAILED:\n{job.error[:800]}"
            )

    # ── Logging ───────────────────────────────────────────────────────────────

    def _setup_logging(self):
        self._log_handler = _QtLogHandler()
        self._log_handler.new_record.connect(self._append_log)
        logging.getLogger().addHandler(self._log_handler)
        logging.getLogger().setLevel(logging.DEBUG)

    def _append_log(self, msg: str):
        self.log_view.appendPlainText(msg)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _tick_clock(self):
        self._clock_label.setText(datetime.now().strftime("%H:%M:%S"))

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Quit",
            "Exit the CFD Automation Tool?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.sim_queue.shutdown()
            event.accept()
        else:
            event.ignore()
