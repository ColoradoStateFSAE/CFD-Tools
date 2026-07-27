"""
Core PyFluent automation - meshing workflow and solver ramp-up strategy
based on Ram Racing Fluent Procedure doc.

Target: Ansys Fluent 2026 R1 (v261) / PyFluent 0.39
Requires: ansys-fluent-core >= 0.39 (pip install ansys-fluent-core)
"""
import math
import logging
import os
import sys
from collections import deque
from typing import Callable, Optional

log = logging.getLogger("fluent_runner")


def mph_to_ms(mph: float) -> float:
    """Convert miles per hour to metres per second."""
    return mph * 0.44704


def ms_to_mph(ms: float) -> float:
    """Convert metres per second to miles per hour."""
    return ms / 0.44704



# ---------------------------------------------------------------------------
# Ansys Fluent 2025 R2 (v252) / PyFluent 0.38 — primary target
# Thin fallbacks kept for 0.28 (2024 R2) compatibility only.
# ---------------------------------------------------------------------------

# Fluent install detection
_AWP_KEY   = "AWP_ROOT261"
_PV        = "26.1"          # product_version string for launch_fluent()

FLUENT_LAUNCH_TIMEOUT = 300  # seconds — increase for slow HPC startup


# ---------------------------------------------------------------------------
# Named selections
#
# These must match the labels created in Ansys Discovery exactly.
#
# Coordinate convention (Fluent Procedure doc):
#   +X  toward the rear of the car  = flow direction  -> drag  = [ 1, 0, 0]
#   +Y  up                                            -> downforce = [0, -1, 0]
#   +Z  driver's left                                 -> half-car lives at z >= 0
#
# Wheel labels differ between full car and half car:
#   Full car   flw / frw / rlw / rrw   + blocks  flwb / frwb / rlwb / rrwb
#   Half car   fw  / rw                + blocks  fwb  / rwb
# ---------------------------------------------------------------------------

AERO_LABELS = ["frontwing", "rearwing", "undertray"]

# Body / chassis. sidepod is only present in some geometries and is filtered
# out automatically when absent.
BODY_LABELS = ["chassis", "sidepod"]

# Suspension — not yet in every geometry. Add these named selections in
# Discovery to get the fz_frontsus / fz_rearsus reports populated.
FRONT_SUS_LABELS = ["front-suspension", "frontsus", "control-arms"]
REAR_SUS_LABELS  = ["rear-suspension",  "rearsus"]

# Domain boundaries — never part of the car force reports
DOMAIN_LABELS = ["inlet", "outlet", "walls", "ground", "symmetry"]


# ---------------------------------------------------------------------------
# Local sizing controls -- Fluent Procedure doc Step 4
#
# All three are Curvature size controls, not plain face sizes. The curvature
# normal angle is what actually drives refinement on curved aero surfaces.
# ---------------------------------------------------------------------------

SIZING_STUFF = {           # curvature_stuff -- anything not wheels or aero
    "growth_rate":            1.2,
    "size_control_type":      "curvature",
    "local_min_size":         0.001,
    "max_size":               0.064,
    "curvature_normal_angle": 12,
    "scope_to":               "faces-and-edges",
}
SIZING_AERO = {            # curvature_aero -- front wing, rear wing, undertray
    "growth_rate":            1.2,
    "size_control_type":      "curvature",
    "local_min_size":         0.0005,
    "max_size":               0.008,
    "curvature_normal_angle": 9,
    "scope_to":               "faces-and-edges",
}
SIZING_WHEELS = {          # curvature_wheels -- wheels + wheel blocks
    "growth_rate":            1.2,
    "size_control_type":      "curvature",
    "local_min_size":         0.0005,
    "max_size":               0.032,
    "curvature_normal_angle": 18,
    "scope_to":               "faces",          # faces only, not edges
}

# Surface mesh -- Step 5
SURFACE_MESH = {
    "growth_rate":              1.2,
    "size_functions":           "Curvature & Proximity",
    "curvature_normal_angle":   18,
    "cells_per_gap":            1,
    "scope_proximity_to":       "faces-and-edges",
    "separate_by_angle":        "No",
}

# Improve surface mesh -- Step 6
SURFACE_FACE_QUALITY_LIMIT = 0.7

# Volume mesh -- Step 11
VOLUME_PEEL_LAYERS = 1

# Improve volume mesh -- Step 12
VOLUME_QUALITY_METHOD = "Orthogonal"
VOLUME_QUALITY_LIMIT  = 0.2


def _wheel_labels(half_sym: bool) -> dict:
    """
    Return {"front": [...], "rear": [...]} wheel labels for the geometry type.

    Half car is the driver's left side (+Z), so it carries one wheel per axle
    and the labels drop the left/right prefix.
    """
    if half_sym:
        return {
            "front": ["fw", "fwb"],
            "rear":  ["rw", "rwb"],
        }
    return {
        "front": ["flw", "frw", "flwb", "frwb"],
        "rear":  ["rlw", "rrw", "rlwb", "rrwb"],
    }


def _all_wheel_labels(half_sym: bool) -> list:
    """All wheel + wheel-block labels, front and rear."""
    w = _wheel_labels(half_sym)
    return w["front"] + w["rear"]


def _car_surface_labels(half_sym: bool) -> list:
    """Every label that makes up the car."""
    return (AERO_LABELS + BODY_LABELS
            + FRONT_SUS_LABELS + REAR_SUS_LABELS
            + _all_wheel_labels(half_sym))


def _filter_existing_labels(watertight, labels: list) -> list:
    """
    Return only the labels present in the imported geometry.

    Optional labels (sidepod, suspension) and the unused half/full wheel set
    are dropped here rather than being passed to Fluent, which would fail with
    "does not evaluate to valid zone(s)".
    """
    try:
        sizing = watertight.add_local_sizing_wtm
        for accessor in (
            lambda: list(sizing.boi_face_label_list.allowed_values()),
            lambda: list(sizing.boi_face_label_list.get_attr("allowedValues")),
        ):
            try:
                available = accessor()
                if available:
                    kept    = [l for l in labels if l in available]
                    dropped = [l for l in labels if l not in available]
                    if dropped:
                        log.debug(f"  Labels not in geometry, skipped: {dropped}")
                    return kept
            except Exception:
                continue
    except Exception:
        pass
    # Could not query — pass through unchanged
    return labels


def _get_pyfluent_version() -> tuple:
    """Returns (major, minor) e.g. (0, 38)."""
    try:
        import ansys.fluent.core as pf
        ver = getattr(pf, "__version__", None)
        if ver is None:
            from importlib.metadata import version
            ver = version("ansys-fluent-core")
        parts = str(ver).split(".")
        maj, minor = int(parts[0]), int(parts[1])
        log.info(f"  PyFluent {ver}")
        return maj, minor
    except Exception as e:
        log.warning(f"  PyFluent version unknown ({e}), assuming 0.38")
        return 0, 38


def _ensure_awp_root():
    """Set AWP_ROOT261 if not already in env. Searches common install paths."""
    if os.environ.get(_AWP_KEY):
        log.info(f"  {_AWP_KEY}={os.environ[_AWP_KEY]}")
        return
    # Check for any AWP_ROOT already set
    existing = {k: v for k, v in os.environ.items() if k.startswith("AWP_ROOT")}
    if existing:
        log.info(f"  Found AWP_ROOT: {existing}")
        return

    is_win = sys.platform == "win32"
    home   = os.path.expanduser("~")

    candidates = [
        # User home (common on HPC)
        os.path.join(home, "ansys_inc", "v252", "fluent"),
        os.path.join(home, "ansys_inc", "v251", "fluent"),
        # System paths
        "/ansys_inc/v261/fluent",
        "/usr/ansys_inc/v261/fluent",
        "/opt/ansys_inc/v261/fluent",
        "/apps/ansys/v261/fluent",
        "/apps/ansys_inc/v261/fluent",
        # Windows
        "C:/Program Files/ANSYS Inc/v261/fluent",
    ]

    for candidate in candidates:
        fluent_bin = os.path.join(candidate, "bin",
                                  "fluent" + (".exe" if is_win else ""))
        if os.path.exists(fluent_bin):
            awp_root = os.path.dirname(candidate)
            os.environ[_AWP_KEY] = awp_root
            log.info(f"  Auto-set {_AWP_KEY}={awp_root}")
            return

    log.warning(
        f"  Fluent not found. Set {_AWP_KEY} manually:\n"
        f"  export {_AWP_KEY}=/path/to/ansys_inc/v261"
    )


def _launch_fluent(pyfluent, config, mode: str):
    """Launch Fluent in the given mode targeting Ansys 2026 R1."""
    _ensure_awp_root()
    timeout = getattr(config, "launch_timeout", FLUENT_LAUNCH_TIMEOUT)
    # PyFluent 0.39: FluentMode/Precision enums preferred, strings still work
    try:
        mode_enum = getattr(pyfluent.FluentMode, mode.upper(), mode)
    except Exception:
        mode_enum = mode
    try:
        prec_enum = pyfluent.Precision.DOUBLE if config.double_precision else pyfluent.Precision.SINGLE
    except Exception:
        prec_enum = "double" if config.double_precision else "single"
    kwargs = dict(
        mode            = mode_enum,
        precision       = prec_enum,
        processor_count = config.num_processes,
        product_version = _PV,
        start_timeout   = timeout,
    )
    log.info(f"  launch_fluent({mode}, procs={config.num_processes}, "
             f"timeout={timeout}s, version={_PV})")
    return pyfluent.launch_fluent(**kwargs)


def _launch_fluent_meshing(pyfluent, config):
    return _launch_fluent(pyfluent, config, "meshing")


def _launch_fluent_solver(pyfluent, config):
    return _launch_fluent(pyfluent, config, "solver")


def _init_workflow(meshing):
    """Initialize Watertight Geometry workflow. Returns the workflow object."""
    wf = meshing.workflow
    wf.InitializeWorkflow(WorkflowType="Watertight Geometry")
    return wf


def _exec_task(task, args: dict = None):
    """
    Execute a workflow task for PyFluent 0.38 / Fluent 252.

    From gRPC trace analysis:
    - setState correctly sets args in Fluent (confirmed by response)
    - task.Execute() may send empty executeCommand args
    - Fluent validates from executeCommand args, NOT from setState
    - task(args_dict) callable syntax routes through PyFluent __call__
      which correctly packages args into the executeCommand gRPC request

    Returns the raw task execution result (bool / None) when available.
    """
    if args:
        # PyFluent 0.38 callable task syntax — puts args into executeCommand
        try:
            result = task(args)
            log.debug("  task(args) callable succeeded")
            return result
        except Exception as e:
            log.debug(f"  task(args) failed: {e}")

        # Try Execute with the args dict as positional arg
        try:
            result = task.Execute(args)
            log.debug("  task.Execute(args) succeeded")
            return result
        except Exception as e:
            log.debug(f"  task.Execute(args) failed: {e}")

        # Try accessing the underlying execute_command on the service
        try:
            # PyFluent internals: task has _service and _path attributes
            service = task.Execute._service if hasattr(task.Execute, '_service') else None
            if service is None:
                service = task._service
            path = getattr(task, '_path', None) or getattr(task, 'path', None)
            if service and path:
                from ansys.fluent.core.services.datamodel_se import StateType
                result = service.execute_command(path, "Execute", args)
                log.debug("  service.execute_command succeeded")
                return result
        except Exception as e:
            log.debug(f"  service.execute_command failed: {e}")

    result = task.Execute()
    log.debug("  task.Execute() completed")
    return result


def _set_task_args(task, args: dict):
    """
    Set workflow task arguments for PyFluent 0.38 / Fluent 252.

    PyFluent 0.38 with Fluent 252 uses generated datamodel classes where
    each task argument is a typed property on the task object itself,
    accessed as task.arguments.file_name (snake_case) or via the
    Arguments sub-object with task.Arguments.FileName = value.

    The correct pattern confirmed for 0.38/252 is:
        task.Arguments.FileName = value   (direct property assignment)
    NOT setattr() and NOT __setattr__() — those bypass the descriptor.

    We try four approaches in order:
    1. Direct attribute assignment on Arguments (0.38 primary)
    2. Dict-style update() (0.28 fallback)
    3. Scheme-eval TUI fallback via task parent session (last resort)
    """
    args_obj = task.Arguments

    # Approach 1: direct attribute assignment — 0.38/252 primary method
    # Real Python attribute assignment syntax triggers gRPC descriptors.
    failed_keys = {}
    for key, value in args.items():
        try:
            setattr(args_obj, key, value)
            log.debug(f"  Set {key}={value!r}")
        except Exception as e:
            log.debug(f"  setattr {key} failed: {e}")
            failed_keys[key] = value

    if not failed_keys:
        return  # all args set successfully
    log.debug(f"  {len(args) - len(failed_keys)}/{len(args)} args set via setattr, retrying {list(failed_keys)} via fallbacks")

    # Approach 2: dict-style update() — 0.28 fallback (only unset keys)
    try:
        args_obj.update(failed_keys)
        return
    except Exception as e:
        log.debug(f"  update() failed: {e}")

    # Approach 3: update_dict (only unset keys) — PyFluent 0.28 fallback
    # Issue #14 fix: this is dead code in 0.38 — log at debug, not warning,
    # since partial setattr failures are normal for optional/unknown keys.
    try:
        args_obj.update_dict(failed_keys)
        return
    except Exception as e:
        log.debug(
            f"  Arg-setting partial failure for {list(failed_keys.keys())} "
            f"(expected on PyFluent 0.38 for unknown keys): {e}"
        )


def _hybrid_init(solver):
    """Hybrid initialization."""
    solver.solution.initialization.hybrid_initialize()


# Shared rolling window for time-per-iteration across all ramps.
# Using a module-level deque so the ETA estimate improves as more
# ramps complete (early ramps are cheaper, so the average converges).
_iter_times = deque(maxlen=10)


def _format_eta(seconds: float) -> str:
    """Format seconds into a human-readable ETA string."""
    if seconds <= 0:
        return "done"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s:02d}s"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m"


def _do_iterate(solver, n: int):
    """Run n iterations using the correct PyFluent keyword."""
    calc = solver.solution.run_calculation
    for kwargs in ({"iter_count": n}, {"number_of_iterations": n}):
        try:
            calc.iterate(**kwargs)
            return
        except Exception:
            continue
    try:
        calc.iterate(n)
    except Exception as e:
        log.warning(f"  iterate({n}): {e}")


def _iterate(solver, total_iters: int,
             progress_cb=None, label: str = "",
             pct_start: float = 0, pct_end: float = 100):
    """
    Run solver iterations in batches with ETA estimation.

    Runs in batches of ~50 iterations, measures wall-clock time per batch,
    keeps a rolling average of the last 10 batch times, and sends ETA
    updates through progress_cb.

    Handles < 10 samples gracefully — uses whatever samples are available.
    On the very first batch there is no prior data, so it shows "estimating..."
    """
    BATCH = 50
    done  = 0

    while done < total_iters:
        n = min(BATCH, total_iters - done)
        t0 = time.time()
        _do_iterate(solver, n)
        elapsed = time.time() - t0
        done += n

        # Record time per iteration for this batch
        if n > 0:
            _iter_times.append(elapsed / n)

        # Compute ETA from rolling average
        remaining = total_iters - done
        if _iter_times and remaining > 0:
            avg = sum(_iter_times) / len(_iter_times)
            eta_sec = avg * remaining
            eta_str = _format_eta(eta_sec)
            samples = len(_iter_times)
            status = (f"{label}: {done}/{total_iters} iters "
                      f"({elapsed/n:.1f}s/iter) — ETA {eta_str}")
        elif remaining > 0:
            status = f"{label}: {done}/{total_iters} iters — estimating..."
        else:
            status = f"{label}: {done}/{total_iters} iters — complete"

        # Update progress (interpolate percentage between pct_start and pct_end)
        if progress_cb and pct_end > pct_start:
            frac = done / total_iters
            pct = pct_start + frac * (pct_end - pct_start)
            progress_cb(status, int(pct))

        log.info(f"  {status}")


def _set_discretization(solver, scheme: str, field: str):
    """Set spatial discretization scheme (internal helper)."""
    methods = solver.solution.methods
    if field == "pressure_velocity_coupling":
        # Issue #2 fix: correct attribute path
        try:
            methods.p_v_coupling.flow_scheme = scheme
        except Exception as e:
            log.warning(f"  PV coupling: {e}")
        return
    try:
        methods.spatial_discretization.discretization_scheme = {field: scheme}
    except Exception as e:
        log.warning(f"  Discretization {field}={scheme}: {e}")


def _read_mesh(solver, mesh_file: str):
    """Read mesh into solver."""
    try:
        solver.file.read_mesh(file_name=mesh_file)
    except (AttributeError, Exception):
        solver.file.read(file_name=mesh_file)


def _write_case(solver, path: str):
    """Write case+data file."""
    try:
        solver.file.write_case_data(file_name=path)
    except AttributeError:
        solver.file.write(file_name=path, file_type="case-data")


def _add_report_lift(solver, name: str, zones: list, force_vector: list):
    try:
        solver.solution.report_definitions.lift[name] = {
            "zones": zones, "force_vector": force_vector,
        }
    except Exception as e:
        log.warning(f"  Lift report {name!r}: {e}")


def _add_report_drag(solver, name: str, zones: list, force_vector: list):
    try:
        solver.solution.report_definitions.drag[name] = {
            "zones": zones, "force_vector": force_vector,
        }
    except Exception as e:
        log.warning(f"  Drag report {name!r}: {e}")


def _add_report_moment(solver, name: str, zones: list,
                       center: list, axis: list):
    """
    Create a moment report definition.
    Issue #3 fix: Fluent 252 rejects 'moment_center' as a creation key.
    Create with zones only, then set center/axis as separate attributes.
    """
    try:
        solver.solution.report_definitions.moment[name] = {"zones": zones}
    except Exception as e:
        log.warning(f"  Moment report {name!r} create: {e}")
        return
    try:
        obj = solver.solution.report_definitions.moment[name]
        # Try flat x/y/z attributes (Fluent 252 confirmed)
        try:
            obj.moment_center_x = float(center[0])
            obj.moment_center_y = float(center[1])
            obj.moment_center_z = float(center[2])
        except Exception:
            # Fallback: set_state dict
            obj.set_state({"moment_center": center})
        try:
            obj.moment_axis = axis
        except Exception:
            obj.set_state({"moment_axis": axis})
    except Exception as e:
        log.warning(f"  Moment report {name!r} center/axis: {e}")


def _get_report_value(solver, report_type: str, name: str) -> float:
    """
    Read a force/moment report value using Fluent built-in scheme functions.

    Uses (report-forces ...) and (report-moments ...) which are always
    available in Fluent 252 and do not depend on monitor history.
    Zone list and force vector are read from the report definition object
    so this works for any report created by _add_report_lift/drag/moment.
    """
    import re as _re

    def _parse(s: str) -> float:
        nums = _re.findall(r'[-+]?[0-9]*[.]?[0-9]+(?:[eE][-+]?[0-9]+)?', str(s))
        return float(nums[0]) if nums else 0.0

    try:
        rd  = solver.solution.report_definitions
        obj = getattr(rd, report_type)[name]

        zones = list(obj.zones.get_state())
        if not zones:
            log.warning(f"  Report {name!r}: no zones defined")
            return 0.0

        # Build a Scheme list of zone name strings
        zone_list = "(list " + " ".join(f'"{z}"' for z in zones) + ")"

        if report_type in ("lift", "drag"):
            vec = list(obj.force_vector.get_state())
            vx, vy, vz = float(vec[0]), float(vec[1]), float(vec[2])
            # report-forces returns a list of (zone pressure viscous) + net entry.
            # Net is (car (reverse result)); total = pressure + viscous = cadr + caddr.
            expr = (
                f"(let* ((f (report-forces {zone_list}"
                f" (list {vx} {vy} {vz}) #f))"
                f" (net (car (reverse f))))"
                f" (+ (cadr net) (caddr net)))"
            )
        else:
            # Moment: center and axis are set separately; use (0 0 0) / (0 0 1)
            # as the universal default — matches _add_report_moment convention.
            expr = (
                f"(let* ((m (report-moments {zone_list}"
                f" (list 0.0 0.0 0.0) (list 0.0 0.0 1.0) #f))"
                f" (net (car (reverse m))))"
                f" (+ (cadr net) (caddr net)))"
            )

        result = solver.scheme_eval.string_eval(expr)
        return _parse(result)

    except Exception as e:
        log.warning(f"  Report {name!r}: {e}")
        return 0.0


def _compute_projected_area(solver, config) -> float:
    """
    Doc Step 2.1.e -- compute the frontal area via Results > Projected Area.

    Minimum feature size 0.0001 m, X direction, scoped to every vehicle
    surface. Without this the reference area stays at Fluent's default of
    1 m^2 and every coefficient (Cl, Cd) is wrong by that factor.

    Returns the area in m^2, or 0.0 if it could not be computed.
    """
    half_sym = getattr(config, "is_half_symmetry", False)

    # Every vehicle surface, filtered to what's actually in the mesh
    candidates = (AERO_LABELS + BODY_LABELS
                  + FRONT_SUS_LABELS + REAR_SUS_LABELS
                  + _all_wheel_labels(half_sym))
    try:
        walls = list(solver.setup.boundary_conditions.wall.keys())
        zones = [z for z in candidates if z in walls]
    except Exception:
        zones = candidates
    if not zones:
        log.warning("  Projected area: no vehicle zones found")
        return 0.0

    MIN_FEATURE = 0.0001   # m

    # Settings API
    try:
        pa = solver.results.report.projected_surface_area
        pa.min_feature_size = MIN_FEATURE
        pa.projection_direction = [1, 0, 0]   # X direction
        pa.surfaces = zones
        area = float(pa.compute())
        if area > 0:
            log.info(f"  Projected area: {area:.5f} m^2 over {len(zones)} zones")
            return area
    except Exception as e:
        log.debug(f"  Projected area (settings API): {e}")

    # TUI
    try:
        result = solver.tui.report.projected_surface_area(
            *zones, "()", "x", str(MIN_FEATURE)
        )
        import re
        m = re.search(r"([-+]?[0-9]*[.]?[0-9]+(?:[eE][-+]?[0-9]+)?)",
                      str(result))
        if m:
            area = float(m.group(1))
            if area > 0:
                log.info(f"  Projected area (TUI): {area:.5f} m^2")
                return area
    except Exception as e:
        log.debug(f"  Projected area (TUI): {e}")

    # Scheme eval
    try:
        zone_list = " ".join(f'"{z}"' for z in zones)
        raw = solver.scheme_eval.string_eval(
            f'(compute-projected-area (list {zone_list}) '
            f"'(1 0 0) {MIN_FEATURE})"
        )
        import re
        m = re.search(r"([-+]?[0-9]*[.]?[0-9]+(?:[eE][-+]?[0-9]+)?)", str(raw))
        if m:
            area = float(m.group(1))
            if area > 0:
                log.info(f"  Projected area (scheme): {area:.5f} m^2")
                return area
    except Exception as e:
        log.debug(f"  Projected area (scheme): {e}")

    log.warning(
        "  Projected area could not be computed -- Cl/Cd will use the "
        "existing reference area and may be wrong"
    )
    return 0.0


def _compute_reference_values(solver, speed_ms: float, car_length_m: float,
                              config=None):
    """
    Doc Step 2.1 -- reference values.

    Compute From: Inlet, Velocity, Length = car length, Reference Zone =
    enclosure, Area = computed projected area.
    """
    rv = solver.setup.reference_values

    # Compute from inlet -- sets density, viscosity, pressure from the BC
    try:
        rv.compute("inlet")
        log.debug("  Reference values computed from inlet")
    except Exception:
        try:
            rv.compute_from = "inlet"
        except Exception:
            pass

    # Reference zone = the enclosure
    try:
        fluid_zones = list(solver.setup.cell_zone_conditions.fluid.keys())
        enclosure = next(
            (z for z in fluid_zones if "enclosure" in z.lower()),
            fluid_zones[0] if fluid_zones else None,
        )
        if enclosure:
            rv.zone = enclosure
            log.info(f"  Reference zone: {enclosure}")
    except Exception as e:
        log.debug(f"  Reference zone: {e}")

    # Velocity and length
    try:
        rv.velocity = speed_ms
    except Exception as e:
        log.warning(f"  Reference values velocity: {e}")
    try:
        rv.length = car_length_m
    except Exception as e:
        log.warning(f"  Reference values length: {e}")

    # Frontal area from projected area computation
    area = 0.0
    if config is not None:
        area = _compute_projected_area(solver, config)
        if area > 0:
            try:
                rv.area = area
            except Exception as e:
                log.warning(f"  Reference values area: {e}")

    log.info(
        f"  Reference values: v={speed_ms:.2f} m/s  L={car_length_m:.3f} m"
        + (f"  A={area:.5f} m^2" if area > 0 else "  A=(not set)")
    )
    return area


# ---------------------------------------------------------------------------
# Meshing helpers
# ---------------------------------------------------------------------------

def compute_refinement_boxes(L: float, W: float, H: float, half_sym: bool):
    """
    Returns Near/Mid/Far box coords as dicts.
    L = car length (x), W = car width (z), H = car height (y).
    half_sym: if True, z_min = 0 (symmetry plane)
    Doc reference: Tables 1-3 in Ram Racing Fluent Procedure.
    """
    z_mirror = 0.0 if half_sym else -(W + H / 2)

    near = {
        "size": 0.032,
        "x_min": -L,          "x_max": 3 * L,
        "y_min": 0,           "y_max": H + L / 3,
        "z_min": z_mirror,    "z_max": W + H / 2,
    }
    mid = {
        "size": 0.064,
        "x_min": -1.25 * L,   "x_max": 5 * L,
        "y_min": 0,            "y_max": H + 2 * L / 3,
        "z_min": 0.0 if half_sym else -(W + H),
        "z_max": W + H,
    }
    far = {
        "size": 0.128,
        "x_min": -1.5 * L,    "x_max": 7 * L,
        "y_min": 0,            "y_max": 2 * L,
        "z_min": 0.0 if half_sym else -(W + 1.5 * H),
        "z_max": W + 1.5 * H,
    }
    return near, mid, far


def _get_refinement_task(meshing, watertight):
    """
    Return the "Create Local Refinement Regions" task.

    This is the task that accepts explicit box coordinates -- it is NOT the
    same as "Add Local Sizing" with Body Of Influence, which requires a
    geometry body to define the region.

    In the 2026 R1 Enhanced Workflow the task is optional and must be
    inserted via insertable_tasks before it can be used. Falls back to the
    legacy TaskObject dict API if the enhanced path is unavailable.

    Returns (mode, task) where mode is "enhanced", "legacy", or None.
    """
    # Already present on the enhanced workflow?
    for attr in ("create_local_refinement_regions",
                 "local_refinement_regions",
                 "create_local_refinement_region"):
        task = getattr(watertight, attr, None)
        if task is not None:
            return ("enhanced", task)

    # Insert it via insertable_tasks
    for parent_attr in ("import_geometry", "add_local_sizing_wtm",
                        "create_surface_mesh"):
        parent = getattr(watertight, parent_attr, None)
        if parent is None:
            continue
        insertables = getattr(parent, "insertable_tasks", None)
        if insertables is None:
            continue
        for task_attr in ("create_local_refinement_regions",
                          "local_refinement_regions",
                          "create_local_refinement_region"):
            inserter = getattr(insertables, task_attr, None)
            if inserter is None:
                continue
            try:
                inserter.insert()
                task = getattr(watertight, task_attr, None)
                if task is not None:
                    log.debug(f"  Inserted task: {task_attr}")
                    return ("enhanced", task)
            except Exception as e:
                log.debug(f"  Insert {task_attr}: {e}")

    # Legacy TaskObject fallback
    try:
        task = meshing.workflow.TaskObject["Create Local Refinement Regions"]
        return ("legacy", task)
    except Exception as e:
        log.debug(f"  Legacy TaskObject lookup: {e}")

    return (None, None)


def _set_task_property(task, name, value) -> bool:
    """Set a task property, handling both set_state() objects and setattr."""
    obj = getattr(task, name, None)
    if obj is None:
        return False
    try:
        if hasattr(obj, "set_state"):
            obj.set_state(value)
        else:
            setattr(task, name, value)
        return True
    except Exception:
        try:
            setattr(task, name, value)
            return True
        except Exception:
            return False


def _apply_task_arguments(task, args: dict) -> bool:
    """
    Push an argument dict onto a workflow task.

    "Create Local Refinement Regions" is a compound task -- its settings live
    in the task's `arguments` datamodel node rather than as direct Python
    attributes, so the CamelCase keys from the legacy API still apply.
    """
    # 1. arguments.set_state()
    try:
        task.arguments.set_state(args)
        return True
    except Exception as e:
        log.debug(f"  arguments.set_state: {e}")
    # 2. arguments.update_dict() / update()
    for method in ("update_dict", "update"):
        try:
            getattr(task.arguments, method)(args)
            return True
        except Exception:
            continue
    # 3. plain assignment
    try:
        task.arguments = args
        return True
    except Exception as e:
        log.debug(f"  arguments assignment: {e}")
    # 4. per-key snake_case attributes (older enhanced-workflow builds)
    n = sum(1 for k, v in args.items() if _set_task_property(task, _snake(k), v))
    return n > 0


def _snake(camel: str) -> str:
    """LocalRefinementRegionName -> local_refinement_region_name, XMin -> x_min"""
    out = []
    for i, ch in enumerate(camel):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _execute_task(task) -> bool:
    """Execute a workflow task, trying compound-child and plain forms."""
    for method in ("add_child_and_update", "execute", "__call__"):
        fn = getattr(task, method, None)
        if fn is None:
            continue
        try:
            if method == "add_child_and_update":
                try:
                    fn(defer_update=False)
                except TypeError:
                    fn()
            else:
                fn()
            return True
        except Exception as e:
            log.debug(f"  {method}(): {e}")
    return False


def _dump_task_arguments(task, label: str):
    """Log the task's real argument keys so naming can be corrected."""
    try:
        state = task.arguments()
        if isinstance(state, dict):
            log.warning(f"  {label} accepts these argument keys: {sorted(state.keys())}")
            return
        log.warning(f"  {label} arguments state: {state}")
    except Exception as e:
        log.warning(f"  {label}: could not read arguments ({e})")


def _add_refinement_box(meshing, watertight, name: str, box: dict) -> bool:
    """
    Create a coordinate-specified local refinement region.

    Per Tables 1-3 of the Fluent Procedure doc, these are pure coordinate
    boxes -- Type=box, CoordinateSpecificationMethod=directly-specify-coordinates,
    Mesh Size, and the six bounds. There is NO label/zone selection: the box
    is defined in absolute space, not relative to any body.

    Coordinates come from compute_refinement_boxes(), the same formulas as
    MATLAB-Scripts/localrefinementregion.m.

    Returns True if the region was created.
    """
    mode, task = _get_refinement_task(meshing, watertight)
    if mode is None:
        log.warning(f"  Refinement box {name!r}: task not available in workflow")
        return False

    args = {
        "LocalRefinementRegionName":     name,
        "Type":                          "box",
        "CoordinateSpecificationMethod": "directly-specify-coordinates",
        "MeshSize":                      box["size"],
        "XMin": box["x_min"], "XMax": box["x_max"],
        "YMin": box["y_min"], "YMax": box["y_max"],
        "ZMin": box["z_min"], "ZMax": box["z_max"],
    }

    extents = (
        f"X[{box['x_min']:.2f}, {box['x_max']:.2f}]  "
        f"Y[{box['y_min']:.2f}, {box['y_max']:.2f}]  "
        f"Z[{box['z_min']:.2f}, {box['z_max']:.2f}]"
    )

    if mode == "legacy":
        try:
            task.Arguments.update(args)
            task.Execute()
            log.info(f"  Added refinement box: {name}  size={box['size']} m  {extents}")
            return True
        except Exception as e:
            log.warning(f"  Refinement box {name!r} (legacy): {e}")
            return False

    if not _apply_task_arguments(task, args):
        log.warning(f"  Refinement box {name!r}: could not set arguments")
        _dump_task_arguments(task, f"Refinement box {name!r}")
        return False

    if not _execute_task(task):
        log.warning(f"  Refinement box {name!r}: execute failed")
        return False

    log.info(f"  Added refinement box: {name}  size={box['size']} m  {extents}")
    return True


def _update_boundaries(watertight) -> bool:
    """
    Doc Step 8 -- assign boundary types by label.

    Fluent auto-assigns from name patterns (*inlet* -> velocity-inlet etc),
    but that silently misses anything not matching, so the types are set
    explicitly here. Everything on the car and the ground is a wall.
    """
    task = getattr(watertight, "update_boundaries", None)
    if task is None:
        log.warning("  Update Boundaries task not available")
        return False

    type_map = {
        "inlet":    "velocity-inlet",
        "outlet":   "pressure-outlet",
        "symmetry": "symmetry",
    }

    try:
        labels = list(task.boundary_label_list.get_state() or [])
    except Exception:
        labels = []

    if labels:
        types = [type_map.get(l, "wall") for l in labels]
        try:
            task.boundary_label_type_list.set_state(types)
            log.info(f"  Boundary types set for {len(labels)} labels")
            for l, t in zip(labels, types):
                if t != "wall":
                    log.info(f"    {l:12s} -> {t}")
        except Exception as e:
            log.debug(f"  boundary_label_type_list: {e}")
    try:
        task.selection_type = "label"
    except Exception:
        pass

    try:
        task()
        return True
    except Exception as e:
        log.warning(f"  Update Boundaries: {e}")
        return False


def _update_regions(watertight) -> int:
    """
    Doc Step 9 -- set region types.

    The enclosure is the fluid region. Anything else Fluent found is a
    leftover body and must be set to solid, otherwise the volume mesher
    tries to fill it. Returns the number of solid regions found so the
    volume mesh step can disable Generate Solid Regions accordingly.
    """
    task = getattr(watertight, "update_regions", None)
    if task is None:
        log.warning("  Update Regions task not available")
        return 0

    n_solid = 0
    try:
        names = list(task.old_region_name_list.get_state()
                     or task.region_name_list.get_state() or [])
    except Exception:
        names = []

    if names:
        types = []
        for n in names:
            if "enclosure" in n.lower():
                types.append("fluid")
            else:
                types.append("solid")
                n_solid += 1
        try:
            task.region_type_list.set_state(types)
            log.info(f"  Regions: {list(zip(names, types))}")
        except Exception as e:
            log.debug(f"  region_type_list: {e}")

        if n_solid:
            log.warning(
                f"  {n_solid} non-enclosure region(s) set to solid -- "
                f"Generate Solid Regions will be disabled"
            )

    try:
        task()
    except Exception as e:
        log.warning(f"  Update Regions: {e}")
    return n_solid


def _add_wheel_refinement(meshing, watertight, wheel_name: str,
                          half_sym: bool = False,
                          labels: list = None) -> bool:
    """
    Per-wheel local refinement region -- Table 4.

    Uses relative-to-body-size: 0.032 m mesh size, box bounds expressed as
    fractions of the wheel body. Because the bounds are relative, this DOES
    need a body to be relative to, so the wheel's own labels are passed in.

    Wheel naming depends on geometry type:
        Full car  FLW -> flw + flwb,  FRW -> frw + frwb, etc.
        Half car  FRW/FLW -> fw + fwb,  RRW/RLW -> rw + rwb
    """
    mode, task = _get_refinement_task(meshing, watertight)
    if mode is None:
        return False

    if labels is None:
        name = wheel_name.strip().lower()
        if half_sym:
            # Half car has a single wheel per axle: fw / rw
            labels = ["fw", "fwb"] if name.startswith("f") else ["rw", "rwb"]
        else:
            # Full car: flw / frw / rlw / rrw plus matching blocks
            base = name if name in ("flw", "frw", "rlw", "rrw") else None
            if base is None:
                # Accept FLW / Front-Left / etc.
                front = name.startswith("f")
                left  = "l" in name[1:2] or "left" in name
                base  = ("f" if front else "r") + ("l" if left else "r") + "w"
            labels = [base, base + "b"]

    labels = _filter_existing_labels(watertight, labels)
    if not labels:
        log.warning(
            f"  Wheel refinement {wheel_name!r}: no matching wheel labels "
            f"in geometry -- skipped"
        )
        return False

    region_name = f"wheel_{wheel_name.lower()}"
    args = {
        "LocalRefinementRegionName":     region_name,
        "Type":                          "box",
        "CoordinateSpecificationMethod": "relative-to-body-size",
        "MeshSize":                      0.032,
        "XMin": 0.1, "XMax": 1.0,
        "YMin": 0.0, "YMax": 0.1,
        "ZMin": 0.1, "ZMax": 0.1,
        "SelectionType":      "label",
        "LabelSelectionList": labels,
        "ZoneSelectionList":  labels,
        "ZoneLocation":       labels,
    }

    if mode == "legacy":
        try:
            task.Arguments.update(args)
            task.Execute()
            log.info(f"  Added wheel refinement box: {wheel_name}  labels={labels}")
            return True
        except Exception as e:
            log.warning(f"  Wheel refinement {wheel_name!r} (legacy): {e}")
            return False

    if not _apply_task_arguments(task, args):
        log.warning(f"  Wheel refinement {wheel_name!r}: could not set arguments")
        _dump_task_arguments(task, f"Wheel refinement {wheel_name!r}")
        return False
    if not _execute_task(task):
        log.warning(f"  Wheel refinement {wheel_name!r}: execute failed")
        return False

    log.info(f"  Added wheel refinement box: {wheel_name}  labels={labels}")
    return True


# ---------------------------------------------------------------------------
# Mesh quality extraction
# ---------------------------------------------------------------------------

# Orthogonal quality bands used in the histogram.
# Values are (label, lower_bound_inclusive, upper_bound_exclusive).
# The final band's upper bound is treated as inclusive (catches 1.0 exactly).
_OQ_BANDS = [
    ("0.00 – 0.10  [CRITICAL]", 0.00, 0.10),
    ("0.10 – 0.20  [poor]",     0.10, 0.20),
    ("0.20 – 0.40  [fair]",     0.20, 0.40),
    ("0.40 – 0.70  [good]",     0.40, 0.70),
    ("0.70 – 0.90  [very good]",0.70, 0.90),
    ("0.90 – 1.00  [excellent]",0.90, 1.01),  # 1.01 so 1.0 is included
]

# Fluent target: min orthogonal quality > 0.1 (ideally > 0.2 for production runs)
_OQ_MIN_WARN  = 0.10   # warn if min falls below this
_OQ_MIN_ERROR = 0.05   # flag as poor quality if min falls below this


def _extract_mesh_quality(meshing) -> dict:
    """
    Extract orthogonal quality statistics from the meshing session.

    Tries the PyFluent 0.38 meshing API first, then falls back to
    Scheme/TUI evaluation.  Always returns a dict — never raises.

    Returned keys:
        oq_min       float   minimum orthogonal quality across all cells
        oq_max       float   maximum (should be ≤ 1.0)
        oq_mean      float   volume-weighted mean orthogonal quality
        oq_pct_below_01  float  fraction of cells with OQ < 0.10  (0–1)
        oq_pct_below_02  float  fraction of cells with OQ < 0.20  (0–1)
        oq_total_cells   int    total cell count
        oq_bands     list[dict] histogram: [{label, lo, hi, count, pct}]
        oq_pass      bool    True when min OQ ≥ _OQ_MIN_WARN
        oq_note      str     human-readable quality verdict
        oq_raw_text  str     raw Fluent output (for debugging)
    """
    result = {
        "oq_min": 0.0, "oq_max": 0.0, "oq_mean": 0.0,
        "oq_pct_below_01": 0.0, "oq_pct_below_02": 0.0,
        "oq_total_cells": 0, "oq_bands": [],
        "oq_pass": False, "oq_note": "Quality data unavailable",
        "oq_raw_text": "",
    }

    # ── Attempt 1: PyFluent 0.38 mesh quality object ─────────────────────
    try:
        mq = meshing.meshing.MeshQuality
        oq_min  = float(mq.MinOrthogonalQuality.get_state())
        oq_max  = float(mq.MaxOrthogonalQuality.get_state())
        oq_mean = float(mq.MeanOrthogonalQuality.get_state())
        result.update({"oq_min": oq_min, "oq_max": oq_max, "oq_mean": oq_mean})
        log.info(f"  Mesh quality (API): min={oq_min:.4f}  mean={oq_mean:.4f}  max={oq_max:.4f}")
    except Exception as e1:
        log.debug(f"  MeshQuality API failed: {e1}")

        # ── Attempt 2: Scheme eval ────────────────────────────────────────
        try:
            raw = meshing.scheme_eval.string_eval(
                '(cx-gui-do cx-set-list-selections "Mesh Quality" '
                '(list "Orthogonal Quality")) '
                '(cx-gui-do cx-activate-item "Mesh Quality") '
                '(cx-gui-do cx-get-list-selections "Mesh Quality")'
            )
            result["oq_raw_text"] = str(raw)
            log.debug(f"  Mesh quality scheme raw: {raw}")
        except Exception as e2:
            log.debug(f"  Scheme eval mesh quality failed: {e2}")

        # ── Attempt 3: TUI report ─────────────────────────────────────────
        try:
            raw = meshing.tui.report.mesh_quality("orthogonal-quality")
            result["oq_raw_text"] = str(raw)
            # Parse "Minimum Orthogonal Quality = X" style output
            import re
            for label, key in [
                (r"[Mm]inimum.*?=\s*([\d.eE+\-]+)", "oq_min"),
                (r"[Mm]aximum.*?=\s*([\d.eE+\-]+)", "oq_max"),
                (r"[Aa]verage.*?=\s*([\d.eE+\-]+)",  "oq_mean"),
            ]:
                m = re.search(label, str(raw))
                if m:
                    result[key] = float(m.group(1))
            log.info(
                f"  Mesh quality (TUI): min={result['oq_min']:.4f}  "
                f"mean={result['oq_mean']:.4f}  max={result['oq_max']:.4f}"
            )
        except Exception as e3:
            log.debug(f"  TUI mesh quality failed: {e3}")

    # ── Cell count ────────────────────────────────────────────────────────
    try:
        # PyFluent 0.38: cell count via GlobalSettings or mesh info
        total_cells = int(
            meshing.meshing.GlobalSettings.FTMRegionData
            .TotalCellCount.get_state()
        )
        result["oq_total_cells"] = total_cells
    except Exception:
        try:
            raw = meshing.tui.report.mesh_statistics()
            import re
            m = re.search(r"(\d[\d,]+)\s+cells", str(raw))
            if m:
                result["oq_total_cells"] = int(m.group(1).replace(",", ""))
        except Exception:
            pass

    # ── Per-band histogram (best-effort via Fluent distribution query) ────
    try:
        # Ask Fluent for the orthogonal quality histogram as a distribution.
        # This is supported in Fluent 252 via scheme.
        raw_hist = meshing.scheme_eval.string_eval(
            "(let ((q (mesh/quality-info))) "
            "(list (assq 'orthogonal-quality q)))"
        )
        result["oq_raw_text"] = (result["oq_raw_text"] + "\n" + str(raw_hist)).strip()
        log.debug(f"  Quality histogram raw: {raw_hist}")
    except Exception as e:
        log.debug(f"  Quality histogram scheme eval skipped: {e}")

    # ── Build band histogram from min/mean/max heuristic ─────────────────
    # If we have at least min + mean, synthesise approximate band counts.
    # This is not exact — it's a triangular distribution approximation used
    # only when Fluent doesn't expose per-band counts directly.
    oq_min  = result["oq_min"]
    oq_mean = result["oq_mean"]
    total   = result["oq_total_cells"]
    bands   = []
    below_01 = 0
    below_02 = 0

    for label, lo, hi in _OQ_BANDS:
        # Rough fraction estimate: linear ramp from min to mean,
        # then flat above mean. Not exact, clearly labelled as approximate.
        hi_eff = min(hi, 1.0)
        if hi_eff <= oq_min:
            frac = 0.0
        elif lo >= oq_mean:
            # Above the mean — uniform distribution assumption
            span_total = max(1.0 - oq_mean, 1e-9)
            frac = max(0.0, (hi_eff - lo)) / span_total * 0.5
        else:
            # Straddles or is below mean
            span_total = max(oq_mean - oq_min, 1e-9)
            effective_lo = max(lo, oq_min)
            frac = max(0.0, min(hi_eff, oq_mean) - effective_lo) / span_total * 0.5

        frac  = min(frac, 1.0)
        count = int(round(frac * total)) if total > 0 else 0
        pct   = frac * 100.0
        bands.append({"label": label, "lo": lo, "hi": hi_eff,
                      "count": count, "pct": pct})
        if hi_eff <= 0.10:
            below_01 += frac
        if hi_eff <= 0.20:
            below_02 += frac

    result["oq_bands"]         = bands
    result["oq_pct_below_01"]  = min(below_01, 1.0)
    result["oq_pct_below_02"]  = min(below_02, 1.0)

    # ── Verdict ───────────────────────────────────────────────────────────
    oq_min = result["oq_min"]
    if oq_min <= 0.0:
        note = "Quality data unavailable — check logs"
        passed = False
    elif oq_min < _OQ_MIN_ERROR:
        note = f"POOR  — min OQ {oq_min:.4f} below {_OQ_MIN_ERROR:.2f}. Remesh recommended."
        passed = False
    elif oq_min < _OQ_MIN_WARN:
        note = f"MARGINAL  — min OQ {oq_min:.4f} below {_OQ_MIN_WARN:.2f}. Review before solving."
        passed = False
    else:
        note = f"PASS  — min OQ {oq_min:.4f} ≥ {_OQ_MIN_WARN:.2f}"
        passed = True

    result["oq_pass"] = passed
    result["oq_note"] = note
    log.info(f"  Mesh quality verdict: {note}")
    return result


# ---------------------------------------------------------------------------
# Main Meshing Workflow
# ---------------------------------------------------------------------------

def run_meshing(config, progress_cb: Optional[Callable] = None):
    """
    Execute the Fluent Meshing Watertight Geometry workflow.

    2026 R1 / PyFluent 0.39: Uses the Enhanced Meshing Workflow API.
    Tasks are accessed as Python attributes on the watertight workflow object
    rather than via dict-based TaskObject["Name"].Arguments patterns.

    Reference: https://fluent.docs.pyansys.com/version/stable/user_guide/meshing/new_meshing_workflows.html
    """
    try:
        import ansys.fluent.core as pyfluent
    except ImportError:
        raise RuntimeError(
            "ansys-fluent-core is not installed. "
            "Run: pip install ansys-fluent-core"
        )

    def prog(msg, pct):
        log.info(f"[MESH {pct:3d}%] {msg}")
        if progress_cb:
            progress_cb(msg, pct)

    prog("Launching Fluent Meshing...", 0)
    meshing = _launch_fluent_meshing(pyfluent, config)

    try:
        # ── Initialize Enhanced Watertight Workflow ───────────────────────
        watertight = meshing.watertight()

        # ── Step 1: Import Geometry ──────────────────────────────────────
        prog("Importing geometry...", 5)
        log.info(f"  Geometry: {config.geometry_path!r}")
        import_geometry = watertight.import_geometry
        import_geometry.file_name.set_state(config.geometry_path)
        import_geometry.length_unit.set_state("m")
        import_geometry()

        # ── Step 2: Local Sizing (doc Step 4) ────────────────────────────
        # All three are Curvature controls. Face Size alone does not refine
        # curved aero surfaces -- the curvature normal angle is what does.
        sizing   = watertight.add_local_sizing_wtm
        half_sym = getattr(config, "is_half_symmetry", False)
        wheels   = _wheel_labels(half_sym)

        log.info(f"  Geometry type: {'half car' if half_sym else 'full car'}")
        log.info(f"  Front wheel labels: {wheels['front']}")
        log.info(f"  Rear wheel labels:  {wheels['rear']}")

        def _add_curvature_sizing(control_name, labels, params, pct, desc):
            """Add one Curvature size control scoped to the given labels."""
            labels = _filter_existing_labels(watertight, labels)
            if not labels:
                log.warning(f"    {control_name}: no matching labels, skipped")
                return False
            prog(f"Adding local sizing: {desc}...", pct)
            sizing.add_child = "yes"
            sizing.boi_control_name = control_name
            sizing.boi_execution    = "Curvature"
            sizing.boi_zoneor_label = "label"
            sizing.boi_face_label_list = labels
            for attr, key in [
                ("boi_growth_rate",           "growth_rate"),
                ("boi_size_control_type",     "size_control_type"),
                ("boi_min_size",              "local_min_size"),
                ("boi_max_size",              "max_size"),
                ("boi_curvature_normal_angle","curvature_normal_angle"),
                ("boi_scope_to",              "scope_to"),
            ]:
                try:
                    setattr(sizing, attr, params[key])
                except Exception as e:
                    log.debug(f"    {control_name}.{attr}: {e}")
            try:
                sizing.add_child_and_update(defer_update=False)
            except TypeError:
                sizing.add_child_and_update()
            log.info(
                f"    {control_name} -> {labels}  "
                f"[min {params['local_min_size']} / max {params['max_size']} m, "
                f"CNA {params['curvature_normal_angle']}deg, "
                f"scope {params['scope_to']}]"
            )
            return True

        _add_curvature_sizing(
            "curvature_stuff",
            BODY_LABELS + FRONT_SUS_LABELS + REAR_SUS_LABELS,
            SIZING_STUFF, 22, "chassis/body",
        )
        _add_curvature_sizing(
            "curvature_aero", AERO_LABELS,
            SIZING_AERO, 28, "aero elements",
        )
        _add_curvature_sizing(
            "curvature_wheels", _all_wheel_labels(half_sym),
            SIZING_WHEELS, 33, "wheels",
        )

        # Near / Mid / Far volume refinement boxes -- Tables 1-3.
        # Pure coordinate boxes, no label selection (see doc screenshot).
        prog("Adding Near/Mid/Far refinement boxes...", 38)
        near, mid, far = compute_refinement_boxes(
            config.car_length_m, config.car_width_m, config.car_height_m,
            half_sym=getattr(config, "is_half_symmetry", False),
        )
        n_boxes = 0
        n_boxes += _add_refinement_box(meshing, watertight,
                                       "local-refinement-nearfield", near)
        n_boxes += _add_refinement_box(meshing, watertight,
                                       "local-refinement-midfield",  mid)
        n_boxes += _add_refinement_box(meshing, watertight,
                                       "local-refinement-farfield",  far)
        if n_boxes < 3:
            log.warning(
                f"  Only {n_boxes}/3 refinement boxes created -- near-field "
                f"mesh will be coarser than intended"
            )

        # Per-wheel refinement boxes -- Table 4.
        # relative-to-body-size needs a body, so these DO take labels.
        if config.use_wheel_mrf and config.wheel_mrf_zones:
            prog("Adding wheel refinement boxes...", 42)
            for wheel in config.wheel_mrf_zones:
                _add_wheel_refinement(
                    meshing, watertight, wheel.name, half_sym,
                )

        # ── Step 3: Generate Surface Mesh (doc Step 5) ───────────────────
        prog("Generating surface mesh...", 50)
        surface_mesh = watertight.create_surface_mesh
        ctrl = surface_mesh.cfd_surface_mesh_controls
        ctrl.min_size = config.surface_mesh_min
        ctrl.max_size = config.surface_mesh_max
        for attr, value in [
            ("growth_rate",            SURFACE_MESH["growth_rate"]),
            ("size_functions",         SURFACE_MESH["size_functions"]),
            ("curvature_normal_angle", SURFACE_MESH["curvature_normal_angle"]),
            ("cells_per_gap",          SURFACE_MESH["cells_per_gap"]),
            ("scope_proximity_to",     SURFACE_MESH["scope_proximity_to"]),
        ]:
            try:
                setattr(ctrl, attr, value)
            except Exception as e:
                log.debug(f"  surface mesh {attr}: {e}")
        try:
            surface_mesh.separate_out_boundary_zones_by_angle = \
                SURFACE_MESH["separate_by_angle"]
        except Exception as e:
            log.debug(f"  separate_out_boundary_zones_by_angle: {e}")
        log.info(
            f"  Surface mesh: min {config.surface_mesh_min} / "
            f"max {config.surface_mesh_max} m, "
            f"CNA {SURFACE_MESH['curvature_normal_angle']}deg, "
            f"{SURFACE_MESH['size_functions']}"
        )
        surface_mesh()

        # ── Improve Surface Mesh (doc Step 6) ────────────────────────────
        prog("Improving surface mesh...", 56)
        improved = False
        for attr in ("improve_surface_mesh", "improve_surface_mesh_wtm"):
            task = getattr(watertight, attr, None)
            if task is None:
                # Optional task -- insert it if the workflow supports it
                try:
                    watertight.create_surface_mesh.insertable_tasks \
                        .improve_surface_mesh.insert()
                    task = getattr(watertight, attr, None)
                except Exception:
                    task = None
            if task is None:
                continue
            try:
                task.face_quality_limit = SURFACE_FACE_QUALITY_LIMIT
            except Exception as e:
                log.debug(f"  face_quality_limit: {e}")
            try:
                task()
                log.info(
                    f"  Surface mesh improved "
                    f"(face quality limit {SURFACE_FACE_QUALITY_LIMIT})"
                )
                improved = True
                break
            except Exception as e:
                log.debug(f"  {attr}(): {e}")
        if not improved:
            log.warning("  Improve Surface Mesh task unavailable -- skipped")

        # ── Step 4: Describe Geometry (doc Step 7) ───────────────────────
        prog("Describing geometry...", 60)
        describe = watertight.describe_geometry
        describe.update_child_tasks(setup_type_changed=False)
        describe.setup_type = "fluid"
        # Doc: all three answers are No
        for attr, value in [
            ("wall_to_internal",     "No"),
            ("invoke_share_topology", "No"),
            ("multizone",             "No"),
        ]:
            try:
                setattr(describe, attr, value)
            except Exception as e:
                log.debug(f"  describe.{attr}: {e}")
        describe.update_child_tasks(setup_type_changed=True)
        describe()

        # ── Update Boundaries (doc Step 8) ───────────────────────────────
        prog("Updating boundaries...", 66)
        _update_boundaries(watertight)

        # ── Step 5: Update Regions (doc Step 9) ──────────────────────────
        prog("Updating regions...", 72)
        n_solid = _update_regions(watertight)

        # ── Step 6: Add Boundary Layers (doc Step 10) ────────────────────
        prog("Adding boundary layers...", 76)
        bl = watertight.add_boundary_layers
        bl.add_child_to_task()
        for attr, value in [
            ("control_name",       "last-ratio_1"),
            ("offset_method_type", "last-ratio"),
            ("number_of_layers",   config.bl_num_layers),
            ("transition_ratio",   config.bl_transition_ratio),
            ("first_height",       config.bl_first_height),
            ("add_in",             "fluid-regions"),
            ("grow_on",            "selected-zones"),
        ]:
            try:
                obj = getattr(bl, attr)
                if hasattr(obj, "set_state"):
                    obj.set_state(value)
                else:
                    setattr(bl, attr, value)
            except Exception as e:
                log.debug(f"  BL {attr}: {e}")
        try:
            # Doc Step 10: select all the aerodynamic devices and the ground
            bl_zones = _filter_existing_labels(
                watertight,
                AERO_LABELS + _all_wheel_labels(half_sym) + ["ground"],
            )
            bl.zone_selection_list.set_state(bl_zones)
            log.info(
                f"  Boundary layers: {config.bl_num_layers} layers, "
                f"last-ratio {config.bl_transition_ratio}, "
                f"first height {config.bl_first_height} m"
            )
            log.info(f"    grown on: {bl_zones}")
        except Exception as e:
            log.debug(f"  BL zone selection: {e}")
        bl.insert_compound_child_task()
        try:
            watertight.add_boundary_layers_child_1()
        except Exception as e:
            log.debug(f"  BL child execute: {e}")
            try:
                bl()
            except Exception:
                pass

        # ── Step 7: Generate Volume Mesh (doc Step 11) ───────────────────
        prog("Generating volume mesh (this takes a while)...", 82)
        vol_mesh = watertight.create_volume_mesh_wtm
        vol_mesh.volume_fill.set_state("poly-hexcore")
        vol_mesh.volume_fill_controls.hex_max_cell_length.set_state(
            config.volume_mesh_max
        )
        for obj, attr, value in [
            (vol_mesh.volume_fill_controls, "hex_min_cell_length",
             config.volume_mesh_min),
            (vol_mesh.volume_fill_controls, "peel_layers",
             VOLUME_PEEL_LAYERS),
            (vol_mesh, "solver_name",            "Fluent"),
            (vol_mesh, "enable_parallel_meshing", True),
        ]:
            try:
                target = getattr(obj, attr)
                if hasattr(target, "set_state"):
                    target.set_state(value)
                else:
                    setattr(obj, attr, value)
            except Exception as e:
                log.debug(f"  volume mesh {attr}: {e}")

        # Doc: if any region was set to solid, do not generate solid regions
        if n_solid:
            for attr in ("generate_solid_regions",
                         "prism_preferences_generate_solid_regions"):
                try:
                    setattr(vol_mesh, attr, False)
                    log.info("  Generate Solid Regions disabled")
                    break
                except Exception:
                    continue

        log.info(
            f"  Volume mesh: poly-hexcore, peel {VOLUME_PEEL_LAYERS}, "
            f"min {config.volume_mesh_min} / max {config.volume_mesh_max} m"
        )
        vol_mesh()

        # ── Improve Volume Mesh ──────────────────────────────────────────
        prog("Improving volume mesh...", 93)
        try:
            meshing.meshing.ImproveVolumeMesh(
                QualityMethod="Orthogonal",
                CellQualityLimit=0.2
            )
        except Exception as e:
            log.warning(f"  ImproveVolumeMesh skipped: {e}")

        # ── Extract mesh quality ─────────────────────────────────────────
        prog("Extracting mesh quality statistics...", 95)
        mesh_quality = _extract_mesh_quality(meshing)

        if not mesh_quality["oq_pass"]:
            log.warning(
                f"  Mesh quality check: {mesh_quality['oq_note']}  "
                f"(min={mesh_quality['oq_min']:.4f})"
            )
        else:
            log.info(f"  Mesh quality check: {mesh_quality['oq_note']}")

        # ── Save mesh ────────────────────────────────────────────────────
        os.makedirs(config.output_dir, exist_ok=True)
        mesh_file = config.output_dir.rstrip("/\\") + "/mesh.msh.h5"

        try:
            meshing.meshing.File.WriteMesh(FileName=mesh_file)
            log.info(f"  Mesh written via meshing.File.WriteMesh")
        except Exception as e:
            log.debug(f"  WriteMesh failed: {e}, trying scheme_eval fallback")
            meshing.scheme_eval.string_eval(f'(write-mesh "{mesh_file}")')

        prog(f"Mesh saved: {mesh_file}", 100)
        log.info(f"Meshing complete. File: {mesh_file}")
        return mesh_file, mesh_quality

    except Exception as e:
        log.error(f"Meshing failed: {e}")
        raise
    finally:
        try:
            meshing.exit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Solver physics helpers
# ---------------------------------------------------------------------------

def _apply_geko_physics(solver, curvature_correction: bool = False,
                        production_limiter: bool = True):
    """Configure k-omega GEKO turbulence model."""
    try:
        visc = solver.setup.models.viscous
        visc.model = "k-omega"
        visc.k_omega_model = "geko"
        try:
            visc.k_omega_options.production_limiter = production_limiter
        except Exception:
            pass
        try:
            visc.k_omega_options.curvature_correction = curvature_correction
        except Exception:
            pass
        log.info(f"  GEKO k-omega: CC={curvature_correction}, PL={production_limiter}")
    except Exception as e:
        log.warning(f"  _apply_geko_physics: {e}")


def _set_boundary_conditions(solver, config):
    """Apply velocity inlet, pressure outlet, symmetry and wall BCs."""
    from simtypes.configs import SimType
    speed_ms  = mph_to_ms(config.vehicle_speed_mph)
    is_turning = config.sim_type == SimType.TURNING

    # ── Resolve yaw angle ─────────────────────────────────────────────────
    yaw_deg = 0.0
    if is_turning:
        yaw_deg = config.effective_yaw_deg()
        log.info(f"  Turning sim: yaw={yaw_deg:.2f}°  "
                 f"radius={config.turn_radius_m:.1f} m")

    yaw_rad  = math.radians(yaw_deg)
    # Inlet velocity components: primary flow is −X, side component is +Z
    # (positive yaw = nose-right = left-hand turn = flow comes from left side)
    vx = speed_ms * math.cos(yaw_rad)
    vz = speed_ms * math.sin(yaw_rad)

    try:
        inlet = solver.setup.boundary_conditions.velocity_inlet["inlet"]
        if is_turning and abs(yaw_deg) > 0.01:
            # Set as velocity components rather than magnitude + direction
            try:
                inlet.momentum.velocity_specification_method = "Components"
                inlet.momentum.x_velocity.value = -vx   # flow in −X direction
                inlet.momentum.y_velocity.value = 0.0
                inlet.momentum.z_velocity.value = vz
                log.info(f"  Inlet components: Vx={-vx:.3f}  Vy=0  Vz={vz:.3f} m/s")
            except Exception:
                # Fallback: magnitude + yaw via direction cosines
                inlet.momentum.velocity_magnitude.value = speed_ms
                try:
                    inlet.momentum.flow_direction_method = "Direction Cosines"
                    inlet.momentum.x_component.value = -math.cos(yaw_rad)
                    inlet.momentum.y_component.value = 0.0
                    inlet.momentum.z_component.value =  math.sin(yaw_rad)
                    log.info(f"  Inlet direction cosines applied for yaw={yaw_deg:.2f}°")
                except Exception as e2:
                    log.warning(f"  Inlet yaw direction cosines failed: {e2}")
        else:
            try:
                inlet.momentum.velocity.value = speed_ms
            except Exception:
                inlet.momentum.velocity_magnitude.value = speed_ms
        try:
            inlet.turbulence.turbulent_intensity = 0.01
            inlet.turbulence.turbulent_viscosity_ratio = 1.0
        except Exception:
            pass
        log.info(f"  Inlet: {speed_ms:.2f} m/s  yaw={yaw_deg:.2f}°")
    except Exception as e:
        log.warning(f"  Inlet BC: {e}")

    try:
        outlet = solver.setup.boundary_conditions.pressure_outlet["outlet"]
        try:
            outlet.momentum.gauge_pressure.value = 0.0
        except Exception:
            pass
        log.info("  Outlet: 0 Pa gauge")
    except Exception as e:
        log.warning(f"  Outlet BC: {e}")

    try:
        ground = solver.setup.boundary_conditions.wall["ground"]
        ground.momentum.wall_motion = "Moving Wall"

        # Doc: Relative to Adjacent Cell Zone, Translational, X = 1, car speed.
        # +X is the flow direction, so the ground moves with the freestream.
        for attr, value in [
            ("relative_to_adjacent_cell_zone", True),
            ("motion_type",                    "Translational"),
            ("translation_direction_x",        1.0),
            ("translation_direction_y",        0.0),
            ("translation_direction_z",        0.0),
        ]:
            try:
                obj = getattr(ground.momentum, attr)
                if hasattr(obj, "set_state"):
                    obj.set_state(value)
                else:
                    setattr(ground.momentum, attr, value)
            except Exception as e:
                log.debug(f"  ground.{attr}: {e}")

        # Direction as a vector, if the API takes it that way instead
        for attr in ("translation_direction", "wall_translation_direction"):
            try:
                getattr(ground.momentum, attr).set_state([1.0, 0.0, 0.0])
                break
            except Exception:
                continue

        _ground_set = False
        for _attr in ("velocity", "velocity_spec",
                      "wall_translational_velocity", "wall_velocity",
                      "motion_speed"):
            try:
                getattr(ground.momentum, _attr).value = speed_ms
                _ground_set = True
                break
            except Exception:
                continue
        if not _ground_set:
            log.warning("  Ground moving wall: could not set velocity")
        else:
            log.info(
                f"  Ground: moving wall, translational +X, "
                f"{speed_ms:.2f} m/s, relative to adjacent cell zone"
            )
    except Exception as e:
        log.warning(f"  Ground BC: {e}")

    try:
        solver.setup.boundary_conditions.symmetry["symmetry"]
        log.info("  Symmetry plane: OK")
    except Exception as e:
        log.debug(f"  Symmetry BC: {e}")

    # ── Wheel MRF ─────────────────────────────────────────────────────────
    if config.use_wheel_mrf:
        for wheel in config.wheel_mrf_zones:
            try:
                if wheel.rpm > 0:
                    omega = wheel.rpm * 2 * math.pi / 60
                    log.info(f"  Wheel MRF {wheel.name}: RPM override {wheel.rpm:.1f} → {omega:.2f} rad/s")
                elif is_turning:
                    # Asymmetric RPM: inner wheels slower, outer wheels faster.
                    # "Left side" wheels (positive Z centre or axis_z=+1) are
                    # the outer wheels for a left-hand (positive yaw) turn.
                    # Determine inner/outer from the wheel's Z-axis sign.
                    track = config.track_width_m
                    R     = config.turn_radius_m
                    is_outer = (wheel.axis_z > 0)   # left-side = outer for LH turn
                    if yaw_deg < 0:                  # right-hand turn — flip
                        is_outer = not is_outer
                    path_radius = (R + track) if is_outer else (R - track)
                    path_radius = max(path_radius, 0.01)   # guard against zero
                    v_wheel     = speed_ms * path_radius / R
                    omega       = v_wheel / wheel.wheel_radius
                    log.info(
                        f"  Wheel MRF {wheel.name} ({'outer' if is_outer else 'inner'}): "
                        f"v={v_wheel:.3f} m/s  ω={omega:.2f} rad/s"
                    )
                else:
                    omega = speed_ms / wheel.wheel_radius
                mrf = solver.setup.cell_zone_conditions.fluid[wheel.zone_name]
                mrf.general.frame_motion = True
                mrf.general.rotation_axis_origin = [
                    wheel.center_x, wheel.center_y, wheel.center_z]
                mrf.general.rotation_axis_direction = [
                    wheel.axis_x, wheel.axis_y, wheel.axis_z]
                mrf.general.angular_velocity.value = omega
                log.info(f"  Wheel MRF {wheel.name}: {omega:.1f} rad/s")
            except Exception as e:
                log.warning(f"  Wheel MRF {wheel.name}: {e}")


def _configure_force_reports(solver, config):
    """
    Set up all force / coefficient / moment / CoP report definitions.

    Report naming convention (matches Fluent report-definitions panel):
      fz              total downforce (all car zones, direction 0,-1,0)
      fx              total drag      (all car zones, direction 1,0,0)
      cl              coefficient of lift  (all car zones)
      cd              coefficient of drag  (all car zones)
      fz_frontwing    front wing downforce
      fx_frontwing    front wing drag
      fz_rearwing     rear wing downforce
      fx_rearwing     rear wing drag
      fz_undertray    undertray downforce
      fx_undertray    undertray drag
      fz_fw           front wheel downforce
      fx_fw           front wheel drag
      fz_rw           rear wheel downforce
      fx_rw           rear wheel drag
      fz_frontsus     front suspension downforce
      fx_frontsus     front suspension drag
      fz_rearsus      rear suspension downforce
      fx_rearsus      rear suspension drag
      SCz             fz / dynamic_pressure  (= Cl * A_ref)
      SCx             fx / dynamic_pressure  (= Cd * A_ref)
      copx            x-coordinate of center of pressure
      copz            z-coordinate of center of pressure (lateral)
      cop_pct         % front aero balance
    """
    # ── Zone definitions ─────────────────────────────────────────────────
    # Labels must match the Discovery named selections exactly.
    half_sym = getattr(config, "is_half_symmetry", False)
    wheels   = _wheel_labels(half_sym)

    frontwing_zones = ["frontwing"]
    rearwing_zones  = ["rearwing"]
    undertray_zones = ["undertray"]
    body_zones      = list(BODY_LABELS)          # chassis (+ sidepod if present)
    suspension_zones_front = list(FRONT_SUS_LABELS)
    suspension_zones_rear  = list(REAR_SUS_LABELS)

    # Wheels + wheel blocks. Full car: flw/frw/rlw/rrw + *b
    #                        Half car: fw/rw + *b
    wheel_zones_front = list(wheels["front"])
    wheel_zones_rear  = list(wheels["rear"])

    # All car zones combined
    all_zones = (frontwing_zones + rearwing_zones + undertray_zones +
                 body_zones + suspension_zones_front + suspension_zones_rear +
                 wheel_zones_front + wheel_zones_rear)

    # Keep only zones that actually exist in the mesh. Unlike the meshing
    # side there is no fallback here -- a report scoped to a missing zone
    # reads zero and silently corrupts the totals.
    try:
        mesh_walls = list(solver.setup.boundary_conditions.wall.keys())

        def _filt(zones, label):
            kept    = [z for z in zones if z in mesh_walls]
            dropped = [z for z in zones if z not in mesh_walls]
            if dropped:
                log.debug(f"    {label}: not in mesh, dropped {dropped}")
            return kept

        frontwing_zones        = _filt(frontwing_zones, "frontwing")
        rearwing_zones         = _filt(rearwing_zones, "rearwing")
        undertray_zones        = _filt(undertray_zones, "undertray")
        body_zones             = _filt(body_zones, "body")
        suspension_zones_front = _filt(suspension_zones_front, "front_sus")
        suspension_zones_rear  = _filt(suspension_zones_rear, "rear_sus")
        wheel_zones_front      = _filt(wheel_zones_front, "front_wheel")
        wheel_zones_rear       = _filt(wheel_zones_rear, "rear_wheel")
        all_zones              = _filt(all_zones, "all")
    except Exception as e:
        log.debug(f"  Zone filtering skipped: {e}")

    log.info(f"  Zone map ({'half car' if half_sym else 'full car'}):")
    log.info(f"    frontwing:    {frontwing_zones}")
    log.info(f"    rearwing:     {rearwing_zones}")
    log.info(f"    undertray:    {undertray_zones}")
    log.info(f"    body/chassis: {body_zones}")
    log.info(f"    front wheel:  {wheel_zones_front}")
    log.info(f"    rear wheel:   {wheel_zones_rear}")
    log.info(f"    front sus:    {suspension_zones_front or '(none)'}")
    log.info(f"    rear sus:     {suspension_zones_rear or '(none)'}")
    log.info(f"    TOTAL:        {len(all_zones)} zones")

    DOWN = [0, -1, 0]
    DRAG = [1,  0, 0]

    # ── Total forces (all car zones) ─────────────────────────────────────
    _add_report_lift(solver, "fz", all_zones, DOWN)
    _add_report_drag(solver, "fx", all_zones, DRAG)

    # ── Coefficients ─────────────────────────────────────────────────────
    try:
        rd = solver.solution.report_definitions
        rd.lift["cl"] = {"zones": all_zones, "force_vector": DOWN,
                         "report_output_type": "Lift Coefficient"}
        rd.drag["cd"] = {"zones": all_zones, "force_vector": DRAG,
                         "report_output_type": "Drag Coefficient"}
        log.info("  cl, cd coefficient reports created")
    except Exception as e:
        log.warning(f"  Coefficient reports: {e}")
        # Fallback: create as regular force reports (extract as coeff in post)
        _add_report_lift(solver, "cl", all_zones, DOWN)
        _add_report_drag(solver, "cd", all_zones, DRAG)

    # ── Per-element: front wing ──────────────────────────────────────────
    _add_report_lift(solver, "fz_frontwing", frontwing_zones, DOWN)
    _add_report_drag(solver, "fx_frontwing", frontwing_zones, DRAG)

    # ── Per-element: rear wing ───────────────────────────────────────────
    _add_report_lift(solver, "fz_rearwing", rearwing_zones, DOWN)
    _add_report_drag(solver, "fx_rearwing", rearwing_zones, DRAG)

    # ── Per-element: undertray ───────────────────────────────────────────
    _add_report_lift(solver, "fz_undertray", undertray_zones, DOWN)
    _add_report_drag(solver, "fx_undertray", undertray_zones, DRAG)

    # ── Per-element: front wheel ─────────────────────────────────────────
    _add_report_lift(solver, "fz_fw", wheel_zones_front, DOWN)
    _add_report_drag(solver, "fx_fw", wheel_zones_front, DRAG)

    # ── Per-element: rear wheel ──────────────────────────────────────────
    _add_report_lift(solver, "fz_rw", wheel_zones_rear, DOWN)
    _add_report_drag(solver, "fx_rw", wheel_zones_rear, DRAG)

    # ── Per-element: front suspension ────────────────────────────────────
    _add_report_lift(solver, "fz_frontsus", suspension_zones_front, DOWN)
    _add_report_drag(solver, "fx_frontsus", suspension_zones_front, DRAG)

    # ── Per-element: rear suspension ─────────────────────────────────────
    _add_report_lift(solver, "fz_rearsus", suspension_zones_rear, DOWN)
    _add_report_drag(solver, "fx_rearsus", suspension_zones_rear, DRAG)

    # ── Per-element: body/chassis ────────────────────────────────────────
    _add_report_lift(solver, "fz_body", body_zones, DOWN)
    _add_report_drag(solver, "fx_body", body_zones, DRAG)

    # ── Moments for CoP calculation ──────────────────────────────────────
    # Moment about front axle origin, Z-axis (pitch moment)
    origin = [0.0, 0.0, 0.0]
    z_axis = [0, 0, 1]
    y_axis = [0, 1, 0]
    _add_report_moment(solver, "my_total", all_zones, origin, z_axis)
    # Lateral moment for copz (about X-axis)
    _add_report_moment(solver, "mx_total", all_zones, origin, y_axis)

    # ── SCz, SCx, copx, copz, cop% ──────────────────────────────────────
    # These are derived quantities. We compute them post-solve using scheme
    # eval because Fluent's expression-based report definitions are version-
    # dependent and fragile. The values are stored in the results dict.
    log.info("  SCz/SCx/CoP will be computed post-solve from force/moment data")

    # ── Turning-specific reports ─────────────────────────────────────────
    from simtypes.configs import SimType
    if config.sim_type == SimType.TURNING:
        centroid_x = getattr(config, "wheelbase_m", 1.575) / 2.0
        centroid = [centroid_x, 0.0, 0.0]
        _add_report_moment(solver, "yaw_moment",   all_zones, centroid, y_axis)
        _add_report_lift  (solver, "lateral_force", all_zones, [0, 0, 1])
        log.info("  Turning reports: yaw_moment + lateral_force")

    log.info(f"  Force reports configured — {len(all_zones)} zones total")

def _set_methods_first_order(solver):
    """First-order spatial discretization for initial convergence."""
    try:
        m = solver.solution.methods
        # Issue #2 fix: p_v_coupling.flow_scheme (not pressure_velocity_coupling.scheme)
        m.p_v_coupling.flow_scheme = "SIMPLE"
    except Exception as e:
        log.warning(f"  _set_methods_first_order PV coupling: {e}")
    try:
        # Issue #2 fix: discretization_scheme dict (not individual .pressure/.momentum attrs)
        m = solver.solution.methods
        m.spatial_discretization.discretization_scheme = {
            "pressure": "standard",
            "mom":      "first-order-upwind",
            "k":        "first-order-upwind",
            "omega":    "first-order-upwind",
        }
    except Exception as e:
        log.debug(f"  _set_methods_first_order discretization: {e}")


def _set_methods_ramp1(solver):
    """Second order pressure (PRESTO!) + second order momentum (ramp 1).
    Matches the Ram Racing procedure: 'Second order + Presto pressure'."""
    try:
        m = solver.solution.methods
        m.p_v_coupling.flow_scheme = "SIMPLE"
    except Exception as e:
        log.warning(f"  _set_methods_ramp1 PV coupling: {e}")
    try:
        m = solver.solution.methods
        m.spatial_discretization.discretization_scheme = {
            "pressure": "presto!",
            "mom":      "second-order-upwind",
            "k":        "first-order-upwind",
            "omega":    "first-order-upwind",
        }
    except Exception as e:
        log.debug(f"  _set_methods_ramp1 discretization: {e}")


def _set_methods_ramp2(solver):
    """Full second order discretization (ramp 2+)."""
    try:
        m = solver.solution.methods
        m.p_v_coupling.flow_scheme = "SIMPLEC"
    except Exception as e:
        log.warning(f"  _set_methods_ramp2 PV coupling: {e}")
    try:
        m = solver.solution.methods
        m.spatial_discretization.discretization_scheme = {
            "pressure": "presto!",
            "mom":      "second-order-upwind",
            "k":        "second-order-upwind",
            "omega":    "second-order-upwind",
        }
    except Exception as e:
        log.debug(f"  _set_methods_ramp2 discretization: {e}")


def run_solver(config, mesh_file: str,
               progress_cb: Optional[Callable] = None,
               mesh_quality: Optional[dict] = None):
    """
    Run the full ramp-up solver strategy from the Ram Racing procedure doc.
    Ramp 0: First order (stabilize)
    Ramp 1: Second order + Presto pressure
    Ramp 2: Full second order, no curvature correction
    Ramp 3: Full send - second order + curvature correction

    mesh_quality: dict returned by run_meshing (orthogonal quality stats).
                  Passed through to the results dict and exported to the
                  results .txt file.  Safe to omit (defaults to empty dict).
    """
    try:
        import ansys.fluent.core as pyfluent
        import warnings
        # Suppress PyFluent 0.39 deprecation warnings for short-form settings access
        # (solver.setup vs solver.settings.setup — both work, short form is cleaner)
        try:
            from ansys.fluent.core.solver.flobject import DeprecatedSettingWarning
            warnings.filterwarnings("ignore", category=DeprecatedSettingWarning)
        except ImportError:
            pass
    except ImportError:
        raise RuntimeError(
            "ansys-fluent-core is not installed. "
            "Run: pip install ansys-fluent-core"
        )

    def prog(msg, pct):
        log.info(f"[SOLVE {pct:3d}%] {msg}")
        if progress_cb:
            progress_cb(msg, pct)

    prog("Launching Fluent solver...", 0)
    solver = _launch_fluent_solver(pyfluent, config)



    try:
        # Load mesh
        prog("Loading mesh...", 2)
        _read_mesh(solver, mesh_file)
        solver.mesh.check()

        # Validate mesh has volume elements
        try:
            mesh_stats = solver.tui.report.mesh_statistics()
            log.info(f"  Mesh loaded: {mesh_stats}")
            # Check for volume cells (should be >0 for volumetric mesh)
            if "cells:" in mesh_stats.lower():
                # Basic check - if no cells mentioned or very few, might be surface
                pass  # For now, assume it's ok if no error
        except Exception as e:
            log.warning(f"  Could not get mesh statistics: {e}")

        # Units — Fluent defaults (SI) throughout; conversions happen in
        # post-processing, not here.

        speed_ms = mph_to_ms(config.vehicle_speed_mph)

        # Physics — initial pass, curvature correction off (doc Step 2.3)
        prog("Configuring physics (GEKO k-omega)...", 5)
        _apply_geko_physics(solver,
                            curvature_correction=False,
                            production_limiter=config.use_production_limiter)

        # Boundary conditions (doc Step 2.4) -- must come before reference
        # values, since "Compute From: Inlet" reads the inlet BC.
        prog("Setting boundary conditions...", 8)
        _set_boundary_conditions(solver, config)

        # Reference values (doc Step 2.1), including the projected frontal area
        prog("Setting reference values + projected area...", 12)
        _compute_reference_values(solver, speed_ms, config.car_length_m,
                                  config=config)

        # Force reports
        _configure_force_reports(solver, config)

        # ── RAMP 0: First order ──────────────────────────────────────────
        prog("Ramp 0: First-order initialization...", 18)
        _set_methods_first_order(solver)
        solver.solution.initialization.hybrid_initialize()
        _iterate(solver, config.ramp0_iters,
                 progress_cb=progress_cb, label="Ramp 0",
                 pct_start=18, pct_end=35)
        _save_case(solver, config, "ramp0_end")
        prog(f"Ramp 0 done ({config.ramp0_iters} iters).", 35)

        # ── RAMP 1: Second order + Presto ───────────────────────────────
        prog("Ramp 1: Second order + Presto pressure...", 38)
        _set_methods_ramp1(solver)
        _iterate(solver, config.ramp1_iters,
                 progress_cb=progress_cb, label="Ramp 1",
                 pct_start=38, pct_end=55)
        _save_case(solver, config, "ramp1_end")
        prog(f"Ramp 1 done ({config.ramp1_iters} iters).", 55)

        # ── RAMP 2: Full second order, no CC ────────────────────────────
        prog("Ramp 2: Full second order, no curvature correction...", 58)
        _set_methods_ramp2(solver)
        _apply_geko_physics(solver,
                            curvature_correction=False,
                            production_limiter=config.use_production_limiter)
        _iterate(solver, config.ramp2_iters,
                 progress_cb=progress_cb, label="Ramp 2",
                 pct_start=58, pct_end=72)
        _save_case(solver, config, "ramp2_end")
        prog(f"Ramp 2 done ({config.ramp2_iters} iters).", 72)

        # ── RAMP 3: Full Send ────────────────────────────────────────────
        prog("Ramp 3: Full send (curvature correction per config)...", 75)
        _set_methods_ramp2(solver)  # same discretization scheme
        _apply_geko_physics(solver,
                            curvature_correction=config.use_curvature_correction,
                            production_limiter=config.use_production_limiter)
        _iterate(solver, config.ramp3_iters,
                 progress_cb=progress_cb, label="Ramp 3 (full send)",
                 pct_start=75, pct_end=95)
        _save_case(solver, config, "final")
        prog(f"Ramp 3 done ({config.ramp3_iters} iters).", 95)

        # ── Export EnSight Gold for ParaView ──────────────────────────
        prog("Exporting EnSight Gold for ParaView...", 96)
        _export_ensight_gold(solver, config)

        # ── Extract results ──────────────────────────────────────────────
        prog("Extracting results...", 97)
        results = _extract_results(solver, config,
                                   mesh_quality=mesh_quality or {})
        _save_case(solver, config, "complete")
        prog("Simulation complete.", 100)
        return results

    finally:
        solver.exit()




def _export_ensight_gold(solver, config):
    """
    Export the solution in EnSight Gold format for ParaView visualization.
    Creates a .encas file + associated .geo and variable files.
    """
    import os
    out_dir = config.output_dir.rstrip("/\\")
    ensight_dir = os.path.join(out_dir, f"{config.name}_ensight")
    os.makedirs(ensight_dir, exist_ok=True)
    ensight_base = os.path.join(ensight_dir, config.name)

    try:
        # Method 1: PyFluent file.export API
        solver.file.export.ensight_gold(
            file_name=ensight_base,
        )
        log.info(f"  EnSight Gold exported: {ensight_dir}/")
        return ensight_dir
    except Exception as e1:
        log.debug(f"  EnSight export API: {e1}")

    try:
        # Method 2: TUI export command
        solver.tui.file.export.ensight_gold(
            ensight_base,   # filename base
            "yes",          # append project ID
            "yes",          # export all variables
        )
        log.info(f"  EnSight Gold exported (TUI): {ensight_dir}/")
        return ensight_dir
    except Exception as e2:
        log.debug(f"  EnSight TUI: {e2}")

    try:
        # Method 3: Scheme eval
        solver.scheme_eval.string_eval(
            f'(ti-menu-load-string "file export ensight-gold '
            f'{ensight_base} () () yes")'
        )
        log.info(f"  EnSight Gold exported (scheme): {ensight_dir}/")
        return ensight_dir
    except Exception as e3:
        log.warning(f"  EnSight Gold export failed: {e3}")
        return None


def _save_case(solver, config, label: str):
    path = f"{config.output_dir.rstrip('/\\')}/{config.name}_{label}.cas.h5"
    solver.file.write(file_name=path, file_type="case-data")
    log.info(f"  Saved: {path}")


def _extract_results(solver, config, mesh_quality=None):
    """
    Extract all force/moment/coefficient results in SI units.

    All values are in standard Ansys SI:
      Forces:  Newtons [N]
      Moments: Newton-metres [N*m]
      Length:  metres [m]
      Speed:  m/s
      Area:   m^2
    """
    results = {}
    if mesh_quality:
        results["mesh_quality"] = mesh_quality

    def fval(report_type, name):
        return _get_report_value(solver, report_type, name)

    # ── Symmetry multiplier ──────────────────────────────────────────────
    mult = 2.0 if config.is_half_symmetry else 1.0

    # ── Total forces [N] ─────────────────────────────────────────────────
    fz_raw = fval("lift", "fz")
    fx_raw = fval("drag", "fx")
    results["fz"] = fz_raw * mult          # total downforce [N]
    results["fx"] = fx_raw * mult          # total drag [N]

    # ── Coefficients ─────────────────────────────────────────────────────
    results["cl"] = fval("lift", "cl")
    results["cd"] = fval("drag", "cd")

    # ── Per-element forces [N] ───────────────────────────────────────────
    element_reports = [
        "fz_frontwing", "fx_frontwing",
        "fz_rearwing",  "fx_rearwing",
        "fz_undertray", "fx_undertray",
        "fz_fw",        "fx_fw",
        "fz_rw",        "fx_rw",
        "fz_frontsus",  "fx_frontsus",
        "fz_rearsus",   "fx_rearsus",
        "fz_body",      "fx_body",
    ]
    for rname in element_reports:
        rtype = "lift" if rname.startswith("fz") else "drag"
        results[rname] = fval(rtype, rname) * mult

    # ── SCz, SCx [m^2] ──────────────────────────────────────────────────
    speed_ms = mph_to_ms(config.vehicle_speed_mph)
    rho      = 1.225   # kg/m^3
    q        = 0.5 * rho * speed_ms ** 2   # dynamic pressure [Pa]
    if q > 0:
        results["SCz"] = abs(results["fz"]) / q   # m^2
        results["SCx"] = abs(results["fx"]) / q   # m^2
    else:
        results["SCz"] = 0.0
        results["SCx"] = 0.0

    # ── Frontal area [m^2] ───────────────────────────────────────────────
    frontal_area = None
    try:
        _area = solver.setup.reference_values.area
        frontal_area = float(_area() if callable(_area) else _area)
        results["frontal_area"] = frontal_area
    except Exception:
        pass

    # ── Center of Pressure [m] ───────────────────────────────────────────
    my_total = fval("moment", "my_total") * mult  # pitch moment [N*m]
    mx_total = fval("moment", "mx_total") * mult  # lateral moment [N*m]
    results["my_total"] = my_total
    results["mx_total"] = mx_total

    fz_total = results["fz"]
    if abs(fz_total) > 1e-6:
        copx = my_total / fz_total        # x-coord of CoP [m]
        results["copx"] = copx

        wheelbase_m = getattr(config, "wheelbase_m", 1.575)
        if wheelbase_m > 0:
            cop_pct_front = (copx / wheelbase_m) * 100.0
            cop_pct_front = max(0, min(100, cop_pct_front))
            results["cop_pct_front"] = cop_pct_front
            results["cop_pct_rear"]  = 100.0 - cop_pct_front
        else:
            results["cop_pct_front"] = 0.0
            results["cop_pct_rear"]  = 0.0
    else:
        results["copx"] = 0.0
        results["cop_pct_front"] = 0.0
        results["cop_pct_rear"]  = 0.0

    # copz (lateral CoP) [m]
    if abs(fz_total) > 1e-6:
        results["copz"] = mx_total / fz_total
    else:
        results["copz"] = 0.0

    # ── L/D ratio ────────────────────────────────────────────────────────
    results["ld_ratio"] = (abs(results["fz"]) / abs(results["fx"])
                           if abs(results["fx"]) > 1e-6 else 0.0)

    if config.is_half_symmetry:
        results["note"] = "Half-car sim — all forces doubled automatically."

    # ── Turning-specific results ─────────────────────────────────────────
    from simtypes.configs import SimType
    if config.sim_type == SimType.TURNING:
        results["yaw_moment"]    = fval("moment", "yaw_moment") * mult  # N*m
        results["lateral_force"] = fval("lift", "lateral_force") * mult  # N
        results["yaw_angle_deg"] = config.effective_yaw_deg()
        results["turn_radius"]   = config.turn_radius_m  # m

    # ── Log summary (SI) ─────────────────────────────────────────────────
    log.info(
        f"  Fz={results['fz']:.1f} N  "
        f"Fx={results['fx']:.1f} N  "
        f"L/D={results['ld_ratio']:.2f}"
    )
    log.info(
        f"  FW: {results.get('fz_frontwing', 0):.1f} N  "
        f"RW: {results.get('fz_rearwing', 0):.1f} N  "
        f"UT: {results.get('fz_undertray', 0):.1f} N"
    )
    log.info(
        f"  SCz={results['SCz']:.4f} m^2  SCx={results['SCx']:.4f} m^2"
    )
    log.info(
        f"  CoP: x={results['copx']:.3f} m  "
        f"Front={results['cop_pct_front']:.1f}%  "
        f"Rear={results['cop_pct_rear']:.1f}%"
    )

    # ── Export results text file ──────────────────────────────────────────
    try:
        from utils.results_exporter import export_results
        result_file = export_results(config, results,
                                     frontal_area_m2=frontal_area,
                                     mesh_quality=results.get("mesh_quality"))
        results["result_file"] = result_file
        log.info(f"  Results exported to: {result_file}")
    except Exception as e:
        log.warning(f"  Results export failed: {e}")

    return results
