"""
Wheel MRF zone editor dialog — PyQt6.
"""
import copy
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QDoubleSpinBox, QGroupBox, QWidget, QFrame,
    QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from simtypes.configs import WheelMRFConfig


class WheelMRFEditorDialog(QDialog):
    def __init__(self, parent, wheel: WheelMRFConfig):
        super().__init__(parent)
        self.wheel = copy.deepcopy(wheel)
        self.setWindowTitle("Edit Wheel MRF Zone")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build()
        self._load()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 16, 20, 16)

        # Header
        hdr = QLabel("Wheel MRF Zone Settings")
        hdr.setObjectName("subheading")
        root.addWidget(hdr)

        # Identity group
        id_group = QGroupBox("Zone Identity")
        id_form = QFormLayout(id_group)
        id_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        id_form.setSpacing(8)

        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText("e.g. FRW")
        self.e_name.setToolTip("Short label used in reports (FLW, FRW, RLW, RRW)")
        id_form.addRow("Wheel Name:", self.e_name)

        self.e_zone = QLineEdit()
        self.e_zone.setPlaceholderText("e.g. mrf_frw")
        self.e_zone.setToolTip(
            "Must exactly match the named selection in Ansys Discovery"
        )
        id_form.addRow("Fluent Zone Name:", self.e_zone)
        root.addWidget(id_group)

        # Center group
        ctr_group = QGroupBox("Rotation Center [m]")
        ctr_form = QFormLayout(ctr_group)
        ctr_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        ctr_form.setSpacing(8)

        self.sb_cx = self._dspin(-99, 99, 4)
        self.sb_cy = self._dspin(-99, 99, 4)
        self.sb_cz = self._dspin(-99, 99, 4)
        ctr_form.addRow("Center X [m]:", self.sb_cx)
        ctr_form.addRow("Center Y [m]:", self.sb_cy)
        ctr_form.addRow(
            "Center Z [m]:",
            self._with_note(self.sb_cz, "Lateral offset from car centreline"),
        )
        root.addWidget(ctr_group)

        # Axis group
        ax_group = QGroupBox("Rotation Axis Direction")
        ax_form = QFormLayout(ax_group)
        ax_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        ax_form.setSpacing(8)

        self.sb_ax = self._dspin(-1, 1, 0)
        self.sb_ay = self._dspin(-1, 1, 0)
        self.sb_az = self._dspin(-1, 1, 0)
        ax_form.addRow("Axis X:", self.sb_ax)
        ax_form.addRow("Axis Y:", self.sb_ay)
        ax_form.addRow(
            "Axis Z:",
            self._with_note(self.sb_az, "+1 left side wheels  |  -1 right side wheels"),
        )
        root.addWidget(ax_group)

        # Properties group
        prop_group = QGroupBox("Wheel Properties")
        prop_form = QFormLayout(prop_group)
        prop_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        prop_form.setSpacing(8)

        self.sb_radius = self._dspin(0.01, 1.0, 4, step=0.001)
        prop_form.addRow(
            "Wheel Radius [m]:",
            self._with_note(self.sb_radius, "Outer tyre radius  (8 inch ≈ 0.2032 m)"),
        )

        self.sb_rpm = self._dspin(0, 99999, 1, step=10.0)
        prop_form.addRow(
            "RPM Override:",
            self._with_note(self.sb_rpm, "Set 0 to auto-calculate from speed ÷ radius"),
        )
        root.addWidget(prop_group)

        # RPM formula note
        note = QLabel(
            "Auto RPM  =  ( v_car [m/s] / r_wheel [m] ) / (2π) × 60"
        )
        note.setObjectName("muted")
        root.addWidget(note)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Accept")
        btns.button(QDialogButtonBox.StandardButton.Ok).setObjectName("accent")
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dspin(self, lo, hi, decimals, step=0.1):
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(decimals)
        sb.setSingleStep(step)
        sb.setMinimumWidth(120)
        return sb

    def _with_note(self, widget, note_text):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(widget)
        note = QLabel(note_text)
        note.setObjectName("muted")
        h.addWidget(note)
        h.addStretch()
        return row

    # ── Load / accept ─────────────────────────────────────────────────────────

    def _load(self):
        w = self.wheel
        self.e_name.setText(w.name)
        self.e_zone.setText(w.zone_name)
        self.sb_cx.setValue(w.center_x)
        self.sb_cy.setValue(w.center_y)
        self.sb_cz.setValue(w.center_z)
        self.sb_ax.setValue(w.axis_x)
        self.sb_ay.setValue(w.axis_y)
        self.sb_az.setValue(w.axis_z)
        self.sb_radius.setValue(w.wheel_radius)
        self.sb_rpm.setValue(w.rpm)

    def _accept(self):
        name = self.e_name.text().strip()
        zone = self.e_zone.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Wheel name cannot be empty.")
            return
        if not zone:
            QMessageBox.warning(self, "Validation", "Zone name cannot be empty.")
            return
        if self.sb_radius.value() <= 0:
            QMessageBox.warning(self, "Validation", "Wheel radius must be > 0.")
            return

        w = self.wheel
        w.name         = name
        w.zone_name    = zone
        w.center_x     = self.sb_cx.value()
        w.center_y     = self.sb_cy.value()
        w.center_z     = self.sb_cz.value()
        w.axis_x       = self.sb_ax.value()
        w.axis_y       = self.sb_ay.value()
        w.axis_z       = self.sb_az.value()
        w.wheel_radius = self.sb_radius.value()
        w.rpm          = self.sb_rpm.value()
        self.accept()
