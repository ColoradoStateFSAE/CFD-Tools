"""
Car Settings dialog — global defaults used when creating new simulations.

Settings are stored in memory only (applied to the next new sim via the
registry defaults). Users can override per-simulation in the editor.
"""
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QDoubleSpinBox, QSpinBox, QFrame, QWidget
)
from PyQt6.QtCore import Qt

# Module-level defaults — mutated when the user saves settings.
_defaults = {
    "wheelbase_in":    62.0,
    "car_length_m":     2.8,
    "car_width_m":      1.4,
    "car_height_m":     1.2,
    "num_processes":   70,
    "launch_timeout":  300,
    "vehicle_speed_mph": 40.0,
}


def get_defaults() -> dict:
    """Return a copy of the current global defaults."""
    return dict(_defaults)


class CarSettingsDialog(QDialog):
    """
    Global car / HPC defaults dialog (File → Car Settings).
    Changes update the module-level _defaults dict, which is read when
    new simulation configs are instantiated via apply_defaults_to_config().
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Car Settings — Global Defaults")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build()
        self._load()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 16, 20, 16)

        note = QLabel(
            "These values are applied as defaults when you create a new simulation. "
            "They can be overridden per-simulation in the editor."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

        # ── Car geometry ────────────────────────────────────────────────
        car_group = QGroupBox("Car Geometry")
        car_form = QFormLayout(car_group)
        car_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        car_form.setSpacing(8)

        self.sb_wheelbase = self._dspin(10.0, 300.0, 2, suffix=" in",
                                        tooltip="Front-to-rear axle distance [inches]")
        car_form.addRow("Wheelbase L:", self.sb_wheelbase)

        self.sb_length = self._dspin(0.1, 10.0, 3, suffix=" m",
                                     tooltip="Car length along X axis [metres]")
        car_form.addRow("Car Length (X):", self.sb_length)

        self.sb_width = self._dspin(0.1, 10.0, 3, suffix=" m",
                                    tooltip="Car width along Z axis [metres]")
        car_form.addRow("Car Width (Z):", self.sb_width)

        self.sb_height = self._dspin(0.1, 10.0, 3, suffix=" m",
                                     tooltip="Car height along Y axis [metres]")
        car_form.addRow("Car Height (Y):", self.sb_height)

        self.sb_speed = self._dspin(1.0, 300.0, 1, suffix=" mph",
                                    tooltip="Default vehicle speed for new simulations")
        car_form.addRow("Vehicle Speed:", self.sb_speed)

        root.addWidget(car_group)

        # ── HPC / solver ────────────────────────────────────────────────
        hpc_group = QGroupBox("HPC / Solver Defaults")
        hpc_form = QFormLayout(hpc_group)
        hpc_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        hpc_form.setSpacing(8)

        self.sb_procs = QSpinBox()
        self.sb_procs.setRange(1, 512)
        self.sb_procs.setToolTip(
            "ThreadRipper: 40–50  |  Xeon Gold: 60  |  Big Boi: 128–170"
        )
        hpc_form.addRow("Processes:", self.sb_procs)

        self.sb_timeout = QSpinBox()
        self.sb_timeout.setRange(60, 1800)
        self.sb_timeout.setSingleStep(30)
        self.sb_timeout.setSuffix(" s")
        self.sb_timeout.setToolTip(
            "Fluent launch timeout. Increase to 300–600 s on slow HPC machines."
        )
        hpc_form.addRow("Launch Timeout:", self.sb_timeout)

        root.addWidget(hpc_group)

        # ── Journals ────────────────────────────────────────────────────
        journal_group = QGroupBox("Fluent Journals")
        journal_form = QFormLayout(journal_group)

        self.lbl_journals_dir = QLabel("—")
        self.lbl_journals_dir.setWordWrap(True)
        self.lbl_journals_dir.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        journal_form.addRow("Location:", self.lbl_journals_dir)

        self.lbl_journals_status = QLabel("—")
        self.lbl_journals_status.setWordWrap(True)
        journal_form.addRow("Recorded:", self.lbl_journals_status)

        journal_note = QLabel(
            "Read-only. Override the location with the RAMRACING_JOURNALS "
            "environment variable, or per simulation on the Journals tab of "
            "the editor."
        )
        journal_note.setObjectName("muted")
        journal_note.setWordWrap(True)
        journal_form.addRow(journal_note)

        self._refresh_journal_info()
        root.addWidget(journal_group)

        # ── Buttons ─────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setObjectName("accent")
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._restore_defaults
        )
        root.addWidget(btns)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _refresh_journal_info(self):
        """Report where journals were found and which are recorded."""
        import os
        try:
            from utils.resource_path import journals_dir
            from core.journal_params import all_sim_type_keys
        except Exception as exc:
            self.lbl_journals_dir.setText(f"unavailable ({exc})")
            return

        root = journals_dir()
        self.lbl_journals_dir.setText(root)

        if not os.path.isdir(root):
            self.lbl_journals_status.setText("directory not found")
            self.lbl_journals_status.setStyleSheet("color: #e06c75;")
            return

        ready, partial = [], []
        for key in all_sim_type_keys():
            folder = os.path.join(root, key)
            has_mesh  = os.path.isfile(os.path.join(folder, "mesh.py"))
            has_solve = os.path.isfile(os.path.join(folder, "solve.py"))
            if has_mesh and has_solve:
                ready.append(key)
            elif has_mesh or has_solve:
                partial.append(key)

        parts = []
        if ready:
            parts.append(f"{len(ready)} complete: {', '.join(ready)}")
        if partial:
            parts.append(f"{len(partial)} partial: {', '.join(partial)}")
        if not parts:
            parts.append("none recorded yet")

        self.lbl_journals_status.setText("  |  ".join(parts))
        self.lbl_journals_status.setStyleSheet(
            "color: #98c379;" if ready else "color: #e5c07b;"
        )

    def _dspin(self, lo, hi, decimals, suffix="", tooltip=""):
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(decimals)
        sb.setSingleStep(0.1)
        if suffix:
            sb.setSuffix(suffix)
        if tooltip:
            sb.setToolTip(tooltip)
        sb.setMinimumWidth(120)
        return sb

    # ── Load / save ───────────────────────────────────────────────────────

    def _load(self):
        d = _defaults
        self.sb_wheelbase.setValue(d["wheelbase_in"])
        self.sb_length.setValue(d["car_length_m"])
        self.sb_width.setValue(d["car_width_m"])
        self.sb_height.setValue(d["car_height_m"])
        self.sb_speed.setValue(d["vehicle_speed_mph"])
        self.sb_procs.setValue(d["num_processes"])
        self.sb_timeout.setValue(d["launch_timeout"])

    def _accept(self):
        _defaults["wheelbase_in"]      = self.sb_wheelbase.value()
        _defaults["car_length_m"]      = self.sb_length.value()
        _defaults["car_width_m"]       = self.sb_width.value()
        _defaults["car_height_m"]      = self.sb_height.value()
        _defaults["vehicle_speed_mph"] = self.sb_speed.value()
        _defaults["num_processes"]     = self.sb_procs.value()
        _defaults["launch_timeout"]    = self.sb_timeout.value()
        self.accept()

    def _restore_defaults(self):
        _defaults.update({
            "wheelbase_in":      62.0,
            "car_length_m":       2.8,
            "car_width_m":        1.4,
            "car_height_m":       1.2,
            "num_processes":     70,
            "launch_timeout":    300,
            "vehicle_speed_mph": 40.0,
        })
        self._load()


def apply_defaults_to_config(config) -> None:
    """
    Apply global defaults to a freshly constructed sim config.
    Call this after instantiating any config class from SIM_TYPE_REGISTRY
    so the user's saved preferences are reflected in new simulations.
    """
    d = _defaults
    config.wheelbase_in      = d["wheelbase_in"]
    config.car_length_m      = d["car_length_m"]
    config.car_width_m       = d["car_width_m"]
    config.car_height_m      = d["car_height_m"]
    config.vehicle_speed_mph = d["vehicle_speed_mph"]
    config.num_processes     = d["num_processes"]
    config.launch_timeout    = d["launch_timeout"]