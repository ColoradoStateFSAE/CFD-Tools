"""
Shared path utilities.
"""
import sys
import os


def resource_path(relative: str) -> str:
    """
    Return the absolute path to a bundled resource.

    When running from a PyInstaller frozen executable, files are extracted
    to sys._MEIPASS.  During normal development, paths are resolved relative
    to the project root (the directory containing this file's parent package).
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    # Project root is one level above this file (utils/ → project root)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, relative)
  
