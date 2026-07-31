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
        self.e_name = QLineEdit()
        form.addRow("Simulation name:", self.e_name)

        self._sub(form, "Files")
        self.e_geometry = QLineEdit()
        self.e_geometry.setPlaceholderText("Watertight .pmdb exported from Discovery")
        form.addRow("Geometry:", self._browse_row(
            self.e_geometry, "Select Geometry",
            "Ansys Geometry (*.pmdb *.dsco);;All Files (*)"))

        self.e_output = QLineEdit()
        form.addRow("Output folder:", self._browse_row(
            self.e_output, "Select Output Folder", directory=True))

        self.e_results = QLineEdit()
        self.e_results.setPlaceholderText("Leave blank to use the output folder")
        form.addRow("Results folder:", self._browse_row(
            self.e_results, "Select Results Folder", directory=True))

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
        self.sb_processes = self._spin(1, 512)
        form.addRow("Processes:", self.sb_processes)
        self._note(form,
                   "ThreadRipper 40–50 · Xeon Gold 60–70 · Big Boi 128–170")

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
        self.e_name.setText(s.name)
        self.e_geometry.setText(s.geometry_path)
        self.e_output.setText(s.output_dir)
        self.e_results.setText(s.results_dir)
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

        self._refresh_boxes()

    def _save(self) -> None:
        s = self.settings
        s.name = self.e_name.text().strip()
        s.geometry_path = self.e_geometry.text().strip()
        s.output_dir = self.e_output.text().strip()
        s.results_dir = self.e_results.text().strip() or s.output_dir
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

            self.summary.setText(
                f"{self.sb_speed.value():.0f} mph   ·   "
                f"{total:,} iterations   ·   "
                f"{self.sb_processes.value()} processes")
        except Exception:
            pass
