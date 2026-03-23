"""
Ram Racing CFD Tool — PyQt6 theme / stylesheet.
One place to change colors for the whole app.
"""

# ── Palette ───────────────────────────────────────────────────────────────────
DARK_BG    = "#1e2127"
PANEL_BG   = "#282c34"
SIDEBAR_BG = "#21252b"
ACCENT     = "#00b4a0"
ACCENT2    = "#4fc3f7"
TEXT       = "#abb2bf"
TEXT_BRIGHT= "#e6e6e6"
RED        = "#e06c75"
GREEN      = "#98c379"
YELLOW     = "#e5c07b"
ORANGE     = "#d19a66"
BORDER     = "#3e4451"
INPUT_BG   = "#2c313a"
HOVER_BG   = "#2f3541"
SEL_BG     = "#3e4451"

STATUS_COLORS = {
    "Queued":    YELLOW,
    "Running":   ACCENT2,
    "Done":      GREEN,
    "Failed":    RED,
    "Cancelled": TEXT,
}

# ── Global QSS stylesheet ─────────────────────────────────────────────────────
QSS = f"""
/* ── Base ── */
QWidget {{
    background-color: {DARK_BG};
    color: {TEXT_BRIGHT};
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 9pt;
}}

QMainWindow {{
    background-color: {DARK_BG};
}}

/* ── Frames / Group boxes ── */
QFrame {{
    background-color: transparent;
}}

QGroupBox {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    font-weight: bold;
    color: {ACCENT};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {ACCENT};
}}

/* ── Labels ── */
QLabel {{
    background-color: transparent;
    color: {TEXT_BRIGHT};
}}

QLabel#heading {{
    font-size: 13pt;
    font-weight: bold;
    color: {ACCENT};
}}

QLabel#subheading {{
    font-size: 10pt;
    font-weight: bold;
    color: {ACCENT2};
}}

QLabel#muted {{
    color: {TEXT};
    font-style: italic;
    font-size: 8pt;
}}

QLabel#status_queued    {{ color: {YELLOW}; font-weight: bold; }}
QLabel#status_running   {{ color: {ACCENT2}; font-weight: bold; }}
QLabel#status_done      {{ color: {GREEN}; font-weight: bold; }}
QLabel#status_failed    {{ color: {RED}; font-weight: bold; }}
QLabel#status_cancelled {{ color: {TEXT}; font-weight: bold; }}

/* ── Buttons ── */
QPushButton {{
    background-color: {PANEL_BG};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 14px;
    font-size: 9pt;
}}

QPushButton:hover {{
    background-color: {HOVER_BG};
    border-color: {ACCENT};
    color: {TEXT_BRIGHT};
}}

QPushButton:pressed {{
    background-color: {SEL_BG};
}}

QPushButton#accent {{
    background-color: {ACCENT};
    color: #0d1117;
    border: none;
    font-weight: bold;
    padding: 6px 18px;
}}

QPushButton#accent:hover {{
    background-color: {ACCENT2};
    color: #0d1117;
}}

QPushButton#accent:pressed {{
    background-color: #007a6e;
}}

QPushButton#danger {{
    background-color: transparent;
    color: {RED};
    border: 1px solid {RED};
}}

QPushButton#danger:hover {{
    background-color: {RED};
    color: white;
}}

QPushButton:disabled {{
    background-color: {PANEL_BG};
    color: {BORDER};
    border-color: {BORDER};
}}

/* ── Icon / arrow buttons (▲ ▼ ✎ ✕) ── */
QPushButton[text="▲"], QPushButton[text="▼"] {{
    background-color: {PANEL_BG};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 0px;
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    font-size: 13pt;
    font-family: "Segoe UI Symbol", "Arial Unicode MS", sans-serif;
    qproperty-iconSize: 0px;
}}

QPushButton[text="▲"]:hover, QPushButton[text="▼"]:hover {{
    background-color: {HOVER_BG};
    border-color: {ACCENT};
    color: {ACCENT};
}}

/* ── Inputs ── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {INPUT_BG};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {ACCENT};
    selection-color: #0d1117;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT};
    margin-right: 6px;
}}

QComboBox QAbstractItemView {{
    background-color: {PANEL_BG};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: #0d1117;
    outline: none;
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {BORDER};
    border: none;
    width: 16px;
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-bottom: 4px solid {TEXT};
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid {TEXT};
}}

/* ── CheckBox ── */
QCheckBox {{
    color: {TEXT_BRIGHT};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {INPUT_BG};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* ── RadioButton ── */
QRadioButton {{
    color: {TEXT_BRIGHT};
    spacing: 10px;
    font-size: 10pt;
}}

QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 2px solid {BORDER};
    background-color: {INPUT_BG};
}}

QRadioButton::indicator:hover {{
    border-color: {ACCENT};
}}

QRadioButton::indicator:checked {{
    border: 2px solid {ACCENT};
    background-color: {INPUT_BG};
    image: none;
}}

QRadioButton::indicator:checked {{
    border: 3px solid {ACCENT};
    background-color: {ACCENT};
}}

/* ── Tab widget ── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 0 6px 6px 6px;
    background-color: {PANEL_BG};
    top: -1px;
}}

QTabBar::tab {{
    background-color: {SIDEBAR_BG};
    color: {TEXT};
    padding: 7px 18px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-radius: 5px 5px 0 0;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {PANEL_BG};
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}

QTabBar::tab:hover:!selected {{
    background-color: {HOVER_BG};
    color: {TEXT_BRIGHT};
}}

/* ── Table / Tree ── */
QTreeWidget, QTableWidget {{
    background-color: {DARK_BG};
    alternate-background-color: {PANEL_BG};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    gridline-color: {BORDER};
    outline: none;
}}

QTreeWidget::item, QTableWidget::item {{
    padding: 4px 6px;
    border: none;
}}

QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: {SEL_BG};
    color: {TEXT_BRIGHT};
}}

QTreeWidget::item:hover, QTableWidget::item:hover {{
    background-color: {HOVER_BG};
}}

QHeaderView::section {{
    background-color: {SIDEBAR_BG};
    color: {ACCENT};
    padding: 5px 8px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-weight: bold;
    font-size: 8.5pt;
}}

/* ── Progress bar ── */
QProgressBar {{
    background-color: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}

/* ── Scroll bars ── */
QScrollBar:vertical {{
    background: {DARK_BG};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: {DARK_BG};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {TEXT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Splitter ── */
QSplitter::handle {{
    background-color: {BORDER};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical   {{ height: 1px; }}

/* ── Plain text / log ── */
QPlainTextEdit, QTextEdit {{
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid {BORDER};
    border-radius: 4px;
    font-family: "Consolas", "Cascadia Code", "Courier New", monospace;
    font-size: 8pt;
    selection-background-color: {ACCENT};
}}

/* ── Menu bar ── */
QMenuBar {{
    background-color: {PANEL_BG};
    color: {TEXT_BRIGHT};
    border-bottom: 1px solid {BORDER};
}}

QMenuBar::item:selected {{
    background-color: {HOVER_BG};
}}

QMenu {{
    background-color: {PANEL_BG};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
}}

QMenu::item:selected {{
    background-color: {ACCENT};
    color: #0d1117;
}}

QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 4px 0;
}}

/* ── Status bar ── */
QStatusBar {{
    background-color: {PANEL_BG};
    color: {TEXT};
    border-top: 1px solid {BORDER};
    font-size: 8pt;
}}

/* ── Dialogs ── */
QDialog {{
    background-color: {DARK_BG};
}}

/* ── Tooltip ── */
QToolTip {{
    background-color: {PANEL_BG};
    color: {TEXT_BRIGHT};
    border: 1px solid {ACCENT};
    padding: 4px 8px;
    border-radius: 4px;
}}
"""