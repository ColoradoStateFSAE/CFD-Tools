# RamRacingCFD.spec — cross-platform PyInstaller build
# Python 3.12 / PyQt6 / PyFluent 0.39 / Ansys Fluent 2026 R1 (v261)
#
# Build:
#   pyinstaller --clean RamRacingCFD.spec
#
# Output:
#   dist/RamRacingCFD/RamRacingCFD[.exe]
#   dist/RamRacingCFD/journals/           <- editable, next to the exe
#
# The journals live BESIDE the executable rather than inside _internal so the
# aero team can re-record them after an Ansys upgrade without rebuilding.
# utils.resource_path.journals_dir() looks there first.

import os
import shutil
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

block_cipher = None
PROJECT_ROOT = Path(".").resolve()

# ── Ansys packages ───────────────────────────────────────────────────────────
ansys_datas, ansys_bins, ansys_hidden = [], [], []
for pkg in (
    "ansys.fluent.core",
    "ansys.units",
    "ansys.api.fluent",
    "ansys.platform",
    "ansys.tools.common",
):
    try:
        d, b, h = collect_all(pkg)
        ansys_datas  += d
        ansys_bins   += b
        ansys_hidden += h
    except Exception:
        pass  # not installed — skip

# Metadata for packages that call importlib.metadata.version() at import time
meta_datas = []
for pkg in (
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
):
    try:
        meta_datas += copy_metadata(pkg)
    except Exception:
        pass

# ── Application data ─────────────────────────────────────────────────────────
app_datas = []
for src, dest in (
    ("assets/logo.png",                 "assets"),
    ("assets/logo.ico",                 "assets"),
    ("utils/Wheel_MRF_Setup_Guide.pdf", "utils"),
):
    if os.path.exists(src):
        app_datas.append((src, dest))
        print(f"  bundling  {src}")
    else:
        print(f"  skipping  {src}  (not found)")

# Journals are bundled as a fallback; the editable copy is placed beside the
# executable after COLLECT, below.
journal_count = 0
journals_root = PROJECT_ROOT / "journals"
if journals_root.is_dir():
    for path in journals_root.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".md"):
            rel_dir = path.parent.relative_to(PROJECT_ROOT)
            app_datas.append((str(path), str(rel_dir)))
            journal_count += 1
    print(f"  bundling  journals/  ({journal_count} files)")
else:
    print("  WARNING   journals/ not found — the build will not be able to "
          "mesh or solve")

# ── Hidden imports ───────────────────────────────────────────────────────────
all_hidden = sorted(set(
    ansys_hidden
    + collect_submodules("grpc")
    + collect_submodules("google.protobuf")
    + [
        # grpc / protobuf internals
        "grpc",
        "grpc._cython",
        "grpc._cython.cygrpc",
        "google.protobuf",
        "google.protobuf.descriptor",
        "google.protobuf.descriptor_pool",
        "google.protobuf.reflection",
        "google.protobuf.symbol_database",
        # application packages
        "core",
        "core.runner",
        "core.queue_manager",
        "core.journal_params",
        "core.journal_runner",
        "simtypes",
        "simtypes.configs",
        "gui",
        "gui.app",
        "gui.sim_editor",
        "gui.wheel_editor",
        "gui.settings_dialog",
        "gui.theme",
        "utils",
        "utils.resource_path",
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
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_file = "assets/logo.ico" if os.path.exists("assets/logo.ico") else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RamRacingCFD",
    icon=icon_file,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,          # stripping corrupts Windows DLLs
    upx=False,
    upx_exclude=["*"],
    console=True,         # set False once the build is verified
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

# ── Editable journals beside the executable ──────────────────────────────────
# PyInstaller 6 puts bundled data under _internal/. Journals are re-recorded
# by the team, so a second copy goes in the dist root where journals_dir()
# finds it first and where it can be edited without a rebuild.
if journals_root.is_dir():
    dist_journals = PROJECT_ROOT / "dist" / "RamRacingCFD" / "journals"
    if dist_journals.exists():
        shutil.rmtree(dist_journals)
    shutil.copytree(
        journals_root,
        dist_journals,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    print(f"\n  editable journals -> {dist_journals}")
