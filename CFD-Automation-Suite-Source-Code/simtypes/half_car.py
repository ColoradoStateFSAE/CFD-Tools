"""
Half Car simulation.

Everything for this simulation type lives in this one file: the settings the
GUI edits, the meshing sequence, the solver setup, the report definitions and
the exports. Nothing is inherited or shared, so what you read here is exactly
what runs.

Geometry: symmetry plane at z = 0, model on the driver's left (+Z).

Coordinate convention
    +X  toward the rear of the car = flow direction   -> drag      [ 1, 0, 0]
    +Y  up                                            -> downforce [0, -1, 0]
    +Z  driver's left                                 -> half model at z >= 0

All values are SI: N, N*m, m, m/s, Pa, m^2.
"""
import math
import os
import time
from dataclasses import dataclass, field

from utils.refinement import refinement_boxes, WHEEL_BOX_SIZE, WHEEL_BOX_RATIOS

NAME = "Half Car"
KEY = "half_car"

MPH_TO_MS = 0.44704
AIR_DENSITY = 1.225          # kg/m^3


# =============================================================================
#  NAMED SELECTIONS
#  Must match the labels created in Ansys Discovery exactly.
#  The GUI shows this table on its Named Selections tab.
# =============================================================================

NAMED_SELECTIONS = {
    # label            (boundary type,     description)
    "inlet":           ("velocity-inlet",  "Domain inlet, upstream face"),
    "outlet":          ("pressure-outlet", "Domain outlet, downstream face"),
    "walls":           ("wall, slip",      "Far-field tunnel walls, zero shear"),
    "ground":          ("wall, moving",    "Ground plane, translating at car speed"),
    "symmetry":        ("symmetry",        "Symmetry plane at z = 0"),

    "frontwing":       ("wall",            "Front wing, all elements"),
    "rearwing":        ("wall",            "Rear wing, all elements"),
    "undertray":       ("wall",            "Undertray and diffuser"),
    "chassis":         ("wall",            "Chassis, nose and body"),
    "sidepod":         ("wall",            "Sidepod, optional"),

    "fw":              ("wall, rotating",  "Front wheel"),
    "fwb":             ("wall, rotating",  "Front wheel block"),
    "rw":              ("wall, rotating",  "Rear wheel"),
    "rwb":             ("wall, rotating",  "Rear wheel block"),

    "front-suspension": ("wall",           "Front suspension members, optional"),
    "rear-suspension":  ("wall",           "Rear suspension members, optional"),
}

AERO       = ["frontwing", "rearwing", "undertray"]
BODY       = ["chassis", "sidepod"]
FRONT_SUS  = ["front-suspension"]
REAR_SUS   = ["rear-suspension"]
FRONT_WHEEL = ["fw", "fwb"]
REAR_WHEEL  = ["rw", "rwb"]
CAR = AERO + BODY + FRONT_SUS + REAR_SUS + FRONT_WHEEL + REAR_WHEEL


# =============================================================================
#  REPORT DEFINITIONS
#  Created in Fluent below. The GUI shows this table on its Reports tab.
#  SCz, SCx, copx, copz and cop_pct are Fluent expressions, so Ansys does the
#  arithmetic rather than Python.
# =============================================================================

REPORT_DEFINITIONS = {
    # name            (kind,       description)
    "fz":             ("lift",     "Total downforce, all car surfaces [N]"),
    "fx":             ("drag",     "Total drag, all car surfaces [N]"),
    "cl":             ("lift",     "Lift coefficient, all car surfaces"),
    "cd":             ("drag",     "Drag coefficient, all car surfaces"),

    "fz_frontwing":   ("lift",     "Front wing downforce [N]"),
    "fx_frontwing":   ("drag",     "Front wing drag [N]"),
    "fz_rearwing":    ("lift",     "Rear wing downforce [N]"),
    "fx_rearwing":    ("drag",     "Rear wing drag [N]"),
    "fz_undertray":   ("lift",     "Undertray downforce [N]"),
    "fx_undertray":   ("drag",     "Undertray drag [N]"),
    "fz_body":        ("lift",     "Chassis and sidepod downforce [N]"),
    "fx_body":        ("drag",     "Chassis and sidepod drag [N]"),

    "fz_fw":          ("lift",     "Front wheel downforce [N]"),
    "fx_fw":          ("drag",     "Front wheel drag [N]"),
    "fz_rw":          ("lift",     "Rear wheel downforce [N]"),
    "fx_rw":          ("drag",     "Rear wheel drag [N]"),
    "fz_frontsus":    ("lift",     "Front suspension downforce [N]"),
    "fx_frontsus":    ("drag",     "Front suspension drag [N]"),
    "fz_rearsus":     ("lift",     "Rear suspension downforce [N]"),
    "fx_rearsus":     ("drag",     "Rear suspension drag [N]"),

    "my_total":       ("moment",   "Pitch moment about the origin, Z axis [N*m]"),
    "mx_total":       ("moment",   "Lateral moment about the origin, Y axis [N*m]"),

    "SCz":            ("expression", "Downforce area, fz / dynamic pressure [m^2]"),
    "SCx":            ("expression", "Drag area, fx / dynamic pressure [m^2]"),
    "copx":           ("expression", "Centre of pressure, x from origin [m]"),
    "copz":           ("expression", "Centre of pressure, z from origin [m]"),
    "cop_pct":        ("expression", "Aero balance, percent forward"),
}


# =============================================================================
#  SETTINGS
#  Everything the GUI can change.
# =============================================================================

@dataclass
class Settings:
    # ── Identity and paths ───────────────────────────────────────────────
    name:          str = "Half Car Sim"
    geometry_path: str = ""
    output_dir:    str = ""
    results_dir:   str = ""

    # Point this at an existing .msh.h5 to skip meshing entirely.
    existing_mesh: str = ""

    # ── Car dimensions [m] ───────────────────────────────────────────────
    car_length: float = 2.9      # x axis
    car_width:  float = 1.4      # z axis
    car_height: float = 1.2      # y axis
    wheelbase:  float = 1.575    # front axle to rear axle

    # ── Operating point ──────────────────────────────────────────────────
    speed_mph: float = 40.0

    # ── Fluent session ───────────────────────────────────────────────────
    processes:        int  = 40
    double_precision: bool = True

    # ── Mesh sizing [m] ──────────────────────────────────────────────────
    surface_min: float = 0.002
    surface_max: float = 0.256
    volume_min:  float = 0.0015
    volume_max:  float = 0.256

    # ── Boundary layers ──────────────────────────────────────────────────
    bl_layers:       int   = 6
    bl_first_height: float = 0.0005

    # ── Rotating wheels ──────────────────────────────────────────────────
    # Origins are the wheel axle centres. Editable in the GUI because they
    # move with wheelbase and ride height.
    wheel_radius: float = 0.2032                    # 8 in
    front_wheel_origin: list = field(default_factory=lambda: [-0.7874, 0.2032, 0.6096])
    rear_wheel_origin:  list = field(default_factory=lambda: [ 0.7874, 0.2032, 0.5842])
    wheel_axis: list = field(default_factory=lambda: [0.0, 0.0, 1.0])

    # ── Solver ramps ─────────────────────────────────────────────────────
    ramp1_iters: int = 200      # first order
    ramp2_iters: int = 300      # second order, PRESTO pressure
    ramp3_iters: int = 500      # full send, curvature correction on

    # ── Exports ──────────────────────────────────────────────────────────
    export_ensight: bool = True

    # ── Derived ──────────────────────────────────────────────────────────
    @property
    def speed_ms(self) -> float:
        return self.speed_mph * MPH_TO_MS

    @property
    def wheel_omega(self) -> float:
        """Wheel rotation rate [rad/s] for rolling without slip."""
        return self.speed_ms / self.wheel_radius if self.wheel_radius else 0.0

    @property
    def dynamic_pressure(self) -> float:
        return 0.5 * AIR_DENSITY * self.speed_ms ** 2

    def validate(self) -> list:
        """Return a list of problems, empty if the settings are usable."""
        problems = []
        if not self.name.strip():
            problems.append("Simulation name is empty")
        if not self.existing_mesh and not self.geometry_path:
            problems.append("No geometry file and no existing mesh")
        if self.geometry_path and not self.geometry_path.lower().endswith(
                (".pmdb", ".dsco")):
            problems.append("Geometry must be .pmdb or .dsco")
        if not self.output_dir:
            problems.append("No output directory")
        if self.speed_mph <= 0:
            problems.append("Speed must be greater than zero")
        if self.processes < 1:
            problems.append("Process count must be at least 1")
        if self.surface_min >= self.surface_max:
            problems.append("Surface min size must be below max size")
        return problems


# =============================================================================
#  MESHING
# =============================================================================

def mesh(s: Settings, log, progress=None) -> str:
    """
    Run the Watertight Geometry workflow and write the mesh.
    Returns the mesh file path.
    """
    import ansys.fluent.core as pyfluent

    def step(pct, msg):
        log.info(f"[MESH {pct:3d}%] {msg}")
        if progress:
            progress(msg, pct)

    os.makedirs(s.output_dir, exist_ok=True)
    mesh_file = os.path.join(s.output_dir, "mesh.msh.h5")

    step(0, "Launching Fluent Meshing")
    session = pyfluent.launch_fluent(
        mode="meshing",
        processor_count=s.processes,
        precision="double" if s.double_precision else "single",
        product_version="26.1",
        cleanup_on_exit=True,
    )

    try:
        workflow = session.workflow
        workflow.InitializeWorkflow(WorkflowType="Watertight Geometry")

        session.meshing.GlobalSettings.LengthUnit.set_state("m")
        session.meshing.GlobalSettings.AreaUnit.set_state("m^2")
        session.meshing.GlobalSettings.VolumeUnit.set_state("m^3")

        # ── Import geometry ───────────────────────────────────────────────
        step(5, f"Importing {os.path.basename(s.geometry_path)}")
        workflow.TaskObject["Import Geometry"].Arguments = {
            "FileName":   s.geometry_path,
            "LengthUnit": "m",
        }
        workflow.TaskObject["Import Geometry"].Execute()

        # ── Local refinement regions ──────────────────────────────────────
        step(12, "Creating refinement regions")
        workflow.TaskObject["Import Geometry"].InsertNextTask(
            CommandName="CreateLocalRefinementRegions"
        )
        refine = workflow.TaskObject["Create Local Refinement Regions"]

        for box in refinement_boxes(s.car_length, s.car_width, s.car_height,
                                    half_model=True):
            refine.Arguments.set_state({
                "RefinementRegionsName": box.name,
                "CreationMethod":        "Box",
                "SelectionType":         "label",
                "BOIMaxSize":            box.size,
                "BOISizeName":           "boi_1",
                "VolumeFill":            "hexcore",
                "BoundingBoxObject": {
                    "SizeRelativeLength": "Directly specify coordinates",
                    "Xmin": box.x_min, "Xmax": box.x_max,
                    "Ymin": box.y_min, "Ymax": box.y_max,
                    "Zmin": box.z_min, "Zmax": box.z_max,
                },
            })
            refine.AddChildAndUpdate(DeferUpdate=False, RetainValues=True)
            log.info(f"  {box}")

        # Wheel boxes are sized relative to the wheel body, so they need the
        # wheel labels rather than coordinates.
        for region_name, labels in (
            ("local-refinement-frontwheel", FRONT_WHEEL),
            ("local-refinement-rearwheel",  REAR_WHEEL),
        ):
            refine.Arguments.set_state({
                "RefinementRegionsName": region_name,
                "CreationMethod":        "Box",
                "SelectionType":         "label",
                "LabelSelectionList":    labels,
                "BOIMaxSize":            WHEEL_BOX_SIZE,
                "BOISizeName":           "boi_1",
                "VolumeFill":            "hexcore",
                "BoundingBoxObject": dict(
                    {"SizeRelativeLength": "Ratio relative to geometry size"},
                    **WHEEL_BOX_RATIOS
                ),
            })
            refine.AddChildAndUpdate(DeferUpdate=False, RetainValues=True)
            log.info(f"  {region_name:28s} relative to {labels}")

        # ── Local sizing ──────────────────────────────────────────────────
        # Curvature controls. The curvature normal angle is what refines
        # curved aero surfaces; a plain face size will not.
        sizing = workflow.TaskObject["Add Local Sizing"]

        step(22, "Local sizing: chassis and suspension")
        sizing.Arguments.set_state({
            "AddChild": "yes",
            "BOIControlName": "curvature_stuff",
            "BOIExecution": "Curvature",
            "BOIFaceLabelList": BODY + FRONT_SUS + REAR_SUS,
            "BOIZoneorLabel": "label",
            "BOIScopeTo": "faces and edges",
            "BOICurvatureNormalAngle": 12,
            "BOIMinSize": 0.001,
            "BOIMaxSize": 0.064,
            "BOIGrowthRate": 1.2,
            "BOICellsPerGap": 1,
        })
        sizing.AddChildAndUpdate(DeferUpdate=False, RetainValues=True)

        step(26, "Local sizing: aero surfaces")
        sizing.Arguments.set_state({
            "AddChild": "yes",
            "BOIControlName": "curvature_aero",
            "BOIExecution": "Curvature",
            "BOIFaceLabelList": AERO,
            "BOIZoneorLabel": "label",
            "BOIScopeTo": "faces and edges",
            "BOICurvatureNormalAngle": 9,
            "BOIMinSize": 0.0005,
            "BOIMaxSize": 0.008,
            "BOIGrowthRate": 1.2,
            "BOICellsPerGap": 1,
        })
        sizing.AddChildAndUpdate(DeferUpdate=False, RetainValues=True)

        step(30, "Local sizing: wheels")
        sizing.Arguments.set_state({
            "AddChild": "yes",
            "BOIControlName": "curvature_wheels",
            "BOIExecution": "Curvature",
            "BOIFaceLabelList": FRONT_WHEEL + REAR_WHEEL,
            "BOIZoneorLabel": "label",
            "BOIScopeTo": "faces",          # faces only, not edges
            "BOICurvatureNormalAngle": 18,
            "BOIMinSize": 0.0005,
            "BOIMaxSize": 0.032,
            "BOIGrowthRate": 1.2,
            "BOICellsPerGap": 1,
        })
        sizing.AddChildAndUpdate(DeferUpdate=False, RetainValues=True)

        # ── Surface mesh ──────────────────────────────────────────────────
        step(40, "Generating surface mesh")
        workflow.TaskObject["Generate the Surface Mesh"].Arguments.set_state({
            "CFDSurfaceMeshControls": {
                "MinSize": s.surface_min,
                "MaxSize": s.surface_max,
                "CellsPerGap": 3,
                "ScopeProximityTo": "faces-and-edges",
            },
        })
        workflow.TaskObject["Generate the Surface Mesh"].Execute()

        step(55, "Improving surface mesh")
        workflow.TaskObject["Generate the Surface Mesh"].InsertNextTask(
            CommandName="ImproveSurfaceMesh"
        )
        workflow.TaskObject["Improve Surface Mesh"].Arguments.set_state(
            {"FaceQualityLimit": 0.7}
        )
        workflow.TaskObject["Improve Surface Mesh"].Execute()

        # ── Geometry description, boundaries, regions ─────────────────────
        step(60, "Describing geometry")
        workflow.TaskObject["Describe Geometry"].Arguments.set_state({
            "SetupType": "The geometry consists of only fluid regions with no voids",
            "NonConformal": "No",
            "WallToInternal": "No",
        })
        workflow.TaskObject["Describe Geometry"].UpdateChildTasks(
            Arguments={"v1": True}, SetupTypeChanged=True
        )
        workflow.TaskObject["Describe Geometry"].Execute()

        step(64, "Updating boundaries and regions")
        workflow.TaskObject["Update Boundaries"].Execute()
        workflow.TaskObject["Update Regions"].Execute()

        # ── Boundary layers ───────────────────────────────────────────────
        # Aero surfaces and the ground only. Wheels are excluded: prisms on a
        # rotating wall cause more trouble than they solve.
        step(68, "Adding boundary layers")
        workflow.TaskObject["Add Boundary Layers"].Arguments.set_state({
            "BLControlName": "last-ratio_1",
            "OffsetMethodType": "last-ratio",
            "NumberOfLayers": s.bl_layers,
            "FirstHeight": s.bl_first_height,
            "FaceScope": {"GrowOn": "selected-zones"},
            "LocalPrismPreferences": {"Continuous": "Continuous"},
            "ZoneSelectionList": AERO + ["ground"],
        })
        workflow.TaskObject["Add Boundary Layers"].AddChildAndUpdate(
            DeferUpdate=False, RetainValues=True
        )

        # ── Volume mesh ───────────────────────────────────────────────────
        step(72, "Generating volume mesh, this takes a while")
        workflow.TaskObject["Generate the Volume Mesh"].Arguments.set_state({
            "VolumeFill": "poly-hexcore",
            "MeshSolidRegions": False,
            "VolumeFillControls": {
                "HexMinCellLength": s.volume_min,
                "HexMaxCellLength": s.volume_max,
            },
        })
        workflow.TaskObject["Generate the Volume Mesh"].Execute()

        step(92, "Improving volume mesh")
        workflow.TaskObject["Generate the Volume Mesh"].InsertNextTask(
            CommandName="ImproveVolumeMesh"
        )
        workflow.TaskObject["Improve Volume Mesh"].Arguments.set_state({
            "QualityMethod": "Orthogonal",
            "CellQualityLimit": 0.15,
            "AddMultipleQualityMethods": "No",
        })
        workflow.TaskObject["Improve Volume Mesh"].Execute()

        # ── Write ─────────────────────────────────────────────────────────
        step(98, f"Writing {mesh_file}")
        session.meshing.File.WriteMesh(FileName=mesh_file)

        step(100, "Meshing complete")
        return mesh_file

    finally:
        try:
            session.exit()
        except Exception:
            pass


# =============================================================================
#  SOLVING
# =============================================================================

def solve(s: Settings, mesh_file: str, log, progress=None) -> dict:
    """
    Set up physics, boundary conditions and reports, run the three ramps,
    export, and return the results.
    """
    import ansys.fluent.core as pyfluent

    def step(pct, msg):
        log.info(f"[SOLVE {pct:3d}%] {msg}")
        if progress:
            progress(msg, pct)

    step(0, "Launching Fluent solver")
    session = pyfluent.launch_fluent(
        mode="solver",
        processor_count=s.processes,
        precision="double" if s.double_precision else "single",
        product_version="26.1",
        cleanup_on_exit=True,
    )

    try:
        setup    = session.settings.setup
        solution = session.settings.solution

        step(2, f"Reading {os.path.basename(mesh_file)}")
        session.settings.file.read_mesh(file_name=mesh_file)
        session.settings.mesh.check()

        # ── Turbulence ────────────────────────────────────────────────────
        step(5, "GEKO k-omega")
        viscous = setup.models.viscous
        viscous.model = "k-omega"
        viscous.k_omega_model = "geko"
        viscous.options.production_limiter = True
        viscous.options.curvature_correction = False   # on at ramp 3

        # ── Boundary conditions ───────────────────────────────────────────
        step(8, "Boundary conditions")
        _boundary_conditions(session, s, log)

        # ── Reference values ──────────────────────────────────────────────
        step(12, "Reference values and projected area")
        area = _reference_values(session, s, log)

        # ── Reports ───────────────────────────────────────────────────────
        step(16, "Report definitions")
        _report_definitions(session, s, area, log)

        # ── Convergence ───────────────────────────────────────────────────
        for equation in ("continuity", "x-velocity", "y-velocity",
                         "z-velocity", "k", "omega"):
            try:
                solution.monitor.residual.equations[equation] \
                    .absolute_criteria = 1e-4
            except Exception:
                pass

        prefix = os.path.join(s.output_dir, s.name)

        # ── Ramp 1: first order ───────────────────────────────────────────
        step(20, f"Ramp 1: first order, {s.ramp1_iters} iterations")
        methods = solution.methods
        methods.p_v_coupling.flow_scheme = "SIMPLE"
        methods.discretization_scheme = {
            "pressure": "standard",
            "mom":      "first-order-upwind",
            "k":        "first-order-upwind",
            "omega":    "first-order-upwind",
        }
        solution.initialization.hybrid_initialize()
        solution.run_calculation.iterate(iter_count=s.ramp1_iters)
        session.settings.file.write_case_data(file_name=f"{prefix}_ramp1")

        # ── Ramp 2: second order, PRESTO pressure ─────────────────────────
        step(40, f"Ramp 2: second order, {s.ramp2_iters} iterations")
        methods.p_v_coupling.flow_scheme = "SIMPLE"
        methods.discretization_scheme = {
            "pressure": "presto!",
            "mom":      "second-order-upwind",
            "k":        "first-order-upwind",
            "omega":    "first-order-upwind",
        }
        solution.run_calculation.iterate(iter_count=s.ramp2_iters)
        session.settings.file.write_case_data(file_name=f"{prefix}_ramp2")

        # ── Ramp 3: full send ─────────────────────────────────────────────
        step(65, f"Ramp 3: full send, {s.ramp3_iters} iterations")
        methods.p_v_coupling.flow_scheme = "SIMPLEC"
        methods.discretization_scheme = {
            "pressure": "presto!",
            "mom":      "second-order-upwind",
            "k":        "second-order-upwind",
            "omega":    "second-order-upwind",
        }
        viscous.options.curvature_correction = True
        solution.run_calculation.iterate(iter_count=s.ramp3_iters)
        session.settings.file.write_case_data(file_name=f"{prefix}_final")

        # ── Exports ───────────────────────────────────────────────────────
        if s.export_ensight:
            step(90, "Exporting EnSight Gold for ParaView")
            _export_ensight(session, s, log)

        step(94, "Reading report values")
        results = _read_reports(session, s, area, log)

        step(97, "Writing results file")
        from utils.results_exporter import write_results
        results["result_file"] = write_results(s, NAME, results, log)

        step(100, "Simulation complete")
        return results

    finally:
        try:
            session.exit()
        except Exception:
            pass


def _boundary_conditions(session, s: Settings, log) -> None:
    """Inlet, outlet, ground, far-field walls and rotating wheels."""
    bc = session.settings.setup.boundary_conditions

    # Inlet
    inlet = bc.velocity_inlet["inlet"]
    inlet.momentum.velocity_magnitude.value = s.speed_ms
    inlet.turbulence.turbulent_intensity = 0.01
    inlet.turbulence.turbulent_viscosity_ratio = 1.0
    log.info(f"  inlet          {s.speed_ms:.3f} m/s")

    # Outlet
    bc.pressure_outlet["outlet"].momentum.gauge_pressure.value = 0.0
    log.info("  outlet         0 Pa gauge")

    # Ground: moving wall, translational along +X, relative to the adjacent
    # cell zone.
    ground = bc.wall["ground"]
    ground.momentum.wall_motion = "Moving Wall"
    ground.momentum.relative = True
    ground.momentum.translational = True
    ground.momentum.velocity.value = s.speed_ms
    ground.momentum.direction_component_x = 1.0
    ground.momentum.direction_component_y = 0.0
    ground.momentum.direction_component_z = 0.0
    log.info(f"  ground         moving wall, +X, {s.speed_ms:.3f} m/s")

    # Far-field walls: zero shear, i.e. slip. Without this a boundary layer
    # grows on the tunnel walls and progressively blocks the domain.
    try:
        walls = bc.wall["walls"]
        walls.momentum.shear_condition = "Specified Shear"
        walls.momentum.shear_stress.x = 0.0
        walls.momentum.shear_stress.y = 0.0
        walls.momentum.shear_stress.z = 0.0
        log.info("  walls          specified zero shear, slip")
    except Exception as exc:
        log.warning(f"  walls: {exc}")

    # Rotating wheels. Moving wall, absolute, rotational about the axle.
    omega = s.wheel_omega
    for labels, origin, corner in (
        (FRONT_WHEEL, s.front_wheel_origin, "front"),
        (REAR_WHEEL,  s.rear_wheel_origin,  "rear"),
    ):
        for label in labels:
            try:
                wall = bc.wall[label]
                wall.momentum.wall_motion = "Moving Wall"
                wall.momentum.relative = False          # absolute
                wall.momentum.rotating = True
                wall.momentum.velocity.value = omega
                wall.momentum.rotation_origin_x = origin[0]
                wall.momentum.rotation_origin_y = origin[1]
                wall.momentum.rotation_origin_z = origin[2]
                wall.momentum.rotation_axis_x = s.wheel_axis[0]
                wall.momentum.rotation_axis_y = s.wheel_axis[1]
                wall.momentum.rotation_axis_z = s.wheel_axis[2]
                log.info(f"  {label:14s} {omega:.2f} rad/s about {origin}")
            except Exception as exc:
                log.warning(f"  {label}: {exc}")


def _reference_values(session, s: Settings, log) -> float:
    """
    Compute from the inlet, then set velocity, length and the projected
    frontal area. Returns the area, or 0.0 if it could not be computed.
    """
    rv = session.settings.setup.reference_values
    try:
        rv.compute("inlet")
    except Exception as exc:
        log.debug(f"  compute from inlet: {exc}")

    rv.velocity = s.speed_ms
    rv.length = s.car_length
    rv.density = AIR_DENSITY

    area = 0.0
    try:
        walls = list(session.settings.setup.boundary_conditions.wall.keys())
        zones = [z for z in CAR if z in walls]
        pa = session.settings.results.report.projected_surface_area
        pa.min_feature_size = 0.0001
        pa.projection_direction = [1, 0, 0]
        pa.surfaces = zones
        area = float(pa.compute())
        rv.area = area
        log.info(f"  projected area {area:.6f} m^2 over {len(zones)} zones")
    except Exception as exc:
        log.warning(f"  projected area failed, coefficients will be wrong: {exc}")

    log.info(f"  reference      v={s.speed_ms:.3f} m/s  L={s.car_length} m")
    return area


def _report_definitions(session, s: Settings, area: float, log) -> None:
    """
    Create all 26 reports.

    Forces and moments are ordinary report definitions. SCz, SCx, copx, copz
    and cop_pct are Fluent expressions, so Ansys does the arithmetic and the
    values appear in the Fluent GUI alongside everything else.
    """
    rd = session.settings.solution.report_definitions
    walls = list(session.settings.setup.boundary_conditions.wall.keys())

    DOWN = [0.0, -1.0, 0.0]
    DRAG = [1.0,  0.0, 0.0]

    def present(labels):
        found = [z for z in labels if z in walls]
        missing = [z for z in labels if z not in walls]
        if missing:
            log.debug(f"    not in mesh: {missing}")
        return found

    def force(name, kind, labels, vector):
        zones = present(labels)
        if not zones:
            log.warning(f"  {name:14s} no zones present, skipped")
            return
        try:
            getattr(rd, kind)[name] = {"zones": zones, "force_vector": vector}
            log.info(f"  {name:14s} {zones}")
        except Exception as exc:
            log.warning(f"  {name}: {exc}")

    def moment(name, labels, centre, axis):
        zones = present(labels)
        if not zones:
            log.warning(f"  {name:14s} no zones present, skipped")
            return
        try:
            rd.moment[name] = {"zones": zones}
            rd.moment[name].mom_center = centre
            rd.moment[name].mom_axis = axis
            log.info(f"  {name:14s} about {centre} axis {axis}")
        except Exception as exc:
            log.warning(f"  {name}: {exc}")

    def expression(name, definition):
        try:
            rd.expression[name] = {"define": definition}
            log.info(f"  {name:14s} = {definition}")
        except Exception as exc:
            log.warning(f"  {name} expression: {exc}")

    # ── Totals ────────────────────────────────────────────────────────────
    force("fz", "lift", CAR, DOWN)
    force("fx", "drag", CAR, DRAG)

    # Coefficients use the reference area set above.
    for name, kind, vector, output in (
        ("cl", "lift", DOWN, "Lift Coefficient"),
        ("cd", "drag", DRAG, "Drag Coefficient"),
    ):
        zones = present(CAR)
        try:
            getattr(rd, kind)[name] = {"zones": zones, "force_vector": vector}
            getattr(rd, kind)[name].report_output_type = output
            log.info(f"  {name:14s} {output}")
        except Exception as exc:
            log.warning(f"  {name}: {exc}")

    # ── Per element ───────────────────────────────────────────────────────
    force("fz_frontwing", "lift", ["frontwing"], DOWN)
    force("fx_frontwing", "drag", ["frontwing"], DRAG)
    force("fz_rearwing",  "lift", ["rearwing"],  DOWN)
    force("fx_rearwing",  "drag", ["rearwing"],  DRAG)
    force("fz_undertray", "lift", ["undertray"], DOWN)
    force("fx_undertray", "drag", ["undertray"], DRAG)
    force("fz_body",      "lift", BODY, DOWN)
    force("fx_body",      "drag", BODY, DRAG)

    # ── Per corner ────────────────────────────────────────────────────────
    force("fz_fw", "lift", FRONT_WHEEL, DOWN)
    force("fx_fw", "drag", FRONT_WHEEL, DRAG)
    force("fz_rw", "lift", REAR_WHEEL,  DOWN)
    force("fx_rw", "drag", REAR_WHEEL,  DRAG)
    force("fz_frontsus", "lift", FRONT_SUS, DOWN)
    force("fx_frontsus", "drag", FRONT_SUS, DRAG)
    force("fz_rearsus",  "lift", REAR_SUS,  DOWN)
    force("fx_rearsus",  "drag", REAR_SUS,  DRAG)

    # ── Moments ───────────────────────────────────────────────────────────
    # About the origin. copx below is therefore measured from the origin, so
    # the geometry origin must sit at the front axle for cop_pct to read as
    # percent forward.
    moment("my_total", CAR, [0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
    moment("mx_total", CAR, [0.0, 0.0, 0.0], [0.0, 1.0, 0.0])

    # ── Expressions: Ansys does this arithmetic ───────────────────────────
    # Half car, so forces are doubled here rather than in Python.
    q = s.dynamic_pressure
    expression("SCz", f"2 * abs(fz) / {q}")
    expression("SCx", f"2 * abs(fx) / {q}")
    expression("copx", "my_total / fz")
    expression("copz", "mx_total / fz")
    expression("cop_pct", f"100 * (my_total / fz) / {s.wheelbase}")


def _read_reports(session, s: Settings, area: float, log) -> dict:
    """
    Read every report back. Journaling omits queries, and expressions may not
    exist on older builds, so anything Fluent could not provide is computed
    here from the raw forces instead.
    """
    rd = session.settings.solution.report_definitions
    results = {"reference_area": area, "dynamic_pressure": s.dynamic_pressure}

    def value(kind, name) -> float:
        try:
            return float(getattr(rd, kind)[name].get_value())
        except Exception:
            pass
        try:
            return float(session.settings.solution.report_definitions
                         .compute(report_defs=[name])[name][0])
        except Exception as exc:
            log.debug(f"  read {name}: {exc}")
            return 0.0

    # Half car: everything is doubled once, here.
    MULT = 2.0

    for name, (kind, _) in REPORT_DEFINITIONS.items():
        if kind == "expression":
            continue
        raw = value(kind, name)
        results[name] = raw * MULT if kind in ("lift", "drag", "moment") else raw

    # Coefficients are already normalised, so they are not doubled.
    results["cl"] = value("lift", "cl")
    results["cd"] = value("drag", "cd")

    # Derived values, preferring Fluent's own expression reports.
    for name in ("SCz", "SCx", "copx", "copz", "cop_pct"):
        results[name] = value("expression", name)

    q = s.dynamic_pressure
    if not results["SCz"]:
        results["SCz"] = abs(results["fz"]) / q if q else 0.0
    if not results["SCx"]:
        results["SCx"] = abs(results["fx"]) / q if q else 0.0
    if not results["copx"] and results["fz"]:
        results["copx"] = results["my_total"] / results["fz"]
    if not results["copz"] and results["fz"]:
        results["copz"] = results["mx_total"] / results["fz"]
    if not results["cop_pct"] and s.wheelbase:
        results["cop_pct"] = 100.0 * results["copx"] / s.wheelbase

    results["ld_ratio"] = (abs(results["fz"]) / abs(results["fx"])
                           if results["fx"] else 0.0)

    log.info(f"  Fz {results['fz']:10.2f} N     Fx {results['fx']:10.2f} N")
    log.info(f"  SCz {results['SCz']:9.4f} m^2   SCx {results['SCx']:9.4f} m^2")
    log.info(f"  CoP {results['copx']:9.4f} m     {results['cop_pct']:.1f} % forward")
    return results


def _export_ensight(session, s: Settings, log) -> None:
    """Write EnSight Gold for ParaView."""
    out = os.path.join(s.output_dir, f"{s.name}_ensight")
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, s.name)
    try:
        session.settings.file.export.ensight_gold(file_name=base)
        log.info(f"  EnSight Gold -> {out}")
    except Exception as exc:
        log.warning(f"  EnSight export failed: {exc}")


# =============================================================================
#  ENTRY POINT
# =============================================================================

def run(s: Settings, log, progress=None) -> dict:
    """
    Mesh if needed, then solve. Returns the results dictionary.

    Set `s.existing_mesh` to skip meshing and go straight to the solver.
    """
    started = time.time()

    if s.existing_mesh:
        if not os.path.isfile(s.existing_mesh):
            raise FileNotFoundError(f"Mesh not found: {s.existing_mesh}")
        log.info(f"Using existing mesh: {s.existing_mesh}")
        mesh_file = s.existing_mesh
    else:
        mesh_file = mesh(s, log, progress)

    results = solve(s, mesh_file, log, progress)
    results["runtime_s"] = time.time() - started
    log.info(f"Total runtime {results['runtime_s'] / 60:.1f} min")
    return results