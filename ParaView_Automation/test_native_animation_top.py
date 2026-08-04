# test_native_animation_top.py
# Standalone test of make_sweep_movie_native on the TOP view.
# Run with: pvpython test_native_animation_top.py

from paraview.simple import *
import batch_postprocess as bp   # must be in the same folder

# ---- EDIT THESE ----
CASE_FILE = r"C:\Users\Hayes Dodson\Downloads\data\FLTG-Setup-Output.encas"
OUT_DIR = r"C:\Users\Hayes Dodson\Downloads\test"
# ---------------------

VIEW_NAME = "top"
FIELD_KEY = "static_pressure"

print("Building pipeline...")
sources = bp.build_pipeline(CASE_FILE)
fluid_source = sources["fluid"]

view = GetActiveViewOrCreate('RenderView')
view.ViewSize = bp.IMG_SIZE

print(f"Running make_sweep_movie_native (view={VIEW_NAME}, field={FIELD_KEY})...")

bp.make_sweep_movie_native(
    fluid_source,
    VIEW_NAME,
    view,
    bp.FIELDS[FIELD_KEY],
    bp.WASH_BOUNDS,
    OUT_DIR,
    "test_case",
    FIELD_KEY,
)

print("Done. Check:", OUT_DIR + r"\movies_mp4\test_case_" + VIEW_NAME + "_" + FIELD_KEY + "_native.mp4")