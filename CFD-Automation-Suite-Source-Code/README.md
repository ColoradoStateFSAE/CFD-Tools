# Ram Racing CFD Automation Tool

**Aerodynamic Subteam · Fluent 2024R2 · PyFluent · PyQt6**

---

## What This Does

A desktop application that automates the full CFD pipeline described in the Ram Racing Fluent Procedure doc (Danny Shireman & Hayes Dodson, 4/30/2025). Drop in a geometry file, configure your run, queue it up, and walk away.

**Pipeline:**
- Geometry import (`.pmdb` or `.dsco` only) → watertight geometry workflow
- Local refinement boxes (Near / Mid / Far, auto-sized from car dimensions)
- Boundary layer setup → volume mesh (poly-hexcore)
- 4-stage solver ramp-up (1st order → 2nd+Presto → Full 2nd → Full Send with CC)
- Wheel Moving Reference Frame — auto-calculates RPM, sets up rotating fluid zones
- Per-element force extraction (front wing / rear wing / undertray individually)
- Center-of-Pressure % calculation (ported directly from MATLAB script)
- Clean results `.txt` export with downforce, drag, CoP %, SCz, SCx, L/D

---

## Supported Simulation Types

| Type | Description |
|------|-------------|
| **Half Car** | Symmetry at Z=0, 2 wheel MRF zones. Forces doubled automatically. |
| **Full Car** | All 4 wheel MRF zones, no symmetry. |
| **Front Wing Only** | Isolated element study, no wheels. |
| **Rear Wing Only** | Isolated element study, no wheels. |
| **Quarter Model** | Two symmetry planes. |

---

## Setup

### Prerequisites

- **Python 3.12** (3.13 works; avoid 3.14 — PyFluent compatibility issues)
- Ansys Fluent 2024R2 installed and licensed on the machine running simulations
- Windows 10/11 or Linux

### Install

```powershell
# Create and activate a venv (PowerShell)
py -3.12 -m venv .venv
& ".\.venv\Scripts\Activate.ps1"

# Install dependencies — use --only-binary to avoid C compilation issues
pip install PyQt6 --only-binary=:all:
pip install pandas --only-binary=:all:
pip install ansys-fluent-core
pip install reportlab
```

> **Note on pandas:** `ansys-fluent-core` depends on pandas. On Windows, always install pandas with `--only-binary=:all:` first, otherwise pip tries to compile it from source and fails with a Meson/vswhere error.

### Run

```powershell
python main.py
```

---

## Build Standalone Executable

```powershell
pip install pyinstaller
pyinstaller RamRacingCFD.spec
# Output: dist/RamRacingCFD/RamRacingCFD.exe  (Windows)
#         dist/RamRacingCFD/RamRacingCFD       (Linux)
```

The `dist/RamRacingCFD/` folder is self-contained — copy the whole folder to any machine that has Fluent installed.

---

## Usage Guide

### 1. Prepare Geometry in Ansys Discovery

Before using this tool, your geometry must be ready:

1. All holes filled, bodies merged, geometry watertight
2. Car facing the **−X direction** (rotate 270° from SolidWorks orientation)
3. MRF cylinder zones created around each wheel and named correctly (see Wheel MRF section)
4. Export as **PMDB**: `Prepare tab → Export → Export as PMDB`

Only `.pmdb` and `.dsco` files are accepted. STEP files will be rejected.

---

### 2. Add a Simulation

Click **＋ Add Simulation** → choose a simulation type → fill in the editor tabs.

#### General Tab
- **Sim name** and **vehicle speed**
- **Geometry File** — browse for your `.pmdb` or `.dsco` (other file types are blocked)
- **Sim Output Dir** — where Fluent saves `.cas.h5` mesh and case files
- **Results Export Dir** — where the finished results `.txt` report is written (can be different from sim output)
- **Processes / MPI Type / Double Precision** — see Computer Presets table below
- **Car dimensions L/W/H** — used to auto-size the Near/Mid/Far refinement boxes

#### Meshing Tab
- Surface mesh min/max sizes
- Volume mesh min/max sizes
- Boundary layer count, first cell height, transition ratio

#### Ramp-Up Tab
- Iteration counts for each of the 4 solver stages
- Curvature correction toggle (Ramp 3 / Full Send only)
- Production limiter toggle

#### Wheel MRF Tab *(only shown on simulations with wheels)*
- Enable/disable MRF entirely
- Add, edit, or remove individual wheel zones
- Each wheel: name, Fluent zone name, rotation center XYZ, rotation axis XYZ, wheel radius
- **Set RPM to 0** for auto-calculation: `RPM = (v_car [m/s] / r_wheel [m]) / (2π) × 60`

#### CoP / Aero Balance Tab
- Set the five geometry constants used in the Center-of-Pressure equations:
  - `L` — wheelbase [in]
  - `Lf` — distance from front wing CoP to front axle [in]
  - `Lr` — distance from rear wing CoP to rear axle [in]
  - `Lu` — distance from undertray CoP to front axle [in]
  - `H` — rear wing drag CoP height from ground [in]
- These are applied after each sim to calculate front/rear aero balance %

---

### 3. Queue Management

- Jobs run one at a time sequentially
- **▲ / ▼** to reorder queued jobs
- **✕ Cancel** removes a queued job (running jobs cannot be interrupted)
- **✎ Edit** or **double-click** to modify a queued job before it starts

---

### 4. Monitor Progress

Click any job in the queue list to see:
- Per-element results (front wing / rear wing / undertray downforce individually)
- Total downforce, total drag, aero system drag, L/D ratio
- Path to the exported results `.txt` file
- Progress bar and current step description
- Full error traceback if it failed

The **Log** tab shows all PyFluent output in real time.

---

## Results Export

After each simulation completes, a timestamped `.txt` file is written to your configured **Results Export Dir**. It contains:

| Section | Fields |
|---------|--------|
| **Downforce** | Front wing, rear wing, undertray (individually), total |
| **Drag** | Total car drag, aero system drag (FW+RW+UT), rear wing drag |
| **Center of Pressure** | CoP location from front axle [in], % rear, % front, resultant force, angle |
| **Aero Coefficients** | SCz (downforce coeff), SCx (drag coeff), L/D ratio, reference area |
| **Additional Zones** | Any extra user-defined zones |
| **Equation Reference** | Full CoP equation listing with your geometry constants |

> Half-car simulations: all forces are automatically doubled (×2) before export.

---

## CoP Equations (Ported from MATLAB)

```
Fy   = Ff + Fr + Fu
Fx   = Fdr
Mz   = (Fr*(L+Lr)) + (Fu*Lu) + (Fdr*H) - (Ff*Lf)
x_cp = Mz / Fy

W_RD = ((Fu*Lu) + (Fr*(L+Lr)) + (Fdr*H) - (Ff*Lf)) / L
W_FD = ((Ff*(L+Lf)) + (Fu*(L-Lu)) - (Fr*Lr) - (Fdr*H)) / L

% Rear  = W_RD / (W_FD + W_RD)
% Front = W_FD / (W_FD + W_RD)
```

Where `Ff` = front wing downforce, `Fr` = rear wing downforce, `Fu` = undertray downforce, `Fdr` = rear wing drag — all in lbf. Geometry constants in inches.

---

## Wheel MRF — How It Works

MRF creates a rotating **fluid volume** around each wheel rather than just spinning the wheel surface. This is significantly more accurate for open-wheel vehicles because the rotating zone captures the airflow jetting outward from the wheel.

The tool automatically:
1. Creates a local refinement box around each wheel zone during meshing
2. Assigns each cell zone as a Moving Reference Frame in the solver
3. Calculates rotation speed from `ω = v_car / r_wheel`
4. Sets rotation axis direction (±Z per wheel, configurable)

**Required zone naming — must exactly match Discovery named selections:**

| Discovery Name | Position | Rotation Axis |
|----------------|----------|---------------|
| `mrf_flw` | Front Left Wheel | axis_z = +1 |
| `mrf_frw` | Front Right Wheel | axis_z = −1 |
| `mrf_rlw` | Rear Left Wheel | axis_z = +1 |
| `mrf_rrw` | Rear Right Wheel | axis_z = −1 |

For half-car simulations, only `mrf_frw` and `mrf_rrw` are needed.

**See `utils/Wheel_MRF_Setup_Guide.pdf`** for full step-by-step instructions on creating these zones in Discovery.

---

## Computer Presets

| Machine | Processes | MPI Type |
|---------|-----------|----------|
| ThreadRipper | 40–50 | openmpi |
| Xeon Gold | 60 | intel |
| Big Boi | 128–170 | default |

Set these in the **General** tab of the sim editor.

---

## Project Structure

```
fluent_pyqt/
├── main.py                      # Entry point — run this
├── requirements.txt
├── RamRacingCFD.spec            # PyInstaller build spec
│
├── core/
│   ├── runner.py                # PyFluent meshing + solver automation
│   └── queue_manager.py        # Thread-safe simulation queue
│
├── simtypes/
│   └── configs.py              # Simulation type dataclasses + CoP geometry
│
├── gui/
│   ├── theme.py                # Global PyQt6 stylesheet + color palette
│   ├── app.py                  # Main window (QMainWindow)
│   ├── sim_editor.py           # Sim config dialog (5 tabs)
│   └── wheel_editor.py        # Wheel MRF zone editor dialog
│
└── utils/
    ├── results_exporter.py     # CoP calc + .txt report writer
    ├── generate_mrf_guide.py   # Script that generates the PDF guide
    └── Wheel_MRF_Setup_Guide.pdf
```

---

## Adding a New Simulation Type

1. Open `simtypes/configs.py`
2. Add a value to the `SimType` enum:
   ```python
   class SimType(Enum):
       ...
       DOWNFORCE_TUNNEL = "Downforce Tunnel"
   ```
3. Create a dataclass inheriting `BaseSimConfig`:
   ```python
   @dataclass
   class DownforceTunnelConfig(BaseSimConfig):
       name: str = "Downforce Tunnel Sim"
       use_wheel_mrf: bool = False

       @property
       def sim_type(self) -> SimType:
           return SimType.DOWNFORCE_TUNNEL
   ```
4. Register it in `SIM_TYPE_REGISTRY`:
   ```python
   SIM_TYPE_REGISTRY = {
       ...
       SimType.DOWNFORCE_TUNNEL: DownforceTunnelConfig,
   }
   ```
5. Done — it will appear in the **Add Simulation** dialog automatically, no other changes needed.

---

## Important Notes

- **Geometry must be `.pmdb` or `.dsco`** — the tool validates the file extension on load and will reject anything else.
- **Half-car forces are doubled automatically** — the ×2 multiplier is applied to all reported values and the exported `.txt` file.
- **Geometry must be fully watertight** before importing. Fill all holes in Discovery first.
- **Car must face −X direction** — rotate 270° in Discovery as per the procedure doc. Required for correct projected area and force direction.
- **MRF cylinder zones must not intersect** any other body. Leave at least 5mm clearance from wheels and bodywork.
- **Results Export Dir and Sim Output Dir are independent** — you can point results to a shared team folder and keep `.cas.h5` files local.
