"""
Core PyFluent automation - meshing workflow and solver ramp-up strategy
based on Ram Racing Fluent Procedure doc.

Requires: ansys-fluent-core (pip install ansys-fluent-core)
"""
import math
import logging
from typing import Callable, Optional

log = logging.getLogger("fluent_runner")



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
    import os, sys
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
    - task.Execute() ALWAYS sends empty executeCommand args {}
    - Fluent validates from executeCommand args, NOT from setState
    - task(args_dict) callable syntax routes through PyFluent __call__
      which correctly packages args into the executeCommand gRPC request

    PyFluent 0.38 made TaskObject instances callable.
    task(args) is the correct 0.38 pattern — not task.Execute().
    """
    if args:
        # PyFluent 0.38 callable task syntax — puts args into executeCommand
        try:
            task(args)
            log.debug("  task(args) callable succeeded")
            return
        except Exception as e:
            log.debug(f"  task(args) failed: {e}")

        # Try Execute with the args dict as positional arg
        try:
            task.Execute(args)
            log.debug("  task.Execute(args) succeeded")
            return
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
                service.execute_command(path, "Execute", args)
                log.debug("  service.execute_command succeeded")
                return
        except Exception as e:
            log.debug(f"  service.execute_command failed: {e}")

    task.Execute()


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
    success_count = 0
    for key, value in args.items():
        try:
            setattr(args_obj, key, value)
            log.debug(f"  Set {key}={value!r}")
            success_count += 1
        except Exception as e:
            log.debug(f"  setattr {key} failed: {e}")

    if success_count == len(args):
        return  # all args set successfully
    log.debug(f"  {success_count}/{len(args)} args set via setattr")

    # Approach 2: dict-style update() — 0.28 fallback
    try:
        args_obj.update(args)
        return
    except Exception as e:
        log.debug(f"  update() failed: {e}")

    # Approach 3: update_dict
    try:
        args_obj.update_dict(args)
        return
    except Exception as e:
        log.warning(f"  All arg-setting methods failed for {list(args.keys())}: {e}")


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
# Main Meshing Workflow
# ---------------------------------------------------------------------------

def run_meshing(config, progress_cb: Optional[Callable] = None):
    """
    Execute the full Fluent Meshing workflow from the Ram Racing procedure doc.
    Steps 1-12 of the Meshing section.
    config: BaseSimConfig subclass instance
    progress_cb: optional callable(step: str, pct: int)
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
        workflow = _init_workflow(meshing)

        # Step 2: Import geometry
        prog("Importing geometry...", 5)
        import_task = workflow.TaskObject["Import Geometry"]
        log.info(f"  Geometry: {config.geometry_path!r}")
        # PyFluent 0.38/252 uses spaced argument names matching the UI labels
        _exec_task(import_task, {
            "File Name":    config.geometry_path,
            "Length Unit":  "m",
        })

        # Step 3: Local Refinement Regions
        prog("Creating local refinement boxes...", 15)
        L = config.car_length_m
        W = config.car_width_m
        H = config.car_height_m
        near, mid, far = compute_refinement_boxes(
            L, W, H, config.is_half_symmetry
        )
        _add_refinement_box(meshing, "local-refinement-nearfield", near)
        _add_refinement_box(meshing, "local-refinement-midfield", mid)
        _add_refinement_box(meshing, "local-refinement-farfield", far)

        # Per-wheel refinement boxes
        if config.use_wheel_mrf and config.wheel_mrf_zones:
            for wheel in config.wheel_mrf_zones:
                _add_wheel_refinement(
                    meshing, wheel.name,
                    wheel.center_x, wheel.center_y, wheel.center_z
                )

        # Step 4a: Local Sizing - Curvature of Stuff
        prog("Adding local sizing: chassis/body...", 28)
        task = workflow.TaskObject["Add Local Sizing"]
        task.AddChildToTask()
        _exec_task(task, {
            "Name": "curvature_stuff",
            "Growth Rate": 1.2,
            "Size Control Type": "curvature",
            "Local Min Size": 0.001,
            "Max Size": 0.064,
            "Curvature Normal Angle": 12,
            "Scope To": "faces-and-edges",
            "Select By": "label",
            "Zones": ["chassis", "driver", "control-arms"],
        })

        # Step 4b: Curvature of Aero
        prog("Adding local sizing: aero elements...", 36)
        task = workflow.TaskObject["Add Local Sizing"]
        task.AddChildToTask()
        _exec_task(task, {
            "Name": "curvature_aero",
            "Growth Rate": 1.2,
            "Size Control Type": "curvature",
            "Local Min Size": 0.0005,
            "Max Size": 0.008,
            "Curvature Normal Angle": 9,
            "Scope To": "faces-and-edges",
            "Select By": "label",
            "Zones": ["front-wing", "rear-wing", "undertray", "fw", "rw",
                      "fwb", "rwb"],
        })

        # Step 4c: Curvature of Wheels
        if config.use_wheel_mrf and config.wheel_mrf_zones:
            prog("Adding local sizing: wheels...", 42)
            wheel_zone_names = [w.zone_name for w in config.wheel_mrf_zones]
            task = workflow.TaskObject["Add Local Sizing"]
            task.AddChildToTask()
            _exec_task(task, {
                "Name": "curvature_wheels",
                "Growth Rate": 1.2,
                "Size Control Type": "curvature",
                "Local Min Size": 0.0005,
                "Max Size": 0.032,
                "Curvature Normal Angle": 18,
                "Scope To": "faces",
                "Select By": "label",
                "Zones": wheel_zone_names,
            })

        # Step 5: Generate Surface Mesh
        prog("Generating surface mesh...", 50)
        _exec_task(workflow.TaskObject["Generate the Surface Mesh"], {
            "Min Size": config.surface_mesh_min,
            "Max Size": config.surface_mesh_max,
            "Growth Rate": 1.2,
            "Size Functions": "curvature-and-proximity",
            "Curvature Normal Angle": 18,
            "Cells Per Gap": 1,
            "Scope Proximity To": "faces-and-edges",
            "Separate Out Boundary Zones By Angle": "no",
        })

        # Step 6: Improve Surface Mesh
        # Note: called after Generate Volume Mesh executes the full pipeline
        prog("Configuring surface mesh improvement...", 58)

        # Step 7: Describe Geometry
        prog("Describing geometry...", 62)
        _exec_task(workflow.TaskObject["Describe Geometry"], {
            "Geometry Type": "fluid-regions-only",
            "Change Boundary Types": "no",
            "Share Topology": "no",
            "Enable Multizone Meshing": "no",
        })

        # Step 8: Update Boundaries
        prog("Updating boundaries...", 66)
        _exec_task(workflow.TaskObject["Update Boundaries"])

        # Step 9: Create + Update Regions (252 splits this into two tasks)
        prog("Updating regions...", 70)
        try:
            _exec_task(workflow.TaskObject["Create Regions"])
        except Exception:
            pass  # not present in all workflow versions
        _exec_task(workflow.TaskObject["Update Regions"])

        # Step 10: Add Boundary Layers (on aero + ground)
        prog("Adding boundary layers...", 74)
        aero_and_ground = ["front-wing", "rear-wing", "undertray",
                           "fw", "rw", "fwb", "rwb", "ground"]
        try:
            workflow.TaskObject["Add Boundary Layers"].AddChildToTask()
        except AttributeError:
            log.warning("  AddChildToTask not available")
        _exec_task(workflow.TaskObject["Add Boundary Layers"], {
            "Add Boundary Layers": "yes",
            "Name": "last-ratio_1",
            "Offset Method Type": "last-ratio",
            "Number of Layers": config.bl_num_layers,
            "Transition Ratio": config.bl_transition_ratio,
            "First Height": config.bl_first_height,
            "Add In": "fluid-regions",
            "Grow On": "selected-zones",
            "Zones": aero_and_ground,
        })

        # Step 11: Generate Volume Mesh — configure then EXECUTE the full pipeline
        # In Fluent 252 Watertight workflow, executing Generate the Volume Mesh
        # triggers the full cascade: import → sizing → surface mesh → describe
        # → boundaries → regions → boundary layers → volume mesh
        prog("Generating volume mesh (this takes a while)...", 85)
        _exec_task(workflow.TaskObject["Generate the Volume Mesh"], {
            "Solver": "fluent",
            "Fill With": "poly-hexcore",
            "Peel Layers": 1,
            "Min Cell Length": config.volume_mesh_min,
            "Max Cell Length": config.volume_mesh_max,
            "Enable Parallel Meshing": True,
        })
        # EXECUTE the workflow cascade:
        # Use task(args) callable syntax — the only pattern that sends
        # File Name through gRPC correctly in 252.

        log.info("  Executing full workflow pipeline...")
        prog("Running meshing pipeline...", 87)
        result = workflow.TaskObject["Generate the Volume Mesh"]({})
        log.info(f"  Volume mesh generation complete (result={result})")
        
        if not result:
            raise RuntimeError("Volume mesh generation failed - check Fluent logs for details")

        # Step 12: Improve Volume Mesh (after full mesh generation)
        prog("Improving volume mesh...", 92)
        try:
            meshing.scheme_eval.string_eval('(improve-volume-mesh "orthogonal" 0.2)')
            log.info("  ImproveVolumeMesh complete")
        except Exception as e:
            log.warning(f"  ImproveVolumeMesh skipped: {e}")

        # Save the mesh
        import os
        os.makedirs(config.output_dir, exist_ok=True)
        mesh_file = config.output_dir.rstrip("/\\") + "/mesh.msh.h5"
        written = False

        # Try 1: scheme eval — most reliable in 252
        try:
            meshing.scheme_eval.string_eval(
                f'(write-case "{mesh_file}")'
            )
            log.info(f"  Case written via scheme_eval")
            written = True
        except Exception as e:
            log.debug(f"  scheme_eval write failed: {e}")

        # Try 2: meshing.meshing.File methods
        if not written:
            file_obj = meshing.meshing.File
            for method_name in ["WriteMesh", "write_mesh", "WriteCaseData", "write_case_data"]:
                method = getattr(file_obj, method_name, None)
                if method:
                    try:
                        method(FileName=mesh_file)
                        log.info(f"  Mesh written via meshing.File.{method_name}")
                        written = True
                        break
                    except Exception as e:
                        log.debug(f"  meshing.File.{method_name} failed: {e}")

        # Try 3: switch_to_solver then write from solver side
        if not written:
            try:
                solver = meshing.switch_to_solver()
                solver.file.write_case(file_name=mesh_file)
                log.info("  Mesh written via switch_to_solver")
                written = True
            except Exception as e:
                log.debug(f"  switch_to_solver write failed: {e}")

        if not written:
            raise RuntimeError(
                f"Could not write mesh to {mesh_file}. "
                f"All write methods failed — check the log for details."
            )

        prog(f"Mesh saved to: {mesh_file}", 100)
        log.info(f"Meshing complete. File: {mesh_file}")
        return mesh_file

    finally:
        meshing.exit()


# ---------------------------------------------------------------------------
# Solver Setup & Ramp-Up
# ---------------------------------------------------------------------------

def _apply_geko_physics(solver, curvature_correction: bool,
                        production_limiter: bool):
    """Set k-omega GEKO turbulence model."""
    solver.setup.models.viscous.model = "k-omega"
    solver.setup.models.viscous.k_omega_model = "geko"
    solver.setup.models.viscous.options.production_limiter = production_limiter
    solver.setup.models.viscous.options.curvature_correction = curvature_correction


def _set_boundary_conditions(solver, config):
    """
    Configure inlet, outlet, ground, symmetry, and wheel BCs.
    Implements moving ground + wheel MRF from the procedure doc.
    """
    speed_ms = mph_to_ms(config.vehicle_speed_mph)

    # Velocity inlet
    inlet = solver.setup.boundary_conditions.velocity_inlet["inlet"]
    inlet.momentum.velocity_magnitude.value = speed_ms

    # Ground - moving wall matching freestream speed
    ground = solver.setup.boundary_conditions.wall["ground"]
    ground.wall_motion = "moving-wall"
    ground.motion.type = "translational"
    ground.motion.velocity.x = speed_ms
    ground.motion.velocity.y = 0.0
    ground.motion.velocity.z = 0.0

    # Wheel MRF cell zones
    if config.use_wheel_mrf and config.wheel_mrf_zones:
        for wheel in config.wheel_mrf_zones:
            rpm = wheel.rpm if wheel.rpm != 0.0 else wheel_rpm(
                speed_ms, wheel.wheel_radius
            )
            log.info(
                f"  Wheel {wheel.name}: {rpm:.1f} RPM "
                f"(r={wheel.wheel_radius}m, v={speed_ms:.2f}m/s)"
            )
            try:
                mrf_zone = solver.setup.cell_zone_conditions.fluid[
                    wheel.zone_name
                ]
                mrf_zone.motion_type = "moving-reference-frame"
                mrf_zone.mrf_motion.rotation_speed = rpm / 60.0  # rps
                mrf_zone.mrf_motion.rotation_axis_origin = [
                    wheel.center_x, wheel.center_y, wheel.center_z
                ]
                mrf_zone.mrf_motion.rotation_axis_direction = [
                    wheel.axis_x, wheel.axis_y, wheel.axis_z
                ]
            except Exception as e:
                log.warning(
                    f"Could not set MRF for wheel zone '{wheel.zone_name}': {e}"
                )


def _set_methods_first_order(solver):
    _set_discretization(solver, "simple",             "pressure_velocity_coupling")
    _set_discretization(solver, "standard",           "pressure")
    _set_discretization(solver, "first-order-upwind", "momentum")
    _set_discretization(solver, "first-order-upwind", "turbulent_kinetic_energy")
    _set_discretization(solver, "first-order-upwind", "specific_dissipation_rate")


def _set_methods_ramp1(solver):
    """Second order + Presto pressure."""
    _set_discretization(solver, "simple",              "pressure_velocity_coupling")
    _set_discretization(solver, "presto",              "pressure")
    _set_discretization(solver, "second-order-upwind", "momentum")
    _set_discretization(solver, "second-order-upwind", "turbulent_kinetic_energy")
    _set_discretization(solver, "second-order-upwind", "specific_dissipation_rate")


def _set_methods_ramp2(solver):
    """Full second order, standard pressure, no curvature correction."""
    _set_discretization(solver, "simple",              "pressure_velocity_coupling")
    _set_discretization(solver, "second-order",        "pressure")
    _set_discretization(solver, "second-order-upwind", "momentum")
    _set_discretization(solver, "second-order-upwind", "turbulent_kinetic_energy")
    _set_discretization(solver, "second-order-upwind", "specific_dissipation_rate")


# Canonical zone label groups (must match named selections in Discovery)
_FW_ZONES  = ["front-wing", "fw", "fwb"]
_RW_ZONES  = ["rear-wing",  "rw", "rwb"]
_UT_ZONES  = ["undertray"]
_ALL_EXCL  = {"ground", "inlet", "outlet", "symmetry", "walls",
              "top-wall", "enclosure-enclosure1", "fff-mrf"}


def _configure_force_reports(solver, config):
    """Set up per-element and total force monitors."""
    all_wall_zones = [z for z in solver.setup.boundary_conditions.wall
                      if z not in _ALL_EXCL]

    def safe_add_lift(name, zones):
        existing = [z for z in zones
                    if z in solver.setup.boundary_conditions.wall]
        if not existing:
            log.warning(f"  No zones found for report '{name}': {zones}")
            return
        _add_report_lift(solver, name, existing, [0, -1, 0])

    def safe_add_drag(name, zones):
        existing = [z for z in zones
                    if z in solver.setup.boundary_conditions.wall]
        if not existing:
            log.warning(f"  No zones found for drag report '{name}': {zones}")
            return
        _add_report_drag(solver, name, existing, [-1, 0, 0])

    # Total car
    safe_add_lift("downforce_total", all_wall_zones)
    safe_add_drag("drag_total",      all_wall_zones)

    # Per element
    safe_add_lift("downforce_fw", _FW_ZONES)
    safe_add_lift("downforce_rw", _RW_ZONES)
    safe_add_lift("downforce_ut", _UT_ZONES)

    # Aero-system drag (FW+RW+UT only)
    safe_add_drag("drag_aero", _FW_ZONES + _RW_ZONES + _UT_ZONES)
    safe_add_drag("drag_rw",   _RW_ZONES)

    # Pitching moment reports — used to derive CoP arm lengths post-sim
    # Moment axis = Z axis (0,0,1), moment centre = origin (front axle at X=0)
    # Fluent moment convention: positive = nose-up
    def safe_add_moment(name, zones):
        existing = [z for z in zones
                    if z in solver.setup.boundary_conditions.wall]
        if not existing:
            log.warning(f"  No zones found for moment report '{name}': {zones}")
            return
        _add_report_moment(solver, name, existing, [0, 0, 0], [0, 0, 1])

    safe_add_moment("moment_fw", _FW_ZONES)
    safe_add_moment("moment_rw", _RW_ZONES)
    safe_add_moment("moment_ut", _UT_ZONES)
    safe_add_moment("moment_total", _FW_ZONES + _RW_ZONES + _UT_ZONES)

    # Extra user-defined zones
    for zone_def in config.extra_result_zones:
        ztype = zone_def.get("type", "lift")
        key   = zone_def.get("result_key",
                             zone_def["label"].lower().replace(" ", "_"))
        zones = zone_def.get("zones", [])
        if ztype == "lift":
            safe_add_lift(key, zones)
        else:
            safe_add_drag(key, zones)

    log.info(f"Force reports configured ({len(all_wall_zones)} total wall zones).")


def run_solver(config, mesh_file: str,
               progress_cb: Optional[Callable] = None):
    """
    Run the full ramp-up solver strategy from the Ram Racing procedure doc.
    Ramp 0: First order (stabilize)
    Ramp 1: Second order + Presto pressure
    Ramp 2: Full second order, no curvature correction
    Ramp 3: Full send - second order + curvature correction
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
    import_file_name = (mesh_file)
    solver = _launch_fluent_solver(pyfluent, config)

    try:
        # Load mesh
        prog("Loading mesh...", 2)
        solver.settings.file.read_case(file_name=import_file_name)
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

        # Units
        solver.setup.general.units["force"] = "lbf"
        solver.setup.general.units["velocity"] = "mph"

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
        prog("Ramp 3: Full send (curvature correction ON)...", 75)
        _set_methods_ramp2(solver)  # same discretization scheme
        _apply_geko_physics(solver,
                            curvature_correction=True,
                            production_limiter=config.use_production_limiter)
        _iterate(solver, config.ramp3_iters
        )
        _save_case(solver, config, "final")
        prog(f"Ramp 3 done ({config.ramp3_iters} iters).", 95)

        # ── Extract results ──────────────────────────────────────────────
        prog("Extracting results...", 97)
        results = _extract_results(solver, config)
        _save_case(solver, config, "complete")
        prog("Simulation complete.", 100)
        return results

    finally:
        solver.exit()


def _save_case(solver, config, label: str):
    path = f"{config.output_dir.rstrip('/\\')}/{config.name}_{label}.cas.h5"
    solver.file.write(file_name=path, file_type="case-data")
    log.info(f"  Saved: {path}")


def _extract_results(solver, config) -> dict:
    """Pull per-element and total forces, then export results file."""
    results = {}

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
                                     frontal_area_m2=frontal_area)
        results["result_file"] = result_file
        log.info(f"  Results exported to: {result_file}")
    except Exception as e:
        log.warning(f"  Results export failed: {e}")

    return results