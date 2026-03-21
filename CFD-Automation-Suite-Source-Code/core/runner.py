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
# Speed / RPM helpers
# ---------------------------------------------------------------------------

def mph_to_ms(mph: float) -> float:
    return mph * 0.44704


def wheel_rpm(speed_ms: float, radius_m: float) -> float:
    """Angular velocity in rad/s, then convert to RPM."""
    omega = speed_ms / radius_m          # rad/s
    return omega * 60.0 / (2.0 * math.pi)


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
    """Create a local refinement box in Fluent Meshing."""
    workflow = meshing.workflow
    task = workflow.TaskObject["Create Local Refinement Regions"]
    task.Arguments.update({
        "LocalRefinementRegionName": name,
        "Type": "box",
        "CoordinateSpecificationMethod": "directly-specify-coordinates",
        "MeshSize": box["size"],
        "XMin": box["x_min"], "XMax": box["x_max"],
        "YMin": box["y_min"], "YMax": box["y_max"],
        "ZMin": box["z_min"], "ZMax": box["z_max"],
    })
    task.Execute()
    log.info(f"  Added refinement box: {name}")


def _add_wheel_refinement(meshing, wheel_name: str,
                          cx: float, cy: float, cz: float):
    """
    Per-wheel local refinement box (0.032 m, relative to body size 0.1).
    Doc: Table 4 - do each wheel separately.
    """
    workflow = meshing.workflow
    task = workflow.TaskObject["Create Local Refinement Regions"]
    task.Arguments.update({
        "LocalRefinementRegionName": f"wheel_{wheel_name.lower()}",
        "Type": "box",
        "CoordinateSpecificationMethod": "relative-to-body-size",
        "MeshSize": 0.032,
        "XMin": 0.1, "XMax": 1.0,
        "YMin": 0.0, "YMax": 0.1,
        "ZMin": 0.1, "ZMax": 0.1,
    })
    task.Execute()
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
    meshing = pyfluent.launch_fluent(
        mode="meshing",
        precision="double" if config.double_precision else "single",
        processor_count=config.num_processes,
    )

    try:
        workflow = meshing.workflow
        workflow.InitializeWorkflow(WorkflowType="Watertight Geometry")

        # Step 2: Import geometry
        prog("Importing geometry...", 5)
        workflow.TaskObject["Import Geometry"].Arguments.update({
            "FileName": config.geometry_path,
            "LengthUnit": "m",
        })
        workflow.TaskObject["Import Geometry"].Execute()

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
        task.Arguments.update({
            "Name": "curvature_stuff",
            "GrowthRate": 1.2,
            "SizeControlType": "curvature",
            "LocalMinSize": 0.001,
            "MaxSize": 0.064,
            "CurvatureNormalAngle": 12,
            "ScopeTo": "faces-and-edges",
            "SelectBy": "label",
            # User must assign labels; we pre-fill with a placeholder.
            "Zones": ["chassis", "driver", "control-arms"],
        })
        task.AddChildToTask()
        task.Execute()

        # Step 4b: Curvature of Aero
        prog("Adding local sizing: aero elements...", 36)
        task = workflow.TaskObject["Add Local Sizing"]
        task.Arguments.update({
            "Name": "curvature_aero",
            "GrowthRate": 1.2,
            "SizeControlType": "curvature",
            "LocalMinSize": 0.0005,
            "MaxSize": 0.008,
            "CurvatureNormalAngle": 9,
            "ScopeTo": "faces-and-edges",
            "SelectBy": "label",
            "Zones": ["front-wing", "rear-wing", "undertray", "fw", "rw",
                      "fwb", "rwb"],
        })
        task.AddChildToTask()
        task.Execute()

        # Step 4c: Curvature of Wheels
        if config.use_wheel_mrf and config.wheel_mrf_zones:
            prog("Adding local sizing: wheels...", 42)
            wheel_zone_names = [w.zone_name for w in config.wheel_mrf_zones]
            task = workflow.TaskObject["Add Local Sizing"]
            task.Arguments.update({
                "Name": "curvature_wheels",
                "GrowthRate": 1.2,
                "SizeControlType": "curvature",
                "LocalMinSize": 0.0005,
                "MaxSize": 0.032,
                "CurvatureNormalAngle": 18,
                "ScopeTo": "faces",
                "SelectBy": "label",
                "Zones": wheel_zone_names,
            })
            task.AddChildToTask()
            task.Execute()

        # Step 5: Generate Surface Mesh
        prog("Generating surface mesh...", 50)
        workflow.TaskObject["Generate the Surface Mesh"].Arguments.update({
            "MinSize": config.surface_mesh_min,
            "MaxSize": config.surface_mesh_max,
            "GrowthRate": 1.2,
            "SizeFunctions": "curvature-and-proximity",
            "CurvatureNormalAngle": 18,
            "CellsPerGap": 1,
            "ScopeProximityTo": "faces-and-edges",
            "SeparateOutBoundaryZonesByAngle": "no",
        })
        workflow.TaskObject["Generate the Surface Mesh"].Execute()

        # Step 6: Improve Surface Mesh
        prog("Improving surface mesh...", 58)
        workflow.TaskObject["Improve Surface Mesh"].Arguments.update({
            "FaceQualityLimit": 0.7,
        })
        workflow.TaskObject["Improve Surface Mesh"].Execute()

        # Step 7: Describe Geometry
        prog("Describing geometry...", 62)
        workflow.TaskObject["Describe Geometry"].Arguments.update({
            "GeometryType": "fluid-regions-only",
            "ChangeBoundaryTypes": "no",
            "ShareTopology": "no",
            "EnableMultizoneMeshing": "no",
        })
        workflow.TaskObject["Describe Geometry"].Execute()

        # Step 8: Update Boundaries
        prog("Updating boundaries...", 66)
        workflow.TaskObject["Update Boundaries"].Execute()

        # Step 9: Update Regions
        prog("Updating regions...", 70)
        workflow.TaskObject["Update Regions"].Execute()

        # Step 10: Add Boundary Layers (on aero + ground)
        prog("Adding boundary layers...", 74)
        aero_and_ground = ["front-wing", "rear-wing", "undertray",
                           "fw", "rw", "fwb", "rwb", "ground"]
        workflow.TaskObject["Add Boundary Layers"].Arguments.update({
            "AddBoundaryLayers": "yes",
            "Name": "last-ratio_1",
            "OffsetMethodType": "last-ratio",
            "NumberOfLayers": config.bl_num_layers,
            "TransitionRatio": config.bl_transition_ratio,
            "FirstHeight": config.bl_first_height,
            "AddIn": "fluid-regions",
            "GrowOn": "selected-zones",
            "Zones": aero_and_ground,
        })
        workflow.TaskObject["Add Boundary Layers"].AddChildToTask()
        workflow.TaskObject["Add Boundary Layers"].Execute()

        # Step 11: Generate Volume Mesh
        prog("Generating volume mesh (this takes a while)...", 80)
        workflow.TaskObject["Generate the Volume Mesh"].Arguments.update({
            "Solver": "fluent",
            "FillWith": "poly-hexcore",
            "PeelLayers": 1,
            "MinCellLength": config.volume_mesh_min,
            "MaxCellLength": config.volume_mesh_max,
            "EnableParallelMeshing": True,
        })
        workflow.TaskObject["Generate the Volume Mesh"].Execute()

        # Step 12: Improve Volume Mesh
        prog("Improving volume mesh...", 92)
        workflow.TaskObject["Improve Volume Mesh"].Arguments.update({
            "QualityMethod": "orthogonal",
            "CellQualityLimit": 0.2,
        })
        workflow.TaskObject["Improve Volume Mesh"].Execute()

        # Save the mesh
        mesh_file = config.output_dir.rstrip("/\\") + "/mesh.msh.h5"
        meshing.file.write(file_name=mesh_file, file_type="mesh")
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
    solver.solution.methods.pressure_velocity_coupling.scheme = "simple"
    solver.solution.methods.spatial_discretization.pressure = "standard"
    solver.solution.methods.spatial_discretization.momentum = "first-order-upwind"
    solver.solution.methods.spatial_discretization.turbulent_kinetic_energy = "first-order-upwind"
    solver.solution.methods.spatial_discretization.specific_dissipation_rate = "first-order-upwind"


def _set_methods_ramp1(solver):
    """Second order + Presto pressure."""
    solver.solution.methods.pressure_velocity_coupling.scheme = "simple"
    solver.solution.methods.spatial_discretization.pressure = "presto"
    solver.solution.methods.spatial_discretization.momentum = "second-order-upwind"
    solver.solution.methods.spatial_discretization.turbulent_kinetic_energy = "second-order-upwind"
    solver.solution.methods.spatial_discretization.specific_dissipation_rate = "second-order-upwind"


def _set_methods_ramp2(solver):
    """Full second order, standard pressure, no curvature correction."""
    solver.solution.methods.pressure_velocity_coupling.scheme = "simple"
    solver.solution.methods.spatial_discretization.pressure = "second-order"
    solver.solution.methods.spatial_discretization.momentum = "second-order-upwind"
    solver.solution.methods.spatial_discretization.turbulent_kinetic_energy = "second-order-upwind"
    solver.solution.methods.spatial_discretization.specific_dissipation_rate = "second-order-upwind"


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
        solver.solution.report_definitions.lift[name] = {
            "zones": existing,
            "force_vector": [0, -1, 0],
        }

    def safe_add_drag(name, zones):
        existing = [z for z in zones
                    if z in solver.setup.boundary_conditions.wall]
        if not existing:
            log.warning(f"  No zones found for drag report '{name}': {zones}")
            return
        solver.solution.report_definitions.drag[name] = {
            "zones": existing,
            "force_vector": [-1, 0, 0],
        }

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
        solver.solution.report_definitions.moment[name] = {
            "zones":  existing,
            "moment_center": [0, 0, 0],
            "moment_axis":   [0, 0, 1],
        }

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
    solver = pyfluent.launch_fluent(
        mode="solver",
        precision="double" if config.double_precision else "single",
        processor_count=config.num_processes,
    )

    try:
        # Load mesh
        prog("Loading mesh...", 2)
        solver.file.read(file_name=mesh_file, file_type="mesh")
        solver.mesh.check()

        # Units
        solver.setup.general.units["force"] = "lbf"
        solver.setup.general.units["velocity"] = "mph"

        # Reference values
        prog("Setting reference values...", 5)
        speed_ms = mph_to_ms(config.vehicle_speed_mph)
        solver.setup.reference_values.compute_from = "inlet"
        solver.setup.reference_values.velocity = speed_ms
        solver.setup.reference_values.length = config.car_length_m

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
        solver.solution.run_calculation.iterate(
            number_of_iterations=config.ramp0_iters
        )
        _save_case(solver, config, "ramp0_end")
        prog(f"Ramp 0 done ({config.ramp0_iters} iters).", 35)

        # ── RAMP 1: Second order + Presto ───────────────────────────────
        prog("Ramp 1: Second order + Presto pressure...", 38)
        _set_methods_ramp1(solver)
        solver.solution.run_calculation.iterate(
            number_of_iterations=config.ramp1_iters
        )
        _save_case(solver, config, "ramp1_end")
        prog(f"Ramp 1 done ({config.ramp1_iters} iters).", 55)

        # ── RAMP 2: Full second order, no CC ────────────────────────────
        prog("Ramp 2: Full second order, no curvature correction...", 58)
        _set_methods_ramp2(solver)
        _apply_geko_physics(solver,
                            curvature_correction=False,
                            production_limiter=config.use_production_limiter)
        solver.solution.run_calculation.iterate(
            number_of_iterations=config.ramp2_iters
        )
        _save_case(solver, config, "ramp2_end")
        prog(f"Ramp 2 done ({config.ramp2_iters} iters).", 72)

        # ── RAMP 3: Full Send ────────────────────────────────────────────
        prog("Ramp 3: Full send (curvature correction ON)...", 75)
        _set_methods_ramp2(solver)  # same discretization scheme
        _apply_geko_physics(solver,
                            curvature_correction=True,
                            production_limiter=config.use_production_limiter)
        solver.solution.run_calculation.iterate(
            number_of_iterations=config.ramp3_iters
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
        try:
            if report_type == "lift":
                return solver.solution.report_definitions.lift[
                    name].get_monitor_value()
            elif report_type == "drag":
                return solver.solution.report_definitions.drag[
                    name].get_monitor_value()
            else:  # moment
                return solver.solution.report_definitions.moment[
                    name].get_monitor_value()
        except Exception as e:
            log.warning(f"  Could not read report '{name}': {e}")
            return 0.0

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