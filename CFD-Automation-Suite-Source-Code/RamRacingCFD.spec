# RamRacingCFD.spec — Cross-platform build (Windows + Linux)
# Python 3.12 / PyQt6 / PyFluent 0.39 / Ansys 2026 R1 (v261)
#
# Build:
#   source .venv/bin/activate          (Linux)
#   .\.venv\Scripts\Activate.ps1       (Windows)
#   rm -rf build dist                  (or: rmdir /s /q build dist)
#   pyinstaller --clean RamRacingCFD.spec
#
# Run:
#   export AWP_ROOT261=/path/to/ansys_inc/v261    (Linux)
#   set AWP_ROOT261=C:\path\to\ANSYS Inc\v261     (Windows)
#   ./dist/RamRacingCFD/RamRacingCFD              (Linux)
#   dist\RamRacingCFD\RamRacingCFD.exe             (Windows)

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ── Collect ansys packages (includes all data files like cfg.yaml) ────────────
ansys_datas = []
ansys_bins  = []
ansys_hidden = []
for pkg in [
    "ansys.fluent.core",
    "ansys.units",
    "ansys.api.fluent",
    "ansys.platform",
    "ansys.tools.common",
]:
    try:
        d, b, h = collect_all(pkg)
        ansys_datas  += d
        ansys_bins   += b
        ansys_hidden += h
    except Exception:
        pass  # package not installed

# Package metadata — needed by packages that call importlib.metadata.version()
from PyInstaller.utils.hooks import copy_metadata
meta_datas = []
for pkg in [
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
    "pandas",
]:
    try:
        meta_datas += copy_metadata(pkg)
    except Exception:
        pass

grpc_h  = collect_submodules("grpc")
proto_h = collect_submodules("google.protobuf")

# ── Application data files ────────────────────────────────────────────────────
app_datas = []

# Only include files that actually exist (prevents build failure in CI)
optional_files = [
    ("assets/logo.png",                  "assets"),
    ("utils/Wheel_MRF_Setup_Guide.pdf",  "utils"),
]
for src, dest in optional_files:
    if os.path.exists(src):
        app_datas.append((src, dest))
        print(f"  Including: {src}")
    else:
        print(f"  Skipping (not found): {src}")

all_datas = meta_datas + ansys_datas + app_datas

all_binaries = ansys_bins

all_hidden = list(set(
    ansys_hidden + grpc_h + proto_h + [
        # grpc / protobuf core
        "grpc",
        "grpc._cython",
        "grpc._cython.cygrpc",
        "google.protobuf",
        "google.protobuf.descriptor",
        "google.protobuf.descriptor_pool",
        "google.protobuf.reflection",
        "google.protobuf.symbol_database",
        # our modules
        "simtypes",
        "simtypes.configs",
        "core",
        "core.runner",
        "core.queue_manager",
        "gui",
        "gui.app",
        "gui.theme",
        "gui.sim_editor",
        "gui.wheel_editor",
        "gui.settings_dialog",
        "gui.resource_path",
        "utils",
        "utils.results_exporter",
        # misc
        "lxml",
        "lxml.etree",
        "PIL",
        "PIL.Image",
    ]
))

a = Analysis(
    ["main.py"],
    pathex=[str(Path(".").resolve())],
    binaries=all_binaries,
    datas=all_datas,
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
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RamRacingCFD",
    icon=None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,            # don't strip on Windows
    upx=False,
    upx_exclude=["*"],
    console=True,           # show console for debugging — set False for release
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=["*"],
    name="RamRacingCFD",
)
