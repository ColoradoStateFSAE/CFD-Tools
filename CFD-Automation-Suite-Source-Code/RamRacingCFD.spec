# RamRacingCFD.spec -- PyInstaller build
# Python 3.12 | PyQt6 | PyFluent 0.39 | Ansys Fluent 2026 R1 (v261)
#
#   pyinstaller --clean RamRacingCFD.spec
#
# Output: dist/RamRacingCFD/RamRacingCFD[.exe]
#
# The bundle is self-contained: Python runtime, PyQt6 and PyFluent are all
# included, so the target machine needs only Ansys Fluent installed.

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

block_cipher = None
PROJECT_ROOT = Path(".").resolve()

print("\n=== Ram Racing CFD build ===")

# ── Ansys packages ───────────────────────────────────────────────────────────
ansys_datas, ansys_bins, ansys_hidden = [], [], []
for package in (
    "ansys.fluent.core",
    "ansys.units",
    "ansys.api.fluent",
    "ansys.platform",
    "ansys.tools.common",
):
    try:
        datas, binaries, hidden = collect_all(package)
        ansys_datas += datas
        ansys_bins += binaries
        ansys_hidden += hidden
        print(f"  collected  {package}")
    except Exception:
        print(f"  skipped    {package}  (not installed)")

# Metadata for packages that call importlib.metadata.version() at import time.
meta_datas = []
for package in (
    "ansys-platform-instancemanagement",
    "ansys-fluent-core",
    "ansys-units",
    "ansys-api-fluent",
    "ansys-tools-filetransfer",
    "ansys-tools-common",
    "PyQt6",
    "PyQt6-Qt6",
    "PyQt6-sip",
    "grpcio",
    "numpy",
):
    try:
        meta_datas += copy_metadata(package)
    except Exception:
        pass

# ── Application data ─────────────────────────────────────────────────────────
app_datas = []
for source, destination in (
    ("assets/logo.png",                 "assets"),
    ("assets/logo.ico",                 "assets"),
    ("utils/Wheel_MRF_Setup_Guide.pdf", "utils"),
):
    if os.path.exists(source):
        app_datas.append((source, destination))
        print(f"  bundling   {source}")
    else:
        print(f"  missing    {source}  (skipped)")

# ── Hidden imports ───────────────────────────────────────────────────────────
# simtypes/__init__.py imports each simulation type explicitly, so PyInstaller
# follows them statically. They are listed here as well so a build does not
# break silently if that changes.
application_modules = [
    "core", "core.queue_manager",
    "simtypes", "simtypes.half_car",
    "gui", "gui.app", "gui.sim_editor", "gui.reference_tabs",
    "gui.settings_dialog", "gui.theme",
    "utils", "utils.refinement", "utils.resource_path", "utils.fluent_log", "utils.naming",
    "utils.results_exporter",
]

all_hidden = sorted(set(
    ansys_hidden
    + collect_submodules("grpc")
    + collect_submodules("google.protobuf")
    + application_modules
    + [
        "grpc",
        "grpc._cython",
        "grpc._cython.cygrpc",
        "google.protobuf",
        "google.protobuf.descriptor",
        "google.protobuf.descriptor_pool",
        "google.protobuf.reflection",
        "google.protobuf.symbol_database",
        "lxml",
        "lxml.etree",
    ]
))

analysis = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=ansys_bins,
    datas=meta_datas + ansys_datas + app_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "IPython",
        "notebook",
        "jupyter",
        "sphinx",
        "pytest",
        "pandas",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

icon_file = "assets/logo.ico" if os.path.exists("assets/logo.ico") else None

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="RamRacingCFD",
    icon=icon_file,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,        # stripping corrupts Windows DLLs
    upx=False,
    upx_exclude=["*"],
    console=True,       # set False once a build has been verified
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=["*"],
    name="RamRacingCFD",
)

print("=== build configured ===\n")
