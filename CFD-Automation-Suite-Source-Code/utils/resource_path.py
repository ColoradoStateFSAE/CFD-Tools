"""
Path helpers for bundled assets.

Resolves files that ship with the application, whether running from source or
from a PyInstaller build.
"""
import os
import sys


def resource_path(relative: str) -> str:
    """
    Absolute path to a bundled resource, for example "assets/logo.png".

    PyInstaller extracts data files to sys._MEIPASS at runtime; from source
    they sit under the project root.
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, relative)


def is_frozen() -> bool:
    """True when running from a PyInstaller build."""
    return getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")