"""
Application stylesheet.

One Dark base with Colorado State green (#1E4D2B) as the brand accent,
lightened to #3d9960 where it needs to read against a dark background.
"""

# ── Palette ──────────────────────────────────────────────────────────────
BG          = "#21252b"     # window background
PANEL       = "#282c34"     # cards, headers, footers
PANEL_LIGHT = "#2c313a"     # inputs, list rows
BORDER      = "#3e4451"
BORDER_LIT  = "#4b5263"

TEXT        = "#abb2bf"     # body
TEXT_BRIGHT = "#dcdfe4"     # headings, values
TEXT_MUTED  = "#7f8593"     # hints, captions

CSU_GREEN   = "#1E4D2B"     # brand
ACCENT      = "#3d9960"     # brand, lightened for dark backgrounds
ACCENT_HOVER = "#4bb072"

OK      = "#98c379"
WARN    = "#e5c07b"
ERROR   = "#e06c75"
INFO    = "#61afef"
RUNNING = "#c678dd"

# Job state -> colour, shared by the queue list and detail pane
STATE_COLOURS = {
    "Pending":   TEXT_MUTED,
    "Running":   RUNNING,
    "Completed": OK,
    "Failed":    ERROR,
    "Cancelled": WARN,
}


QSS = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Cantarell", sans-serif;
    font-size: 12px;
}}

QMainWindow, QDialog {{ background-color: {BG}; }}

/* ── Headings ───────────────────────────────────────────────────────── */
QLabel#heading {{
    color: {TEXT_BRIGHT};
    font-size: 17px;
    font-weight: 600;
    padding: 2px 0;
}}
QLabel#subheading {{
    color: {ACCENT};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 10px 0 3px 0;
}}
QLabel#muted {{ color: {TEXT_MUTED}; font-size: 11px; }}
QLabel#value {{ color: {TEXT_BRIGHT}; font-weight: 600; }}

/* ── Inputs ─────────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background-color: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    color: {TEXT_BRIGHT};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {PANEL};
    color: {TEXT_MUTED};
}}
QLineEdit[valid="false"] {{ border: 1px solid {ERROR}; }}

QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    color: {TEXT_BRIGHT};
    outline: none;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: {PANEL};
    border: none;
    width: 15px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {BORDER_LIT};
}}

/* ── Buttons ────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 14px;
    color: {TEXT_BRIGHT};
}}
QPushButton:hover {{ background-color: {BORDER}; border-color: {BORDER_LIT}; }}
QPushButton:pressed {{ background-color: {PANEL}; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; border-color: {PANEL}; }}

QPushButton#accent {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#accent:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#accent:disabled {{
    background-color: {PANEL_LIGHT};
    border-color: {BORDER};
    color: {TEXT_MUTED};
}}
QPushButton#danger {{ color: {ERROR}; }}
QPushButton#danger:hover {{ background-color: {ERROR}; color: #ffffff; }}

/* ── Tabs ───────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background-color: {PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_MUTED};
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{
    color: {TEXT_BRIGHT};
    border-bottom: 2px solid {ACCENT};
}}

/* ── Lists and tables ───────────────────────────────────────────────── */
QListWidget, QTableWidget, QTreeWidget {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 4px;
    outline: none;
    alternate-background-color: {PANEL_LIGHT};
}}
QListWidget::item {{ padding: 7px 9px; border-radius: 3px; }}
QListWidget::item:hover {{ background-color: {PANEL_LIGHT}; }}
QListWidget::item:selected {{
    background-color: {CSU_GREEN};
    color: {TEXT_BRIGHT};
}}

QTableWidget {{ gridline-color: {BORDER}; }}
QTableWidget::item {{ padding: 5px 7px; }}
QTableWidget::item:selected {{ background-color: {CSU_GREEN}; }}
QHeaderView::section {{
    background-color: {PANEL_LIGHT};
    color: {ACCENT};
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}

/* ── Progress ───────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    height: 16px;
    text-align: center;
    color: {TEXT_BRIGHT};
    font-size: 11px;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 2px; }}

/* ── Group boxes ────────────────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
    color: {TEXT_BRIGHT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: {ACCENT};
}}

/* ── Log ────────────────────────────────────────────────────────────── */
QPlainTextEdit#log {{
    background-color: #1b1e24;
    border: 1px solid {BORDER};
    font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 11px;
    color: {TEXT};
}}

/* ── Scrollbars ─────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background-color: {BG}; width: 11px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {BORDER}; border-radius: 5px; min-height: 26px;
}}
QScrollBar::handle:vertical:hover {{ background-color: {BORDER_LIT}; }}
QScrollBar:horizontal {{
    background-color: {BG}; height: 11px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {BORDER}; border-radius: 5px; min-width: 26px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ── Misc ───────────────────────────────────────────────────────────── */
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {PANEL_LIGHT};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
QSplitter::handle {{ background-color: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{ color: {BORDER}; }}
QMenuBar {{ background-color: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 6px 11px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {PANEL_LIGHT}; }}
QMenu {{
    background-color: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 3px; }}
QMenu::item:selected {{ background-color: {CSU_GREEN}; }}
QToolTip {{
    background-color: {PANEL_LIGHT};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
    padding: 5px;
}}
QStatusBar {{ background-color: {PANEL}; border-top: 1px solid {BORDER}; }}
"""