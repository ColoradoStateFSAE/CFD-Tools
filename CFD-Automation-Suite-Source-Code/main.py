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

    # Default font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    window = RamRacingCFDWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
