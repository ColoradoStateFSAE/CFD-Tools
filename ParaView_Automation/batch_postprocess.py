# ============================================================================
# batch_postprocess.py
# VERSION: 2026-08-31_1901
# ============================================================================
# Written fresh against a confirmed ParaView 6.2.0-RC1 GUI trace.
#
# WHY THE PREVIOUS VERSION BROKE:
#   ParaView changed from 6.1.1 to 6.2.0-RC1. Block selector names changed:
#       6.1.1  ->  /Root/enclosureenclosure11
#       6.2.0  ->  /Root/enclosure-enclosure11     (hyphen added)
#   ExtractBlock does NOT error on a bad selector, it just returns 0 cells,
#   so everything downstream silently rendered blank. This script now probes
#   candidate selector strings at runtime and uses whichever actually returns
#   cells, so a future rename cannot silently break it again.
#
# Run with:   pvpython batch_postprocess_2026-08-05_0202.py
# Headless:   pvbatch --mesa batch_postprocess_2026-08-05_0202.py
# ============================================================================

from paraview.simple import *
import os
import sys
import shutil
import argparse
import subprocess
import datetime

paraview.simple._DisableFirstRenderCameraReset()

SCRIPT_VERSION = "2026-08-31_1901"

# ============================================================
# CASES
# ============================================================
CASES = [
    {"name": "case_001",
     "file": r"D:\ParaviewData\NemisisFullCar\FLTG.encas",
     "out":  r"D:\ParaviewData\NemisisFullCar\Photos"},
]

# ============================================================
# BLOCK SELECTORS
# Candidates are tried in order; the first that yields cells wins.
# Add new spellings here if a future ParaView version renames things again.
# ============================================================
CAR_BLOCK_NAMES = ['undertray', 'rearwing', 'frontwing', 'chassis',
                   'front_sus', 'rear_sus', 'rw', 'fw', 'rwb', 'fwb']

FLUID_BLOCK_CANDIDATES = [
    '/Root/enclosure-enclosure11',   # ParaView 6.2.0-RC1 (confirmed from trace)
    '/Root/enclosureenclosure11',    # ParaView 6.1.1
]

# ============================================================
# BOUNDS
# ============================================================
CAR_BOUNDS = {
    "x": (-1.8415, 1.23425),    # inlet(-) to outlet(+), streamwise
    "y": (0.0, 1.32862),        # ground to roof
    "z": (-0.70231, 0.70231),   # full width once the car block is reflected
}

# sweep/slice range for movies and slice decks
WASH_BOUNDS = {
    "x": (-1.0, 2.5),
    "y": (0.0, 1.8),
    "z": (0.0, 1.8),
}

# ============================================================
# FIELDS AND COLOR
#
# Ansys renamed every field between releases, so names are resolved at runtime
# against whatever the file actually contains:
#
#   role              2025R2                      2026R1
#   ----------------  --------------------------  ---------------------
#   static pressure   Static_Pressure             pressure
#   total pressure    Total_Pressure             total_pressure
#   velocity mag      Velocity_Magnitude         velocity_magnitude
#   velocity vector   Velocity                   velocity
#   wall shear        Wall_Shear_Stress          wall_shear
#   Q criterion       Q_Criterion_Normalized     q_criterion
#   skin friction     Skin_Friction_Coefficient  skin_friction_coef
#
# Note 2026R1 has no "static_pressure"; static pressure is just "pressure".
# Candidates are tried in order, first match wins. Add new spellings here if a
# future release renames things again.
# ============================================================
FIELD_CANDIDATES = {
    "static_pressure": ["Static_Pressure", "pressure", "static_pressure"],
    "total_pressure":  ["Total_Pressure", "total_pressure"],
    "velocity":        ["Velocity_Magnitude", "velocity_magnitude"],
    "velocity_vector": ["Velocity", "velocity"],
    "wall_shear":      ["Wall_Shear_Stress", "wall_shear", "Wall_Shear", "wall_shear_stress"],
    "q_criterion":     ["Q_Criterion_Normalized", "q_criterion",
                        "Q_Criterion_Raw", "raw_q_criterion"],
    "skin_friction":   ["Skin_Friction_Coefficient", "skin_friction_coef",
                        "skin_friction_coefficient"],
}

# Ranges are keyed by ROLE, not by array name, so they survive the rename.
FIELD_RANGES_BY_ROLE = {
    "velocity":        [0, 30],
    "static_pressure": [-750, 250],
    "total_pressure":  [-750, 300],
}

# Populated by resolve_fields() once a case is opened. Maps role -> real array
# name in this file, e.g. {"static_pressure": "pressure", ...}
FIELDS = {}
FIELD_RANGES = {}
ALL_COLOR_FIELDS = []

COLOR_PRESET = 'Rainbow Uniform'

ISOSURFACE_VALUE = 1.0

# ============================================================
# SURFACE LIC (flow-vis paint comparison)
#
# The convolution vector must be wall shear stress. Velocity is ~0 at the wall
# under no-slip, so convolving along it yields a flat, directionless texture.
# Wall shear stress is what actually drives streak direction in a real
# oil-flow test, so it makes the render comparable to a paint photo.
# ============================================================
LIC_NUMBER_OF_STEPS = 100       # ParaView default 40; higher = longer streaks
LIC_STEP_SIZE = 0.2             # ParaView default 0.25; lower = finer detail
LIC_INTENSITY = 0.9             # ParaView default 0.8; higher = stronger streaks
LIC_ENHANCE_CONTRAST = 'Color Only'   # 'Off' | 'LIC Only' | 'LIC and Color' | 'Color Only'
LIC_ANTIALIAS = 1               # 0 off, 1 on. Cleans up streak edges


def available_arrays(proxy):
    """Point-data array names present on this proxy."""
    names = []
    try:
        pd = proxy.PointData
        for i in range(len(pd)):
            names.append(pd.GetArray(i).GetName())
    except Exception as e:
        print(f"  [fields] could not list arrays: {e}")
    return names


def resolve_fields(reader):
    """Match each logical role to a real array name in this file.

    Sets the module-level FIELDS, FIELD_RANGES and ALL_COLOR_FIELDS so the rest
    of the script can keep referring to roles instead of release-specific names.
    """
    global FIELDS, FIELD_RANGES, ALL_COLOR_FIELDS

    present = available_arrays(reader)
    lookup = {n.lower(): n for n in present}

    FIELDS = {}
    missing = []
    for role, candidates in FIELD_CANDIDATES.items():
        for cand in candidates:
            if cand in present:
                FIELDS[role] = cand
                break
            if cand.lower() in lookup:
                FIELDS[role] = lookup[cand.lower()]
                break
        else:
            missing.append(role)

    FIELD_RANGES = {FIELDS[r]: v for r, v in FIELD_RANGES_BY_ROLE.items() if r in FIELDS}
    ALL_COLOR_FIELDS = [FIELDS[r] for r in
                        ("velocity", "static_pressure", "total_pressure",
                         "skin_friction", "wall_shear", "q_criterion")
                        if r in FIELDS]

    print(f"  [fields] {len(present)} arrays in file, resolved:")
    for role in FIELD_CANDIDATES:
        if role in FIELDS:
            print(f"           {role:16s} -> {FIELDS[role]}")
        else:
            print(f"           {role:16s} -> NOT FOUND")

    critical = ["static_pressure", "total_pressure", "velocity", "velocity_vector"]
    lost = [r for r in critical if r not in FIELDS]
    if lost:
        raise RuntimeError(
            f"Required fields not found: {', '.join(lost)}. "
            f"Add the correct spelling to FIELD_CANDIDATES at the top of this script. "
            f"Arrays present: {', '.join(sorted(present))}"
        )
    if missing:
        print(f"  [fields] optional fields unavailable: {', '.join(missing)} "
              f"(stages needing them will be skipped or fall back)")


# ============================================================
# OUTPUT SETTINGS
# 4K MP4 export is confirmed working in 6.2 (the trace exported
# ImageResolution=[3840, 2160] successfully).
# ============================================================
IMG_SIZE = [2560, 1440]
MOVIE_FRAMERATE = 20      # playback framerate
MOVIE_SECONDS = 5           # clip length in seconds
N_SWEEP_FRAMES = MOVIE_FRAMERATE * MOVIE_SECONDS   
SLICE_STEP = 0.01          # 10mm

# ============================================================
# FFMPEG
#
# Movies are rendered as PNG frames with SaveScreenshot (which honours the
# requested resolution reliably) and then encoded with ffmpeg.
#
# ParaView's own vtkMP4Writer and the native animation engine are NOT used.
# The writer caps out around 1920x1088, needs both dimensions divisible by 16,
# and SaveAnimation ignored ImageResolution in offscreen pvpython, silently
# producing 1540x942 frames. A plain per-frame loop avoids all of that.
#
# Set FFMPEG_PATH once here so it never has to be passed as a flag.
# ============================================================
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"
FFMPEG_CRF = 18                 # 0 lossless, 18 visually lossless, 23 default
FFMPEG_PRESET = "medium"        # ultrafast..veryslow, slower = smaller file
KEEP_FRAMES = False             # keep the PNG frames after encoding


def ffmpeg_available():
    if os.path.isabs(FFMPEG_PATH):
        return os.path.exists(FFMPEG_PATH)
    return shutil.which(FFMPEG_PATH) is not None


def force_render_size(view, size):
    """Force the offscreen render window AND its layout to the target size.

    SaveAnimation's ImageResolution argument is not reliably honoured in an
    offscreen pvpython process: if the layout disagrees, frames come out at the
    render window's own size instead (observed: 1540x942 when 3840x2160 was
    requested). Setting both is what actually pins the output resolution.
    """
    view.ViewSize = list(size)
    try:
        layout = GetLayout(view)
        if layout is not None:
            layout.SetSize(int(size[0]), int(size[1]))
    except Exception as e:
        print(f"    [size] could not set layout size: {e}")
    Render()


def png_size(path):
    """Read width/height straight from the PNG IHDR chunk. No dependencies."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        w = int.from_bytes(head[16:20], "big")
        h = int.from_bytes(head[20:24], "big")
        return (w, h)
    except Exception:
        return None


# ============================================================
# CAMERAS (from .pvcc state files, perspective projection)
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
CAM_FRONT = {
    "position": [-2.7083522739750983, 0.9135278128072652, 1.1695509914959028],
    "focal_point": [-0.6499999761581421, 0.9135278128072652, 1.1695509914959028],
    "view_up": [0, 1, 0],
}
CAM_SIDE = {
    "position": [0.832442, 1.67923, 6.27772],
    "focal_point": [0.832442, 1.67923, 3.45115],
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

CAMERA_PARALLEL_SCALE = 18.6899   # from the trace, used by camera keyframes
CAMERA_VIEW_ANGLE = 30.0


def apply_camera(view, cam):
    view.CameraParallelProjection = 0
    view.CameraPosition = cam["position"]
    view.CameraFocalPoint = cam["focal_point"]
    view.CameraViewUp = cam["view_up"]


def shifted_camera(view_name, distance):
    """Base camera translated along the sweep axis by `distance`."""
    base = CAMS_BY_VIEW[view_name]
    idx = AXIS_INDEX[AXIS_FOR_VIEW[view_name]]
    shift = [0.0, 0.0, 0.0]
    shift[idx] = distance
    return {
        "position": [base["position"][i] + shift[i] for i in range(3)],
        "focal_point": [base["focal_point"][i] + shift[i] for i in range(3)],
        "view_up": base["view_up"],
    }


# ============================================================
# BLOCK SELECTOR PROBING
# ============================================================
def _make_extract(reader, selectors):
    ex = ExtractBlock(Input=reader)
    try:
        ex.Assembly = 'Hierarchy'    # exists in 6.2, may not in older builds
    except Exception:
        pass
    ex.Selectors = selectors
    ex.UpdatePipeline()
    return ex


def _cells(proxy):
    return proxy.GetDataInformation().GetNumberOfCells()


def resolve_fluid_block(reader):
    for candidate in FLUID_BLOCK_CANDIDATES:
        try:
            ex = _make_extract(reader, [candidate])
            n = _cells(ex)
            print(f"  [probe] fluid selector {candidate!r} -> {n} cells")
            if n > 0:
                return ex, candidate
            Delete(ex)
        except Exception as e:
            print(f"  [probe] fluid selector {candidate!r} raised: {e}")
    raise RuntimeError(
        "No fluid block selector matched. Open the file in the GUI, add an "
        "ExtractBlock, and check the exact selector string in the trace. "
        "Then add it to FLUID_BLOCK_CANDIDATES at the top of this script."
    )


def resolve_car_blocks(reader):
    """Car block names have no special characters, but the hyphen change on the
    enclosure block shows names can shift between versions, so probe per block
    and keep whichever spelling returns cells."""
    working = []
    for base in CAR_BLOCK_NAMES:
        for candidate in (f'/Root/{base}', f'/Root/{base.replace("_", "-")}'):
            try:
                ex = _make_extract(reader, [candidate])
                n = _cells(ex)
                Delete(ex)
                if n > 0:
                    working.append(candidate)
                    break
            except Exception:
                continue
        else:
            print(f"  [warn] no working selector found for car block {base!r}")

    if not working:
        raise RuntimeError("No car block selectors matched. Check block names in the GUI.")

    ex = _make_extract(reader, working)
    print(f"  [probe] car blocks -> {len(working)}/{len(CAR_BLOCK_NAMES)} matched, "
          f"{_cells(ex)} cells")
    return ex


def make_reflect(input_proxy):
    r = AxisAlignedReflect(Input=input_proxy)
    r.ReflectionPlane.Set(Origin=[0.0, 0.0, 0.0], Normal=[0.0, 0.0, 1.0])
    r.ReflectAllInputArrays = 1
    r.UpdatePipeline()
    return r


def build_pipeline(case_file):
    if not os.path.exists(case_file):
        raise RuntimeError(f"Case file not found: {case_file}")

    reader = OpenDataFile(case_file)
    reader.UpdatePipeline()
    print(f"  [check] reader cells: {_cells(reader)}")

    resolve_fields(reader)

    car_extract = resolve_car_blocks(reader)
    car = make_reflect(car_extract)            # mirror the car for full-width visuals
    print(f"  [check] car after reflect: {_cells(car)} cells")

    fluid, sel = resolve_fluid_block(reader)   # fluid stays half-width (symmetric flow)
    print(f"  [check] using fluid selector: {sel}")

    return {"car": car, "fluid": fluid}


# ============================================================
# COLOR / LEGEND
# ============================================================
def hide_all_scalar_bars(view):
    for f in ALL_COLOR_FIELDS:
        try:
            GetScalarBar(GetColorTransferFunction(f), view).Visibility = 0
        except Exception:
            pass


def apply_color(view, field):
    hide_all_scalar_bars(view)
    ctf = GetColorTransferFunction(field)
    if field in FIELD_RANGES:
        ctf.RescaleTransferFunction(*FIELD_RANGES[field])
    ctf.ApplyPreset(COLOR_PRESET, True)
    sb = GetScalarBar(ctf, view)
    sb.WindowLocation = 'Any Location'
    sb.Position = [0.90, 0.35]
    sb.ScalarBarLength = 0.33
    sb.ScalarBarThickness = 16
    return ctf


def shot(view, path, size=None):
    SaveScreenshot(path, view, ImageResolution=size or IMG_SIZE)


# ============================================================
# STREAMLINE SEEDS
# ============================================================
SEED_MAIN = {"center": [CAR_BOUNDS["x"][0] - 0.5, 0.55, 0.0], "radius": 0.65, "n": 600}
SEED_UNDER = {"center": [CAR_BOUNDS["x"][0] - 0.25, 0.06, 0.0], "radius": 0.55, "n": 500}


def _tracer(source, seed):
    t = StreamTracer(Input=source, SeedType='Point Cloud')
    t.SeedType.Center = seed["center"]
    t.SeedType.Radius = seed["radius"]
    t.SeedType.NumberOfPoints = seed["n"]
    t.Vectors = ['POINTS', FIELDS['velocity_vector']]
    t.MaximumStreamlineLength = 8
    return t


# ============================================================
# OUTPUT 1: CONTOURS ON CAR SURFACE (pressure only, no-slip makes velocity ~0)
# ============================================================
def save_contour(car, view, field, filename, out_dir):
    d = os.path.join(out_dir, "contours")
    os.makedirs(d, exist_ok=True)
    disp = Show(car, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color(view, field)
    disp.SetScalarBarVisibility(view, True)
    Render()
    shot(view, os.path.join(d, filename))
    GetScalarBar(ctf, view).Visibility = 0
    Hide(car, view)


# ============================================================
# OUTPUT 2: STREAMLINES (seeded in the fluid domain, car shown for context)
# ============================================================
def save_streamlines(fluid, car, view, field, filename, out_dir):
    d = os.path.join(out_dir, "streamlines")
    os.makedirs(d, exist_ok=True)

    t1 = _tracer(fluid, SEED_MAIN)
    t2 = _tracer(fluid, SEED_UNDER)
    both = AppendDatasets(Input=[t1, t2])
    both.UpdatePipeline()

    car_disp = Show(car, view)
    car_disp.Representation = 'Surface'
    ColorBy(car_disp, None)
    car_disp.AmbientColor = [0.6, 0.6, 0.6]
    car_disp.DiffuseColor = [0.6, 0.6, 0.6]

    disp = Show(both, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color(view, field)
    disp.SetScalarBarVisibility(view, True)
    Render()
    shot(view, os.path.join(d, filename))

    GetScalarBar(ctf, view).Visibility = 0
    Delete(both); Delete(t2); Delete(t1)
    Hide(car, view)


# ============================================================
# OUTPUT 3: LINE GRAPHS
# ============================================================
def save_centerline_graph(fluid, out_dir, name):
    d = os.path.join(out_dir, "graphs", "centerline")
    os.makedirs(d, exist_ok=True)
    x0, x1 = CAR_BOUNDS["x"]
    pol = PlotOverLine(Input=fluid)
    pol.Point1 = [x0, 0.05, 0.0]
    pol.Point2 = [x1, 0.05, 0.0]
    pol.UpdatePipeline()
    SaveData(os.path.join(d, f"{name}_centerline.csv"), proxy=pol, WriteTimeSteps=False)
    Delete(pol)


def save_spanwise_graphs(fluid, out_dir, name):
    d = os.path.join(out_dir, "graphs", "spanwise")
    os.makedirs(d, exist_ok=True)
    z0, z1 = WASH_BOUNDS["z"]
    x0, x1 = CAR_BOUNDS["x"]
    for i in range(int(round((z1 - z0) / SLICE_STEP)) + 1):
        z = z0 + i * SLICE_STEP
        pol = PlotOverLine(Input=fluid)
        pol.Point1 = [x0, 0.05, z]
        pol.Point2 = [x1, 0.05, z]
        pol.UpdatePipeline()
        tag = f"z{z * 1000:+05.0f}mm".replace("+", "p").replace("-", "m")
        SaveData(os.path.join(d, f"{tag}.csv"), proxy=pol, WriteTimeSteps=False)
        Delete(pol)


# ============================================================
# OUTPUT 4: SWEEP MOVIE via ParaView's native animation engine.
# All calls below are copied from the confirmed 6.2.0-RC1 trace:
#   GetAnimationTrack('Origin', index=N, proxy=slice.SliceType)
#   CompositeKeyFrame() with KeyTime / KeyValues / Interpolation='Ramp'
#   track.Set(TimeMode='Normalized', StartTime=0, EndTime=1, Enabled=1, KeyFrames=[...])
#   GetCameraTrack(view=...) with CameraKeyFrame() and Mode='Interpolate Camera'
#   SaveAnimation(filename=..., viewOrLayout=..., FrameWindow=[0, N-1], ...)
#
# Mode='Interpolate Camera' matters: the default is 'Follow-data', which
# ignores the keyframe positions entirely.
# ============================================================
def make_sweep_movie(fluid, view_name, view, field, bounds, out_dir, name, field_key):
    """Render the sweep as PNG frames, then encode with ffmpeg.

    No animation tracks and no SaveAnimation. Each frame sets the slice origin
    and the camera explicitly, then SaveScreenshot writes it at the requested
    resolution. This is slower per frame than the native engine but it is the
    only path that reliably honours the resolution.
    """
    d = os.path.join(out_dir, "movies")
    os.makedirs(d, exist_ok=True)
    axis = AXIS_FOR_VIEW[view_name]
    idx = AXIS_INDEX[axis]
    lo, hi = bounds[axis]

    stem = f"{name}_{view_name}_{field_key}"
    frame_dir = os.path.join(d, "frames", stem)
    os.makedirs(frame_dir, exist_ok=True)
    for old in os.listdir(frame_dir):
        if old.endswith(".png"):
            try:
                os.remove(os.path.join(frame_dir, old))
            except OSError:
                pass

    sl = Slice(Input=fluid)
    sl.SliceType.Normal = NORMAL_VEC[axis]
    origin = [0.0, 0.0, 0.0]
    origin[idx] = lo
    sl.SliceType.Origin = origin
    sl.UpdatePipeline()

    disp = Show(sl, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color(view, field)
    disp.SetScalarBarVisibility(view, True)

    force_render_size(view, IMG_SIZE)

    for i in range(N_SWEEP_FRAMES):
        t = i / (N_SWEEP_FRAMES - 1) if N_SWEEP_FRAMES > 1 else 0.0
        pos = lo + t * (hi - lo)
        origin = [0.0, 0.0, 0.0]
        origin[idx] = pos
        sl.SliceType.Origin = origin
        apply_camera(view, shifted_camera(view_name, pos - lo))
        Render()
        SaveScreenshot(os.path.join(frame_dir, f"frame_{i:05d}.png"), view,
                       ImageResolution=IMG_SIZE)

    frames = sorted(f for f in os.listdir(frame_dir) if f.endswith(".png"))
    if not frames:
        print(f"  [movie] FAILED no frames written to {frame_dir}")
        GetScalarBar(ctf, view).Visibility = 0
        Delete(sl)
        return

    actual = png_size(os.path.join(frame_dir, frames[0]))
    if actual is None:
        print(f"    [size] could not read frame dimensions")
    elif list(actual) != list(IMG_SIZE):
        print(f"    [size] WARNING frames are {actual[0]}x{actual[1]}, "
              f"not the requested {IMG_SIZE[0]}x{IMG_SIZE[1]}")
    else:
        print(f"    [size] frames confirmed at {actual[0]}x{actual[1]}")

    in_pattern = os.path.join(frame_dir, "frame_%05d.png")
    out_path = os.path.join(d, f"{stem}.mp4")
    cmd = [FFMPEG_PATH, "-y",
           "-framerate", str(MOVIE_FRAMERATE),
           "-i", in_pattern,
           "-c:v", "libx264",
           "-preset", FFMPEG_PRESET,
           "-crf", str(FFMPEG_CRF),
           "-pix_fmt", "yuv420p",
           "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
           out_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        mb = os.path.getsize(out_path) / 1e6
        secs = len(frames) / MOVIE_FRAMERATE
        print(f"  [movie] wrote {out_path} "
              f"({mb:.1f} MB, {len(frames)} frames, {secs:.1f}s @ {MOVIE_FRAMERATE}fps)")
        if not KEEP_FRAMES:
            for f in frames:
                try:
                    os.remove(os.path.join(frame_dir, f))
                except OSError:
                    pass
            try:
                os.rmdir(frame_dir)
            except OSError:
                pass
    except FileNotFoundError:
        print(f"  [movie] ffmpeg not found at {FFMPEG_PATH}")
        print(f"          frames kept at {frame_dir}")
        print(f"          encode manually: \"{FFMPEG_PATH}\" -framerate {MOVIE_FRAMERATE} "
              f"-i \"{in_pattern}\" -c:v libx264 -crf {FFMPEG_CRF} "
              f"-pix_fmt yuv420p \"{out_path}\"")
    except subprocess.CalledProcessError as e:
        tail = e.stderr.decode(errors="ignore")[-600:] if e.stderr else "(no output)"
        print(f"  [movie] ffmpeg failed for {stem}:\n{tail}")

    GetScalarBar(ctf, view).Visibility = 0
    Delete(sl)


# ============================================================
# OUTPUT 5: STATIC SLICE DECK (camera follows each slice)
# ============================================================
def make_slice_deck(fluid, view_name, view, field, bounds, out_dir, name, field_key):
    d = os.path.join(out_dir, "slices", view_name, field_key)
    os.makedirs(d, exist_ok=True)
    axis = AXIS_FOR_VIEW[view_name]
    idx = AXIS_INDEX[axis]
    lo, hi = bounds[axis]

    sl = Slice(Input=fluid)
    sl.SliceType.Normal = NORMAL_VEC[axis]

    disp = Show(sl, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color(view, field)
    disp.SetScalarBarVisibility(view, True)

    for i in range(int(round((hi - lo) / SLICE_STEP)) + 1):
        pos = lo + i * SLICE_STEP
        origin = [0.0, 0.0, 0.0]
        origin[idx] = pos
        sl.SliceType.Origin = origin
        apply_camera(view, shifted_camera(view_name, pos - lo))
        Render()
        tag = f"{axis}{pos * 1000:+05.0f}mm".replace("+", "p").replace("-", "m")
        shot(view, os.path.join(d, f"{tag}.png"))

    GetScalarBar(ctf, view).Visibility = 0
    Delete(sl)


# ============================================================
# OUTPUT 6: SURFACE LIC AND Q-CRITERION ISOSURFACES
# ============================================================
def save_surface_lic(car, view, cam, filename, out_dir):
    """Surface LIC, the CFD analogue of oil-flow paint.

    The convolution vector MUST be wall shear stress, not velocity. Velocity
    goes to ~0 at the wall under no-slip, so convolving along it produces a
    flat, directionless texture. Wall shear stress is what physically drives
    the direction oil streaks on a real flow-vis run, so it is what makes the
    CFD image comparable to a paint photo.
    """
    d = os.path.join(out_dir, "surface_lic")
    os.makedirs(d, exist_ok=True)

    disp = Show(car, view)
    disp.SetRepresentationType('Surface LIC')

    try:
        lic_vec = FIELDS.get('wall_shear') or FIELDS['velocity_vector']
        disp.SelectInputVectors = ['POINTS', lic_vec]
        if 'wall_shear' in FIELDS:
            print(f"    [lic] convolving along {lic_vec}")
        else:
            print(f"    [lic] WARNING wall shear not in this file, using {lic_vec}; "
                  f"streaks will look flat because velocity is ~0 at the wall")
    except Exception as e:
        print(f"    [lic] WARNING could not set the LIC vector "
              f"({e}); falling back to the default vector, streaks may look flat")

    # More steps and a smaller step size give crisper streaks, which matters
    # when the point is to compare line-for-line against a paint photo.
    try:
        disp.NumberOfSteps = LIC_NUMBER_OF_STEPS
        disp.StepSize = LIC_STEP_SIZE
        disp.LICIntensity = LIC_INTENSITY
        disp.EnhancedLIC = 1
        disp.NormalizeVectors = 1
        disp.EnhanceContrast = LIC_ENHANCE_CONTRAST
        disp.AntiAlias = LIC_ANTIALIAS
    except Exception as e:
        print(f"    [lic] note: some LIC quality settings unavailable ({e})")

    ColorBy(disp, ('POINTS', FIELDS["total_pressure"]))
    ctf = apply_color(view, FIELDS["total_pressure"])
    disp.SetScalarBarVisibility(view, True)
    apply_camera(view, cam)
    Render()
    shot(view, os.path.join(d, filename))
    GetScalarBar(ctf, view).Visibility = 0
    Hide(car, view)


def save_isosurface(fluid, car, view, cam, filename, out_dir):
    d = os.path.join(out_dir, "isosurfaces")
    os.makedirs(d, exist_ok=True)

    c = Contour(Input=fluid)
    c.ContourBy = ['POINTS', FIELDS['q_criterion']]
    c.Isosurfaces = [ISOSURFACE_VALUE]
    c.UpdatePipeline()

    if _cells(c) == 0:
        print(f"  [warn] isosurface empty at {FIELDS['q_criterion']}={ISOSURFACE_VALUE}, "
              f"try a lower ISOSURFACE_VALUE")

    car_disp = Show(car, view)
    car_disp.Representation = 'Surface'
    ColorBy(car_disp, None)
    car_disp.AmbientColor = [0.6, 0.6, 0.6]
    car_disp.DiffuseColor = [0.6, 0.6, 0.6]

    disp = Show(c, view)
    ColorBy(disp, ('POINTS', FIELDS['velocity']))
    ctf = apply_color(view, FIELDS['velocity'])
    disp.SetScalarBarVisibility(view, True)
    apply_camera(view, cam)
    Render()
    shot(view, os.path.join(d, filename))

    GetScalarBar(ctf, view).Visibility = 0
    Delete(c)
    Hide(car, view)


# ============================================================
# STAGES
# Each stage is independently runnable via --stage. Order here is the order
# they run in when several are selected.
# ============================================================
ALL_STAGES = ["contours", "streamlines", "graphs", "movies", "slices", "lic", "iso"]
ALL_VIEWS = ["top", "side", "front"]
ALL_FIELDS = ["velocity", "static_pressure", "total_pressure"]


def stage_contours(car, fluid, view, out, name, opt):
    apply_camera(view, CAM_ISO)
    save_contour(car, view, FIELDS["static_pressure"], f"{name}_iso_static.png", out)
    save_contour(car, view, FIELDS["total_pressure"], f"{name}_iso_total.png", out)
    apply_camera(view, CAM_UNDERSIDE_ISO)
    save_contour(car, view, FIELDS["static_pressure"], f"{name}_under_static.png", out)
    save_contour(car, view, FIELDS["total_pressure"], f"{name}_under_total.png", out)


def stage_streamlines(car, fluid, view, out, name, opt):
    apply_camera(view, CAM_ISO)
    save_streamlines(fluid, car, view, FIELDS["static_pressure"], f"{name}_iso_sl_static.png", out)
    save_streamlines(fluid, car, view, FIELDS["velocity"], f"{name}_iso_sl_velocity.png", out)
    apply_camera(view, CAM_UNDERSIDE_ISO)
    save_streamlines(fluid, car, view, FIELDS["static_pressure"], f"{name}_under_sl_static.png", out)
    save_streamlines(fluid, car, view, FIELDS["velocity"], f"{name}_under_sl_velocity.png", out)


def stage_graphs(car, fluid, view, out, name, opt):
    save_centerline_graph(fluid, out, name)
    save_spanwise_graphs(fluid, out, name)


def stage_movies(car, fluid, view, out, name, opt):
    for fk in opt["fields"]:
        for vn in opt["views"]:
            print(f"    movie: {fk} / {vn}")
            make_sweep_movie(fluid, vn, view, FIELDS[fk], WASH_BOUNDS, out, name, fk)


def stage_slices(car, fluid, view, out, name, opt):
    for fk in opt["fields"]:
        for vn in opt["views"]:
            print(f"    slice deck: {fk} / {vn}")
            make_slice_deck(fluid, vn, view, FIELDS[fk], WASH_BOUNDS, out, name, fk)


def stage_lic(car, fluid, view, out, name, opt):
    save_surface_lic(car, view, CAM_ISO, f"{name}_iso_lic.png", out)
    save_surface_lic(car, view, CAM_UNDERSIDE_ISO, f"{name}_under_lic.png", out)


def stage_iso(car, fluid, view, out, name, opt):
    if 'q_criterion' not in FIELDS:
        print("    skipped: no Q-criterion field in this export")
        return
    save_isosurface(fluid, car, view, CAM_ISO, f"{name}_iso_qcrit.png", out)
    save_isosurface(fluid, car, view, CAM_UNDERSIDE_ISO, f"{name}_under_qcrit.png", out)


STAGE_FUNCS = {
    "contours": stage_contours,
    "streamlines": stage_streamlines,
    "graphs": stage_graphs,
    "movies": stage_movies,
    "slices": stage_slices,
    "lic": stage_lic,
    "iso": stage_iso,
}


# ============================================================
# MAIN
# ============================================================
def process_case(case, opt):
    name = case["name"]
    out = case["out"]
    os.makedirs(out, exist_ok=True)
    print(f"\n=== {name} ===")

    src = build_pipeline(case["file"])
    car, fluid = src["car"], src["fluid"]

    if opt["probe_only"]:
        print("  [probe-only] pipeline resolved, stopping before any rendering")
        Delete(car)
        Delete(fluid)
        return

    view = GetActiveViewOrCreate('RenderView')
    force_render_size(view, IMG_SIZE)

    stages = opt["stages"]
    for i, s in enumerate(stages, 1):
        print(f"  [{i}/{len(stages)}] {s}")
        t0 = datetime.datetime.now()
        STAGE_FUNCS[s](car, fluid, view, out, name, opt)
        dt = (datetime.datetime.now() - t0).total_seconds()
        print(f"      {s} took {dt:.1f}s")

    Delete(car)
    Delete(fluid)
    print(f"=== done: {name} ===")


def parse_args():
    p = argparse.ArgumentParser(
        prog="batch_postprocess",
        description="ParaView batch post-processing for FSAE aero CFD.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # just check the block selectors resolve, render nothing
  pvpython %(prog)s.py --probe-only

  # one movie, one field, one view, low res, few frames (fast smoke test)
  pvpython %(prog)s.py --stage movies --fields static_pressure --views side \\
                       --frames 10 --resolution 1280 720

  # contours only
  pvpython %(prog)s.py --stage contours

  # everything except the slow stuff
  pvpython %(prog)s.py --stage contours streamlines graphs lic iso

  # full run
  pvpython %(prog)s.py --stage all
""")
    p.add_argument("--stage", nargs="+", default=["all"],
                   choices=ALL_STAGES + ["all"],
                   help="which stage(s) to run (default: all)")
    p.add_argument("--views", nargs="+", default=ALL_VIEWS, choices=ALL_VIEWS,
                   help="limit movies/slices to these views (default: all three)")
    p.add_argument("--fields", nargs="+", default=ALL_FIELDS, choices=ALL_FIELDS,
                   help="limit movies/slices to these fields (default: all three)")
    p.add_argument("--case", nargs="+", default=None,
                   help="only run cases with these names (default: all in CASES)")
    p.add_argument("--frames", type=int, default=None,
                   help=f"override sweep frame count (default {N_SWEEP_FRAMES})")
    p.add_argument("--fps", type=int, default=None,
                   help=f"override movie framerate (default {MOVIE_FRAMERATE})")
    p.add_argument("--seconds", type=float, default=None,
                   help=f"clip length in seconds; sets frames = fps * seconds "
                        f"(default {MOVIE_SECONDS})")
    p.add_argument("--slice-step", type=float, default=None,
                   help=f"override slice spacing in metres (default {SLICE_STEP})")
    p.add_argument("--resolution", nargs=2, type=int, metavar=("W", "H"), default=None,
                   help=f"override output resolution (default {IMG_SIZE[0]} {IMG_SIZE[1]})")
    p.add_argument("--ffmpeg-path", default=None,
                   help="full path to ffmpeg.exe if it is not on PATH")
    p.add_argument("--crf", type=int, default=None,
                   help=f"ffmpeg quality, 0 lossless to 51 worst (default {FFMPEG_CRF})")
    p.add_argument("--keep-frames", action="store_true",
                   help="keep the intermediate PNG frames after ffmpeg encoding")
    p.add_argument("--probe-only", action="store_true",
                   help="resolve block selectors and exit without rendering")
    p.add_argument("--list-stages", action="store_true",
                   help="print available stages and exit")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.list_stages:
        print("stages:")
        for s in ALL_STAGES:
            print(f"  {s}")
        sys.exit(0)

    # apply overrides to module-level settings
    if args.frames is not None:
        N_SWEEP_FRAMES = args.frames
    if args.fps is not None:
        MOVIE_FRAMERATE = args.fps
    if args.seconds is not None:
        MOVIE_SECONDS = args.seconds
    # --frames wins if given explicitly, otherwise derive from fps x seconds
    if args.frames is None and (args.fps is not None or args.seconds is not None):
        N_SWEEP_FRAMES = int(round(MOVIE_FRAMERATE * MOVIE_SECONDS))
    if args.slice_step is not None:
        SLICE_STEP = args.slice_step
    if args.resolution is not None:
        IMG_SIZE = list(args.resolution)
    if args.ffmpeg_path is not None:
        FFMPEG_PATH = args.ffmpeg_path
    if args.crf is not None:
        FFMPEG_CRF = args.crf
    if args.keep_frames:
        KEEP_FRAMES = True

    stages = ALL_STAGES if "all" in args.stage else [s for s in ALL_STAGES if s in args.stage]

    opt = {
        "stages": stages,
        "views": [v for v in ALL_VIEWS if v in args.views],
        "fields": [f for f in ALL_FIELDS if f in args.fields],
        "probe_only": args.probe_only,
    }

    cases = CASES if args.case is None else [c for c in CASES if c["name"] in args.case]
    if not cases:
        print(f"!! no cases matched {args.case}", file=sys.stderr)
        sys.exit(1)

    print(f"batch_postprocess version {SCRIPT_VERSION}")
    print(f"started {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        print(f"ParaView {GetParaViewVersion()}")
    except Exception:
        pass
    print(f"stages     : {', '.join(stages) if not args.probe_only else '(probe only)'}")
    print(f"views      : {', '.join(opt['views'])}")
    print(f"fields     : {', '.join(opt['fields'])}")
    print(f"resolution : {IMG_SIZE[0]}x{IMG_SIZE[1]}")
    print(f"slice step : {SLICE_STEP} m")
    if "movies" in stages and not args.probe_only:
        have_ff = ffmpeg_available()
        secs = N_SWEEP_FRAMES / MOVIE_FRAMERATE
        print(f"clip       : {N_SWEEP_FRAMES} frames @ {MOVIE_FRAMERATE}fps = {secs:.1f}s")
        print(f"ffmpeg     : {FFMPEG_PATH} ({'found' if have_ff else 'NOT FOUND'})")
        if not have_ff:
            print("             frames will still render, encode them manually afterwards")
    print(f"cases      : {', '.join(c['name'] for c in cases)}")

    run_start = datetime.datetime.now()
    for case in cases:
        try:
            process_case(case, opt)
        except Exception as e:
            print(f"!! {case['name']} failed: {e}", file=sys.stderr)
            raise
    print(f"\ntotal runtime {(datetime.datetime.now() - run_start).total_seconds():.1f}s")