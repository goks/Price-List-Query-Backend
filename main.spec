# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


root = Path.cwd()
data_pairs = []
for relative_path in ("GUI", "icons", "service-account", "fonts"):
    source = root / relative_path
    if source.exists():
        data_pairs.append((str(source), relative_path))


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=data_pairs,
    hiddenimports=["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtQml", "shiboken6"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Price List Update",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icons\\Price List Backend Quenry v2.ico",
)
