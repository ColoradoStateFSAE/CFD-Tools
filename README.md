<img width="207" height="233" alt="Ram Racing Logo" src="https://github.com/user-attachments/assets/0967733d-0662-43cc-ac3a-1226af33b587" />

# Ram Racing FSAE — Aero CFD Tools

A collection of aerodynamic simulation tools, automation software, MATLAB analysis scripts, and reference documentation maintained by the Ram Racing FSAE Aerodynamics Subteam.

---

## Repository Contents

| Directory | Description |
|-----------|-------------|
| [`CFD-Automation-Suite-Source-Code/`](#cfd-automation-suite) | Desktop GUI application — automates the full Fluent CFD pipeline |
| [`MATLAB-Scripts/`](#matlab-scripts) | Post-processing scripts for CoP, aero balance, and refinement box generation |
| [`Documentation/`](#documentation) | Ansys Fluent procedure document and team references |
| [`Documents/`](#documents) | External reference material (Fluent tutorial guides, etc.) |

---

## CFD Automation Suite

A PyQt6 desktop application that automates the complete CFD pipeline defined in the Ram Racing Fluent Procedure document. Configure a simulation, queue it, and walk away — meshing, solving, and results export all run unattended.

### What it does

```
Geometry (.pmdb) → Watertight Mesh → Poly-Hexcore Volume Mesh
    → 4-Stage Solver Ramp-Up → Force Extraction → CoP Calculation → Results .txt
```

- Imports `.pmdb` / `.dsco` geometry from Ansys Discovery
- Runs the Fluent 252 Watertight Geometry workflow automatically
- Applies Near / Mid / Far volume refinement boxes (auto-sized from car dimensions)
- Configures 6-layer boundary layers on all aero surfaces and ground
- Sets up Wheel Moving Reference Frame (MRF) zones with auto-calculated RPM
- Executes a 4-ramp solver strategy (1st order → 2nd order + PRESTO → full 2nd order → full send with curvature correction)
- Extracts per-element forces: front wing, rear wing, undertray individually
- Derives Center of Pressure directly from Fluent pitching moment reports — no hand-measured geometry constants required
- Exports a timestamped results `.txt` with downforce, drag, CoP %, SCz, SCx, and L/D

### Supported simulation types

| Type | Description |
|------|-------------|
| **Half Car** | Symmetry plane at Z = 0, 2 wheel MRF zones. Forces doubled automatically. |
| **Full Car** | All 4 wheel MRF zones, no symmetry plane. |
| **Front Wing Only** | Isolated element study, no wheels. |
| **Rear Wing Only** | Isolated element study, no wheels. |
| **Quarter Model** | Two symmetry planes. |
| **Turning** | Full car at a yaw angle with asymmetric wheel RPMs for cornering analysis. |

### Platform requirements

| | Requirement |
|---|---|
| **OS** | Rocky Linux 8.x (primary HPC) · Windows 10/11 |
| **Python** | 3.12 |
| **Ansys** | Fluent 2025 R2 (v252) licensed and installed |
| **PyFluent** | ansys-fluent-core 0.38.x |

### Setup — Rocky Linux (HPC)

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install PyQt6 --only-binary=:all:
pip install ansys-fluent-core==0.38.1
pip install pyinstaller   # only needed for building the executable

# Set Ansys environment variable
export AWP_ROOT252=/home/<user>/ansys_inc/v252

# Run
python main.py
```

> If `python3.12` is not available and you lack `sudo`: copy the `.venv` from another machine that already has it set up using `rsync -az user@host:~/CFD-Tools/.../.venv/ .venv/` then run `python3 -m venv --upgrade .venv`.

### Setup — Windows

```powershell
py -3.12 -m venv .venv
& ".\.venv\Scripts\Activate.ps1"

# Install pandas with --only-binary first (avoids Meson compile error)
pip install pandas --only-binary=:all:
pip install PyQt6 --only-binary=:all:
pip install ansys-fluent-core

python main.py
```

### Build standalone executable

```bash
# Build (run on the target OS — do not cross-compile)
pyinstaller --clean RamRacingCFD.spec

# Output: dist/RamRacingCFD/RamRacingCFD   (Linux)
#         dist/RamRacingCFD/RamRacingCFD.exe  (Windows)
```

The `dist/RamRacingCFD/` folder is fully self-contained. Copy it to any machine with Fluent installed and run it directly — no Python required.

For Rocky Linux, an `install.sh` is included that installs the bundle to `/opt/RamRacingCFD` and adds a launcher to `/usr/local/bin/ramracingcfd`:

```bash
sudo ./install.sh
ramracingcfd
```

### Quick start

1. **Prepare geometry** in Ansys Discovery — car facing **−X**, fully watertight, exported as `.pmdb`
2. Click **＋ Add Simulation** → choose sim type → fill in the editor tabs
3. Set geometry file, output directory, vehicle speed, and process count
4. Click **▶ Start Queue** — progress updates in real time in the log panel
5. Results `.txt` is written to your configured Results Export Dir when complete

### Using an existing mesh (skip meshing)

If you've already run meshing and just want to iterate on solver settings, set the **Existing Mesh** field in the Meshing tab to a previously generated `.msh.h5` file. The ~90 minute meshing pipeline will be skipped and the solver will launch directly.

### Results export format

Each completed simulation writes a timestamped `.txt` report:

```
================================================================
   Ram Racing Aerodynamics -- CFD Results Export
================================================================

  Simulation  : Half Car Sim
  Type        : Half Car
  Speed       : 40.0 mph
  Exported    : 2026-05-08 15:05:36

----------------------------------------------------------------
  MESH QUALITY  (orthogonal quality, post-improvement)
----------------------------------------------------------------
  Verdict                          PASS — min OQ 0.0647 ≥ 0.10
  Min Orthogonal Quality                              0.0647
  ...

----------------------------------------------------------------
  DOWNFORCE (lbf)  x2 (half-car)
----------------------------------------------------------------
  Front Wing                                        142.500 lbf
  Rear Wing                                         189.200 lbf
  Undertray                                         118.000 lbf
  TOTAL Downforce                                   449.700 lbf
  ...

----------------------------------------------------------------
  CENTER OF PRESSURE  (derived from simulation moments)
----------------------------------------------------------------
  CoP from front axle                                28.400 in
  Aero Balance -- Rear                               54.19 %
  Aero Balance -- Front                              45.81 %
  ...
```

### Computer presets

| Machine | Processes | MPI Type | Approx mesh time |
|---------|-----------|----------|-----------------|
| ThreadRipper 2990WX | 40–50 | openmpi | ~90 min |
| Xeon Gold cluster | 60 | intel | ~60 min |
| Big Boi | 128–170 | default | ~40 min |

### Project structure

```
CFD-Automation-Suite-Source-Code/
├── main.py                      ← Entry point
├── requirements.txt
├── RamRacingCFD.spec            ← PyInstaller build spec
├── install.sh                   ← Rocky Linux installer
├── RamRacingCFD.rpm.spec        ← RPM package spec
│
├── core/
│   ├── runner.py                ← PyFluent meshing + solver automation
│   └── queue_manager.py         ← Thread-safe simulation queue
│
├── simtypes/
│   └── configs.py               ← Simulation type dataclasses + validation
│
├── gui/
│   ├── app.py                   ← Main window
│   ├── sim_editor.py            ← Simulation config dialog (tabbed)
│   ├── wheel_editor.py          ← Wheel MRF zone editor
│   ├── settings_dialog.py       ← Application settings
│   └── theme.py                 ← PyQt6 stylesheet
│
└── utils/
    ├── results_exporter.py      ← CoP calculation + .txt report writer
    └── Wheel_MRF_Setup_Guide.pdf
```

### Adding a new simulation type

1. Add a value to `SimType` in `simtypes/configs.py`
2. Create a dataclass subclassing `BaseSimConfig` with `@property def sim_type`
3. Register it in `SIM_TYPE_REGISTRY`

It will appear in the **Add Simulation** dialog automatically with no other changes needed.

---

## MATLAB Scripts

Post-processing scripts used to analyse Fluent results and compute aero balance metrics. These predate the automation suite and are kept as reference / cross-check tools.

### `Aerobalancecode_actual.m`

Computes front/rear aero balance percentage from per-element force and geometry inputs.

```matlab
% Inputs (set at top of file):
L   = 62;     % Wheelbase [in]
Lf  = 29.36;  % FW CoP to front axle [in]
Lr  = 8.1;    % RW CoP to rear axle [in]
Lu  = 42.93;  % Undertray CoP to front axle [in]
H   = 42.84;  % RW drag CoP height from ground [in]
Ff  = 59;     % Front wing downforce [lbf]
Fr  = 68;     % Rear wing downforce [lbf]
Fu  = 57;     % Undertray downforce [lbf]
Fdr = 27.4;   % Rear wing drag [lbf]

% Outputs:
% Percent_rear, Percent_front
```

The automation suite ports this logic directly into `utils/results_exporter.py`, so this script is primarily used for manual cross-checking of exported results.

### `copcode_actual.m`

Full CoP calculation including resultant force angle and pitching moment. Same geometry constants as `Aerobalancecode_actual.m` but also computes `x_cp`, `F_resultant`, and `theta`.

### `MatrixCOP.m`

Vectorised version of `copcode_actual.m` that accepts arrays of inputs — useful for sweep studies (e.g. front wing pitch angle sweep across multiple CFD runs). Input arrays for `Lf`, `Lr`, `Lu`, `Ff`, `Fr`, `Fu`, `Fdr` with a corresponding `List` of labels.

### `localrefinementregion.m`

Interactive script that prompts for car dimensions (L, W, H) and prints the Near / Mid / Far refinement box coordinates to use in Fluent. The automation suite implements this logic automatically in `runner.py:compute_refinement_boxes()`, but this script is useful for manually setting up refinement regions in the Fluent GUI.

### CoP equations (all scripts)

```
Fy  = Ff + Fr + Fu
Fx  = Fdr
Mz  = (Fr*(L+Lr)) + (Fu*Lu) + (Fdr*H) - (Ff*Lf)
x_cp = Mz / Fy               % CoP location from front axle [in]

W_RD = ((Fu*Lu) + (Fr*(L+Lr)) + (Fdr*H) - (Ff*Lf)) / L
W_FD = ((Ff*(L+Lf)) + (Fu*(L-Lu)) - (Fr*Lr) - (Fdr*H)) / L

% Rear  = W_RD / (W_FD + W_RD)
% Front = W_FD / (W_FD + W_RD)
```

---

## Documentation

### `Ansys Fluent Procedure.pdf`

The canonical Ram Racing CFD procedure document (Danny Shireman & Hayes Dodson, April 2025). Covers:

- Geometry preparation requirements in Ansys Discovery
- Coordinate system and orientation conventions (car faces −X)
- Watertight Geometry workflow step-by-step
- Recommended mesh sizing parameters
- Solver ramp-up strategy (the 4-stage approach the automation suite implements)
- Wheel MRF setup instructions
- Force and moment report configuration

This document is the primary reference for any CFD work on the team. The automation suite is a direct implementation of the procedure described here.

---

## Documents

External reference material. Currently contains:

- **Ansys Fluent Workbench Tutorial Guide 2024 R2** — official Ansys documentation for Fluent meshing workflows and solver setup. Useful for understanding the Watertight Geometry workflow internals and troubleshooting mesh failures.

---

## Geometry Requirements

Before running any simulation, geometry must meet these requirements:

| Requirement | Details |
|-------------|---------|
| **File format** | `.pmdb` or `.dsco` only — export from Ansys Discovery via Prepare → Export as PMDB |
| **Orientation** | Car faces **−X direction** — rotate 270° from SolidWorks default |
| **Watertight** | All holes filled, no gaps, geometry fully closed |
| **Named selections** | Inlet, outlet, symmetry, ground, and all aero zone labels must match the Fluent zone name expectations |
| **Wheel MRF zones** | Cylindrical fluid volumes around each wheel, named `mrf_flw`, `mrf_frw`, `mrf_rlw`, `mrf_rrw` |
| **No self-intersections** | Geometry with self-intersecting faces may fail surface meshing — repair in SpaceClaim or Discovery |

The tool validates the file extension on load and rejects anything other than `.pmdb` / `.dsco`.

---

## Wheel MRF Setup

Wheel MRF creates a rotating fluid volume around each wheel, which is significantly more accurate than a simple rotating wall for open-wheel vehicles — the rotating zone captures the airflow jetting outward from the tyre.

**Zone naming — must match Discovery named selections exactly:**

| Zone name | Position | Rotation axis |
|-----------|----------|---------------|
| `mrf_flw` | Front left | axis_z = +1 |
| `mrf_frw` | Front right | axis_z = −1 |
| `mrf_rlw` | Rear left | axis_z = +1 |
| `mrf_rrw` | Rear right | axis_z = −1 |

For half-car simulations only `mrf_frw` and `mrf_rrw` are needed.

RPM is auto-calculated at solve time: `ω = v_car [m/s] / r_wheel [m]`. Set `rpm = 0` in the wheel editor to use auto-calculation. Individual RPM overrides take precedence.

See `CFD-Automation-Suite-Source-Code/utils/Wheel_MRF_Setup_Guide.pdf` for full step-by-step Discovery instructions.

---

## Known Issues and Active Development

See the GitHub Issues tab for the current bug tracker. Major known issues as of v0.0.2:

- **Force extraction** (Issue #1): `report-forces` scheme eval approach being validated — forces may read as 0.0 on first run after a fresh Fluent session
- **Refinement boxes** (Issue #9): Near/Mid/Far BOI task argument keys are being verified against Fluent 252 — boxes may not apply correctly in the current version
- **Turning sim yaw** (Issue #11): Auto-yaw formula corrected to `atan(v²/(g·R))` in v0.0.2

---

## License

See `LICENSE` for details.

---

## Contact

For questions, issues, or feature requests, open a GitHub Issue or contact the current Aero Sub-Team Lead.

**Aerodynamics Subteam — Ram Racing FSAE**
