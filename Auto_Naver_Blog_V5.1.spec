# -*- mode: python ; coding: utf-8 -*-
import os

icon_path = os.path.abspath('setting\\david153.ico')

a = Analysis(
    ['Auto_Naver_Blog_V5.1.py'],
    pathex=[],
    binaries=[],
    datas=[('setting', 'setting')],
    hiddenimports=[
        'PyQt6.QtCore', 
        'PyQt6.QtGui', 
        'PyQt6.QtWidgets',
        'moviepy.editor',
        'moviepy.video.io.ImageSequenceClip',
        'moviepy.video.VideoClip',
        'moviepy.video.compositing.CompositeVideoClip',
        'moviepy.audio.AudioClip',
        'moviepy.audio.io.AudioFileClip',
        'imageio',
        'imageio_ffmpeg',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'pyautogui',
    ],
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
    uac_admin=False,
)
