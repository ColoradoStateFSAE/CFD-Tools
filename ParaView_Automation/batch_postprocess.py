# ============================================================================
# batch_postprocess.py
# VERSION: 2026-08-05_0247
# ============================================================================
# Written fresh against a confirmed ParaView 6.2.0-RC1 GUI trace.
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

SCRIPT_VERSION = "2026-08-05_0247"

# ============================================================
# CASES
# ============================================================
CASES = [
    {"name": "case_001",
     "file": r"C:\Users\HayesDodson\Downloads\data\FLTG-Setup-Output.encas",
     "out":  r"C:\Users\HayesDodson\Downloads\test"},
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
ALL_COLOR_FIELDS = ["Velocity_Magnitude", "Static_Pressure", "Total_Pressure",
                    "Skin_Friction_Coefficient"]

ISOSURFACE_FIELD = 'Q_Criterion_Normalized'
ISOSURFACE_VALUE = 1.0
ISOSURFACE_COLOR_FIELD = 'Velocity_Magnitude'

# ============================================================
# OUTPUT SETTINGS
# 4K MP4 export is confirmed working in 6.2 (the trace exported
# ImageResolution=[3840, 2160] successfully).
# ============================================================
IMG_SIZE = [3840, 2160]
N_SWEEP_FRAMES = 120        # 5 seconds at 24fps
MOVIE_FRAMERATE = 24
MOVIE_BITRATE = 10000000
SLICE_STEP = 0.05           # 50mm

# ============================================================
# MOVIE ENCODER BACKENDS
#
# 'paraview' uses vtkMP4Writer (Windows Media Foundation). Two hard limits:
#   1. H.264 encodes in 16x16 macroblocks, so BOTH dimensions must be
#      divisible by 16. 1920x1080 FAILS because 1080/16 = 67.5. The standard
#      padded height is 1088. 1280x720 works because both divide cleanly.
#   2. It will not initialize above roughly 1920x1088 in an offscreen
#      pvpython process, so true 4K movies are not possible on this path.
#
# 'ffmpeg' renders PNG frames at full resolution and encodes them externally.
# No macroblock or dimension limits, so 4K movies work. Requires ffmpeg on
# PATH (see README for install instructions).
#
# 'auto' (default) picks ffmpeg when it is available and the requested size
# exceeds what vtkMP4Writer can handle, otherwise uses ParaView directly.
# ============================================================
MOVIE_ENCODER = "auto"          # auto | paraview | ffmpeg
FFMPEG_PATH = "ffmpeg"          # or a full path like r"C:\ffmpeg\bin\ffmpeg.exe"
FFMPEG_CRF = 18                 # 0 lossless, 18 visually lossless, 23 default
FFMPEG_PRESET = "medium"        # ultrafast..veryslow, slower = smaller file
KEEP_FRAMES = False             # keep the PNG frames after encoding
MACROBLOCK = 16
MP4_MAX_WIDTH = 1920
MP4_MAX_HEIGHT = 1088


def ffmpeg_available():
    if os.path.isabs(FFMPEG_PATH):
        return os.path.exists(FFMPEG_PATH)
    return shutil.which(FFMPEG_PATH) is not None


def snap_to_macroblock(size):
    """Round each dimension up to the next multiple of 16 for H.264."""
    return [((v + MACROBLOCK - 1) // MACROBLOCK) * MACROBLOCK for v in size]


def within_mp4_writer_limits(size):
    return size[0] <= MP4_MAX_WIDTH and size[1] <= MP4_MAX_HEIGHT


def choose_encoder(size):
    """Return 'paraview' or 'ffmpeg' for the requested movie resolution."""
    if MOVIE_ENCODER in ("paraview", "ffmpeg"):
        return MOVIE_ENCODER
    if within_mp4_writer_limits(snap_to_macroblock(size)) or not ffmpeg_available():
        return "paraview"
    return "ffmpeg"

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
    t.Vectors = ['POINTS', 'Velocity']
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
    d = os.path.join(out_dir, "movies")
    os.makedirs(d, exist_ok=True)
    axis = AXIS_FOR_VIEW[view_name]
    idx = AXIS_INDEX[axis]
    lo, hi = bounds[axis]

    sl = Slice(registrationName=f'SweepSlice_{view_name}_{field_key}', Input=fluid)
    sl.SliceType.Normal = NORMAL_VEC[axis]
    origin = [0.0, 0.0, 0.0]
    origin[idx] = lo
    sl.SliceType.Origin = origin
    sl.UpdatePipeline()

    disp = Show(sl, view)
    ColorBy(disp, ('POINTS', field))
    ctf = apply_color(view, field)
    disp.SetScalarBarVisibility(view, True)

    base = CAMS_BY_VIEW[view_name]
    apply_camera(view, base)

    scene = GetAnimationScene()
    scene.NumberOfFrames = N_SWEEP_FRAMES

    # --- slice Origin track ---
    track = GetAnimationTrack('Origin', index=idx, proxy=sl.SliceType)
    kf0 = CompositeKeyFrame()
    kf0.Set(KeyTime=0.0, KeyValues=[lo], Interpolation='Ramp',
            Base=2.0, StartPower=0.0, EndPower=1.0, Phase=0.0, Frequency=1.0, Offset=0.0)
    kf1 = CompositeKeyFrame()
    kf1.Set(KeyTime=1.0, KeyValues=[hi], Interpolation='Ramp',
            Base=2.0, StartPower=0.0, EndPower=1.0, Phase=0.0, Frequency=1.0, Offset=0.0)
    track.Set(TimeMode='Normalized', StartTime=0.0, EndTime=1.0, Enabled=1,
              KeyFrames=[kf0, kf1])

    # --- camera track, translated by the same distance the slice travels ---
    end_cam = shifted_camera(view_name, hi - lo)
    ckf0 = CameraKeyFrame()
    ckf0.Set(KeyTime=0.0, KeyValues=[0.0],
             Position=base["position"], FocalPoint=base["focal_point"],
             ViewUp=base["view_up"], ViewAngle=CAMERA_VIEW_ANGLE,
             ParallelScale=CAMERA_PARALLEL_SCALE)
    ckf1 = CameraKeyFrame()
    ckf1.Set(KeyTime=1.0, KeyValues=[0.0],
             Position=end_cam["position"], FocalPoint=end_cam["focal_point"],
             ViewUp=end_cam["view_up"], ViewAngle=CAMERA_VIEW_ANGLE,
             ParallelScale=CAMERA_PARALLEL_SCALE)
    cam_track = GetCameraTrack(view=view)
    cam_track.Set(TimeMode='Normalized', StartTime=0.0, EndTime=1.0, Enabled=1,
                  Mode='Interpolate Camera', Interpolation='Spline',
                  KeyFrames=[ckf0, ckf1], DataSource=None)

    stem = f"{name}_{view_name}_{field_key}"
    encoder = choose_encoder(IMG_SIZE)

    if encoder == "paraview":
        size = snap_to_macroblock(IMG_SIZE)
        if size != IMG_SIZE:
            print(f"    [encoder] snapped {IMG_SIZE[0]}x{IMG_SIZE[1]} -> "
                  f"{size[0]}x{size[1]} (H.264 needs multiples of {MACROBLOCK})")
        if not within_mp4_writer_limits(size):
            print(f"    [encoder] WARNING {size[0]}x{size[1]} exceeds the vtkMP4Writer "
                  f"limit of {MP4_MAX_WIDTH}x{MP4_MAX_HEIGHT}. Install ffmpeg and use "
                  f"--encoder ffmpeg for this resolution.")
        out_path = os.path.join(d, f"{stem}.mp4").replace("\\", "/")
        SaveAnimation(filename=out_path, viewOrLayout=view,
                      ImageResolution=size,
                      FrameRate=MOVIE_FRAMERATE,
                      FrameStride=1,
                      FrameWindow=[0, N_SWEEP_FRAMES - 1],
                      BitRate=MOVIE_BITRATE)
        ok = os.path.exists(out_path) and os.path.getsize(out_path) > 0
        print(f"  [movie] {'wrote' if ok else 'FAILED'} {out_path}")

    else:
        # Render PNG frames at full requested resolution, then encode with ffmpeg.
        # No macroblock or dimension limits on this path.
        frame_dir = os.path.join(d, "frames", stem)
        os.makedirs(frame_dir, exist_ok=True)
        for old in os.listdir(frame_dir):
            if old.endswith(".png"):
                try:
                    os.remove(os.path.join(frame_dir, old))
                except OSError:
                    pass

        frame_pattern_pv = os.path.join(frame_dir, f"{stem}.png").replace("\\", "/")
        SaveAnimation(filename=frame_pattern_pv, viewOrLayout=view,
                      ImageResolution=IMG_SIZE,
                      FrameRate=MOVIE_FRAMERATE,
                      FrameStride=1,
                      FrameWindow=[0, N_SWEEP_FRAMES - 1])

        frames = sorted(f for f in os.listdir(frame_dir) if f.endswith(".png"))
        if not frames:
            print(f"  [movie] FAILED no frames written to {frame_dir}")
        else:
            # ParaView numbers frames as <stem>.NNNN.png
            digits = len(frames[0].rsplit(".", 2)[1])
            in_pattern = os.path.join(frame_dir, f"{stem}.%0{digits}d.png")
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
                size_mb = os.path.getsize(out_path) / 1e6
                print(f"  [movie] wrote {out_path} ({size_mb:.1f} MB, {len(frames)} frames, ffmpeg)")
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
                print(f"  [movie] ffmpeg not found. Frames kept at {frame_dir}")
                print(f"          encode manually: ffmpeg -framerate {MOVIE_FRAMERATE} "
                      f"-i \"{in_pattern}\" -c:v libx264 -crf {FFMPEG_CRF} "
                      f"-pix_fmt yuv420p \"{out_path}\"")
            except subprocess.CalledProcessError as e:
                tail = e.stderr.decode(errors="ignore")[-600:] if e.stderr else "(no output)"
                print(f"  [movie] ffmpeg failed for {stem}:\n{tail}")

    # tear the tracks back down so the next movie starts clean
    cam_track.Enabled = 0
    track.Enabled = 0
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
    d = os.path.join(out_dir, "surface_lic")
    os.makedirs(d, exist_ok=True)
    disp = Show(car, view)
    disp.SetRepresentationType('Surface LIC')
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
    c.ContourBy = ['POINTS', ISOSURFACE_FIELD]
    c.Isosurfaces = [ISOSURFACE_VALUE]
    c.UpdatePipeline()

    if _cells(c) == 0:
        print(f"  [warn] isosurface empty at {ISOSURFACE_FIELD}={ISOSURFACE_VALUE}, "
              f"try a lower ISOSURFACE_VALUE")

    car_disp = Show(car, view)
    car_disp.Representation = 'Surface'
    ColorBy(car_disp, None)
    car_disp.AmbientColor = [0.6, 0.6, 0.6]
    car_disp.DiffuseColor = [0.6, 0.6, 0.6]

    disp = Show(c, view)
    ColorBy(disp, ('POINTS', ISOSURFACE_COLOR_FIELD))
    ctf = apply_color(view, ISOSURFACE_COLOR_FIELD)
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
    view.ViewSize = IMG_SIZE

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
    p.add_argument("--slice-step", type=float, default=None,
                   help=f"override slice spacing in metres (default {SLICE_STEP})")
    p.add_argument("--resolution", nargs=2, type=int, metavar=("W", "H"), default=None,
                   help=f"override output resolution (default {IMG_SIZE[0]} {IMG_SIZE[1]})")
    p.add_argument("--encoder", choices=["auto", "paraview", "ffmpeg"], default=None,
                   help="movie encoder backend (default: auto). 'paraview' is capped at "
                        "1920x1088 and needs dimensions divisible by 16; 'ffmpeg' has no "
                        "such limits and is required for 4K movies")
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
    if args.slice_step is not None:
        SLICE_STEP = args.slice_step
    if args.resolution is not None:
        IMG_SIZE = list(args.resolution)
    if args.encoder is not None:
        MOVIE_ENCODER = args.encoder
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
    print(f"frames/fps : {N_SWEEP_FRAMES} @ {MOVIE_FRAMERATE}")
    print(f"slice step : {SLICE_STEP} m")
    if "movies" in stages and not args.probe_only:
        chosen = choose_encoder(IMG_SIZE)
        have_ff = ffmpeg_available()
        print(f"encoder    : {MOVIE_ENCODER} -> using '{chosen}' "
              f"(ffmpeg {'found' if have_ff else 'NOT found'})")
        if chosen == "paraview":
            snapped = snap_to_macroblock(IMG_SIZE)
            if snapped != IMG_SIZE:
                print(f"             movie size will snap to {snapped[0]}x{snapped[1]}")
            if not within_mp4_writer_limits(snapped):
                print(f"             WARNING above the {MP4_MAX_WIDTH}x{MP4_MAX_HEIGHT} "
                      f"vtkMP4Writer limit, install ffmpeg for this resolution")
    print(f"cases      : {', '.join(c['name'] for c in cases)}")

    run_start = datetime.datetime.now()
    for case in cases:
        try:
            process_case(case, opt)
        except Exception as e:
            print(f"!! {case['name']} failed: {e}", file=sys.stderr)
            raise
    print(f"\ntotal runtime {(datetime.datetime.now() - run_start).total_seconds():.1f}s")