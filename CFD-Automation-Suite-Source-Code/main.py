"""
Ram Racing CFD Automation Suite — Entry Point

Journal-driven architecture: the Fluent workflow lives in recorded Python
journals under journals/<sim_type>/{mesh,solve}.py, which the suite renders
and executes. See journals/README.md.

Run:    python main.py
Build:  pyinstaller RamRacingCFD.spec
"""
import os
import sys

# Project root on the path when run as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_NAME    = "Ram Racing CFD Automation"
APP_VERSION = "3.0"
ORG_NAME    = "Ram Racing FSAE"

# Every simulation type needs a folder here. Kept in sync with SimType
# in simtypes/configs.py.
EXPECTED_SIM_TYPES = [
    "half_car",
    "full_car",
    "front_wing",
    "rear_wing",
    "quarter_model",
    "turning",
]


def _fail(title: str, message: str) -> None:
    """Report a startup failure through a dialog if possible, else stderr."""
    print(f"\n{title}\n{'-' * len(title)}\n{message}\n", file=sys.stderr)
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, message)
    except Exception:
        pass
    sys.exit(1)


def check_dependencies() -> None:
    """Verify the imports the app cannot start without."""
    missing = []
    try:
        import PyQt6.QtWidgets  # noqa: F401
    except ImportError:
        missing.append("PyQt6            pip install PyQt6 --only-binary=:all:")
    try:
        import ansys.fluent.core  # noqa: F401
    except ImportError:
        missing.append("ansys-fluent-core  pip install ansys-fluent-core")

    if missing:
        _fail(
            "Missing dependencies",
            "The following packages are required:\n\n  "
            + "\n  ".join(missing)
            + "\n\nOr install everything:  pip install -r requirements.txt",
        )


def check_journals() -> tuple:
    """
    Locate the journals directory and report which simulation types are usable.

    A missing journal is not fatal — the rest of the app still runs and the
    affected simulation type reports the problem when queued.

    Returns (journals_dir, {sim_type: (has_mesh, has_solve)}).
    """
    from utils.resource_path import journals_dir

    root = journals_dir()
    if not os.path.isdir(root):
        _fail(
            "Journals not found",
            f"Expected the journals directory at:\n\n    {root}\n\n"
            "The suite runs recorded Fluent journals and cannot mesh or solve "
            "without them.\n\n"
            "Reinstall, or set RAMRACING_JOURNALS to the directory containing "
            "half_car/, full_car/, and so on.",
        )

    status = {}
    for sim_type in EXPECTED_SIM_TYPES:
        folder = os.path.join(root, sim_type)
        status[sim_type] = (
            os.path.isfile(os.path.join(folder, "mesh.py")),
            os.path.isfile(os.path.join(folder, "solve.py")),
        )
    return root, status


def _report_journal_status(root: str, status: dict) -> None:
    """Print which journals were found, so a partial install is obvious."""
    ready   = [t for t, (m, s) in status.items() if m and s]
    partial = [t for t, (m, s) in status.items() if (m or s) and not (m and s)]
    absent  = [t for t, (m, s) in status.items() if not m and not s]

    print(f"Journals: {root}")
    if ready:
        print(f"  ready    {', '.join(ready)}")
    for sim_type in partial:
        has_mesh, has_solve = status[sim_type]
        missing = "solve.py" if has_mesh else "mesh.py"
        print(f"  partial  {sim_type} — missing {missing}")
    if absent:
        print(f"  absent   {', '.join(absent)}")
    if not ready:
        print("  WARNING: no simulation type has both journals recorded yet.")
        print("  Record them with:  python tools/record_journal.py --help")


def check_ansys() -> None:
    """
    Warn if Ansys Fluent 2026 R1 is not visible. Not fatal — the app is
    still useful for editing and queueing simulations without it.
    """
    if os.environ.get("AWP_ROOT261"):
        print(f"Ansys:    AWP_ROOT261={os.environ['AWP_ROOT261']}")
        return

    candidates = [
        r"C:\Program Files\ANSYS Inc\v261",
        os.path.expanduser("~/ansys_inc/v261"),
        "/ansys_inc/v261",
        "/usr/ansys_inc/v261",
    ]
    for path in candidates:
        if os.path.isdir(path):
            os.environ["AWP_ROOT261"] = path
            print(f"Ansys:    {path}  (AWP_ROOT261 set automatically)")
            return

    print("Ansys:    NOT FOUND — set AWP_ROOT261 before running a simulation")


def main() -> None:
    print(f"{APP_NAME} {APP_VERSION}")

    check_dependencies()

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont, QIcon

    journals_root, journal_status = check_journals()
    _report_journal_status(journals_root, journal_status)
    check_ansys()
    print()

    from gui.app import RamRacingCFDWindow
    from gui.theme import QSS
    from utils.resource_path import resource_path

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)
    app.setStyleSheet(QSS)

    icon_path = resource_path(os.path.join("assets", "logo.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    app.setFont(QFont("Segoe UI", 9))

    window = RamRacingCFDWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()