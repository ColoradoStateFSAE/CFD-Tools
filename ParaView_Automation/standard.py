# batch_postprocess.py — run with: pvpython batch_postprocess.py  (test one case first)
from paraview.simple import *
import os

CASES = [
    {"name": "case_001", "file": r"C:\data\case_001\results.case", "out": r"C:\data\case_001\images"},
    # add more cases here
]

# --- FIXED CAMERAS (tune these once against your car geometry) ---
CAM_ISO = {
    "position": [3500, -4000, 2000],
    "focal_point": [1200, 0, 300],
    "view_up": [0, 0, 1],
    "view_angle": 30,
}
CAM_UNDERSIDE_ISO = {
    "position": [3500, -4000, -1200],   # below car, still angled
    "focal_point": [1200, 0, -100],
    "view_up": [0, 0, 1],
    "view_angle": 30,
}

# --- FIXED COLOR SCALES (set from your known Cp/velocity range) ---
PRESSURE_RANGE = [-1500, 500]     # Pa, adjust to your data
VELOCITY_RANGE = [0, 30]          # m/s, adjust to your data
CPT_RANGE      = [-2.0, 1.0]

IMG_SIZE = [1920, 1080]

# Reference values for CpT if not already exported by Fluent
P_REF = 0.0
RHO = 1.225
V_REF = 15.0   # m/s, update to your test speed
DYN_PRESS = 0.5 * RHO * V_REF**2


def setup_camera(view, cam):
    view.CameraPosition = cam["position"]
    view.CameraFocalPoint = cam["focal_point"]
    view.CameraViewUp = cam["view_up"]
    view.CameraViewAngle = cam["view_angle"]


def save_contour(view, reader, field, rng, filename, out_dir):
    disp = Show(reader, view)
    ColorBy(disp, ('POINTS', field))
    ctf = GetColorTransferFunction(field)
    ctf.RescaleTransferFunction(rng[0], rng[1])
    disp.SetScalarBarVisibility(view, True)
    Render()
    SaveScreenshot(os.path.join(out_dir, filename), view, ImageResolution=IMG_SIZE)
    Hide(reader, view)


def save_streamlines(view, reader, field, rng, seed_center, seed_bounds, filename, out_dir):
    tracer = StreamTracer(Input=reader, SeedType='Point Cloud')
    tracer.SeedType.Center = seed_center
    tracer.SeedType.Radius = seed_bounds
    tracer.SeedType.NumberOfPoints = 200
    tracer.Vectors = ['POINTS', 'Velocity']
    tracer.MaximumStreamlineLength = 5000
    tracer.UpdatePipeline()

    disp = Show(tracer, view)
    ColorBy(disp, ('POINTS', field))
    ctf = GetColorTransferFunction(field)
    ctf.RescaleTransferFunction(rng[0], rng[1])
    disp.SetScalarBarVisibility(view, True)
    Render()
    SaveScreenshot(os.path.join(out_dir, filename), view, ImageResolution=IMG_SIZE)
    Delete(tracer)


def process_case(case):
    os.makedirs(case["out"], exist_ok=True)
    reader = OpenDataFile(case["file"])
    reader.UpdatePipeline()

    # Add CpT if not already present in the data
    calc = Calculator(Input=reader)
    calc.ResultArrayName = 'CpT'
    calc.Function = f'(TotalPressure-{P_REF})/{DYN_PRESS}'   # adjust field name to match your export
    calc.UpdatePipeline()

    view = GetActiveViewOrCreate('RenderView')
    view.ViewSize = IMG_SIZE

    # --- Isometric contours ---
    setup_camera(view, CAM_ISO)
    save_contour(view, reader, 'Pressure', PRESSURE_RANGE, f"{case['name']}_iso_pressure.png", case["out"])
    save_contour(view, reader, 'Velocity', VELOCITY_RANGE, f"{case['name']}_iso_velocity.png", case["out"])

    # --- Underside contours ---
    setup_camera(view, CAM_UNDERSIDE_ISO)
    save_contour(view, reader, 'Pressure', PRESSURE_RANGE, f"{case['name']}_under_pressure.png", case["out"])
    save_contour(view, reader, 'Velocity', VELOCITY_RANGE, f"{case['name']}_under_velocity.png", case["out"])

    # --- Streamlines (seed upstream of the front of the car, spanning its width/height) ---
    seed_center = [-1000, 0, 300]     # adjust: in front of car nose
    seed_bounds = 800                  # adjust: radius to span car width/height

    setup_camera(view, CAM_ISO)
    save_streamlines(view, reader, 'Pressure', PRESSURE_RANGE, seed_center, seed_bounds,
                      f"{case['name']}_iso_streamlines_pressure.png", case["out"])
    save_streamlines(view, reader, 'Velocity', VELOCITY_RANGE, seed_center, seed_bounds,
                      f"{case['name']}_iso_streamlines_velocity.png", case["out"])

    setup_camera(view, CAM_UNDERSIDE_ISO)
    save_streamlines(view, reader, 'Pressure', PRESSURE_RANGE, seed_center, seed_bounds,
                      f"{case['name']}_under_streamlines_pressure.png", case["out"])
    save_streamlines(view, reader, 'Velocity', VELOCITY_RANGE, seed_center, seed_bounds,
                      f"{case['name']}_under_streamlines_velocity.png", case["out"])

    # --- Centerline CpT graph (front to rear) ---
    pol = PlotOverLine(Input=calc)
    pol.Point1 = [-1000, 0, 300]   # front of car, tune to your coord system
    pol.Point2 = [3500, 0, 300]    # rear of car
    pol.UpdatePipeline()
    SaveData(os.path.join(case["out"], f"{case['name']}_centerline_CpT.csv"),
             proxy=pol, WriteTimeSteps=False)

    Delete(pol); Delete(calc); Delete(reader)


for case in CASES:
    process_case(case)
    print(f"Done: {case['name']}")