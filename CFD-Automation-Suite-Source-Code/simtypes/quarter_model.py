"""
Quarter Model simulation.

Everything for this simulation type lives in this one file: the settings the
GUI edits, the meshing sequence, the solver setup, the report definitions and
the exports. Nothing is inherited or shared, so what you read here is exactly
what runs.

Geometry: ONE quarter of the car -- one corner, bounded by two symmetry
planes. This models a single wheel and the nearest wing (front OR rear, not
both), used for a quick correlation or mesh-sensitivity check on one element
without paying for a full or half car mesh.

    symmetry    z = 0, the car centreline (as in the half-car model)
    symmetry2   x = wheelbase / 2, bisecting the car front-to-rear

ASSUMPTION: the exact quarter-model convention was not specified anywhere
upstream of this file. This implementation covers the front quarter (front
wing + front wheel) by default; set `end` to "rear" in Settings for the rear
quarter instead. If your team's convention differs -- a different split
plane, or a different pair of elements -- this is the one file to edit.

Coordinate convention
    +X  toward the rear of the car = flow direction   -> drag      [ 1, 0, 0]
    +Y  up                                            -> downforce [0, -1, 0]
    +Z  driver's left                                 -> quarter model at z >= 0

All values are SI: N, N*m, m, m/s, Pa, m^2.
"""
import math
import os
import time
from dataclasses import dataclass, field

from utils.fluent_log import FluentLogCapture
from utils.naming import RunIdentity
from utils.refinement import refinement_boxes, WHEEL_BOX_SIZE, WHEEL_BOX_RATIOS

NAME = "Quarter Model"
KEY = "quarter_model"

MPH_TO_MS = 0.44704
AIR_DENSITY = 1.225          # kg/m^3

# Passed to Fluent as -mpi=<type>. "default" omits the flag entirely.
MPI_TYPES = ["intel", "openmpi", "msmpi", "default"]

# Seconds to wait for Fluent to come up. Parallel start-up on a busy node can
# be slow; beyond this it is hung rather than slow.
FLUENT_START_TIMEOUT = 300


# =============================================================================
#  NAMED SELECTIONS
#  Must match the labels created in Ansys Discovery exactly.
#  The GUI shows this table on its Named Selections tab.
# =============================================================================

# Front-quarter labels. A rear-quarter geometry uses "rearwing" in place of
# "frontwing" and "rw"/"rwb" in place of "fw"/"fwb" -- see _labels_for_end()
# below, which both the mesh and solve code call rather than reading these
# module-level names directly.
NAMED_SELECTIONS = {
    # label            (boundary type,     required, description)
    "inlet":           ("velocity-inlet",  True,  "Domain inlet, upstream face"),
    "outlet":          ("pressure-outlet", True,  "Domain outlet, downstream face"),
    "walls":           ("wall, slip",      True,  "Far-field tunnel walls, zero shear"),
    "ground":          ("wall, moving",    True,  "Ground plane, translating at car speed"),
    "symmetry":        ("symmetry",        True,  "Centreline symmetry plane, z = 0"),
    "symmetry2":       ("symmetry",        True,
                        "Second symmetry plane bisecting front-to-rear"),

    "frontwing":       ("wall",            False, "Front wing (front quarter only)"),
    "rearwing":        ("wall",            False, "Rear wing (rear quarter only)"),
    "chassis":         ("wall",            True,  "Chassis, nose and body"),
    "sidepod":         ("wall",            False, "Sidepod, only in some geometries"),

    "fw":              ("wall, rotating",  False, "Front wheel (front quarter only)"),
    "fwb":             ("wall, rotating",  False, "Front wheel block (front quarter only)"),
    "rw":              ("wall, rotating",  False, "Rear wheel (rear quarter only)"),
    "rwb":             ("wall, rotating",  False, "Rear wheel block (rear quarter only)"),

    "fl_sus": ("wall",           False, "Front left suspension members"),
    "rl_sus": ("wall",           False, "Rear left suspension members"),
}

# Labels the simulation cannot run correctly without, regardless of which
# end is modelled. The front/rear wing and wheel labels are checked
# separately in check_named_selections() once `end` is known.
REQUIRED_LABELS = [name for name, (_, required, _d)
                   in NAMED_SELECTIONS.items() if required]


def _labels_for_end(end: str) -> dict:
    """
    The aero and wheel labels for whichever end this quarter model covers.

    `end` is "front" or "rear". Anything else raises, since silently
    defaulting would mesh and solve the wrong element.
    """
    if end == "front":
        return {"aero": ["frontwing"], "wheel": ["fw", "fwb"]}
    if end == "rear":
        return {"aero": ["rearwing"],  "wheel": ["rw", "rwb"]}
    raise ValueError(f"Settings.end must be 'front' or 'rear', got {end!r}")

BODY      = ["chassis", "sidepod"]
# There is no undertray split that makes sense for a quarter model -- the
# diffuser spans the car's centreline -- so it is left out entirely here.

FRONT_SUS = ["fl_sus"]
REAR_SUS  = ["rl_sus"]


def _car_labels(end: str) -> list:
    """Every label this quarter model's mesh and reports use, for `end`."""
    ends = _labels_for_end(end)
    sus = FRONT_SUS if end == "front" else REAR_SUS
    return ends["aero"] + BODY + sus + ends["wheel"]


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
    # ── Identity ─────────────────────────────────────────────────────────
    # Project / Run / MAP match the CFD Rolling Report workbook, so a run's
    # folder name is the same string as its Master Log Point ID.
    project:    str = ""
    run:        str = ""
    map_number: int = 1
    description: str = ""       # free text, copied into the results file

    # Where the Project/Run/MAP tree is created. Set once under Settings.
    output_root: str = ""

    geometry_path: str = ""

    # Point this at an existing .msh.h5 to skip meshing entirely.
    existing_mesh: str = ""

    # Which corner this quarter model covers -- "front" or "rear". Decides
    # which wing and wheel labels are meshed, boundary-conditioned and
    # reported on. See _labels_for_end() above.
    end: str = "front"

    # ── Car dimensions [m] ───────────────────────────────────────────────
    car_length: float = 2.9      # x axis
    car_width:  float = 1.4      # z axis
    car_height: float = 1.2      # y axis
    wheelbase:  float = 1.575    # front axle to rear axle

    # ── Operating point ──────────────────────────────────────────────────
    speed_mph: float = 40.0

    # ── Fluent session ───────────────────────────────────────────────────
    # Defaults to the cores this machine actually has, capped at 40. A count
    # above the physical core count stalls Fluent during parallel start-up.
    processes:        int  = field(
        default_factory=lambda: min(40, max(1, (os.cpu_count() or 4))))
    double_precision: bool = True

    # MPI implementation. intel suits the Xeon Gold nodes; openmpi is the
    # ThreadRipper default; use "default" to let Fluent choose.
    mpi_type: str = "intel"

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
    # Origins are the RIGHT side (+Z) axle centres. The left side is the
    # same point mirrored to -Z, so one pair of fields drives all four
    # wheels rather than asking for four origins in the GUI.
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
    def identity(self) -> RunIdentity:
        return RunIdentity(project=self.project, run=self.run,
                           map_number=self.map_number, root=self.output_root)

    @property
    def name(self) -> str:
        """Point ID, e.g. R018-MAP01. Used for every file this run writes."""
        return self.identity.point_id

    @property
    def output_dir(self) -> str:
        """<root>/<project>/<run>/<point id>"""
        return self.identity.map_dir

    @property
    def results_dir(self) -> str:
        """Results sit beside the case files."""
        return self.output_dir

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
        problems = list(self.identity.validate())
        if self.end not in ("front", "rear"):
            problems.append("End must be 'front' or 'rear'")
        if not self.existing_mesh and not self.geometry_path:
            problems.append("No geometry file and no existing mesh")
        if self.geometry_path and not self.geometry_path.lower().endswith(
                (".pmdb", ".dsco")):
            problems.append("Geometry must be .pmdb or .dsco")
        if self.speed_mph <= 0:
            problems.append("Speed must be greater than zero")
        if self.processes < 1:
            problems.append("Process count must be at least 1")
        available = os.cpu_count() or 1
        if self.processes > available:
            problems.append(
                f"{self.processes} processes requested but this machine has "
                f"{available} cores. Fluent will stall during parallel "
                f"start-up.")
        if self.mpi_type not in MPI_TYPES:
            problems.append(
                f"MPI type must be one of {', '.join(MPI_TYPES)}")
        if self.surface_min >= self.surface_max:
            problems.append("Surface min size must be below max size")
        return problems




# =============================================================================
#  NAMED SELECTION HANDLING
# =============================================================================

def _available_labels(workflow, log) -> list:
    """
    The face labels the imported geometry actually defines.

    Returns an empty list if Fluent will not report them, in which case the
    caller passes its labels through unfiltered rather than guessing.
    """
    try:
        task = workflow.TaskObject["Add Local Sizing"]
    except Exception:
        return []

    for attempt in (
        lambda: task.Arguments.get_attr("BOIFaceLabelList/allowedValues"),
        lambda: task.Arguments.getAttribValue("BOIFaceLabelList/allowedValues"),
        lambda: task.Arguments["BOIFaceLabelList"].get_attr("allowedValues"),
    ):
        try:
            values = attempt()
            if values:
                return sorted(str(v) for v in values)
        except Exception:
            continue

    log.debug("  Could not query the geometry's labels")
    return []


def _filter(labels: list, available: list, purpose: str, log) -> list:
    """
    Keep only labels the geometry defines.

    Passing a label Fluent does not know rejects the whole control, so an
    optional selection that is absent would otherwise take the required ones
    down with it.
    """
    if not available:
        return labels                       # unknown, so change nothing

    kept = [l for l in labels if l in available]
    missing = [l for l in labels if l not in available]
    if missing:
        log.info(f"    {purpose}: skipping absent {missing}")
    return kept


def check_named_selections(workflow, log) -> list:
    """
    Report which named selections the geometry provides, straight after
    import. Returns the missing required ones.
    """
    available = _available_labels(workflow, log)
    if not available:
        log.warning("  Could not read the geometry's named selections; "
                    "continuing without checking them")
        return []

    log.info(f"  Geometry defines {len(available)} labels: {available}")

    missing_required = []
    missing_optional = []
    for name, (_type, required, _desc) in NAMED_SELECTIONS.items():
        if name in available:
            continue
        (missing_required if required else missing_optional).append(name)

    if missing_optional:
        log.info(f"  Optional labels not present: {missing_optional}")

    if missing_required:
        log.error(f"  MISSING REQUIRED LABELS: {missing_required}")
        log.error("  Add these named selections in Ansys Discovery and "
                  "re-export the .pmdb. The mesh will be wrong without them.")

    unexpected = [l for l in available
                  if l not in NAMED_SELECTIONS
                  and not l.startswith("enclosure")]
    if unexpected:
        log.info(f"  Labels in the geometry the suite does not use: "
                 f"{unexpected}")

    return missing_required


# =============================================================================
#  FLUENT LAUNCH
# =============================================================================

def _launch(mode: str, s: Settings, log):
    """
    Start Fluent and report exactly what was requested.

    A run that appears to hang with no CPU activity is almost always a launch
    problem rather than a meshing problem, so the arguments, the core count
    and the MPI choice are all logged before the call and the connection is
    confirmed afterwards.

    Fluent writes its transcript, cleanup scripts and other working files to
    the process's working directory. Without `cwd`, that is wherever the
    suite itself was launched from -- the VS Code project folder when run
    from source, or the install folder when run as an exe -- rather than the
    run's own output folder. Setting cwd here fixes it in both cases; the
    exe alone would not have.
    """
    import ansys.fluent.core as pyfluent

    available = os.cpu_count() or 1
    requested = int(s.processes)

    if requested > available:
        log.warning(
            f"  {requested} processes requested but this machine reports "
            f"{available} cores.")
        log.warning(
            f"  Fluent may fail to start or stall during parallel setup. "
            f"Lower the process count on the General tab.")

    work_dir = s.identity.create_dirs()

    args = dict(
        mode=mode,
        processor_count=requested,
        precision="double" if s.double_precision else "single",
        product_version="26.1",
        cleanup_on_exit=True,
        start_timeout=FLUENT_START_TIMEOUT,
        cwd=work_dir,
    )
    if s.mpi_type and s.mpi_type != "default":
        args["additional_arguments"] = f"-mpi={s.mpi_type}"

    log.info(f"  mode           {mode}")
    log.info(f"  processes      {requested}  (machine has {available} cores)")
    log.info(f"  precision      {args['precision']}")
    log.info(f"  mpi            {s.mpi_type}")
    log.info(f"  extra args     {args.get('additional_arguments', '(none)')}")
    log.info(f"  working dir    {work_dir}")
    log.info(f"  start timeout  {FLUENT_START_TIMEOUT}s")
    log.info(f"  AWP_ROOT261    {os.environ.get('AWP_ROOT261', 'NOT SET')}")

    started = time.time()
    session = pyfluent.launch_fluent(**args)
    log.info(f"  Fluent connected in {time.time() - started:.1f}s")

    # Confirm the session really is parallel. A silent fall back to serial is
    # the usual reason a run appears to hang with one core busy and the rest
    # idle.
    try:
        actual = session.scheme_eval.scheme_eval("(rpgetvar 'parallel/nprocs)")
        log.info(f"  Fluent reports  {actual} compute node(s)")
        if requested > 1 and str(actual).strip() in ("1", "1.0"):
            log.warning(
                f"  Fluent started SERIAL despite requesting {requested} "
                f"processes. Check the MPI type: intel needs Intel MPI "
                f"installed, msmpi is the usual Windows fallback.")
    except Exception as exc:
        log.debug(f"  Could not read node count: {exc}")

    return session


# =============================================================================
#  MESHING
# =============================================================================

def mesh(s: Settings, log, progress=None, control=None) -> str:
    """
    Run the Watertight Geometry workflow and write the mesh.
    Returns the mesh file path.

    `control` lets the queue stop the run: step() checks it, and the session
    is registered so it can be forced down mid-call.
    """
    def step(pct, msg):
        if control:
            control.check()
        log.info(f"[MESH {pct:3d}%] {msg}")
        if progress:
            progress(msg, pct)

    os.makedirs(s.output_dir, exist_ok=True)
    mesh_file = os.path.join(s.output_dir, "mesh.msh.h5")

    step(0, f"Launching Fluent Meshing "
            f"({s.processes} processes, {s.mpi_type} MPI)")
    session = _launch("meshing", s, log)
    if control:
        control.register(session)

    # Everything Fluent prints now appears in the application log.
    transcript = FluentLogCapture(session, log,
                                  output_dir=s.output_dir, tag="mesh").start()

    end_labels = _labels_for_end(s.end)
    aero_labels  = end_labels["aero"]
    wheel_labels = end_labels["wheel"]
    sus_labels   = FRONT_SUS if s.end == "front" else REAR_SUS
    log.info(f"  Quarter model: {s.end} end "
             f"(aero={aero_labels}, wheel={wheel_labels})")

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

        # ── Named selections ──────────────────────────────────────────────
        # Checked here, immediately after import, so a geometry missing a
        # label fails in seconds rather than after an hour of meshing.
        step(8, "Checking named selections")
        missing = check_named_selections(workflow, log)
        if missing:
            raise RuntimeError(
                "Geometry is missing required named selections: "
                + ", ".join(missing)
                + ". Add them in Ansys Discovery and re-export the .pmdb.")
        available = _available_labels(workflow, log)

        # ── Local refinement regions ──────────────────────────────────────
        step(12, "Creating refinement regions")
        workflow.TaskObject["Import Geometry"].InsertNextTask(
            CommandName="CreateLocalRefinementRegions"
        )
        refine = workflow.TaskObject["Create Local Refinement Regions"]

        for box in refinement_boxes(s.car_length, s.car_width, s.car_height,
                                    half_model=False):     # full car -- z is not clamped
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

        # Wheel box is sized relative to the wheel body, so it needs the
        # wheel labels rather than coordinates. Only one corner exists here.
        for region_name, labels in (
            (f"local-refinement-{s.end}wheel",
             _filter(wheel_labels, available, f"{s.end} wheel box", log)),
        ):
            if not labels:
                log.warning(f"  {region_name}: no wheel labels present, "
                            f"skipped")
                continue
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
            "BOIFaceLabelList": _filter(BODY + sus_labels,
                                        available, "curvature_stuff", log),
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
            "BOIFaceLabelList": _filter(aero_labels, available,
                                        "curvature_aero", log),
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
            "BOIFaceLabelList": _filter(wheel_labels,
                                        available, "curvature_wheels", log),
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
            "ZoneSelectionList": _filter(aero_labels + ["ground"], available,
                                         "boundary layers", log),
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
        transcript.stop()
        if control:
            control.release(session)
        try:
            session.exit()
        except Exception:
            pass


# =============================================================================
#  SOLVING
# =============================================================================

def solve(s: Settings, mesh_file: str, log, progress=None,
          control=None) -> dict:
    """
    Set up physics, boundary conditions and reports, run the three ramps,
    export, and return the results.

    `control` lets the queue stop the run: step() checks it, and the session
    is registered so it can be forced down mid-iteration.
    """
    def step(pct, msg):
        if control:
            control.check()
        log.info(f"[SOLVE {pct:3d}%] {msg}")
        if progress:
            progress(msg, pct)

    step(0, f"Launching Fluent solver "
            f"({s.processes} processes, {s.mpi_type} MPI)")
    session = _launch("solver", s, log)
    if control:
        control.register(session)

    # Residuals and force monitors stream into the application log.
    transcript = FluentLogCapture(session, log,
                                  output_dir=s.output_dir, tag="solve").start()

    try:
        setup    = session.settings.setup
        solution = session.settings.solution

        step(2, f"Reading {os.path.basename(mesh_file)}")
        session.settings.file.read_mesh(file_name=mesh_file)
        session.settings.mesh.check()

        # ── Turbulence ────────────────────────────────────────────────────
        step(5, "GEKO k-omega")
        viscous = setup.models.viscous

        # Each set individually and logged, so a Scheme-level failure (e.g.
        # "ASSQ: invalid argument: improper list") names the exact call that
        # caused it. `required=True` still aborts the run -- model and
        # k_omega_model must succeed or GEKO isn't actually running.
        # `required=False` logs a warning and moves on, since a turbulence
        # option defaulting to Fluent's own value is not worth failing an
        # hour-long run over. Several attribute paths are tried in order,
        # since Fluent 2026 R1's settings API rejected "options.<flag>" for
        # some flags on this build -- see CHANGELOG.md.
        def _set_viscous(attr_paths, value, required=True):
            paths = [attr_paths] if isinstance(attr_paths, str) else attr_paths
            last_exc = None
            for attr_path in paths:
                obj = viscous
                parts = attr_path.split(".")
                try:
                    for part in parts[:-1]:
                        obj = getattr(obj, part)
                    setattr(obj, parts[-1], value)
                    log.info(f"  viscous.{attr_path} = {value}")
                    return
                except Exception as exc:
                    last_exc = exc
                    log.debug(f"  viscous.{attr_path} = {value}  failed: {exc}")
            if required:
                log.error(f"  viscous.{paths[0]} = {value}  FAILED "
                          f"(tried {paths}): {last_exc}")
                raise last_exc
            log.warning(f"  viscous.{paths[0]} = {value}  could not be set "
                       f"(tried {paths}) -- continuing with Fluent's default")

        _set_viscous("model", "k-omega")
        _set_viscous("k_omega_model", "geko")
        _set_viscous(
            ["options.production_limiter", "production_limiter"],
            True, required=False)
        _set_viscous(
            ["options.curvature_correction", "curvature_correction"],
            False, required=False)   # on at ramp 3

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
        for _attr in ("options.curvature_correction", "curvature_correction"):
            try:
                obj = viscous
                parts = _attr.split(".")
                for part in parts[:-1]:
                    obj = getattr(obj, part)
                setattr(obj, parts[-1], True)
                log.info(f"  viscous.{_attr} = True  (ramp 3)")
                break
            except Exception as _exc:
                log.debug(f"  viscous.{_attr} ramp 3: {_exc}")
        else:
            log.warning("  Could not enable curvature correction for "
                       "ramp 3 -- continuing without it")
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
        transcript.stop()
        if control:
            control.release(session)
        try:
            session.exit()
        except Exception:
            pass


def _boundary_conditions(session, s: Settings, log) -> None:
    """Inlet, outlet, ground, far-field walls and rotating wheels."""
    bc = session.settings.setup.boundary_conditions

    # What the mesh actually contains. A boundary condition applied to a
    # zone that is not there raises, so each is checked first and reported
    # rather than taking the whole run down.
    try:
        walls = list(bc.wall.keys())
    except Exception:
        walls = []
    log.info(f"  mesh has {len(walls)} wall zone(s)")

    # Inlet
    try:
        inlet = bc.velocity_inlet["inlet"]
        inlet.momentum.velocity_magnitude.value = s.speed_ms
        inlet.turbulence.turbulent_intensity = 0.01
        inlet.turbulence.turbulent_viscosity_ratio = 1.0
        log.info(f"  inlet          {s.speed_ms:.3f} m/s")
    except Exception as exc:
        raise RuntimeError(
            f"Could not set the inlet boundary condition: {exc}. "
            f"The mesh must contain a velocity-inlet zone named 'inlet'."
        ) from exc

    # Outlet
    try:
        bc.pressure_outlet["outlet"].momentum.gauge_pressure.value = 0.0
        log.info("  outlet         0 Pa gauge")
    except Exception as exc:
        raise RuntimeError(
            f"Could not set the outlet boundary condition: {exc}. "
            f"The mesh must contain a pressure-outlet zone named 'outlet'."
        ) from exc

    # Ground: moving wall, translational along +X, relative to the adjacent
    # cell zone. Without it the floor is stationary and the underbody flow is
    # wrong, so a missing ground stops the run.
    if "ground" not in walls and walls:
        raise RuntimeError(
            "The mesh has no wall zone named 'ground'. Without a moving "
            "ground the underbody flow is invalid.")
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
        far_field = bc.wall["walls"]     # do not shadow the `walls` name list
        far_field.momentum.shear_condition = "Specified Shear"
        far_field.momentum.shear_stress.x = 0.0
        far_field.momentum.shear_stress.y = 0.0
        far_field.momentum.shear_stress.z = 0.0
        log.info("  walls          specified zero shear, slip")
    except Exception as exc:
        log.warning(f"  walls: {exc}")
        log.warning("  Far-field walls are no-slip; a boundary layer will "
                    "grow on them and inflate drag.")

    # Rotating wheel -- just the one, at whichever axle this quarter model
    # covers. front_wheel_origin is used for a front quarter model,
    # rear_wheel_origin for a rear one.
    omega = s.wheel_omega
    wheel_labels = _labels_for_end(s.end)["wheel"]
    origin = s.front_wheel_origin if s.end == "front" else s.rear_wheel_origin

    present = [l for l in wheel_labels if not walls or l in walls]
    if not present:
        log.warning(f"  {s.end} wheel: none of {wheel_labels} are in the "
                    f"mesh, so it will not rotate")
    for label in present:
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
        zones = [z for z in _car_labels(s.end) if z in walls]
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
    Create reports for the {s.end} corner this quarter model covers.

    Forces and moments are ordinary report definitions. SCz, SCx, copx, copz
    and cop_pct are Fluent expressions, so Ansys does the arithmetic.

    Only one wing, one wheel and one suspension pair exist in a quarter
    model, so fz_frontwing/fz_rearwing etc. are still created for whichever
    end is modelled but read back as zero for the other -- see
    _read_reports() for how the missing side is represented.
    """
    rd = session.settings.solution.report_definitions
    walls = list(session.settings.setup.boundary_conditions.wall.keys())

    end_labels = _labels_for_end(s.end)
    aero_labels = end_labels["aero"]
    wheel_labels = end_labels["wheel"]
    sus_labels = FRONT_SUS if s.end == "front" else REAR_SUS
    car_labels = _car_labels(s.end)

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
    force("fz", "lift", car_labels, DOWN)
    force("fx", "drag", car_labels, DRAG)

    # Coefficients use the reference area set above.
    for name, kind, vector, output in (
        ("cl", "lift", DOWN, "Lift Coefficient"),
        ("cd", "drag", DRAG, "Drag Coefficient"),
    ):
        zones = present(car_labels)
        try:
            getattr(rd, kind)[name] = {"zones": zones, "force_vector": vector}
            getattr(rd, kind)[name].report_output_type = output
            log.info(f"  {name:14s} {output}")
        except Exception as exc:
            log.warning(f"  {name}: {exc}")

    # ── Per element -- only the end this quarter model covers exists ──────
    if s.end == "front":
        force("fz_frontwing", "lift", aero_labels, DOWN)
        force("fx_frontwing", "drag", aero_labels, DRAG)
    else:
        force("fz_rearwing", "lift", aero_labels, DOWN)
        force("fx_rearwing", "drag", aero_labels, DRAG)
    force("fz_body", "lift", BODY, DOWN)
    force("fx_body", "drag", BODY, DRAG)

    # ── Per corner ────────────────────────────────────────────────────────
    fz_key, fx_key = ("fz_fw", "fx_fw") if s.end == "front" else ("fz_rw", "fx_rw")
    force(fz_key, "lift", wheel_labels, DOWN)
    force(fx_key, "drag", wheel_labels, DRAG)

    sus_fz_key, sus_fx_key = (
        ("fz_frontsus", "fx_frontsus") if s.end == "front"
        else ("fz_rearsus", "fx_rearsus"))
    force(sus_fz_key, "lift", sus_labels, DOWN)
    force(sus_fx_key, "drag", sus_labels, DRAG)

    # ── Moments ───────────────────────────────────────────────────────────
    # About the origin. copx below is therefore measured from the origin, so
    # the geometry origin must sit at the front axle for cop_pct to read as
    # percent forward.
    moment("my_total", car_labels, [0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
    moment("mx_total", car_labels, [0.0, 0.0, 0.0], [0.0, 1.0, 0.0])

    # ── Expressions: Ansys does this arithmetic ───────────────────────────
    # Two symmetry planes means this mesh is one quarter of the car, so
    # multiply by 4 to represent the whole car -- the same principle as the
    # half-car model's factor of 2, just twice over.
    q = s.dynamic_pressure
    expression("SCz", f"4 * abs(fz) / {q}")
    expression("SCx", f"4 * abs(fx) / {q}")
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

    # Two symmetry planes: this mesh is one quarter of the car, so fz/fx/
    # moments are multiplied by 4 to represent the full car -- consistent
    # with the SCz/SCx expressions above.
    MULT = 4.0

    for name, (kind, _) in REPORT_DEFINITIONS.items():
        if kind == "expression":
            continue
        raw = value(kind, name)
        results[name] = raw * MULT if kind in ("lift", "drag", "moment") else raw

    # Coefficients are already normalised, so they are not multiplied.
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

def run(s: Settings, log, progress=None, control=None) -> dict:
    """
    Mesh if needed, then solve. Returns the results dictionary.

    Set `s.existing_mesh` to skip meshing and go straight to the solver.
    `control` is supplied by the queue and allows the run to be stopped.
    """
    started = time.time()

    # Create <root>/<project>/<run>/<point id> up front so mesh, case files,
    # EnSight export and the results file all land together.
    s.identity.create_dirs()
    log.info(f"Point ID   {s.name}")
    log.info(f"Folder     {s.output_dir}")

    if s.existing_mesh:
        if not os.path.isfile(s.existing_mesh):
            raise FileNotFoundError(f"Mesh not found: {s.existing_mesh}")
        log.info(f"Using existing mesh: {s.existing_mesh}")
        mesh_file = s.existing_mesh
    else:
        mesh_file = mesh(s, log, progress, control)

    results = solve(s, mesh_file, log, progress, control)
    results["runtime_s"] = time.time() - started
    log.info(f"Total runtime {results['runtime_s'] / 60:.1f} min")
    return results