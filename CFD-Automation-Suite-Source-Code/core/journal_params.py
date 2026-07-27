"""
Journal parameter resolution.

Builds the {{TOKEN}} -> value map that core.journal_runner substitutes into a
recorded Fluent journal before executing it. See journals/PLACEHOLDERS.md for
the authoritative token list.

This module deliberately imports nothing from ansys.fluent, so the token values
can be computed, printed and tested without launching Fluent:

    python -m core.journal_params --sim-type half_car

Coordinate convention (Fluent Procedure doc):
    +X  toward the rear of the car = flow direction
    +Y  up
    +Z  driver's left  ->  half car occupies z >= 0
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

log = logging.getLogger("journal_params")

MPH_TO_MS = 0.44704


# ---------------------------------------------------------------------------
# Simulation type -> journal folder name
# ---------------------------------------------------------------------------

def sim_type_key(sim_type) -> str:
    """
    Folder name under journals/ for a SimType.

        SimType.HALF_CAR        -> "half_car"
        SimType.FRONT_WING_ONLY -> "front_wing"

    Derived from the enum member name so adding a SimType needs no edit here,
    with two aliases to keep the folder names short.
    """
    aliases = {
        "FRONT_WING_ONLY": "front_wing",
        "REAR_WING_ONLY":  "rear_wing",
    }
    name = getattr(sim_type, "name", str(sim_type))
    return aliases.get(name, name.lower())


def all_sim_type_keys() -> List[str]:
    """Every journal folder name the suite expects, from the SimType enum."""
    from simtypes.configs import SimType
    return [sim_type_key(t) for t in SimType]


# ---------------------------------------------------------------------------
# Named selections
# ---------------------------------------------------------------------------

AERO_LABELS      = ["frontwing", "rearwing", "undertray"]
BODY_LABELS      = ["chassis", "sidepod"]
FRONT_SUS_LABELS = ["front-suspension"]
REAR_SUS_LABELS  = ["rear-suspension"]
DOMAIN_LABELS    = ["inlet", "outlet", "walls", "ground", "symmetry"]


def wheel_labels(half_sym: bool) -> Dict[str, List[str]]:
    """
    Wheel and wheel-block labels for the geometry type.

    Half car is the driver's left side (+Z), so it carries one wheel per axle
    and the labels drop the left/right prefix.
    """
    if half_sym:
        return {"front": ["fw", "fwb"], "rear": ["rw", "rwb"]}
    return {
        "front": ["flw", "frw", "flwb", "frwb"],
        "rear":  ["rlw", "rrw", "rlwb", "rrwb"],
    }


def all_wheel_labels(half_sym: bool) -> List[str]:
    w = wheel_labels(half_sym)
    return w["front"] + w["rear"]


def car_surface_labels(half_sym: bool) -> List[str]:
    """Every label making up the car — used for projected area and reports."""
    return (AERO_LABELS + BODY_LABELS
            + FRONT_SUS_LABELS + REAR_SUS_LABELS
            + all_wheel_labels(half_sym))


# ---------------------------------------------------------------------------
# Refinement boxes -- Tables 1-3 of the Fluent Procedure doc
# ---------------------------------------------------------------------------

def compute_refinement_boxes(L: float, W: float, H: float,
                             half_sym: bool = False) -> Dict[str, dict]:
    """
    Near / Mid / Far refinement box bounds in metres.

    Same formulas as MATLAB-Scripts/localrefinementregion.m:

        Near  0.032   X -(L)     to 3L    Y 0 to H+L/3    Z -(W+H/2)  to W+H/2
        Mid   0.064   X -(1.25L) to 5L    Y 0 to H+2L/3   Z -(W+H)    to W+H
        Far   0.128   X -(1.5L)  to 7L    Y 0 to 2L       Z -(W+3H/2) to W+3H/2

    Half car sets every z_min to 0, since the model lives at z >= 0.
    """
    def z_min(extent: float) -> float:
        return 0.0 if half_sym else -extent

    near = {
        "size":  0.032,
        "x_min": -L,          "x_max": 3.0 * L,
        "y_min": 0.0,         "y_max": H + L / 3.0,
        "z_min": z_min(W + H / 2.0),  "z_max": W + H / 2.0,
    }
    mid = {
        "size":  0.064,
        "x_min": -1.25 * L,   "x_max": 5.0 * L,
        "y_min": 0.0,         "y_max": H + 2.0 * L / 3.0,
        "z_min": z_min(W + H),        "z_max": W + H,
    }
    far = {
        "size":  0.128,
        "x_min": -1.5 * L,    "x_max": 7.0 * L,
        "y_min": 0.0,         "y_max": 2.0 * L,
        "z_min": z_min(W + 1.5 * H),  "z_max": W + 1.5 * H,
    }
    return {"near": near, "mid": mid, "far": far}


# ---------------------------------------------------------------------------
# Wheel MRF
# ---------------------------------------------------------------------------

def wheel_mrf_spec(config, speed_ms: float) -> List[dict]:
    """
    One dict per wheel MRF zone, ready to loop over inside a journal:

        {'name': 'FRW', 'zone': 'mrf_frw', 'origin': [x, y, z],
         'axis': [0, 0, -1], 'radius': 0.203, 'omega': 88.09, 'rpm': 841.2}

    omega is rad/s, computed as v / r unless an rpm override is set on the
    wheel. Turning simulations set different rpm per wheel, and that override
    is respected here.
    """
    spec = []
    for w in getattr(config, "wheel_mrf_zones", []) or []:
        radius = float(getattr(w, "wheel_radius", 0.203)) or 0.203
        rpm    = float(getattr(w, "rpm", 0.0) or 0.0)
        if rpm > 0:
            omega = rpm * 2.0 * 3.141592653589793 / 60.0
        else:
            omega = speed_ms / radius
            rpm   = omega * 60.0 / (2.0 * 3.141592653589793)
        spec.append({
            "name":   w.name,
            "zone":   w.zone_name,
            "origin": [float(w.center_x), float(w.center_y), float(w.center_z)],
            "axis":   [float(w.axis_x),   float(w.axis_y),   float(w.axis_z)],
            "radius": radius,
            "omega":  round(omega, 4),
            "rpm":    round(rpm, 2),
        })
    return spec


# ---------------------------------------------------------------------------
# Token map
# ---------------------------------------------------------------------------

def build(config, mesh_file: str = "") -> Dict[str, Any]:
    """
    Resolve every {{TOKEN}} for one simulation.

    `mesh_file` is passed by the runner once known; when empty it defaults to
    <output_dir>/mesh.msh.h5.
    """
    from simtypes.configs import SimType

    half_sym = bool(getattr(config, "is_half_symmetry", False))
    speed_ms = float(config.vehicle_speed_mph) * MPH_TO_MS
    out_dir  = (config.output_dir or "").rstrip("/\\")
    res_dir  = (config.results_dir or out_dir).rstrip("/\\")
    mesh_file = mesh_file or os.path.join(out_dir, "mesh.msh.h5")

    boxes  = compute_refinement_boxes(
        config.car_length_m, config.car_width_m, config.car_height_m, half_sym
    )
    wheels = wheel_labels(half_sym)

    tokens: Dict[str, Any] = {
        # ── Paths ────────────────────────────────────────────────────────
        "GEOMETRY_PATH": config.geometry_path,
        "MESH_FILE":     mesh_file,
        "OUTPUT_DIR":    out_dir,
        "RESULTS_DIR":   res_dir,
        "CASE_PREFIX":   os.path.join(out_dir, config.name),
        "ENSIGHT_DIR":   os.path.join(out_dir, f"{config.name}_ensight"),
        "SIM_NAME":      config.name,

        # ── Car dimensions ───────────────────────────────────────────────
        "CAR_LENGTH":  float(config.car_length_m),
        "CAR_WIDTH":   float(config.car_width_m),
        "CAR_HEIGHT":  float(config.car_height_m),
        "WHEELBASE":   float(getattr(config, "wheelbase_m", 1.575)),
        "IS_HALF_CAR": half_sym,

        # ── Labels ───────────────────────────────────────────────────────
        "AERO_LABELS":        list(AERO_LABELS),
        "BODY_LABELS":        list(BODY_LABELS),
        "SUS_LABELS_FRONT":   list(FRONT_SUS_LABELS),
        "SUS_LABELS_REAR":    list(REAR_SUS_LABELS),
        "WHEEL_LABELS_FRONT": wheels["front"],
        "WHEEL_LABELS_REAR":  wheels["rear"],
        "WHEEL_LABELS_ALL":   all_wheel_labels(half_sym),
        "CAR_LABELS":         car_surface_labels(half_sym),
        "VEHICLE_ZONES":      car_surface_labels(half_sym),
        "STUFF_LABELS":       BODY_LABELS + FRONT_SUS_LABELS + REAR_SUS_LABELS,
        "BL_ZONES":           AERO_LABELS + all_wheel_labels(half_sym) + ["ground"],

        # ── Mesh sizing ──────────────────────────────────────────────────
        "SURFACE_MIN":         float(config.surface_mesh_min),
        "SURFACE_MAX":         float(config.surface_mesh_max),
        "VOLUME_MIN":          float(config.volume_mesh_min),
        "VOLUME_MAX":          float(config.volume_mesh_max),
        "BL_LAYERS":           int(config.bl_num_layers),
        "BL_FIRST_HEIGHT":     float(config.bl_first_height),
        "BL_TRANSITION_RATIO": float(config.bl_transition_ratio),

        # ── Wheel refinement (Table 4 bounds are relative, so constant) ──
        "WHEEL_BOX_SIZE": 0.032,

        # ── Solver ───────────────────────────────────────────────────────
        "SPEED_MS":                 round(speed_ms, 6),
        "SPEED_MPH":                float(config.vehicle_speed_mph),
        "RAMP0_ITERS":              int(getattr(config, "ramp0_iters", 200)),
        "RAMP1_ITERS":              int(getattr(config, "ramp1_iters", 300)),
        "RAMP2_ITERS":              int(getattr(config, "ramp2_iters", 300)),
        "RAMP3_ITERS":              int(getattr(config, "ramp3_iters", 500)),
        "USE_CURVATURE_CORRECTION": bool(config.use_curvature_correction),
        "USE_PRODUCTION_LIMITER":   bool(config.use_production_limiter),
        "PROCESSES":                int(config.num_processes),

        # ── Wheel MRF ────────────────────────────────────────────────────
        "WHEEL_MRF": wheel_mrf_spec(config, speed_ms),
    }

    # ── Refinement boxes ─────────────────────────────────────────────────
    for prefix, box in (("NEAR", boxes["near"]),
                        ("MID",  boxes["mid"]),
                        ("FAR",  boxes["far"])):
        tokens[f"{prefix}_SIZE"] = box["size"]
        for axis in "xyz":
            for bound in ("min", "max"):
                key = f"{axis}_{bound}"
                tokens[f"{prefix}_{axis.upper()}_{bound.upper()}"] = \
                    round(box[key], 6)

    # ── Turning only ─────────────────────────────────────────────────────
    if getattr(config, "sim_type", None) == SimType.TURNING:
        import math
        yaw = float(config.effective_yaw_deg())
        rad = math.radians(yaw)
        tokens.update({
            "YAW_ANGLE_DEG": round(yaw, 4),
            "TURN_RADIUS":   float(getattr(config, "turn_radius_m", 0.0)),
            # Flow along +X, yawed about the vertical (+Y) axis
            "INLET_VECTOR":  [round(math.cos(rad), 6),
                              0.0,
                              round(math.sin(rad), 6)],
        })

    return tokens


def describe(tokens: Dict[str, Any]) -> str:
    """Human-readable dump of a token map, for logs and --check output."""
    lines = []
    for key in sorted(tokens):
        value = tokens[key]
        if isinstance(value, list) and value and isinstance(value[0], dict):
            lines.append(f"  {key:26s} {len(value)} entries")
            for entry in value:
                lines.append(f"  {'':26s}   {entry}")
        else:
            lines.append(f"  {key:26s} {value!r}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI -- inspect tokens without launching Fluent
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    from simtypes.configs import SimType, SIM_TYPE_REGISTRY

    parser = argparse.ArgumentParser(
        description="Print resolved journal tokens for a default config."
    )
    parser.add_argument("--sim-type", default="half_car",
                        help="journal folder name, e.g. half_car")
    args = parser.parse_args()

    match = next(
        (t for t in SimType if sim_type_key(t) == args.sim_type), None
    )
    if match is None:
        valid = ", ".join(all_sim_type_keys())
        raise SystemExit(f"Unknown sim type {args.sim_type!r}. Valid: {valid}")

    config = SIM_TYPE_REGISTRY[match]()
    config.name          = f"{args.sim_type} preview"
    config.geometry_path = "C:/example/car.pmdb"
    config.output_dir    = "C:/example/out"

    tokens = build(config)
    print(f"{match.value} — {len(tokens)} tokens\n")
    print(describe(tokens))


if __name__ == "__main__":
    _main()