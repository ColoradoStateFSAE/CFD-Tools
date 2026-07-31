# batch_postprocess.py
# Run with: pvpython batch_postprocess.py   (test on ONE case first)
# Headless on HPC later with: pvbatch --mesa batch_postprocess.py
#
# Covers:
#   1-9.  Original standard set (iso/underside-iso contours, streamlines, centerline graph)
#   10.   Sweeping slice movies (velocity/static/total pressure x top/side/front)
#   11.   50mm slice decks (same fields x views)
#   12.   Spanwise static pressure line graphs (tip-to-tail, every 50mm across car width)
#   13.   Surface LIC streamlines (flow-vis paint comparison)

from paraview.simple import *
import os

paraview.simple._DisableFirstRenderCameraReset()

# ============================================================
# CASES - populate one entry per Fluent run
# ============================================================
CASES = [
    {"name": "case_001", "file": r"C:\path\to\case_001\FLTG-1-00001.encas", "out": r"C:\path\to\case_001\images"},
    # add more cases here
]

# ============================================================
# GEOMETRY - block names to keep (car surfaces only, confirmed from your ExtractBlock)
# ============================================================
CAR_BLOCKS = [
    '/vtkMultiBlockDataSet/undertray',
    '/vtkMultiBlockDataSet/rearwing',
    '/vtkMultiBlockDataSet/frontwing',
    '/vtkMultiBlockDataSet/chassis',
    '/vtkMultiBlockDataSet/front_sus',
    '/vtkMultiBlockDataSet/rear_sus',
    '/vtkMultiBlockDataSet/rw',
    '/vtkMultiBlockDataSet/fw',
    '/vtkMultiBlockDataSet/rwb',
    '/vtkMultiBlockDataSet/fwb',
]
# NOTE: if ExtractBlock().Selectors = CAR_BLOCKS errors out, run Start Trace over just
# building ExtractBlock1 in the GUI and send the exact call back, syntax varies by version.

# ============================================================
# BOUNDS
# ============================================================
CAR_BOUNDS = {
    "x": (-1.8415, 1.23425),   # inlet(-) to outlet(+), streamwise
    "y": (0.0, 1.32862),        # ground to roof
    "z": (-0.70231, 0.70231),   # full width, symmetric after reflect
}

# extended for wake/wash resolution: +3m downstream, +2m up, Z unchanged
WASH_BOUNDS = {
    "x": (CAR_BOUNDS["x"][0], CAR_BOUNDS["x"][1] + 3.0),
    "y": (CAR_BOUNDS["y"][0], CAR_BOUNDS["y"][1] + 2.0),
    "z": CAR_BOUNDS["z"],
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
    # tune these to your actual data ranges so color scales are fixed across cases
    "Velocity_Magnitude": [0, 30],
    "Static_Pressure": [-1500, 500],
    "Total_Pressure": [-1000, 1000],
}

IMG_SIZE = [1920, 1080]
N_SWEEP_FRAMES = 30
SLICE_STEP = 0.05  # 50mm

# ============================================================
# FIXED CAMERAS - traced directly from your GUI session
# ============================================================
CAM_ISO = {
    "position": [-5.168290238998194, 3.1907989459561232, 3.859907198505371],
    "focal_point": [-0.33957097312688794, 0.6451492970271008, 0.12655292696877032],
    "view_up": [0.29551835849896174, 0.922845130744072, -0.24703393380674607],
    "parallel_scale": 1.7116295794848735,
}
CAM_UNDERSIDE_ISO = {
    "position": [-2.78343145444443, -5.521651747384183, 2.809984883765469],
    "focal_point": [-0.3477141510178081, 0.11215029862658193, 0.3478005436634496],
    "view_up": [-0.6618338173671472, 0.521496331899044, 0.5385327975203293],
    "parallel_scale": 1.7116295794848735,
}


def apply_perspective_camera(view, cam):
    view.CameraParallelProjection = 0
    view.CameraPosition = cam["position"]
    view.CameraFocalPoint = cam["focal_point"]
    view.CameraViewUp = cam["view_up"]


# ============================================================
# COMPUTED ORTHOGRAPHIC CAMERAS (front / side / top) - built from bounds
# NOTE: up-vectors and which side is "side view" are best-guess defaults.
# Flip signs below if the orientation comes out wrong.
# ============================================================
def setup_front_view(view, bounds, margin=1.1):
    cx = sum(bounds["x"]) / 2
    cy = sum(bounds["y"]) / 2
    cz = sum(bounds["z"]) / 2
    y_range = bounds["y"][1] - bounds["y"][0]
    z_range = bounds["z"][1] - bounds["z"][0]
    scale = max(y_range, z_range) / 2 * margin
    dist = max(y_range, z_range, bounds["x"][1] - bounds["x"][0]) * 2 + 5
    view.CameraParallelProjection = 1
    view.CameraPosition = [bounds["x"][0] - dist, cy, cz]
    view.CameraFocalPoint = [cx, cy, cz]
    view.CameraViewUp = [0, 1, 0]
    view.CameraParallelScale = scale


def setup_side_view(view, bounds, margin=1.1):
    cx = sum(bounds["x"]) / 2
    cy = sum(bounds["y"]) / 2
    cz = sum(bounds["z"]) / 2
    x_range = bounds["x"][1] - bounds["x"][0]
    y_range = bounds["y"][1] - bounds["y"][0]
    scale = max(x_range, y_range) / 2 * margin
    dist = max(x_range, y_range, bounds["z"][1] - bounds["z"][0]) * 2 + 5
    view.CameraParallelProjection = 1
    view.CameraPosition = [cx, cy, bounds["z"][1] + dist]
    view.CameraFocalPoint = [cx, cy, cz]
    view.CameraViewUp = [0, 1, 0]
    view.CameraParallelScale = scale


def setup_top_view(view, bounds, margin=1.1):
    cx = sum(bounds["x"]) / 2
    cy = sum(bounds["y"]) / 2
    cz = sum(bounds["z"]) / 2
    x_range = bounds["x"][1] - bounds["x"][0]
    z_range = bounds["z"][1] - bounds["z"][0]
    scale = max(x_range, z_range) / 2 * margin
    dist = max(x_range, z_range, bounds["y"][1] - bounds["y"][0]) * 2 + 5
    view.CameraParallelProjection = 1
    view.CameraPosition = [cx, bounds["y"][1] + dist, cz]
    view.CameraFocalPoint = [cx, cy, cz]
    view.CameraViewUp = [-1, 0, 0]
    view.CameraParallelScale = scale


VIEW_SETUP = {
    "front": setup_front_view,
    "side": setup_side_view,
    "top": setup_top_view,
}
AXIS_FOR_VIEW = {"front": "x", "side": "z", "top": "y"}  # sweep/slice normal per view
NORMAL_VEC = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


# ============================================================
# PIPELINE BUILD (per case)
# ============================================================
def build_pipeline(case_file):
    reader = OpenDataFile(case_file)
    reader.UpdatePipeline()

    extract = ExtractBlock(Input=reader)
    extract.Selectors = CAR_BLOCKS
    extract.UpdatePipeline()

    reflect = AxisAlignedReflect(Input=extract)
    reflect.Plane = 'Z Min'
    reflect.ReflectAllInputArrays = 1
    reflect.UpdatePipeline()

    return reflect


# ============================================================
# 1-4: CONTOURS (iso + underside-iso, pressure + velocity)
# ============================================================
def save_contour(source, view, field, filename, out_dir):
    disp = Show(source, view)
    ColorBy(disp, ('POINTS', field))
    ctf = GetColorTransferFunction(field)
    ctf.RescaleTransferFunction(*FIELD_RANGES[field])
    disp.SetScalarBarVisibility(view, True)
    Render()
    SaveScreenshot(os.path.join(out_dir, filename), view, ImageResolution=IMG_SIZE)
    Hide(source, view)


# ============================================================
# 6-9: STREAMLINES (iso + underside-iso, pressure + velocity)
# ============================================================
def save_streamlines(source, view, field, seed_center, seed_radius, filename, out_dir):
    tracer = StreamTracer(Input=source, SeedType='Point Cloud')
    tracer.SeedType.Center = seed_center
    tracer.SeedType.Radius = seed_radius
    tracer.SeedType.NumberOfPoints = 200
    tracer.Vectors = ['POINTS', 'Velocity']
    tracer.MaximumStreamlineLength = 8

    disp = Show(tracer, view)
    ColorBy(disp, ('POINTS', field))
    ctf = GetColorTransferFunction(field)
    ctf.RescaleTransferFunction(*FIELD_RANGES[field])
    disp.SetScalarBarVisibility(view, True)
    Render()
    SaveScreenshot(os.path.join(out_dir, filename), view, ImageResolution=IMG_SIZE)
    Delete(tracer)


# ============================================================
# 5: CENTERLINE PRESSURE GRAPH (front to rear, using Total_Pressure directly, no CpT calc)
# ============================================================
def save_centerline_graph(source, out_dir, name):
    x0, x1 = CAR_BOUNDS["x"]
    pol = PlotOverLine(Input=source)
    pol.Point1 = [x0, 0.05, 0.0]
    pol.Point2 = [x1, 0.05, 0.0]
    pol.UpdatePipeline()
    SaveData(os.path.join(out_dir, f"{name}_centerline_pressure.csv"),
             proxy=pol, WriteTimeSteps=False)
    Delete(pol)


# ============================================================
# 10: SWEEPING SLICE MOVIES (frame sequence, combine with ffmpeg after)
# ============================================================
def make_sweep_movie(source, view_name, view, field, bounds, out_dir, name):
    axis = AXIS_FOR_VIEW[view_name]
    lo, hi = bounds[axis]

    slice1 = Slice(Input=source)
    slice1.SliceType = 'Plane'
    slice1.SliceType.Normal = NORMAL_VEC[axis]

    disp = Show(slice1, view)
    ColorBy(disp, ('POINTS', field))
    ctf = GetColorTransferFunction(field)
    ctf.RescaleTransferFunction(*FIELD_RANGES[field])
    disp.SetScalarBarVisibility(view, True)

    VIEW_SETUP[view_name](view, bounds)

    for i in range(N_SWEEP_FRAMES):
        t = i / (N_SWEEP_FRAMES - 1)
        pos = lo + t * (hi - lo)
        origin = [0.0, 0.0, 0.0]
        origin[AXIS_INDEX[axis]] = pos
        slice1.SliceType.Origin = origin
        Render()
        SaveScreenshot(os.path.join(out_dir, f"{name}_{view_name}_frame{i:03d}.png"),
                        view, ImageResolution=IMG_SIZE)

    Delete(slice1)
    # After running, stitch frames with (outside ParaView):
    #   ffmpeg -framerate 10 -i {name}_{view}_frame%03d.png -pix_fmt yuv420p {name}_{view}.mp4


# ============================================================
# 11: 50MM SLICE DECKS (static images, same orientations as movies)
# ============================================================
def make_slice_deck(source, view_name, view, field, bounds, out_dir, name):
    axis = AXIS_FOR_VIEW[view_name]
    lo, hi = bounds[axis]
    n_steps = int(round((hi - lo) / SLICE_STEP))

    slice1 = Slice(Input=source)
    slice1.SliceType = 'Plane'
    slice1.SliceType.Normal = NORMAL_VEC[axis]

    disp = Show(slice1, view)
    ColorBy(disp, ('POINTS', field))
    ctf = GetColorTransferFunction(field)
    ctf.RescaleTransferFunction(*FIELD_RANGES[field])
    disp.SetScalarBarVisibility(view, True)

    VIEW_SETUP[view_name](view, bounds)

    for i in range(n_steps + 1):
        pos = lo + i * SLICE_STEP
        origin = [0.0, 0.0, 0.0]
        origin[AXIS_INDEX[axis]] = pos
        slice1.SliceType.Origin = origin
        Render()
        tag = f"{axis}{pos * 1000:+.0f}mm".replace("+", "p").replace("-", "m")
        SaveScreenshot(os.path.join(out_dir, f"{name}_{view_name}_{tag}.png"),
                        view, ImageResolution=IMG_SIZE)

    Delete(slice1)


# ============================================================
# 12: SPANWISE STATIC PRESSURE GRAPHS (tip-to-tail line, every 50mm across car width)
# ============================================================
def make_spanwise_pressure_graphs(source, out_dir, name):
    z_lo, z_hi = CAR_BOUNDS["z"]
    x0, x1 = CAR_BOUNDS["x"]
    n_steps = int(round((z_hi - z_lo) / SLICE_STEP))

    for i in range(n_steps + 1):
        z = z_lo + i * SLICE_STEP
        pol = PlotOverLine(Input=source)
        pol.Point1 = [x0, 0.05, z]
        pol.Point2 = [x1, 0.05, z]
        pol.UpdatePipeline()
        tag = f"z{z * 1000:+.0f}mm".replace("+", "p").replace("-", "m")
        SaveData(os.path.join(out_dir, f"{name}_spanwise_pressure_{tag}.csv"),
                  proxy=pol, WriteTimeSteps=False)
        Delete(pol)


# ============================================================
# 13: SURFACE LIC STREAMLINES (flow-vis paint comparison)
# ============================================================
def save_surface_lic(source, view, cam_dict, filename, out_dir, apply_cam_func=None):
    try:
        from paraview import simple
        simple.LoadDistributedPlugin('SurfaceLIC', ns=globals())
    except Exception as e:
        print(f"SurfaceLIC plugin load warning (may already be loaded): {e}")

    disp = Show(source, view)
    disp.SetRepresentationType('Surface LIC')
    ColorBy(disp, ('POINTS', 'Skin_Friction_Coefficient'))
    disp.SetScalarBarVisibility(view, True)

    if apply_cam_func:
        apply_cam_func(view, cam_dict)
    else:
        apply_perspective_camera(view, cam_dict)

    Render()
    SaveScreenshot(os.path.join(out_dir, filename), view, ImageResolution=IMG_SIZE)
    Hide(source, view)


# ============================================================
# MAIN PER-CASE PIPELINE
# ============================================================
def process_case(case):
    os.makedirs(case["out"], exist_ok=True)
    source = build_pipeline(case["file"])
    name = case["name"]

    view = GetActiveViewOrCreate('RenderView')
    view.ViewSize = IMG_SIZE

    # --- 1-4: contours ---
    apply_perspective_camera(view, CAM_ISO)
    save_contour(source, view, FIELDS["static_pressure"], f"{name}_iso_pressure.png", case["out"])
    save_contour(source, view, FIELDS["velocity"], f"{name}_iso_velocity.png", case["out"])

    apply_perspective_camera(view, CAM_UNDERSIDE_ISO)
    save_contour(source, view, FIELDS["static_pressure"], f"{name}_under_pressure.png", case["out"])
    save_contour(source, view, FIELDS["velocity"], f"{name}_under_velocity.png", case["out"])

    # --- 5: centerline graph ---
    save_centerline_graph(source, case["out"], name)

    # --- 6-9: streamlines ---
    seed_center = [CAR_BOUNDS["x"][0] - 0.5, 0.5, 0.0]
    seed_radius = 0.6

    apply_perspective_camera(view, CAM_ISO)
    save_streamlines(source, view, FIELDS["static_pressure"], seed_center, seed_radius,
                      f"{name}_iso_streamlines_pressure.png", case["out"])
    save_streamlines(source, view, FIELDS["velocity"], seed_center, seed_radius,
                      f"{name}_iso_streamlines_velocity.png", case["out"])

    apply_perspective_camera(view, CAM_UNDERSIDE_ISO)
    save_streamlines(source, view, FIELDS["static_pressure"], seed_center, seed_radius,
                      f"{name}_under_streamlines_pressure.png", case["out"])
    save_streamlines(source, view, FIELDS["velocity"], seed_center, seed_radius,
                      f"{name}_under_streamlines_velocity.png", case["out"])

    # --- 10: sweeping movies (velocity, static pressure, total pressure x top/side/front) ---
    for view_name in ["top", "side", "front"]:
        for field_key in ["velocity", "static_pressure", "total_pressure"]:
            make_sweep_movie(source, view_name, view, FIELDS[field_key], WASH_BOUNDS, case["out"], name)

    # --- 11: 50mm slice decks ---
    for view_name in ["top", "side", "front"]:
        for field_key in ["velocity", "static_pressure", "total_pressure"]:
            make_slice_deck(source, view_name, view, FIELDS[field_key], WASH_BOUNDS, case["out"], name)

    # --- 12: spanwise pressure graphs ---
    make_spanwise_pressure_graphs(source, case["out"], name)

    # --- 13: surface LIC streamlines ---
    apply_perspective_camera(view, CAM_ISO)
    save_surface_lic(source, view, CAM_ISO, f"{name}_iso_surface_lic.png", case["out"])
    save_surface_lic(source, view, CAM_UNDERSIDE_ISO, f"{name}_under_surface_lic.png", case["out"])

    Delete(source)
    print(f"Done: {name}")


if __name__ == "__main__":
    for case in CASES:
        process_case(case)
