# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[('ProcessCapture.exe', '.')],
    datas=[('assets/dslight.ico', 'assets'), ('assets/diagnostic-bg-120.png', 'assets'), ('assets/diagnostic-bg-160.png', 'assets'), ('assets/diagnostic-bg-240.png', 'assets'), ('assets/diagnostic-bg-320.png', 'assets'), ('assets/ds5-light-logo.svg', 'assets'), ('assets/dualsense-controls.svg', 'assets'), ('assets/diagnostic-controller.svg', 'assets'), ('vendor/ds5audio_original.py', 'vendor'), ('vendor/LICENSE-Studio.txt', 'vendor'), ('vendor/tksvg0.16/pkgIndex.tcl', 'vendor/tksvg0.16'), ('vendor/tksvg0.16/tksvg016t.dll', 'vendor/tksvg0.16')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'torch', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DS5Light',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/dslight.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DS5Light',
)
