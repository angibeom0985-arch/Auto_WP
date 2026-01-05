# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [('setting/david153.ico', 'setting')]
binaries = []
hiddenimports = ['PyQt6', 'selenium', 'google.generativeai', 'openai', 'moviepy', 'imageio', 'imageio_ffmpeg']

# Collect metadata to fix 'No package metadata was found' error
try:
    datas += copy_metadata('imageio')
    datas += copy_metadata('moviepy')
    datas += copy_metadata('google.generativeai')
    datas += copy_metadata('google.ai.generativelanguage')
except Exception as e:
    print(f"Warning: Failed to copy metadata: {e}")

tmp_ret = collect_all('PyQt6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['Auto_Naver_Blog_V5.1.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5'],
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
    name='Auto_Naver_Blog_V5.1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='setting/david153.ico',
)
