# batch_postprocess.py
# Run with: pvpython batch_postprocess.py [flags]
#
# Examples:
#   pvpython batch_postprocess.py --all
#   pvpython batch_postprocess.py --contours --streamlines
#   pvpython batch_postprocess.py --movies --views side --fields static_pressure
#   pvpython batch_postprocess.py --slices --views top front
#   pvpython batch_postprocess.py --list
#
# Headless on HPC: pvbatch --mesa batch_postprocess.py --all

from paraview.simple import *
import os
import sys
import argparse

paraview.simple._DisableFirstRenderCameraReset()

# ============================================================
# CASES - populate one entry per Fluent run
# ============================================================
CASES = [
    {"name": "case_001", "file": r"C:\Users\Hayes Dodson\Downloads\data\FLTG-Setup-Output.encas", "out": r"C:\Users\Hayes Dodson\Downloads\test"},
    # add more cases here
]

# ============================================================
# GEOMETRY - block names (confirmed via GUI trace, root node is '/Root/')
# ============================================================
CAR_BLOCKS = [
    '/Root/undertray',
    '/Root/rearwing',
    '/Root/frontwing',
    '/Root/chassis',
    '/Root/front_sus',
    '/Root/rear_sus',
    '/Root/rw',
    '/Root/fw',
    '/Root/rwb',
    '/Root/fwb',
]
FLUID_BLOCK = ['/Root/enclosureenclosure11']

# ============================================================
# BOUNDS
# ============================================================
CAR_BOUNDS = {
    "x": (-1.8415, 1.23425),
    "y": (0.0, 1.32862),
    "z": (-0.70231, 0.70231),
}

WASH_BOUNDS = {
    "x": (-1.0, 2.5),
    "y": (0.0, 1.8),
    "z": (0.0, 1.8),
}

# ============================================================
# FIELDS
# ============================================================
FIELDS = {
    "velocity": "Velocity_Magnitude",
    "static_pressure": "Static_Pressure",
    "total_pressure": "Total_Pressure",
}
FIELD_RANGES = {
    "Velocity_Magnitude": [0, 30],
    "Static_Pressure": [-750, 250],
    "Total_Pressure": [-750, 300],
}
COLOR_PRESET = 'Rainbow Uniform'
ALL_COLOR_FIELDS = ["Velocity_Magnitude", "Static_Pressure", "Total_Pressure", "Skin_Friction_Coefficient"]

ALL_FIELD_KEYS = ["velocity", "static_pressure", "total_pressure"]
ALL_VIEW_NAMES = ["top", "side", "front"]

# ============================================================
# ISOSURFACES
# ============================================================
ISOSURFACE_FIELD = 'Q_Criterion_Normalized'
ISOSURFACE_VALUE = 1.0
ISOSURFACE_COLOR_FIELD = 'Velocity_Magnitude'

IMG_SIZE = [3840, 2160]
FRONT_IMG_SIZE = IMG_SIZE

N_SWEEP_FRAMES = 120  # 24fps x 5 seconds
SLICE_STEP = 0.05     # 50mm
MOVIE_FRAMERATE = 24

MOVIE_SWEEP_RANGES = {
    "front": (-1.0, 2.5),
    "side": (1.0, 0.0),
    "top": (1.5, 0.0),
}

# ============================================================
# STREAMLINE SEEDING
# ============================================================
STREAMLINE_SEED_MAIN = {
    "center": [CAR_BOUNDS["x"][0] - 0.5, 0.55, 0.0],
    "radius": 0.65,
    "n_points": 600,
}
STREAMLINE_SEED_UNDERFLOOR = {
    "center": [CAR_BOUNDS["x"][0] - 0.25, 0.06, 0.0],
    "radius": 0.55,
    "n_points": 500,
}

# ============================================================
# FIXED CAMERAS
# ============================================================
CAM_ISO = {
    "position": [-5.168290238998194, 3.1907989459561232, 3.859907198505371],
    "focal_point": [-0.33957097312688794, 0.6451492970271008, 0.12655292696877032],
    "view_up": [0.29551835849896174, 0.922845130744072, -0.24703393380674607],
}
CAM_UNDERSIDE_ISO = {
    "position": [-2.78343145444443, -5.521651747384183, 2.809984883765469],
    "focal_point": [-0.3477141510178081, 0.11215029862658193, 0.3478005436634496],
    "view_up": [-0.6618338173671472, 0.521496331899044, 0.5385327975203293],
}


def apply_perspective_camera(view, cam):
    view.CameraParallelProjection = 0
    view.CameraPosition = cam["position"]
    view.CameraFocalPoint = cam["focal_point"]
    view.CameraViewUp = cam["view_up"]


CAM_FRONT = {
    "position": [-2.7083522739750983, 0.9135278128072652, 1.1695509914959028],
    "focal_point": [-0.6499999761581421, 0.9135278128072652, 1.1695509914959028],
    "view_up": [0, 1, 0],
}
CAM_SIDE = {
    "position": [0.8294243044063128, 1.582674436005691, 6.277717263679178],
    "focal_point": [0.8294243044063128, 1.582674436005691, 3.451149174643433],
    "view_up": [0, 1, 0],
}
CAM_TOP = {
    "position": [0.751265683965002, -8.001096802782317, 2.2228029730645984],
    "focal_point": [0.751265683965002, 0.25, 2.2228029730645984],
    "view_up": [0, 0, 1],
}

CAMS_BY_VIEW = {"front": CAM_FRONT, "side": CAM_SIDE, "top": CAM_TOP}
AXIS_FOR_VIEW = {"front": "x", "side": "z", "top": "y"}
NORMAL_VEC = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def camera_following_slice(view_name, slice_pos, sweep_start):
    base = CAMS_BY_VIEW[view_name]
    axis = AXIS_FOR_VIEW[view_name]
    delta = slice_pos - sweep_start
    shift = [0.0, 0.0, 0.0]
    shift[AXIS_INDEX[axis]] = delta
    return {
        "position": [base["position"][i] + shift[i] for i in range(3)],
        "focal_point": [base["focal_point"][i] + shift[i] for i in range(3)],
        "view_up": base["view_up"],
    }


# ============================================================
# COLOR PRESET HELPER
# ============================================================
def hide_all_known_scalar_bars(view):
    for f in ALL_COLOR_FIELDS:
        try:
            ctf = GetColorTransferFunction(f)
            GetScalarBar(ctf, view).Visibility = 0
        except Exception:
            pass


def apply_color_preset(view, field):
    hide_all_known_scalar_bars(view)
    ctf = GetColorTransferFunction(field)
    ctf.RescaleTransferFunction(*FIELD_RANGES[field])
    ctf.ApplyPreset(COLOR_PRESET, True)
    sb = GetScalarBar(ctf, view)
    sb.WindowLocation = 'Any Location'
    sb.Position = [0.90, 0.35]
    sb.ScalarBarLength = 0.30
    return ctf


# ============================================================
# PIPELINE BUILD
# ============================================================
REFLECT_FLUID_BLOCK = False


def _make_reflect(input_proxy):
    reflect = AxisAlignedReflect(Input=input_proxy)
    reflect.ReflectionPlane.Set(
        Origin=[0.0, 0.0, 0.0],
        Normal=[0.0, 0.0, 1.0],
    )
    reflect.ReflectAllInputArrays = 1
    reflect.UpdatePipeline()
    return reflect


def build_pipeline(case_file, need_car=True, need_fluid=True):
    """Only builds the branches actually needed by the selected steps, which
    matters a lot for memory: the fluid branch alone is ~20M cells."""
    reader = OpenDataFile(case_file)
    reader.UpdatePipeline()

    car_reflect = None
    fluid_source = None

    if need_car:
        car_extract = ExtractBlock(Input=reader)
        car_extract.Selectors = CAR_BLOCKS
        car_extract.UpdatePipeline()

        n_cells = car_extract.GetDataInformation().GetNumberOfCells()
        print(f"  [check] Car ExtractBlock cell count: {n_cells}")
        if n_cells == 0:
            raise RuntimeError(
                "Car ExtractBlock produced 0 cells. CAR_BLOCKS selector strings don't match "
                "this file's hierarchy."
            )

        car_reflect = _make_reflect(car_extract)
        print(f"  [check] Car reflect cell count: {car_reflect.GetDataInformation().GetNumberOfCells()}")

    if need_fluid:
        fluid_extract = ExtractBlock(Input=reader)
        fluid_extract.Selectors = FLUID_BLOCK
        fluid_extract.UpdatePipeline()

        n_fluid_cells = fluid_extract.GetDataInformation().GetNumberOfCells()
        print(f"  [check] Fluid ExtractBlock cell count: {n_fluid_cells}")
        if n_fluid_cells == 0:
            raise RuntimeError(
                "Fluid ExtractBlock produced 0 cells. FLUID_BLOCK selector doesn't match "
                "this file's hierarchy."
            )

        if REFLECT_FLUID_BLOCK:
            fluid_source = _make_reflect(fluid_extract)
            print(f"  [check] Fluid reflect cell count: {fluid_source.GetDataInformation().GetNumberOfCells()}")
        else:
            fluid_source = fluid_extract

    return {"car": car_reflect, "fluid": fluid_source}


# ============================================================
# 1-2: CONTOURS
# ============================================================
def save_contour(source, view, field, filename, out_dir):
    sub_dir = os.path.join(out_dir, "contours")
    os.makedirs(sub_dir, exist_ok=True)
    disp = Show(source, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color_preset(view, field)
    disp.SetScalarBarVisibility(view, True)
    Render()
    SaveScreenshot(os.path.join(sub_dir, filename), view, ImageResolution=IMG_SIZE)
    GetScalarBar(ctf, view).Visibility = 0
    Hide(source, view)


# ============================================================
# 5: CENTERLINE PRESSURE GRAPH
# ============================================================
def save_centerline_graph(source, out_dir, name):
    sub_dir = os.path.join(out_dir, "graphs", "centerline")
    os.makedirs(sub_dir, exist_ok=True)
    x0, x1 = CAR_BOUNDS["x"]
    pol = PlotOverLine(Input=source)
    pol.Point1 = [x0, 0.05, 0.0]
    pol.Point2 = [x1, 0.05, 0.0]
    pol.UpdatePipeline()
    SaveData(os.path.join(sub_dir, f"{name}_centerline_pressure.csv"),
             proxy=pol, WriteTimeSteps=False)
    Delete(pol)


# ============================================================
# 6-9: STREAMLINES
# ============================================================
def save_streamlines(source, car_source, view, field, filename, out_dir):
    sub_dir = os.path.join(out_dir, "streamlines")
    os.makedirs(sub_dir, exist_ok=True)

    tracer_main = StreamTracer(Input=source, SeedType='Point Cloud')
    tracer_main.SeedType.Center = STREAMLINE_SEED_MAIN["center"]
    tracer_main.SeedType.Radius = STREAMLINE_SEED_MAIN["radius"]
    tracer_main.SeedType.NumberOfPoints = STREAMLINE_SEED_MAIN["n_points"]
    tracer_main.Vectors = ['POINTS', 'Velocity']
    tracer_main.MaximumStreamlineLength = 8

    tracer_under = StreamTracer(Input=source, SeedType='Point Cloud')
    tracer_under.SeedType.Center = STREAMLINE_SEED_UNDERFLOOR["center"]
    tracer_under.SeedType.Radius = STREAMLINE_SEED_UNDERFLOOR["radius"]
    tracer_under.SeedType.NumberOfPoints = STREAMLINE_SEED_UNDERFLOOR["n_points"]
    tracer_under.Vectors = ['POINTS', 'Velocity']
    tracer_under.MaximumStreamlineLength = 8

    combined = AppendDatasets(Input=[tracer_main, tracer_under])
    combined.UpdatePipeline()

    car_disp = Show(car_source, view)
    car_disp.Representation = 'Surface'
    ColorBy(car_disp, None)
    car_disp.AmbientColor = [0.6, 0.6, 0.6]
    car_disp.DiffuseColor = [0.6, 0.6, 0.6]

    disp = Show(combined, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color_preset(view, field)
    disp.SetScalarBarVisibility(view, True)
    Render()
    SaveScreenshot(os.path.join(sub_dir, filename), view, ImageResolution=IMG_SIZE)
    GetScalarBar(ctf, view).Visibility = 0
    Delete(combined)
    Delete(tracer_under)
    Delete(tracer_main)
    Hide(car_source, view)


# ============================================================
# 10: SWEEPING SLICE MOVIES (native ParaView animation engine)
# ============================================================
def make_sweep_movie(source, view_name, view, field, lo, hi, out_dir, name, field_key):
    sub_dir = os.path.join(out_dir, "movies_mp4")
    os.makedirs(sub_dir, exist_ok=True)
    axis = AXIS_FOR_VIEW[view_name]
    axis_index = AXIS_INDEX[axis]
    img_size = FRONT_IMG_SIZE if view_name == "front" else IMG_SIZE
    view.ViewSize = img_size

    slice1 = Slice(registrationName='NativeSweepSlice', Input=source)
    slice1.SliceType.Normal = NORMAL_VEC[axis]
    origin0 = [0.0, 0.0, 0.0]
    origin0[axis_index] = lo
    slice1.SliceType.Origin = origin0

    disp = Show(slice1, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color_preset(view, field)
    disp.SetScalarBarVisibility(view, True)

    base_cam = CAMS_BY_VIEW[view_name]
    apply_perspective_camera(view, base_cam)

    scene = GetAnimationScene()
    scene.PlayMode = 'Sequence'
    scene.NumberOfFrames = N_SWEEP_FRAMES

    origin_track = GetAnimationTrack('Origin', index=axis_index, proxy=slice1.SliceType)
    origin_kf0 = CompositeKeyFrame()
    origin_kf0.KeyTime = 0.0
    origin_kf0.KeyValues = [lo]
    origin_kf1 = CompositeKeyFrame()
    origin_kf1.KeyTime = 1.0
    origin_kf1.KeyValues = [hi]
    origin_track.KeyFrames = [origin_kf0, origin_kf1]

    delta = hi - lo
    shift = [0.0, 0.0, 0.0]
    shift[axis_index] = delta
    end_position = [base_cam["position"][i] + shift[i] for i in range(3)]
    end_focal = [base_cam["focal_point"][i] + shift[i] for i in range(3)]

    camera_track = GetCameraTrack(view)
    cam_kf0 = CameraKeyFrame()
    cam_kf0.KeyTime = 0.0
    cam_kf0.Position = base_cam["position"]
    cam_kf0.FocalPoint = base_cam["focal_point"]
    cam_kf0.ViewUp = base_cam["view_up"]
    cam_kf1 = CameraKeyFrame()
    cam_kf1.KeyTime = 1.0
    cam_kf1.Position = end_position
    cam_kf1.FocalPoint = end_focal
    cam_kf1.ViewUp = base_cam["view_up"]
    camera_track.KeyFrames = [cam_kf0, cam_kf1]

    out_path = os.path.join(sub_dir, f"{name}_{view_name}_{field_key}.mp4")
    SaveAnimation(out_path, view, ImageResolution=img_size,
                  FrameRate=MOVIE_FRAMERATE, FrameWindow=[0, N_SWEEP_FRAMES - 1])

    GetScalarBar(ctf, view).Visibility = 0
    Delete(slice1)
    view.ViewSize = IMG_SIZE
    print(f"  [movie] wrote {out_path}")


# ============================================================
# 11: 50MM SLICE DECKS
# ============================================================
def make_slice_deck(source, view_name, view, field, bounds, out_dir, name, field_key):
    sub_dir = os.path.join(out_dir, "slices", view_name, field_key)
    os.makedirs(sub_dir, exist_ok=True)
    axis = AXIS_FOR_VIEW[view_name]
    lo, hi = bounds[axis]
    n_steps = int(round((hi - lo) / SLICE_STEP))
    img_size = FRONT_IMG_SIZE if view_name == "front" else IMG_SIZE
    view.ViewSize = img_size

    slice1 = Slice(Input=source)
    slice1.SliceType.Normal = NORMAL_VEC[axis]

    disp = Show(slice1, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color_preset(view, field)
    disp.SetScalarBarVisibility(view, True)

    for i in range(n_steps + 1):
        pos = lo + i * SLICE_STEP
        origin = [0.0, 0.0, 0.0]
        origin[AXIS_INDEX[axis]] = pos
        slice1.SliceType.Origin = origin
        apply_perspective_camera(view, camera_following_slice(view_name, pos, lo))
        Render()
        tag = f"{axis}{pos * 1000:+04.0f}mm".replace("+", "p").replace("-", "m")
        SaveScreenshot(os.path.join(sub_dir, f"{tag}.png"),
                        view, ImageResolution=img_size)

    GetScalarBar(ctf, view).Visibility = 0
    Delete(slice1)
    view.ViewSize = IMG_SIZE
    print(f"  [slices] wrote {n_steps + 1} images to {sub_dir}")


# ============================================================
# 12: SPANWISE STATIC PRESSURE GRAPHS
# ============================================================
def make_spanwise_pressure_graphs(source, out_dir, name):
    sub_dir = os.path.join(out_dir, "graphs", "spanwise_pressure")
    os.makedirs(sub_dir, exist_ok=True)
    z_lo, z_hi = WASH_BOUNDS["z"]
    x0, x1 = CAR_BOUNDS["x"]
    n_steps = int(round((z_hi - z_lo) / SLICE_STEP))

    for i in range(n_steps + 1):
        z = z_lo + i * SLICE_STEP
        pol = PlotOverLine(Input=source)
        pol.Point1 = [x0, 0.05, z]
        pol.Point2 = [x1, 0.05, z]
        pol.UpdatePipeline()
        tag = f"z{z * 1000:+04.0f}mm".replace("+", "p").replace("-", "m")
        SaveData(os.path.join(sub_dir, f"{tag}.csv"),
                  proxy=pol, WriteTimeSteps=False)
        Delete(pol)
    print(f"  [spanwise] wrote {n_steps + 1} CSVs to {sub_dir}")


# ============================================================
# 13: SURFACE LIC
# ============================================================
def save_surface_lic(source, view, cam_dict, filename, out_dir, apply_cam_func=None):
    sub_dir = os.path.join(out_dir, "surface_lic")
    os.makedirs(sub_dir, exist_ok=True)

    disp = Show(source, view)
    disp.SetRepresentationType('Surface LIC')
    ColorBy(disp, ('POINTS', FIELDS["total_pressure"]))
    ctf = apply_color_preset(view, FIELDS["total_pressure"])
    disp.SetScalarBarVisibility(view, True)

    if apply_cam_func:
        apply_cam_func(view, cam_dict)
    else:
        apply_perspective_camera(view, cam_dict)

    Render()
    SaveScreenshot(os.path.join(sub_dir, filename), view, ImageResolution=IMG_SIZE)
    GetScalarBar(ctf, view).Visibility = 0
    Hide(source, view)


# ============================================================
# 14: Q-CRITERION ISOSURFACES
# ============================================================
def save_isosurface(fluid_source, car_source, view, cam_dict, filename, out_dir, apply_cam_func=None):
    sub_dir = os.path.join(out_dir, "isosurfaces")
    os.makedirs(sub_dir, exist_ok=True)

    contour = Contour(Input=fluid_source)
    contour.ContourBy = ['POINTS', ISOSURFACE_FIELD]
    contour.Isosurfaces = [ISOSURFACE_VALUE]
    contour.UpdatePipeline()

    car_disp = Show(car_source, view)
    car_disp.Representation = 'Surface'
    ColorBy(car_disp, None)
    car_disp.AmbientColor = [0.6, 0.6, 0.6]
    car_disp.DiffuseColor = [0.6, 0.6, 0.6]

    disp = Show(contour, view)
    ColorBy(disp, ('POINTS', ISOSURFACE_COLOR_FIELD))
    ctf = apply_color_preset(view, ISOSURFACE_COLOR_FIELD)
    disp.SetScalarBarVisibility(view, True)

    if apply_cam_func:
        apply_cam_func(view, cam_dict)
    else:
        apply_perspective_camera(view, cam_dict)

    Render()
    SaveScreenshot(os.path.join(sub_dir, filename), view, ImageResolution=IMG_SIZE)
    GetScalarBar(ctf, view).Visibility = 0
    Delete(contour)
    Hide(car_source, view)


# ============================================================
# STEP DEFINITIONS - which pipeline branches each step needs
# ============================================================
STEP_INFO = {
    "contours":    {"car": True,  "fluid": False, "desc": "Car surface pressure contours (iso + underside-iso)"},
    "centerline":  {"car": False, "fluid": True,  "desc": "Centerline pressure CSV (front to rear)"},
    "streamlines": {"car": True,  "fluid": True,  "desc": "Streamlines w/ car body (iso + underside-iso)"},
    "movies":      {"car": False, "fluid": True,  "desc": "Sweeping slice movies (.mp4, native animation)"},
    "slices":      {"car": False, "fluid": True,  "desc": "50mm static slice decks (.png)"},
    "spanwise":    {"car": False, "fluid": True,  "desc": "Spanwise pressure CSVs (every 50mm across width)"},
    "lic":         {"car": True,  "fluid": False, "desc": "Surface LIC colored by total pressure"},
    "isosurfaces": {"car": True,  "fluid": True,  "desc": "Q-criterion vortex isosurfaces"},
}
ALL_STEPS = list(STEP_INFO.keys())


# ============================================================
# MAIN PER-CASE PIPELINE
# ============================================================
def process_case(case, steps, field_keys, view_names):
    os.makedirs(case["out"], exist_ok=True)
    name = case["name"]

    need_car = any(STEP_INFO[s]["car"] for s in steps)
    need_fluid = any(STEP_INFO[s]["fluid"] for s in steps)

    sources = build_pipeline(case["file"], need_car=need_car, need_fluid=need_fluid)
    car_source = sources["car"]
    fluid_source = sources["fluid"]

    view = GetActiveViewOrCreate('RenderView')
    view.ViewSize = IMG_SIZE  # needed for correct legend font scaling

    if "contours" in steps:
        print("[step] contours")
        apply_perspective_camera(view, CAM_ISO)
        save_contour(car_source, view, FIELDS["static_pressure"], f"{name}_iso_pressure.png", case["out"])
        save_contour(car_source, view, FIELDS["total_pressure"], f"{name}_iso_total_pressure.png", case["out"])
        apply_perspective_camera(view, CAM_UNDERSIDE_ISO)
        save_contour(car_source, view, FIELDS["static_pressure"], f"{name}_under_pressure.png", case["out"])
        save_contour(car_source, view, FIELDS["total_pressure"], f"{name}_under_total_pressure.png", case["out"])

    if "centerline" in steps:
        print("[step] centerline")
        save_centerline_graph(fluid_source, case["out"], name)

    if "streamlines" in steps:
        print("[step] streamlines")
        apply_perspective_camera(view, CAM_ISO)
        save_streamlines(fluid_source, car_source, view, FIELDS["static_pressure"],
                          f"{name}_iso_streamlines_pressure.png", case["out"])
        save_streamlines(fluid_source, car_source, view, FIELDS["velocity"],
                          f"{name}_iso_streamlines_velocity.png", case["out"])
        apply_perspective_camera(view, CAM_UNDERSIDE_ISO)
        save_streamlines(fluid_source, car_source, view, FIELDS["static_pressure"],
                          f"{name}_under_streamlines_pressure.png", case["out"])
        save_streamlines(fluid_source, car_source, view, FIELDS["velocity"],
                          f"{name}_under_streamlines_velocity.png", case["out"])

    if "movies" in steps:
        print("[step] movies")
        for field_key in field_keys:
            for view_name in view_names:
                lo, hi = MOVIE_SWEEP_RANGES[view_name]
                make_sweep_movie(fluid_source, view_name, view, FIELDS[field_key], lo, hi,
                                  case["out"], name, field_key)

    if "slices" in steps:
        print("[step] slices")
        for field_key in field_keys:
            for view_name in view_names:
                make_slice_deck(fluid_source, view_name, view, FIELDS[field_key], WASH_BOUNDS,
                                 case["out"], name, field_key)

    if "spanwise" in steps:
        print("[step] spanwise")
        make_spanwise_pressure_graphs(fluid_source, case["out"], name)

    if "lic" in steps:
        print("[step] lic")
        apply_perspective_camera(view, CAM_ISO)
        save_surface_lic(car_source, view, CAM_ISO, f"{name}_iso_surface_lic.png", case["out"])
        save_surface_lic(car_source, view, CAM_UNDERSIDE_ISO, f"{name}_under_surface_lic.png", case["out"])

    if "isosurfaces" in steps:
        print("[step] isosurfaces")
        save_isosurface(fluid_source, car_source, view, CAM_ISO, f"{name}_iso_qcriterion.png", case["out"])
        save_isosurface(fluid_source, car_source, view, CAM_UNDERSIDE_ISO, f"{name}_under_qcriterion.png", case["out"])

    if car_source is not None:
        Delete(car_source)
    if fluid_source is not None:
        Delete(fluid_source)
    print(f"Done: {name}")


# ============================================================
# CLI
# ============================================================
def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="ParaView batch post-processing for FSAE CFD results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  pvpython batch_postprocess.py --all\n"
               "  pvpython batch_postprocess.py --contours --streamlines\n"
               "  pvpython batch_postprocess.py --movies --views side --fields static_pressure\n"
               "  pvpython batch_postprocess.py --list\n",
    )
    parser.add_argument("--all", action="store_true", help="Run every step")
    parser.add_argument("--list", action="store_true", help="List available steps and exit")

    for step, info in STEP_INFO.items():
        parser.add_argument(f"--{step}", action="store_true", help=info["desc"])

    parser.add_argument("--fields", nargs="+", choices=ALL_FIELD_KEYS, default=ALL_FIELD_KEYS,
                        help="Limit movies/slices to these fields (default: all)")
    parser.add_argument("--views", nargs="+", choices=ALL_VIEW_NAMES, default=ALL_VIEW_NAMES,
                        help="Limit movies/slices to these views (default: all)")
    parser.add_argument("--cases", nargs="+", default=None,
                        help="Limit to these case names (default: all in CASES)")

    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.list:
        print("Available steps:")
        for step, info in STEP_INFO.items():
            branches = []
            if info["car"]:
                branches.append("car")
            if info["fluid"]:
                branches.append("fluid")
            print(f"  --{step:<14} {info['desc']}  [needs: {', '.join(branches)}]")
        print("\nFields:", ", ".join(ALL_FIELD_KEYS))
        print("Views: ", ", ".join(ALL_VIEW_NAMES))
        sys.exit(0)

    if args.all:
        steps = list(ALL_STEPS)
    else:
        steps = [s for s in ALL_STEPS if getattr(args, s)]

    if not steps:
        print("No steps selected. Use --all, one or more step flags, or --list to see options.")
        sys.exit(1)

    cases = CASES
    if args.cases:
        cases = [c for c in CASES if c["name"] in args.cases]
        if not cases:
            print(f"No matching cases for: {args.cases}")
            sys.exit(1)

    print(f"Steps:  {', '.join(steps)}")
    print(f"Fields: {', '.join(args.fields)}")
    print(f"Views:  {', '.join(args.views)}")
    print(f"Cases:  {', '.join(c['name'] for c in cases)}")
    print()

    for case in cases:
        process_case(case, steps, args.fields, args.views)