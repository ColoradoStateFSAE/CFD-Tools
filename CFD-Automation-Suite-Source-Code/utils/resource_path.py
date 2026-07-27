"""
Shared path utilities.

Two kinds of path are resolved here:

  resource_path()  read-only assets baked into the build (logo, PDFs)
  journals_dir()   the recorded Fluent journals, which must stay EDITABLE
                   after install so journals can be re-recorded without
                   rebuilding the executable
"""
import sys
import os


def _project_root() -> str:
    """Directory containing main.py — one level above utils/."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_frozen() -> bool:
    """True when running from a PyInstaller build."""
    return getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")


def resource_path(relative: str) -> str:
    """
    Absolute path to a bundled read-only resource.

    Frozen builds extract data files to sys._MEIPASS; from source they sit
    under the project root.
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(_project_root(), relative)


def journals_dir() -> str:
    """
    Absolute path to the journals directory.

    Journals are recorded output that the aero team edits and re-records, so
    an installed copy must be writable. Search order:

      1. RAMRACING_JOURNALS environment variable  (explicit override)
      2. <directory containing the executable>/journals   (installed, editable)
      3. sys._MEIPASS/journals                            (bundled fallback)
      4. <project root>/journals                          (running from source)

    Returns the first candidate that exists. If none do, returns the path it
    would prefer so the caller can report a useful error.
    """
    candidates = []

    override = os.environ.get("RAMRACING_JOURNALS", "").strip()
    if override:
        candidates.append(override)

    if is_frozen():
        # Next to the .exe — where the installer puts the editable copy
        candidates.append(
            os.path.join(os.path.dirname(sys.executable), "journals")
        )
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "journals"))

    candidates.append(os.path.join(_project_root(), "journals"))

    for path in candidates:
        if os.path.isdir(path):
            return os.path.abspath(path)

    return os.path.abspath(candidates[0]) if candidates else ""


def journal_path(sim_type_key: str, stage: str,
                 override_dir: str = "") -> str:
    """
    Path to one journal.

        journal_path("half_car", "mesh")  -> <journals>/half_car/mesh.py

    `stage` is "mesh" or "solve".

    `override_dir` comes from BaseSimConfig.journal_dir and points straight at
    a folder containing mesh.py and solve.py, bypassing the sim-type layout.
    That lets one job run a variant journal without disturbing the installed
    set.

    Existence is not checked here — the caller reports a missing journal with
    the context of which simulation needed it.
    """
    override_dir = (override_dir or "").strip()
    if override_dir:
        return os.path.join(override_dir, f"{stage}.py")
    return os.path.join(journals_dir(), sim_type_key, f"{stage}.py")