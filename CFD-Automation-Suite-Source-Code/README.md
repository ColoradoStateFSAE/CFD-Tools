# CFD Automation Suite

Desktop application that automates the Ram Racing aero CFD pipeline in Ansys Fluent: geometry → mesh → solve → results, unattended, queued, and organized on disk automatically.

**Target:** Ansys Fluent 2026 R1 (v261) · PyFluent ≥ 0.39 · Python 3.12 · PyQt6

---

## Design

Every simulation type is **one self-contained file** under `simtypes/`. There is no shared base class and no separate config format — a file like `simtypes/half_car.py` contains its own `Settings` dataclass, its own meshing sequence, its own solver setup, and its own report definitions. Reading that one file tells you exactly what running Half Car does.

Adding a new simulation type means writing one new file and adding it to `simtypes/__init__.py`. Nothing in `gui/` or `core/` needs to change — the editor, the reference tabs, and the queue are all driven generically off whatever `Settings`, `NAMED_SELECTIONS`, and `REPORT_DEFINITIONS` a simulation type exposes.

```
main.py                    Entry point, dependency and Ansys checks

simtypes/
  __init__.py               Registry: MODULES, get(), names()
  half_car.py                Complete: settings, mesh(), solve(), reports
  full_car.py                 Same shape, no symmetry, all 4 wheels
  quarter_model.py             Same shape, two symmetry planes

core/
  queue_manager.py           Background worker, one job at a time
  web_monitor.py             Phone/browser monitor (plain HTTP, no auth)

gui/
  app.py                     Main window: queue, detail pane, log
  sim_editor.py               Tabbed editor for one simulation's settings
  reference_tabs.py            Named Selections / Report Definitions tables
  settings_dialog.py           App-wide defaults (projects root, MPI, etc.)
  theme.py                     Stylesheet

utils/
  naming.py                  Project/Run/MAP Point ID and folder layout
  refinement.py               Near/Mid/Far box coordinate calculator
  fluent_log.py                Streams Fluent's transcript into the log
  log_buffer.py                 Rolling log buffer the phone monitor reads
  results_exporter.py            Writes the results .txt
  resource_path.py               Bundled asset paths (dev vs. PyInstaller)
```

---

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows

pip install --upgrade pip
pip install PyQt6 --only-binary=:all:
pip install ansys-fluent-core>=0.39.0

export AWP_ROOT261=/path/to/ansys_inc/v261     # set once; auto-detected after

python main.py
```

`PyQt6 --only-binary=:all:` matters — building it from source needs `qmake`, which usually isn't present on HPC nodes.

---

## Running a simulation

1. **File → New Simulation**, pick a type
2. **General tab** — set Project, Run, and MAP #. The Point ID (`R018-MAP01`) and output folder build themselves; nothing is typed by hand. Use **Next free** to auto-pick the next unused MAP number for a run.
3. Point **Geometry** at a watertight `.pmdb`/`.dsco`, or set **Existing Mesh** to skip meshing entirely and go straight to solving
4. **Meshing / Solver / Wheels tabs** — adjust sizing, ramp iteration counts, wheel radius and origin as needed
5. **Named Selections** and **Reports** tabs are read-only references showing exactly what this simulation type expects from your Discovery geometry and what it will produce — check these against your actual geometry before running
6. Save, then **▶ Start Queue** when you're ready — adding a simulation does *not* start it automatically

Output lands at:

```
<projects root>/<project>/<run>/<point id>/
    mesh.msh.h5
    <point id>_ramp1.cas.h5, _ramp2.cas.h5, _final.cas.h5
    <point id>_ensight/
    <point id>_<timestamp>_results.txt
    solution.trn  (and other Fluent working files — see note below)
```

`launch_fluent(..., cwd=...)` is set to that folder, so Fluent's own transcript and cleanup files land there too, not in whatever directory the app happened to be started from.

---

## Named selections

Each simulation type's **Named Selections** tab is the authoritative list — it's read directly from that file's `NAMED_SELECTIONS` dict, so it can't drift out of sync with what the code actually does. A quick summary:

| | Half Car | Full Car | Quarter Model |
|---|---|---|---|
| Symmetry | `symmetry` (z = 0) | none | `symmetry` + `symmetry2` |
| Wheels | `fw`/`fwb`, `rw`/`rwb` | `flw`/`frw`/`rlw`/`rrw` + blocks | one corner only |
| Doubling | ×2 | ×1 | ×4 |

`ground`, `inlet`, `outlet`, and `walls` are required in every type. Optional labels (sidepod, suspension) are skipped automatically if the geometry doesn't have them — meshing won't fail because of a missing optional label, only a missing *required* one, and it fails fast (right after geometry import) rather than after a full meshing run.

---

## Wheels

Wheels are **rotating walls** — moving wall, absolute, rotational about the axle. There is no MRF and no separate rotating cell zone. Set the wheel radius and one origin per axle in the Wheels tab; for Full Car, that origin is the right-side (+Z) point and the left side is mirrored automatically.

Rotation rate is computed from vehicle speed and wheel radius (`ω = v / r`), logged at solve time.

---

## Reports

27 report definitions per run (fewer for Quarter Model, since only one end of the car exists). Totals, per-element forces, and moments are ordinary Fluent report definitions; **SCz, SCx, copx, copz, and cop_pct are Fluent expressions** — Ansys evaluates them, not Python. If the expression API isn't available on a given Fluent build, `_read_reports()` falls back to computing the same thing from the raw forces, and logs when it does.

Half Car and Quarter Model results are scaled (×2, ×4) to represent the full car; Full Car is not, since all sides are already meshed.

---

## Phone monitor

The app serves the queue and a live log tail over plain HTTP — no login, since [Tailscale](https://tailscale.com) is the access control. **File → Phone Monitor** shows the URL. Enable/disable and the port are in **File → Settings**.

```
http://<tailscale-ip>:8765
```

---

## Building

```bash
pyinstaller --clean RamRacingCFD.spec
```

Windows installer (`installer.nsi`) and the RPM spec expect the PyInstaller bundle to already exist — run PyInstaller first, always. Both scripts fail loudly rather than silently packaging an empty or broken bundle.

If a new `simtypes/` or `utils/` module doesn't show up in the built app, check it's listed in `RamRacingCFD.spec`'s hidden imports:

```bash
python3 - << 'EOF'
import re, os
spec = open('RamRacingCFD.spec').read()
listed = set(re.findall(r'"((?:core|gui|utils|simtypes)(?:\.\w+)?)"', spec))
actual = set()
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('__pycache__', 'dist', 'build')]
    for f in files:
        if f.endswith('.py') and f != 'main.py':
            m = os.path.join(root, f)[2:-3].replace(os.sep, '.').replace('.__init__', '')
            if m.split('.')[0] in ('core', 'gui', 'utils', 'simtypes'):
                actual.add(m)
print("in spec, no module:", sorted(listed - actual) or "none")
print("module, not in spec:", sorted(actual - listed) or "none")
EOF
```

---

## Adding a simulation type

1. Copy the closest existing file in `simtypes/` (e.g. `half_car.py` for anything with a symmetry plane, `full_car.py` for anything without)
2. Change `NAME`, `KEY`, `NAMED_SELECTIONS`, and whatever meshing/solving logic actually differs
3. Add it to `MODULES` in `simtypes/__init__.py`
4. Add it to the hidden imports in `RamRacingCFD.spec`

It appears in **New Simulation**, gets its own Named Selections and Reports tabs, and joins the queue automatically — nothing else needs to change.

---

## See also

- `TESTING_CHECKLIST.md` — what to actually verify against real Fluent before trusting a build
- `CHANGELOG.md` — what changed and why, including bugs found and fixed along the way
