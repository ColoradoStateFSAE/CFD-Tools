"""
Carbon Fiber Part Weight Calculator (PyQt6)
--------------------------------------------
Estimates part weight from surface area using measured carbon swatch data,
with support for sandwich panels (skin, core, skin) and a fallback path
for dry carbon fabric where no swatch exists yet (uses a standard infusion
fiber volume fraction to estimate cured laminate weight).

Adding a new swatch: add one line to SWATCH_DATA below.
Adding a new core material: add one line to CORE_MATERIALS below.
"""

import sys

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QComboBox, QCheckBox,
    QPushButton, QTextEdit, QGridLayout, QVBoxLayout, QFrame, QMessageBox,
)

# ---------------------------------------------------------------------------
# DATA: add new swatches or cores here, nothing else needs to change
# ---------------------------------------------------------------------------

# Measured/cured areal weight of each carbon layup, in grams per square meter
SWATCH_DATA = {
    "1L of 12k": 846.996,
    "1L of 12k and 1L of 3k": 1149.427,
    "2L of 12k": 1693.834,
    "2L of 3k": 605.836,
    "1L of 3k": 286.867,
}

# Core materials: density in kg/m^3, and a sensible default thickness in mm
CORE_MATERIALS = {
    "Airex T10.100 PET (2mm default)": {
        "density_kg_m3": 100.0,
        "default_thickness_mm": 2.0,
    },
    # Nomex aramid paper, ASTM D374/D646/D828-97 data sheet values.
    # Density (g/cc) converted to kg/m^3, typical thickness used as default mm.
    "Nomex Paper 2 mil (0.06mm)": {
        "density_kg_m3": 720.0,
        "default_thickness_mm": 0.06,
    },
    "Nomex Paper 3 mil (0.08mm)": {
        "density_kg_m3": 810.0,
        "default_thickness_mm": 0.08,
    },
    "Nomex Paper 4 mil (0.11mm)": {
        "density_kg_m3": 830.0,
        "default_thickness_mm": 0.11,
    },
    "Nomex Paper 5 mil (0.13mm)": {
        "density_kg_m3": 880.0,
        "default_thickness_mm": 0.13,
    },
    "Nomex Paper 7 mil (0.18mm)": {
        "density_kg_m3": 950.0,
        "default_thickness_mm": 0.18,
    },
    "Nomex Paper 10 mil (0.26mm)": {
        "density_kg_m3": 960.0,
        "default_thickness_mm": 0.26,
    },
    "Nomex Paper 12 mil (0.31mm)": {
        "density_kg_m3": 1000.0,
        "default_thickness_mm": 0.31,
    },
    "Nomex Paper 15 mil (0.39mm)": {
        "density_kg_m3": 1020.0,
        "default_thickness_mm": 0.39,
    },
    "Nomex Paper 20 mil (0.52mm)": {
        "density_kg_m3": 1060.0,
        "default_thickness_mm": 0.52,
    },
    "Nomex Paper 24 mil (0.61mm)": {
        "density_kg_m3": 1130.0,
        "default_thickness_mm": 0.61,
    },
    "Nomex Paper 30 mil (0.78mm)": {
        "density_kg_m3": 1080.0,
        "default_thickness_mm": 0.78,
    },
}

CUSTOM_DRY_LABEL = "Custom dry carbon (enter gsm)"

# ---------------------------------------------------------------------------
# INFUSION ASSUMPTIONS: used only when a dry gsm is entered instead of a
# measured swatch. Adjust these if your process changes.
# ---------------------------------------------------------------------------
DEFAULT_FIBER_VOLUME_FRACTION = 0.40   # typical for vacuum infusion
CARBON_FIBER_DENSITY_G_CM3 = 1.80      # standard 12k/3k carbon fiber
INFUSION_RESIN_DENSITY_G_CM3 = 1.15    # typical infusion epoxy

G_TO_LB = 1.0 / 453.59237


def estimate_infused_areal_weight(
    dry_gsm,
    vf=DEFAULT_FIBER_VOLUME_FRACTION,
    fiber_density=CARBON_FIBER_DENSITY_G_CM3,
    resin_density=INFUSION_RESIN_DENSITY_G_CM3,
):
    """
    Estimate the cured (infused) areal weight of a laminate from a dry
    fabric areal weight, using a standard vacuum infusion fiber volume
    fraction. Resin mass is derived directly as a ratio to fiber mass so
    no unit conversion errors are possible.
    """
    resin_to_fiber_mass_ratio = (1.0 / vf - 1.0) * (resin_density / fiber_density)
    resin_gsm = dry_gsm * resin_to_fiber_mass_ratio
    return dry_gsm + resin_gsm


def core_areal_weight_g_m2(density_kg_m3, thickness_mm):
    thickness_m = thickness_mm / 1000.0
    kg_per_m2 = density_kg_m3 * thickness_m
    return kg_per_m2 * 1000.0


def skin_choices():
    return list(SWATCH_DATA.keys()) + [CUSTOM_DRY_LABEL]


class CarbonWeightCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Carbon Part Weight Calculator")
        self._build_layout()
        self._refresh_sandwich_state()

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------
    def _build_layout(self):
        outer = QVBoxLayout(self)
        grid = QGridLayout()
        outer.addLayout(grid)

        row = 0
        grid.addWidget(QLabel("Surface area (m^2):"), row, 0)
        self.area_entry = QLineEdit()
        self.area_entry.setFixedWidth(140)
        grid.addWidget(self.area_entry, row, 1)
        row += 1

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(sep1, row, 0, 1, 2)
        row += 1

        self.sandwich_check = QCheckBox("Sandwich panel (skin, core, skin)")
        self.sandwich_check.stateChanged.connect(self._refresh_sandwich_state)
        grid.addWidget(self.sandwich_check, row, 0, 1, 2)
        row += 1

        # Skin 1
        self.skin1_label = QLabel("Skin 1 material:")
        self.skin1_combo = QComboBox()
        self.skin1_combo.addItems(skin_choices())
        self.skin1_combo.currentIndexChanged.connect(self._refresh_sandwich_state)
        grid.addWidget(self.skin1_label, row, 0)
        grid.addWidget(self.skin1_combo, row, 1)
        row += 1

        self.skin1_gsm_label = QLabel("Skin 1 dry gsm:")
        self.skin1_gsm_entry = QLineEdit()
        self.skin1_gsm_entry.setFixedWidth(140)
        grid.addWidget(self.skin1_gsm_label, row, 0)
        grid.addWidget(self.skin1_gsm_entry, row, 1)
        row += 1

        # Same skin checkbox
        self.same_skin_check = QCheckBox("Skin 2 same as skin 1")
        self.same_skin_check.setChecked(True)
        self.same_skin_check.stateChanged.connect(self._refresh_sandwich_state)
        grid.addWidget(self.same_skin_check, row, 0, 1, 2)
        row += 1

        # Skin 2
        self.skin2_label = QLabel("Skin 2 material:")
        self.skin2_combo = QComboBox()
        self.skin2_combo.addItems(skin_choices())
        self.skin2_combo.currentIndexChanged.connect(self._refresh_sandwich_state)
        grid.addWidget(self.skin2_label, row, 0)
        grid.addWidget(self.skin2_combo, row, 1)
        row += 1

        self.skin2_gsm_label = QLabel("Skin 2 dry gsm:")
        self.skin2_gsm_entry = QLineEdit()
        self.skin2_gsm_entry.setFixedWidth(140)
        grid.addWidget(self.skin2_gsm_label, row, 0)
        grid.addWidget(self.skin2_gsm_entry, row, 1)
        row += 1

        # Core
        self.core_label = QLabel("Core material:")
        self.core_combo = QComboBox()
        self.core_combo.addItems(list(CORE_MATERIALS.keys()))
        self.core_combo.currentIndexChanged.connect(self._load_core_default_thickness)
        grid.addWidget(self.core_label, row, 0)
        grid.addWidget(self.core_combo, row, 1)
        row += 1

        self.core_thickness_label = QLabel("Core thickness (mm):")
        self.core_thickness_entry = QLineEdit()
        self.core_thickness_entry.setFixedWidth(140)
        grid.addWidget(self.core_thickness_label, row, 0)
        grid.addWidget(self.core_thickness_entry, row, 1)
        row += 1
        self._load_core_default_thickness()

        self.resin_absorb_check = QCheckBox("Core absorbs resin during infusion")
        self.resin_absorb_check.stateChanged.connect(self._refresh_sandwich_state)
        grid.addWidget(self.resin_absorb_check, row, 0, 1, 2)
        row += 1

        self.resin_pickup_label = QLabel("Resin pickup (% of dry core weight):")
        self.resin_pickup_entry = QLineEdit()
        self.resin_pickup_entry.setFixedWidth(140)
        self.resin_pickup_entry.setText("0")
        grid.addWidget(self.resin_pickup_label, row, 0)
        grid.addWidget(self.resin_pickup_entry, row, 1)
        row += 1

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(sep2, row, 0, 1, 2)
        row += 1

        self.calc_button = QPushButton("Calculate")
        self.calc_button.clicked.connect(self._calculate)
        grid.addWidget(self.calc_button, row, 0)
        row += 1

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFixedSize(420, 230)
        grid.addWidget(self.result_text, row, 0, 1, 2)

        self._row_widgets = {
            "skin1_gsm": (self.skin1_gsm_label, self.skin1_gsm_entry),
            "same_skin": (self.same_skin_check, None),
            "skin2": (self.skin2_label, self.skin2_combo),
            "skin2_gsm": (self.skin2_gsm_label, self.skin2_gsm_entry),
            "core": (self.core_label, self.core_combo),
            "core_thickness": (self.core_thickness_label, self.core_thickness_entry),
            "resin_absorb": (self.resin_absorb_check, None),
            "resin_pickup": (self.resin_pickup_label, self.resin_pickup_entry),
        }

    def _load_core_default_thickness(self):
        core = CORE_MATERIALS[self.core_combo.currentText()]
        self.core_thickness_entry.setText(str(core["default_thickness_mm"]))

    def _set_visible(self, key, visible):
        widgets = self._row_widgets[key]
        for w in widgets:
            if w is not None:
                w.setVisible(visible)

    def _refresh_sandwich_state(self):
        sandwich_on = self.sandwich_check.isChecked()

        skin1_custom = self.skin1_combo.currentText() == CUSTOM_DRY_LABEL
        self._set_visible("skin1_gsm", skin1_custom)

        for key in ("same_skin", "core", "core_thickness", "resin_absorb"):
            self._set_visible(key, sandwich_on)

        if sandwich_on:
            same_skin = self.same_skin_check.isChecked()
            self._set_visible("skin2", not same_skin)
            skin2_custom = (not same_skin) and (self.skin2_combo.currentText() == CUSTOM_DRY_LABEL)
            self._set_visible("skin2_gsm", skin2_custom)
            self._set_visible("resin_pickup", self.resin_absorb_check.isChecked())
        else:
            self._set_visible("skin2", False)
            self._set_visible("skin2_gsm", False)
            self._set_visible("resin_pickup", False)

    # -----------------------------------------------------------------
    # Calculation
    # -----------------------------------------------------------------
    def _get_skin_gsm(self, choice, gsm_entry):
        if choice == CUSTOM_DRY_LABEL:
            try:
                dry_gsm = float(gsm_entry.text())
            except ValueError:
                raise ValueError("Enter a valid dry gsm value for the custom skin.")
            return estimate_infused_areal_weight(dry_gsm), True
        return SWATCH_DATA[choice], False

    def _calculate(self):
        try:
            area_m2 = float(self.area_entry.text())
        except ValueError:
            QMessageBox.critical(self, "Input error", "Enter a valid surface area in m^2.")
            return
        if area_m2 <= 0:
            QMessageBox.critical(self, "Input error", "Surface area must be greater than zero.")
            return

        try:
            skin1_gsm, skin1_estimated = self._get_skin_gsm(self.skin1_combo.currentText(), self.skin1_gsm_entry)
        except ValueError as e:
            QMessageBox.critical(self, "Input error", str(e))
            return

        lines = []
        lines.append(f"Surface area: {area_m2:.4f} m^2")
        lines.append(f"Skin 1 ({self.skin1_combo.currentText()}): {skin1_gsm:.2f} g/m^2" +
                     (" (estimated from dry gsm, standard infusion VFR)" if skin1_estimated else ""))

        total_gsm = skin1_gsm

        if self.sandwich_check.isChecked():
            if self.same_skin_check.isChecked():
                skin2_gsm, skin2_estimated = skin1_gsm, skin1_estimated
                skin2_name = self.skin1_combo.currentText()
            else:
                try:
                    skin2_gsm, skin2_estimated = self._get_skin_gsm(self.skin2_combo.currentText(), self.skin2_gsm_entry)
                except ValueError as e:
                    QMessageBox.critical(self, "Input error", str(e))
                    return
                skin2_name = self.skin2_combo.currentText()

            lines.append(f"Skin 2 ({skin2_name}): {skin2_gsm:.2f} g/m^2" +
                         (" (estimated from dry gsm, standard infusion VFR)" if skin2_estimated else ""))

            try:
                core_thickness_mm = float(self.core_thickness_entry.text())
            except ValueError:
                QMessageBox.critical(self, "Input error", "Enter a valid core thickness in mm.")
                return

            core = CORE_MATERIALS[self.core_combo.currentText()]
            core_dry_gsm = core_areal_weight_g_m2(core["density_kg_m3"], core_thickness_mm)
            lines.append(f"Core dry ({self.core_combo.currentText()}, {core_thickness_mm:.2f} mm): {core_dry_gsm:.2f} g/m^2")

            core_gsm = core_dry_gsm
            if self.resin_absorb_check.isChecked():
                try:
                    pickup_pct = float(self.resin_pickup_entry.text())
                except ValueError:
                    QMessageBox.critical(self, "Input error", "Enter a valid resin pickup percentage.")
                    return
                resin_pickup_gsm = core_dry_gsm * (pickup_pct / 100.0)
                core_gsm = core_dry_gsm + resin_pickup_gsm
                lines.append(f"Resin absorbed by core ({pickup_pct:.1f}%): {resin_pickup_gsm:.2f} g/m^2")
                lines.append(f"Core total (dry + absorbed resin): {core_gsm:.2f} g/m^2")

            total_gsm = skin1_gsm + skin2_gsm + core_gsm

        total_grams = total_gsm * area_m2
        total_lb = total_grams * G_TO_LB

        lines.append(f"Total areal weight: {total_gsm:.2f} g/m^2")
        lines.append("")
        lines.append(f"Estimated weight: {total_grams:.1f} g")
        lines.append(f"Estimated weight: {total_lb:.3f} lb")

        self.result_text.setPlainText("\n".join(lines))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CarbonWeightCalculator()
    window.show()
    sys.exit(app.exec())