"""
Core PyFluent automation - meshing workflow and solver ramp-up strategy
based on Ram Racing Fluent Procedure doc.

Requires: ansys-fluent-core (pip install ansys-fluent-core)
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
_AWP_KEY   = "AWP_ROOT252"
_PV        = "25.2"          # product_version string for launch_fluent()

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
    """Set AWP_ROOT252 if not already in env. Searches common install paths."""
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
        "/ansys_inc/v252/fluent",
        "/usr/ansys_inc/v252/fluent",
        "/opt/ansys_inc/v252/fluent",
        "/apps/ansys/v252/fluent",
        "/apps/ansys_inc/v252/fluent",
        # Windows
        "C:/Program Files/ANSYS Inc/v252/fluent",
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
        f"  export {_AWP_KEY}=/path/to/ansys_inc/v252"
    )


def _launch_fluent(pyfluent, config, mode: str):
    """Launch Fluent in the given mode targeting Ansys 2025 R2."""
    _ensure_awp_root()
    timeout = getattr(config, "launch_timeout", FLUENT_LAUNCH_TIMEOUT)
    kwargs = dict(
        mode            = mode,
        precision       = "double" if config.double_precision else "single",
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

    # Approach 3: update_dict (only unset keys)
    try:
        args_obj.update_dict(failed_keys)
        return
    except Exception as e:
        log.warning(f"  All arg-setting methods failed for {list(failed_keys.keys())}: {e}")


def _hybrid_init(solver):
    """Hybrid initialization."""
    solver.solution.initialization.hybrid_initialize()


def _iterate(solver, n: int):
    """Run n iterations."""
    solver.solution.run_calculation.iterate(number_of_iterations=n)


def _set_discretization(solver, scheme: str, field: str):
    """Set spatial discretization scheme."""
    methods = solver.solution.methods
    if field == "pressure_velocity_coupling":
        methods.pressure_velocity_coupling.scheme = scheme
        return
    try:
        methods.spatial_discretization.__setattr__(field, scheme)
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
    try:
        solver.solution.report_definitions.moment[name] = {
            "zones": zones, "moment_center": center, "moment_axis": axis,
        }
    except Exception as e:
        log.warning(f"  Moment report {name!r}: {e}")


def _get_report_value(solver, report_type: str, name: str) -> float:
    try:
        rd = solver.solution.report_definitions
        if report_type == "lift":
            return rd.lift[name].get_monitor_value()
        elif report_type == "drag":
            return rd.drag[name].get_monitor_value()
        else:
            return rd.moment[name].get_monitor_value()
    except Exception as e:
        log.warning(f"  Report {name!r}: {e}")
        return 0.0


def _compute_reference_values(solver, speed_ms: float, car_length_m: float):
    """Set reference values for coefficient calculation."""
    try:
        rv = solver.setup.reference_values
        rv.compute_from = "inlet"
        rv.velocity     = speed_ms
        rv.length       = car_length_m
    except Exception as e:
        log.warning(f"  Reference values: {e}")


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


def _add_refinement_box(meshing, name: str, box: dict):
    """
    Create a local refinement box via Add Local Sizing task.
    In Fluent 252 Watertight workflow, BOI (Body of Influence) sizing
    replaces the separate 'Create Local Refinement Regions' task.
    Each refinement region is added as a child sizing with Type=body-of-influence.
    """
    workflow = meshing.workflow
    task = workflow.TaskObject["Add Local Sizing"]
    try:
        task.AddChildToTask()
    except Exception:
        pass
    _exec_task(task, {
        "Name":             name,
        "Size Control Type": "body-of-influence",
        "BOI Type":         "box",
        "Mesh Size":        box["size"],
        "BOI X Min":        box["x_min"], "BOI X Max": box["x_max"],
        "BOI Y Min":        box["y_min"], "BOI Y Max": box["y_max"],
        "BOI Z Min":        box["z_min"], "BOI Z Max": box["z_max"],
    })
    log.info(f"  Added refinement box: {name}")


def _add_wheel_refinement(meshing, wheel_name: str,
                          cx: float, cy: float, cz: float):
    """Per-wheel BOI refinement box via Add Local Sizing."""
    workflow = meshing.workflow
    task = workflow.TaskObject["Add Local Sizing"]
    r = 0.25   # 250mm box half-size around wheel center
    try:
        task.AddChildToTask()
    except Exception:
        pass
    _exec_task(task, {
        "Name":             f"boi_wheel_{wheel_name.lower()}",
        "Size Control Type": "body-of-influence",
        "BOI Type":         "box",
        "Mesh Size":        0.032,
        "BOI X Min":        cx - r, "BOI X Max": cx + r,
        "BOI Y Min":        0.0,    "BOI Y Max": cy + r,
        "BOI Z Min":        cz - r, "BOI Z Max": cz + r,
    })
    log.info(f"  Added wheel refinement box: {wheel_name}")


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
    Based on PyFluent docs: task.Arguments = dict(...) then task.Execute()
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
        workflow = meshing.workflow
        workflow.InitializeWorkflow(WorkflowType="Watertight Geometry")
        tasks = workflow.TaskObject

        # ── Step 1: Import Geometry ──────────────────────────────────────
        prog("Importing geometry...", 5)
        log.info(f"  Geometry: {config.geometry_path!r}")
        tasks["Import Geometry"].Arguments = {
            "FileName":   config.geometry_path,
            "LengthUnit": "m",
        }
        tasks["Import Geometry"].Execute()

        # ── Step 2: Local Sizing ─────────────────────────────────────────
        # Curvature sizing — chassis/body
        prog("Adding local sizing: chassis/body...", 22)
        tasks["Add Local Sizing"].Arguments = {
            "AddChild": "yes",
            "BOIControlName": "curvature_stuff",
            "BOIExecution": "Face Size",
            "BOIFaceLabelList": ["chassis", "driver", "control-arms"],
            "BOISize": config.surface_mesh_max,
        }
        tasks["Add Local Sizing"].AddChildAndUpdate()

        # Curvature sizing — aero elements
        prog("Adding local sizing: aero elements...", 28)
        tasks["Add Local Sizing"].Arguments = {
            "AddChild": "yes",
            "BOIControlName": "curvature_aero",
            "BOIExecution": "Face Size",
            "BOIFaceLabelList": [
                "front-wing", "rear-wing", "undertray",
                "fw", "rw", "fwb", "rwb",
            ],
            "BOISize": 0.008,
        }
        tasks["Add Local Sizing"].AddChildAndUpdate()

        # Wheel sizing
        if config.use_wheel_mrf and config.wheel_mrf_zones:
            prog("Adding local sizing: wheels...", 33)
            wheel_labels = [w.zone_name for w in config.wheel_mrf_zones]
            tasks["Add Local Sizing"].Arguments = {
                "AddChild": "yes",
                "BOIControlName": "curvature_wheels",
                "BOIExecution": "Face Size",
                "BOIFaceLabelList": wheel_labels,
                "BOISize": 0.032,
            }
            tasks["Add Local Sizing"].AddChildAndUpdate()

        # Near / Mid / Far volume refinement boxes (Tables 1-3, Fluent Procedure doc)
        prog("Adding Near/Mid/Far refinement boxes...", 38)
        near, mid, far = compute_refinement_boxes(
            config.car_length_m, config.car_width_m, config.car_height_m,
            half_sym=getattr(config, "is_half_symmetry", False),
        )
        _add_refinement_box(meshing, "boi_near", near)
        _add_refinement_box(meshing, "boi_mid",  mid)
        _add_refinement_box(meshing, "boi_far",  far)

        # Per-wheel refinement boxes
        if config.use_wheel_mrf and config.wheel_mrf_zones:
            prog("Adding wheel refinement boxes...", 42)
            for wheel in config.wheel_mrf_zones:
                _add_wheel_refinement(
                    meshing, wheel.name,
                    wheel.center_x, wheel.center_y, wheel.center_z,
                )

        # ── Step 3: Generate Surface Mesh ────────────────────────────────
        prog("Generating surface mesh...", 50)
        tasks["Generate the Surface Mesh"].Arguments = {
            "CFDSurfaceMeshControls": {
                "MinSize": config.surface_mesh_min,
                "MaxSize": config.surface_mesh_max,
                "ScopeProximityTo": "faces-and-edges",
            },
            "SurfaceMeshPreferences": {
                "SmoothFoldedFacesLimit": 100,
            },
        }
        # Enable smooth-folded-faces via TUI before executing surface mesh
        # This allows Fluent to repair self-intersecting faces automatically
        try:
            meshing.tui.objects.wrap.set.use_smooth_folded_faces("yes")
            log.info("  use_smooth_folded_faces enabled")
        except Exception as e:
            log.debug(f"  use_smooth_folded_faces TUI call skipped: {e}")
        tasks["Generate the Surface Mesh"].Execute()

        # ── Step 4: Describe Geometry ────────────────────────────────────
        prog("Describing geometry...", 60)
        tasks["Describe Geometry"].Arguments = {
            "SetupType": "The geometry consists of only fluid regions with no voids",
            "WallToInternal": "No",
            "InvokeShareTopology": "No",
        }
        tasks["Describe Geometry"].Execute()

        # ── Step 5: Update Boundaries ────────────────────────────────────
        prog("Updating boundaries...", 68)
        tasks["Update Boundaries"].Execute()

        # ── Step 6: Create + Update Regions ─────────────────────────────
        prog("Updating regions...", 72)
        try:
            tasks["Create Regions"].Execute()
        except Exception as e:
            log.debug(f"  Create Regions: {e}")

        # Assign region types before Update Regions:
        # Any region whose name contains "enclosure" is fluid (poly-hexcore).
        # Everything else (car body volumes etc.) is solid (none = skip meshing).
        try:
            import re as _re
            gs = meshing.meshing.GlobalSettings
            all_regions = list(gs.FTMRegionData.AllRegionNameList.get_state())
            if all_regions:
                types  = []
                fills  = []
                for r in all_regions:
                    if "enclosure" in r.lower():
                        types.append("fluid")
                        fills.append("poly-hexcore")
                    else:
                        types.append("solid")
                        fills.append("none")
                log.info(f"  Regions: {list(zip(all_regions, types))}")
                tasks["Update Regions"].Arguments = {
                    "AllRegionNameList":       all_regions,
                    "AllRegionTypeList":       types,
                    "AllRegionVolumeFillList": fills,
                }
            else:
                log.debug("  No region list available, letting Fluent auto-assign")
        except Exception as e:
            log.debug(f"  Update Regions args: {e}")
        tasks["Update Regions"].Execute()

        # ── Step 7: Add Boundary Layers ──────────────────────────────────
        prog("Adding boundary layers...", 76)
        aero_and_ground = [
            "front-wing", "rear-wing", "undertray",
            "fw", "rw", "fwb", "rwb", "ground",
        ]
        tasks["Add Boundary Layers"].Arguments = {
            "AddChild": "yes",
            "FLParams": {
                "BLControlName":    "last-ratio_1",
                "NumberOfLayers":   config.bl_num_layers,
                "TransitionRatio":  config.bl_transition_ratio,
                "FirstHeight":      config.bl_first_height,
                "OffsetMethod":     "last-ratio",
            },
            "FLZoneList": aero_and_ground,
        }
        tasks["Add Boundary Layers"].AddChildAndUpdate()

        # ── Step 8: Generate Volume Mesh ─────────────────────────────────
        prog("Generating volume mesh (this takes a while)...", 82)
        tasks["Generate the Volume Mesh"].Arguments = {
            "VolumeFill": "poly-hexcore",
            "VolumeFillControls": {
                "HexMaxCellLength": config.volume_mesh_max,
            },
        }
        tasks["Generate the Volume Mesh"].Execute()

        # ── Save mesh ────────────────────────────────────────────────────
        prog("Improving volume mesh...", 93)
        try:
            meshing.meshing.ImproveVolumeMesh(
                QualityMethod="Orthogonal",
                CellQualityLimit=0.2
            )
        except Exception as e:
            log.warning(f"  ImproveVolumeMesh skipped: {e}")

        # ── Extract mesh quality BEFORE closing the meshing session ──────
        prog("Extracting mesh quality statistics...", 95)
        mesh_quality = _extract_mesh_quality(meshing)

        if not mesh_quality["oq_pass"]:
            log.warning(
                f"  Mesh quality check: {mesh_quality['oq_note']}  "
                f"(min={mesh_quality['oq_min']:.4f})"
            )
        else:
            log.info(f"  Mesh quality check: {mesh_quality['oq_note']}")

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
    speed_ms = mph_to_ms(config.vehicle_speed_mph)
    try:
        # Inlet — velocity inlet
        inlet = solver.setup.boundary_conditions.velocity_inlet["inlet"]
        try:
            inlet.momentum.velocity.value = speed_ms
        except Exception:
            inlet.momentum.velocity_magnitude.value = speed_ms
        try:
            inlet.turbulence.turbulent_intensity = 0.01
            inlet.turbulence.turbulent_viscosity_ratio = 1.0
        except Exception:
            pass
        log.info(f"  Inlet: {speed_ms:.2f} m/s")
    except Exception as e:
        log.warning(f"  Inlet BC: {e}")

    try:
        # Outlet — pressure outlet (0 Pa gauge)
        outlet = solver.setup.boundary_conditions.pressure_outlet["outlet"]
        try:
            outlet.momentum.gauge_pressure.value = 0.0
        except Exception:
            pass
        log.info("  Outlet: 0 Pa gauge")
    except Exception as e:
        log.warning(f"  Outlet BC: {e}")

    try:
        # Ground — moving wall at vehicle speed
        ground = solver.setup.boundary_conditions.wall["ground"]
        ground.momentum.wall_motion = "Moving Wall"
        try:
            ground.momentum.velocity.value = speed_ms
        except Exception:
            ground.momentum.wall_velocity.value = speed_ms
        log.info(f"  Ground moving wall: {speed_ms:.2f} m/s")
    except Exception as e:
        log.warning(f"  Ground BC: {e}")

    try:
        # Symmetry
        solver.setup.boundary_conditions.symmetry["symmetry"]
        log.info("  Symmetry plane: OK")
    except Exception as e:
        log.debug(f"  Symmetry BC: {e}")

    # Wheel MRF
    if config.use_wheel_mrf:
        for wheel in config.wheel_mrf_zones:
            try:
                if wheel.rpm > 0:
                    omega = wheel.rpm * 2 * math.pi / 60  # explicit override
                    log.info(f"  Wheel MRF {wheel.name}: using RPM override {wheel.rpm:.1f} → {omega:.2f} rad/s")
                else:
                    omega = speed_ms / wheel.wheel_radius  # auto-calculate
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
    """Set up lift/drag/moment report definitions for all aero surfaces."""
    aero_zones = [
        "frontwing", "rearwing", "undertray",
        "fw", "rw", "fwb", "rwb", "chassis",
    ]
    fw_zones  = ["fw", "fwb", "frontwing"]
    rw_zones  = ["rw", "rwb", "rearwing"]
    ut_zones  = ["undertray"]
    all_aero  = fw_zones + rw_zones + ut_zones + ["chassis"]

    # Filter to zones that actually exist in the mesh
    try:
        all_zones = list(solver.setup.boundary_conditions.wall.keys())
        def _filter(zones):
            filtered = [z for z in zones if z in all_zones]
            return filtered if filtered else zones  # fall back if none matched
        fw_zones  = _filter(fw_zones)
        rw_zones  = _filter(rw_zones)
        ut_zones  = _filter(ut_zones)
        all_aero  = _filter(all_aero)
    except Exception:
        pass

    # ── Totals ──────────────────────────────────────────────────────────────
    # Names match the keys used in _extract_results exactly.
    _add_report_lift  (solver, "total_downforce", all_aero, [0, -1, 0])
    _add_report_drag  (solver, "total_drag",      all_aero, [1,  0, 0])
    _add_report_drag  (solver, "drag_aero",       fw_zones + rw_zones + ut_zones, [1, 0, 0])

    # ── Per-element downforce ────────────────────────────────────────────────
    _add_report_lift(solver, "downforce_fw", fw_zones, [0, -1, 0])
    _add_report_lift(solver, "downforce_rw", rw_zones, [0, -1, 0])
    _add_report_lift(solver, "downforce_ut", ut_zones, [0, -1, 0])

    # ── Per-element drag ─────────────────────────────────────────────────────
    _add_report_drag(solver, "drag_total", all_aero,  [1, 0, 0])
    _add_report_drag(solver, "drag_rw",    rw_zones,  [1, 0, 0])

    # ── Per-element pitching moments about front axle (Z axis, origin) ───────
    # Used by _derive_cop in results_exporter to compute CoP without hand-measured
    # geometry constants.  Axis = [0,0,1] (Z), center = [0,0,0] (front axle origin).
    front_axle = [0.0, 0.0, 0.0]
    z_axis     = [0,   0,   1  ]
    _add_report_moment(solver, "moment_fw",    fw_zones, front_axle, z_axis)
    _add_report_moment(solver, "moment_rw",    rw_zones, front_axle, z_axis)
    _add_report_moment(solver, "moment_ut",    ut_zones, front_axle, z_axis)
    _add_report_moment(solver, "moment_total", all_aero, front_axle, z_axis)

    log.info(
        f"  Force reports configured — "
        f"FW zones: {fw_zones}  RW zones: {rw_zones}  UT zones: {ut_zones}"
    )


def _set_methods_first_order(solver):
    """First-order spatial discretization for initial convergence."""
    try:
        m = solver.solution.methods
        m.pressure_velocity_coupling.scheme = "SIMPLE"
        try:
            m.spatial_discretization.pressure = "Standard"
            m.spatial_discretization.momentum = "First Order Upwind"
            m.spatial_discretization.turbulent_kinetic_energy = "First Order Upwind"
            m.spatial_discretization.specific_dissipation_rate = "First Order Upwind"
        except Exception as e:
            log.debug(f"  Methods (first order): {e}")
    except Exception as e:
        log.warning(f"  _set_methods_first_order: {e}")


def _set_methods_ramp1(solver):
    """Second order pressure (PRESTO!) + second order momentum (ramp 1).
    Matches the Ram Racing procedure: 'Second order + Presto pressure'."""
    try:
        m = solver.solution.methods
        m.pressure_velocity_coupling.scheme = "SIMPLE"
        try:
            m.spatial_discretization.pressure = "PRESTO!"
            m.spatial_discretization.momentum = "Second Order Upwind"
            m.spatial_discretization.turbulent_kinetic_energy = "First Order Upwind"
            m.spatial_discretization.specific_dissipation_rate = "First Order Upwind"
        except Exception as e:
            log.debug(f"  Methods (ramp1): {e}")
    except Exception as e:
        log.warning(f"  _set_methods_ramp1: {e}")


def _set_methods_ramp2(solver):
    """Full second order discretization (ramp 2+)."""
    try:
        m = solver.solution.methods
        m.pressure_velocity_coupling.scheme = "SIMPLEC"
        try:
            m.spatial_discretization.pressure = "PRESTO!"
            m.spatial_discretization.momentum = "Second Order Upwind"
            m.spatial_discretization.turbulent_kinetic_energy = "Second Order Upwind"
            m.spatial_discretization.specific_dissipation_rate = "Second Order Upwind"
        except Exception as e:
            log.debug(f"  Methods (ramp2): {e}")
    except Exception as e:
        log.warning(f"  _set_methods_ramp2: {e}")


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
        _iterate(solver, config.ramp0_iters
        )
        _save_case(solver, config, "ramp0_end")
        prog(f"Ramp 0 done ({config.ramp0_iters} iters).", 35)

        # ── RAMP 1: Second order + Presto ───────────────────────────────
        prog("Ramp 1: Second order + Presto pressure...", 38)
        _set_methods_ramp1(solver)
        _iterate(solver, config.ramp1_iters
        )
        _save_case(solver, config, "ramp1_end")
        prog(f"Ramp 1 done ({config.ramp1_iters} iters).", 55)

        # ── RAMP 2: Full second order, no CC ────────────────────────────
        prog("Ramp 2: Full second order, no curvature correction...", 58)
        _set_methods_ramp2(solver)
        _apply_geko_physics(solver,
                            curvature_correction=False,
                            production_limiter=config.use_production_limiter)
        _iterate(solver, config.ramp2_iters
        )
        _save_case(solver, config, "ramp2_end")
        prog(f"Ramp 2 done ({config.ramp2_iters} iters).", 72)

        # ── RAMP 3: Full Send ────────────────────────────────────────────
        prog("Ramp 3: Full send (curvature correction per config)...", 75)
        _set_methods_ramp2(solver)  # same discretization scheme
        _apply_geko_physics(solver,
                            curvature_correction=config.use_curvature_correction,
                            production_limiter=config.use_production_limiter)
        _iterate(solver, config.ramp3_iters
        )
        _save_case(solver, config, "final")
        prog(f"Ramp 3 done ({config.ramp3_iters} iters).", 95)

        # ── Extract results ──────────────────────────────────────────────
        prog("Extracting results...", 97)
        results = _extract_results(solver, config,
                                   mesh_quality=mesh_quality or {})
        _save_case(solver, config, "complete")
        prog("Simulation complete.", 100)
        return results

    finally:
        solver.exit()


def _save_case(solver, config, label: str):
    path = f"{config.output_dir.rstrip('/\\')}/{config.name}_{label}.cas.h5"
    solver.file.write(file_name=path, file_type="case-data")
    log.info(f"  Saved: {path}")


def _extract_results(solver, config, mesh_quality: Optional[dict] = None) -> dict:
    """Pull per-element and total forces, then export results file."""
    results = {}
    if mesh_quality:
        results["mesh_quality"] = mesh_quality

    def get_val(report_type, name):
        return _get_report_value(solver, report_type, name)

    # Raw values (half-car: NOT doubled here — exporter handles multiplier)
    results["downforce_fw_lbf"]  = get_val("lift", "downforce_fw")
    results["downforce_rw_lbf"]  = get_val("lift", "downforce_rw")
    results["downforce_ut_lbf"]  = get_val("lift", "downforce_ut")
    results["drag_total_lbf"]    = get_val("drag", "drag_total")
    results["drag_aero_lbf"]     = get_val("drag", "drag_aero")
    results["drag_rw_lbf"]       = get_val("drag", "drag_rw")

    # Pitching moments about front axle (Z axis, origin) [lbf·m from Fluent]
    # Convert to inches for CoP calculation to match MATLAB script convention
    M_TO_IN = 39.3701
    results["moment_fw_lbf_in"]  = get_val("moment", "moment_fw")  * M_TO_IN
    results["moment_rw_lbf_in"]  = get_val("moment", "moment_rw")  * M_TO_IN
    results["moment_ut_lbf_in"]  = get_val("moment", "moment_ut")  * M_TO_IN
    results["moment_tot_lbf_in"] = get_val("moment", "moment_total") * M_TO_IN

    # Convenience totals
    mult = 2.0 if config.is_half_symmetry else 1.0
    total_df   = (results["downforce_fw_lbf"] +
                  results["downforce_rw_lbf"] +
                  results["downforce_ut_lbf"]) * mult
    total_drag = results["drag_total_lbf"] * mult
    results["downforce_lbf"] = total_df
    results["drag_lbf"]      = total_drag
    results["ld_ratio"]      = total_df / total_drag if total_drag else 0.0

    if config.is_half_symmetry:
        results["note"] = "Half-car sim — all forces doubled automatically."

    # Extra user-defined zones
    for zone_def in config.extra_result_zones:
        key   = zone_def.get("result_key",
                             zone_def["label"].lower().replace(" ", "_"))
        ztype = zone_def.get("type", "lift")
        results[key] = get_val(ztype, key)

    # Try to get frontal area from the solver
    frontal_area = None
    try:
        frontal_area = solver.setup.reference_values.area
    except Exception:
        pass

    log.info(
        f"  FW={results['downforce_fw_lbf']:.1f} lbf  "
        f"RW={results['downforce_rw_lbf']:.1f} lbf  "
        f"UT={results['downforce_ut_lbf']:.1f} lbf  "
        f"TotalDf={total_df:.1f} lbf  "
        f"TotalDrag={total_drag:.1f} lbf  "
        f"L/D={results['ld_ratio']:.2f}"
    )

    # Export results text file
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
