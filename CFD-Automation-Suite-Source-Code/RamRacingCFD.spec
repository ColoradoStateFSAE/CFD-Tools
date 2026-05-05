# RamRacingCFD.spec — Rocky Linux 8.10 build
# Python 3.12 / PyQt6 / PyFluent 0.38 / Ansys 2025 R2 (v252)
#
# Build:
#   source .venv/bin/activate
#   rm -rf build dist
#   pyinstaller RamRacingCFD.spec
#   chmod +x dist/RamRacingCFD/RamRacingCFD
#
# Run:
#   export AWP_ROOT252=/home/xeongold/ansys_inc/v252
#   ./dist/RamRacingCFD/RamRacingCFD

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ── Collect ansys packages (includes all data files like cfg.yaml) ────────────
ansys_fc_d, ansys_fc_b, ansys_fc_h = collect_all("ansys.fluent.core")
ansys_u_d,  ansys_u_b,  ansys_u_h  = collect_all("ansys.units")
ansys_a_d,  ansys_a_b,  ansys_a_h  = collect_all("ansys.api.fluent")
ansys_p_d,  ansys_p_b,  ansys_p_h  = collect_all("ansys.platform")
ansys_t_d,  ansys_t_b,  ansys_t_h  = collect_all("ansys.tools.common")

# Package metadata — needed by packages that call importlib.metadata.version()
# at import time (ansys.platform.instancemanagement does this)
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
        pass  # package not installed — skip

grpc_h  = collect_submodules("grpc")
proto_h = collect_submodules("google.protobuf")
nltk_h  = collect_submodules("nltk")

all_datas = (
    meta_datas
    + ansys_fc_d + ansys_u_d + ansys_a_d + ansys_p_d + ansys_t_d + [
        ("utils/Wheel_MRF_Setup_Guide.pdf", "utils"),
        ("assets/logo.png",                 "assets"),
    ]
)

all_binaries = ansys_fc_b + ansys_u_b + ansys_a_b + ansys_p_b + ansys_t_b

# ── Rocky 8 specific: bundle xcb platform plugin ─────────────────────────────
# Rocky 8 ships an older libxcb — the one bundled with PyQt6 may not load
# against the system xcb. We force-include the Qt xcb plugin from the venv
# and also bundle libatomic which Rocky 8 sometimes can't find.
try:
    import subprocess
    qt_plugin_path = subprocess.check_output(
        [sys.executable, "-c",
         "from PyQt6.QtCore import QLibraryInfo; "
         "print(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))"],
        text=True
    ).strip()

    # Platform plugin
    xcb = os.path.join(qt_plugin_path, "platforms", "libqxcb.so")
    if os.path.exists(xcb):
        all_binaries.append((xcb, "PyQt6/Qt6/plugins/platforms"))
        print(f"spec: bundled {xcb}")

    # Wayland plugin (fallback if xcb unavailable)
    wayland = os.path.join(qt_plugin_path, "platforms", "libqwayland-generic.so")
    if os.path.exists(wayland):
        all_binaries.append((wayland, "PyQt6/Qt6/plugins/platforms"))

    # xcb integration plugin
    xcb_qpa_dir = os.path.join(qt_plugin_path, "xcbglintegrations")
    if os.path.isdir(xcb_qpa_dir):
        for f in os.listdir(xcb_qpa_dir):
            all_binaries.append(
                (os.path.join(xcb_qpa_dir, f), "PyQt6/Qt6/plugins/xcbglintegrations")
            )

    # Qt image format plugins
    img_dir = os.path.join(qt_plugin_path, "imageformats")
    if os.path.isdir(img_dir):
        for f in os.listdir(img_dir):
            if f.endswith(".so") and "pdf" not in f:  # skip libqpdf (needs libatomic)
                all_binaries.append(
                    (os.path.join(img_dir, f), "PyQt6/Qt6/plugins/imageformats")
                )
except Exception as e:
    print(f"spec WARNING: Qt plugin collection failed: {e}")

# libatomic — required by Qt PDF plugin, not always present on Rocky 8
for lib_path in [
    "/usr/lib64/libatomic.so.1",
    "/lib64/libatomic.so.1",
    "/usr/lib/libatomic.so.1",
]:
    if os.path.exists(lib_path):
        all_binaries.append((lib_path, "."))
        print(f"spec: bundled {lib_path}")
        break

all_hidden = (
    ansys_fc_h + ansys_u_h + ansys_a_h + ansys_p_h + ansys_t_h
    + grpc_h + proto_h + nltk_h
    + [
        # PyQt6
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtPrintSupport",
        "PyQt6.sip",
        # ansys internals that collect_all can miss
        "ansys.fluent.core.generated",
        "ansys.fluent.core.generated.solver",
        "ansys.fluent.core.generated.solver.settings_builtin",
        "ansys.fluent.core.generated.datamodel_252",
        "ansys.fluent.core.solver.settings_builtin_bases",
        "ansys.fluent.core.solver.flobject",
        "ansys.fluent.core.variable_strategies",
        "ansys.fluent.core.variable_strategies.expr",
        "ansys.units.variable_descriptor",
        "ansys.units.quantity",
        "ansys.units.systems",
        "ansys.units._constants",
        # grpc
        "grpc._cython.cygrpc",
        "grpc._channel",
        "grpc._interceptor",
        "grpc.experimental",
        # protobuf
        "google.protobuf.descriptor",
        "google.protobuf.descriptor_pool",
        "google.protobuf.reflection",
        "google.protobuf.symbol_database",
        # our modules
        "simtypes.configs",
        "core.runner",
        "core.queue_manager",
        "gui.app",
        "gui.theme",
        "gui.sim_editor",
        "gui.wheel_editor",
        "utils.results_exporter",
        # misc
        "reportlab",
        "reportlab.platypus",
        "reportlab.lib.pagesizes",
        "lxml",
        "lxml.etree",
        "PIL",
        "PIL.Image",
    ]
)

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
        # scipy pulls in a lot on Rocky 8 — exclude unless needed
        # "scipy",
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
    strip=True,
    upx=False,
    upx_exclude=["*"],   # exclude ALL files from UPX — belt and suspenders
    console=False,
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
    strip=True,
    upx=False,
    upx_exclude=["*"],   # exclude ALL files from UPX
    name="RamRacingCFD",
)

