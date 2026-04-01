# RamRacingCFD.spec — PyInstaller build spec (PyQt6 edition)
# Supports Windows 10/11 and Rocky Linux 8
#
# Windows: pyinstaller RamRacingCFD.spec  -> dist/RamRacingCFD/RamRacingCFD.exe
# Linux:   pyinstaller RamRacingCFD.spec  -> dist/RamRacingCFD/RamRacingCFD

import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_LINUX   = sys.platform.startswith("linux")

block_cipher = None

# ── Collect all ansys packages including their data files ─────────────────────
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# Core fluent package
ansys_fc_d, ansys_fc_b, ansys_fc_h = collect_all("ansys.fluent.core")

# ansys.units — contains cfg.yaml which is required at runtime
ansys_u_d,  ansys_u_b,  ansys_u_h  = collect_all("ansys.units")

# ansys.api.fluent — protobuf generated files
ansys_a_d,  ansys_a_b,  ansys_a_h  = collect_all("ansys.api.fluent")

# ansys.platform — instance management
ansys_p_d,  ansys_p_b,  ansys_p_h  = collect_all("ansys.platform")

# grpc and protobuf — heavy dynamic import usage
grpc_h    = collect_submodules("grpc")
proto_h   = collect_submodules("google.protobuf")
nltk_h    = collect_submodules("nltk")

# Combine all collected data and binaries
all_datas    = (ansys_fc_d + ansys_u_d + ansys_a_d + ansys_p_d + [
    ('utils/Wheel_MRF_Setup_Guide.pdf', 'utils'),
    ('assets/logo.png', 'assets'),
])
all_binaries = ansys_fc_b + ansys_u_b + ansys_a_b + ansys_p_b
all_hidden   = (ansys_fc_h + ansys_u_h + ansys_a_h + ansys_p_h
                + grpc_h + proto_h + nltk_h + [
    # PyQt6
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtPrintSupport',
    'PyQt6.sip',
    # ansys specifics that collect_all can still miss
    'ansys.fluent.core.generated',
    'ansys.fluent.core.generated.solver',
    'ansys.fluent.core.generated.solver.settings_builtin',
    'ansys.fluent.core.solver.settings_builtin_bases',
    'ansys.fluent.core.solver.flobject',
    'ansys.fluent.core.variable_strategies',
    'ansys.fluent.core.variable_strategies.expr',
    'ansys.units.variable_descriptor',
    'ansys.units.quantity',
    'ansys.units.systems',
    'ansys.units._constants',
    # grpc internals
    'grpc._cython.cygrpc',
    'grpc._channel',
    'grpc._interceptor',
    'grpc.experimental',
    # protobuf
    'google.protobuf.descriptor',
    'google.protobuf.descriptor_pool',
    'google.protobuf.reflection',
    'google.protobuf.symbol_database',
    # our modules
    'simtypes.configs',
    'core.runner',
    'core.queue_manager',
    'gui.app',
    'gui.theme',
    'gui.sim_editor',
    'gui.wheel_editor',
    'utils.results_exporter',
    # misc
    'reportlab',
    'reportlab.platypus',
    'reportlab.lib.pagesizes',
    'lxml',
    'lxml.etree',
])

# ── Platform-specific Qt xcb plugins (Linux only) ────────────────────────────
if IS_LINUX:
    import subprocess, os
    try:
        qt_plugin_path = subprocess.check_output(
            ["python3", "-c",
             "from PyQt6.QtCore import QLibraryInfo; "
             "print(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))"],
            text=True
        ).strip()
        xcb_src = os.path.join(qt_plugin_path, "platforms", "libqxcb.so")
        if os.path.exists(xcb_src):
            all_binaries.append((xcb_src, "PyQt6/Qt6/plugins/platforms"))
    except Exception:
        pass

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'scipy', 'IPython',
        'notebook', 'jupyter', 'sphinx', 'pytest',
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
    name='RamRacingCFD',
    icon='assets/logo.ico' if IS_WINDOWS else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=IS_LINUX,
    upx=True,
    upx_exclude=[
        'libQt6*', 'Qt6*', 'PyQt6*',
        'qwindows.dll', 'libqxcb.so',
        '_cygrpc*.pyd', '*.so',
    ],
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
    strip=IS_LINUX,
    upx=True,
    upx_exclude=[
        'libQt6*', 'Qt6*', 'PyQt6*',
        'qwindows.dll', 'libqxcb.so',
        '_cygrpc*.pyd', '*.so',
    ],
    name='RamRacingCFD',
)
