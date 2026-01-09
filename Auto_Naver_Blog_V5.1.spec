# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, copy_metadata, collect_data_files, collect_submodules
import os

# setting 폴더 전체 포함 (ico, image 폴더, 설정 파일들)
datas = [
    ('setting', 'setting'),  # setting 폴더 전체 포함
]

binaries = []

# Hidden imports - 동적 import와 lazy loading을 위해 명시적으로 추가
hiddenimports = [
    # Core
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'selenium', 'selenium.webdriver', 'selenium.webdriver.chrome.service',
    'selenium.webdriver.common.by', 'selenium.webdriver.support.ui',
    'selenium.webdriver.support.expected_conditions',
    'selenium.common.exceptions',
    'webdriver_manager', 'webdriver_manager.chrome',
    
    # AI
    'google.generativeai', 'google.ai.generativelanguage',
    'openai',
    
    # Image/Video processing
    'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont',
    'moviepy', 'moviepy.editor', 'moviepy.video.io.VideoFileClip',
    'imageio', 'imageio_ffmpeg',
    
    # Network & Web
    'requests', 'urllib3', 'certifi',
    
    # Utils
    'traceback', 'json', 'datetime', 'random', 'time',
]

# Collect all submodules for complex packages
try:
    hiddenimports += collect_submodules('PIL')
    hiddenimports += collect_submodules('moviepy')
    hiddenimports += collect_submodules('imageio')
except Exception as e:
    print(f"Warning: Failed to collect submodules: {e}")

# Collect metadata to fix 'No package metadata was found' error
try:
    datas += copy_metadata('imageio')
    datas += copy_metadata('moviepy')
    datas += copy_metadata('google.generativeai')
    datas += copy_metadata('google.ai.generativelanguage')
    datas += copy_metadata('PIL')
    datas += copy_metadata('Pillow')
except Exception as e:
    print(f"Warning: Failed to copy metadata: {e}")

# Collect imageio_ffmpeg binaries
try:
    tmp_ret = collect_all('imageio_ffmpeg')
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]
    print("✅ imageio_ffmpeg collected")
except Exception as e:
    print(f"Warning: Failed to collect imageio_ffmpeg: {e}")

# Collect PyQt6
tmp_ret = collect_all('PyQt6')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# Collect PIL/Pillow data files
try:
    tmp_ret = collect_all('PIL')
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]
    print("✅ PIL/Pillow collected")
except Exception as e:
    print(f"Warning: Failed to collect PIL: {e}")


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
