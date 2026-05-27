"""
Simulation configuration editor — PyQt6.
Tabbed dialog: General | Meshing | Ramp-Up | Wheel MRF
CoP is derived automatically from Fluent moment reports — no geometry tab needed.
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QGroupBox, QLabel, QLineEdit,
    QDoubleSpinBox, QSpinBox, QComboBox, QCheckBox, QPushButton,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QFrame, QSizePolicy, QTextEdit
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor

from simtypes.configs import BaseSimConfig, WheelMRFConfig, SIM_TYPE_REGISTRY

MPI_OPTIONS = ["openmpi", "intel", "default"]


def _browse_file(parent, var: QLineEdit, title: str,
                 filters: str = "All Files (*)"):
    path, _ = QFileDialog.getOpenFileName(parent, title, "", filters)
    if path:
        var.setText(path)


def _browse_dir(parent, var: QLineEdit, title: str = "Select Directory"):
    path = QFileDialog.getExistingDirectory(parent, title, "")
    if path:
        var.setText(path)


class SimEditorDialog(QDialog):
    def __init__(self, parent, config: BaseSimConfig):
        super().__init__(parent)
        self.config = config
        self.accepted_ok = False
        self.setWindowTitle(
            f"Edit Simulation — {config.sim_type.value}"
        )
        self.setMinimumSize(680, 620)
        self.setModal(True)
        self._build()
        self._load_from_config()

    # ── Main layout ───────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        hdr = QFrame()
        hdr.setStyleSheet(
            "QFrame { background-color: #282c34; border-bottom: 1px solid #3e4451; }"
        )
        hdr.setFixedHeight(52)
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(16, 0, 16, 0)
        title = QLabel(f"⚙  {self.config.sim_type.value} Configuration")
        title.setObjectName("subheading")
        hdr_l.addWidget(title)
        root.addWidget(hdr)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs)

        self._build_general_tab()
        self._build_mesh_tab()
        self._build_rampup_tab()
        if self.config.use_wheel_mrf:
            self._build_wheel_tab()
        from simtypes.configs import SimType
        if self.config.sim_type == SimType.TURNING:
            self._build_turning_tab()

        # Button row
        btn_frame = QFrame()
        btn_frame.setStyleSheet(
            "QFrame { background-color: #282c34; border-top: 1px solid #3e4451; }"
        )
        btn_l = QHBoxLayout(btn_frame)
        btn_l.setContentsMargins(16, 10, 16, 10)
        btn_l.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_l.addWidget(cancel_btn)

        ok_btn = QPushButton("✔  Accept")
        ok_btn.setObjectName("accent")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._accept)
        btn_l.addWidget(ok_btn)

        root.addWidget(btn_frame)

    # ── General tab ───────────────────────────────────────────────────────────

    def _build_general_tab(self):
        w = self._scroll_tab("  General  ")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(9)
        form.setContentsMargins(20, 16, 20, 16)

        self.e_name = QLineEdit()
        form.addRow("Simulation Name:", self.e_name)

        self.sb_speed = QDoubleSpinBox()
        self.sb_speed.setRange(1, 300)
        self.sb_speed.setDecimals(1)
        self.sb_speed.setSuffix("  mph")
        form.addRow("Vehicle Speed:", self.sb_speed)

        form.addRow(self._hsep())

        # Geometry path — pmdb/dsco only
        self.e_geom = QLineEdit()
        self.e_geom.setPlaceholderText("Select .pmdb or .dsco file from Discovery…")
        geom_btn = QPushButton("Browse…")
        geom_btn.clicked.connect(
            lambda: _browse_file(
                self, self.e_geom,
                "Select Geometry (.pmdb or .dsco)",
                "Ansys Discovery Files (*.pmdb *.dsco);;PMDB (*.pmdb);;DSCO (*.dsco)"
            )
        )
        form.addRow("Geometry File:", self._browse_row(self.e_geom, geom_btn))

        # Output dirs
        self.e_output = QLineEdit()
        self.e_output.setPlaceholderText("Where Fluent saves .cas.h5 files…")
        out_btn = QPushButton("Browse…")
        out_btn.clicked.connect(
            lambda: _browse_dir(self, self.e_output, "Select Simulation Output Directory")
        )
        form.addRow("Sim Output Dir:", self._browse_row(self.e_output, out_btn))

        self.e_results = QLineEdit()
        self.e_results.setPlaceholderText("Where the results .txt report is saved…")
        res_btn = QPushButton("Browse…")
        res_btn.clicked.connect(
            lambda: _browse_dir(self, self.e_results, "Select Results Export Directory")
        )
        form.addRow("Results Export Dir:", self._browse_row(self.e_results, res_btn))

        form.addRow(self._hsep())

        # HPC settings
        hpc_label = QLabel("HPC / Solver Settings")
        hpc_label.setObjectName("subheading")
        form.addRow(hpc_label)

        self.sb_procs = QSpinBox()
        self.sb_procs.setRange(1, 512)
        self.sb_procs.setToolTip(
            "ThreadRipper: 40–50  |  Xeon Gold: 60  |  Big Boi: 128–170"
        )
        form.addRow("Processes:", self.sb_procs)

        self.sb_timeout = QSpinBox()
        self.sb_timeout.setRange(60, 1800)
        self.sb_timeout.setSingleStep(30)
        self.sb_timeout.setSuffix(" s")
        self.sb_timeout.setToolTip(
            "How long to wait for Fluent to start before giving up. "
            "Increase to 300-600s on slow HPC cluster machines."
        )
        form.addRow("Launch Timeout:", self.sb_timeout)

        self.cb_mpi = QComboBox()
        self.cb_mpi.addItems(MPI_OPTIONS)
        self.cb_mpi.setToolTip(
            "ThreadRipper → openmpi  |  Xeon Gold → intel  |  Big Boi → default"
        )
        form.addRow("MPI Type:", self.cb_mpi)

        self.chk_double = QCheckBox("Double Precision  (recommended)")
        form.addRow("", self.chk_double)

        form.addRow(self._hsep())

        # Car dimensions
        dim_label = QLabel("Car Dimensions  (for refinement box sizing)")
        dim_label.setObjectName("subheading")
        form.addRow(dim_label)

        self.sb_cl = QDoubleSpinBox()
        self.sb_cl.setRange(0.1, 10); self.sb_cl.setDecimals(3); self.sb_cl.setSuffix(" m")
        form.addRow("Length L (X axis):", self.sb_cl)

        self.sb_cw = QDoubleSpinBox()
        self.sb_cw.setRange(0.1, 10); self.sb_cw.setDecimals(3); self.sb_cw.setSuffix(" m")
        form.addRow("Width W (Z axis):", self.sb_cw)

        self.sb_ch = QDoubleSpinBox()
        self.sb_ch.setRange(0.1, 10); self.sb_ch.setDecimals(3); self.sb_ch.setSuffix(" m")
        form.addRow("Height H (Y axis):", self.sb_ch)

        form.addRow(self._hsep())

        wb_label = QLabel("CoP Calculation")
        wb_label.setObjectName("subheading")
        form.addRow(wb_label)

        self.sb_wheelbase = QDoubleSpinBox()
        self.sb_wheelbase.setRange(10.0, 300.0)
        self.sb_wheelbase.setDecimals(2)
        self.sb_wheelbase.setSingleStep(0.5)
        self.sb_wheelbase.setSuffix(" in")
        self.sb_wheelbase.setToolTip(
            "Front-to-rear axle distance. Used to compute front/rear aero balance %.\n"
            "Lf, Lr, Lu are derived automatically from Fluent moment reports — "
            "no hand measurement needed."
        )
        note_wb = QLabel("Lf / Lr / Lu derived from simulation moment data automatically.")
        note_wb.setObjectName("muted")
        note_wb.setWordWrap(True)
        form.addRow("Wheelbase L:", self.sb_wheelbase)
        form.addRow(note_wb)

        w.layout().addLayout(form)
        w.layout().addStretch()

    # ── Mesh tab ──────────────────────────────────────────────────────────────

    def _build_mesh_tab(self):
        w = self._scroll_tab("  Meshing  ")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(9)
        form.setContentsMargins(20, 16, 20, 16)

        surf = QLabel("Surface Mesh")
        surf.setObjectName("subheading")
        form.addRow(surf)

        self.sb_surf_min = self._mspin()
        self.sb_surf_max = self._mspin(max_v=1.0)
        form.addRow("Min Size [m]:", self.sb_surf_min)
        form.addRow("Max Size [m]:", self.sb_surf_max)

        form.addRow(self._hsep())

        vol = QLabel("Volume Mesh")
        vol.setObjectName("subheading")
        form.addRow(vol)

        self.sb_vol_min = self._mspin()
        self.sb_vol_max = self._mspin(max_v=1.0)
        form.addRow("Min Size [m]:", self.sb_vol_min)
        form.addRow("Max Size [m]:", self.sb_vol_max)

        form.addRow(self._hsep())

        bl = QLabel("Boundary Layers")
        bl.setObjectName("subheading")
        form.addRow(bl)

        self.sb_bl_layers = QSpinBox()
        self.sb_bl_layers.setRange(1, 30)
        form.addRow("Number of Layers:", self.sb_bl_layers)

        self.sb_bl_first = self._mspin(max_v=0.01, step=0.0001, decimals=5)
        form.addRow("First Height [m]:", self.sb_bl_first)

        self.sb_bl_trans = QDoubleSpinBox()
        self.sb_bl_trans.setRange(0.1, 1.0)
        self.sb_bl_trans.setDecimals(4)
        self.sb_bl_trans.setSingleStep(0.01)
        form.addRow("Transition Ratio:", self.sb_bl_trans)

        w.layout().addLayout(form)
        w.layout().addStretch()

    # ── Ramp-up tab ───────────────────────────────────────────────────────────

    def _build_rampup_tab(self):
        w = self._scroll_tab("  Ramp-Up  ")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(9)
        form.setContentsMargins(20, 16, 20, 16)

        lbl = QLabel("Ramp-Up Iterations")
        lbl.setObjectName("subheading")
        form.addRow(lbl)

        ramps = [
            ("sb_r0", "Ramp 0  (1st order stabilisation):", 50, 5000),
            ("sb_r1", "Ramp 1  (2nd order + Presto pressure):", 50, 5000),
            ("sb_r2", "Ramp 2  (Full 2nd order, no CC):", 50, 5000),
            ("sb_r3", "Ramp 3  (Full Send — CC on):", 50, 10000),
        ]
        for attr, label, lo, hi in ramps:
            sb = QSpinBox()
            sb.setRange(lo, hi)
            sb.setSingleStep(50)
            setattr(self, attr, sb)
            form.addRow(label, sb)

        form.addRow(self._hsep())

        turb = QLabel("Turbulence Options")
        turb.setObjectName("subheading")
        form.addRow(turb)

        self.chk_cc = QCheckBox(
            "Enable Curvature Correction on Ramp 3  (Full Send)"
        )
        self.chk_pl = QCheckBox("Enable Production Limiter  (recommended ON)")
        form.addRow("", self.chk_cc)
        form.addRow("", self.chk_pl)

        note = QLabel(
            "Curvature correction is always OFF for Ramps 0–2 regardless of "
            "this setting. When enabled here it is applied during Ramp 3 only."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)

        w.layout().addLayout(form)
        w.layout().addStretch()

    # ── Wheel MRF tab ─────────────────────────────────────────────────────────

    def _build_wheel_tab(self):
        w = self._scroll_tab("  Wheel MRF  ")
        v = w.layout()
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)

        top = QHBoxLayout()
        self.chk_mrf = QCheckBox(
            "Enable Wheel Moving Reference Frame (MRF)"
        )
        top.addWidget(self.chk_mrf)
        top.addStretch()
        v.addLayout(top)

        note = QLabel(
            "Each wheel needs a cylindrical MRF cell zone created in Ansys Discovery. "
            "See the Wheel MRF Setup Guide PDF for step-by-step instructions.\n"
            "RPM = 0 → auto-calculated from vehicle speed and wheel radius."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        v.addWidget(note)

        # Table
        cols = ["Name", "Zone Name", "Cx [m]", "Cy [m]", "Cz [m]",
                "Ax", "Ay", "Az", "Radius [m]", "RPM"]
        self.wheel_table = QTableWidget(0, len(cols))
        self.wheel_table.setHorizontalHeaderLabels(cols)
        self.wheel_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.wheel_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.wheel_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.wheel_table.setAlternatingRowColors(True)
        self.wheel_table.verticalHeader().setVisible(False)
        self.wheel_table.setMinimumHeight(160)
        v.addWidget(self.wheel_table)

        # Buttons
        btn_row = QHBoxLayout()
        for label, slot in [
            ("＋  Add Wheel",    self._add_wheel),
            ("✎  Edit",         self._edit_wheel),
            ("✕  Remove",       self._remove_wheel),
        ]:
            btn = QPushButton(label)
            if "Add" in label:
                btn.setObjectName("accent")
            elif "Remove" in label:
                btn.setObjectName("danger")
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        reset_btn = QPushButton("↺  Reset Defaults")
        reset_btn.clicked.connect(self._reset_wheels)
        btn_row.addWidget(reset_btn)
        v.addLayout(btn_row)

        v.addStretch()
        self._refresh_wheel_table()

    # ── Wheel table helpers ───────────────────────────────────────────────────

    def _refresh_wheel_table(self):
        if not hasattr(self, "wheel_table"):
            return
        t = self.wheel_table
        t.setRowCount(0)
        for w in self.config.wheel_mrf_zones:
            r = t.rowCount()
            t.insertRow(r)
            vals = [
                w.name, w.zone_name,
                f"{w.center_x:.3f}", f"{w.center_y:.3f}", f"{w.center_z:.3f}",
                f"{w.axis_x:.0f}", f"{w.axis_y:.0f}", f"{w.axis_z:.0f}",
                f"{w.wheel_radius:.4f}",
                "auto" if w.rpm == 0 else f"{w.rpm:.0f}",
            ]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                t.setItem(r, c, item)

    def _selected_wheel_idx(self):
        rows = self.wheel_table.selectedItems()
        if not rows:
            return None
        return self.wheel_table.currentRow()

    def _add_wheel(self):
        from gui.wheel_editor import WheelMRFEditorDialog
        dlg = WheelMRFEditorDialog(self, WheelMRFConfig(name="NEW", zone_name="mrf_new"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.config.wheel_mrf_zones.append(dlg.wheel)
            self._refresh_wheel_table()

    def _edit_wheel(self):
        idx = self._selected_wheel_idx()
        if idx is None:
            return
        from gui.wheel_editor import WheelMRFEditorDialog
        dlg = WheelMRFEditorDialog(self, self.config.wheel_mrf_zones[idx])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.config.wheel_mrf_zones[idx] = dlg.wheel
            self._refresh_wheel_table()

    def _remove_wheel(self):
        idx = self._selected_wheel_idx()
        if idx is None:
            return
        del self.config.wheel_mrf_zones[idx]
        self._refresh_wheel_table()

    def _reset_wheels(self):
        default = SIM_TYPE_REGISTRY[self.config.sim_type]()
        self.config.wheel_mrf_zones = default.wheel_mrf_zones
        self._refresh_wheel_table()

    # ── Load / write config ───────────────────────────────────────────────────

    def _load_from_config(self):
        c = self.config
        self.e_name.setText(c.name)
        self.sb_speed.setValue(c.vehicle_speed_mph)
        self.e_geom.setText(c.geometry_path)
        self.e_output.setText(c.output_dir)
        self.e_results.setText(c.results_dir)
        self.sb_procs.setValue(c.num_processes)
        self.sb_timeout.setValue(c.launch_timeout)
        self.cb_mpi.setCurrentText(c.mpi_type)
        self.chk_double.setChecked(c.double_precision)
        self.sb_cl.setValue(c.car_length_m)
        self.sb_cw.setValue(c.car_width_m)
        self.sb_ch.setValue(c.car_height_m)
        self.sb_wheelbase.setValue(c.wheelbase_in)

        self.sb_surf_min.setValue(c.surface_mesh_min)
        self.sb_surf_max.setValue(c.surface_mesh_max)
        self.sb_vol_min.setValue(c.volume_mesh_min)
        self.sb_vol_max.setValue(c.volume_mesh_max)
        self.sb_bl_layers.setValue(c.bl_num_layers)
        self.sb_bl_first.setValue(c.bl_first_height)
        self.sb_bl_trans.setValue(c.bl_transition_ratio)

        self.sb_r0.setValue(c.ramp0_iters)
        self.sb_r1.setValue(c.ramp1_iters)
        self.sb_r2.setValue(c.ramp2_iters)
        self.sb_r3.setValue(c.ramp3_iters)
        self.chk_cc.setChecked(c.use_curvature_correction)
        self.chk_pl.setChecked(c.use_production_limiter)

        if hasattr(self, "chk_mrf"):
            self.chk_mrf.setChecked(c.use_wheel_mrf)

        # Turning tab
        if hasattr(self, "sb_turn_radius"):
            self.sb_turn_radius.setValue(c.turn_radius_m)
            self.sb_track_width.setValue(c.track_width_m)
            self.chk_auto_yaw.setChecked(c.auto_yaw)
            self.sb_yaw.setValue(c.yaw_angle_deg)
            self._update_yaw_preview()


    def _write_to_config(self):
        c = self.config
        c.name              = self.e_name.text().strip()
        c.vehicle_speed_mph = self.sb_speed.value()
        c.geometry_path     = self.e_geom.text().strip()
        c.output_dir        = self.e_output.text().strip()
        c.results_dir       = self.e_results.text().strip()
        c.num_processes     = self.sb_procs.value()
        c.launch_timeout    = self.sb_timeout.value()
        c.mpi_type          = self.cb_mpi.currentText()
        c.double_precision  = self.chk_double.isChecked()
        c.car_length_m      = self.sb_cl.value()
        c.car_width_m       = self.sb_cw.value()
        c.car_height_m      = self.sb_ch.value()
        c.wheelbase_in      = self.sb_wheelbase.value()

        c.surface_mesh_min  = self.sb_surf_min.value()
        c.surface_mesh_max  = self.sb_surf_max.value()
        c.volume_mesh_min   = self.sb_vol_min.value()
        c.volume_mesh_max   = self.sb_vol_max.value()
        c.bl_num_layers     = self.sb_bl_layers.value()
        c.bl_first_height   = self.sb_bl_first.value()
        c.bl_transition_ratio = self.sb_bl_trans.value()

        c.ramp0_iters              = self.sb_r0.value()
        c.ramp1_iters              = self.sb_r1.value()
        c.ramp2_iters              = self.sb_r2.value()
        c.ramp3_iters              = self.sb_r3.value()
        c.use_curvature_correction = self.chk_cc.isChecked()
        c.use_production_limiter   = self.chk_pl.isChecked()

        if hasattr(self, "chk_mrf"):
            c.use_wheel_mrf = self.chk_mrf.isChecked()

        # Turning tab
        if hasattr(self, "sb_turn_radius"):
            c.turn_radius_m  = self.sb_turn_radius.value()
            c.track_width_m  = self.sb_track_width.value()
            c.auto_yaw       = self.chk_auto_yaw.isChecked()
            c.yaw_angle_deg  = self.sb_yaw.value()


    def _accept(self):
        try:
            self._write_to_config()
        except Exception as e:
            QMessageBox.critical(self, "Input Error", str(e))
            return
        errors = self.config.validate()
        if errors:
            QMessageBox.warning(self, "Validation Error", "\n".join(errors))
            return
        self.accepted_ok = True
        self.accept()

    # ── Turning tab ───────────────────────────────────────────────────────────

    def _build_turning_tab(self):
        w = self._scroll_tab("  Cornering  ")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(9)
        form.setContentsMargins(20, 16, 20, 16)

        # Section heading
        head = QLabel("Cornering Parameters")
        head.setObjectName("subheading")
        form.addRow(head)

        # Turn radius
        self.sb_turn_radius = QDoubleSpinBox()
        self.sb_turn_radius.setRange(0.5, 500.0)
        self.sb_turn_radius.setDecimals(2)
        self.sb_turn_radius.setSingleStep(0.5)
        self.sb_turn_radius.setSuffix(" m")
        self.sb_turn_radius.setToolTip(
            "Radius from the car centreline to the turn centre.\n"
            "Typical autocross: 6–12 m.  Skidpad: 7.625 m (SAE)."
        )
        form.addRow("Turn Radius:", self.sb_turn_radius)

        # Track width
        self.sb_track_width = QDoubleSpinBox()
        self.sb_track_width.setRange(0.1, 5.0)
        self.sb_track_width.setDecimals(3)
        self.sb_track_width.setSingleStep(0.05)
        self.sb_track_width.setSuffix(" m")
        self.sb_track_width.setToolTip(
            "Lateral distance from car centreline to wheel centre.\n"
            "Used to compute inner/outer wheel speed asymmetry."
        )
        form.addRow("Track Width (½ car):", self.sb_track_width)

        form.addRow(self._hsep())

        # Yaw angle — auto or manual
        yaw_head = QLabel("Inlet Yaw Angle")
        yaw_head.setObjectName("subheading")
        form.addRow(yaw_head)

        self.chk_auto_yaw = QCheckBox("Auto  (derived from speed ÷ radius)")
        self.chk_auto_yaw.setToolTip(
            "When enabled, yaw = atan(v / R).  Uncheck to set manually."
        )
        form.addRow("", self.chk_auto_yaw)

        self.sb_yaw = QDoubleSpinBox()
        self.sb_yaw.setRange(-89.0, 89.0)
        self.sb_yaw.setDecimals(2)
        self.sb_yaw.setSingleStep(0.5)
        self.sb_yaw.setSuffix(" °")
        self.sb_yaw.setToolTip(
            "Manual yaw angle applied to the inlet velocity vector.\n"
            "Positive = nose-right / left-hand turn.\n"
            "Only used when Auto is unchecked."
        )
        form.addRow("Manual Yaw Angle:", self.sb_yaw)

        # Preview label — shows the resolved yaw angle live
        self._yaw_preview = QLabel("—")
        self._yaw_preview.setObjectName("muted")
        form.addRow("Resolved Yaw:", self._yaw_preview)

        # Wire auto-yaw toggle and preview updates
        self.chk_auto_yaw.toggled.connect(self._update_yaw_preview)
        self.sb_turn_radius.valueChanged.connect(self._update_yaw_preview)
        self.sb_speed.valueChanged.connect(self._update_yaw_preview)   # General tab
        self.sb_yaw.valueChanged.connect(self._update_yaw_preview)

        form.addRow(self._hsep())

        # Wheel speed note
        info_head = QLabel("Wheel Speed Asymmetry")
        info_head.setObjectName("subheading")
        form.addRow(info_head)

        note = QLabel(
            "Outer wheels travel a longer path than inner wheels.\n"
            "RPMs are calculated automatically at solve time:\n\n"
            "  v_outer = v_car × (R + track) / R\n"
            "  v_inner = v_car × (R − track) / R\n"
            "  ω = v / r_wheel\n\n"
            "Left-side wheels (axis_z = +1) are outer wheels for a\n"
            "positive yaw (left-hand turn).  Individual RPM overrides\n"
            "in the Wheel MRF tab will take precedence."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)

        form.addRow(self._hsep())

        # Outputs note
        out_head = QLabel("Additional Outputs")
        out_head.setObjectName("subheading")
        form.addRow(out_head)

        out_note = QLabel(
            "Yaw Moment (lbf·ft) — about car centroid, Y axis.\n"
            "Lateral Force (lbf) — total side force, Z axis.\n\n"
            "+ve yaw moment = oversteer tendency.\n"
            "−ve yaw moment = understeer tendency."
        )
        out_note.setObjectName("muted")
        out_note.setWordWrap(True)
        form.addRow(out_note)

        w.layout().addLayout(form)
        w.layout().addStretch()

    def _update_yaw_preview(self):
        """Recompute and display the resolved yaw angle in the Cornering tab."""
        if not hasattr(self, "chk_auto_yaw"):
            return
        if self.chk_auto_yaw.isChecked():
            import math
            speed_ms = self.sb_speed.value() * 0.44704
            R = self.sb_turn_radius.value()
            if R > 0:
                yaw = math.degrees(math.atan2(speed_ms, R))
                self._yaw_preview.setText(f"{yaw:.2f}°  (auto)")
            else:
                self._yaw_preview.setText("—  (invalid radius)")
            self.sb_yaw.setEnabled(False)
        else:
            self._yaw_preview.setText(f"{self.sb_yaw.value():.2f}°  (manual)")
            self.sb_yaw.setEnabled(True)

    # ── Utility widget builders ───────────────────────────────────────────────

    def _scroll_tab(self, title: str) -> QWidget:
        """Create a tab page with a VBoxLayout and add to notebook."""
        from PyQt6.QtWidgets import QScrollArea
        page = QWidget()
        page.setLayout(QVBoxLayout())
        page.layout().setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)

        self.tabs.addTab(scroll, title)
        return page

    def _browse_row(self, edit: QLineEdit, btn: QPushButton) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(edit)
        h.addWidget(btn)
        return row

    def _hsep(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: #3e4451;")
        return line

    def _mspin(self, min_v=0.0001, max_v=0.1, step=0.001, decimals=4):
        sb = QDoubleSpinBox()
        sb.setRange(min_v, max_v)
        sb.setDecimals(decimals)
        sb.setSingleStep(step)
        sb.setSuffix(" m")
        return sb
