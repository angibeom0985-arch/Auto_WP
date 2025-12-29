# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

# 필요한 패키지들에 대해 모든 정보를 수집합니다.
# imageio, moviepy, proglog(로그용)를 모두 수집해야 에러가 안 납니다.
datas_io, binaries_io, hidden_io = collect_all('imageio')
datas_mv, binaries_mv, hidden_mv = collect_all('moviepy')
datas_pl, binaries_pl, hidden_pl = collect_all('proglog')
datas_if, binaries_if, hidden_if = collect_all('imageio_ffmpeg')

a = Analysis(
    ['Auto_Naver_Blog_V5.1.py'],
    pathex=[],
    binaries=binaries_io + binaries_mv + binaries_pl + binaries_if,
    datas=[('setting', 'setting')] + datas_io + datas_mv + datas_pl + datas_if,
    hiddenimports=[
        'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 
        'selenium', 'webdriver_manager', 
        'google.generativeai', 'openai',
        'moviepy.video.io.VideoFileClip',
        'moviepy.video.VideoClip',
        'moviepy.audio.AudioClip',
        'moviepy.video.compositing.CompositeVideoClip',
        'numpy', 'decorator', 'tqdm'
    ] + hidden_io + hidden_mv + hidden_pl + hidden_if,
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
    upx=False,  # UPX 압축 비활성화 (로딩 속도 개선)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='setting/david153.ico',  # 아이콘 파일 경로
)
