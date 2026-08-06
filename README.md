<img width="207" height="233" alt="Ram Racing Logo" src="https://github.com/user-attachments/assets/0967733d-0662-43cc-ac3a-1226af33b587" />

# Ram Racing FSAE — Aero CFD Tools

A collection of aerodynamic simulation tools, automation software, MATLAB analysis scripts, and reference documentation maintained by the Ram Racing FSAE Aerodynamics Subteam.

---

## Repository Contents

| Directory | Description |
|-----------|-------------|
| [`CFD-Automation-Suite-Source-Code/`](#cfd-automation-suite) | Desktop GUI application — automates the full Fluent CFD pipeline |
| `MATLAB-Scripts/` | Post-processing scripts for CoP, aero balance, and refinement box generation |
| `Documentation/` | Ansys Fluent procedure document and team references |
| `Documents/` | External reference material (Fluent tutorial guides, etc.) |

---

## CFD Automation Suite

A PyQt6 desktop application that automates the complete CFD pipeline defined in the Ram Racing Fluent Procedure document. Configure a simulation, queue it, and walk away — meshing, solving, and results export all run unattended.

Every simulation type is one self-contained Python file. There's no shared base class, no inheritance, and no separate configuration format — the settings, the meshing sequence, the solver setup, and the report definitions for e.g. Half Car all live in `simtypes/half_car.py`, readable top to bottom.

**Target environment:** Ansys Fluent 2026 R1 (v261), PyFluent 0.39, Python 3.12.

### What it does

```
Geometry (.pmdb) → Watertight Mesh → Poly-Hexcore Volume Mesh
    → 3-Stage Solver Ramp-Up → Report Definitions → Results .txt + EnSight
```

- Imports `.pmdb` / `.dsco` geometry from Ansys Discovery
- Runs the Fluent 2026 R1 Enhanced Watertight Geometry workflow
- Applies Near / Mid / Far refinement boxes, auto-sized from car dimensions
- Wheels are modelled as **rotating walls** — no MRF, no separate cell zones
- Runs a 3-stage solver ramp (first order → second order + PRESTO → full second order with curvature correction)
- Creates 27 Fluent report definitions per run, including SCz/SCx/CoP as Fluent *expressions* — Ansys does that arithmetic, not Python
- Exports EnSight Gold for ParaView and a results `.txt`, both landing inside the run's own output folder
- Output is organized automatically as Project → Run → MAP #, matching the team's CFD Rolling Report naming
- Serves a live queue + log view over the network for checking progress from a phone on Tailscale

### Supported simulation types

| Type | Description |
|------|-------------|
| **Half Car** | Symmetry plane at z = 0. One wheel per axle (`fw`/`rw`). Forces doubled to represent the full car. |
| **Full Car** | No symmetry plane. All four wheels modelled individually (`flw`/`frw`/`rlw`/`rrw`). No doubling. |
| **Quarter Model** | One corner of the car (front or rear), bounded by two symmetry planes. Forces ×4. |

See `CFD-Automation-Suite-Source-Code/README.md` for setup and usage.

---

## MATLAB Scripts

Post-processing scripts for CoP and aero balance calculation, and a refinement-box coordinate generator that predates the Python suite's own `utils/refinement.py`. Kept for reference and for anyone doing hand calculations outside the suite.

---

## Documentation

The Ram Racing Fluent Procedure document — the source of truth for meshing sizing, boundary conditions, and solver settings. The automation suite is a direct implementation of this document; if the two ever disagree, the procedure document is what team practice actually follows and the suite should be brought in line with it.

---

## Documents

Reference material not specific to this repository — Ansys documentation, published papers, and similar.
