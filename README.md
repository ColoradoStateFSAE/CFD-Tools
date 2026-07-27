<img width="207" height="233" alt="Ram Racing Logo" src="https://github.com/user-attachments/assets/0967733d-0662-43cc-ac3a-1226af33b587" />

# Ram Racing FSAE — Aero CFD Tools

A collection of aerodynamic simulation tools, automation software, MATLAB analysis scripts, and reference documentation maintained by the Ram Racing FSAE Aerodynamics Subteam.

**Current target:** Ansys Fluent 2026 R1 (v261) · PyFluent 0.39 · Python 3.12

---

## Repository Contents

| Directory | Description |
|-----------|-------------|
| [`CFD-Automation-Suite-Source-Code/`](#cfd-automation-suite) | Desktop GUI application — automates the full Fluent CFD pipeline |
| [`MATLAB-Scripts/`](#matlab-scripts) | Post-processing scripts for CoP, aero balance, and refinement box generation |
| [`Documentation/`](#documentation) | Ansys Fluent procedure document and team references |
| [`Documents/`](#documents) | External reference material (Fluent tutorial guides, etc.) |

---

## Downloads

Nightly builds are published automatically from `main`:

**[→ Latest Nightly Build](https://github.com/ColoradoStateFSAE/CFD-Tools/releases/tag/nightly-latest)**

| File | Use |
|------|-----|
| `RamRacingCFD-setup-*.exe` | Full Windows installer — Start Menu entry, sets `AWP_ROOT261` automatically |
| `RamRacingCFD-portable-*.zip` | Portable — unzip anywhere, run `RamRacingCFD.exe` |
| `app-nightly-*.tar.gz` | Source archive |

Python is **not** required — the runtime and all dependencies are bundled. Ansys Fluent 2026 R1 must be installed and licensed separately.

---

## CFD Automation Suite

A PyQt6 desktop application that automates the complete CFD pipeline defined in the Ram Racing Fluent Procedure document. Configure a simulation, queue it, and walk away — meshing, solving, post-processing export, and results extraction all run unattended.

### Pipeline

```
Geometry (.pmdb)
    ↓  Enhanced Watertight Meshing Workflow
Poly-Hexcore Volume Mesh  (~7M cells, ~90 min on 40 cores)
    ↓  4-Stage Solver Ramp-Up
Converged Solution
    ↓
    ├→ EnSight Gold export  (for ParaView)
    ├→ 26 Fluent report definitions
    └→ Results .txt  (forces, CoP, coefficients — all SI)
```

### What it does

- Imports `.pmdb` / `.dsco` geometry from Ansys Discovery
- Runs the **Enhanced Meshing Workflow** (2026 R1 attribute-based API)
- Applies Near / Mid / Far volume refinement boxes auto-sized from car dimensions
- Adds per-wheel BOI refinement boxes around each MRF zone
- Configures boundary layers on all aero surfaces and the ground plane
- Sets up Wheel Moving Reference Frame (MRF) zones with auto-calculated RPM
- Executes a 4-ramp solver strategy — 1st order → 2nd order + PRESTO → full 2nd order → full send with curvature correction
- Creates **26 report definitions** covering total, per-element, and per-corner forces
- Derives Center of Pressure directly from Fluent pitching moment reports — no hand-measured geometry constants
- Auto-exports **EnSight Gold** format for ParaView visualisation
- Writes a timestamped results `.txt` in **pure SI units**
- Shows a **live ETA** during solving based on a rolling average of iteration times

### Supported simulation types

| Type | Description |
|------|-------------|
| **Half Car** | Symmetry plane at Z = 0, 2 wheel MRF zones. Forces doubled automatically. |
| **Full Car** | All 4 wheel MRF zones, no symmetry plane. |
| **Front Wing Only** | Isolated element study, no wheels. |
| **Rear Wing Only** | Isolated element study, no wheels. |
| **Quarter Model** | Two symmetry planes. |
| **Turning** | Full car at yaw with asymmetric wheel RPMs for cornering analysis. |

### Platform requirements

| | Requirement |
|---|---|
| **OS** | Rocky Linux 8.x (primary HPC) · Windows 10/11 |
| **Python** | 3.12 |
| **Ansys** | Fluent 2026 R1 (v261) licensed and installed |
| **PyFluent** | ansys-fluent-core ≥ 0.39 |
| **Env var** | `AWP_ROOT261` pointing at the Ansys install |

---

## Setup

### Rocky Linux (HPC)

```bash
python3.12 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install PyQt6 --only-binary=:all:
pip install ansys-fluent-core
pip install pyinstaller          # only needed to build the executable

export AWP_ROOT261=/home/<user>/ansys_inc/v261
python main.py
```

> **No `python3.12` and no sudo?** Copy a working venv from another machine:
> `rsync -az user@host:~/CFD-Tools/.../.venv/ .venv/` then `python3 -m venv --upgrade .venv`

> **PyQt6 fails to build** with a `qmake` error? Use the prebuilt wheel: `pip install PyQt6 --only-binary=:all:`

### Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install PyQt6 --only-binary=:all:
pip install ansys-fluent-core

$env:AWP_ROOT261 = "C:\Program Files\ANSYS Inc\v261"
python main.py
```

### Running headless / over NoMachine

The GUI needs a display. Over SSH use X11 forwarding (`ssh -X`), or check that NoMachine set `$DISPLAY`:

```bash
echo $DISPLAY          # should print something like :1001
ls /tmp/.X11-unix/     # find the display number if it's empty
export DISPLAY=:1
```

If Qt reports `xcb-cursor0 ... not found`:

```bash
sudo dnf install xcb-util-cursor
```

---

## Building the executable

**PyInstaller must run before NSIS.** Running NSIS alone produces an installer containing only `.py` source files, which cannot run without Python.

```bash
# Linux
source .venv/bin/activate
pyinstaller --clean RamRacingCFD.spec
chmod +x dist/RamRacingCFD/RamRacingCFD
```

```powershell
# Windows — application bundle
.\.venv\Scripts\Activate.ps1
pyinstaller --clean RamRacingCFD.spec

# Windows — wrap the bundle in an installer
makensis installer.nsi        # → RamRacingCFD-Setup.exe
```

`dist/RamRacingCFD/` is fully self-contained — zip it and copy to any machine with Fluent installed.

**Sanity checks:** the bundle should be 50+ MB and the installer 20+ MB. Anything smaller means dependencies weren't collected. The CI workflow enforces both thresholds.

### Rocky Linux install script

```bash
sudo ./install.sh      # installs to /opt/RamRacingCFD, adds `ramracingcfd` to PATH
ramracingcfd
```

---

## Quick start

1. **Prepare geometry** in Ansys Discovery — car facing **−X**, watertight, exported as `.pmdb`
2. Click **＋ Add Simulation** → choose sim type → fill in the editor tabs
3. Set geometry file, output directory, vehicle speed, and process count
4. Click **▶ Start Queue** — progress and ETA update live in the log panel
5. Results `.txt` and the EnSight export land in your configured directories

### Skipping the mesh

Iterating on solver settings? Set the **Existing Mesh** field in the Meshing tab to a previously generated `.msh.h5`. The ~90 minute meshing pipeline is skipped and the solver launches directly. Leave it blank for a normal full run.

---

## Report Definitions

The suite creates **26 report definitions** in Fluent on every run.

### Totals

| Report | Quantity | Zones | Direction |
|--------|----------|-------|-----------|
| `fz` | Downforce | all car | 0, −1, 0 |
| `fx` | Drag | all car | 1, 0, 0 |
| `cl` | Lift coefficient | all car | — |
| `cd` | Drag coefficient | all car | — |

### Per-element

| Report | Zones |
|--------|-------|
| `fz_frontwing` / `fx_frontwing` | `frontwing` |
| `fz_rearwing` / `fx_rearwing` | `rearwing` |
| `fz_undertray` / `fx_undertray` | `undertray` |
| `fz_body` / `fx_body` | `chassis` |
| `fz_fw` / `fx_fw` | `fw`, `fwb` + front wheel MRF zones |
| `fz_rw` / `fx_rw` | `rw`, `rwb` + rear wheel MRF zones |
| `fz_frontsus` / `fx_frontsus` | `front-suspension` |
| `fz_rearsus` / `fx_rearsus` | `rear-suspension` |

### Moments

| Report | Quantity |
|--------|----------|
| `my_total` | Pitch moment about front axle, Z-axis |
| `mx_total` | Lateral moment about front axle, Y-axis |

Turning simulations add `yaw_moment` and `lateral_force`.

### Derived quantities

Computed post-solve from the reports above:

| Output | Formula | Unit |
|--------|---------|------|
| `SCz` | `fz / q` | m² |
| `SCx` | `fx / q` | m² |
| `copx` | `my_total / fz` | m from front axle |
| `copz` | `mx_total / fz` | m |
| `cop_pct_front` | `copx / wheelbase × 100` | % |
| `ld_ratio` | `\|fz\| / \|fx\|` | — |

where `q = ½ρV²` with ρ = 1.225 kg/m³.

---

## Units

**Everything is standard Ansys SI.** No imperial conversions anywhere in the pipeline.

| Quantity | Unit |
|----------|------|
| Force | Newtons [N] |
| Moment | Newton-metres [N·m] |
| Length | metres [m] |
| Speed | metres/second [m/s] |
| Pressure | Pascals [Pa] |
| Area | square metres [m²] |

The only exception is the **vehicle speed input field**, which accepts mph for convenience and converts to m/s immediately. The results file prints both (`17.88 m/s (40.0 mph)`).

---

## Results output

```
==================================================================
   Ram Racing Aerodynamics -- CFD Results Export
==================================================================

  Simulation  : Half Car Sim
  Type        : Half Car
  Speed       : 17.88 m/s  (40.0 mph)
  Exported    : 2026-07-27 15:05:36

----------------------------------------------------------------
  MESH QUALITY  (orthogonal quality)
----------------------------------------------------------------
  Verdict                                  PASS — min OQ 0.0647
  Min Orthogonal Quality                       0.0647
  Total Cell Count                          7,155,750

----------------------------------------------------------------
  DOWNFORCE [N]  x2 (half-car)
----------------------------------------------------------------
  Front Wing                                 632.500 N
  Rear Wing                                  841.200 N
  Undertray                                  524.800 N
  Front Wheel                                 88.100 N
  Rear Wheel                                  92.400 N
  Front Suspension                            14.200 N
  Rear Suspension                             15.900 N
  Body/Chassis                               102.300 N
  TOTAL Fz                                  2311.400 N

----------------------------------------------------------------
  CENTER OF PRESSURE
----------------------------------------------------------------
  CoP x (from front axle)                     0.7214 m
  Aero Balance -- Front                        45.81 %
  Aero Balance -- Rear                         54.19 %

----------------------------------------------------------------
  AERODYNAMIC COEFFICIENTS
----------------------------------------------------------------
  SCz  (= Fz / q)                             1.2340 m^2
  SCx  (= Fx / q)                             0.4180 m^2
  L/D Ratio                                    2.952
  Dynamic Pressure q                          195.42 Pa
```

---

## ParaView visualisation

Every simulation auto-exports EnSight Gold format to `<output_dir>/<sim_name>_ensight/`.

```
File → Open → <sim_name>.encas
```

**Recommended checks:**

| View | What it shows |
|------|---------------|
| Slice at Y = 0.1 m, colour by Cell Volume | Near/mid/far refinement box boundaries as visible cell size steps |
| Slice at Z = 0 (symmetry plane) | Boundary layers on wing and undertray surfaces |
| Slice at X = front axle | Wheel refinement box cross-section |
| Clip + zoom on a trailing edge | Individual boundary layer cells stacked on the surface |

If cell volume is uniform across the domain, the refinement boxes did not apply.

---

## Mesh validation

Beyond the automated quality check, verify resolution three ways:

**1. Cell count and quality** — logged automatically. Min orthogonal quality should exceed 0.10; the run warns below that.

**2. Zone face density** — aero zones (0.008 m sizing) should have far more faces per unit area than the chassis (0.256 m sizing). A ratio under 2× means local sizing didn't take effect.

**3. Grid convergence study** — the only way to truly confirm resolution is sufficient:

| Level | `surface_mesh_max` | `volume_mesh_max` | Approx cells |
|-------|-------------------|-------------------|--------------|
| Coarse | 0.512 | 0.512 | ~1.5 M |
| Medium | 0.256 | 0.256 | ~7 M |
| Fine | 0.128 | 0.128 | ~25 M |

Forces changing under 5% between medium and fine means medium is adequate. Over 10% between coarse and medium means coarse is too coarse.

---

## Geometry requirements

| Requirement | Details |
|-------------|---------|
| **File format** | `.pmdb` or `.dsco` — export from Discovery via Prepare → Export as PMDB |
| **Orientation** | Car faces **−X** — rotate 270° from SolidWorks default |
| **Watertight** | All holes filled, no gaps, geometry fully closed |
| **Named selections** | Must match the list below exactly |
| **Wheel MRF zones** | Cylindrical fluid volumes around each wheel |
| **No self-intersections** | Repair in SpaceClaim or Discovery — meshing will fail otherwise |

### Named selections

**Domain boundaries**

| Name | Type |
|------|------|
| `inlet` | Velocity inlet |
| `outlet` | Pressure outlet |
| `walls` | Far-field walls |
| `ground` | Moving wall |
| `symmetry` | Symmetry plane (half-car only) |

**Car surfaces**

| Name | Component |
|------|-----------|
| `frontwing` | Front wing |
| `rearwing` | Rear wing |
| `undertray` | Undertray / diffuser |
| `chassis` | Body / chassis |
| `fw`, `fwb` | Front wheel and wheel body |
| `rw`, `rwb` | Rear wheel and wheel body |
| `front-suspension` | Front suspension members |
| `rear-suspension` | Rear suspension members |

> `fw` / `fwb` / `rw` / `rwb` are **wheel** zones, not wing zones. The wings use `frontwing` and `rearwing` only.

---

## Wheel MRF setup

Wheel MRF creates a rotating fluid volume around each wheel — significantly more accurate than a rotating wall for open-wheel vehicles, since the rotating zone captures airflow jetting outward from the tyre.

| Zone name | Position | Rotation axis |
|-----------|----------|---------------|
| `mrf_flw` | Front left | axis_z = +1 |
| `mrf_frw` | Front right | axis_z = −1 |
| `mrf_rlw` | Rear left | axis_z = +1 |
| `mrf_rrw` | Rear right | axis_z = −1 |

Half-car simulations only need `mrf_frw` and `mrf_rrw`.

RPM is auto-calculated at solve time as `ω = v / r`. Set `rpm = 0` in the wheel editor to use auto-calculation; individual overrides take precedence.

See `utils/Wheel_MRF_Setup_Guide.pdf` for step-by-step Discovery instructions.

---

## Project structure

```
CFD-Automation-Suite-Source-Code/
├── main.py                      ← Entry point
├── requirements.txt
├── RamRacingCFD.spec            ← PyInstaller build spec
├── installer.nsi                ← NSIS installer (packages PyInstaller output)
├── install.sh / uninstall.sh    ← Rocky Linux installer
├── RamRacingCFD.rpm.spec        ← RPM package spec
│
├── core/
│   ├── runner.py                ← Meshing + solver automation, report defs, EnSight export
│   └── queue_manager.py         ← Thread-safe simulation queue
│
├── simtypes/
│   └── configs.py               ← Simulation type dataclasses + validation
│
├── gui/
│   ├── app.py                   ← Main window
│   ├── sim_editor.py            ← Tabbed simulation config dialog
│   ├── wheel_editor.py          ← Wheel MRF zone editor
│   ├── settings_dialog.py       ← Application settings
│   ├── resource_path.py         ← PyInstaller-aware path resolution
│   └── theme.py                 ← PyQt6 stylesheet
│
└── utils/
    ├── results_exporter.py      ← CoP calculation + SI results report
    └── Wheel_MRF_Setup_Guide.pdf
```

### Adding a new simulation type

1. Add a value to `SimType` in `simtypes/configs.py`
2. Create a dataclass subclassing `BaseSimConfig` with a `sim_type` property
3. Register it in `SIM_TYPE_REGISTRY`

It appears in the **Add Simulation** dialog automatically.

---

## Computer presets

| Machine | Processes | MPI | Approx mesh time |
|---------|-----------|-----|-----------------|
| ThreadRipper 2990WX | 40–50 | openmpi | ~90 min |
| Xeon Gold cluster | 60 | intel | ~60 min |
| Big Boi | 128–170 | default | ~40 min |

---

## MATLAB Scripts

Post-processing scripts predating the automation suite, kept as reference and cross-check tools. **Note:** these use imperial units (lbf, inches) while the automation suite uses SI — convert before comparing.

### `Aerobalancecode_actual.m`
Computes front/rear aero balance from per-element force and geometry inputs. Ported into `utils/results_exporter.py`.

### `copcode_actual.m`
Full CoP calculation including resultant force angle and pitching moment.

### `MatrixCOP.m`
Vectorised version accepting arrays — useful for sweep studies across multiple CFD runs.

### `localrefinementregion.m`
Prompts for car dimensions and prints Near/Mid/Far refinement box coordinates. Implemented automatically in `runner.py:compute_refinement_boxes()`.

### CoP equations

```
Fy   = Ff + Fr + Fu
Fx   = Fdr
Mz   = (Fr*(L+Lr)) + (Fu*Lu) + (Fdr*H) - (Ff*Lf)
x_cp = Mz / Fy

W_RD = ((Fu*Lu) + (Fr*(L+Lr)) + (Fdr*H) - (Ff*Lf)) / L
W_FD = ((Ff*(L+Lf)) + (Fu*(L-Lu)) - (Fr*Lr) - (Fdr*H)) / L
```

The automation suite instead derives CoP directly from Fluent moment reports, avoiding hand-measured lever arms entirely.

---

## Documentation

### `Ansys Fluent Procedure.pdf`

The canonical Ram Racing CFD procedure (Danny Shireman & Hayes Dodson, April 2025). Covers geometry preparation, coordinate conventions, the Watertight workflow, mesh sizing, the 4-stage solver ramp, wheel MRF setup, and report configuration.

The automation suite is a direct implementation of this document.

---

## Documents

External reference material — currently the **Ansys Fluent Workbench Tutorial Guide 2024 R2**, useful for understanding meshing workflow internals and troubleshooting mesh failures.

---

## Migration notes — 2025 R2 → 2026 R1

The meshing API changed substantially. Key differences:

| 2025 R2 (legacy) | 2026 R1 (enhanced) |
|------------------|--------------------|
| `workflow.InitializeWorkflow(WorkflowType="Watertight Geometry")` | `meshing.watertight()` |
| `tasks["Import Geometry"].Arguments = {...}` | `watertight.import_geometry.file_name.set_state(path)` |
| `task.Execute()` | `task()` |
| `task.AddChildAndUpdate()` | `task.add_child_and_update(defer_update=False)` |
| `AWP_ROOT252` | `AWP_ROOT261` |

The solver API is backward compatible — `solver.setup.*` still works, though `solver.settings.setup.*` is preferred and the short form now emits deprecation warnings (suppressed in `runner.py`).

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `NameError: name 'deque' is not defined` | Missing `from collections import deque` in `runner.py` |
| Installer produces a non-working app | NSIS ran without PyInstaller — build order matters |
| `SyntaxError: invalid decimal literal` in `.spec` | PowerShell pasted into the spec file; it must be pure Python |
| Forces all read 0.0 | Report names mismatch, or named selections missing from geometry |
| `qmake` error installing PyQt6 | Use `pip install PyQt6 --only-binary=:all:` |
| Qt platform plugin "xcb" not loadable | `sudo dnf install xcb-util-cursor`, check `$DISPLAY` |
| `UnicodeEncodeError` on Windows | Add `encoding="utf-8"` to `open()` calls |
| Mesh fails at volume mesh step | Refinement box task arguments — check zone names and BOI settings |

---

## License

See `Documentation/LICENSE.txt`.

---

## Contact

Open a GitHub Issue or contact the current Aero Sub-Team Lead.

**Aerodynamics Subteam — Ram Racing FSAE — Colorado State University**
