"""
Ram Racing CFD Automation Suite

Each simulation type is one self-contained file under simtypes/, holding its
own settings, meshing sequence, solver setup and report definitions.

Run:    python main.py
Build:  pyinstaller RamRacingCFD.spec
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_NAME    = "Ram Racing CFD Automation"
APP_VERSION = "4.0"
ORG_NAME    = "Ram Racing FSAE"


def fail(title: str, message: str) -> None:
    """Report a startup failure, through a dialog when Qt is available."""
    print(f"\n{title}\n{'-' * len(title)}\n{message}\n", file=sys.stderr)
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, message)
    except Exception:
        pass
    sys.exit(1)


def check_dependencies() -> None:
    missing = []
    try:
        import PyQt6.QtWidgets  # noqa: F401
    except ImportError:
        missing.append("PyQt6              pip install PyQt6 --only-binary=:all:")
    try:
        import ansys.fluent.core  # noqa: F401
    except ImportError:
        missing.append("ansys-fluent-core  pip install ansys-fluent-core")

    if missing:
        fail("Missing dependencies",
             "The following packages are required:\n\n  "
             + "\n  ".join(missing)
             + "\n\nOr install everything:  pip install -r requirements.txt")


def check_ansys() -> None:
    """Locate Ansys Fluent 2026 R1. A warning, not a failure."""
    if os.environ.get("AWP_ROOT261"):
        print(f"Ansys:  AWP_ROOT261={os.environ['AWP_ROOT261']}")
        return

    for path in (r"C:\Program Files\ANSYS Inc\v261",
                 os.path.expanduser("~/ansys_inc/v261"),
                 "/ansys_inc/v261",
                 "/usr/ansys_inc/v261"):
        if os.path.isdir(path):
            os.environ["AWP_ROOT261"] = path
            print(f"Ansys:  {path}")
            return

    print("Ansys:  NOT FOUND -- set AWP_ROOT261 before running a simulation")


def main() -> None:
    print(f"{APP_NAME} {APP_VERSION}")
    check_dependencies()

    import simtypes
    print(f"Types:  {', '.join(name for _, name in simtypes.names())}")
    check_ansys()
    print()

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont, QIcon

    from gui.app import MainWindow
    from gui.theme import QSS
    from utils.resource_path import resource_path

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)
    app.setStyleSheet(QSS)
    app.setFont(QFont("Segoe UI", 9))

    icon = resource_path(os.path.join("assets", "logo.png"))
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()