# RamRacingCFD.spec — PyInstaller build spec (PyQt6 edition)
# Supports Windows 10 and Rocky Linux 8
#
# Windows build:
#   pyinstaller RamRacingCFD.spec
#   Output: dist/RamRacingCFD/RamRacingCFD.exe
#
# Linux build (Rocky 8):
#   pyinstaller RamRacingCFD.spec
#   Output: dist/RamRacingCFD/RamRacingCFD
#   chmod +x dist/RamRacingCFD/RamRacingCFD

import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_LINUX   = sys.platform.startswith("linux")

block_cipher = None

# ── Platform-specific Qt xcb plugins needed on Linux ─────────────────────────
# On Rocky 8, PyInstaller sometimes misses these — list them explicitly.
linux_binaries = []
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
            linux_binaries.append((xcb_src, "PyQt6/Qt6/plugins/platforms"))
    except Exception:
        pass  # Will still work if Qt is installed system-wide

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=linux_binaries,
    datas=[
        ('utils/Wheel_MRF_Setup_Guide.pdf', 'utils'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'PyQt6.QtPrintSupport',
        'ansys.fluent.core',
        'grpc',
        'grpc._cython.cygrpc',
        'reportlab',
        'reportlab.platypus',
        'reportlab.lib.pagesizes',
        'simtypes.configs',
        'core.runner',
        'core.queue_manager',
        'gui.app',
        'gui.theme',
        'gui.sim_editor',
        'gui.wheel_editor',
        'utils.results_exporter',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'scipy', 'IPython',
        'notebook', 'jupyter', 'sphinx',
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
    debug=False,
    bootloader_ignore_signals=False,
    strip=IS_LINUX,
    upx=True,
    upx_exclude=[
        'libQt6*', 'Qt6*', 'PyQt6*',
        'qwindows.dll', 'libqxcb.so',
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
    ],
    name='RamRacingCFD',
)
