"""
Simulation editor.

Edits a simulation type's Settings dataclass. Fields are bound by attribute
name, so any simulation type exposing the standard names works here without
changes; anything it does not define is simply skipped.

Tabs: General, Meshing, Solver, Wheels, plus the two reference tables.
"""
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QFrame, QScrollArea, QFileDialog, QMessageBox, QGroupBox, QComboBox,
)
from PyQt6.QtCore import Qt

from gui.reference_tabs import NamedSelectionsTab, ReportDefinitionsTab
from utils.refinement import refinement_boxes


class SimEditor(QDialog):
    """Modal editor for one simulation's settings."""

    def __init__(self, sim_type, settings, parent=None, is_new=False):
        super().__init__(parent)
        self.sim_type = sim_type
        self.settings = settings

        self.setWindowTitle(
            f"{'New' if is_new else 'Edit'} Simulation — {sim_type.NAME}"
        )
        self.setMinimumSize(820, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet("QFrame { background-color: #282c34; "
                             "border-bottom: 1px solid #3e4451; }")
        head_layout = QVBoxLayout(header)
        head_layout.setContentsMargins(18, 12, 18, 12)
        title = QLabel(sim_type.NAME)
        title.setObjectName("heading")
        head_layout.addWidget(title)
        subtitle = QLabel(sim_type.__doc__.strip().splitlines()[0]
                          if sim_type.__doc__ else "")
        subtitle.setObjectName("muted")
        head_layout.addWidget(subtitle)
        root.addWidget(header)

        # ── Tabs ─────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)

        self._build_general()
        self._build_meshing()
        self._build_solver()
        if hasattr(settings, "front_wheel_origin"):
            self._build_wheels()

        selections = NamedSelectionsTab()
        selections.load(sim_type)
        self.tabs.addTab(selections, "  Named Selections  ")

        reports = ReportDefinitionsTab()
        reports.load(sim_type)
        self.tabs.addTab(reports, "  Reports  ")

        # ── Buttons ──────────────────────────────────────────────────────
        footer = QFrame()
        footer.setStyleSheet("QFrame { background-color: #282c34; "
                             "border-top: 1px solid #3e4451; }")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(18, 11, 18, 11)

        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        foot.addWidget(self.summary)
        foot.addStretch()

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)

        accept = QPushButton("Save")
        accept.setObjectName("accent")
        accept.setDefault(True)
        accept.clicked.connect(self._accept)
        foot.addWidget(accept)

        root.addWidget(footer)

        self._load()
        self._refresh_summary()

    # ── Tab construction helpers ─────────────────────────────────────────

    def _tab(self, title: str):
        """Return a (page, form) pair already added as a scrollable tab."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(4)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(9)
        outer.addLayout(form)
        outer.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)
        return page, form

    @staticmethod
    def _sub(form, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("subheading")
        form.addRow(label)

    @staticmethod
    def _note(form, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("muted")
        label.setWordWrap(True)
        form.addRow("", label)

    @staticmethod
    def _hr(form) -> None:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        form.addRow(line)

    def _browse_row(self, edit: QLineEdit, caption: str,
                    file_filter: str = "", directory: bool = False) -> QWidget:
        """A line edit with a Browse button beside it."""
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(edit, 1)

        button = QPushButton("Browse…")
        button.setFixedWidth(84)

        def pick():
            if directory:
                path = QFileDialog.getExistingDirectory(self, caption,
                                                        edit.text())
            else:
                path, _ = QFileDialog.getOpenFileName(self, caption,
                                                      edit.text(), file_filter)
            if path:
                edit.setText(path)

        button.clicked.connect(pick)
        row.addWidget(button)
        return box

    @staticmethod
    def _spin(minimum, maximum, decimals=0, step=1.0, suffix=""):
        widget = QSpinBox() if decimals == 0 else QDoubleSpinBox()
        widget.setRange(int(minimum) if decimals == 0 else minimum,
                        int(maximum) if decimals == 0 else maximum)
        if decimals:
            widget.setDecimals(decimals)
            widget.setSingleStep(step)
        if suffix:
            widget.setSuffix(f"  {suffix}")
        return widget

    # ── General ──────────────────────────────────────────────────────────

    def _build_general(self):
        _, form = self._tab("  General  ")

        self._sub(form, "Identity")
        self._note(form,
                   "Project, Run and MAP match the CFD Rolling Report. The "
                   "Point ID built from them names this run's folder and "
                   "every file in it, so a folder and its Master Log row "
                   "always share a name.")

        from utils.naming import existing_projects, existing_runs

        # Project: editable, but offers what is already on disk
        self.combo_project = QComboBox()
        self.combo_project.setEditable(True)
        self.combo_project.setPlaceholderText("e.g. Dauntless")
        self.combo_project.currentTextChanged.connect(self._project_changed)
        form.addRow("Project:", self.combo_project)

        self.combo_run = QComboBox()
        self.combo_run.setEditable(True)
        self.combo_run.setPlaceholderText("e.g. 18  or  R018")
        self.combo_run.currentTextChanged.connect(self._run_changed)
        form.addRow("Run:", self.combo_run)

        map_row = QWidget()
        map_layout = QHBoxLayout(map_row)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(6)
        self.sb_map = self._spin(1, 999)
        self.sb_map.valueChanged.connect(self._refresh_identity)
        map_layout.addWidget(self.sb_map, 1)
        next_button = QPushButton("Next free")
        next_button.setFixedWidth(84)
        next_button.setToolTip(
            "Use the first MAP number this run has not used yet")
        next_button.clicked.connect(self._use_next_map)
        map_layout.addWidget(next_button)
        form.addRow("MAP number:", map_row)

        self.lbl_point_id = QLabel("")
        self.lbl_point_id.setObjectName("value")
        form.addRow("Point ID:", self.lbl_point_id)

        self.e_description = QLineEdit()
        self.e_description.setPlaceholderText(
            "Optional: what this point is testing, for the Master Log")
        form.addRow("Description:", self.e_description)

        self.lbl_folder = QLabel("")
        self.lbl_folder.setObjectName("muted")
        self.lbl_folder.setWordWrap(True)
        self.lbl_folder.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Folder:", self.lbl_folder)

        self._hr(form)
        self._sub(form, "Geometry")
        self.e_geometry = QLineEdit()
        self.e_geometry.setPlaceholderText("Watertight .pmdb exported from Discovery")
        form.addRow("Geometry:", self._browse_row(
            self.e_geometry, "Select Geometry",
            "Ansys Geometry (*.pmdb *.dsco);;All Files (*)"))

        self._hr(form)
        self._sub(form, "Skip Meshing")
        self.e_existing = QLineEdit()
        self.e_existing.setPlaceholderText(
            "Optional: an existing .msh.h5 to solve directly")
        form.addRow("Existing mesh:", self._browse_row(
            self.e_existing, "Select Mesh",
            "Fluent Mesh (*.msh.h5 *.msh *.cas.h5);;All Files (*)"))
        self._note(form,
                   "When set, meshing is skipped entirely and the solver runs "
                   "against this file. Useful for trying solver settings "
                   "without waiting on a remesh.")

        self._hr(form)
        self._sub(form, "Operating Point")
        self.sb_speed = self._spin(1, 300, 1, 1.0, "mph")
        self.sb_speed.valueChanged.connect(self._refresh_summary)
        form.addRow("Vehicle speed:", self.sb_speed)
        self.lbl_speed = QLabel("")
        self.lbl_speed.setObjectName("muted")
        form.addRow("", self.lbl_speed)

        self._sub(form, "Fluent Session")
        import os as _os
        cores = _os.cpu_count() or 1
        self.sb_processes = self._spin(1, 512)
        self.sb_processes.valueChanged.connect(self._check_processes)
        form.addRow("Processes:", self.sb_processes)

        self.lbl_processes = QLabel("")
        self.lbl_processes.setObjectName("muted")
        self.lbl_processes.setWordWrap(True)
        form.addRow("", self.lbl_processes)
        self._machine_cores = cores

        self._note(form,
                   "ThreadRipper 40–50 · Xeon Gold 60–70 · Big Boi 128–170. "
                   "Asking for more processes than the machine has cores "
                   "stalls Fluent during parallel start-up.")

        self.combo_mpi = QComboBox()
        try:
            from simtypes.half_car import MPI_TYPES
            self.combo_mpi.addItems(MPI_TYPES)
        except Exception:
            self.combo_mpi.addItems(["intel", "openmpi", "msmpi", "default"])
        form.addRow("MPI type:", self.combo_mpi)
        self._note(form,
                   "intel for the Xeon Gold nodes · openmpi for ThreadRipper · "
                   "default lets Fluent choose. Passed as -mpi=<type>.")

        self.cb_double = QCheckBox("Double precision")
        form.addRow("", self.cb_double)

    # ── Meshing ──────────────────────────────────────────────────────────

    def _build_meshing(self):
        _, form = self._tab("  Meshing  ")

        self._sub(form, "Car Dimensions")
        self._note(form, "Drive the Near / Mid / Far refinement boxes below.")
        self.sb_length = self._spin(0.1, 20, 3, 0.05, "m")
        self.sb_width  = self._spin(0.1, 10, 3, 0.05, "m")
        self.sb_height = self._spin(0.1, 10, 3, 0.05, "m")
        for widget in (self.sb_length, self.sb_width, self.sb_height):
            widget.valueChanged.connect(self._refresh_boxes)
        form.addRow("Length  (x):", self.sb_length)
        form.addRow("Width   (z):", self.sb_width)
        form.addRow("Height  (y):", self.sb_height)

        self.sb_wheelbase = self._spin(0.1, 10, 3, 0.01, "m")
        form.addRow("Wheelbase:", self.sb_wheelbase)

        self._hr(form)
        self._sub(form, "Refinement Regions")
        self.lbl_boxes = QLabel("")
        self.lbl_boxes.setObjectName("muted")
        self.lbl_boxes.setStyleSheet(
            "font-family: 'Cascadia Mono', 'Consolas', monospace; "
            "font-size: 11px;")
        self.lbl_boxes.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(self.lbl_boxes)

        self._hr(form)
        self._sub(form, "Surface Mesh")
        self.sb_surf_min = self._spin(0.0001, 1, 4, 0.001, "m")
        self.sb_surf_max = self._spin(0.001, 5, 3, 0.01, "m")
        form.addRow("Minimum size:", self.sb_surf_min)
        form.addRow("Maximum size:", self.sb_surf_max)

        self._sub(form, "Volume Mesh")
        self.sb_vol_min = self._spin(0.0001, 1, 4, 0.001, "m")
        self.sb_vol_max = self._spin(0.001, 5, 3, 0.01, "m")
        form.addRow("Minimum cell:", self.sb_vol_min)
        form.addRow("Maximum cell:", self.sb_vol_max)

        self._sub(form, "Boundary Layers")
        self.sb_bl_layers = self._spin(1, 40)
        self.sb_bl_height = self._spin(0.00001, 0.1, 5, 0.0001, "m")
        form.addRow("Layer count:", self.sb_bl_layers)
        form.addRow("First height:", self.sb_bl_height)
        self._note(form, "Grown on the aero surfaces and the ground.")

    # ── Solver ───────────────────────────────────────────────────────────

    def _build_solver(self):
        _, form = self._tab("  Solver  ")

        self._sub(form, "Ramp Sequence")
        self._note(form,
                   "Three stages, each starting from the previous result. "
                   "Raise the counts if the force monitors have not flattened "
                   "by the end of a stage.")

        self.sb_ramp1 = self._spin(0, 100000)
        self.sb_ramp2 = self._spin(0, 100000)
        self.sb_ramp3 = self._spin(0, 100000)
        for widget in (self.sb_ramp1, self.sb_ramp2, self.sb_ramp3):
            widget.setSingleStep(50)
            widget.valueChanged.connect(self._refresh_summary)

        form.addRow("1  First order:", self.sb_ramp1)
        self._note(form, "Standard pressure, first order momentum. Stabilises "
                         "the field from the hybrid initialisation.")
        form.addRow("2  Second order:", self.sb_ramp2)
        self._note(form, "PRESTO! pressure, second order momentum.")
        form.addRow("3  Full send:", self.sb_ramp3)
        self._note(form, "SIMPLEC, full second order, curvature correction on. "
                         "The values reported come from this stage.")

        self.lbl_total_iters = QLabel("")
        self.lbl_total_iters.setObjectName("value")
        form.addRow("Total:", self.lbl_total_iters)

        self._hr(form)
        self._sub(form, "Exports")
        self.cb_ensight = QCheckBox(
            "Write EnSight Gold for ParaView after solving")
        form.addRow("", self.cb_ensight)
        self._note(form,
                   "Creates <output>/<name>_ensight/. Open the .encas file in "
                   "ParaView. The results .txt is always written.")

    # ── Wheels ───────────────────────────────────────────────────────────

    def _build_wheels(self):
        _, form = self._tab("  Wheels  ")

        self._sub(form, "Rotating Walls")
        self._note(form,
                   "Wheels are modelled as rotating walls: moving wall, "
                   "absolute, rotational about the axle. The rotation rate "
                   "follows from the vehicle speed and wheel radius, so only "
                   "the geometry is set here.")

        self.sb_wheel_radius = self._spin(0.01, 1.0, 4, 0.001, "m")
        self.sb_wheel_radius.valueChanged.connect(self._refresh_summary)
        form.addRow("Wheel radius:", self.sb_wheel_radius)

        self.lbl_omega = QLabel("")
        self.lbl_omega.setObjectName("value")
        form.addRow("Rotation rate:", self.lbl_omega)

        self._hr(form)
        self._sub(form, "Front Axle Origin")
        self._note(form, "Axle centre in metres. Y is normally the wheel "
                         "radius, so the wheel sits on the ground.")
        self.front_xyz = []
        for axis in ("X", "Y", "Z"):
            widget = self._spin(-50, 50, 4, 0.001, "m")
            self.front_xyz.append(widget)
            form.addRow(f"Front  {axis}:", widget)

        self._sub(form, "Rear Axle Origin")
        self.rear_xyz = []
        for axis in ("X", "Y", "Z"):
            widget = self._spin(-50, 50, 4, 0.001, "m")
            self.rear_xyz.append(widget)
            form.addRow(f"Rear   {axis}:", widget)

        self._note(form,
                   "Both axles rotate about +Z. If the origin sits at the "
                   "wheelbase centre rather than the front axle, the reported "
                   "aero balance is measured from that centre.")

    # ── Load and save ────────────────────────────────────────────────────

    def _load(self) -> None:
        s = self.settings
        from utils.naming import existing_projects, existing_runs

        root = getattr(s, "output_root", "")
        self.combo_project.blockSignals(True)
        self.combo_project.clear()
        if root:
            self.combo_project.addItems(existing_projects(root))
        self.combo_project.setCurrentText(s.project)
        self.combo_project.blockSignals(False)

        self.combo_run.blockSignals(True)
        self.combo_run.clear()
        if root and s.project:
            self.combo_run.addItems(existing_runs(root, s.project))
        self.combo_run.setCurrentText(s.run)
        self.combo_run.blockSignals(False)

        self.sb_map.setValue(max(1, s.map_number))

        self.e_description.setText(getattr(s, "description", ""))
        self.e_geometry.setText(s.geometry_path)
        self.e_existing.setText(s.existing_mesh)
        self.sb_speed.setValue(s.speed_mph)
        self.sb_processes.setValue(s.processes)
        self.cb_double.setChecked(s.double_precision)
        if hasattr(s, "mpi_type"):
            index = self.combo_mpi.findText(s.mpi_type)
            self.combo_mpi.setCurrentIndex(index if index >= 0 else 0)

        self.sb_length.setValue(s.car_length)
        self.sb_width.setValue(s.car_width)
        self.sb_height.setValue(s.car_height)
        self.sb_wheelbase.setValue(s.wheelbase)
        self.sb_surf_min.setValue(s.surface_min)
        self.sb_surf_max.setValue(s.surface_max)
        self.sb_vol_min.setValue(s.volume_min)
        self.sb_vol_max.setValue(s.volume_max)
        self.sb_bl_layers.setValue(s.bl_layers)
        self.sb_bl_height.setValue(s.bl_first_height)

        self.sb_ramp1.setValue(s.ramp1_iters)
        self.sb_ramp2.setValue(s.ramp2_iters)
        self.sb_ramp3.setValue(s.ramp3_iters)
        self.cb_ensight.setChecked(s.export_ensight)

        if hasattr(self, "front_xyz"):
            self.sb_wheel_radius.setValue(s.wheel_radius)
            for widget, value in zip(self.front_xyz, s.front_wheel_origin):
                widget.setValue(value)
            for widget, value in zip(self.rear_xyz, s.rear_wheel_origin):
                widget.setValue(value)

        self._check_processes()
        self._refresh_identity()
        self._refresh_boxes()

    def _save(self) -> None:
        s = self.settings
        s.project = self.combo_project.currentText().strip()
        s.run = self.combo_run.currentText().strip()
        s.map_number = self.sb_map.value()

        s.description = self.e_description.text().strip()
        s.geometry_path = self.e_geometry.text().strip()
        s.existing_mesh = self.e_existing.text().strip()
        s.speed_mph = self.sb_speed.value()
        s.processes = self.sb_processes.value()
        s.double_precision = self.cb_double.isChecked()
        if hasattr(s, "mpi_type"):
            s.mpi_type = self.combo_mpi.currentText()

        s.car_length = self.sb_length.value()
        s.car_width = self.sb_width.value()
        s.car_height = self.sb_height.value()
        s.wheelbase = self.sb_wheelbase.value()
        s.surface_min = self.sb_surf_min.value()
        s.surface_max = self.sb_surf_max.value()
        s.volume_min = self.sb_vol_min.value()
        s.volume_max = self.sb_vol_max.value()
        s.bl_layers = self.sb_bl_layers.value()
        s.bl_first_height = self.sb_bl_height.value()

        s.ramp1_iters = self.sb_ramp1.value()
        s.ramp2_iters = self.sb_ramp2.value()
        s.ramp3_iters = self.sb_ramp3.value()
        s.export_ensight = self.cb_ensight.isChecked()

        if hasattr(self, "front_xyz"):
            s.wheel_radius = self.sb_wheel_radius.value()
            s.front_wheel_origin = [w.value() for w in self.front_xyz]
            s.rear_wheel_origin = [w.value() for w in self.rear_xyz]

    def _accept(self) -> None:
        self._save()
        problems = self.settings.validate()
        if problems:
            QMessageBox.warning(
                self, "Incomplete settings",
                "Fix the following before saving:\n\n  • "
                + "\n  • ".join(problems))
            return
        self.accept()

    # ── Live feedback ────────────────────────────────────────────────────

    # ── Identity ─────────────────────────────────────────────────────────

    def _project_changed(self) -> None:
        """Repopulate the run list for the project just chosen."""
        from utils.naming import existing_runs
        root = getattr(self.settings, "output_root", "")
        project = self.combo_project.currentText().strip()

        current = self.combo_run.currentText()
        self.combo_run.blockSignals(True)
        self.combo_run.clear()
        if root and project:
            self.combo_run.addItems(existing_runs(root, project))
        self.combo_run.setCurrentText(current)
        self.combo_run.blockSignals(False)

        self._refresh_identity()

    def _run_changed(self) -> None:
        self._refresh_identity()

    def _use_next_map(self) -> None:
        """Jump to the first MAP number this run has not used."""
        from utils.naming import next_map_number
        root = getattr(self.settings, "output_root", "")
        self.sb_map.setValue(next_map_number(
            root,
            self.combo_project.currentText().strip(),
            self.combo_run.currentText().strip(),
        ))

    def _refresh_identity(self) -> None:
        """Show the Point ID and folder these three fields produce."""
        from utils.naming import RunIdentity

        identity = RunIdentity(
            project=self.combo_project.currentText().strip(),
            run=self.combo_run.currentText().strip(),
            map_number=self.sb_map.value(),
            root=getattr(self.settings, "output_root", ""),
        )

        self.lbl_point_id.setText(identity.point_id or "—")

        problems = identity.validate()
        if problems:
            self.lbl_folder.setText(problems[0])
            self.lbl_folder.setStyleSheet("color: #e5c07b;")
        elif identity.exists:
            self.lbl_folder.setText(
                f"{identity.map_dir}\n"
                f"This point already exists and will be overwritten.")
            self.lbl_folder.setStyleSheet("color: #e5c07b;")
        else:
            self.lbl_folder.setText(identity.map_dir)
            self.lbl_folder.setStyleSheet("color: #7f8593;")

        self._refresh_summary()

    def _check_processes(self) -> None:
        """Warn as soon as the process count exceeds the machine's cores."""
        cores = getattr(self, "_machine_cores", 1)
        requested = self.sb_processes.value()
        if requested > cores:
            self.lbl_processes.setText(
                f"This machine has {cores} cores. {requested} processes will "
                f"stall Fluent during start-up.")
            self.lbl_processes.setStyleSheet("color: #e06c75;")
        else:
            self.lbl_processes.setText(f"This machine has {cores} cores.")
            self.lbl_processes.setStyleSheet("color: #7f8593;")

    def _refresh_boxes(self) -> None:
        """Show the refinement boxes the current dimensions produce."""
        half = "half" in self.sim_type.KEY or "quarter" in self.sim_type.KEY
        try:
            boxes = refinement_boxes(self.sb_length.value(),
                                     self.sb_width.value(),
                                     self.sb_height.value(),
                                     half_model=half)
        except Exception:
            return
        lines = []
        for box in boxes:
            label = box.name.replace("local-refinement-", "")
            lines.append(
                f"{label:10s} {box.size:5.3f} m   "
                f"X [{box.x_min:7.2f}, {box.x_max:7.2f}]   "
                f"Y [{box.y_min:6.2f}, {box.y_max:6.2f}]   "
                f"Z [{box.z_min:6.2f}, {box.z_max:6.2f}]"
            )
        if half:
            lines.append("")
            lines.append("z_min clamped to 0 for the half model")
        self.lbl_boxes.setText("\n".join(lines))
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        """Footer summary plus the derived speed and wheel rate."""
        try:
            speed_ms = self.sb_speed.value() * 0.44704
            self.lbl_speed.setText(
                f"{speed_ms:.3f} m/s     dynamic pressure "
                f"{0.5 * 1.225 * speed_ms ** 2:.1f} Pa")

            total = (self.sb_ramp1.value() + self.sb_ramp2.value()
                     + self.sb_ramp3.value())
            self.lbl_total_iters.setText(f"{total:,} iterations")

            if hasattr(self, "lbl_omega"):
                radius = self.sb_wheel_radius.value()
                if radius > 0:
                    omega = speed_ms / radius
                    self.lbl_omega.setText(
                        f"{omega:.2f} rad/s     {omega * 60 / 6.283185:.0f} rpm")

            point = self.lbl_point_id.text()
            prefix = f"{point}   ·   " if point and point != "—" else ""
            self.summary.setText(
                f"{prefix}"
                f"{self.sb_speed.value():.0f} mph   ·   "
                f"{total:,} iterations   ·   "
                f"{self.sb_processes.value()} processes")
        except Exception:
            pass
