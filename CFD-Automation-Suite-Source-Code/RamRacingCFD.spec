# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Ram Racing CFD Automation Tool
# 
# Build Windows .exe:
#   pyinstaller RamRacingCFD.spec
#
# Build Linux binary:
#   pyinstaller RamRacingCFD.spec
#
# Output will be in dist/RamRacingCFD/

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[],
    hiddenimports=[
        'ansys.fluent.core',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'threading',
        'queue',
        'logging',
        'json',
        'math',
        'copy',
        'simtypes.configs',
        'core.runner',
        'core.queue_manager',
        'gui.app',
        'gui.sim_editor',
        'gui.wheel_editor',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    strip=False,
    upx=True,
    console=False,      # Set True to show console for debug output
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows icon (add ram_racing.ico to project root if desired):
    # icon='ram_racing.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RamRacingCFD',
)
