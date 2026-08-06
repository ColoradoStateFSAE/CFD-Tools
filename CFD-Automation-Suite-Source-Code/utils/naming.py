"""
Run identification and output folder layout.

Matches CFD_Rolling_Report.xlsx, so a simulation and its Master Log row carry
the same identifier and nothing has to be cross-referenced by hand.

    Project     the car or study, e.g. "RR27"
    Run         a batch of related points, e.g. "R018"
    MAP #       one attitude within that run, e.g. 1

    Point ID    Run-MAPxx, e.g. "R018-MAP01"

Folders mirror that hierarchy, so everything for a point lands together:

    <root>/
        Dauntless/
            R018/
                R018-MAP01/      case files, EnSight export, results .txt
                R018-MAP02/
            R019/
                R019-MAP01/
"""
import os
import re
from dataclasses import dataclass


def normalise_run(run: str) -> str:
    """
    Put a run label into the canonical Rnnn form.

        "18"   -> "R018"      "R18"  -> "R018"
        "r018" -> "R018"      "R018" -> "R018"

    A label that is not a plain number keeps its own text, uppercased, so
    something like "BASELINE" still works.
    """
    run = (run or "").strip()
    if not run:
        return ""
    match = re.fullmatch(r"[Rr]?0*(\d+)", run)
    if match:
        return f"R{int(match.group(1)):03d}"
    return run.upper()


def safe(component: str) -> str:
    """Make one path component safe without mangling it."""
    cleaned = "".join(
        c if c.isalnum() or c in "._- " else "_" for c in str(component)
    ).strip()
    return cleaned or "unnamed"


@dataclass
class RunIdentity:
    """
    Identifies one simulated point and where its output belongs.

    Everything here is derived, so the Point ID on disk and the Point ID in
    the Master Log cannot drift apart.
    """
    project:    str = ""
    run:        str = ""
    map_number: int = 1
    root:       str = ""        # folder holding every project

    # ── Identity ─────────────────────────────────────────────────────────

    @property
    def run_id(self) -> str:
        """Canonical run label, e.g. R018."""
        return normalise_run(self.run)

    @property
    def point_id(self) -> str:
        """
        Unique identifier for this point, e.g. R018-MAP01.

        The run is part of it so two runs can reuse a MAP number without
        colliding.
        """
        run_id = self.run_id
        if not run_id:
            return ""
        return f"{run_id}-MAP{int(self.map_number):02d}"

    # ── Folders ──────────────────────────────────────────────────────────

    @property
    def project_dir(self) -> str:
        if not self.root or not self.project:
            return ""
        return os.path.join(self.root, safe(self.project))

    @property
    def run_dir(self) -> str:
        parent = self.project_dir
        if not parent or not self.run_id:
            return ""
        return os.path.join(parent, safe(self.run_id))

    @property
    def map_dir(self) -> str:
        """<root>/<project>/<run>/<point id> -- where output is written."""
        parent = self.run_dir
        if not parent or not self.point_id:
            return ""
        return os.path.join(parent, safe(self.point_id))

    # ── Checks ───────────────────────────────────────────────────────────

    def validate(self) -> list:
        """Problems preventing a usable Point ID or folder. Empty if fine."""
        problems = []
        if not (self.root or "").strip():
            problems.append(
                "No projects folder. Set one in File > Settings.")
        if not (self.project or "").strip():
            problems.append("No project name, e.g. Dauntless")
        if not self.run_id:
            problems.append("No run number, e.g. R018")
        if int(self.map_number) < 1:
            problems.append("MAP number must be 1 or greater")
        return problems

    @property
    def exists(self) -> bool:
        """True if this point already has a folder, i.e. it has been run."""
        path = self.map_dir
        return bool(path) and os.path.isdir(path)

    def describe(self) -> str:
        """One line summarising where output will go."""
        path = self.map_dir
        if not path:
            return "Set the projects folder, project and run to build a path"
        return path + ("   (already exists)" if self.exists else "")

    # ── Convenience ──────────────────────────────────────────────────────

    def next_map_number(self) -> int:
        """
        The next unused MAP number for this run, from what is on disk.
        Returns 1 when the run is new.
        """
        run_path = self.run_dir
        if not run_path or not os.path.isdir(run_path):
            return 1

        used = []
        pattern = re.compile(rf"{re.escape(self.run_id)}-MAP(\d+)$")
        for entry in os.listdir(run_path):
            match = pattern.fullmatch(entry)
            if match:
                used.append(int(match.group(1)))
        return max(used) + 1 if used else 1

    def known_projects(self) -> list:
        """Existing project folders under the root, for a dropdown."""
        if not self.root or not os.path.isdir(self.root):
            return []
        return sorted(
            entry for entry in os.listdir(self.root)
            if os.path.isdir(os.path.join(self.root, entry))
            and not entry.startswith(".")
        )

    def known_runs(self) -> list:
        """Existing run folders in this project, newest label last."""
        parent = self.project_dir
        if not parent or not os.path.isdir(parent):
            return []
        return sorted(
            entry for entry in os.listdir(parent)
            if os.path.isdir(os.path.join(parent, entry))
            and not entry.startswith(".")
        )


# ── Module-level convenience, for populating dropdowns ───────────────────────

def existing_projects(root: str) -> list:
    """Project folders already under the root."""
    return RunIdentity(root=root).known_projects()


def existing_runs(root: str, project: str) -> list:
    """Run folders already in a project."""
    return RunIdentity(root=root, project=project).known_runs()


def next_map_number(root: str, project: str, run: str) -> int:
    """First unused MAP number for a run."""
    return RunIdentity(root=root, project=project, run=run).next_map_number()
