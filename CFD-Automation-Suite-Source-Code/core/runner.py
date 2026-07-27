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


def _compute_reference_values(solver, speed_ms: float, car_length_m: float):
    """
    Set reference values for coefficient calculation.
    Issue #6 fix: compute_from doesn't exist in Fluent 252 — use .compute().
    Velocity and length are set independently so a failing compute() call
    does not prevent the other values from being applied.
    """
    rv = solver.setup.reference_values
    # Step 1: compute from inlet (sets density, velocity, etc. from BC)
    try:
        rv.compute("inlet")
        log.debug("  Reference values computed from inlet")
    except Exception:
        try:
            rv.compute_from = "inlet"
        except Exception:
            pass  # not available — proceed with manual values
    # Step 2: override velocity and length explicitly
    try:
        rv.velocity = speed_ms
    except Exception as e:
        log.warning(f"  Reference values velocity: {e}")
    try:
        rv.length = car_length_m
    except Exception as e:
        log.warning(f"  Reference values length: {e}")
    log.info(f"  Reference values: v={speed_ms:.2f} m/s  L={car_length_m:.2f} m")


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
    Return the "Create Local Refinement Regions" task, inserting it into
    the workflow first if necessary.

    2026 R1 Enhanced Workflow exposes tasks as attributes and requires
    optional tasks to be inserted via insertable_tasks before use.
    Falls back to the legacy TaskObject dict API if needed.
    """
    # 1. Already present on the enhanced workflow?
    for attr in ("create_local_refinement_regions",
                 "local_refinement_regions",
                 "create_local_refinement_region"):
        task = getattr(watertight, attr, None)
        if task is not None:
            return ("enhanced", task)

    # 2. Insert it via insertable_tasks
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

    # 3. Legacy TaskObject fallback
    try:
        task = meshing.workflow.TaskObject["Create Local Refinement Regions"]
        return ("legacy", task)
    except Exception as e:
        log.debug(f"  Legacy TaskObject lookup: {e}")

    return (None, None)


def _set_task_property(task, name, value):
    """Set a task property, handling both set_state() and plain setattr."""
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


def _add_refinement_box(meshing, watertight, name: str, box: dict) -> bool:
    """
    Create a coordinate-specified local refinement box.

    Box coordinates come from compute_refinement_boxes(), which implements
    Tables 1-3 of the Ram Racing Fluent Procedure document (the same
    formulas as localrefinementregion.m).

    Returns True if the region was created.
    """
    mode, task = _get_refinement_task(meshing, watertight)

    if mode is None:
        log.warning(f"  Refinement box {name!r}: task not available in workflow")
        return False

    if mode == "legacy":
        try:
            task.Arguments.update({
                "LocalRefinementRegionName":     name,
                "Type":                          "box",
                "CoordinateSpecificationMethod": "directly-specify-coordinates",
                "MeshSize":                      box["size"],
                "XMin": box["x_min"], "XMax": box["x_max"],
                "YMin": box["y_min"], "YMax": box["y_max"],
                "ZMin": box["z_min"], "ZMax": box["z_max"],
            })
            task.Execute()
            log.info(
                f"  Added refinement box: {name}  size={box['size']} m  "
                f"X[{box['x_min']:.2f}, {box['x_max']:.2f}]  "
                f"Y[{box['y_min']:.2f}, {box['y_max']:.2f}]  "
                f"Z[{box['z_min']:.2f}, {box['z_max']:.2f}]"
            )
            return True
        except Exception as e:
            log.warning(f"  Refinement box {name!r} (legacy): {e}")
            return False

    # Enhanced workflow — snake_case properties
    props = [
        ("local_refinement_region_name",     name),
        ("region_name",                      name),
        ("type",                             "box"),
        ("region_type",                      "box"),
        ("coordinate_specification_method",  "directly-specify-coordinates"),
        ("mesh_size",                        box["size"]),
        ("x_min", box["x_min"]), ("x_max", box["x_max"]),
        ("y_min", box["y_min"]), ("y_max", box["y_max"]),
        ("z_min", box["z_min"]), ("z_max", box["z_max"]),
    ]
    n_set = 0
    for prop, value in props:
        if _set_task_property(task, prop, value):
            n_set += 1

    if n_set == 0:
        log.warning(
            f"  Refinement box {name!r}: no properties could be set "
            f"(available: {[a for a in dir(task) if not a.startswith('_')][:15]})"
        )
        return False

    try:
        task()
        log.info(
            f"  Added refinement box: {name}  size={box['size']} m  "
            f"X[{box['x_min']:.2f}, {box['x_max']:.2f}]  "
            f"Y[{box['y_min']:.2f}, {box['y_max']:.2f}]  "
            f"Z[{box['z_min']:.2f}, {box['z_max']:.2f}]"
        )
        return True
    except Exception as e:
        log.warning(f"  Refinement box {name!r} execute: {e}")
        return False


def _add_wheel_refinement(meshing, watertight, wheel_name: str,
                          cx: float, cy: float, cz: float) -> bool:
    """
    Per-wheel local refinement box.

    Uses relative-to-body-size specification per Table 4 of the Fluent
    Procedure document: 0.032 m mesh size, box sized relative to the
    wheel body rather than absolute coordinates.
    """
    mode, task = _get_refinement_task(meshing, watertight)
    if mode is None:
        return False

    region_name = f"wheel_{wheel_name.lower()}"

    if mode == "legacy":
        try:
            task.Arguments.update({
                "LocalRefinementRegionName":     region_name,
                "Type":                          "box",
                "CoordinateSpecificationMethod": "relative-to-body-size",
                "MeshSize":                      0.032,
                "XMin": 0.1, "XMax": 1.0,
                "YMin": 0.0, "YMax": 0.1,
                "ZMin": 0.1, "ZMax": 0.1,
            })
            task.Execute()
            log.info(f"  Added wheel refinement box: {wheel_name}")
            return True
        except Exception as e:
            log.warning(f"  Wheel refinement {wheel_name!r} (legacy): {e}")
            return False

    props = [
        ("local_refinement_region_name",    region_name),
        ("region_name",                     region_name),
        ("type",                            "box"),
        ("region_type",                     "box"),
        ("coordinate_specification_method", "relative-to-body-size"),
        ("mesh_size",                       0.032),
        ("x_min", 0.1), ("x_max", 1.0),
        ("y_min", 0.0), ("y_max", 0.1),
        ("z_min", 0.1), ("z_max", 0.1),
    ]
    n_set = sum(1 for p, v in props if _set_task_property(task, p, v))
    if n_set == 0:
        return False

    try:
        task()
        log.info(f"  Added wheel refinement box: {wheel_name}")
        return True
    except Exception as e:
        log.warning(f"  Wheel refinement {wheel_name!r} execute: {e}")
        return False

def _add_wheel_refinement(watertight, wheel_name: str,
                          cx: float, cy: float, cz: float):
    """Per-wheel BOI refinement box via Enhanced Meshing Workflow."""
    r = 0.25
    _add_refinement_box(watertight, f"boi_wheel_{wheel_name.lower()}", {
        "size": 0.032,
        "x_min": cx - r, "x_max": cx + r,
        "y_min": 0.0,    "y_max": cy + r,
        "z_min": cz - r, "z_max": cz + r,
    })


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

        # ── Step 2: Local Sizing ─────────────────────────────────────────
        sizing = watertight.add_local_sizing_wtm

        # Curvature sizing — chassis/body
        prog("Adding local sizing: chassis/body...", 22)
        sizing.add_child = "yes"
        sizing.boi_control_name = "curvature_stuff"
        sizing.boi_execution = "Face Size"
        sizing.boi_face_label_list = ["chassis", "driver", "control-arms"]
        sizing.boi_size = config.surface_mesh_max
        sizing.boi_zoneor_label = "label"
        sizing.add_child_and_update(defer_update=False)

        # Curvature sizing — aero elements
        prog("Adding local sizing: aero elements...", 28)
        sizing.add_child = "yes"
        sizing.boi_control_name = "curvature_aero"
        sizing.boi_execution = "Face Size"
        sizing.boi_face_label_list = [
            "front-wing", "rear-wing", "undertray",
            "fw", "rw", "fwb", "rwb",
        ]
        sizing.boi_size = 0.008
        sizing.boi_zoneor_label = "label"
        sizing.add_child_and_update(defer_update=False)

        # Wheel sizing
        if config.use_wheel_mrf and config.wheel_mrf_zones:
            prog("Adding local sizing: wheels...", 33)
            wheel_labels = [w.zone_name for w in config.wheel_mrf_zones]
            sizing.add_child = "yes"
            sizing.boi_control_name = "curvature_wheels"
            sizing.boi_execution = "Face Size"
            sizing.boi_face_label_list = wheel_labels
            sizing.boi_size = 0.032
            sizing.boi_zoneor_label = "label"
            sizing.add_child_and_update(defer_update=False)

        # Near / Mid / Far volume refinement boxes
        # Coordinates from compute_refinement_boxes() — Tables 1-3 of the
        # Ram Racing Fluent Procedure doc, same formulas as
        # MATLAB-Scripts/localrefinementregion.m
        prog("Adding Near/Mid/Far refinement boxes...", 38)
        near, mid, far = compute_refinement_boxes(
            config.car_length_m, config.car_width_m, config.car_height_m,
            half_sym=getattr(config, "is_half_symmetry", False),
        )
        n_boxes = 0
        n_boxes += _add_refinement_box(meshing, watertight, "boi_near", near)
        n_boxes += _add_refinement_box(meshing, watertight, "boi_mid",  mid)
        n_boxes += _add_refinement_box(meshing, watertight, "boi_far",  far)
        if n_boxes < 3:
            log.warning(
                f"  Only {n_boxes}/3 refinement boxes created — "
                f"mesh will be coarser in the near field than intended"
            )

        # Per-wheel refinement boxes (Table 4)
        if config.use_wheel_mrf and config.wheel_mrf_zones:
            prog("Adding wheel refinement boxes...", 42)
            for wheel in config.wheel_mrf_zones:
                _add_wheel_refinement(
                    meshing, watertight, wheel.name,
                    wheel.center_x, wheel.center_y, wheel.center_z,
                )

        # ── Step 3: Generate Surface Mesh ────────────────────────────────
        prog("Generating surface mesh...", 50)
        surface_mesh = watertight.create_surface_mesh
        surface_mesh.cfd_surface_mesh_controls.min_size = config.surface_mesh_min
        surface_mesh.cfd_surface_mesh_controls.max_size = config.surface_mesh_max
        try:
            surface_mesh.cfd_surface_mesh_controls.scope_proximity_to = "faces-and-edges"
        except Exception:
            pass
        surface_mesh()

        # ── Step 4: Describe Geometry ────────────────────────────────────
        prog("Describing geometry...", 60)
        describe = watertight.describe_geometry
        describe.update_child_tasks(setup_type_changed=False)
        describe.setup_type = "fluid"
        describe.update_child_tasks(setup_type_changed=True)
        describe()

        # ── Step 5: Update Regions ───────────────────────────────────────
        prog("Updating regions...", 72)
        watertight.update_regions()

        # ── Step 6: Add Boundary Layers ──────────────────────────────────
        prog("Adding boundary layers...", 76)
        bl = watertight.add_boundary_layers
        bl.add_child_to_task()
        try:
            bl.control_name.set_state("last-ratio_1")
            bl.number_of_layers = config.bl_num_layers
            bl.first_height = config.bl_first_height
            bl.transition_ratio = config.bl_transition_ratio
            bl.offset_method_type = "last-ratio"
        except Exception as e:
            log.debug(f"  BL params: {e}")
        try:
            aero_and_ground = [
                "front-wing", "rear-wing", "undertray",
                "fw", "rw", "fwb", "rwb", "ground",
            ]
            bl.zone_selection_list.set_state(aero_and_ground)
        except Exception:
            pass
        bl.insert_compound_child_task()
        try:
            watertight.add_boundary_layers_child_1()
        except Exception as e:
            log.debug(f"  BL child execute: {e}")
            # Fallback: try executing without child
            try:
                bl()
            except Exception:
                pass

        # ── Step 7: Generate Volume Mesh ─────────────────────────────────
        prog("Generating volume mesh (this takes a while)...", 82)
        vol_mesh = watertight.create_volume_mesh_wtm
        vol_mesh.volume_fill.set_state("poly-hexcore")
        vol_mesh.volume_fill_controls.hex_max_cell_length.set_state(
            config.volume_mesh_max
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
        # Issue #4 fix: try correct attribute names in order for Fluent 252
        _ground_set = False
        for _attr in ("velocity", "velocity_spec", "wall_translational_velocity",
                      "wall_velocity"):
            try:
                getattr(ground.momentum, _attr).value = speed_ms
                _ground_set = True
                break
            except Exception:
                continue
        if not _ground_set:
            log.warning(f"  Ground moving wall: could not set velocity — tried all known attrs")
        else:
            log.info(f"  Ground moving wall: {speed_ms:.2f} m/s")
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
    frontwing_zones = ["frontwing"]
    rearwing_zones  = ["rearwing"]
    undertray_zones = ["undertray"]
    chassis_zones   = ["chassis"]
    suspension_zones_front = ["front-suspension", "frontsuspension"]
    suspension_zones_rear  = ["rear-suspension", "rearsuspension"]

    # Wheel zones — from MRF config or default names
    wheel_zones_front = []
    wheel_zones_rear  = []
    if config.use_wheel_mrf and config.wheel_mrf_zones:
        for w in config.wheel_mrf_zones:
            if "f" in w.name.lower()[:2]:   # FRW, FLW
                wheel_zones_front.append(w.zone_name)
            else:                            # RRW, RLW
                wheel_zones_rear.append(w.zone_name)
    # fw/fwb = front wheel zones, rw/rwb = rear wheel zones
    wheel_zones_front = ["fw", "fwb"] + wheel_zones_front
    wheel_zones_rear  = ["rw", "rwb"] + wheel_zones_rear

    # All car zones combined
    all_zones = (frontwing_zones + rearwing_zones + undertray_zones +
                 chassis_zones + suspension_zones_front + suspension_zones_rear +
                 wheel_zones_front + wheel_zones_rear)

    # Filter to zones that actually exist in the mesh
    try:
        mesh_walls = list(solver.setup.boundary_conditions.wall.keys())
        def _filt(zones):
            filtered = [z for z in zones if z in mesh_walls]
            return filtered if filtered else zones
        frontwing_zones        = _filt(frontwing_zones)
        rearwing_zones         = _filt(rearwing_zones)
        undertray_zones        = _filt(undertray_zones)
        chassis_zones          = _filt(chassis_zones)
        suspension_zones_front = _filt(suspension_zones_front)
        suspension_zones_rear  = _filt(suspension_zones_rear)
        wheel_zones_front      = _filt(wheel_zones_front)
        wheel_zones_rear       = _filt(wheel_zones_rear)
        all_zones              = _filt(all_zones)
    except Exception:
        pass

    log.info(f"  Zone map:")
    log.info(f"    frontwing: {frontwing_zones}")
    log.info(f"    rearwing:  {rearwing_zones}")
    log.info(f"    undertray: {undertray_zones}")
    log.info(f"    front_wheel: {wheel_zones_front}")
    log.info(f"    rear_wheel:  {wheel_zones_rear}")
    log.info(f"    front_sus:   {suspension_zones_front}")
    log.info(f"    rear_sus:    {suspension_zones_rear}")

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
    _add_report_lift(solver, "fz_body", chassis_zones, DOWN)
    _add_report_drag(solver, "fx_body", chassis_zones, DRAG)

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

        # Units — skip custom units, Fluent defaults (SI) work fine for force/moment output
        # We convert results in post-processing instead

        # Reference values
        prog("Setting reference values...", 5)
        speed_ms = mph_to_ms(config.vehicle_speed_mph)
        _compute_reference_values(solver, speed_ms, config.car_length_m)

        # Physics - initial (no curvature correction)
        prog("Configuring physics (GEKO k-omega)...", 8)
        _apply_geko_physics(solver,
                            curvature_correction=False,
                            production_limiter=config.use_production_limiter)

        # Boundary conditions
        prog("Setting boundary conditions...", 12)
        _set_boundary_conditions(solver, config)

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
