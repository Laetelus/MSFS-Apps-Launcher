# -*- mode: python ; coding: utf-8 -*-
# Build with build.bat (or: python -m PyInstaller --noconfirm --clean MSFSLauncher.spec)
#
# One exe, two modes (see src/app.py):
#   MSFSLauncher.exe            -> the GUI
#   MSFSLauncher.exe --service  -> the launcher that exe.xml starts
import os
from PyInstaller.utils.hooks import collect_all

datas = [('ui', 'ui')]
binaries = []
hiddenimports = ['pystray._win32']   # pystray picks its backend at run time
tmp_ret = collect_all('SimConnect')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# App icon: made by src/generate_icon.py (build.bat runs it first)
icon_file = os.path.join(SPECPATH, 'assets', 'launcher.ico')
icon = [icon_file] if os.path.exists(icon_file) else None


a = Analysis(
    ['src/app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Installed on the build PC but not used by the app (pywebview uses Edge WebView2 via
    # WinForms, not Qt; nothing imports numpy). Leaving them in adds ~120 MB.
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'qtpy', 'numpy', 'tkinter',
              'matplotlib', 'pandas', 'scipy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MSFSLauncher',
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
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MSFSLauncher',
)
