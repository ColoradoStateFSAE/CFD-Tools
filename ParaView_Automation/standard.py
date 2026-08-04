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
import subprocess

paraview.simple._DisableFirstRenderCameraReset()

# ============================================================
# CASES - populate one entry per Fluent run
# ============================================================
CASES = [
    {"name": "case_001", "file": r"C:\Users\HayesDodson\Downloads\data\FLTG-Setup-Output.encas", "out": r"C:\Users\HayesDodson\Downloads\test"},
    # add more cases here
]

# ============================================================
# GEOMETRY - block names to keep (car surfaces only, confirmed from your ExtractBlock)
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
# fluid/enclosure volume block - needed for slices, sweeps, and streamlines
# (velocity/pressure fields live in the fluid domain, not on the car surface)
FLUID_BLOCK = ['/Root/enclosureenclosure11']
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

# explicit sweep/slice range for movies and slice decks (fluid domain, outside-to-center on Z)
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
    # tune these to your actual data ranges so color scales are fixed across cases
    "Velocity_Magnitude": [0, 30],
    "Static_Pressure": [-750, 250],
    "Total_Pressure": [-750, 300],
}
COLOR_PRESET = 'Rainbow Uniform'
ALL_COLOR_FIELDS = ["Velocity_Magnitude", "Static_Pressure", "Total_Pressure", "Skin_Friction_Coefficient"]

# ============================================================
# ISOSURFACES - Q-criterion vortex structures, a standard way to spot
# induced-drag sources (wingtip/diffuser vortices, separation) at a glance.
# ISOSURFACE_VALUE is data-dependent - 1.0 is a common starting point for the
# normalized field, but check the first result and adjust if it looks empty
# or overwhelming.
# ============================================================
ISOSURFACE_FIELD = 'Q_Criterion_Normalized'
ISOSURFACE_VALUE = 1.0
ISOSURFACE_COLOR_FIELD = 'Velocity_Magnitude'

IMG_SIZE = [3840, 2160]  # true 4K. PNG is lossless regardless of size, this just gives more pixels to work with
FRONT_IMG_SIZE = IMG_SIZE  # back to horizontal, same resolution as the other views
N_SWEEP_FRAMES = 30
SLICE_STEP = 0.05  # 50mm

# ============================================================
# MOVIE STITCHING - automatically combine each sweep's PNG frames into an .mp4
# Requires ffmpeg on PATH (https://ffmpeg.org/download.html). If it's not found,
# frames still get saved, just no .mp4 - stitch manually with the printed command.
# ============================================================
STITCH_MOVIES = True
FFMPEG_PATH = "ffmpeg"  # set to a full path like r"C:\ffmpeg\bin\ffmpeg.exe" if not on PATH
MOVIE_FRAMERATE = 10


def stitch_frames_to_mp4(frame_dir, case_out_dir, out_name):
    mp4_dir = os.path.join(case_out_dir, "movies_mp4")
    os.makedirs(mp4_dir, exist_ok=True)
    out_path = os.path.join(mp4_dir, f"{out_name}.mp4")
    frame_pattern = os.path.join(frame_dir, "frame_%03d.png")
    cmd = [FFMPEG_PATH, "-y", "-framerate", str(MOVIE_FRAMERATE), "-i", frame_pattern,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  [movie] wrote {out_path}")
    except FileNotFoundError:
        print(f"  [movie] ffmpeg not found on PATH - skipped stitching {out_name}. "
              f"Install ffmpeg and add it to PATH, or set FFMPEG_PATH at the top of this script. "
              f"Manual command: ffmpeg -framerate {MOVIE_FRAMERATE} -i \"{frame_pattern}\" "
              f"-c:v libx264 -pix_fmt yuv420p \"{out_path}\"")
    except subprocess.CalledProcessError as e:
        stderr_tail = e.stderr.decode(errors="ignore")[-500:] if e.stderr else "(no output)"
        print(f"  [movie] ffmpeg failed for {out_name}: {stderr_tail}")

# ============================================================
# STREAMLINE SEEDING - two regions: general upstream cloud (denser now) plus a
# dedicated low, tight seed right ahead of the nose to guarantee underfloor coverage
# ============================================================
STREAMLINE_SEED_MAIN = {
    "center": [CAR_BOUNDS["x"][0] - 0.5, 0.55, 0.0],
    "radius": 0.65,
    "n_points": 600,
}
STREAMLINE_SEED_UNDERFLOOR = {
    "center": [CAR_BOUNDS["x"][0] - 0.25, 0.06, 0.0],  # low, close to ground, just upstream of nose
    "radius": 0.55,  # spans roughly the car's half-width at very low height
    "n_points": 500,
}

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
# FIXED CAMERAS - front, side, top
# Sourced directly from the .pvcc camera state files (authoritative, exact).
# All three use perspective projection (CameraParallelProjection=0 in every
# .pvcc file) - not orthographic - so parallel_scale isn't used here.
# ============================================================
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

VIEW_SETUP = {
    "front": lambda view, bounds: apply_perspective_camera(view, CAM_FRONT),
    "side": lambda view, bounds: apply_perspective_camera(view, CAM_SIDE),
    "top": lambda view, bounds: apply_perspective_camera(view, CAM_TOP),
}
AXIS_FOR_VIEW = {"front": "x", "side": "z", "top": "y"}  # sweep/slice normal per view
NORMAL_VEC = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


# ============================================================
# PIPELINE BUILD (per case)
# Returns both branches: car (surface geometry, for contours/LIC) and
# fluid (volume domain, for slices/sweeps/streamlines/graphs)
# ============================================================
REFLECT_FLUID_BLOCK = False  # fluid domain stays half-width (symmetric flow, only reflect the car block for visuals)


def _make_reflect(input_proxy):
    reflect = AxisAlignedReflect(Input=input_proxy)
    reflect.ReflectionPlane.Set(
        Origin=[0.0, 0.0, 0.0],
        Normal=[0.0, 0.0, 1.0],
    )
    reflect.ReflectAllInputArrays = 1
    reflect.UpdatePipeline()
    return reflect


def build_pipeline(case_file):
    reader = OpenDataFile(case_file)
    reader.UpdatePipeline()

    # --- Car surface branch (contours, surface LIC) ---
    car_extract = ExtractBlock(Input=reader)
    car_extract.Selectors = CAR_BLOCKS
    car_extract.UpdatePipeline()

    n_cells = car_extract.GetDataInformation().GetNumberOfCells()
    print(f"  [check] Car ExtractBlock cell count: {n_cells}")
    if n_cells == 0:
        raise RuntimeError(
            "Car ExtractBlock produced 0 cells. CAR_BLOCKS selector strings don't match "
            "this file's hierarchy. Run the diagnostic hierarchy dump before continuing."
        )

    car_reflect = _make_reflect(car_extract)
    print(f"  [check] Car reflect cell count: {car_reflect.GetDataInformation().GetNumberOfCells()}")

    # --- Fluid volume branch (slices, sweeps, streamlines, line graphs) ---
    fluid_extract = ExtractBlock(Input=reader)
    fluid_extract.Selectors = FLUID_BLOCK
    fluid_extract.UpdatePipeline()

    n_fluid_cells = fluid_extract.GetDataInformation().GetNumberOfCells()
    print(f"  [check] Fluid ExtractBlock cell count: {n_fluid_cells}")
    if n_fluid_cells == 0:
        raise RuntimeError(
            "Fluid ExtractBlock produced 0 cells. FLUID_BLOCK selector doesn't match "
            "this file's hierarchy. Check the exact enclosure block name."
        )

    if REFLECT_FLUID_BLOCK:
        fluid_source = _make_reflect(fluid_extract)
        print(f"  [check] Fluid reflect cell count: {fluid_source.GetDataInformation().GetNumberOfCells()}")
    else:
        fluid_source = fluid_extract

    return {"car": car_reflect, "fluid": fluid_source}


# ============================================================
# COLOR PRESET HELPER - applied everywhere a field is color-mapped
# ============================================================
def hide_all_known_scalar_bars(view):
    """Force-clear every legend we might have created, regardless of which
    field owns it. Called before showing any new legend so stale ones from
    a previous field can never remain stacked on screen."""
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
    sb.Position = [0.90, 0.35]   # right side, vertically centered
    sb.ScalarBarLength = 0.30    # length of the bar (normalized viewport units)
    return ctf


# ============================================================
# 1-4: CONTOURS (iso + underside-iso, PRESSURE ONLY)
# velocity contour on the car surface was removed: due to the no-slip
# condition, surface velocity is always ~0, so it isn't a meaningful contour.
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
# 6-9: STREAMLINES (iso + underside-iso, pressure + velocity)
# Two seed sources combined: general upstream cloud + dedicated low seed
# to guarantee dense coverage under the undertray.
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

    # show the car body as plain solid geometry for context (not colored by any field)
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
# 5: CENTERLINE PRESSURE GRAPH (front to rear, using Total_Pressure directly, no CpT calc)
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
# 10: SWEEPING SLICE MOVIES (frame sequence, combine with ffmpeg after)
# ============================================================
def make_sweep_movie(source, view_name, view, field, bounds, out_dir, name, field_key):
    sub_dir = os.path.join(out_dir, "movies", view_name, field_key)
    os.makedirs(sub_dir, exist_ok=True)
    axis = AXIS_FOR_VIEW[view_name]
    lo, hi = bounds[axis]
    img_size = FRONT_IMG_SIZE if view_name == "front" else IMG_SIZE
    view.ViewSize = img_size

    slice1 = Slice(Input=source)
    slice1.SliceType.Normal = NORMAL_VEC[axis]

    disp = Show(slice1, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color_preset(view, field)
    disp.SetScalarBarVisibility(view, True)

    VIEW_SETUP[view_name](view, bounds)

    for i in range(N_SWEEP_FRAMES):
        t = i / (N_SWEEP_FRAMES - 1)
        pos = lo + t * (hi - lo)
        origin = [0.0, 0.0, 0.0]
        origin[AXIS_INDEX[axis]] = pos
        slice1.SliceType.Origin = origin
        Render()
        SaveScreenshot(os.path.join(sub_dir, f"frame_{i:03d}.png"),
                        view, ImageResolution=img_size)

    GetScalarBar(ctf, view).Visibility = 0
    Delete(slice1)
    view.ViewSize = IMG_SIZE  # restore default for whatever runs next

    if STITCH_MOVIES:
        stitch_frames_to_mp4(sub_dir, out_dir, f"{name}_{view_name}_{field_key}")


# ============================================================
# 11: 50MM SLICE DECKS (static images, same orientations as movies)
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

    VIEW_SETUP[view_name](view, bounds)

    for i in range(n_steps + 1):
        pos = lo + i * SLICE_STEP
        origin = [0.0, 0.0, 0.0]
        origin[AXIS_INDEX[axis]] = pos
        slice1.SliceType.Origin = origin
        Render()
        tag = f"{axis}{pos * 1000:+04.0f}mm".replace("+", "p").replace("-", "m")
        SaveScreenshot(os.path.join(sub_dir, f"{tag}.png"),
                        view, ImageResolution=img_size)

    GetScalarBar(ctf, view).Visibility = 0
    Delete(slice1)
    view.ViewSize = IMG_SIZE  # restore default for whatever runs next


# ============================================================
# 12: SPANWISE STATIC PRESSURE GRAPHS (tip-to-tail line, every 50mm across car width)
# ============================================================
def make_spanwise_pressure_graphs(source, out_dir, name):
    sub_dir = os.path.join(out_dir, "graphs", "spanwise_pressure")
    os.makedirs(sub_dir, exist_ok=True)
    z_lo, z_hi = WASH_BOUNDS["z"]  # outside (z_hi) to center (z_lo=0), symmetric flow
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


# ============================================================
# 14: Q-CRITERION ISOSURFACES (iso + underside-iso) - vortex structures,
# a standard way to visually locate induced-drag sources
# ============================================================
def save_isosurface(fluid_source, car_source, view, cam_dict, filename, out_dir, apply_cam_func=None):
    sub_dir = os.path.join(out_dir, "isosurfaces")
    os.makedirs(sub_dir, exist_ok=True)

    contour = Contour(Input=fluid_source)
    contour.ContourBy = ['POINTS', ISOSURFACE_FIELD]
    contour.Isosurfaces = [ISOSURFACE_VALUE]
    contour.UpdatePipeline()

    # show the car body as plain solid geometry for context
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
# 13: SURFACE LIC STREAMLINES (flow-vis paint comparison)
# ============================================================
def save_surface_lic(source, view, cam_dict, filename, out_dir, apply_cam_func=None):
    sub_dir = os.path.join(out_dir, "surface_lic")
    os.makedirs(sub_dir, exist_ok=True)
    # Surface LIC is built-in and renders fine without an explicit plugin load in this
    # ParaView version - the load call previously just produced a harmless but noisy warning.

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
# MAIN PER-CASE PIPELINE
# ============================================================
def process_case(case):
    os.makedirs(case["out"], exist_ok=True)
    sources = build_pipeline(case["file"])
    car_source = sources["car"]
    fluid_source = sources["fluid"]
    name = case["name"]

    view = GetActiveViewOrCreate('RenderView')
    view.ViewSize = IMG_SIZE  # needed for correct legend font scaling

    # --- 1-2: contours (car surface, static + total pressure - velocity omitted, no-slip means it's ~0 on the surface) ---
    apply_perspective_camera(view, CAM_ISO)
    save_contour(car_source, view, FIELDS["static_pressure"], f"{name}_iso_pressure.png", case["out"])
    save_contour(car_source, view, FIELDS["total_pressure"], f"{name}_iso_total_pressure.png", case["out"])

    apply_perspective_camera(view, CAM_UNDERSIDE_ISO)
    save_contour(car_source, view, FIELDS["static_pressure"], f"{name}_under_pressure.png", case["out"])
    save_contour(car_source, view, FIELDS["total_pressure"], f"{name}_under_total_pressure.png", case["out"])

    # --- 5: centerline graph (fluid domain, so points off the surface still sample real data) ---
    save_centerline_graph(fluid_source, case["out"], name)

    # --- 6-9: streamlines (fluid domain - car surface has ~0 velocity at the wall) ---
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

    # --- 10: sweeping movies (fluid domain, velocity/static/total pressure x bottom/side/front) ---
    for field_key in ["velocity", "static_pressure", "total_pressure"]:
        for view_name in ["top", "side", "front"]:
            make_sweep_movie(fluid_source, view_name, view, FIELDS[field_key], WASH_BOUNDS, case["out"], name, field_key)

    # --- 11: 50mm slice decks (fluid domain) ---
    for field_key in ["velocity", "static_pressure", "total_pressure"]:
        for view_name in ["top", "side", "front"]:
            make_slice_deck(fluid_source, view_name, view, FIELDS[field_key], WASH_BOUNDS, case["out"], name, field_key)

    # --- 12: spanwise pressure graphs (fluid domain) ---
    make_spanwise_pressure_graphs(fluid_source, case["out"], name)

    # --- 13: surface LIC streamlines (car surface) ---
    apply_perspective_camera(view, CAM_ISO)
    save_surface_lic(car_source, view, CAM_ISO, f"{name}_iso_surface_lic.png", case["out"])
    save_surface_lic(car_source, view, CAM_UNDERSIDE_ISO, f"{name}_under_surface_lic.png", case["out"])

    # --- 14: Q-criterion isosurfaces (vortex structures / drag source locator) ---
    save_isosurface(fluid_source, car_source, view, CAM_ISO, f"{name}_iso_qcriterion.png", case["out"])
    save_isosurface(fluid_source, car_source, view, CAM_UNDERSIDE_ISO, f"{name}_under_qcriterion.png", case["out"])

    Delete(car_source)
    Delete(fluid_source)
    print(f"Done: {name}")


if __name__ == "__main__":
    for case in CASES:
        process_case(case)
