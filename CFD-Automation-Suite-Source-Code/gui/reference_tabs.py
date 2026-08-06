"""
Reference tables.

Two read-only views built from the active simulation type's own dictionaries:

    NAMED_SELECTIONS    what to create in Ansys Discovery
    REPORT_DEFINITIONS  what the simulation will produce

Because they read the simulation type module directly, they cannot drift out
of step with what actually runs.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from gui.theme import ACCENT, OK, WARN, TEXT_MUTED, TEXT_BRIGHT, INFO

# Boundary type -> colour, so the role of each selection reads at a glance
TYPE_COLOURS = {
    "velocity-inlet":  INFO,
    "pressure-outlet": INFO,
    "symmetry":        INFO,
    "wall, moving":    WARN,
    "wall, rotating":  WARN,
    "wall, slip":      WARN,
    "wall":            OK,
}

KIND_COLOURS = {
    "lift":       OK,
    "drag":       WARN,
    "moment":     INFO,
    "expression": ACCENT,
}


class _FilterTable(QWidget):
    """A searchable, read-only three column table."""

    def __init__(self, title: str, blurb: str, headers: list, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)

        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)

        note = QLabel(blurb)
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(QLabel("Filter:"))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Type to narrow the list…")
        self.filter.textChanged.connect(self._apply_filter)
        row.addWidget(self.filter, 1)
        self.count = QLabel("")
        self.count.setObjectName("muted")
        row.addWidget(self.count)
        layout.addLayout(row)

        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

    def _fill(self, rows: list, colour_map: dict) -> None:
        """rows: [(key, kind, description), ...]"""
        self._rows = rows
        self.table.setRowCount(len(rows))
        for r, (key, kind, description) in enumerate(rows):
            name = QTableWidgetItem(key)
            name.setForeground(QColor(TEXT_BRIGHT))
            font = name.font()
            font.setBold(True)
            name.setFont(font)
            self.table.setItem(r, 0, name)

            kind_item = QTableWidgetItem(kind)
            kind_item.setForeground(QColor(colour_map.get(kind, TEXT_MUTED)))
            self.table.setItem(r, 1, kind_item)

            self.table.setItem(r, 2, QTableWidgetItem(description))

        self.count.setText(f"{len(rows)} entries")
        self._apply_filter(self.filter.text())

    def _apply_filter(self, text: str) -> None:
        text = text.strip().lower()
        shown = 0
        for r in range(self.table.rowCount()):
            haystack = " ".join(
                self.table.item(r, c).text().lower()
                for c in range(self.table.columnCount())
                if self.table.item(r, c)
            )
            hide = bool(text) and text not in haystack
            self.table.setRowHidden(r, hide)
            shown += 0 if hide else 1
        total = self.table.rowCount()
        self.count.setText(
            f"{shown} of {total} entries" if text else f"{total} entries"
        )


class NamedSelectionsTab(_FilterTable):
    """Labels the geometry must define, and what each becomes in Fluent."""

    def __init__(self, parent=None):
        super().__init__(
            "Named Selections",
            "Create these in Ansys Discovery before exporting the .pmdb. "
            "The names must match exactly — a mismatch means the sizing "
            "control or report silently covers nothing. Entries marked "
            "optional may be left out.",
            ["Label", "Becomes", "Description"],
            parent,
        )

    def load(self, sim_type) -> None:
        rows = []
        for label, entry in sim_type.NAMED_SELECTIONS.items():
            if len(entry) == 3:
                kind, required, description = entry
            else:                       # older two-part form
                kind, description = entry
                required = True
            marker = "" if required else "optional -- "
            rows.append((label, kind, f"{marker}{description}"))
        self._fill(rows, TYPE_COLOURS)


class ReportDefinitionsTab(_FilterTable):
    """Reports the simulation creates in Fluent."""

    def __init__(self, parent=None):
        super().__init__(
            "Report Definitions",
            "Created in Fluent when the simulation runs, and written to the "
            "results file when it finishes. Expression reports are evaluated "
            "by Ansys itself rather than in Python.",
            ["Report", "Kind", "Description"],
            parent,
        )

    def load(self, sim_type) -> None:
        rows = [(name, kind, description)
                for name, (kind, description)
                in sim_type.REPORT_DEFINITIONS.items()]
        self._fill(rows, KIND_COLOURS)
