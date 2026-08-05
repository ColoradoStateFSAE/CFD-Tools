"""
Application settings.

Preferences that apply to the whole application rather than to one
simulation. Per-simulation values live in the simulation editor.
"""
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox, QLabel, QSpinBox,
    QCheckBox, QComboBox, QDialogButtonBox, QLineEdit, QHBoxLayout,
    QPushButton, QFileDialog, QWidget,
)
from PyQt6.QtCore import Qt, QSettings

import simtypes


class SettingsDialog(QDialog):
    """Defaults applied to new simulations, plus environment information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)

        self.store = QSettings("Ram Racing FSAE", "CFD Automation")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        heading = QLabel("Settings")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        # ── Defaults for new simulations ─────────────────────────────────
        defaults = QGroupBox("Defaults for New Simulations")
        form = QFormLayout(defaults)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sb_processes = QSpinBox()
        self.sb_processes.setRange(1, 512)
        form.addRow("Processes:", self.sb_processes)

        hint = QLabel("ThreadRipper 40–50 · Xeon Gold 60–70 · "
                      "Big Boi 128–170")
        hint.setObjectName("muted")
        form.addRow("", hint)

        self.combo_mpi = QComboBox()
        self.combo_mpi.addItems(["intel", "openmpi", "msmpi", "default"])
        form.addRow("MPI type:", self.combo_mpi)

        mpi_hint = QLabel("intel for Xeon Gold · openmpi for ThreadRipper")
        mpi_hint.setObjectName("muted")
        form.addRow("", mpi_hint)

        self.cb_double = QCheckBox("Double precision")
        form.addRow("", self.cb_double)

        self.cb_ensight = QCheckBox("Export EnSight Gold for ParaView")
        form.addRow("", self.cb_ensight)

        self.e_output = QLineEdit()
        self.e_output.setPlaceholderText(
            "Where the Project / Run / MAP folders are created")
        output_row = QWidget()
        browse_row = QHBoxLayout(output_row)
        browse_row.setContentsMargins(0, 0, 0, 0)
        browse_row.setSpacing(6)
        browse_row.addWidget(self.e_output, 1)
        browse = QPushButton("Browse…")
        browse.setFixedWidth(84)
        browse.clicked.connect(self._pick_output)
        browse_row.addWidget(browse)
        form.addRow("Output root:", output_row)

        root_note = QLabel(
            "Every simulation writes to "
            "&lt;root&gt;/&lt;project&gt;/&lt;run&gt;/&lt;point id&gt;, "
            "for example  Dauntless/R018/R018-MAP01.  Point ID matches the "
            "CFD Rolling Report, so a folder and its Master Log row share a "
            "name. Put this on the shared drive to keep the team's runs "
            "together.")
        root_note.setObjectName("muted")
        root_note.setWordWrap(True)
        form.addRow("", root_note)

        layout.addWidget(defaults)

        # ── Interface ────────────────────────────────────────────────────
        interface = QGroupBox("Interface")
        interface_form = QFormLayout(interface)
        interface_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.combo_log = QComboBox()
        self.combo_log.addItems(["INFO", "DEBUG", "WARNING"])
        interface_form.addRow("Log level:", self.combo_log)

        detail = QLabel("DEBUG shows every Fluent call, which is useful when "
                        "a simulation fails but very noisy otherwise.")
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        interface_form.addRow("", detail)

        layout.addWidget(interface)

        # ── Environment ──────────────────────────────────────────────────
        environment = QGroupBox("Environment")
        env_form = QFormLayout(environment)
        env_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        ansys = os.environ.get("AWP_ROOT261", "")
        ansys_label = QLabel(ansys or "not found")
        ansys_label.setWordWrap(True)
        ansys_label.setStyleSheet(
            "color: #98c379;" if ansys else "color: #e06c75;")
        env_form.addRow("Ansys 2026 R1:", ansys_label)

        if not ansys:
            fix = QLabel('setx AWP_ROOT261 "C:\\Program Files\\'
                         'ANSYS Inc\\v261" /M')
            fix.setObjectName("muted")
            fix.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            env_form.addRow("", fix)

        types = QLabel(", ".join(name for _, name in simtypes.names()))
        types.setWordWrap(True)
        env_form.addRow("Simulation types:", types)

        layout.addWidget(environment)

        # ── Buttons ──────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        buttons.button(
            QDialogButtonBox.StandardButton.RestoreDefaults
        ).clicked.connect(self._restore)
        layout.addWidget(buttons)

        self._load()

    # ── Persistence ──────────────────────────────────────────────────────

    def _pick_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Output Root Folder", self.e_output.text())
        if path:
            self.e_output.setText(path)

    def _load(self) -> None:
        self.sb_processes.setValue(
            int(self.store.value("processes", 40)))
        self.cb_double.setChecked(
            self.store.value("double_precision", True, type=bool))
        self.combo_mpi.setCurrentText(self.store.value("mpi_type", "intel"))
        self.cb_ensight.setChecked(
            self.store.value("export_ensight", True, type=bool))
        self.e_output.setText(self.store.value("output_root", ""))
        self.combo_log.setCurrentText(self.store.value("log_level", "INFO"))

    def _save(self) -> None:
        self.store.setValue("processes", self.sb_processes.value())
        self.store.setValue("double_precision", self.cb_double.isChecked())
        self.store.setValue("mpi_type", self.combo_mpi.currentText())
        self.store.setValue("export_ensight", self.cb_ensight.isChecked())
        self.store.setValue("output_root", self.e_output.text().strip())
        self.store.setValue("log_level", self.combo_log.currentText())

        import logging
        logging.getLogger().setLevel(
            getattr(logging, self.combo_log.currentText(), logging.INFO))

        self.accept()

    def _restore(self) -> None:
        self.sb_processes.setValue(40)
        self.cb_double.setChecked(True)
        self.combo_mpi.setCurrentText("intel")
        self.cb_ensight.setChecked(True)
        self.e_output.clear()
        self.combo_log.setCurrentText("INFO")


def apply_defaults(settings) -> None:
    """
    Apply the saved defaults to a fresh Settings instance.
    Called when a new simulation is created.
    """
    store = QSettings("Ram Racing FSAE", "CFD Automation")
    settings.processes = int(store.value("processes", settings.processes))
    settings.double_precision = store.value(
        "double_precision", settings.double_precision, type=bool)
    if hasattr(settings, "mpi_type"):
        settings.mpi_type = store.value("mpi_type", settings.mpi_type)
    settings.export_ensight = store.value(
        "export_ensight", settings.export_ensight, type=bool)
    root = store.value("output_root", "")
    if root and hasattr(settings, "output_root"):
        settings.output_root = root
