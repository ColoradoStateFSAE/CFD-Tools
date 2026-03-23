"""
Ram Racing CFD Automation Tool — Entry Point (PyQt6)
Run:  python main.py
Build: pyinstaller RamRacingCFD.spec
"""
import sys
import os

# Ensure project root is on the path when run as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from gui.app import RamRacingCFDWindow
from gui.theme import QSS


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Ram Racing CFD Automation")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("Ram Racing FSAE")

    # Global stylesheet
    app.setStyleSheet(QSS)
    
    #Windows Icon
    def _resource_path(relative):
        import sys, os
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)

    from PyQt6.QtGui import QIcon
    icon_path = _resource_path(os.path.join("assets", "logo.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # Default font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    window = RamRacingCFDWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
