#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto WP multi-site - 워드프레스 자동 포스팅 by 데이비
"""

import sys
import os
import json
import time
import random
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path
import shutil

# GUI 라이브러리
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QScrollArea,
    QGroupBox, QGridLayout, QSpinBox, QComboBox, QCheckBox, QListWidget,
    QFileDialog, QMessageBox, QProgressBar, QSplitter, QFrame,
    QListWidgetItem, QDialog, QDialogButtonBox, QFormLayout, QProgressDialog,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QFont, QPixmap, QIcon, QPalette, QColor

class PostingWorker(QThread):
    """포스팅 작업 스레드"""
    status_update = pyqtSignal(str)
    posting_complete = pyqtSignal()
    single_posting_complete = pyqtSignal()  # 개별 포스팅 완료 신호 추가
    error_occurred = pyqtSignal(str)
    
    def __init__(self, config_manager, sites_data, start_site_id="all"):
        super().__init__()
        self.config_manager = config_manager
        self.sites_data = sites_data
        self.start_site_id = start_site_id
        self.is_running = True
        self.is_paused = False
        self._force_stop = False  # 강제 중지 플래그 추가
    
    def stop(self):
        """포스팅 강제 중지"""
        print("🛑 [WORKER] 포스팅 워커 중지 요청됨")
        self.is_running = False
        self._force_stop = True
        # 스레드가 종료될 때까지 기다림
        self.wait(5000)  # 최대 5초 대기
        print("🛑 [WORKER] 포스팅 워커 중지 완료")
    
    def safe_emit_status(self, message):
        """안전한 상태 업데이트 발송 - 터미널과 GUI 동시 출력"""
        try:
            # 터미널과 GUI에 동일한 메시지 출력
            print(message, flush=True)
            self.status_update.emit(message)
            self.msleep(10)  # 10ms 대기
                
        except Exception as e:
            print(f"[ERROR] 신호 발송 실패: {e}")
            sys.stdout.flush()
        
    def run(self):
        """포스팅 작업 실행 - 모든 키워드가 소진될 때까지 반복"""
        try:
            # 전체 라운드 카운터
            round_count = 0
            
            # 시작 사이트 결정
            start_index = 0
            if self.start_site_id != "all":
                # 특정 사이트부터 시작
                for idx, site in enumerate(self.sites_data):
                    if site.get("id") == self.start_site_id or str(idx) == str(self.start_site_id):
                        start_index = idx
                        self.safe_emit_status(f"▶️ {site.get('name', 'Unknown')} 시작")
                        break
            
            # 무한 반복: 모든 사이트의 키워드가 소진될 때까지 계속
            while self.is_running and not self._force_stop:
                try:
                    round_count += 1
                    self.safe_emit_status(f"🔄 라운드 {round_count} 시작 - 모든 사이트 순회")
                    
                    # 강제 중지 체크
                    if self._force_stop:
                        self.safe_emit_status("⏹️ 강제 중지")
                        return
                    
                    # 이번 라운드에서 포스팅된 사이트 카운터
                    posted_sites_count = 0
                    
                    # 시작 사이트부터 순회 (라운드 1에서만 적용)
                    sites_to_process = self.sites_data[start_index:] + self.sites_data[:start_index] if round_count == 1 else self.sites_data
                    
                    # 모든 사이트 순회
                    for i, site in enumerate(sites_to_process):
                        if not self.is_running or self._force_stop:
                            print("⏹️ 포스팅 중지")
                            self.safe_emit_status("⏹️ 포스팅 중지")
                            return
                            
                        # 일시정지 확인
                        while self.is_paused and self.is_running and not self._force_stop:
                            print("⏸️ 일시정지")
                            self.safe_emit_status("⏸️ 일시정지")
                            self.msleep(1000)  # 1초 대기
                            
                        if not self.is_running:
                            print("⏹️ 포스팅 중지")
                            self.safe_emit_status("⏹️ 포스팅 중지")
                            return
                        
                        site_name = site.get('name', 'Unknown')
                        self.safe_emit_status(f"📍 라운드 {round_count} - {site_name} ({i+1}/{len(self.sites_data)}) 포스팅 시작")
                        self.safe_emit_status("=====================================================================================")
                        
                        # 이 사이트에 사용 가능한 키워드가 있는지 확인
                        try:
                            available_keywords = self.config_manager.get_site_keywords(site)
                            if not available_keywords:
                                self.safe_emit_status(f"⚠️ {site_name}: 사용 가능한 키워드 없음 - 스킵")
                                continue
                        except Exception as keyword_error:
                            self.safe_emit_status(f"❌ {site_name}: 키워드 조회 오류 - 다음 사이트로 계속")
                            continue
                        
                        # 실제 포스팅 작업 수행
                        try:
                            self.process_site_posting(site)
                            posted_sites_count += 1
                            self.safe_emit_status(f"✅ {site_name} 포스팅 완료")
                            self.safe_emit_status("=====================================================================================")
                        except Exception as site_error:
                            error_msg = f"❌ {site_name}: 포스팅 오류 - {str(site_error)}"
                            self.safe_emit_status(error_msg)
                            continue
                        
                        # 사이트 간 대기 (마지막 사이트가 아닌 경우)
                        if i < len(self.sites_data) - 1:
                            try:
                                wait_time = self.config_manager.data["global_settings"].get("default_wait_time", "47~50")
                                if "~" in wait_time:
                                    import random
                                    min_time, max_time = map(int, wait_time.split("~"))
                                    delay = random.randint(min_time, max_time)
                                else:
                                    delay = int(wait_time) if wait_time.isdigit() else 50
                            except:
                                delay = 50  # 기본값
                                
                            # 대기 중에도 중지/일시정지 체크
                            for j in range(delay):
                                if not self.is_running:
                                    return
                                while self.is_paused and self.is_running:
                                    self.msleep(1000)
                                if not self.is_running:
                                    return
                                    
                                self.msleep(1000)
                    
                    # 이번 라운드 완료 후 체크
                    if posted_sites_count == 0:
                        # 어떤 사이트도 포스팅하지 못했으면 모든 키워드가 소진됨
                        self.safe_emit_status("🎉 모든 사이트의 키워드가 소진되었습니다!")
                        self.safe_emit_status(f"📊 총 {round_count}라운드 완료! 포스팅 작업 종료")
                        break
                    else:
                        self.safe_emit_status(f"🏁 라운드 {round_count} 완료 - {posted_sites_count}개 사이트 포스팅 성공")
                        
                        # 다음 라운드를 위한 일반 대기 (사이트 간 간격과 동일)
                        try:
                            wait_time = self.config_manager.data["global_settings"].get("default_wait_time", "47~50")
                            
                            # 범위 형태 처리 (예: "47~50")
                            if "~" in wait_time or "-" in wait_time:
                                try:
                                    separator = "~" if "~" in wait_time else "-"
                                    min_time, max_time = map(int, wait_time.split(separator))
                                    delay = random.randint(min_time, max_time)
                                except ValueError:
                                    delay = 50  # 기본값
                            else:
                                delay = int(wait_time) if wait_time.isdigit() else 50
                        except:
                            delay = 50  # 기본값
                        
                        # 대기 (라운드 간에도 일반 포스팅 간격 사용)
                        for j in range(delay):
                            if not self.is_running:
                                return
                            while self.is_paused and self.is_running:
                                self.msleep(1000)
                            if not self.is_running:
                                return
                                
                            self.msleep(1000)
                        
                except Exception as round_error:
                    self.safe_emit_status(f"❌ 라운드 {round_count} 오류 - 다음 라운드 진행")
                    # 라운드 오류가 발생해도 계속 진행
                    import time
                    time.sleep(5)  # 5초 대기 후 다음 라운드 진행
                        
            if self.is_running:
                self.safe_emit_status("🎉 모든 키워드 사용 완료!")
                self.posting_complete.emit()
                
        except KeyboardInterrupt:
            print("⏹️ 사용자에 의해 중단되었습니다.")
            self.safe_emit_status("⏹️ 사용자 중단")
            return
        except Exception as e:
            print(f"❌ PostingWorker 중요 오류 발생: {str(e)}")
            print(f"� 10초 후 자동 재시작을 시도합니다")
            self.safe_emit_status("❌ 시스템 오류 - 10초 후 재시작 시도")
            
            # 10초 대기 후 재시작 시도
            for i in range(10, 0, -1):
                if not self.is_running:
                    return
                self.safe_emit_status(f"🔄 재시작까지 {i}초 남음")
                import time
                time.sleep(1)
            
            # 재시작 시도
            if self.is_running:
                self.safe_emit_status("🔄 재시작 중")
                try:
                    self.run()  # 재귀적으로 재시작
                except:
                    print("❌ 재시작 실패 - 포스팅을 종료합니다.")
                    self.safe_emit_status("❌ 재시작 실패")
                    self.error_occurred.emit(str(e))
            
    def process_site_posting(self, site):
        """개별 사이트 포스팅 처리 - 새로운 워크플로우 적용"""
        try:
            site_name = site.get('name', 'Unknown')
            site_id = site.get('id')
            site_url = site.get('url', '')
            
            # 🔒 포스팅 시작 상태 저장 (진행 중으로 표시)
            self.config_manager.save_posting_state(site_id, site_url, in_progress=True)
            
            # 키워드 가져오기 (사용 가능한 키워드만)
            keywords = self.config_manager.get_site_keywords(site)
            if not keywords:
                self.status_update.emit(f"⚠️ {site_name}: 키워드 없음")
                # 포스팅 실패 상태 저장 (완료됨으로 표시하여 다음 사이트로 이동)
                self.config_manager.save_posting_state(site_id, site_url, in_progress=False)
                return
                
            keyword = keywords[0]  # 첫 번째 키워드 선택
            self.status_update.emit(f"🔑 선택된 키워드: '{keyword}'")
            
            # 🔒 중요: 키워드 선택 후 바로 백업 정보 저장
            keyword_file = site.get('keyword_file')
            if keyword_file:
                print(f"📋 {site_name}: 키워드 파일 '{keyword_file}' 확인")
            else:
                print(f"⚠️ {site_name}: 키워드 파일 설정이 없습니다.")
                self.status_update.emit(f"⚠️ {site_name}: 키워드 파일 미설정")
                return
            
            # AI 설정 가져오기
            ai_provider = self.config_manager.data["global_settings"].get("default_ai", "gemini")
            posting_mode = self.config_manager.data["global_settings"].get("posting_mode", "수익용")
            
            # ContentGenerator 인스턴스 생성
            from datetime import datetime
            config_data = {
                'openai_api_key': self.config_manager.data.get("api_keys", {}).get("openai", ""),
                'gemini_api_key': self.config_manager.data.get("api_keys", {}).get("gemini", "")
            }
            
            def log_func(message):
                """로그 함수"""
                try:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
                    sys.stdout.flush()  # 즉시 콘솔 출력
                    self.status_update.emit(message)
                except Exception as log_error:
                    print(f"[LOG ERROR] {log_error}")
                    # 로그 함수 오류가 발생해도 계속 진행
                    pass
            
            # MainWindow 인스턴스를 auto_wp_instance로 전달 (config_manager 접근용)
            class MockAutoWP:
                def __init__(self, config_manager, worker_thread):
                    self.config_manager = config_manager
                    self.current_ai_provider = config_manager.data.get("global_settings", {}).get("default_ai", "gemini")
                    self.posting_mode = config_manager.data.get("global_settings", {}).get("posting_mode", "수익용")
                    # Worker Thread 참조 저장
                    self.worker_thread = worker_thread
                
                @property
                def is_posting(self):
                    # Worker Thread의 상태를 실시간으로 반환
                    return self.worker_thread.is_running and not self.worker_thread._force_stop
                
                @property
                def is_paused(self):
                    return self.worker_thread.is_paused
            
            mock_auto_wp = MockAutoWP(self.config_manager, self)
            content_generator = ContentGenerator(config_data, log_func, mock_auto_wp)
            
            # ContentGenerator가 worker thread 상태를 실시간으로 체크할 수 있게 설정
            content_generator.worker_thread = self
            # ContentGenerator의 포스팅 상태를 True로 설정
            content_generator.is_posting = True
            # AI 제공자 설정 추가 (명시적으로 설정)
            content_generator.current_ai_provider = ai_provider
            
            # API 재초기화 강제 실행 (Worker Thread에서 config_manager 접근)
            content_generator.config_manager = self.config_manager
            content_generator.initialize_apis()
            
            # 현재 처리 중인 사이트 정보를 전달
            content_generator.set_current_site(site)
            
            # 콘텐츠 생성
            title, content, thumbnail_path = content_generator.generate_content(keyword)
            
            if not self.is_running:
                print(f"⏹️ {site_name}: 포스팅이 중지되었습니다. 키워드 '{keyword}' 보존됨")
                return
                
            if title and content:
                # 워드프레스에 포스팅
                result = content_generator.post_to_wordpress(site, title, content, thumbnail_path)
                
                if result and result.get('success'):
                    # 🔥 중요: 포스팅 성공 후에만 키워드를 used 파일로 이동
                    try:
                        self.status_update.emit(f"🔄 키워드 '{keyword}' 처리 완료 파일로 이동")
                        keyword_moved = self.move_keyword_to_used(keyword, site)
                        if not keyword_moved:
                            self.status_update.emit(f"⚠️ 포스팅 완료, 키워드 이동 실패")
                    except Exception as keyword_error:
                        self.status_update.emit(f"⚠️ 포스팅 완료, 키워드 처리 오류")
                    
                    # 🔒 포스팅 성공 시 완료 상태 저장 (다음 사이트로 이동)
                    self.config_manager.save_posting_state(site_id, site_url, in_progress=False)
                    self.status_update.emit(f"✅ 다음 프로그램 실행 시 {site_name} 다음 사이트부터 시작됩니다")
                    
                    # 개별 포스팅 완료 신호 발송 (카운트다운 시작용)
                    self.single_posting_complete.emit()
                        
                else:
                    self.status_update.emit(f"❌ {site_name}: 워드프레스 포스팅 실패 - 키워드 보존")
                    # 🔒 포스팅 실패 시 진행 중 상태 유지 (재시작 시 같은 사이트에서 재시작)
                    self.config_manager.save_posting_state(site_id, site_url, in_progress=True)
            else:
                self.status_update.emit(f"❌ {site_name}: 콘텐츠 생성 실패 - 키워드 보존")
                # 🔒 콘텐츠 생성 실패 시 진행 중 상태 유지
                self.config_manager.save_posting_state(site_id, site_url, in_progress=True)
            
        except Exception as e:
            self.status_update.emit(f"❌ {site_name} 예외 발생 - 키워드 보존됨")
            # 🔒 예외 발생 시 진행 중 상태 유지 (재시작 시 같은 사이트에서 재시작)
            self.config_manager.save_posting_state(site_id, site_url, in_progress=True)
            # 예외가 발생해도 키워드를 보존하고 다음 사이트로 진행

    def move_keyword_to_used(self, keyword, site):
        """사용한 키워드를 used 파일로 이동 - 'used_' 접두사 붙인 파일로 이동"""
        try:
            keyword_file = site.get('keyword_file')
            if not keyword_file:
                return False
                
            base_path = get_base_path()
            keywords_path = os.path.join(base_path, "keywords", keyword_file)
            
            # 'used_' 접두사가 붙은 파일명 생성 (예: ai-news_keywords.txt -> used_ai-news_keywords.txt)
            used_filename = f"used_{keyword_file}"
            used_path = os.path.join(base_path, "keywords", used_filename)
            
            # 원본 파일이 존재하는지 확인
            if not os.path.exists(keywords_path):
                return False
            
            # 원본 파일에서 키워드 제거
            with open(keywords_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 키워드 제거 (정확히 일치하는 라인만)
            updated_lines = []
            keyword_found = False
            for line in lines:
                if line.strip() == keyword.strip():
                    keyword_found = True
                    print(f"🔍 키워드 '{keyword}' 발견하여 제거 준비")
                    continue
                updated_lines.append(line)
            
            if keyword_found:
                # 원본 파일 업데이트 (백업 후 진행)
                backup_path = keywords_path + ".backup"
                import shutil
                shutil.copy2(keywords_path, backup_path)
                
                try:
                    with open(keywords_path, 'w', encoding='utf-8') as f:
                        f.writelines(updated_lines)
                    
                    # used 파일에 키워드 추가 (파일이 없으면 생성)
                    with open(used_path, 'a', encoding='utf-8') as f:
                        f.write(f"{keyword.strip()}\n")
                    
                    # 백업 파일 삭제 (성공시)
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    
                    print(f"✅ 키워드 '{keyword}' 이동 완료: {keyword_file} -> {used_filename}")
                    return True
                    
                except Exception as file_error:
                    # 복원 시도
                    if os.path.exists(backup_path):
                        shutil.copy2(backup_path, keywords_path)
                        os.remove(backup_path)
                        print(f"� 키워드 파일 복원 완료")
                    
                    print(f"❌ 파일 쓰기 오류로 키워드 이동 실패: {file_error}")
                    return False
            else:
                print(f"⚠️ 키워드 '{keyword}'를 {keyword_file}에서 찾을 수 없습니다.")
                return False
                
        except Exception as e:
            print(f"❌ 키워드 이동 중 예외 발생: {e}")
            return False
            
    def pause(self):
        """일시정지"""
        self.is_paused = True
        
    def resume(self):
        """재개"""
        self.is_paused = False
        
    def stop(self):
        """중지"""
        self.is_running = False
        self.is_paused = False

# 기존 라이브러리들
import requests
import urllib.parse
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import re
import subprocess

# AI API 라이브러리들
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

def install_package(package_name):
    """패키지 동적 설치"""
    try:
        # 먼저 패키지가 이미 설치되어 있는지 확인
        try:
            __import__(package_name.split('==')[0].replace('-', '_'))
            print(f"📦 {package_name} 이미 설치되어 있음")
            return True
        except ImportError:
            pass
        
        import subprocess
        import sys
        print(f"📦 {package_name} 설치 시도 중")
        
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", package_name, "--user", "--quiet"
        ], capture_output=True, text=True, timeout=120, check=False)
        
        if result.returncode == 0:
            print(f"✅ {package_name} 설치 성공!")
            return True
        else:
            print(f"❌ {package_name} 설치 실패: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ {package_name} 설치 중 오류: {e}")
        return False

def try_import_gemini():
    """Gemini API 동적 import 시도"""
    try:
        import google.generativeai as genai
        print("✅ google-generativeai 라이브러리 로드 성공")
        return True, genai
    except ImportError as e:
        print(f"❌ google-generativeai 라이브러리 없음: {e}")
        
        # 동적 설치 시도
        if install_package("google-generativeai"):
            try:
                # 설치 후 다시 import 시도
                import importlib
                import google.generativeai as genai
                print("✅ google-generativeai 설치 후 로드 성공!")
                return True, genai
            except Exception as reload_error:
                print(f"❌ 설치 후 로드 실패: {reload_error}")
                return False, None
        else:
            return False, None
    except Exception as e:
        print(f"❌ google-generativeai 라이브러리 예상치 못한 오류: {e}")
        return False, None

# Gemini API 동적 로드
GEMINI_AVAILABLE, genai = try_import_gemini()

# WordPress API
try:
    import pandas as pd
except ImportError:
    pd = None

def get_base_path():
    """실행 파일의 기본 경로 반환 (EXE/PY 모두 지원)"""
    if getattr(sys, 'frozen', False):  # PyInstaller로 빌드된 EXE인 경우
        return os.path.dirname(sys.executable)
    else:  # 일반 Python 스크립트인 경우
        return os.path.dirname(os.path.abspath(__file__))

def log_to_file(message):
    """EXE 실행 시 로그 파일에 기록"""
    try:
        if getattr(sys, 'frozen', False):  # EXE 실행 시에만
            log_file = os.path.join(get_base_path(), "debug.log")
            with open(log_file, "a", encoding="utf-8") as f:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {message}\n")
                f.flush()
    except Exception:
        pass  # 로그 실패 시 무시

def get_requests_session():
    """최적화된 requests 세션 생성"""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=3, pool_maxsize=5, max_retries=0)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Auto-WP/1.0',
        'Connection': 'keep-alive',
    })
    return session

# 설정 파일 경로
SETTING_FILE = os.path.join(get_base_path(), "setting.json")

# 기본 디렉토리 생성
for directory in ['keywords', 'thumbnails', 'fonts', 'prompts', 'output']:
    dir_path = os.path.join(get_base_path(), directory)
    os.makedirs(dir_path, exist_ok=True)

# 다크 모드 색상 테마 (Nord Theme 기반)
COLORS = {
    'background': '#2E3440',   # 메인 배경
    'surface': '#3B4252',      # 서피스 (입력창 등)
    'surface_light': '#434C5E', # 밝은 서피스
    'surface_dark': '#2E3440', # 어두운 서피스
    'primary': '#81A1C1',      # 포인트 색상
    'primary_hover': '#88C0D0', # 포인트 호버
    'secondary': '#5E81AC',    # 보조 색상
    'accent': '#5E81AC',       # 액센트
    'success': '#A3BE8C',      # 성공 (녹색)
    'warning': '#EBCB8B',      # 경고 (노란색)
    'warning_hover': '#D2B773', # 경고 호버
    'danger': '#BF616A',       # 위험 (빨간색)
    'info': '#88C0D0',         # 정보 (청록색)
    'info_hover': '#8FBCBB',   # 정보 호버
    'text': '#FFFFFF',         # 기본 텍스트 (흰색으로 변경)
    'text_secondary': '#FFFFFF', # 보조 텍스트 (흰색으로 변경)
    'text_muted': '#FFFFFF',   # 회색 텍스트 (흰색으로 변경)
    'border': '#4C566A',       # 테두리
    'hover': '#434C5E'         # 호버 배경
}

# WordPress 테마 색상
WORDPRESS_COLORS = {
    'primary_blue': '#0073aa',      # WordPress 기본 파란색
    'dark_blue': '#005177',         # 어두운 파란색
    'light_blue': '#00a0d2',        # 밝은 파란색
    'background_dark': '#1e1e1e',   # 어두운 배경
    'surface_dark': '#2d2d2d',      # 어두운 서피스
    'surface_light': '#383838',     # 밝은 서피스
    'text_primary': '#ffffff',      # 기본 텍스트
    'text_secondary': '#cccccc',    # 보조 텍스트
    'success': '#46b450',           # 성공 색상
    'warning': '#ffb900',           # 경고 색상
    'error': '#dc3232',             # 오류 색상
    'danger': '#dc3232',            # 위험 색상 (error와 동일)
    'accent': '#00d084'             # WordPress 액센트 색상
}

class WordPressButton(QPushButton):
    """WordPress 스타일 버튼"""
    def __init__(self, text, button_type="primary", parent=None):
        super().__init__(text, parent)
        self.button_type = button_type
        self.is_active = False  # 활성화 상태
        self.setCursor(Qt.CursorShape.PointingHandCursor)  # 커서 스타일 적용
        self.updateStyle()

    def setActive(self, active):
        """활성화 상태 설정"""
        self.is_active = active
        self.updateStyle()

    def updateStyle(self):
        """스타일 업데이트"""
        base_style = f"""
            QPushButton {{
                font-size: 14px;
                font-weight: 500;
                padding: 12px 24px;
                border-radius: 6px;
                border: none;
                color: {WORDPRESS_COLORS['text_primary']};
                min-height: 20px;
            }}
        """

        # inactive 상태일 경우 더 어두운 회색 글씨
        text_color = "#4a5568" if getattr(self, 'is_inactive', False) else WORDPRESS_COLORS['text_primary']

        if self.button_type == "primary":
            # 시작 버튼 등
            bg_color = "#1e3a8a" if self.is_active else WORDPRESS_COLORS['primary_blue']
            self.setStyleSheet(base_style + f"""
                QPushButton {{
                    background-color: {bg_color};
                    color: {text_color};
                }}
                QPushButton:hover {{
                    background-color: {WORDPRESS_COLORS['dark_blue']};
                }}
                QPushButton:pressed {{
                    background-color: {WORDPRESS_COLORS['light_blue']};
                }}
                QPushButton:disabled {{
                    background-color: #1a365d;
                    color: #a0aec0;
                    border: none;
                }}
            """)
        elif self.button_type == "success":
            self.setStyleSheet(base_style + f"""
                QPushButton {{
                    background-color: {WORDPRESS_COLORS['success']};
                    color: {text_color};
                }}
                QPushButton:hover {{
                    background-color: #3d9946;
                }}
                QPushButton:disabled {{
                    background-color: #2d7a32;
                    color: #a5d6a7;
                    border: none;
                }}
            """)
        elif self.button_type == "warning":
            self.setStyleSheet(base_style + f"""
                QPushButton {{
                    background-color: {WORDPRESS_COLORS['warning']};
                    color: {text_color};
                }}
                QPushButton:hover {{
                    background-color: #e6a700;
                }}
                QPushButton:disabled {{
                    background-color: #b8860b;
                    color: #fff3cd;
                    border: none;
                }}
            """)
        elif self.button_type == "error":
            self.setStyleSheet(base_style + f"""
                QPushButton {{
                    background-color: {WORDPRESS_COLORS['error']};
                    color: {text_color};
                }}
                QPushButton:hover {{
                    background-color: #c42d2d;
                }}
                QPushButton:disabled {{
                    background-color: #8b1538;
                    color: #f5c6cb;
                    border: none;
                }}
            """)
        elif self.button_type == "secondary":
            self.setStyleSheet(base_style + f"""
                QPushButton {{
                    background-color: {WORDPRESS_COLORS['surface_light']};
                    color: {text_color if not getattr(self, 'is_inactive', False) else "#718096"};
                }}
                QPushButton:hover {{
                    background-color: {WORDPRESS_COLORS['primary_blue']};
                    color: {WORDPRESS_COLORS['text_primary']};
                }}
                QPushButton:disabled {{
                    background-color: #4a5568;
                    color: #718096;
                    border: none;
                }}
            """)

    def setInactive(self, inactive=True):
        """버튼을 비활성화 표시로 설정 (배경은 유지, 글자만 회색)"""
        self.is_inactive = inactive
        self.updateStyle()

    def setButtonType(self, button_type):
        """버튼 타입 변경"""
        self.button_type = button_type
        self.updateStyle()

class ResourceScanner:
    """리소스 파일 스캔 및 자동 묶음 클래스"""

    def __init__(self, base_path):
        self.base_path = base_path
        self.fonts = []
        self.images = []
        self.keyword_files = []
        self.prompt_files = {}

    def scan_all_resources(self):
        """모든 리소스 파일 스캔"""
        self.scan_fonts()
        self.scan_images()
        self.scan_keywords()
        self.scan_prompts()

    def scan_fonts(self):
        """폰트 파일 스캔"""
        fonts_dir = os.path.join(self.base_path, "fonts")
        self.fonts = []

        if os.path.exists(fonts_dir):
            try:
                for file in os.listdir(fonts_dir):
                    if file.lower().endswith(('.ttf', '.otf', '.woff', '.woff2')):
                        file_path = os.path.join(fonts_dir, file)
                        if os.path.isfile(file_path):  # 파일 존재 확인
                            self.fonts.append({
                                'name': file,
                                'path': file_path,
                                'relative_path': f"fonts/{file}",
                                'size': self.get_file_size(file_path)
                            })
            except (OSError, IOError) as e:
                print(f"⚠️ 폰트 디렉토리 스캔 오류: {e}")

    def scan_images(self):
        """이미지 파일 스캔 (썸네일 템플릿)"""
        images_dir = os.path.join(self.base_path, "images")
        self.images = []

        if os.path.exists(images_dir):
            try:
                for file in os.listdir(images_dir):
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')):
                        file_path = os.path.join(images_dir, file)
                        if os.path.isfile(file_path):  # 파일 존재 확인
                            self.images.append({
                                'name': file,
                                'path': file_path,
                                'relative_path': f"images/{file}",
                                'size': self.get_file_size(file_path)
                            })
            except (OSError, IOError) as e:
                print(f"⚠️ 이미지 디렉토리 스캔 오류: {e}")

    def scan_keywords(self):
        """키워드 파일 스캔"""
        self.keyword_files = []

        # 루트 디렉토리의 txt 파일들
        try:
            for file in os.listdir(self.base_path):
                if file.lower().endswith('.txt') and 'keyword' in file.lower():
                    file_path = os.path.join(self.base_path, file)
                    if os.path.isfile(file_path):  # 파일 존재 확인
                        keywords_count = self.count_keywords_in_file(file_path)
                        self.keyword_files.append({
                            'name': file,
                            'path': file_path,
                            'relative_path': file,
                            'keywords_count': keywords_count,
                            'suggested_for': self.suggest_site_for_keywords(file)
                        })

            # keywords 서브 디렉토리의 txt 파일들도 스캔
            keywords_dir = os.path.join(self.base_path, "keywords")
            if os.path.exists(keywords_dir):
                for file in os.listdir(keywords_dir):
                    if file.lower().endswith('.txt') and not file.startswith('used_'):
                        file_path = os.path.join(keywords_dir, file)
                        if os.path.isfile(file_path):  # 파일 존재 확인
                            keywords_count = self.count_keywords_in_file(file_path)
                            self.keyword_files.append({
                                'name': file,
                                'path': file_path,
                                'relative_path': f"keywords/{file}",
                                'keywords_count': keywords_count,
                                'suggested_for': self.suggest_site_for_keywords(file)
                            })
        except (OSError, IOError) as e:
            print(f"⚠️ 키워드 파일 스캔 오류: {e}")

    def scan_prompts(self):
        """프롬프트 파일 스캔"""
        prompts_dir = os.path.join(self.base_path, "prompts")
        self.prompt_files = {'gpt': [], 'gemini': []}

        for ai_type in ['gpt', 'gemini']:
            ai_dir = os.path.join(prompts_dir, ai_type)
            if os.path.exists(ai_dir):
                for file in os.listdir(ai_dir):
                    if file.lower().endswith('.txt'):
                        self.prompt_files[ai_type].append({
                            'name': file,
                            'path': os.path.join(ai_dir, file),
                            'relative_path': f"prompts/{ai_type}/{file}",
                            'size': self.get_file_size(os.path.join(ai_dir, file))
                        })

    def get_file_size(self, file_path):
        """파일 크기 반환 (KB)"""
        try:
            size = os.path.getsize(file_path)
            return round(size / 1024, 2)
        except:
            return 0

    def count_keywords_in_file(self, file_path):
        """파일의 키워드 개수 세기"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
                return len(lines)
        except:
            return 0

    def suggest_site_for_keywords(self, filename):
        """파일명 기반 사이트 추천"""
        filename_lower = filename.lower()
        if 'tech' in filename_lower or '기술' in filename_lower:
            return "기술 관련 사이트"
        elif 'news' in filename_lower or '뉴스' in filename_lower:
            return "뉴스 사이트"
        elif 'blog' in filename_lower or '블로그' in filename_lower:
            return "개인 블로그"
        elif 'business' in filename_lower or '비즈니스' in filename_lower:
            return "비즈니스 사이트"
        else:
            return "범용"

    def get_resource_summary(self):
        """리소스 요약 정보"""
        return {
            'fonts_count': len(self.fonts),
            'images_count': len(self.images),
            'keyword_files_count': len(self.keyword_files),
            'total_keywords': sum(kf['keywords_count'] for kf in self.keyword_files),
            'gpt_prompts': len(self.prompt_files['gpt']),
            'gemini_prompts': len(self.prompt_files['gemini'])
        }

class ContentGenerator:
    """콘텐츠 생성기 - GPT와 Gemini API 지원"""
    def __init__(self, config_data, log_func, auto_wp_instance=None):
        self.config_data = config_data
        self.log = log_func
        self.auto_wp = auto_wp_instance
        self.openai_client = None
        self.gemini_model = None

        # API 상태 추적
        self.api_status = {
            'openai': False,
            'gemini': False
        }

        # 포스팅 상태 관리
        self.is_posting = False
        self.worker_thread = None  # Worker Thread 참조

        # config_manager 속성 추가
        if self.auto_wp and hasattr(self.auto_wp, 'config_manager'):
            self.config_manager = self.auto_wp.config_manager
        else:
            self.config_manager = None

    def should_stop_posting(self):
        """포스팅 중지 여부를 확인하는 헬퍼 메서드"""
        try:
            # Worker Thread 상태 우선 체크 (가장 정확함)
            if hasattr(self, 'worker_thread') and self.worker_thread:
                is_running = getattr(self.worker_thread, 'is_running', True)
                force_stop = getattr(self.worker_thread, '_force_stop', False)
                if not is_running or force_stop:
                    return True
            
            # Auto WP 인스턴스의 is_posting 상태 체크
            if hasattr(self.auto_wp, 'is_posting'):
                if not self.auto_wp.is_posting:
                    return True
            
            # 모든 체크를 통과하면 계속 진행
            return False
        except Exception:
            # 오류 발생 시 안전하게 계속 진행 (중지하지 않음)
            return False

        # GUI에서 선택한 AI 모델 (기본값 먼저 설정)
        self.current_ai_provider = "gemini"  # 기본값
        
        # config_manager에서 설정 가져오기
        if self.config_manager:
            try:
                global_settings = self.config_manager.data.get("global_settings", {})
                self.current_ai_provider = global_settings.get("default_ai", "gemini")
            except Exception:
                self.current_ai_provider = "gemini"
            
        # auto_wp_instance에서 직접 가져오기 (우선순위 높음)
        if hasattr(auto_wp_instance, 'current_ai_provider'):
            try:
                self.current_ai_provider = auto_wp_instance.current_ai_provider
            except Exception:
                pass  # 기본값 유지

        # API 초기화
        self.initialize_apis()
        
        # 현재 처리 중인 사이트 정보
        self.current_site = None

    def set_current_site(self, site):
        """현재 처리 중인 사이트 정보 설정"""
        self.current_site = site
    
    def get_thumbnail_file(self):
        """현재 사이트의 썸네일 파일 또는 기본 썸네일 반환"""
        import random
        
        # 현재 사이트의 썸네일 이미지 사용
        if self.current_site and self.current_site.get('thumbnail_image'):
            thumbnail_filename = self.current_site.get('thumbnail_image')
            thumbnail_path = os.path.join(get_base_path(), 'images', thumbnail_filename)
            if os.path.exists(thumbnail_path):
                return thumbnail_filename
        
        # 기본 썸네일 목록에서 랜덤 선택 (정확한 파일명 사용)
        available_thumbnails = ['썸네일 (1).jpg', '썸네일 (2).jpg', '썸네일 (3).jpg',
                              '썸네일 (4).jpg', '썸네일 (5).jpg', '썸네일 (6).jpg', 
                              '썸네일 (7).jpg']
        
        # 존재하는 파일 중에서만 선택
        existing_thumbnails = []
        for thumb in available_thumbnails:
            thumb_path = os.path.join(get_base_path(), 'images', thumb)
            if os.path.exists(thumb_path):
                existing_thumbnails.append(thumb)
        
        if existing_thumbnails:
            return random.choice(existing_thumbnails)
        else:
            return '썸네일 (1).jpg'  # 최후 기본값

    def initialize_apis(self):
        """사용 가능한 모든 API 초기화"""

        # API 상태 초기화
        self.api_status = {'openai': False, 'gemini': False}

        # OpenAI 초기화
        if self.config_manager:
            openai_api_key = self.config_manager.data.get("api_keys", {}).get("openai", "")
        else:
            openai_api_key = self.config_data.get('openai_api_key', '')

        if openai_api_key and openai_api_key not in ["your_openai_api_key", ""]:
            try:
                self.openai_client = OpenAI(api_key=openai_api_key)
                self.api_status['openai'] = True
            except Exception as e:
                self.log(f"🔥 OpenAI 클라이언트 초기화 실패: {e}")
                self.openai_client = None
                self.api_status['openai'] = False
        else:
            self.log("⚠️ OpenAI API 키가 설정되지 않았거나 유효하지 않습니다.")

        # Gemini 초기화
        if self.config_manager:
            gemini_api_key = self.config_manager.data.get("api_keys", {}).get("gemini", "")
        else:
            gemini_api_key = self.config_data.get('gemini_api_key', '')

        if GEMINI_AVAILABLE and gemini_api_key and gemini_api_key not in ["your_gemini_api_key", ""]:
            try:
                # API 키 설정
                genai.configure(api_key=gemini_api_key)

                # 안전 설정 구성 - 콘텐츠 차단 최소화
                safety_settings = [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_ONLY_HIGH"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_ONLY_HIGH"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_ONLY_HIGH"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_ONLY_HIGH"
                    }
                ]

                # 모델 초기화 시 사용 가능한 모델 확인 (최신 모델부터 시도)
                model_priority = ['gemini-2.5-flash-lite', 'gemini-2.0-flash-exp', 'gemini-1.5-flash', 'gemini-1.5-pro']
                model_initialized = False
                
                for model_name in model_priority:
                    try:
                        self.gemini_model = genai.GenerativeModel(
                            model_name,
                            safety_settings=safety_settings
                        )
                        
                        # 간단한 테스트 호출로 API 작동 확인
                        test_response = self.gemini_model.generate_content(
                            "테스트",
                            generation_config=genai.types.GenerationConfig(
                                max_output_tokens=10,
                                temperature=0.1
                            )
                        )
                        
                        if hasattr(test_response, 'text') and test_response.text:
                            model_initialized = True
                            break
                        else:
                            continue
                        
                    except Exception as model_error:
                        self.log(f"❌ {model_name} 실패: {str(model_error)[:100]}")
                        continue
                
                if not model_initialized:
                    self.log("❌ 모든 Gemini 모델 초기화 실패")
                    raise Exception("사용 가능한 Gemini 모델이 없습니다.")

                self.api_status['gemini'] = True
                
            except Exception as e:
                self.log(f"🔥 Gemini 클라이언트 초기화 실패: {e}")
                self.log(f"📋 상세 오류: {str(e)}")
                if "API_KEY_INVALID" in str(e):
                    self.log("❌ Gemini API 키가 유효하지 않습니다. 설정에서 올바른 키를 입력해주세요.")
                elif "PERMISSION_DENIED" in str(e):
                    self.log("❌ API 권한이 없습니다. Google AI Studio에서 API 키 권한을 확인해주세요.")
                elif "QUOTA_EXCEEDED" in str(e):
                    self.log("❌ API 할당량을 초과했습니다. 잠시 후 다시 시도하거나 결제 정보를 확인해주세요.")
                else:
                    self.log("❌ 네트워크 연결이나 API 서버 문제일 수 있습니다.")
                self.gemini_model = None
                self.api_status['gemini'] = False
        elif not GEMINI_AVAILABLE:
            self.log("❌ google-generativeai 라이브러리가 설치되지 않았습니다.")
            self.log("💡 pip install google-generativeai 명령으로 설치해주세요.")
            self.gemini_model = None
            self.api_status['gemini'] = False
        elif not gemini_api_key or gemini_api_key in ["your_gemini_api_key", ""]:
            self.log("⚠️ Gemini API 키가 설정되지 않았거나 기본값입니다.")
            self.log("💡 설정 탭에서 올바른 Gemini API 키를 입력해주세요.")
            self.gemini_model = None
            self.api_status['gemini'] = False
        else:
            self.log(f"❓ Gemini 초기화 조건 불만족: AVAILABLE={GEMINI_AVAILABLE}, KEY_LENGTH={len(gemini_api_key) if gemini_api_key else 0}")
            self.gemini_model = None
            self.api_status['gemini'] = False

        # 최종 상태 요약
        self.log(f"🤖 API 초기화 완료: OpenAI={'✅' if self.api_status['openai'] else '❌'}, Gemini={'✅' if self.api_status['gemini'] else '❌'}")

    def call_ai_api(self, prompt, step_name, max_tokens=1500, temperature=0.7, system_content=None):
        """통합 AI API 호출"""
        # 중지 체크
        if hasattr(self, 'auto_wp') and hasattr(self.auto_wp, 'posting_worker') and not self.auto_wp.posting_worker.is_running:
            self.log(f"⏹️ {step_name} AI API 호출 전 중지됨")
            return None
        
        ai_provider = self.current_ai_provider
        
        # Gemini API 사용 시 더 상세한 검증
        if ai_provider == 'gemini':
            # API 키 확인
            gemini_key = self.config_manager.data.get("api_keys", {}).get("gemini", "").strip()
            if not gemini_key:
                self.log("❌ Gemini API 키가 설정되지 않았습니다. 설정 탭에서 API 키를 입력해주세요.")
                return None
            
            # 모델 상태 확인
            if not self.api_status.get('gemini'):
                self.log("❌ Gemini API가 초기화되지 않았습니다. API 키와 네트워크 상태를 확인해주세요.")
                return None
                
            if not self.gemini_model:
                self.log("❌ Gemini 모델이 로드되지 않았습니다. API 키를 확인하고 프로그램을 재시작해주세요.")
                return None
            
            return self.call_gemini_api(prompt, step_name, max_tokens, temperature, system_content)
            
        elif ai_provider in ['gpt', 'openai']:
            # OpenAI API 키 확인
            openai_key = self.config_manager.data.get("api_keys", {}).get("openai", "").strip()
            if not openai_key:
                self.log("❌ OpenAI API 키가 설정되지 않았습니다. 설정 탭에서 API 키를 입력해주세요.")
                return None
                
            if not self.api_status.get('openai'):
                self.log("❌ OpenAI API가 초기화되지 않았습니다. API 키와 네트워크 상태를 확인해주세요.")
                return None
                
            return self.call_openai_api(prompt, step_name, max_tokens, temperature, system_content)
        else:
            self.log(f"❌ 알 수 없는 AI 제공자: {ai_provider}. 설정을 확인.")
            return None

    def call_openai_api(self, prompt, step_name, max_tokens, temperature, system_content):
        """OpenAI API 호출"""
        try:
            messages = [{"role": "system", "content": system_content}, {"role": "user", "content": prompt}] if system_content else [{"role": "user", "content": prompt}]
            
            # 현재 모델 설정 가져오기
            if self.config_manager:
                current_model = self.config_manager.data.get("global_settings", {}).get("openai_model", "gpt-3.5-turbo")
            else:
                current_model = "gpt-3.5-turbo"
            
            response = self.openai_client.chat.completions.create(
                model=current_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=60
            )
            return response.choices[0].message.content
        except Exception as api_error:
            self.log(f"❌ {step_name} OpenAI API 오류: {api_error}")
            return None

    def call_gemini_api(self, prompt, step_name, max_tokens, temperature, system_content):
        """Gemini API 호출"""
        try:
            # API 키 재확인
            gemini_key = self.config_manager.data.get("api_keys", {}).get("gemini", "").strip()
            if not gemini_key:
                raise Exception("Gemini API 키가 설정되지 않았습니다.")
            
            # 모델 상태 재확인
            if not self.gemini_model:
                raise Exception("Gemini 모델이 초기화되지 않았습니다.")
            
            full_prompt = f"{system_content}\n\n---\n\n{prompt}" if system_content else prompt
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens, 
                temperature=temperature
            )
            
            # 타임아웃과 함께 API 호출
            import time
            start_time = time.time()
            
            try:
                response = self.gemini_model.generate_content(full_prompt, generation_config=generation_config)
                elapsed_time = time.time() - start_time
                
                if hasattr(response, 'text') and response.text:
                    return response.text
                else:
                    # 빈 응답에 대한 상세 정보
                    if hasattr(response, 'prompt_feedback'):
                        feedback = response.prompt_feedback
                        if feedback and hasattr(feedback, 'block_reason'):
                            raise Exception(f"Gemini가 콘텐츠를 차단했습니다: {feedback.block_reason}")
                    raise Exception("응답 텍스트가 비어있습니다.")
            except Exception as gen_error:
                elapsed_time = time.time() - start_time
                self.log(f"❌ API 호출 실패 ({elapsed_time:.1f}초 후): {gen_error}")
                raise
                
        except Exception as api_error:
            error_msg = str(api_error)
            self.log(f"❌ {step_name} Gemini API 오류: {error_msg}")
            
            # 구체적인 오류 유형별 안내
            if "API_KEY_INVALID" in error_msg or "Invalid API key" in error_msg:
                self.log("💡 해결방법: 설정 탭에서 올바른 Gemini API 키를 입력해주세요.")
            elif "QUOTA_EXCEEDED" in error_msg or "quota" in error_msg.lower():
                self.log("💡 해결방법: API 할당량을 확인하고, 잠시 후 다시 시도해주세요.")
            elif "PERMISSION_DENIED" in error_msg:
                self.log("💡 해결방법: Google AI Studio에서 API 권한을 확인해주세요.")
            elif "RESOURCE_EXHAUSTED" in error_msg:
                self.log("💡 해결방법: 요청량이 많습니다. 잠시 후 다시 시도해주세요.")
            elif "UNAVAILABLE" in error_msg or "network" in error_msg.lower():
                self.log("💡 해결방법: 네트워크 연결을 확인하거나 잠시 후 다시 시도해주세요.")
            else:
                self.log(f"💡 예상치 못한 오류입니다. 자세한 정보: {error_msg}")
                
            return None

    def check_rate_limit(self, provider):
        """분당 및 일일 요청 제한 확인"""
        current_time = time.time()
        tracker = self.request_tracker[provider]

        # 분당 요청 확인
        requests = tracker['requests']
        max_requests = tracker['max_per_minute']

        # 1분 이전의 요청들 제거
        requests[:] = [req_time for req_time in requests if current_time - req_time < 60]

        minute_limit_ok = len(requests) < max_requests

        # 일일 요청 확인
        daily_limit_ok = True
        if tracker['daily_reset_time'] is None:
            # 첫 요청일 경우 오늘 자정으로 설정
            from datetime import datetime, timedelta
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            tracker['daily_reset_time'] = today.timestamp()

        # 하루가 지났는지 확인 (UTC 기준 24시간)
        if current_time - tracker['daily_reset_time'] >= 86400:  # 24시간
            tracker['daily_requests'] = 0
            tracker['daily_reset_time'] = current_time

        daily_limit_ok = tracker['daily_requests'] < tracker['max_per_day']

        return minute_limit_ok and daily_limit_ok

    def add_request(self, provider):
        """요청 추가"""
        current_time = time.time()
        tracker = self.request_tracker[provider]

        # 분당 추적
        tracker['requests'].append(current_time)

        # 일일 추적
        tracker['daily_requests'] += 1

        # 현재 요청 수 로깅
        minute_count = len(tracker['requests'])
        daily_count = tracker['daily_requests']
        self.log(f"📊 {provider.upper()} 요청 추가 - 분당: {minute_count}/{tracker['max_per_minute']}, 일일: {daily_count}/{tracker['max_per_day']}")

    def get_quota_status(self, provider):
        """할당량 상태 반환"""
        tracker = self.request_tracker[provider]
        current_time = time.time()

        # 분당 요청 수
        requests = [req for req in tracker['requests'] if current_time - req < 60]
        minute_count = len(requests)

        # 일일 요청 수
        daily_count = tracker['daily_requests']

        return {
            'minute_count': minute_count,
            'minute_limit': tracker['max_per_minute'],
            'daily_count': daily_count,
            'daily_limit': tracker['max_per_day'],
            'minute_ok': minute_count < tracker['max_per_minute'],
            'daily_ok': daily_count < tracker['max_per_day'],
        }

    def wait_for_rate_limit(self, provider):
        """할당량 대기"""
        while not self.check_rate_limit(provider):
            current_time = time.time()
            requests = self.request_tracker[provider]['requests']
            oldest_request = min(requests) if requests else current_time
            wait_time = 60 - (current_time - oldest_request) + 1  # 1초 여유

            self.log(f"⏳ {provider.upper()} 할당량 대기 중 ({wait_time:.0f}초 남음)")
            time.sleep(min(wait_time, 10))  # 최대 10초씩 대기

    def analyze_api_error(self, error_str, provider):
        """API 오류 분석 및 처리 방법 결정 - 할당량 체크 제거"""
        error_lower = error_str.lower()

        # 일시적 오류 패턴 (재시도 가능)
        temporary_patterns = [
            'connection error' in error_lower,
            'timeout' in error_lower,
            'internal server error' in error_lower,
            '500' in error_str,
            '502' in error_str,
            '503' in error_str,
            'service unavailable' in error_lower
        ]

        if any(temporary_patterns):
            return 'TEMPORARY_ERROR'
        else:
            return 'OTHER_ERROR'

    def generate_ai_title(self, keyword):
        """AI를 사용해 prompt1.txt 제목 지침에 따른 제목 생성"""
        try:
            title_prompt = f"""너는 SEO 전문가야. 아래 제목 지침에 따라 '{keyword}'에 대한 제목을 정확히 생성해.

제목 지침:
- 제목 형식: '{keyword} | 숫자가 들어간 후킹문구' 형식
- 글자수: 50~60자, 숫자 필수 포함
- 후킹 요소: 혜택 강조, 고통 해결, 구체적 수치 활용
- 중요: 반드시 '{keyword} |' 로 시작해야 함!

제목 예시:
"인덕션 청소 | 10분만에 완벽하게 끝내는 3가지 방법"
"스마트폰 배터리 | 2배 오래 쓰는 5가지 비밀 설정"
"냉장고 정리 | 30분으로 1주일이 편해지는 수납법"

키워드: {keyword}

위 지침에 맞는 제목 1개만 출력해. 설명이나 다른 내용은 일체 포함하지 마."""

            system_prompt = "너는 SEO 제목 전문가야. 주어진 지침에 따라 정확한 제목만 생성해."
            
            result = self.call_ai_api(title_prompt, "제목 생성", max_tokens=100, temperature=0.7, system_content=system_prompt)
            
            if result and result.strip():
                generated_title = result.strip()
                # 제목 형식 검증
                if generated_title.startswith(f"{keyword} |") and any(char.isdigit() for char in generated_title):
                    self.log(f"🎯 AI 생성 제목: {generated_title}")
                    return generated_title
                else:
                    self.log(f"❌ AI 제목 형식 불일치: {generated_title}")
                    return None
            else:
                self.log("❌ AI 제목 생성 실패: 빈 응답")
                return None
                
        except Exception as e:
            self.log(f"❌ AI 제목 생성 중 오류: {e}")
            return None

    def clean_step1_content(self, content):
        """1단계 콘텐츠 정리 - 제목+간단한 서론+링크버튼만 남기기"""
        try:
            import re
            
            # AI 역할 언급 완전 제거
            role_patterns = [
                r'제가\s*\d+년\s*경력의?\s*SEO\s*작가로서',
                r'저는\s*\d+년\s*경력의?\s*SEO\s*작가로서',
                r'\d+년\s*경력의?\s*SEO\s*작가로서',
                r'\d+년\s*경력의?\s*전문가로서',
                r'SEO\s*전문가로서',
                r'콘텐츠\s*작가로서',
                r'전문\s*작가로서'
            ]
            
            for pattern in role_patterns:
                content = re.sub(pattern, '', content, flags=re.IGNORECASE)
            
            # 첫 번째 링크버튼만 보호
            first_link = ""
            def preserve_first_link(match):
                nonlocal first_link
                if not first_link:
                    first_link = match.group(0)
                    return "__FIRST_LINK__"
                return ""  # 두 번째 이후 링크 제거
            
            # 모든 링크 패턴 처리
            link_patterns = [
                r'<div><center><p><a[^>]*class="링크버튼"[^>]*>.*?</a></p></center></div>',
                r'<div><center><a[^>]*class="blink"[^>]*>.*?</a></center></div>',
                r'<center><a[^>]*class="blink"[^>]*>.*?</a></center>',
                r'<p[^>]*center[^>]*>.*?<a[^>]*class="링크버튼"[^>]*>.*?</a>.*?</p>'
            ]
            
            for pattern in link_patterns:
                content = re.sub(pattern, preserve_first_link, content, flags=re.DOTALL)
            
            # HTML을 줄 단위로 분리
            lines = content.split('\n')
            result_lines = []
            h1_found = False
            paragraph_count = 0
            max_paragraphs = 2  # 서론은 최대 2개 문단만
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # h1 태그는 유지
                if '<h1>' in line:
                    result_lines.append(line)
                    h1_found = True
                    continue
                
                # h1 이후에만 처리
                if not h1_found:
                    continue
                
                # h2, h3 이하 소제목 발견 시 중단
                if re.search(r'<h[2-6]', line, re.IGNORECASE):
                    break
                
                # li, ul 태그 제거 (1단계에는 리스트 없어야 함)
                if re.search(r'<[ul|li]', line, re.IGNORECASE):
                    continue
                
                # p 태그만 허용하되 최대 개수 제한
                if '<p>' in line and paragraph_count < max_paragraphs:
                    result_lines.append(line)
                    paragraph_count += 1
                elif line == "__FIRST_LINK__":
                    # 링크버튼 위치 표시
                    result_lines.append(line)
            
            # 결과 조합
            content = '\n'.join(result_lines)
            
            # 링크버튼 복원
            if first_link:
                content = content.replace("__FIRST_LINK__", first_link)
            
            # 최종 정리
            content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
            
            return content.strip()
            
        except Exception as e:
            self.log(f"1단계 콘텐츠 정리 중 오류: {e}")
            return content

    def clean_step5_content(self, content):
        """5단계 콘텐츠 정리 - 표와 FAQ 구조 확인 및 강제"""
        try:
            import re
            
            # 표가 있는지 확인
            has_table = '<table' in content and '</table>' in content
            
            # FAQ가 있는지 확인 (Q1~Q5)
            faq_pattern = r'<h3><strong>Q[1-5]\..*?</strong></h3>'
            faq_matches = re.findall(faq_pattern, content, flags=re.IGNORECASE)
            has_complete_faq = len(faq_matches) >= 5
            
            # "자주 묻는 질문" 헤더가 있는지 확인
            has_faq_header = '<h2><strong>자주 묻는 질문</strong></h2>' in content
            
            # 로그 출력
            if not has_table:
                self.log("🚨 5단계: 표가 누락됨 - prompt5.txt 구조 위반!")
            if not has_complete_faq:
                self.log(f"🚨 5단계: FAQ 부족 (발견: {len(faq_matches)}개/필요: 5개) - prompt5.txt 구조 위반!")
            if not has_faq_header:
                self.log("🚨 5단계: FAQ 헤더 누락 - <h2><strong>자주 묻는 질문</strong></h2> 필요!")
                
            # 구조 위반 시 경고
            if not (has_table and has_complete_faq and has_faq_header):
                self.log("⚠️ prompt5.txt HTML 구조가 제대로 지켜지지 않았습니다!")
                
            return content
            
        except Exception as e:
            self.log(f"5단계 콘텐츠 정리 중 오류: {e}")
            return content

    def remove_prompt_meta_terms(self, content):
        """프롬프트 메타 용어 및 지시사항 제거 - SEO 내용 제거 강화"""
        try:
            import re
            # 제거할 메타 용어들
            meta_terms = [
                r'행동\s*유도\s*문구\s*텍스트',
                r'문구\s*텍스트',
                r'메타\s*텍스트',
                r'프롬프트\s*지시사항',
                r'시스템\s*프롬프트',
                r'AI\s*지침',
                r'콘텐츠\s*생성\s*지침',
                r'작성\s*가이드라인',
                r'HTML\s*태그\s*가이드',
                r'서론\s*\d+자',
                r'본문\s*\d+자',
                r'제목\s*\d+자',
                r'\d+자\s*내외',
                r'\d+자\s*분량',
                r'총\s*\d+-?\d*자',
                r'😊.*?:',        # 이모지 + 콜론 패턴
                r'👍.*?:',
                r'✅.*?:',
                r'💡.*?:',
                r'📌.*?:',
                r'🔍.*?:',
                r'➡️.*?:',
                r'단계별\s*목표',
                r'핵심\s*키워드',
                r'타겟\s*독자',
                r'```[a-z]*',     # 마크다운 코드 블록 시작
                r'```',           # 마크다운 코드 블록 끝
                r'\*\*[^*]*\*\*:',  # 볼드 마크다운 + 콜론
                r'#+\s*[^#]*:',     # 마크다운 헤더 + 콜론
                # AI 역할 언급 제거 패턴 추가
                r'\d+년\s*경력의?\s*SEO\s*작가로서',
                r'\d+년\s*경력의?\s*SEO\s*콘텐츠\s*작가로서',
                r'\d+년\s*경력의?\s*전문가로서',
                r'SEO\s*전문가로서',
                r'콘텐츠\s*작가로서',
                r'전문\s*작가로서',
                r'경험\s*많은\s*작가로서',
                r'숙련된\s*작가로서',
                # SEO 관련 내용 제거 패턴 추가
                r'SEO.*?본질.*?콘텐츠\s*자산',
                r'SEO.*?본질.*?콘텐츠\s*자산',
                r'짧은\s*것들을\s*차근차근\s*시작하기',
                r'완벽한\s*SEO란\s*없음',
                r'오늘\s*하나의\s*제목.*?구체적인\s*정보.*?가볍게\s*시작하면\s*됩니다',
                r'이번\s*주\s*목표.*?제목에\s*검색\s*키워드\s*포함하기',
                r'다음\s*주\s*목표.*?본문에\s*소제목\s*구조\s*만들기',
                r'다\s*음\s*주\s*목표.*?외부\s*링크\s*연결하기',
                r'구글은\s*단기간에\s*결과가\s*나오는\s*것이\s*아니다',
                r'한\s*달에\s*10개보다는\s*매주\s*2개씩\s*꾸준히',
                r'블루투스\s*이어폰\s*연결\s*안될\s*때\s*비교\s*정보',
                r'구분.*?특징.*?장점.*?\s*형태'
            ]

            # 각 메타 용어 제거
            for term in meta_terms:
                content = re.sub(term, '', content, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)

            # HTML 관련 마크업 문구 제거 강화
            html_markup_patterns = [
                r'```html.*?```',     # ```html...``` 코드블록 전체
                r'```html',           # ```html 시작
                r'```',              # ``` 마크다운 코드블록
                r'`html.*?`',         # `html...` 인라인 코드
                r'`html',            # `html
                r'"html',            # "html 
                r'html\s*코드',       # html 코드
                r'HTML\s*구조',       # HTML 구조  
                r'html\s*태그',       # html 태그
                r'HTML\s*태그',       # HTML 태그
                r'<\/\*.*?\*\/>',     # /* */ 주석
                r'<!--.*?-->',        # HTML 주석
                # 마크다운 문법 제거 강화
                r'#{1,6}\s+',         # ### 마크다운 헤더
                r'\*\*([^*]+)\*\*',   # **bold** 마크다운
                r'\*([^*]+)\*',       # *italic* 마크다운  
                r'!\[.*?\]\(.*?\)',   # ![이미지](링크) 마크다운
                r'\[([^\]]+)\]\([^)]+\)', # [텍스트](링크) 마크다운
                # HTML 문서 구조 태그 완전 제거
                r'<!DOCTYPE[^>]*>',   # DOCTYPE
                r'<html[^>]*>',       # <html> 태그
                r'</html>',           # </html> 태그
                r'<head[^>]*>.*?</head>', # <head> 섹션 전체
                r'<body[^>]*>',       # <body> 태그
                r'</body>',           # </body> 태그
                r'<meta[^>]*>',       # <meta> 태그
                r'<title[^>]*>.*?</title>', # <title> 태그
            ]
            
            for pattern in html_markup_patterns:
                content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)

            # <h1> 태그 완전 제거 (시스템에서 사용하지 않음)
            content = re.sub(r'<h1[^>]*>.*?</h1>', '', content, flags=re.IGNORECASE | re.DOTALL)
            content = re.sub(r'<h1[^>]*>', '', content, flags=re.IGNORECASE)
            content = re.sub(r'</h1>', '', content, flags=re.IGNORECASE)

            # prompt1.txt에서 나와서는 안 되는 h2 태그 제거 (1단계는 제목+서론+링크버튼만)
            content = re.sub(r'<h2[^>]*>.*?</h2>', '', content, flags=re.IGNORECASE | re.DOTALL)
            content = re.sub(r'<h2[^>]*>', '', content, flags=re.IGNORECASE)
            content = re.sub(r'</h2>', '', content, flags=re.IGNORECASE)

            # 특정 패턴들 추가 제거
            content = re.sub(r'서론\s*\d+자', '', content, flags=re.IGNORECASE)
            content = re.sub(r'본문\s*\d+자', '', content, flags=re.IGNORECASE)
            content = re.sub(r'제목\s*\d+자', '', content, flags=re.IGNORECASE)

            # 마크다운 관련 지시문 제거
            content = re.sub(r'마크다운\s*문법\s*절대\s*사용\s*금지', '', content, flags=re.IGNORECASE)
            content = re.sub(r'HTML\s*태그만\s*사용', '', content, flags=re.IGNORECASE)
            content = re.sub(r'코드\s*블록\s*사용\s*금지', '', content, flags=re.IGNORECASE)
            content = re.sub(r'html\s*같은\s*마크다운\s*코드\s*블록', '', content, flags=re.IGNORECASE)

            # SEO 관련 표나 구조화된 내용 제거
            content = re.sub(r'<table>.*?</table>', '', content, flags=re.IGNORECASE | re.DOTALL)
            content = re.sub(r'구분.*?특징.*?장점', '', content, flags=re.IGNORECASE | re.DOTALL)

            # 단독으로 나오는 숫자+점 패턴 제거
            content = re.sub(r'^\s*\d+\.\s*$', '', content, flags=re.MULTILINE)
            content = re.sub(r'<p>\s*\d+\.\s*</p>', '', content, flags=re.IGNORECASE)

            # 빈 태그나 의미없는 구문 정리
            content = re.sub(r'<p>\s*</p>', '', content)
            content = re.sub(r'<div>\s*</div>', '', content)
            content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # 과도한 줄바꿈 정리

            return content.strip()

        except Exception as e:
            self.log(f"메타 용어 제거 중 오류: {e}")
            return content

    def generate_approval_content(self, keyword):
        """승인용 콘텐츠 생성 - AI 제공자에 관계없이 통합"""
        try:
            # 승인용 프롬프트 파일 로드
            approval_files = [
                "approval1.txt", "approval2.txt", "approval3.txt"
            ]

            all_content_parts = []
            title = ""

            # 모든 승인용 프롬프트 파일을 순차적으로 적용
            for i, approval_file in enumerate(approval_files, 1):
                prompt_path = os.path.join(get_base_path(), "prompts", approval_file)

                if os.path.exists(prompt_path):
                    # UTF-8 BOM 처리를 위해 utf-8-sig 사용
                    try:
                        with open(prompt_path, 'r', encoding='utf-8-sig') as f:
                            prompt_template = f.read()
                    except UnicodeDecodeError:
                        # BOM이 없는 경우 일반 utf-8로 재시도
                        with open(prompt_path, 'r', encoding='utf-8') as f:
                            prompt_template = f.read()

                    # 키워드 대체
                    prompt = prompt_template.replace("{keyword}", keyword)

                    print(f"승인용 {i}단계 생성 중", end=" ")

                    # 통합 AI API 호출
                    try:
                        response_text = self.call_ai_api(prompt, f"승인용 {i}단계", max_tokens=1500, temperature=0.7)

                        if response_text and response_text.strip():
                            step_content = self.remove_prompt_meta_terms(response_text.strip())
                            
                            # 1단계는 특별 처리 - 제목+서론+링크버튼만 유지
                            if i == 1:
                                step_content = self.clean_step1_content(step_content)
                                
                            all_content_parts.append(step_content)

                            # 첫 번째 단계에서 제목 추출
                            if i == 1 and step_content:
                                lines = step_content.split('\n')
                                for line in lines:
                                    line = line.strip()
                                    if line and not line.startswith('<'):
                                        import re
                                        clean_title = re.sub(r'<[^>]+>', '', line)
                                        if len(clean_title) > 10:
                                            title = clean_title
                                            break

                        # 다음 단계로 계속 진행

                    except Exception as step_error:
                        self.log(f"  ✨ 승인용 단계 {i} 오류: {step_error}")
                        # 단계별 오류 시에도 계속 진행
                else:
                    self.log(f"  🔥 승인용 프롬프트 파일 없음: {approval_file}")

            if not all_content_parts:
                self.log(f"🔥 승인용 콘텐츠 생성 실패 - 모든 단계 실패")
                return None, None, None

            # 모든 단계의 콘텐츠를 결합
            full_content = "\n\n".join(all_content_parts)
            print()  # 승인용 콘텐츠 생성 완료 후 개행

            # 마크다운을 HTML로 변환
            full_content = self.convert_markdown_to_html(full_content)
            
            # HTML 구조 정리 및 오류 수정
            full_content = self.clean_content(full_content)

            if not title:
                # prompt1.txt 제목 지침에 따른 AI 생성 제목
                title = self.generate_ai_title(keyword)
                if not title:
                    # AI 실패 시 fallback 제목 생성
                    hook_phrases = [
                        "5분만에 끝내는 완벽 가이드", "10가지 핵심 포인트", "3단계로 마스터하기",
                        "7가지 전문가 팁", "2배 효과적인 방법", "30초만에 해결하는 비법",
                        "15분 투자로 평생 활용", "4가지 실무 노하우", "6개월 경험을 압축한 가이드",
                        "9가지 검증된 방법", "1일 1시간으로 완성", "12가지 실전 전략"
                    ]
                    import random
                    hook_phrase = random.choice(hook_phrases)
                    title = f"{keyword} | {hook_phrase}"
                self.log(f"📝 자동 생성된 제목: {title}")

            # 썸네일 이미지 선택 및 제목 추가
            thumbnail_filename = self.get_thumbnail_file()
            base_thumbnail_path = os.path.join(get_base_path(), 'images', thumbnail_filename)

            # 제목이 있으면 썸네일에 제목 추가
            thumbnail_path = self.create_thumbnail_with_title(title, keyword)

            self.log(f"✅ 승인용 완료: {title}")
            return title, full_content, thumbnail_path

        except Exception as e:
            self.log(f"🔥 승인용 콘텐츠 생성 오류: {e}")
            return None, None, None

    def convert_markdown_to_html(self, content):
        """마크다운을 HTML로 변환"""
        try:
            # 먼저 링크 버튼 부분을 보호 (class="blink" 포함)
            link_patterns = []
            def preserve_link_html(match):
                link_patterns.append(match.group(0))
                return f"__LINK_PLACEHOLDER_{len(link_patterns)-1}__"

            # <div><center><a class="blink"  패턴 보호
            content = re.sub(r'<div><center><a[^>]*class="blink"[^>]*>.*?</a></center></div>', preserve_link_html, content, flags=re.DOTALL)
            # <center><a class="blink"  패턴도 보호
            content = re.sub(r'<center><a[^>]*class="blink"[^>]*>.*?</a></center>', preserve_link_html, content, flags=re.DOTALL)
            # 단순 <a class="blink"  패턴도 보호
            content = re.sub(r'<a[^>]*class="blink"[^>]*>.*?</a>', preserve_link_html, content, flags=re.DOTALL)

            # 마크다운 코드 블록 제거 (```html, ```python 등)
            content = re.sub(r'```[a-z]*\n?', '', content, flags=re.IGNORECASE)
            content = re.sub(r'```', '', content)

            # 제목 처리 - h1은 제거 (제목은 별도 필드로 처리)
            content = re.sub(r'^# (.*?)$', '', content, flags=re.MULTILINE)
            content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
            content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)

            # 굵은 글씨 처리
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'__(.*?)__', r'<strong>\1</strong>', content)

            # 기울임 처리
            content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)
            content = re.sub(r'_(.*?)_', r'<em>\1</em>', content)

            # 리스트 처리
            content = re.sub(r'^- (.*?)$', r'<li>\1</li>', content, flags=re.MULTILINE)
            content = re.sub(r'^\* (.*?)$', r'<li>\1</li>', content, flags=re.MULTILINE)
            content = re.sub(r'^(\d+)\. (.*?)$', r'<li>\2</li>', content, flags=re.MULTILINE)

            # 연속된 <li> 태그를 <ul>로 감싸기
            content = re.sub(r'(<li>.*?</li>\s*)+', lambda m: f'<ul>{m.group(0)}</ul>', content, flags=re.DOTALL)

            # 수평선 처리
            content = re.sub(r'^---+$', r'<hr>', content, flags=re.MULTILINE)
            content = re.sub(r'^\*\*\*+$', r'<hr>', content, flags=re.MULTILINE)

            # 블록 인용 처리
            content = re.sub(r'^> (.*?)$', r'<blockquote>\1</blockquote>', content, flags=re.MULTILINE)

            # 단락 처리 (빈 줄로 구분된 텍스트를 <p> 태그로)
            paragraphs = content.split('\n\n')
            html_paragraphs = []

            for para in paragraphs:
                para = para.strip()
                if para and not para.startswith('<') and '__LINK_PLACEHOLDER_' not in para:
                    para = f'<p>{para}</p>'
                html_paragraphs.append(para)

            content = '\n\n'.join(html_paragraphs)

            # 줄바꿈 처리 - <br> 태그 남용 방지
            # 링크 버튼 내부의 <br>은 보호하되, 일반 텍스트의 줄바꿈은 공백으로 처리
            content = re.sub(r'(?<!>)\n(?!<)', ' ', content)
            
            # 과도한 공백 정리
            content = re.sub(r'\s+', ' ', content)
            content = re.sub(r'>\s+<', '><', content)  # 태그 사이 불필요한 공백 제거

            # 보호한 링크 부분 복원
            for i, link in enumerate(link_patterns):
                content = content.replace(f"__LINK_PLACEHOLDER_{i}__", link)

            return content

        except Exception as e:
            self.log(f"마크다운 변환 중 오류: {e}")
            return content

    def generate_simple_content(self, keyword, content_type="revenue"):
        """간단한 콘텐츠 생성 - 수익용/승인용 선택 가능"""
        try:
            # 콘텐츠 생성 시작 - 포스팅 상태 활성화
            self.is_posting = True

            # 사용 가능한 AI 모델 확인
            if not self.api_status.get('gemini', False) and not self.api_status.get('openai', False):
                self.log("🔥 사용 가능한 AI 모델이 없습니다.")
                self.is_posting = False
                return None, None, None

            self.log(f"👍 콘텐츠 타입: {content_type} (AI 제공자 자동 선택)")

            # 콘텐츠 타입에 따른 생성 방식 선택
            if content_type == "approval":
                # 승인용 콘텐츠 생성
                return self.generate_approval_content(keyword)
            else:
                # 수익용 콘텐츠 생성 (기본값)
                return self.generate_revenue_content(keyword)

        except Exception as e:
            self.log(f"🔥 콘텐츠 생성 중 오류: {e}")
            self.is_posting = False
            return None, None, None

    def generate_revenue_content(self, keyword):
        """수익용 콘텐츠 생성 - 단순화된 버전"""
        self.log("🔄 수익용 콘텐츠 생성을 시작합니다")
        
        # 현재 키워드를 인스턴스 변수로 저장 (URL 복구에서 사용)
        self.current_keyword = keyword
        
        try:
            all_content_parts = []
            title = ""

            # 5단계 순차 실행
            for step_num in range(1, 6):
                # self.log(f"수익용 {step_num}단계 진행 중")
                
                # 중지 체크
                if not self.is_posting:
                    self.log(f"⏹️ {step_num}단계 중지됨")
                    return None, None, None
                
                # 시스템 프롬프트 생성 (prompt 파일 내용 포함)
                system_content = self.get_revenue_system_prompt(step_num, keyword)
                
                # 사용자 프롬프트 - 1단계는 제목도 함께 요청
                if step_num == 1:
                    user_prompt = f"""다음 두 가지를 작성해주세요:

1. 제목: '{keyword} | 숫자가 포함된 후킹문구' 형식 (50-60자)
   예시: "건강검진 예약 | 3분만에 끝내는 간편 신청법"

2. 위에서 제공한 HTML 템플릿에 {keyword}에 맞는 내용을 채워서 완성

첫 번째 줄에 제목만 단독으로 출력하고, 그 다음에 HTML 콘텐츠를 출력해주세요."""
                else:
                    user_prompt = f"{keyword}에 대한 콘텐츠를 작성해주세요."
                
                # AI API 호출
                self.log(f"🤖 {step_num}단계 AI API 호출")
                response_text = self.call_ai_api(
                    user_prompt, f"수익용 {step_num}단계", 
                    max_tokens=1500, 
                    temperature=0.7, 
                    system_content=system_content
                )
                
                if not response_text:
                    self.log(f"❌ {step_num}단계 AI 응답 실패")
                    return None, None, None
                
                # 1단계는 정리 함수 사용하지 않음 (HTML 구조 보존 위해)
                if step_num == 1:
                    step_content = response_text.strip()
                else:
                    # 2-5단계도 HTML 구조 보존 - AI 역할 언급만 제거
                    step_content = response_text.strip()
                    # 간단한 AI 역할 언급만 제거 (HTML 구조는 보존)
                    import re
                    ai_mentions = [
                        r'SEO\s*전문가로서',
                        r'콘텐츠\s*작가로서',
                        r'전문\s*작가로서',
                        r'\d+년\s*경력의?\s*.*?작가로서',
                        r'인공지능.*?',
                        r'AI.*?로서'
                    ]
                    for mention in ai_mentions:
                        step_content = re.sub(mention, '', step_content, flags=re.IGNORECASE)
                    
                    # 마크다운 문법 제거 (HTML 구조는 보존)
                    markdown_patterns = [
                        r'#{1,6}\s+',         # ### 마크다운 헤더
                        r'\*\*([^*]+)\*\*',   # **bold** → 내용만 남기고 제거
                        r'\*([^*]+)\*',       # *italic* → 내용만 남기고 제거
                        r'```[a-z]*',         # ```code 시작
                        r'```',               # ``` 끝
                        r'`([^`]+)`',         # `inline code` → 내용만 남기고 제거
                        r'`html\s*',          # `html 제거
                        r'`javascript\s*',    # `javascript 제거
                        r'`css\s*',           # `css 제거
                        r'`[a-z]+\s*',        # `언어명 제거
                    ]
                    for pattern in markdown_patterns:
                        if pattern in [r'\*\*([^*]+)\*\*', r'\*([^*]+)\*', r'`([^`]+)`']:
                            step_content = re.sub(pattern, r'\1', step_content)  # 내용만 남기고 마크다운 제거
                        else:
                            step_content = re.sub(pattern, '', step_content)
                    
                    # 마크다운 문법 제거 (HTML 구조는 보존)
                    markdown_patterns = [
                        r'#{1,6}\s+',         # ### 마크다운 헤더
                        r'\*\*([^*]+)\*\*',   # **bold** → 제거
                        r'\*([^*]+)\*',       # *italic* → 제거
                        r'```[a-z]*',         # ```code 시작
                        r'```',               # ``` 끝
                        r'`([^`]+)`',         # `inline code` → 제거
                    ]
                    for pattern in markdown_patterns:
                        if pattern in [r'\*\*([^*]+)\*\*', r'\*([^*]+)\*', r'`([^`]+)`']:
                            step_content = re.sub(pattern, r'\1', step_content)  # 내용만 남기고 마크다운 제거
                        else:
                            step_content = re.sub(pattern, '', step_content)
                
                # 1단계에서 제목 추출 및 서론 정리
                if step_num == 1:
                    # 제목 추출 - 더 강력한 로직
                    lines = step_content.split('\n')
                    content_lines = []
                    title_found = False
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        # HTML 태그 제거하여 제목 확인
                        clean_line = line.replace('<h1>', '').replace('</h1>', '').replace('<title>', '').replace('</title>', '')
                        clean_line = clean_line.strip()
                        
                        # 제목 조건: |가 포함되어 있고, HTML 태그로 시작하지 않으며, 적절한 길이
                        if '|' in clean_line and not clean_line.startswith('<') and len(clean_line) > 15 and not title_found:
                            title = clean_line
                            title_found = True
                            continue  # 제목 라인은 본문에서 제외
                        
                        # h1 태그로 된 제목도 제외 (중복 방지)
                        if line.startswith('<h1>') and line.endswith('</h1>'):
                            continue
                            
                        # 나머지는 본문(서론)으로 포함
                        content_lines.append(line)
                    
                    # 제목이 추출되지 않으면 대체 제목 생성
                    if not title:
                        title = f"{keyword} | 5가지 핵심 정보 완벽 정리"
                        self.log(f"⚠️ 제목 추출 실패, 대체 제목 사용: {title}")
                    
                    # 서론 부분만 step_content로 설정 (제목 제외)
                    step_content = '\n'.join(content_lines)
                    self.log(f"✅ 최종 제목: {title}")
                
                # 2-5단계는 추가 정리만 적용
                else:
                    # 마크다운 및 HTML 문서 구조 제거만 추가 적용
                    pass
                
                all_content_parts.append(step_content)
                self.log(f"✅ {step_num}단계 완료")
            
            # 전체 내용 결합
            full_content = "\n\n".join(all_content_parts)
            
            # 체크리스트 감지 및 리스트 코드 추가
            full_content = self.add_checklist_if_needed(full_content, keyword)
            
            # 앱 다운로드 버튼 추가 (필요한 경우) - 플래그 초기화
            self.download_buttons_added = False
            full_content = self.add_download_buttons_to_content(full_content, keyword)
            
            # 가짜 URL 교체 (다운로드 버튼이 없는 경우에만 외부링크 추가)
            full_content = self.replace_fake_urls(full_content, keyword)
            
            # 썸네일 생성
            thumbnail_path = self.create_thumbnail(title, keyword) if title else None
            
            self.log("✅ 수익용 콘텐츠 생성 완료")
            return title, full_content, thumbnail_path
            
        except Exception as e:
            self.log(f"❌ 수익용 콘텐츠 생성 중 오류: {e}")
            return None, None, None

    def replace_fake_urls(self, content, keyword):
        """AI가 생성한 모든 URL을 신뢰할 수 있는 URL로 교체"""
        try:
            import re
            
            # setting.json에서 신뢰할 수 있는 URL 리스트 로드
            trusted_urls = self.load_trusted_urls()
            
            # 1. 가짜 링크 텍스트를 실제 텍스트로 교체
            link_text_patterns = [
                (r'링크\s*텍스트', f'{keyword} 더 알아보기'),
                (r'앵커\s*텍스트', f'{keyword} 바로가기'),
                (r'링크\s*버튼', f'{keyword} 정보'),
                (r'url\s*입력', f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"),
                (r'링크\s*주소', f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"),
                (r'여기에\s*링크', f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"),
            ]
            
            for pattern, replacement in link_text_patterns:
                content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
            
            # 다운로드 버튼이 있는 경우 기존 URL 교체만 수행 (새 링크 추가 안함)
            if hasattr(self, 'download_buttons_added') and self.download_buttons_added:
                self.log("🔗 다운로드 버튼이 이미 추가되어 기존 URL만 교체합니다.")
                
                # 기존 href URL만 교체 (HTML 구조 유지)
                href_pattern = r'href="(https?://[^"]*)"'
                replacement_count = 0
                
                def replace_url(match):
                    nonlocal replacement_count
                    original_url = match.group(1)
                    # 이미 신뢰할 수 있는 URL인지 확인
                    if self.is_trusted_url(original_url, trusted_urls):
                        return match.group(0)  # 원본 그대로 반환
                        
                    # 콘텐츠 맥락과 키워드를 분석하여 적절한 URL 선택
                    replacement_url = self.select_contextual_url(original_url, keyword, content, trusted_urls)
                    replacement_count += 1
                    self.log(f"🔗 기존 URL 교체 ({replacement_count}): {original_url} → {replacement_url}")
                    return f'href="{replacement_url}"'
                
                content = re.sub(href_pattern, replace_url, content)
                
                if replacement_count > 0:
                    self.log(f"✅ 총 {replacement_count}개의 기존 URL이 교체되었습니다.")
                else:
                    self.log("ℹ️ 교체할 URL이 없거나 모든 URL이 이미 신뢰할 수 있는 URL입니다.")
                
                return content
            
            # 다운로드 버튼이 없는 경우: URL 교체 + 외부링크 추가
            # 2. href URL 교체 (HTML 구조 유지)
            href_pattern = r'href="(https?://[^"]*)"'
            replacement_count = 0
            
            def replace_url(match):
                nonlocal replacement_count
                original_url = match.group(1)
                # 이미 신뢰할 수 있는 URL인지 확인
                if self.is_trusted_url(original_url, trusted_urls):
                    return match.group(0)  # 원본 그대로 반환
                    
                # 콘텐츠 맥락과 키워드를 분석하여 적절한 URL 선택
                replacement_url = self.select_contextual_url(original_url, keyword, content, trusted_urls)
                replacement_count += 1
                self.log(f"🔗 URL 교체 ({replacement_count}): {original_url} → {replacement_url}")
                return f'href="{replacement_url}"'
            
            content = re.sub(href_pattern, replace_url, content)
            
            # 3. 외부링크가 부족한 경우 추가
            existing_links = len(re.findall(r'<a\s+[^>]*href=', content, re.IGNORECASE))
            if existing_links < 2:
                # 본문 끝부분에 외부링크 추가
                additional_link_text = f"{keyword} 더 알아보기"
                additional_link_url = self.select_contextual_url("", keyword, content, trusted_urls)
                additional_link = f'<p><a href="{additional_link_url}" target="_blank">{additional_link_text}</a></p>'
                
                content = content.rstrip() + "\n\n" + additional_link
                self.log(f"🔗 외부링크 추가: {additional_link_text} → {additional_link_url}")
                replacement_count += 1
            
            if replacement_count > 0:
                self.log(f"✅ 총 {replacement_count}개의 URL이 신뢰할 수 있는 URL로 교체/추가되었습니다.")
            else:
                self.log("ℹ️ 교체할 URL이 없거나 모든 URL이 이미 신뢰할 수 있는 URL입니다.")
            
            return content
            
        except Exception as e:
            self.log(f"URL 교체 중 오류: {e}")
            return content
    
    def load_trusted_urls(self):
        """setting.json에서 신뢰할 수 있는 URL 리스트 로드"""
        try:
            import json
            config_path = os.path.join(get_base_path(), "setting.json")
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            return config_data.get('trusted_urls', {})
        except Exception as e:
            self.log(f"신뢰할 수 있는 URL 리스트 로드 실패: {e}")
            return {}
    
    def is_trusted_url(self, url, trusted_urls):
        """URL이 신뢰할 수 있는 URL인지 확인"""
        try:
            # 다운로드 버튼 URL들은 항상 신뢰할 수 있는 URL로 처리
            download_button_domains = [
                'www.apple.com',
                'play.google.com', 
                'apps.microsoft.com',
                'tools.applemediaservices.com',
                'upload.wikimedia.org'
            ]
            
            url_domain = url.split('/')[2] if '://' in url else url.split('/')[0]
            
            # 다운로드 버튼 관련 도메인은 교체하지 않음
            if any(domain in url_domain for domain in download_button_domains):
                return True
            
            # 기존 신뢰할 수 있는 URL 확인
            for category, url_list in trusted_urls.items():
                for trusted_url in url_list:
                    # 도메인 기반으로 비교 (쿼리 파라미터 무시)
                    trusted_domain = trusted_url.split('/')[2] if '://' in trusted_url else trusted_url
                    url_domain = url.split('/')[2] if '://' in url else url
                    if trusted_domain in url or url_domain == trusted_domain:
                        return True
            return False
        except Exception:
            return False
    
    def select_contextual_url(self, original_url, keyword, content, trusted_urls):
        """콘텐츠 맥락을 분석하여 가장 적절한 신뢰할 수 있는 URL 선택"""
        try:
            keyword_lower = keyword.lower()
            content_lower = content.lower()
            
            # 원본 URL 주변 텍스트 분석
            import re
            url_context = ""
            url_pattern = re.escape(original_url)
            match = re.search(f'.{{0,100}}{url_pattern}.{{0,100}}', content_lower)
            if match:
                url_context = match.group()
            
            # 키워드와 콘텐츠 맥락 기반 카테고리 선택
            context_text = f"{keyword_lower} {url_context}".lower()
            
            # 자동차 관련
            if any(term in context_text for term in ['자동차', '차량', '견적', '신차', '중고차', '운전', '면허', '대출', '보험']):
                if trusted_urls.get('자동차_관련'):
                    return trusted_urls['자동차_관련'][0]
            
            # 통신 관련
            elif any(term in context_text for term in ['통신', '핸드폰', '휴대폰', '인터넷', '와이파이', '요금제', '모바일']):
                if trusted_urls.get('통신_관련'):
                    return trusted_urls['통신_관련'][0]
            
            # 정부/공공기관 관련
            elif any(term in context_text for term in ['세금', '홈택스', '신고', '납부', '공제', '정부', '공공', '민원']):
                if trusted_urls.get('정부_공공기관'):
                    return trusted_urls['정부_공공기관'][0]
            
            # 금융 관련
            elif any(term in context_text for term in ['은행', '대출', '적금', '예금', '카드', '결제', '금융', '투자']):
                if trusted_urls.get('금융_관련'):
                    return trusted_urls['금융_관련'][0]
            
            # 부동산 관련
            elif any(term in context_text for term in ['부동산', '집', '아파트', '주택', '임대', '매매', '전세', '월세']):
                if trusted_urls.get('부동산_관련'):
                    return trusted_urls['부동산_관련'][0]
            
            # 기본값: 네이버 검색
            if trusted_urls.get('기본_검색'):
                return f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"
            
            # fallback
            return f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"
                
        except Exception as e:
            self.log(f"맥락 분석 중 오류: {e}")
            return f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"

    def fix_broken_urls(self, content):
        """잘린 URL 구조 복구 (URL 내용은 건드리지 않음)"""
        try:
            import re
            
            # 잘린 HTML 링크 구조 복구 패턴들
            broken_patterns = [
                # href가 시작되었지만 닫히지 않은 경우: href="https://... 텍스트
                (r'href\s*=\s*["\']([^"\']*?https?://[^"\'>\s]*?)(\s+[^"\'<>]*?)(?=[<>\n])', 
                 r'href="\1">\2</a>'),
                
                # <a 태그가 시작되었지만 닫히지 않은 경우
                (r'<a\s+([^>]*?)>\s*([^<]*?)(?=\s*<(?!/?a))', 
                 r'<a \1>\2</a>'),
                
                # href 속성에 따옴표가 없는 경우: href=https://...
                (r'href\s*=\s*([^"\'\s>]+)', 
                 r'href="\1"'),
            ]
            
            fix_count = 0
            
            for pattern, replacement in broken_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, replacement, content)
                    fix_count += len(matches)
                    self.log(f"� HTML 링크 구조 복구: {len(matches)}개")
            
            if fix_count > 0:
                self.log(f"✅ 총 {fix_count}개의 링크 구조 복구 완료")
            
            return content
            
        except Exception as e:
            self.log(f"링크 구조 복구 중 오류: {e}")
            return content

    def add_checklist_if_needed(self, content, keyword):
        """체크리스트 키워드 감지 시 리스트 코드 추가"""
        try:
            # 체크리스트 관련 키워드들
            checklist_keywords = [
                '체크리스트', '체크 리스트', 'checklist', '확인 사항', '확인사항',
                '점검 리스트', '점검리스트', '확인 목록', '확인목록', '점검 항목',
                '필수 사항', '필수사항', '준비 사항', '준비사항', '체크 항목'
            ]
            
            # 키워드나 본문에서 체크리스트 관련 키워드 확인
            keyword_lower = keyword.lower()
            content_lower = content.lower()
            
            has_checklist_keyword = any(check_word in keyword_lower for check_word in checklist_keywords)
            has_checklist_content = any(check_word in content_lower for check_word in checklist_keywords)
            
            if has_checklist_keyword or has_checklist_content:
                self.log(f"체크리스트 관련 내용 감지: 리스트 코드 추가")
                
                # 체크리스트 HTML 생성
                checklist_html = f"""
<h3><strong>{keyword} 체크리스트</strong></h3>
<p>{keyword}과 관련된 중요한 체크사항들을 정리해보겠습니다. 아래 항목들을 차례대로 확인해보세요.</p>
<ul>
<li>기본 정보 확인하기</li>
<li>필요한 준비사항 점검하기</li>
<li>관련 문서 및 자료 준비하기</li>
<li>일정 및 시간 계획 세우기</li>
<li>최종 확인 및 검토하기</li>
</ul>
"""
                
                # 첫 번째 h2 태그 이후에 체크리스트 추가
                h2_matches = list(re.finditer(r'<h2[^>]*>.*?</h2>', content, re.IGNORECASE | re.DOTALL))
                
                if h2_matches:
                    first_h2_end = h2_matches[0].end()
                    content = (content[:first_h2_end] + 
                             f"\n\n{checklist_html}\n\n" + 
                             content[first_h2_end:])
                else:
                    # h2 태그가 없으면 본문 앞부분에 추가
                    first_p_match = re.search(r'</p>', content)
                    if first_p_match:
                        insert_position = first_p_match.end()
                        content = (content[:insert_position] + 
                                 f"\n\n{checklist_html}\n\n" + 
                                 content[insert_position:])
                
                self.log("✅ 체크리스트를 본문에 성공적으로 추가했습니다.")
            
            return content
            
        except Exception as e:
            self.log(f"체크리스트 추가 중 오류: {e}")
            return content

    def generate_download_button_html(self, keyword):
        """앱 다운로드 버튼 HTML 생성"""
        try:
            import urllib.parse
            encoded_keyword = urllib.parse.quote(keyword)
            
            download_html = f"""<div class="button-container">
    <p>
        <a href="https://www.apple.com/kr/search/{keyword}?src=globalnav" class="custom-download-btn appstore-button" target="_self">
            <img src="https://upload.wikimedia.org/wikipedia/commons/6/67/App_Store_%28iOS%29.svg" class="btn-logo" alt="App Store">
            <span>App Store에서 바로 다운로드</span>
        </a>
    </p>
    <p>
        <a href="https://play.google.com/store/search?q={keyword}&amp;c=apps" class="custom-download-btn playstore-button" target="_self">
            <img src="https://upload.wikimedia.org/wikipedia/commons/d/d0/Google_Play_Arrow_logo.svg" class="btn-logo" alt="Google Play">
            <span>Google Play에서 바로 다운로드</span>
        </a>
    </p>
    <p>
        <a href="https://apps.microsoft.com/search?query={keyword}&hl=ko-KR&gl=KR" class="custom-download-btn window-button" target="_self">
            <img src="https://upload.wikimedia.org/wikipedia/commons/f/f7/Get_it_from_Microsoft_Badge.svg" class="btn-logo" alt="Microsoft Store">
            <span>Windows에서 바로 다운로드</span>
        </a>
    </p>
    <p>
        <a href="https://www.apple.com/kr/search/{keyword}?src=globalnav" class="custom-download-btn macbook-button" target="_self">
            <img src="https://upload.wikimedia.org/wikipedia/commons/f/fa/Apple_logo_black.svg" class="btn-logo" alt="Mac App Store">
            <span>MacBook에서 바로 다운로드</span>
        </a>
    </p>
</div>"""
            
            return download_html
            
        except Exception as e:
            self.log(f"다운로드 버튼 HTML 생성 오류: {e}")
            return ""

    def generate_random_cta_message(self):
        """다운로드 버튼용 랜덤 행동유도 멘트 생성"""
        cta_messages = [
            "<p style=\"text-align: center;\" data-ke-size=\"size16\"><b>📱지금 바로 <span style=\"color: #ee2323;\">다운로드</span>해서 체험해보세요! 🚀</b></p>",
            "<p style=\"text-align: center;\" data-ke-size=\"size16\"><b>⬇️아래 <span style=\"color: #ee2323;\">링크</span>를 클릭하여 설치하세요! ✨</b></p>",
            "<p style=\"text-align: center;\" data-ke-size=\"size16\"><b>🎯손쉽게 <span style=\"color: #ee2323;\">다운받고</span> 시작해보세요! 💪</b></p>",
            "<p style=\"text-align: center;\" data-ke-size=\"size16\"><b>💡지금 <span style=\"color: #ee2323;\">설치</span>하고 편리함을 경험하세요! 🌟</b></p>",
            "<p style=\"text-align: center;\" data-ke-size=\"size16\"><b>🔥바로 <span style=\"color: #ee2323;\">다운로드</span>해서 활용해보세요! 👍</b></p>",
            "<p style=\"text-align: center;\" data-ke-size=\"size16\"><b>⚡빠르게 <span style=\"color: #ee2323;\">설치</span>하고 이용해보세요! 🎉</b></p>",
            "<p style=\"text-align: center;\" data-ke-size=\"size16\"><b>📥아래에서 <span style=\"color: #ee2323;\">무료 다운로드</span> 가능합니다! 🎁</b></p>",
            "<p style=\"text-align: center;\" data-ke-size=\"size16\"><b>🚀지금 <span style=\"color: #ee2323;\">클릭</span>해서 바로 시작하세요! 💫</b></p>"
        ]
        
        import random
        return random.choice(cta_messages)

    def add_download_buttons_to_content(self, content, keyword):
        """본문 내용에서 '앱 다운'과 관련된 내용을 찾아 다운로드 버튼 추가"""
        try:
            if not content or not keyword:
                return content
            
            # 앱/소프트웨어 관련 키워드들 (더 정확한 필터링)
            app_software_keywords = [
                '앱', '어플', '어플리케이션', '소프트웨어', '프로그램', 
                '설치', '다운로드', '다운받', '내려받',
                '앱스토어', '플레이스토어', 'app store', 'play store',
                '구글플레이', 'google play', '애플스토어',
                '설치하기', '다운로드하기', '받기', '설치해', '다운해',
                '모바일 앱', '데스크톱 앱', 'pc 프로그램', '윈도우 프로그램',
                '게임', '어플게임', '모바일게임'
            ]
            
            # 다운로드와 관련된 키워드들
            download_action_keywords = [
                '다운로드', '다운받', '설치', '받아보', '설치하', '다운하', '내려받',
                '앱을 받', '앱을 다운', '앱 받기', '설치하기',
                '다운로드하기', '내려받기', '받기', '설치해'
            ]
            
            # 제외할 키워드들 (다운로드 버튼이 절대 불필요한 경우)
            exclude_keywords = [
                'gpt', 'chat', '챗', '지피티', 'chatgpt', 'ai', '인공지능',
                '웹사이트', '사이트', '온라인', '브라우저', 'web', 'browser',
                '서비스', '플랫폼', '검색', '정보', '가이드', '방법', '팁',
                '제한', '요금', '가격', '비용', '구독', '무료', '유료', '요금제',
                '사용법', '기능', '특징', '장점', '단점', '비교', '차이점',
                '질문', 'faq', '문의', '문제', '오류', '해결'
            ]
            
            # 키워드 자체가 앱/소프트웨어인지 확인 (단, 제외 키워드는 제외)
            keyword_lower = keyword.lower()
            is_excluded = any(exclude_word in keyword_lower for exclude_word in exclude_keywords)
            
            # 제외 키워드가 있으면 다운로드 버튼 생성하지 않음
            if is_excluded:
                self.log(f"'{keyword}' 키워드는 다운로드와 관련이 없는 내용으로 판단되어 다운로드 버튼을 생성하지 않습니다.")
                return content
            
            is_app_keyword = any(app_word in keyword_lower for app_word in ['앱', '어플', 'app', '프로그램', '소프트웨어', '게임'])
            
            # 본문에서 앱/소프트웨어 관련 키워드 찾기
            content_lower = content.lower()
            has_app_keywords = any(app_word in content_lower for app_word in app_software_keywords)
            has_download_keywords = any(download_word in content_lower for download_word in download_action_keywords)
            
            # 매우 엄격한 조건: 1) 키워드에 앱 관련 단어가 있거나, 2) 본문에 앱과 다운로드 키워드가 모두 있을 때만
            if is_app_keyword or (has_app_keywords and has_download_keywords):
                self.log(f"앱/소프트웨어 관련 키워드와 다운로드 관련 키워드를 발견했습니다. 다운로드 버튼을 추가합니다.")
                
                # 다운로드 버튼 HTML 생성
                download_button_html = self.generate_download_button_html(keyword)
                
                # 랜덤 행동유도 멘트 생성
                random_cta = self.generate_random_cta_message()
                
                # 본문의 적절한 위치에 다운로드 버튼 삽입
                # 첫 번째 <h2> 태그 뒤나 본문 중간 적절한 위치에 삽입
                h2_matches = list(re.finditer(r'<h2[^>]*>.*?</h2>', content, re.IGNORECASE | re.DOTALL))
                
                if h2_matches and len(h2_matches) >= 1:
                    # 첫 번째 h2 태그 이후 적절한 위치 찾기
                    first_h2_end = h2_matches[0].end()
                    
                    # h2 태그 이후 첫 번째 문단 끝에 버튼 추가
                    remaining_content = content[first_h2_end:]
                    p_match = re.search(r'</p>', remaining_content)
                    
                    if p_match:
                        insert_position = first_h2_end + p_match.end()
                        content = (content[:insert_position] + 
                                 f"\n\n{random_cta}\n" +
                                 download_button_html + "\n\n" + 
                                 content[insert_position:])
                    else:
                        # 적절한 위치를 찾지 못했으면 첫 번째 h2 이후에 바로 추가
                        content = (content[:first_h2_end] + 
                                 f"\n\n{random_cta}\n" +
                                 download_button_html + "\n\n" + 
                                 content[first_h2_end:])
                else:
                    # h2 태그가 없으면 본문 처음 문단 이후에 추가
                    first_p_match = re.search(r'</p>', content)
                    if first_p_match:
                        insert_position = first_p_match.end()
                        content = (content[:insert_position] + 
                                 f"\n\n{random_cta}\n" +
                                 download_button_html + "\n\n" + 
                                 content[insert_position:])
                
                self.log("✅ 다운로드 버튼을 본문에 성공적으로 추가했습니다.")
                # 다운로드 버튼이 추가되었음을 표시하는 플래그 설정
                self.download_buttons_added = True
            else:
                self.log(f"앱/소프트웨어 관련 내용이 아니거나 다운로드 언급이 없어 다운로드 버튼을 추가하지 않습니다.")
                self.download_buttons_added = False
            
            return content
            
        except Exception as e:
            self.log(f"다운로드 버튼 추가 중 오류 발생: {e}")
            return content
    # def generate_with_gemini(self, keyword):
    #     """[사용하지 않음] AI 제공자별 구분은 제거됨. generate_content() 사용"""
    #     pass

    def generate_with_openai(self, keyword):
        try:
            # 프롬프트 파일 로드
            prompt_files = [
                "prompt1.txt", "prompt2.txt", "prompt3.txt",
                "prompt4.txt", "prompt5.txt"
            ]

            self.log(f"👍 Gemini 수익용 콘텐츠 생성: {keyword} (5단계 프롬프트 순차 적용)")

            all_content_parts = []
            title = ""

            # 모든 프롬프트 파일을 순차적으로 적용
            for i, prompt_file in enumerate(prompt_files, 1):
                # Worker Thread에서 실행 중일 때는 중지/일시정지 체크를 더 유연하게
                try:
                    # WorkerThread의 상태를 우선 확인
                    if hasattr(self.auto_wp, 'is_posting') and not self.auto_wp.is_posting:
                        self.log(f"🛑 Gemini 콘텐츠 생성이 중지되었습니다. (메인 앱 중지 요청)")
                        return None, None, None
                    
                    # 내부 상태 체크 (더 관대하게)
                    if not getattr(self, 'is_posting', True):
                        self.log(f"🛑 Gemini 콘텐츠 생성이 중지되었습니다. (내부 상태)")
                        return None, None, None
                        
                except AttributeError:
                    # 속성이 없는 경우 계속 진행 (Worker Thread에서는 정상)
                    pass

                # 일시정지 체크 - 메인 클래스의 상태를 확인
                try:
                    is_paused = getattr(self.auto_wp, 'is_paused', False)
                    pause_check_count = 0
                    while is_paused and pause_check_count < 1000:  # 최대 500초(8분) 대기
                        time.sleep(0.5)
                        pause_check_count += 1
                        # 일시정지 중에도 중지 확인
                        if hasattr(self.auto_wp, 'is_posting') and not self.auto_wp.is_posting:
                            return None, None, None
                        is_paused = getattr(self.auto_wp, 'is_paused', False)
                except AttributeError:
                    # 속성이 없는 경우 일시정지 없이 계속 진행
                    # ContentGenerator는 Worker Thread에서 실행되므로 메인 앱의 상태만 체크
                    pass

                prompt_path = os.path.join(get_base_path(), "prompts", "gemini", prompt_file)

                if os.path.exists(prompt_path):
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        prompt_template = f.read()

                    # 키워드 대체
                    prompt = prompt_template.replace("{keyword}", keyword)

                    # 기타 필요한 링크 변수들 처리
                    import urllib.parse
                    encoded_keyword = urllib.parse.quote(keyword)
                    prompt = prompt.replace("{url}", f"https://search.naver.com/search.naver?query={encoded_keyword}")
                    prompt = prompt.replace("{naver_search_link}", f'<a href="https://search.naver.com/search.naver?query={encoded_keyword}" target="_self">{keyword} 관련 정보</a>')
                    prompt = prompt.replace("{youtube_link}", f'<a href="https://tv.naver.com/search?query={encoded_keyword}" target="_self">{keyword} 관련 영상</a>')
                    prompt = prompt.replace("{primary_link}", f'<a href="https://search.naver.com/search.naver?query={encoded_keyword}" target="_self">{keyword} 상세 정보</a>')

                    # 정부 및 공공기관 링크들
                    prompt = prompt.replace("{hometax_link}", '<a href="https://www.hometax.go.kr" target="_self">홈택스 바로가기</a>')
                    prompt = prompt.replace("{lh_link}", '<a href="https://www.lh.or.kr" target="_self">LH 한국토지주택공사</a>')
                    prompt = prompt.replace("{efine_link}", '<a href="https://www.efine.go.kr" target="_self">교통민원24</a>')
                    prompt = prompt.replace("{gov24_link}", '<a href="https://www.gov.kr" target="_self">정부24</a>')
                    prompt = prompt.replace("{wetax_link}", '<a href="https://www.wetax.go.kr" target="_self">위택스</a>')
                    prompt = prompt.replace("{kepco_link}", '<a href="https://cyber.kepco.co.kr" target="_self">한국전력 사이버지점</a>')
                    prompt = prompt.replace("{car365_link}", '<a href="https://www.car365.go.kr" target="_self">자동차365</a>')
                    prompt = prompt.replace("{apply_lh_link}", '<a href="https://apply.lh.or.kr" target="_self">LH청약플러스</a>')
                    prompt = prompt.replace("{bokjiro_link}", '<a href="https://www.bokjiro.go.kr" target="_self">복지로</a>')
                    
                    # 금융기관 링크들
                    prompt = prompt.replace("{kbstar_link}", '<a href="https://www.kbstar.com" target="_self">KB국민은행</a>')
                    prompt = prompt.replace("{shinhan_link}", '<a href="https://www.shinhan.com" target="_self">신한은행</a>')
                    prompt = prompt.replace("{hanabank_link}", '<a href="https://www.hanabank.com" target="_self">하나은행</a>')
                    prompt = prompt.replace("{wooribank_link}", '<a href="https://www.wooribank.com" target="_self">우리은행</a>')
                    prompt = prompt.replace("{ibk_link}", '<a href="https://www.ibk.co.kr" target="_self">IBK기업은행</a>')
                    prompt = prompt.replace("{kdb_link}", '<a href="https://www.kdb.co.kr" target="_self">KDB산업은행</a>')
                    prompt = prompt.replace("{bok_link}", '<a href="https://www.bok.or.kr" target="_self">한국은행</a>')
                    prompt = prompt.replace("{fss_link}", '<a href="https://www.fss.or.kr" target="_self">금융감독원</a>')
                    prompt = prompt.replace("{toss_link}", '<a href="https://toss.im" target="_self">토스</a>')
                    prompt = prompt.replace("{kakaopay_link}", '<a href="https://www.kakaopay.com" target="_self">카카오페이</a>')
                    
                    # 통신 및 유틸리티 링크들
                    prompt = prompt.replace("{tworld_link}", '<a href="https://www.tworld.co.kr" target="_self">T월드</a>')
                    prompt = prompt.replace("{kt_link}", '<a href="https://www.kt.com" target="_self">KT</a>')
                    prompt = prompt.replace("{uplus_link}", '<a href="https://www.uplus.co.kr" target="_self">LG U+</a>')
                    prompt = prompt.replace("{naver_land_link}", '<a href="https://land.naver.com" target="_self">네이버 부동산</a>')
                    prompt = prompt.replace("{zigbang_link}", '<a href="https://www.zigbang.com" target="_self">직방</a>')
                    
                    # 자동차 관련 링크들
                    prompt = prompt.replace("{bobaedream_link}", '<a href="https://www.bobaedream.co.kr" target="_self">보배드림</a>')
                    prompt = prompt.replace("{encar_link}", '<a href="https://www.encar.com" target="_self">엔카</a>')
                    prompt = prompt.replace("{kcar_link}", '<a href="https://www.kcar.com" target="_self">K카</a>')
                    prompt = prompt.replace("{tmap_link}", '<a href="https://www.tmap.co.kr" target="_self">T맵</a>')
                    prompt = prompt.replace("{naver_map_link}", '<a href="https://map.naver.com" target="_self">네이버 지도</a>')
                    prompt = prompt.replace("{kakao_map_link}", '<a href="https://map.kakao.com" target="_self">카카오맵</a>')
                    prompt = prompt.replace("{hyundai_link}", '<a href="https://www.hyundai.com" target="_self">현대자동차</a>')
                    prompt = prompt.replace("{kia_link}", '<a href="https://www.kia.com" target="_self">기아</a>')

                    self.log(f"📝 {i}단계")

                    # 프롬프트 파일 내용을 그대로 사용 (시스템 프롬프트 없이)

                    # 중지 체크 (API 호출 전)
                    if self.should_stop_posting():
                        self.log(f"🛑 Gemini API 호출 전 중지 감지")
                        return None, None, None

                    # Gemini API 호출 (할당량 체크 제거)
                    try:
                        import signal
                        import threading
                        
                        # 타임아웃을 위한 결과 저장 변수
                        api_result = [None]
                        api_error = [None]
                        
                        def api_call():
                            try:
                                # 시스템 프롬프트와 함께 사용
                                system_content = self.get_revenue_system_prompt(i, keyword)
                                full_prompt = f"{system_content}\n\n---\n\n{prompt}"
                                api_result[0] = self.gemini_model.generate_content(full_prompt)
                            except Exception as e:
                                api_error[0] = e
                        
                        # 별도 스레드에서 API 호출
                        api_thread = threading.Thread(target=api_call)
                        api_thread.daemon = True
                        api_thread.start()
                        
                        # 최대 60초 대기 (매 0.5초마다 중지 체크)
                        timeout_count = 0
                        max_timeout = 120  # 60초 (0.5초 * 120)
                        
                        while api_thread.is_alive() and timeout_count < max_timeout:
                            # 중지 체크
                            if self.should_stop_posting():
                                self.log(f"🛑 Gemini API 호출 중 중지 감지")
                                return None, None, None
                            
                            time.sleep(0.5)
                            timeout_count += 1
                        
                        # 타임아웃 체크
                        if api_thread.is_alive():
                            self.log(f"⏰ Gemini API 호출 타임아웃 (60초) - 프롬프트 {i} 건너뜀")
                            continue
                        
                        # 에러 체크
                        if api_error[0]:
                            raise api_error[0]
                        
                        response = api_result[0]

                        # 중지 체크 (API 호출 후)
                        if self.should_stop_posting():
                            self.log(f"🛑 Gemini API 호출 후 중지 감지")
                            return None, None, None

                        # 응답 검증
                        if hasattr(response, 'candidates') and response.candidates:
                            if response.text and response.text.strip():
                                step_content = self.remove_prompt_meta_terms(response.text.strip())

                                # 첫 번째 단계에서 제목 추출 및 본문에서 제거
                                if i == 1 and step_content:
                                    lines = step_content.split('\n')
                                    extracted_title = ""
                                    content_lines = []
                                    title_found = False

                                    for line_idx, line in enumerate(lines):
                                        line = line.strip()
                                        if line and not line.startswith('<') and not title_found and len(line) > 15:
                                            # HTML 태그 제거하여 제목 추출
                                            import re
                                            clean_title = re.sub(r'<[^>]+>', '', line)
                                            clean_title = re.sub(r'^#+\s*', '', clean_title)  # 마크다운 제목 기호 제거
                                            if len(clean_title.strip()) > 10:  # 의미있는 제목인지 확인
                                                extracted_title = clean_title.strip()
                                                title_found = True
                                                # 제목 다음 줄부터 본문으로 사용
                                                content_lines = lines[line_idx + 1:]
                                                break

                                    if extracted_title:
                                        title = extracted_title
                                        # 제목이 제거된 본문만 추가
                                        step_content = '\n'.join(content_lines)

                                all_content_parts.append(step_content)
                                self.log(f"✅ {i}단계")
                            else:
                                self.log(f"📌 {i}단계 빈 응답")
                        else:
                            # 차단된 콘텐츠 처리
                            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                                block_reason = getattr(response.prompt_feedback, 'block_reason', None)
                                if block_reason:
                                    self.log(f"  📌 단계 {i} 콘텐츠 차단됨: {block_reason}")
                                else:
                                    self.log(f"  📌 단계 {i} 알수없는 차단")
                            else:
                                self.log(f"  🔥 단계 {i} 응답 없음")

                    except Exception as step_error:
                        error_str = str(step_error)
                        self.log(f"  ✨ 단계 {i} 오류: {error_str}")

                        # 간단한 오류 분석 (할당량 체크 제거)
                        error_type = self.analyze_api_error(error_str, 'gemini')

                        if error_type == 'TEMPORARY_ERROR':
                            self.log(f"  ⌛ 단계 {i} 일시적 오류 - 10초 대기 후 계속 진행")
                            time.sleep(10)
                        else:
                            self.log(f"  🔥 단계 {i} API 호출 오류: {step_error}")
                        # 단계별 오류 시에도 계속 진행
                else:
                    self.log(f"  🔥 프롬프트 파일 없음: {prompt_file}")

            if not all_content_parts:
                self.log(f"🔥 Gemini 콘텐츠 생성 실패 - 모든 단계 실패")
                return None, None, None

            # 모든 단계의 콘텐츠를 결합
            full_content = "\n\n".join(all_content_parts)

            # 마크다운을 HTML로 변환
            full_content = self.convert_markdown_to_html(full_content)
            
            # HTML 구조 정리 및 오류 수정
            full_content = self.clean_content(full_content)

            if not title:
                # prompt1.txt 제목 지침에 따른 fallback 제목 생성
                # 형식: {keyword} | 숫자포함 후킹문구
                hook_phrases = [
                    "5분만에 끝내는 완벽 가이드", "10가지 핵심 포인트", "3단계로 마스터하기",
                    "7가지 전문가 팁", "2배 효과적인 방법", "30초만에 해결하는 비법",
                    "15분 투자로 평생 활용", "4가지 실무 노하우", "6개월 경험을 압축한 가이드",
                    "9가지 검증된 방법", "1일 1시간으로 완성", "12가지 실전 전략"
                ]
                import random
                hook_phrase = random.choice(hook_phrases)
                title = f"{keyword} | {hook_phrase}"
                self.log(f"📝 자동 생성된 제목: {title}")

            # 썸네일 이미지 선택 및 제목 추가
            thumbnail_filename = self.get_thumbnail_file()
            base_thumbnail_path = os.path.join(get_base_path(), 'images', thumbnail_filename)

            # 제목이 있으면 썸네일에 제목 추가
            thumbnail_path = self.create_thumbnail_with_title(title, keyword)

            self.log(f"✅ Gemini 완료: {title}")
            self.is_posting = False
            return title, full_content, thumbnail_path

        except Exception as e:
            self.log(f"🔥 Gemini 콘텐츠 생성 오류: {e}")
            self.is_posting = False
            return None, None, None

    # def generate_with_openai(self, keyword):
    #     """[사용하지 않음] AI 제공자별 구분은 제거됨. generate_content() 사용"""
    #     pass
        try:
            # 프롬프트 파일 로드
            prompt_files = [
                "prompt1.txt", "prompt2.txt", "prompt3.txt",
                "prompt4.txt", "prompt5.txt"
            ]

            self.log(f"👍 GPT 수익용 콘텐츠 생성: {keyword} (5단계 프롬프트 순차 적용)")

            all_content_parts = []
            title = ""

            # 모든 프롬프트 파일을 순차적으로 적용
            for i, prompt_file in enumerate(prompt_files, 1):
                # 중지/일시정지 체크
                if not self.is_posting:
                    self.log(f"🛑 콘텐츠 생성이 중지되었습니다.")
                    return None, None, None

                while self.is_paused:
                    time.sleep(0.5)
                    if not self.is_posting:
                        return None, None, None

                prompt_path = os.path.join(get_base_path(), "prompts", "gpt", prompt_file)

                if os.path.exists(prompt_path):
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        prompt_template = f.read()

                    # 키워드 대체
                    prompt = prompt_template.replace("{keyword}", keyword)

                    self.log(f"📝 {i}단계")

                    # 중지 체크 (API 호출 전)
                    if not self.is_posting:
                        self.log(f"🛑 API 호출 전 중지 감지")
                        return None, None, None

                    # 시스템 프롬프트와 함께 OpenAI API 호출
                    system_content = self.get_revenue_system_prompt(i, keyword)
                    response = self.openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=3000,
                        temperature=0.7
                    )

                    # 중지 체크 (API 호출 후)
                    if not self.is_posting:
                        self.log(f"🛑 API 호출 후 중지 감지")
                        return None, None, None

                    if response and response.choices and response.choices[0].message.content:
                        step_content = self.remove_prompt_meta_terms(response.choices[0].message.content.strip())
                        all_content_parts.append(step_content)

                        # 첫 번째 단계에서 제목 추출
                        if i == 1 and step_content:
                            lines = step_content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and not line.startswith('<'):
                                    # HTML 태그 제거하여 제목 추출
                                    import re
                                    clean_title = re.sub(r'<[^>]+>', '', line)
                                    if len(clean_title) > 10:  # 의미있는 제목인지 확인
                                        title = clean_title
                                        break

                        self.log(f"✅ {i}단계")
                    else:
                        self.log(f"  🔥 단계 {i} 응답 없음")
                else:
                    self.log(f"  🔥 프롬프트 파일 없음: {prompt_file}")

            if not all_content_parts:
                self.log(f"🔥 GPT 콘텐츠 생성 실패 - 모든 단계 실패")
                return None, None, None

            # 모든 단계의 콘텐츠를 결합
            full_content = "\n\n".join(all_content_parts)

            # 마크다운을 HTML로 변환
            full_content = self.convert_markdown_to_html(full_content)
            
            # HTML 구조 정리 및 오류 수정
            full_content = self.clean_content(full_content)

            if not title:
                # prompt1.txt 제목 지침에 따른 fallback 제목 생성
                # 형식: {keyword} | 숫자포함 후킹문구
                hook_phrases = [
                    "5분만에 끝내는 완벽 가이드", "10가지 핵심 포인트", "3단계로 마스터하기",
                    "7가지 전문가 팁", "2배 효과적인 방법", "30초만에 해결하는 비법",
                    "15분 투자로 평생 활용", "4가지 실무 노하우", "6개월 경험을 압축한 가이드",
                    "9가지 검증된 방법", "1일 1시간으로 완성", "12가지 실전 전략"
                ]
                import random
                hook_phrase = random.choice(hook_phrases)
                title = f"{keyword} | {hook_phrase}"
                self.log(f"📝 자동 생성된 제목: {title}")

            # 썸네일 이미지 선택 및 제목 추가
            thumbnail_filename = self.get_thumbnail_file()
            base_thumbnail_path = os.path.join(get_base_path(), 'images', thumbnail_filename)

            # 제목이 있으면 썸네일에 제목 추가
            thumbnail_path = self.create_thumbnail_with_title(title, keyword)

            self.log(f"✅ GPT 완료: {title}")
            return title, full_content, thumbnail_path

        except Exception as e:
            self.log(f"🔥 OpenAI 콘텐츠 생성 오류: {e}")
            return None, None, None

    def convert_markdown_to_html(self, content):
        """간단한 마크다운을 HTML로 변환 - <br> 태그 남용 방지"""
        if not content:
            return content

        import re

        # 기존 HTML 태그는 보호
        if '<div>' in content or '<p>' in content or '<h2>' in content:
            return content  # 이미 HTML 형태면 그대로 반환

        # 헤딩 변환
        content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
        content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', content, flags=re.MULTILINE)

        # 볼드, 이탤릭 변환
        content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
        content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)

        # 리스트 변환
        content = re.sub(r'^- (.*?)$', r'<li>\1</li>', content, flags=re.MULTILINE)
        content = re.sub(r'(<li>.*?</li>\s*)+', r'<ul>\1</ul>', content, flags=re.DOTALL)

        # 인용구 변환
        content = re.sub(r'^> (.*?)$', r'<blockquote>\1</blockquote>', content, flags=re.MULTILINE)

        # 수평선 변환
        content = re.sub(r'^---$', r'<hr>', content, flags=re.MULTILINE)

        # 단락 처리 - 빈 줄로 구분된 텍스트를 <p> 태그로
        paragraphs = content.split('\n\n')
        html_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<'):
                para = f'<p>{para}</p>'
            html_paragraphs.append(para)
        
        content = '\n'.join(html_paragraphs)

        # 단일 줄바꿈은 공백으로 처리 (<br> 태그 남용 방지)
        content = re.sub(r'(?<!>)\n(?!<)', ' ', content)
        
        # 과도한 공백 정리
        content = re.sub(r'\s+', ' ', content)

        return content

    def upload_thumbnail(self, site_url, username, password, post_id, thumbnail_path):
        """썸네일 이미지 업로드"""
        try:
            if not site_url.endswith('/'):
                site_url += '/'
            media_url = f"{site_url}wp-json/wp/v2/media"

            import base64
            import requests

            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers = {
                'Authorization': f'Basic {credentials}',
            }

            with open(thumbnail_path, 'rb') as img_file:
                files = {
                    'file': (os.path.basename(thumbnail_path), img_file, 'image/jpeg')
                }

                response = requests.post(media_url, files=files, headers=headers, timeout=30)

                if response.status_code == 201:
                    media_id = response.json().get('id')

                    # 포스트에 썸네일 설정
                    post_update_url = f"{site_url}wp-json/wp/v2/posts/{post_id}"
                    update_data = {'featured_media': media_id}
                    headers['Content-Type'] = 'application/json'

                    requests.post(post_update_url, json=update_data, headers=headers, timeout=30)
                    self.log(f"   👍 썸네일 업로드 완료")

        except Exception as e:
            self.log(f"   📌 썸네일 업로드 실패: {e}")

    def create_thumbnail_with_title(self, title, keyword):
        """제목이 포함된 썸네일 이미지를 생성합니다 - image 폴더의 JPG 파일 사용"""
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageEnhance
            from datetime import datetime
            import random
            import textwrap

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # thumbnails 폴더에 썸네일 저장
            output_dir = os.path.join(get_base_path(), "thumbnails")
            os.makedirs(output_dir, exist_ok=True)

            filename = f"thumbnail_{timestamp}.webp"
            filepath = os.path.join(output_dir, filename)

            # image 폴더에서 JPG 파일 찾기
            images_dir = os.path.join(get_base_path(), "images")
            available_images = []

            if os.path.exists(images_dir):
                for file in os.listdir(images_dir):
                    if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                        available_images.append(os.path.join(images_dir, file))

            # 배경 이미지 설정 - 사이트별 설정 우선 사용
            background_path = None
            
            # 현재 사이트의 썸네일 이미지 설정 확인
            if self.current_site and self.current_site.get('thumbnail_image'):
                thumbnail_filename = self.current_site.get('thumbnail_image')
                specific_path = os.path.join(images_dir, thumbnail_filename)
                if os.path.exists(specific_path):
                    background_path = specific_path
                    self.log(f"🖼️ 사이트별 썸네일 이미지 사용: {thumbnail_filename}")
                else:
                    self.log(f"⚠️ 사이트별 썸네일 이미지 파일이 없습니다: {thumbnail_filename}")
            
            # 사이트별 설정이 없거나 파일이 없으면 랜덤 선택
            if not background_path and available_images:
                background_path = random.choice(available_images)
                self.log(f"🖼️ 기본 배경 이미지 사용: {os.path.basename(background_path)}")
            
            if background_path:
                try:
                    # 배경 이미지 로드 및 리사이즈 (300x300 정사각형)
                    background = Image.open(background_path)
                    background = background.resize((300, 300), Image.Resampling.LANCZOS)

                    # 배경 이미지 살짝 어둡게(텍스트 가독성 향상)
                    enhancer = ImageEnhance.Brightness(background)
                    background = enhancer.enhance(0.7)  # 70% 밝기

                    # 반투명 오버레이 추가 (300x300)
                    overlay = Image.new('RGBA', (300, 300), (0, 0, 0, 100))  # 검정색 반투명
                    background = Image.alpha_composite(background.convert('RGBA'), overlay)
                    background = background.convert('RGB')

                except Exception as img_error:
                    self.log(f"배경 이미지 처리 오류: {img_error}, 기본 배경 사용")
                    background = Image.new('RGB', (1200, 630), color=(0, 115, 170))  # WordPress 블루
            else:
                # 이미지가 없으면 기본 그라디언트 배경 생성 (300x300)
                background = Image.new('RGB', (300, 300), color=(0, 115, 170))
                self.log("🎨 기본 그라디언트 배경 사용")

            draw = ImageDraw.Draw(background)

            # 폰트 설정 (한글 지원)
            try:
                # 한글 폰트 우선 시도
                font_paths = [
                    os.path.join(get_base_path(), "fonts", "timon.ttf"),  # 프로젝트 폰트
                    "C:/Windows/Fonts/malgun.ttf",  # 맑은 고딕
                    "C:/Windows/Fonts/gulim.ttc",   # 굴림
                    "arial.ttf"  # 영문 폰트
                ]

                font = None
                for font_path in font_paths:
                    try:
                        if os.path.exists(font_path):
                            font = ImageFont.truetype(font_path, 24)  # 300px에 맞게 폰트 크기 축소
                            break
                    except:
                        continue

                if not font:
                    font = ImageFont.load_default()

            except Exception as font_error:
                self.log(f"폰트 로드 오류: {font_error}")
                font = ImageFont.load_default()

            # 제목 텍스트 처리 (자동 줄바꿈)
            cleaned_title = title.replace('|', '\n')  # | 문자를 줄바꿈으로 변환

            # 텍스트 길이에 따른 자동 줄바꿈 (300px에 맞게 조정)
            max_chars_per_line = 12  # 300px 크기에 맞게 줄임
            if len(cleaned_title) > max_chars_per_line and '\n' not in cleaned_title:
                # textwrap을 사용하여 자동 줄바꿈
                wrapped_lines = textwrap.fill(cleaned_title, width=max_chars_per_line).split('\n')
                text_lines = wrapped_lines
            else:
                text_lines = cleaned_title.split('\n')

            # 최대 3줄로 제한
            if len(text_lines) > 3:
                text_lines = text_lines[:3]
                text_lines[-1] = text_lines[-1][:10] + "" if len(text_lines[-1]) > 10 else text_lines[-1]

            # 텍스트 위치 계산 (중앙 정렬) - 300px에 맞게 조정
            line_height = 30  # 줄 간격 축소
            total_height = len(text_lines) * line_height
            start_y = (300 - total_height) // 2

            # 각 줄을 중앙에 배치
            for i, line in enumerate(text_lines):
                try:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_width = bbox[2] - bbox[0]
                except:
                    # 구형 PIL 버전 호환
                    text_width, _ = draw.textsize(line, font=font)

                x = (300 - text_width) // 2  # 300px 중앙 정렬
                y = start_y + (i * line_height)

                # 텍스트 그림자 효과 (축소)
                shadow_offset = 2  # 그림자 간격 축소
                draw.text((x + shadow_offset, y + shadow_offset), line, fill=(0, 0, 0, 180), font=font)

                # 메인 텍스트 (흰색)
                draw.text((x, y), line, fill=(255, 255, 255), font=font)

            # 키워드 라벨 추가 (선택사항) - 300px에 맞게 조정
            if keyword and len(keyword) <= 10:  # 글자 수 제한 축소
                try:
                    small_font = ImageFont.truetype(font_paths[0] if font_paths and os.path.exists(font_paths[0]) else "arial.ttf", 14)  # 폰트 크기 축소
                except:
                    small_font = font

                keyword_text = f"#{keyword}"
                try:
                    kw_bbox = draw.textbbox((0, 0), keyword_text, font=small_font)
                    kw_width = kw_bbox[2] - kw_bbox[0]
                except:
                    kw_width, _ = draw.textsize(keyword_text, font=small_font)

                kw_x = (300 - kw_width) // 2  # 300px 중앙 정렬
                kw_y = start_y + total_height + 15  # 간격 축소

                # 키워드 배경 박스 (크기 축소)
                padding = 8  # 패딩 축소
                draw.rectangle([kw_x - padding, kw_y - 3, kw_x + kw_width + padding, kw_y + 20],
                              fill=(0, 115, 170, 200), outline=(255, 255, 255))
                draw.text((kw_x, kw_y), keyword_text, fill=(255, 255, 255), font=small_font)

            # WEBP 형식으로 저장 (고품질 적은 용량)
            background.save(filepath, 'WEBP', quality=85, method=6)

            # 썸네일 생성 완료 - 로그 제거
            return filepath

        except Exception as e:
            self.log(f"썸네일 생성 오류: {e}")
            # 백업: 간단한 텍스트 썸네일 생성 (300x300)
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new('RGB', (300, 300), color=(0, 115, 170))  # 300x300 정사각형
                draw = ImageDraw.Draw(img)

                try:
                    font = ImageFont.truetype("arial.ttf", 20)  # 폰트 크기 축소
                except:
                    font = ImageFont.load_default()

                text = title[:30] + "" if len(title) > 30 else title  # 글자 수 축소
                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except:
                    text_width, text_height = draw.textsize(text, font=font)

                x = (300 - text_width) // 2  # 300px 중앙 정렬
                y = (300 - text_height) // 2  # 300px 중앙 정렬

                draw.text((x, y), text, fill=(255, 255, 255), font=font)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(get_base_path(), "thumbnails", f"thumbnail_{timestamp}.webp")
                img.save(filepath, 'WEBP')
                # 기본 썸네일 생성 완료 - 로그 제거
                return filepath
            except:
                return None

    def generate_content(self, keyword):
        """통합된 콘텐츠 생성 함수 - 포스팅 모드에 따라 승인용/수익용 구분"""
        if self.config_manager:
            posting_mode = self.config_manager.data.get("global_settings", {}).get("posting_mode", "수익용")
        else:
            posting_mode = getattr(self.auto_wp, 'posting_mode', '수익용')
            
        if posting_mode == "승인용":
            return self.generate_approval_content(keyword)
        else:
            return self.generate_revenue_content(keyword)

    # def generate_content_with_5_prompts(self, keyword):
    #     """[사용하지 않음] generate_revenue_content() 함수로 통합됨"""
    #     pass
        try:
            # 1단계: 제목 및 서론
            self.log("📝 1단계: 제목 및 서론 생성 중")
            self.log("  ➡️ prompt1.txt 적용 + AI API 호출 중")
            
            # 중지 체크
            if hasattr(self, 'auto_wp') and hasattr(self.auto_wp, 'posting_worker') and not self.auto_wp.posting_worker.is_running:
                self.log("⏹️ 1단계 시작 전 중지됨")
                return None, None, None
            
            title_and_intro = self.execute_prompt_step(1, keyword, "", "", "")
            if not title_and_intro: 
                self.log("❌ 1단계 실패")
                return None, None, None
            
            # 1단계 콘텐츠 정리 (AI 역할 언급 제거, 구조 검증)
            title_and_intro = self.clean_step1_content(title_and_intro)
            
            title, intro = self.extract_title_and_intro(title_and_intro, keyword)
            self.log("✅ 1단계")

            # 2단계: 첫 번째 본문
            self.log("📝 2단계: 첫 번째 본문 생성 중")
            self.log("  ➡️ prompt2.txt 적용 + AI API 호출 중")
            
            # 중지 체크
            if hasattr(self, 'auto_wp') and hasattr(self.auto_wp, 'posting_worker') and not self.auto_wp.posting_worker.is_running:
                self.log("⏹️ 2단계 시작 전 중지됨")
                return None, None, None
            
            body1 = self.execute_prompt_step(2, keyword, "", "", f"제목: {title}\n서론: {intro}")
            if not body1: 
                self.log("❌ 2단계 실패")
                return None, None, None
            self.log("  ✅ 2단계 완료")

            # 3단계: 두 번째 본문
            self.log("📝 3단계: 두 번째 본문 생성 중")
            self.log("  ➡️ prompt3.txt 적용 + AI API 호출 중")
            
            # 중지 체크
            if hasattr(self, 'auto_wp') and hasattr(self.auto_wp, 'posting_worker') and not self.auto_wp.posting_worker.is_running:
                self.log("⏹️ 3단계 시작 전 중지됨")
                return None, None, None
            
            body2 = self.execute_prompt_step(3, keyword, "", "", f"제목: {title}\n서론: {intro}\n첫 번째 본문: {body1}")
            if not body2: 
                self.log("❌ 3단계 실패")
                return None, None, None
            self.log("  ✅ 3단계 완료")

            # 4단계: 세 번째 본문
            self.log("📝 4단계: 세 번째 본문 생성 중")
            self.log("  ➡️ prompt4.txt 적용 + AI API 호출 중")
            
            # 중지 체크
            if hasattr(self, 'auto_wp') and hasattr(self.auto_wp, 'posting_worker') and not self.auto_wp.posting_worker.is_running:
                self.log("⏹️ 4단계 시작 전 중지됨")
                return None, None, None
            
            body3 = self.execute_prompt_step(4, keyword, "", "", f"제목: {title}\n서론: {intro}\n첫 번째 본문: {body1}\n두 번째 본문: {body2}")
            if not body3: 
                self.log("❌ 4단계 실패")
                return None, None, None
            self.log("  ✅ 4단계 완료")

            # 5단계: 표, 자주 묻는 질문
            self.log("📝 5단계: 표 및 FAQ 생성 중")
            self.log("  ➡️ prompt5.txt 적용 + AI API 호출 중")
            
            # 중지 체크
            if hasattr(self, 'auto_wp') and hasattr(self.auto_wp, 'posting_worker') and not self.auto_wp.posting_worker.is_running:
                self.log("⏹️ 5단계 시작 전 중지됨")
                return None, None, None
            
            final_part = self.execute_prompt_step(5, keyword, "", "", f"제목: {title}\n서론: {intro}\n첫 번째 본문: {body1}\n두 번째 본문: {body2}\n세 번째 본문: {body3}")
            if not final_part: 
                self.log("❌ 5단계 실패")
                return None, None, None
            
            # 5단계 콘텐츠 검증 (표와 FAQ 구조 확인)
            final_part = self.clean_step5_content(final_part)
            self.log("  ✅ 5단계 완료")

            # 최종 콘텐츠 조합 및 후처리
            self.log("🔧 콘텐츠 조합 및 후처리 중")
            # intro는 서론만 포함하도록 처리 (제목은 이미 별도로 추출됨)
            final_content = f"{intro}\n\n{body1}\n\n{body2}\n\n{body3}\n\n{final_part}"
            
            # URL 변수 치환 먼저 수행
            final_content = self.replace_prompt_variables(final_content, keyword, [], [], "")
            
            # 콘텐츠 정리 수행
            final_content = self.clean_content(final_content, keyword)
            
            self.log("🖼️ 썸네일 생성 중")
            thumbnail_path = self.create_thumbnail(title, keyword)
            
            self.log(f"✅ 5단계 수익용 콘텐츠 생성 완료: {title}")
            
            return title, final_content, thumbnail_path

        except Exception as e:
            self.log(f"❌ 5단계 프롬프트 처리 중 오류 발생: {e}")
            return None, None, None

    def generate_approval_content_internal(self, keyword):
        """승인용 콘텐츠 생성 (3단계 방식)"""
        self.log("🔄 승인용 콘텐츠 생성을 시작합니다")
        try:
            title = ""
            content_parts = []
            
            for step in range(1, 4):
                # self.log(f"📝 승인용 {step}단계 진행 중")
                
                # 중지 체크
                if hasattr(self, 'auto_wp') and hasattr(self.auto_wp, 'posting_worker') and not self.auto_wp.posting_worker.is_running:
                    self.log(f"⏹️ 승인용 {step}단계 시작 전 중지됨")
                    return None, None, None
                
                approval_file = os.path.join(get_base_path(), "prompts", f"approval{step}.txt")
                if not os.path.exists(approval_file):
                    self.log(f"⚠️ approval{step}.txt 파일을 찾을 수 없습니다.")
                    continue
                    
                with open(approval_file, 'r', encoding='utf-8') as f:
                    prompt = f.read().replace("{keyword}", keyword)

                # 이전 단계 결과를 다음 프롬프트에 포함
                if step > 1:
                    prompt += f"\n\n이전 단계 내용:\n" + "\n".join(content_parts)
                
                # 시스템 프롬프트는 각 단계별로 특화된 지침을 포함
                system_content = self.get_approval_system_prompt(step, keyword)

                response_text = self.call_ai_api(
                    prompt, f"승인용 {step}단계", max_tokens=3000, system_content=system_content
                )
                if not response_text: 
                    self.log(f"❌ 승인용 {step}단계 실패")
                    return None, None, None

                # 1단계에서 제목 추출
                if step == 1:
                    title, intro_content = self.extract_approval_title_and_intro(response_text, keyword)
                    content_parts.append(intro_content)
                    self.log(f"✅ 승인용 {step}단계 완료: 제목 및 서론 생성됨")
                else:
                    content_parts.append(response_text.strip())
                    self.log(f"✅ 승인용 {step}단계 완료: 본문 생성됨")

                self.log(f"승인용 {step}단계 완료")

            full_content = "\n\n".join(content_parts)
            thumbnail_path = self.create_thumbnail(title, keyword)
            return title, full_content, thumbnail_path
        except Exception as e:
            self.log(f"승인용 콘텐츠 생성 중 오류 발생: {e}")
            return None, None, None

    def execute_prompt_step(self, step_num, keyword, urls, anchor_links, context):
        """각 프롬프트 단계를 실행하고 AI API를 호출하는 헬퍼 함수"""
        try:
            # 중지 체크
            if hasattr(self, 'auto_wp') and hasattr(self.auto_wp, 'posting_worker') and not self.auto_wp.posting_worker.is_running:
                self.log(f"⏹️ {step_num}단계 실행 전 중지됨")
                return None
            
            prompt_file = os.path.join(get_base_path(), "prompts", f"prompt{step_num}.txt")
            if not os.path.exists(prompt_file):
                self.log(f"⚠️ prompt{step_num}.txt 파일을 찾을 수 없습니다.")
                return None
                
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_content = f.read()

            prompt = self.replace_prompt_variables(prompt_content, keyword, urls, anchor_links, context)
            
            # HTML 구조 준수를 위한 시스템 프롬프트 추가
            system_prompt = f"""너는 전문 SEO 콘텐츠 작가야.

**절대적으로 준수해야 할 규칙:**

1. **제목 형식 (1단계에만 해당) - 매우 중요!**: 
   - 100% 무조건 "{keyword} | 숫자포함 후킹문구" 형식만 허용
   - 절대 금지: "- 완벽 가이드", "- 완벽 설명", "- 방법", "- 노하우" 형식
   - 정확한 예시: "{keyword} | 10분만에 완성하는 5가지 방법"
   - 잘못된 예시: "{keyword} - 완벽 가이드" (절대 사용 금지)
   - 반드시 파이프(|) 기호 사용, 숫자 필수 포함

2. **HTML 구조 100% 완전 준수**: 
   - 프롬프트 끝부분의 HTML 예시를 한 글자도 빠뜨리지 말고 정확히 복사해
   - 모든 태그 정확히 열고 닫기: <p></p>, <div></div>, <center></center>
   - class와 style 속성을 정확히 그대로 복사해
   - 절대 임의로 태그 변경하거나 생략하지 말 것
   - href="url" 부분은 {{url}}로 변경하지 말고 "url"로 그대로 유지해

3. **변수 처리**: 
   - {{keyword}}, {{url}} 등 중괄호 변수는 절대 사용 금지
   - 변수 부분은 프롬프트 예시대로 정확히 작성해

4. **출력 형식**: 
   - 프롬프트의 HTML 예시만 출력해
   - 설명, 주석, 코멘트 등 일체 금지
   - 예시에 없는 추가 태그나 내용 절대 금지

5. **1단계 특별 주의사항**:
   - 제목은 반드시 "{keyword} |" 로 시작해
   - 서론에 제목 중복 절대 금지
   - AI 역할 언급 금지 ("SEO 작가로서", "전문가로서" 등)
   - 1단계는 오직 제목+서론+링크버튼만 생성
   - h2 소제목이나 본문 내용 절대 금지
   - HTML 예시 구조 정확히 따라야 해

6. **5단계 특별 주의사항**:
   - prompt5.txt에 명시된 대로 반드시 '표'와 '자주 묻는 질문 5개' 모두 작성
   - 표는 3행 3-4열 구성으로 비교 정보 제공
   - FAQ는 Q1~Q5까지 총 5개 질문과 답변 완전 작성
   - 각 답변은 200-300자로 작성
   - HTML 구조를 정확히 따라야 함

현재 {step_num}단계야. 프롬프트의 HTML 예시를 정확히 복사해서 내용만 채워 넣어."""
            
            max_tokens = 3000 if step_num == 5 else 1500
            result = self.call_ai_api(
                prompt, f"{step_num}단계", max_tokens=max_tokens, temperature=0.7, system_content=system_prompt
            )
            return result
        except Exception as e:
            self.log(f"{step_num}단계 처리 중 오류: {e}")
            return None

    def create_thumbnail(self, title, keyword):
        """썸네일 이미지를 생성합니다."""
        try:
            # images 폴더에서 사이트별 또는 무작위 배경 이미지 선택
            images_dir = os.path.join(get_base_path(), "images")
            background_path = None
            
            if os.path.exists(images_dir):
                available_images = [os.path.join(images_dir, f) for f in os.listdir(images_dir) 
                                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                # 현재 사이트의 썸네일 이미지 설정 확인
                if self.current_site and self.current_site.get('thumbnail_image'):
                    thumbnail_filename = self.current_site.get('thumbnail_image')
                    specific_path = os.path.join(images_dir, thumbnail_filename)
                    if os.path.exists(specific_path):
                        background_path = specific_path
                        self.log(f"🎯 사이트별 썸네일 이미지 사용: {thumbnail_filename}")
                    else:
                        self.log(f"⚠️ 사이트별 썸네일 이미지 파일이 없습니다: {thumbnail_filename}")
                
                # 사이트별 설정이 없거나 파일이 없으면 랜덤 선택
                if not background_path and available_images:
                    background_path = random.choice(available_images)
                    self.log(f"🖼️ 기본 배경 이미지 사용: {os.path.basename(background_path)}")
                
                if background_path:
                    background = Image.open(background_path)
                    # 이미지를 300x300 정사각형으로 크롭 및 리사이즈
                    background = background.resize((300, 300), Image.Resampling.LANCZOS)
                else:
                    background = Image.new('RGB', (300, 300), color=(41, 128, 185)) # 기본 배경
            else:
                background = Image.new('RGB', (300, 300), color=(41, 128, 185)) # 기본 배경

            draw = ImageDraw.Draw(background)
            
            # 폰트 설정 - 본문과 동일한 timon.ttf 사용
            try:
                # fonts 폴더의 timon.ttf 폰트 사용 (본문과 동일)
                font_path = os.path.join(get_base_path(), "fonts", "timon.ttf")
                font = ImageFont.truetype(font_path, 28)  # 크기 약간 증가
            except Exception as font_error:
                print(f"timon.ttf 폰트 로드 실패: {font_error}")
                try:
                    # 대체 폰트들
                    font = ImageFont.truetype("C:/Windows/Fonts/gulim.ttc", 24)
                except:
                    try:
                        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 24)
                    except:
                        font = ImageFont.load_default()

            # 제목 텍스트를 이미지 중앙에 그리기 (간단한 버전)
            # 제목이 너무 길면 줄바꿈
            words = title.split()
            lines = []
            current_line = []
            
            for word in words:
                test_line = ' '.join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=font)
                if bbox[2] - bbox[0] > 250:  # 250px 이상이면 줄바꿈
                    if current_line:
                        lines.append(' '.join(current_line))
                        current_line = [word]
                    else:
                        lines.append(word)
                        current_line = []
                else:
                    current_line.append(word)
            
            if current_line:
                lines.append(' '.join(current_line))
                
            # 텍스트 중앙 정렬
            y_start = 150 - (len(lines) * 15)  # 대략적인 중앙 위치
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                x = (300 - (bbox[2] - bbox[0])) // 2
                y = y_start + (i * 30)
                draw.text((x, y), line, fill=(255, 255, 255), font=font)
            
            # 최종 이미지를 WebP 형식으로 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(get_base_path(), "thumbnails", f"thumbnail_{timestamp}.webp")
            background.save(filepath, 'WEBP', quality=85)
            return filepath
        except Exception as e:
            self.log(f"썸네일 생성 오류: {e}")
            return None

    def post_to_wordpress(self, site_data, title, content, thumbnail_path=None):
        """워드프레스에 포스트를 게시합니다."""
        try:
            site_name = site_data.get('name', 'Unknown')
            site_url = site_data.get('url')
            username = site_data.get('username')
            password = site_data.get('password')
            category = site_data.get('category_id', 1)

            # WordPress REST API URL 구성
            api_url = f"{site_url.rstrip('/')}/wp-json/wp/v2/posts"
            
            # 여러 인증 방법 시도
            auth_success, headers = self.try_authentication_methods(site_name, site_url, username, password)
            
            if not auth_success:
                # 비밀번호 힌트 생성
                password_hint = password[:4] + "***" + password[-4:] if len(password) > 8 else password[:2] + "***"
                
                return {'success': False, 'error': 'Authentication failed'}

            post_data = {
                'title': title,
                'content': content,
                'status': 'publish',
                'categories': [int(category)]
            }

            session = get_requests_session()
            response = session.post(api_url, headers=headers, json=post_data, timeout=30)

            if response.status_code == 201:
                post_info = response.json()
                post_id = post_info['id']
                self.log(f"📤 포스트 업로드 성공 {site_name}")

                # 썸네일 업로드
                if thumbnail_path and os.path.exists(thumbnail_path):
                    media_id = self.upload_featured_image(site_url, headers, thumbnail_path, post_id)
                    if media_id:
                        self.log(f"🖼️ 썸네일 업로드 완료 {site_name}")
                    else:
                        self.log(f"⚠️ {site_name}: 썸네일 업로드 실패 (포스트는 성공)")
                
                # HTML 콘텐츠를 output 폴더에 저장
                try:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_dir = os.path.join(get_base_path(), "output")
                    os.makedirs(output_dir, exist_ok=True)
                    
                    # 사이트 이름에서 파일명에 사용할 수 없는 문자 제거
                    safe_site_name = "".join(c for c in site_name if c.isalnum() or c in ('-', '_', '.')).rstrip()
                    if not safe_site_name:
                        safe_site_name = "site"
                    
                    # HTML 파일 저장
                    html_filename = f"{safe_site_name}_{timestamp}_post_{post_id}.html"
                    html_filepath = os.path.join(output_dir, html_filename)
                    
                    # 전체 HTML 구조로 저장 (제목 포함)
                    full_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body>
    <h1>{title}</h1>
    {content}
</body>
</html>"""
                    
                    with open(html_filepath, 'w', encoding='utf-8') as f:
                        f.write(full_html)
                    
                    self.log(f"💾 HTML 저장 완료: {html_filename}")
                except Exception as e:
                    self.log(f"⚠️ HTML 저장 실패: {e}")
                
                return {'success': True, 'post_id': post_id}
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_msg += f" - {error_data['message']}"
                    if 'code' in error_data:
                        error_msg += f" (코드: {error_data['code']})"
                except:
                    error_msg += f" - {response.text[:200]}"
                
                self.log(f"❌ {site_name}: 포스팅 실패: {error_msg}")
                return {'success': False, 'error': error_msg}
        except Exception as e:
            self.log(f"❌ {site_name}: 워드프레스 포스팅 오류: {e}")
            return {'success': False, 'error': str(e)}

    def try_authentication_methods(self, site_name, site_url, username, password):
        """다양한 인증 방법을 시도합니다"""
        session = get_requests_session()
        user_url = f"{site_url.rstrip('/')}/wp-json/wp/v2/users/me"
        
        # 비밀번호 힌트 생성 (보안을 위해 일부만 표시)
        password_hint = password[:4] + "***" + password[-4:] if len(password) > 8 else password[:2] + "***"
        
        # WordPress REST API 접근성 확인
        self.check_rest_api_accessibility(site_name, site_url)
        
        # 방법 1: Application Password (공백 포함)
        headers1 = self.create_auth_header(username, password, "Application Password with spaces")
        if self.test_auth_method(session, user_url, headers1, site_name, "Application Password (공백포함)", username, password_hint):
            return True, headers1
        
        # 방법 2: Application Password (공백 제거)
        password_no_spaces = password.replace(" ", "")
        self.log(f"🔑 {site_name}: 방법 2 - Application Password (공백 제거) 시도")
        self.log(f"🔧 {site_name}: 공백 제거된 비밀번호 길이: {len(password_no_spaces)}자")
        headers2 = self.create_auth_header(username, password_no_spaces, "Application Password without spaces")
        if self.test_auth_method(session, user_url, headers2, site_name, "Application Password (공백제거)", username, password_hint):
            return True, headers2
        
        # 방법 3: 기본 Basic Auth
        self.log(f"🔑 {site_name}: 방법 3 - 기본 Basic Auth 시도")
        headers3 = self.create_auth_header(username, password, "Basic Auth")
        if self.test_auth_method(session, user_url, headers3, site_name, "Basic Auth", username, password_hint):
            return True, headers3
        
        # 방법 4: WordPress 기본 인증 (username@domain 형식)
        if '@' not in username and site_url:
            domain = site_url.replace('https://', '').replace('http://', '').split('/')[0]
            username_with_domain = f"{username}@{domain}"
            headers4 = self.create_auth_header(username_with_domain, password, "Domain Auth")
            if self.test_auth_method(session, user_url, headers4, site_name, "도메인 포함 인증", username_with_domain, password_hint):
                return True, headers4
            
            # 방법 5: 도메인 포함 + 공백 제거
            self.log(f"🔑 {site_name}: 방법 5 - 도메인 포함 + 공백 제거 시도")
            headers5 = self.create_auth_header(username_with_domain, password_no_spaces, "Domain Auth + No Spaces")
            if self.test_auth_method(session, user_url, headers5, site_name, "도메인 포함 + 공백제거", username_with_domain, password_hint):
                return True, headers5
        
        # 모든 인증 방법 실패 시 자세한 가이드 제공
        self.provide_authentication_guide(site_name, site_url, username)
        
        return False, None

    def check_rest_api_accessibility(self, site_name, site_url):
        """WordPress REST API 접근성 확인"""
        try:
            # REST API 엔드포인트 확인
            api_base_url = f"{site_url.rstrip('/')}/wp-json/wp/v2"
            
            session = get_requests_session()
            response = session.get(api_base_url, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                return False
                
        except Exception as e:
            return False

    def provide_authentication_guide(self, site_name, site_url, username):
        """인증 실패 시 상세한 가이드 제공"""
        pass  # 로그 제거됨

    def create_auth_header(self, username, password, method_name):
        """인증 헤더 생성"""
        import base64
        credentials = f"{username}:{password}"
        token = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
        
        return {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'Auto-WP/1.0'
        }

    def test_auth_method(self, session, user_url, headers, site_name, method_name, username="", password_hint=""):
        """인증 방법 테스트"""
        try:
            response = session.get(user_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                user_info = response.json()
                user_name = user_info.get('name', 'Unknown')
                return True
            else:
                # 인증 실패 시 사용자명과 비밀번호 힌트 표시
                if username:
                    self.log(f"❌ {site_name}: {method_name} 인증 실패 (HTTP {response.status_code}) - 사용자명: '{username}', 비밀번호: '{password_hint}'")
                else:
                    self.log(f"❌ {site_name}: {method_name} 인증 실패 (HTTP {response.status_code})")
                return False
        except Exception as e:
            if username:
                self.log(f"❌ {site_name}: {method_name} 인증 중 오류: {e} - 사용자명: '{username}', 비밀번호: '{password_hint}'")
            else:
                self.log(f"❌ {site_name}: {method_name} 인증 중 오류: {e}")
            return False

    def upload_featured_image(self, site_url, headers, image_path, post_id):
        """특성 이미지(썸네일) 업로드"""
        try:
            media_url = f"{site_url}/wp-json/wp/v2/media"
            
            with open(image_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(image_path), f, 'image/webp')
                }
                headers_upload = {'Authorization': headers['Authorization']}
                
                session = get_requests_session()
                response = session.post(media_url, headers=headers_upload, files=files, timeout=30)
                
                if response.status_code == 201:
                    media_info = response.json()
                    media_id = media_info['id']
                    
                    # 포스트에 특성 이미지 설정
                    post_url = f"{site_url}/wp-json/wp/v2/posts/{post_id}"
                    update_data = {'featured_media': media_id}
                    
                    session.post(post_url, headers=headers, json=update_data, timeout=30)
                    return media_id
                else:
                    self.log(f"⚠️ 썸네일 업로드 실패: {response.status_code}")
                    return None
        except Exception as e:
            self.log(f"❌ 썸네일 업로드 오류: {e}")
            return None

    def clean_content(self, content, keyword=None):
        """콘텐츠 정리 및 최적화 - HTML 구조 완전 정리"""
        if not content:
            return content
            
        # 기본 정리 작업들
        content = content.strip()
        
        # 1. 깨진 HTML 태그 수정
        # 불완전한 태그 패턴들 수정
        content = re.sub(r'<p[^>]*>\s*<p[^>]*>', '<p>', content, flags=re.IGNORECASE)
        content = re.sub(r'</p>\s*</p>', '</p>', content, flags=re.IGNORECASE)
        content = re.sub(r'<div[^>]*>\s*<div[^>]*>', '<div>', content, flags=re.IGNORECASE)
        content = re.sub(r'</div>\s*</div>', '</div>', content, flags=re.IGNORECASE)
        
        # 2. 색상 스타일 속성이 깨진 경우 수정
        content = re.sub(r'<span style="color:\s*"[^>]*>', '<span style="color: #ee2323;">', content, flags=re.IGNORECASE)
        content = re.sub(r'<span style="color:\s+[^"]*"', '<span style="color: #ee2323;"', content, flags=re.IGNORECASE)
        content = re.sub(r'style="color:\s*//[^"]*"', 'style="color: #ee2323;"', content, flags=re.IGNORECASE)
        content = re.sub(r'style="color:\s*#ee2323[^"]*"', 'style="color: #ee2323;"', content, flags=re.IGNORECASE)
        
        # 2-1. 더 강력한 깨진 HTML 속성 수정
        # style 속성이 URL로 잘못 들어간 경우 완전 수정
        content = re.sub(r'<span style="color:\s*//[^"]*"[^>]*>', '<span style="color: #ee2323;">', content, flags=re.IGNORECASE)
        content = re.sub(r'<span[^>]*style="[^"]*//[^"]*"[^>]*>', '<span style="color: #ee2323;">', content, flags=re.IGNORECASE)
        
        # href 속성에 잘못된 URL이 들어간 경우 수정
        if keyword:
            search_url = f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"
            content = re.sub(r'href="[^"]*//search\.naver\.com[^"]*"', f'href="{search_url}"', content, flags=re.IGNORECASE)
            content = re.sub(r'href="//[^"]*"', f'href="{search_url}"', content, flags=re.IGNORECASE)
            
        # 2-2. 깨진 링크 구조 완전 복구
        # 잘못된 패턴: style="color: //search.naver.com..." target="_self">텍스트</a>
        # 올바른 패턴으로 수정
        if keyword:
            pattern = r'style="color:\s*//[^"]*"\s*target="_self">([^<]*)</a>'
            replacement = f'style="color: #ee2323;">{keyword} 상세정보</span>을 통해, 지금 바로 해보세요!</b></p><br><div><center><a class="blink" href="{search_url}" target="_self">\\1</a>'
            content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        
        # 3. 불완전한 닫는 태그들 정리
        content = re.sub(r'</strong>\s*새우,', '</strong>', content, flags=re.IGNORECASE)
        content = re.sub(r'</h4>\s*<br>\s*<p>', '</h4>\n<p>', content, flags=re.IGNORECASE)
        
        # 4. 테이블 태그가 깨진 경우 정리
        content = re.sub(r'<td[^>]*>\s*<td[^>]*>', '<td>', content, flags=re.IGNORECASE)
        content = re.sub(r'</td>\s*</td>', '</td>', content, flags=re.IGNORECASE)
        
        # 5. 과도한 <br> 태그 정리 - 연속된 3개 이상의 <br>만 제거
        content = re.sub(r'(<br\s*/?>\s*){3,}', '<br><br>', content, flags=re.IGNORECASE)
        
        # 6. HTML 태그 간 불필요한 <br> 제거
        content = re.sub(r'</p>\s*<br\s*/?>\s*<p>', '</p>\n<p>', content, flags=re.IGNORECASE)
        content = re.sub(r'</h[1-6]>\s*<br\s*/?>\s*<p>', '</h2>\n<p>', content, flags=re.IGNORECASE)
        content = re.sub(r'</div>\s*<br\s*/?>\s*<div>', '</div>\n<div>', content, flags=re.IGNORECASE)
        
        # 7. 시작과 끝의 불필요한 <br> 제거
        content = re.sub(r'^(<br\s*/?>\s*)+', '', content, flags=re.IGNORECASE)
        content = re.sub(r'(<br\s*/?>\s*)+$', '', content, flags=re.IGNORECASE)
        
        # 8. 링크 태그를 보호하면서 처리
        link_pattern = r'<a[^>]*>.*?</a>'
        links = re.findall(link_pattern, content, flags=re.IGNORECASE | re.DOTALL)
        
        # 임시 플레이스홀더로 링크 교체
        temp_content = content
        for i, link in enumerate(links):
            temp_content = temp_content.replace(link, f"__LINK_PLACEHOLDER_{i}__", 1)
        
        # 링크가 없는 부분에서 과도한 <br> 제거 (2개 연속까지만 허용)
        temp_content = re.sub(r'(<br\s*/?>\s*){3,}', '<br><br>', temp_content, flags=re.IGNORECASE)
        
        # 링크 복원
        for i, link in enumerate(links):
            temp_content = temp_content.replace(f"__LINK_PLACEHOLDER_{i}__", link, 1)
        
        content = temp_content
        
        # 9. 불완전한 HTML 태그 정리
        content = re.sub(r'<strong>\s*</strong>', '', content, flags=re.IGNORECASE)
        content = re.sub(r'</strong>\s*<strong>', ' ', content, flags=re.IGNORECASE)
        
        # 10. 잘못된 HTML 구조 정리
        content = re.sub(r'<p[^>]*>\s*</p>', '', content, flags=re.IGNORECASE)  # 빈 p 태그 제거
        
        # 11. 중복된 제목이나 내용 제거
        lines = content.split('\n')
        seen_lines = set()
        seen_content = set()
        unique_lines = []
        
        for line in lines:
            # 제목 패턴 중복 체크 (h2, h3 태그)
            title_match = re.search(r'<h[2-3][^>]*>(.+?)</h[2-3]>', line, flags=re.IGNORECASE)
            if title_match:
                title_text = title_match.group(1).strip()
                if title_text not in seen_lines:
                    seen_lines.add(title_text)
                    unique_lines.append(line)
            else:
                # 일반 내용 중복 체크 (HTML 태그 제거 후 비교)
                clean_line = re.sub(r'<[^>]*>', '', line).strip()
                if clean_line:
                    # 너무 짧거나 의미없는 내용 제거
                    if len(clean_line) > 10 and clean_line not in seen_content:
                        # 비슷한 내용 체크 (80% 이상 유사하면 중복으로 간주)
                        is_duplicate = False
                        for existing_content in seen_content:
                            if len(existing_content) > 10:
                                similarity = self.similarity_ratio(clean_line, existing_content)
                                if similarity > 0.8:
                                    is_duplicate = True
                                    break
                        
                        if not is_duplicate:
                            seen_content.add(clean_line)
                            unique_lines.append(line)
                    elif len(clean_line) <= 10:
                        # 짧은 라인은 중복 체크 없이 추가 (HTML 태그만 있는 경우 등)
                        unique_lines.append(line)
                else:
                    # 빈 라인도 유지
                    unique_lines.append(line)
        
        content = '\n'.join(unique_lines)
        
        # 12. 깨진 HTML 구조 복구
        # 닫히지 않은 태그들을 찾아서 정리
        open_tags = []
        tag_pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9]*)[^>]*>'
        
        for match in re.finditer(tag_pattern, content):
            is_closing = match.group(1) == '/'
            tag_name = match.group(2).lower()
            
            if not is_closing:
                # 자체 닫힘 태그가 아닌 경우에만 추가
                if tag_name not in ['br', 'img', 'hr', 'input', 'meta', 'link']:
                    open_tags.append(tag_name)
            else:
                # 닫는 태그인 경우 매칭되는 열린 태그 제거
                if open_tags and open_tags[-1] == tag_name:
                    open_tags.pop()
        
        # 13. 끝부분의 불완전한 내용 제거
        # 의미없는 단어들이나 불완전한 문장, 깨진 HTML 구조 제거
        content = re.sub(r'\s*(당근|단호|center|table|td|tr|color|style|href)\s*$', '', content, flags=re.IGNORECASE)
        content = re.sub(r'<[^>]*>?\s*$', '', content)  # 끝에 불완전한 태그 제거
        content = re.sub(r'[^>]*>\s*$', '', content)  # 끝에 불완전한 태그 내용 제거
        content = re.sub(r'\s*=\s*$', '', content)  # 끝에 등호나 불완전한 속성 제거
        content = re.sub(r'\s*"\s*$', '', content)  # 끝에 따옴표만 있는 경우 제거
        
        # 13-1. 불완전한 문장이나 단락 제거
        # 끝이 완전하지 않은 문장들 제거 (마침표, 물음표, 느낌표로 끝나지 않는 경우)
        lines = content.split('\n')
        complete_lines = []
        for line in lines:
            clean_line = re.sub(r'<[^>]*>', '', line).strip()  # HTML 태그 제거 후 체크
            if clean_line and len(clean_line) > 5:
                # 완전한 문장인지 체크 (한글 문장 특성 고려)
                if (clean_line.endswith(('.', '!', '?', '요', '다', '죠', '어요', '습니다', '네요', '게요')) or 
                    '</p>' in line or '</div>' in line or '</h2>' in line or '</h3>' in line):
                    complete_lines.append(line)
                elif len(clean_line) < 10:  # 너무 짧은 라인은 제거
                    continue
        
        content = '\n'.join(complete_lines)
        
        # 14. 최종 정리
        content = re.sub(r'\n\s*\n', '\n', content)  # 연속된 빈 줄 제거
        content = content.strip()
        
        return content
        
        # 마크다운을 HTML로 변환 (혹시 AI가 마크다운으로 출력한 경우 대비)
        # 헤딩 변환
        content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
        content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', content, flags=re.MULTILINE)

        # 볼드, 이탤릭 변환
        content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
        content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)

        # 마크다운 리스트를 HTML로 변환
        lines = content.split('\n')
        in_list = False
        result_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith('- ') or line_stripped.startswith('* '):
                if not in_list:
                    result_lines.append('<ul>')
                    in_list = True
                list_item = line_stripped[2:].strip()
                result_lines.append(f'<li>{list_item}</li>')
            else:
                if in_list:
                    result_lines.append('</ul>')
                    in_list = False
                result_lines.append(line)
        
        if in_list:
            result_lines.append('</ul>')
            
        content = '\n'.join(result_lines)

        # 인용구 변환
        content = re.sub(r'^> (.*?)$', r'<blockquote>\1</blockquote>', content, flags=re.MULTILINE)

        # 수평선 변환
        content = re.sub(r'^---$', r'<hr>', content, flags=re.MULTILINE)

        # 연속된 공백/줄바꿈 정리
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = re.sub(r' {2,}', ' ', content)
        
        # 빈 HTML 태그 제거
        content = re.sub(r'<p>\s*</p>', '', content)
        content = re.sub(r'<div>\s*</div>', '', content)
        content = re.sub(r'<strong>\s*</strong>', '', content)
        content = re.sub(r'<u>\s*</u>', '', content)
        
        return content.strip()

    def extract_title_and_intro(self, content, keyword):
        """제목과 서론을 추출 - 올바른 제목 형식 확인 및 보정"""
        lines = content.strip().split('\n')
        title = ""
        intro = content
        
        # 첫 번째 줄을 제목으로 사용 (HTML 태그 제거 후)
        if lines:
            first_line = lines[0].strip()
            # HTML 태그 제거
            title = re.sub(r'<[^>]+>', '', first_line).strip()
            # 나머지를 서론으로 사용
            intro = '\n'.join(lines[1:]).strip()
        
        # 제목에서 HTML 태그 제거 (제목은 순수 텍스트로)
        title = re.sub(r'<[^>]+>', '', title).strip()
        
        # 제목 형식 검증 및 보정
        if not self.is_valid_title_format(title, keyword):
            title = self.generate_hook_title(keyword)
            self.log(f"⚠️ 제목 형식이 올바르지 않아 자동 생성: {title}")
        
        # 서론에서 제목과 완전히 동일한 내용 제거 (대소문자 구분 없이)
        if title and intro:
            # 1. 완전히 동일한 제목 제거
            title_pattern = re.escape(title)
            intro = re.sub(rf'^.*{title_pattern}.*$', '', intro, flags=re.MULTILINE | re.IGNORECASE)
            
            # 2. 키워드가 포함된 소제목 형태 제거 (: 또는 | 포함)
            keyword_patterns = [
                rf'^.*{re.escape(keyword)}.*:.*$',
                rf'^.*{re.escape(keyword)}.*\|.*$',
                rf'^.*{re.escape(keyword)}.*방법.*$',
                rf'^.*{re.escape(keyword)}.*가이드.*$'
            ]
            for pattern in keyword_patterns:
                intro = re.sub(pattern, '', intro, flags=re.MULTILINE | re.IGNORECASE)
            
            # 3. HTML 헤딩 태그 완전 제거
            intro = re.sub(r'<h[1-6][^>]*>.*?</h[1-6]>', '', intro, flags=re.IGNORECASE | re.DOTALL)
            intro = re.sub(r'</?h[1-6][^>]*>', '', intro, flags=re.IGNORECASE)
            
            # 4. 과도한 <br> 태그 정리
            intro = re.sub(r'(<br\s*/?>\s*){2,}', '', intro, flags=re.IGNORECASE)
            intro = re.sub(r'^<br\s*/?>', '', intro, flags=re.IGNORECASE)
            intro = re.sub(r'<br\s*/?>$', '', intro, flags=re.IGNORECASE)
            
            # 5. 빈 문단이나 의미없는 내용 제거
            intro_lines = intro.split('\n')
            cleaned_lines = []
            for line in intro_lines:
                clean_line = line.strip()
                if (clean_line and 
                    len(clean_line) > 10 and 
                    not clean_line.startswith('#') and
                    not clean_line.lower().startswith(keyword.lower())):
                    cleaned_lines.append(line)
            
            intro = '\n'.join(cleaned_lines).strip()
        
        return title, intro

    def is_valid_title_format(self, title, keyword):
        """제목이 올바른 형식({keyword} | 후킹문구)인지 검증 - 매우 엄격"""
        if not title:
            return False
        
        # 1. 금지된 패턴 체크 (하이픈 형식 완전 거부)
        forbidden_patterns = [
            r'-\s*완벽\s*가이드',
            r'-\s*완벽\s*설명', 
            r'-\s*완벽\s*방법',
            r'-\s*노하우',
            r'-\s*팁',
            r'-\s*정리',
            r'-.*가이드$',
            r'-.*방법$',
            r'-.*설명$'
        ]
        
        for forbidden in forbidden_patterns:
            if re.search(forbidden, title, re.IGNORECASE):
                return False
        
        # 2. 필수 패턴 체크: {keyword} | 숫자포함 후킹문구
        required_pattern = rf'{re.escape(keyword)}\s*\|\s*.+'
        if not re.search(required_pattern, title, re.IGNORECASE):
            return False
        
        # 3. 파이프(|) 기호가 있는지 확인
        if '|' not in title:
            return False
        
        # 4. 숫자가 포함되어 있는지 확인
        if not re.search(r'\d+', title):
            return False
        
        # 5. 길이 체크 (20-80자)
        if len(title) < 20 or len(title) > 80:
            return False
        
        # 6. 키워드가 제목 시작 부분에 있는지 확인
        if not title.lower().strip().startswith(keyword.lower()):
            return False
        
        return True

    def similarity_ratio(self, str1, str2):
        """두 문자열의 유사도 계산 (0.0 ~ 1.0)"""
        try:
            from difflib import SequenceMatcher
            return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
        except:
            # difflib를 사용할 수 없는 경우 간단한 비교
            words1 = set(str1.lower().split())
            words2 = set(str2.lower().split())
            if not words1 or not words2:
                return 0.0
            intersection = words1.intersection(words2)
            union = words1.union(words2)
            return len(intersection) / len(union) if union else 0.0

    def validate_and_fix_title(self, title, keyword):
        """제목이 '{keyword} | 숫자가 들어간 후킹문구' 형식인지 검증하고 수정"""
        try:
            # 제목이 '{keyword} |' 로 시작하는지 확인
            expected_start = f"{keyword} |"
            
            # 1차 검증: 정확한 형식 확인
            if not title.startswith(expected_start):
                self.log(f"⚠️ 제목이 지침에 맞지 않음: {title}")
                
                # 제목 수정 시도
                if "|" in title:
                    # | 이후 부분을 후킹문구로 사용
                    parts = title.split("|", 1)
                    hook_part = parts[1].strip()
                    
                    # 키워드가 앞부분에 없거나 다른 경우 교체
                    if not parts[0].strip() == keyword:
                        # 숫자가 포함되어 있는지 확인
                        if any(char.isdigit() for char in hook_part):
                            fixed_title = f"{keyword} | {hook_part}"
                            self.log(f"✅ 제목을 지침에 맞게 수정: {fixed_title}")
                            return fixed_title
                
                # 기본 후킹문구 생성 (항상 숫자 포함)
                fixed_title = self.generate_hook_title(keyword)
                self.log(f"🔧 기본 제목 생성: {fixed_title}")
                return fixed_title
            
            # 2차 검증: 올바른 형식이지만 숫자 포함 여부 확인
            if "|" in title:
                hook_part = title.split("|", 1)[1].strip()
                if not any(char.isdigit() for char in hook_part):
                    # 숫자가 없으면 추가
                    enhanced_hook = self.add_number_to_hook(hook_part)
                    fixed_title = f"{keyword} | {enhanced_hook}"
                    self.log(f"� 제목에 숫자 추가: {fixed_title}")
                    return fixed_title
            
            return title
            
        except Exception as e:
            self.log(f"제목 검증 중 오류: {e}")
            # 오류 발생 시 안전한 기본 제목 반환
            return self.generate_hook_title(keyword)
    
    def generate_hook_title(self, keyword):
        """숫자가 포함된 기본 후킹 제목 생성"""
        import random
        hook_phrases = [
            f"{random.randint(3, 10)}가지 핵심 정보",
            f"{random.randint(5, 15)}분만에 완벽 이해",
            f"{random.randint(3, 7)}단계 완벽 가이드",
            f"{random.randint(10, 30)}초만에 알아보는 방법",
            f"2024년 최신 {random.randint(5, 20)}가지 팁",
            f"{random.randint(7, 15)}가지 필수 노하우",
            f"{random.randint(3, 8)}분 완벽 정리",
            f"{random.randint(5, 12)}가지 실용 정보"
        ]
        
        selected_hook = random.choice(hook_phrases)
        return f"{keyword} | {selected_hook}"
    
    def add_number_to_hook(self, hook_text):
        """후킹문구에 숫자 추가"""
        import random
        numbers = [random.randint(3, 10), random.randint(5, 15), random.randint(7, 20)]
        selected_number = random.choice(numbers)
        
        # 기존 후킹문구에 자연스럽게 숫자 추가
        if "가지" not in hook_text and "단계" not in hook_text and "분" not in hook_text:
            return f"{selected_number}가지 {hook_text}"
        else:
            return f"{selected_number}분만에 알아보는 {hook_text}"

    def extract_approval_title_and_intro(self, content, keyword):
        """승인용 콘텐츠에서 제목과 서론 추출"""
        return self.extract_title_and_intro(content, keyword)

    def replace_prompt_variables(self, prompt_content, keyword, urls, anchor_links, context):
        """프롬프트 변수들을 실제 값으로 치환 - 모든 변수 처리"""
        prompt = prompt_content.replace("{keyword}", keyword)
        prompt = prompt.replace("{context}", context)
        
        # 기본 URL 변수들 치환
        search_url = f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"
        prompt = prompt.replace("{url}", search_url)
        # href="url" 패턴만 치환 (다른 URL은 건드리지 않음)
        prompt = re.sub(r'href=["\']?\s*url\s*["\']?', f'href="{search_url}"', prompt, flags=re.IGNORECASE)
        
        # 모든 링크 변수들 치환
        prompt = prompt.replace("{naver_search_link}", f'<a href="{search_url}" target="_self">{keyword} 관련 정보</a>')
        prompt = prompt.replace("{youtube_link}", f'<a href="https://tv.naver.com/search?query={keyword.replace(" ", "+")}" target="_self">{keyword} 관련 영상</a>')
        prompt = prompt.replace("{primary_link}", f'<a href="{search_url}" target="_self">{keyword} 상세 정보</a>')
        
        # 정부 및 공공기관 링크들
        prompt = prompt.replace("{hometax_link}", '<a href="https://www.hometax.go.kr" target="_self">홈택스 바로가기</a>')
        prompt = prompt.replace("{lh_link}", '<a href="https://www.lh.or.kr" target="_self">LH 한국토지주택공사</a>')
        prompt = prompt.replace("{efine_link}", '<a href="https://www.efine.go.kr" target="_self">교통민원24</a>')
        prompt = prompt.replace("{gov24_link}", '<a href="https://www.gov.kr" target="_self">정부24</a>')
        prompt = prompt.replace("{wetax_link}", '<a href="https://www.wetax.go.kr" target="_self">위택스</a>')
        prompt = prompt.replace("{kepco_link}", '<a href="https://cyber.kepco.co.kr" target="_self">한국전력 사이버지점</a>')
        prompt = prompt.replace("{car365_link}", '<a href="https://www.car365.go.kr" target="_self">자동차365</a>')
        prompt = prompt.replace("{apply_lh_link}", '<a href="https://apply.lh.or.kr" target="_self">LH청약플러스</a>')
        prompt = prompt.replace("{bokjiro_link}", '<a href="https://www.bokjiro.go.kr" target="_self">복지로</a>')
        
        # 금융기관 링크들
        prompt = prompt.replace("{kbstar_link}", '<a href="https://www.kbstar.com" target="_self">KB국민은행</a>')
        prompt = prompt.replace("{shinhan_link}", '<a href="https://www.shinhan.com" target="_self">신한은행</a>')
        prompt = prompt.replace("{hanabank_link}", '<a href="https://www.hanabank.com" target="_self">하나은행</a>')
        prompt = prompt.replace("{wooribank_link}", '<a href="https://www.wooribank.com" target="_self">우리은행</a>')
        prompt = prompt.replace("{ibk_link}", '<a href="https://www.ibk.co.kr" target="_self">IBK기업은행</a>')
        prompt = prompt.replace("{kdb_link}", '<a href="https://www.kdb.co.kr" target="_self">KDB산업은행</a>')
        prompt = prompt.replace("{bok_link}", '<a href="https://www.bok.or.kr" target="_self">한국은행</a>')
        prompt = prompt.replace("{fss_link}", '<a href="https://www.fss.or.kr" target="_self">금융감독원</a>')
        prompt = prompt.replace("{toss_link}", '<a href="https://toss.im" target="_self">토스</a>')
        prompt = prompt.replace("{kakaopay_link}", '<a href="https://www.kakaopay.com" target="_self">카카오페이</a>')
        
        # 부동산 및 기타 링크들
        prompt = prompt.replace("{naver_land_link}", '<a href="https://land.naver.com" target="_self">네이버 부동산</a>')
        prompt = prompt.replace("{naver_map_link}", '<a href="https://map.naver.com" target="_self">네이버 지도</a>')
        prompt = prompt.replace("{zigbang_link}", '<a href="https://www.zigbang.com" target="_self">직방</a>')
        prompt = prompt.replace("{dabang_link}", '<a href="https://www.dabangapp.com" target="_self">다방</a>')
        
        # 통신 및 유틸리티 링크들
        prompt = prompt.replace("{tworld_link}", '<a href="https://www.tworld.co.kr" target="_self">T월드</a>')
        prompt = prompt.replace("{kt_link}", '<a href="https://www.kt.com" target="_self">KT</a>')
        prompt = prompt.replace("{uplus_link}", '<a href="https://www.uplus.co.kr" target="_self">LG U+</a>')
        
        # 자동차 관련 링크들
        prompt = prompt.replace("{bobaedream_link}", '<a href="https://www.bobaedream.co.kr" target="_self">보배드림</a>')
        prompt = prompt.replace("{encar_link}", '<a href="https://www.encar.com" target="_self">엔카</a>')
        
        return prompt

    def get_approval_system_prompt(self, step, keyword):
        """승인용 시스템 프롬프트 생성 - 통합된 URL과 기본 지침 포함"""
        
        # URL 변수들을 하나로 통합  
        url_variables = {
            # 기본 검색 링크들
            "{url}": f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}",
            "{naver_search_link}": f'<a href="https://search.naver.com/search.naver?query={keyword.replace(" ", "+")}" target="_self">{keyword} 관련 정보</a>',
            "{youtube_link}": f'<a href="https://tv.naver.com/search?query={keyword.replace(" ", "+")}" target="_self">{keyword} 관련 영상</a>',
            "{primary_link}": f'<a href="https://search.naver.com/search.naver?query={keyword.replace(" ", "+")}" target="_self">{keyword} 상세 정보</a>',
            
            # 정부 및 공공기관 링크들
            "{hometax_link}": '<a href="https://www.hometax.go.kr" target="_self">홈택스 바로가기</a>',
            "{lh_link}": '<a href="https://www.lh.or.kr" target="_self">LH 한국토지주택공사</a>',
            "{efine_link}": '<a href="https://www.efine.go.kr" target="_self">교통민원24</a>',
            "{gov24_link}": '<a href="https://www.gov.kr" target="_self">정부24</a>',
            "{wetax_link}": '<a href="https://www.wetax.go.kr" target="_self">위택스</a>',
            "{kepco_link}": '<a href="https://cyber.kepco.co.kr" target="_self">한국전력 사이버지점</a>',
            "{car365_link}": '<a href="https://www.car365.go.kr" target="_self">자동차365</a>',
            "{apply_lh_link}": '<a href="https://apply.lh.or.kr" target="_self">LH청약플러스</a>',
            "{bokjiro_link}": '<a href="https://www.bokjiro.go.kr" target="_self">복지로</a>',
            
            # 금융기관 링크들
            "{kbstar_link}": '<a href="https://www.kbstar.com" target="_self">KB국민은행</a>',
            "{shinhan_link}": '<a href="https://www.shinhan.com" target="_self">신한은행</a>',
            "{hanabank_link}": '<a href="https://www.hanabank.com" target="_self">하나은행</a>',
            "{wooribank_link}": '<a href="https://www.wooribank.com" target="_self">우리은행</a>',
            "{ibk_link}": '<a href="https://www.ibk.co.kr" target="_self">IBK기업은행</a>',
            "{kdb_link}": '<a href="https://www.kdb.co.kr" target="_self">KDB산업은행</a>',
            "{bok_link}": '<a href="https://www.bok.or.kr" target="_self">한국은행</a>',
            "{fss_link}": '<a href="https://www.fss.or.kr" target="_self">금융감독원</a>',
            "{toss_link}": '<a href="https://toss.im" target="_self">토스</a>',
            "{kakaopay_link}": '<a href="https://www.kakaopay.com" target="_self">카카오페이</a>',
            
            # 통신 및 유틸리티 링크들
            "{tworld_link}": '<a href="https://www.tworld.co.kr" target="_self">T월드</a>',
            "{kt_link}": '<a href="https://www.kt.com" target="_self">KT</a>',
            "{uplus_link}": '<a href="https://www.uplus.co.kr" target="_self">LG U+</a>',
            "{naver_land_link}": '<a href="https://land.naver.com" target="_self">네이버 부동산</a>',
            "{zigbang_link}": '<a href="https://www.zigbang.com" target="_self">직방</a>',
            
            # 자동차 관련 링크들
            "{bobaedream_link}": '<a href="https://www.bobaedream.co.kr" target="_self">보배드림</a>',
            "{encar_link}": '<a href="https://www.encar.com" target="_self">엔카</a>',
            "{kcar_link}": '<a href="https://www.kcar.com" target="_self">K카</a>',
            "{tmap_link}": '<a href="https://www.tmap.co.kr" target="_self">T맵</a>',
            "{naver_map_link}": '<a href="https://map.naver.com" target="_self">네이버 지도</a>',
            "{kakao_map_link}": '<a href="https://map.kakao.com" target="_self">카카오맵</a>',
            "{hyundai_link}": '<a href="https://www.hyundai.com" target="_self">현대자동차</a>',
            "{kia_link}": '<a href="https://www.kia.com" target="_self">기아</a>'
        }
        
        # URL 목록을 문자열로 변환
        url_list = '\n'.join([f"- {key}: {value}" for key, value in url_variables.items()])
        
        base_prompt = f"""넌 10년 경력의 고도로 숙련된 SEO 콘텐츠 전문가야.

IMPORTANT: 반드시 prompts.txt 파일의 지침을 엄격히 따라야 합니다.

승인용 콘텐츠 작성 규칙:
1. 마크다운 문법 절대 금지 (**, ##, - 등 금지)
2. HTML 태그만 사용 (<h1>, <h2>, <h3>, <p>, <strong>, <ul>, <li>, <table> 등)
3. 자연스럽고 유익한 내용으로 구성
4. 검색엔진과 사용자 모두에게 최적화된 고품질 콘텐츠 작성
5. 읽기 쉽고 정보가 풍부한 콘텐츠를 작성
6. 상업적 색채를 최소화하고 순수한 정보 전달에 집중

prompts.txt 파일 지침 준수:
- prompt1.txt: 제목은 반드시 '{keyword} |' 로 시작, 서론 작성 규칙 따르기
- prompt2~4.txt: 본문 지침에 따라 소제목과 내용 구성
- prompt5.txt: 표와 FAQ 구성 지침 준수

외부링크 사용 시:
- 절대로 존재하지 않는 URL (https://www.example.com 등) 사용 금지
- 아래 제공된 실제 URL 변수들만 사용
- 외부링크 위에 행동 유도 멘트 추가 (독자의 고통 해결이나 혜택 암시)

사용 가능한 실제 URL 변수들:
{url_list}

키워드: '{keyword}'
단계: {step}
출력 형식: 순수 HTML (마크다운 절대 금지)

중요: prompts.txt 파일의 모든 지침을 정확히 따라주세요."""

        return base_prompt

    def get_revenue_system_prompt(self, step_num, keyword):
        """수익용 시스템 프롬프트 생성 - prompt 파일 읽어서 사용"""
        try:
            # prompt 파일 경로
            prompt_file = f"prompts/prompt{step_num}.txt"
            
            # 파일 읽기
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_content = f.read()
            
            # {keyword} 치환
            prompt_content = prompt_content.replace('{keyword}', keyword)
            
            # 간단한 전처리 - AI 역할 언급 방지 규칙 추가
            prompt_content += "\n\n중요: AI 역할이나 '인공지능' 언급 절대 금지. '~해요'체로 작성."
            
            return prompt_content
            
        except Exception as e:
            self.log(f"프롬프트 파일 읽기 오류: {e}")
            # 기본 프롬프트
            return f"""너는 SEO 콘텐츠 작가다. {keyword}에 대한 고품질 콘텐츠를 '~해요'체로 작성해라.
            
규칙:
- AI 역할 언급 절대 금지
- 마크다운 문법 사용 금지
- 순수 HTML만 사용
- {keyword}에 대한 유용한 정보 제공"""

    def extract_approval_title_and_intro(self, content, keyword):
        """승인용 콘텐츠에서 제목과 서론 추출"""
        return self.extract_title_and_intro(content, keyword)

        return base_prompt

                
class ConfigManager:
    """단일 JSON 구조 설정 관리 클래스 (setting.json)"""

    def __init__(self):
        self.setting_file = os.path.join(get_base_path(), "setting.json")
        self.data = self.load_setting()

    # property 완전 제거 - 직접 접근 방식
    
    def load_setting(self):
        """단일 JSON 파일에서 모든 설정 로드"""
        default_data = {
            "api_keys": {
                "openai": "",
                "gemini": ""
            },
            "global_settings": {
                "default_ai": "gemini",
                "default_wait_time": "47~50",
                "posting_mode": "수익용",
                "ai_model": "",
                "common_username": "",
                "common_password": "",
                "font_path": "fonts/timon.ttf",
                "max_sites": 20,
                "auto_save": True
            },
            "posting_state": {
                "last_site_id": None,
                "last_site_url": "",
                "posting_in_progress": False,
                "next_site_id": None
            },
            "version": "multi-site",
            "sites": []
        }

        try:
            if os.path.exists(self.setting_file):
                with open(self.setting_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    # 기본값과 병합
                    for key in default_data:
                        if key in loaded_data:
                            if isinstance(default_data[key], dict):
                                default_data[key].update(loaded_data[key])
                            else:
                                default_data[key] = loaded_data[key]
                    return default_data
            return default_data
        except Exception as e:
            print(f"설정 로드 오류: {e}")
            return default_data

    def save_setting(self):
        """단일 JSON 파일에 모든 설정 저장"""
        try:
            with open(self.setting_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ 설정 저장 오류: {e}")
            return False

    def load_config(self):
        """기존 호환성을 위한 메서드 - 직접 데이터 반환"""
        return self.data

    def reload_config(self):
        """설정 파일을 다시 로드하여 메모리 데이터 갱신"""
        try:
            print("🔄 설정 파일 다시 로드 중...")
            self.data = self.load_setting()
            print("✅ 설정 파일 로드 완료")
            return True
        except Exception as e:
            print(f"❌ 설정 파일 다시 로드 실패: {e}")
            return False

    def save_config(self):
        """기존 호환성을 위한 메서드"""
        return self.save_setting()

    def load_sites(self):
        """기존 호환성을 위한 메서드 - 직접 사이트 데이터 반환"""
        return {"sites": self.data.get("sites", [])}

    def save_sites(self):
        """기존 호환성을 위한 메서드"""
        return self.save_setting()

    def save_posting_state(self, site_id, site_url, in_progress=False):
        """현재 포스팅 상태 저장"""
        try:
            # 포스팅이 완료된 경우(in_progress=False), 다음 사이트로 이동할 수 있도록 next_site_id 설정
            next_site_id = None
            if not in_progress:
                next_site_id = self.get_next_site_id(site_id)
                print(f"🔄 포스팅 완료: {site_id} → 다음 시작 사이트: {next_site_id}")
            
            self.data["posting_state"] = {
                "last_site_id": site_id,
                "last_site_url": site_url,
                "posting_in_progress": in_progress,
                "next_site_id": next_site_id
            }
            self.save_setting()
        except Exception as e:
            print(f"포스팅 상태 저장 오류: {e}")

    def get_posting_state(self):
        """마지막 포스팅 상태 반환"""
        return self.data.get("posting_state", {
            "last_site_id": None,
            "last_site_url": "",
            "posting_in_progress": False,
            "next_site_id": None
        })

    def get_next_site_id(self, current_site_id):
        """현재 사이트 다음의 사이트 ID 반환"""
        try:
            sites = self.data.get("sites", [])
            if not sites:
                return None
            
            # 현재 사이트의 인덱스 찾기
            current_index = -1
            for i, site in enumerate(sites):
                if site.get("id") == current_site_id:
                    current_index = i
                    break
            
            if current_index == -1:
                # 현재 사이트를 찾지 못한 경우 첫 번째 사이트 반환
                return sites[0].get("id") if sites else None
            
            # 다음 사이트 반환 (마지막 사이트면 첫 번째로)
            next_index = (current_index + 1) % len(sites)
            return sites[next_index].get("id")
            
        except Exception as e:
            print(f"다음 사이트 ID 조회 오류: {e}")
            return None

    def get_start_site_id(self):
        """시작할 사이트 ID 반환 - 마지막 상태에 따라 결정"""
        try:
            posting_state = self.get_posting_state()
            
            # 포스팅이 진행 중이었다면 같은 사이트에서 재시작
            if posting_state.get("posting_in_progress", False):
                last_site_id = posting_state.get("last_site_id")
                print(f"🔄 포스팅 재시작: {last_site_id}에서 계속")
                return last_site_id
            
            # 포스팅이 완료되었다면 다음 사이트부터 시작
            next_site_id = posting_state.get("next_site_id")
            if next_site_id:
                print(f"🔄 다음 사이트부터 시작: {next_site_id}")
                return next_site_id
            
            # 저장된 상태가 없다면 첫 번째 사이트
            sites = self.data.get("sites", [])
            first_site_id = sites[0].get("id") if sites else None
            print(f"🔄 첫 번째 사이트부터 시작: {first_site_id}")
            return first_site_id
            
        except Exception as e:
            print(f"시작 사이트 ID 조회 오류: {e}")
            # 오류 발생 시 첫 번째 사이트 반환
            sites = self.data.get("sites", [])
            return sites[0].get("id") if sites else None
            print(f"시작 사이트 ID 조회 오류: {e}")
            return None

    def add_site(self, site_data):
        """새 사이트 추가"""
        # sites 데이터 구조 확인 및 보정
        if "sites" not in self.data:
            print("data에 sites 키가 없음, 초기화")
            self.data["sites"] = []
        
        # 안전한 ID 생성
        existing_ids = [site.get("id", 0) for site in self.data["sites"] if isinstance(site, dict)]
        site_id = max(existing_ids) + 1 if existing_ids else 1
        
        site_data["id"] = site_id
        site_data["created_at"] = datetime.now().isoformat()
        site_data["active"] = True

        # 키워드 파일과 썸네일 이미지 파일 자동 생성
        self.create_site_resources(site_data)

        self.data["sites"].append(site_data)
        self.save_sites()
        return site_id

    def create_site_resources(self, site_data):
        """사이트별 리소스 파일 생성"""
        try:
            # 키워드 파일 생성
            keyword_file = site_data.get("keyword_file", "")
            if keyword_file:
                keyword_path = os.path.join(get_base_path(), "keywords", keyword_file)
                if not os.path.exists(keyword_path):
                    # 기본 키워드 템플릿 생성
                    default_keywords = [
                        "# 사이트별 키워드 파일",
                        f"# 사이트: {site_data.get('name', '')}",
                        f"# URL: {site_data.get('url', '')}",
                        "",
                        "# 키워드를 한 줄에 하나씩 작성.",
                        "# 예시:",
                        "인공지능",
                        "AI 뉴스",
                        "머신러닝",
                        "딥러닝",
                        "기술 동향"
                    ]

                    with open(keyword_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(default_keywords))

                    print(f"키워드 파일 생성됨: {keyword_path}")

            # 썸네일 이미지 파일 확인 (존재하지 않으면 경고 메시지만)
            thumbnail_image = site_data.get("thumbnail_image", "")
            if thumbnail_image:
                thumbnail_path = os.path.join(get_base_path(), "images", thumbnail_image)
                if not os.path.exists(thumbnail_path):
                    print(f"경고: 썸네일 이미지가 없습니다. 다음 경로에 이미지를 추가해주세요: {thumbnail_path}")

        except Exception as e:
            print(f"사이트 리소스 생성 오류: {e}")

    def get_site(self, site_id):
        """사이트 정보 조회"""
        for site in self.data.get("sites", []):
            if site["id"] == site_id:
                return site
        return None

    def update_site(self, site_id, site_data):
        """사이트 정보 업데이트"""
        for i, site in enumerate(self.data.get("sites", [])):
            if site["id"] == site_id:
                site_data["id"] = site_id
                site_data["updated_at"] = datetime.now().isoformat()
                self.data["sites"][i] = site_data
                self.save_setting()
                return True
        return False

    def delete_site(self, site_id):
        """사이트 삭제"""
        try:
            log_to_file(f"[MAIN] 사이트 삭제 시작 - ID: {site_id} (타입: {type(site_id)})")
            
            # sites 데이터를 직접 수정
            if "sites" not in self.data:
                self.data["sites"] = []
            
            original_count = len(self.data["sites"])
            log_to_file(f"[MAIN] 삭제 전 사이트 수: {original_count}")
            
            # 기존 사이트들의 ID와 타입 확인
            for i, site in enumerate(self.data["sites"]):
                log_to_file(f"[MAIN] 사이트 {i}: ID={site['id']} (타입: {type(site['id'])}), 이름={site.get('name', 'Unknown')}")
            
            # 타입 통일해서 삭제 (문자열과 숫자 모두 고려) - data 직접 수정
            self.data["sites"] = [s for s in self.data["sites"] if str(s["id"]) != str(site_id)]
            
            log_to_file(f"[MAIN] 삭제 후 사이트 수: {len(self.data['sites'])}")
            
            self.save_setting()  # save_sites 대신 save_setting 직접 호출
            log_to_file(f"[MAIN] 설정 파일 저장 완료")
            
            # 실제로 삭제되었는지 확인
            result = len(self.data["sites"]) < original_count
            log_to_file(f"[MAIN] 삭제 결과: {result}")
            return result
        except Exception as e:
            print(f"사이트 삭제 오류: {e}")
            log_to_file(f"[MAIN] 사이트 삭제 오류: {e}")
            return False

    def update_site_active(self, site_id, active_status):
        """사이트 활성화 상태 업데이트"""
        try:
            for site in self.data["sites"]:
                if site["id"] == site_id:
                    site["active"] = active_status
                    site["updated_at"] = datetime.now().isoformat()
                    self.save_setting()
                    return True
            return False
        except Exception as e:
            print(f"사이트 활성화 상태 업데이트 오류: {e}")
            return False

    def get_site_keywords(self, site_data):
        """사이트별 키워드 파일에서 키워드 로드 - used 키워드 제외"""
        try:
            keyword_file = site_data.get("keyword_file", "")
            if not keyword_file:
                return []

            base_path = get_base_path()
            keyword_path = os.path.join(base_path, "keywords", keyword_file)
            if not os.path.exists(keyword_path):
                print(f"❌ 키워드 파일이 존재하지 않습니다: {keyword_path}")
                return []

            # 원본 키워드 파일 읽기
            with open(keyword_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 주석 제거하고 빈 줄 제거
            available_keywords = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    available_keywords.append(line)

            # used 키워드 파일이 있다면 이미 사용된 키워드들을 확인
            used_filename = f"used_{keyword_file}"
            used_path = os.path.join(base_path, "keywords", used_filename)
            used_keywords = set()
            
            if os.path.exists(used_path):
                try:
                    with open(used_path, 'r', encoding='utf-8') as f:
                        used_lines = f.readlines()
                    for line in used_lines:
                        line = line.strip()
                        if line:
                            used_keywords.add(line)
                except Exception as used_error:
                    print(f"⚠️ used 파일 읽기 오류: {used_error}")

            # 사용되지 않은 키워드만 반환
            final_keywords = [keyword for keyword in available_keywords if keyword not in used_keywords]
            
            if not final_keywords:
                print(f"⚠️ 사용 가능한 키워드가 없습니다. used 파일을 확인.")
                
            return final_keywords

        except Exception as e:
            print(f"❌ 키워드 파일 로드 오류: {e}")
            return []

    def get_site_thumbnail_path(self, site_data):
        """사이트별 썸네일 이미지 경로 반환"""
        thumbnail_image = site_data.get("thumbnail_image", "")
        if thumbnail_image:
            thumbnail_path = os.path.join(get_base_path(), "images", thumbnail_image)
            if os.path.exists(thumbnail_path):
                return thumbnail_path
        return None

class SiteEditDialog(QDialog):
    """사이트 추가/편집 다이얼로그"""

    def __init__(self, parent=None, site_data=None):
        super().__init__(parent)
        self.site_data = site_data
        self.is_edit = site_data is not None
        self.setup_ui()

        if self.is_edit:
            self.load_site_data()

    def setup_ui(self):
        """UI 설정"""
        self.setWindowTitle("사이트 편집" if self.is_edit else "새 사이트 추가")
        self.setFixedSize(600, 500)  # 크기 증가

        layout = QVBoxLayout()

        # 폼 레이아웃
        form_layout = QFormLayout()

        # WordPress URL
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://yoursite.com")
        self.url_edit.textChanged.connect(self.update_resource_info)
        form_layout.addRow("WordPress URL:", self.url_edit)

        # 카테고리 ID
        self.category_edit = QSpinBox()
        self.category_edit.setRange(1, 9999)
        self.category_edit.setValue(1)
        form_layout.addRow("카테고리 ID:", self.category_edit)

        layout.addLayout(form_layout)

        # 썸네일 선택 섹션 추가
        thumbnail_group = QGroupBox("🖼️ 썸네일 이미지 선택")
        thumbnail_layout = QVBoxLayout()
        
        # 썸네일 콤보박스
        thumbnail_combo_layout = QHBoxLayout()
        thumbnail_combo_layout.addWidget(QLabel("썸네일 이미지:"))
        
        self.thumbnail_combo = QComboBox()
        self.thumbnail_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.populate_thumbnail_combo()
        thumbnail_combo_layout.addWidget(self.thumbnail_combo)
        thumbnail_layout.addLayout(thumbnail_combo_layout)
        
        # 미리보기 라벨
        self.thumbnail_preview = QLabel("미리보기")
        self.thumbnail_preview.setFixedSize(150, 150)
        self.thumbnail_preview.setStyleSheet("border: 1px solid #ccc; background: #f0f0f0;")
        self.thumbnail_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_preview.setScaledContents(True)
        thumbnail_layout.addWidget(self.thumbnail_preview)
        
        # 콤보박스 변경 시 미리보기 업데이트
        self.thumbnail_combo.currentTextChanged.connect(self.update_thumbnail_preview)
        
        thumbnail_group.setLayout(thumbnail_layout)
        layout.addWidget(thumbnail_group)

        # 리소스 정보 표시
        resource_group = QGroupBox("🤖 자동 생성될 파일 정보")
        resource_layout = QFormLayout()

        self.keyword_file_label = QLabel("입력 대기 중")
        self.keyword_file_label.setStyleSheet("color: #88C0D0; font-weight: bold;")
        resource_layout.addRow("키워드 파일:", self.keyword_file_label)

        self.thumbnail_file_label = QLabel("입력 대기 중")
        self.thumbnail_file_label.setStyleSheet("color: #88C0D0; font-weight: bold;")
        resource_layout.addRow("썸네일 이미지:", self.thumbnail_file_label)

        resource_group.setLayout(resource_layout)
        layout.addWidget(resource_group)

        # 연결 테스트 버튼
        test_btn = QPushButton("연결 테스트")
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.clicked.connect(self.test_connection)
        layout.addWidget(test_btn)

        # 버튼
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

        # 초기 리소스 정보 업데이트
        self.update_resource_info()
        
        # 초기 썸네일 미리보기 업데이트
        self.update_thumbnail_preview()

    def populate_thumbnail_combo(self):
        """썸네일 콤보박스에 사용 가능한 이미지 목록 추가"""
        try:
            images_dir = os.path.join(get_base_path(), "images")
            if os.path.exists(images_dir):
                available_thumbnails = []
                for file in os.listdir(images_dir):
                    if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                        available_thumbnails.append(file)
                
                # 기본 썸네일들을 우선적으로 정렬
                priority_thumbnails = [f'썸네일 ({i}).jpg' for i in range(1, 8)]
                sorted_thumbnails = []
                
                # 우선순위 썸네일 먼저 추가
                for thumb in priority_thumbnails:
                    if thumb in available_thumbnails:
                        sorted_thumbnails.append(thumb)
                        available_thumbnails.remove(thumb)
                
                # 나머지 썸네일 추가
                sorted_thumbnails.extend(sorted(available_thumbnails))
                
                self.thumbnail_combo.addItems(sorted_thumbnails)
                
                # 편집 모드에서 기존 썸네일 선택
                if self.is_edit and self.site_data:
                    existing_thumbnail = self.site_data.get('thumbnail_image', '')
                    if existing_thumbnail in sorted_thumbnails:
                        self.thumbnail_combo.setCurrentText(existing_thumbnail)
                        
            else:
                self.thumbnail_combo.addItem("이미지 폴더 없음")
                
        except Exception as e:
            print(f"썸네일 목록 로드 오류: {e}")
            self.thumbnail_combo.addItem("로드 실패")

    def update_thumbnail_preview(self):
        """선택된 썸네일의 미리보기 업데이트"""
        try:
            selected_thumbnail = self.thumbnail_combo.currentText()
            if selected_thumbnail and selected_thumbnail not in ["이미지 폴더 없음", "로드 실패"]:
                thumbnail_path = os.path.join(get_base_path(), "images", selected_thumbnail)
                if os.path.exists(thumbnail_path):
                    from PyQt6.QtGui import QPixmap
                    pixmap = QPixmap(thumbnail_path)
                    scaled_pixmap = pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.thumbnail_preview.setPixmap(scaled_pixmap)
                    return
            
            # 기본 미리보기
            self.thumbnail_preview.setText("미리보기\n없음")
            
        except Exception as e:
            print(f"썸네일 미리보기 오류: {e}")
            self.thumbnail_preview.setText("미리보기\n오류")

    def update_resource_info(self):
        """리소스 파일 정보 업데이트"""
        url = self.url_edit.text().strip()
        if url:
            # URL에서 사이트 이름 추출
            site_name = url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            domain_parts = site_name.split('.')
            keyword_prefix = domain_parts[0] if domain_parts else site_name

            # 키워드 파일과 썸네일 이미지 파일명
            keyword_file = f"{keyword_prefix}_keywords.txt"
            
            # 썸네일 이미지는 기존 데이터가 있으면 사용하고, 없으면 기본 이미지 사용
            thumbnail_image = ""
            if self.site_data and self.site_data.get('thumbnail_image'):
                # 편집 모드: 기존 썸네일 이미지 사용
                thumbnail_image = self.site_data.get('thumbnail_image')
            else:
                # 새 사이트 추가: 사용 가능한 기본 썸네일 중 하나 선택
                available_thumbnails = ['썸네일 (1).jpg', '썸네일 (2).jpg', '썸네일 (3).jpg', 
                                      '썸네일 (4).jpg', '썸네일 (5).jpg', '썸네일 (6).jpg', 
                                      '썸네일 (7).jpg']
                for thumb in available_thumbnails:
                    thumb_path = os.path.join(get_base_path(), "images", thumb)
                    if os.path.exists(thumb_path):
                        thumbnail_image = thumb
                        break
                if not thumbnail_image:
                    thumbnail_image = '썸네일 (1).jpg'  # 기본값

            # 파일 경로
            keyword_path = os.path.join(get_base_path(), "keywords", keyword_file)
            thumbnail_path = os.path.join(get_base_path(), "images", thumbnail_image)

            # 키워드 파일 상태
            if os.path.exists(keyword_path):
                self.keyword_file_label.setText(f"✅ {keyword_file} (존재함)")
                self.keyword_file_label.setStyleSheet("color: #A3BE8C; font-weight: bold;")
            else:
                self.keyword_file_label.setText(f"📝 {keyword_file} (새로 생성됨)")
                self.keyword_file_label.setStyleSheet("color: #EBCB8B; font-weight: bold;")

            # 썸네일 이미지 상태
            if os.path.exists(thumbnail_path):
                self.thumbnail_file_label.setText(f"✅ {thumbnail_image} (존재함)")
                self.thumbnail_file_label.setStyleSheet("color: #A3BE8C; font-weight: bold;")
            else:
                self.thumbnail_file_label.setText(f"📌 {thumbnail_image} (수동으로 추가 필요)")
                self.thumbnail_file_label.setStyleSheet("color: #D08770; font-weight: bold;")
        else:
            self.keyword_file_label.setText("URL을 입력")
            self.thumbnail_file_label.setText("URL을 입력")
            self.keyword_file_label.setStyleSheet("color: #88C0D0; font-weight: bold;")
            self.thumbnail_file_label.setStyleSheet("color: #88C0D0; font-weight: bold;")

    def load_site_data(self):
        """사이트 데이터 로드"""
        if self.site_data:
            self.url_edit.setText(self.site_data.get("url", ""))
            self.category_edit.setValue(self.site_data.get("category_id", 1))

    def test_connection(self):
        """WordPress 연결 테스트 - 다중 인증 방법 지원"""
        url = self.url_edit.text().strip()

        # 전역 설정에서 사용자명/비밀번호 가져오기
        config_manager = self.parent().config_manager
        username = config_manager.data["global_settings"].get("common_username", "")
        password = config_manager.data["global_settings"].get("common_password", "")

        if not all([url, username, password]):
            QMessageBox.warning(self, "경고", "URL과 전역 설정의 사용자명/비밀번호를 확인해주세요.")
            return

        # 진행 상황 다이얼로그
        progress_dialog = QProgressDialog("WordPress 연결 진단 중", "취소", 0, 100, self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.show()

        try:
            session = requests.Session()
            
            # 1. 기본 사이트 접근 테스트
            progress_dialog.setValue(20)
            progress_dialog.setLabelText("사이트 접근성 확인 중")
            QApplication.processEvents()
            
            try:
                site_response = session.get(url, timeout=10)
                if site_response.status_code != 200:
                    progress_dialog.close()
                    QMessageBox.warning(self, "사이트 접근 경고", f"사이트 접근 시 HTTP {site_response.status_code} 응답")
                    return
            except Exception as e:
                progress_dialog.close()
                QMessageBox.critical(self, "사이트 접근 실패", f"사이트에 접근할 수 없습니다:\n{str(e)}")
                return
            
            # 2. WordPress REST API 확인
            progress_dialog.setValue(40)
            progress_dialog.setLabelText("WordPress REST API 확인 중")
            QApplication.processEvents()
            
            api_test_url = f"{url.rstrip('/')}/wp-json/wp/v2/"
            try:
                api_response = session.get(api_test_url, timeout=10)
                if api_response.status_code == 200:
                    api_info = api_response.json()
                    wp_description = api_info.get('description', 'WordPress Site')
                else:
                    progress_dialog.close()
                    QMessageBox.warning(self, "REST API 오류", f"WordPress REST API 접근 불가 (HTTP {api_response.status_code})")
                    return
            except Exception as e:
                progress_dialog.close()
                QMessageBox.critical(self, "REST API 오류", f"WordPress REST API 확인 실패:\n{str(e)}")
                return
            
            # 3. 다중 인증 방법 테스트
            progress_dialog.setValue(60)
            progress_dialog.setLabelText("인증 방법 테스트 중")
            QApplication.processEvents()
            
            user_url = f"{url.rstrip('/')}/wp-json/wp/v2/users/me"
            auth_success = False
            user_info = None
            successful_method = ""
            
            # 여러 인증 방법 시도
            import base64
            auth_methods = [
                ("Application Password (공백 포함)", username, password),
                ("Application Password (공백 제거)", username, password.replace(" ", "")),
                ("Basic Authentication", username, password)
            ]
            
            for method_name, user, pwd in auth_methods:
                if progress_dialog.wasCanceled():
                    return
                
                try:
                    credentials = f"{user}:{pwd}"
                    token = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
                    headers = {
                        'Authorization': f'Basic {token}',
                        'User-Agent': 'Auto-WP/1.0'
                    }
                    
                    auth_response = session.get(user_url, headers=headers, timeout=15)
                    
                    if auth_response.status_code == 200:
                        user_info = auth_response.json()
                        auth_success = True
                        successful_method = method_name
                        break
                        
                except Exception:
                    continue
            
            # 4. 카테고리 확인
            if auth_success:
                progress_dialog.setValue(80)
                progress_dialog.setLabelText("카테고리 확인 중")
                QApplication.processEvents()
                
                category_id = self.category_edit.value()
                categories_url = f"{url.rstrip('/')}/wp-json/wp/v2/categories/{category_id}"
                
                category_name = "알 수 없음"
                try:
                    cat_response = session.get(categories_url, headers=headers, timeout=10)
                    if cat_response.status_code == 200:
                        cat_info = cat_response.json()
                        category_name = cat_info.get('name', f'ID {category_id}')
                except Exception:
                    pass
            
            # 5. 결과 표시
            progress_dialog.setValue(100)
            progress_dialog.close()
            
            if auth_success and user_info:
                user_name = user_info.get('name', 'Unknown')
                user_roles = user_info.get('roles', [])
                capabilities = user_info.get('capabilities', {})
                
                # 핵심 권한 확인
                can_publish = capabilities.get('publish_posts', False)
                can_edit = capabilities.get('edit_posts', False)
                can_upload = capabilities.get('upload_files', False)
                
                message = f"✅ 연결 성공!\n\n"
                message += f"WordPress: {wp_description}\n"
                message += f"인증 방법: {successful_method}\n\n"
                message += f"사용자 정보:\n"
                message += f"  이름: {user_name}\n"
                message += f"  역할: {', '.join(user_roles)}\n\n"
                message += f"권한 확인:\n"
                message += f"  포스트 작성: {'✅' if can_edit else '❌'}\n"
                message += f"  포스트 발행: {'✅' if can_publish else '❌'}\n"
                message += f"  파일 업로드: {'✅' if can_upload else '❌'}\n\n"
                message += f"포스팅 카테고리: {category_name} (ID: {category_id})"
                
                if not (can_edit and can_publish):
                    message += f"\n\n⚠️ 경고: 포스트 작성/발행 권한이 부족합니다.\n사용자를 '편집자' 이상 권한으로 설정해주세요."
                
                QMessageBox.information(self, "연결 테스트 결과", message)
            else:
                # 인증 실패 안내
                error_msg = "❌ 모든 인증 방법 실패!\n\n"
                error_msg += "📋 Application Password 설정 가이드:\n"
                error_msg += "1. WordPress 관리자 로그인\n"
                error_msg += "2. 사용자 > 프로필 메뉴로 이동\n"
                error_msg += "3. 'Application Passwords' 섹션 찾기\n"
                error_msg += "4. 앱 이름 입력 (예: Auto-WP)\n"
                error_msg += "5. '새 Application Password 추가' 클릭\n"
                error_msg += "6. 생성된 패스워드를 복사\n"
                error_msg += "7. 전역 설정의 패스워드 필드에 붙여넣기\n\n"
                error_msg += "⚠️ 주의사항:\n"
                error_msg += "• Application Password는 일반 로그인 패스워드와 다릅니다\n"
                error_msg += "• 생성된 패스워드는 한 번만 표시됩니다\n"
                error_msg += "• 사용자는 '편집자' 이상의 권한이 필요합니다"
                
                QMessageBox.warning(self, "인증 실패", error_msg)
                
        except requests.exceptions.ConnectTimeout:
            if 'progress_dialog' in locals():
                progress_dialog.close()
            QMessageBox.critical(self, "연결 오류", "❌ 연결 시간 초과\n\nURL을 확인해주세요.")
        except requests.exceptions.ConnectionError:
            if 'progress_dialog' in locals():
                progress_dialog.close()
            QMessageBox.critical(self, "연결 오류", "❌ 서버에 연결할 수 없습니다\n\nURL과 네트워크 연결을 확인해주세요.")
        except Exception as e:
            if 'progress_dialog' in locals():
                progress_dialog.close()
            QMessageBox.critical(self, "오류", f"❌ 연결 테스트 중 오류:\n{str(e)}")

    def get_site_data(self):
        """사이트 데이터 반환"""
        # 전역 설정에서 공통 설정 가져오기
        config_manager = self.parent().config_manager

        # URL에서 사이트 이름 자동 생성
        url = self.url_edit.text().strip()
        site_name = url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]

        # 도메인에서 키워드 파일명 생성 (예: ai.ddgaz0813.com -> ai)
        domain_parts = site_name.split('.')
        keyword_prefix = domain_parts[0] if domain_parts else site_name

        # 썸네일 이미지 파일명 결정 - 사용자가 선택한 썸네일 사용
        thumbnail_image = self.thumbnail_combo.currentText()
        if not thumbnail_image or thumbnail_image in ["이미지 폴더 없음", "로드 실패"]:
            thumbnail_image = '썸네일 (1).jpg'  # 기본값

        # 키워드 파일 경로 생성
        keyword_file = f"{keyword_prefix}_keywords.txt"

        return {
            "name": site_name,
            "url": url,
            "username": config_manager.data["global_settings"].get("common_username", ""),
            "password": config_manager.data["global_settings"].get("common_password", ""),
            "category_id": self.category_edit.value(),
            "ai_provider": config_manager.data["global_settings"].get("default_ai", "gemini"),
            "wait_time": config_manager.data["global_settings"].get("default_wait_time", "47~50"),
            "thumbnail_image": thumbnail_image,  # 썸네일 이미지 파일명
            "keyword_file": keyword_file,        # 키워드 파일명
            "keywords": []  # 키워드는 파일에서 동적으로 로드
        }

class SiteWidget(QWidget):
    """개별 사이트 위젯"""

    edit_requested = pyqtSignal(int)
    keywords_requested = pyqtSignal(int)
    thumbnails_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    toggle_requested = pyqtSignal(int)  # 활성화 토글용 시그널

    def __init__(self, site_data):
        super().__init__()
        self.site_data = site_data
        self.setup_ui()

    def setup_ui(self):
        """사이트 카드 UI - 더욱 직관적이고 정보가 잘 보이도록 개선"""
        # 사이트 카드의 최소 높이 설정으로 잘림 현상 방지
        self.setMinimumHeight(120)  # 최소 높이 설정
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)  # 25에서 8로 줄임 (약 3분의 1)
        layout.setSpacing(7)  # 20에서 7로 줄임 (약 3분의 1)

        # 통합 사이트 카드
        main_card = QWidget()
        style_css = f"""
            QWidget {{
                background-color: {COLORS['surface_light']};
                border: {'1px'} solid {COLORS['border']};
                border-radius: {'12px'};
                padding: {'7px'};
            }}
        """
        main_card.setStyleSheet(style_css)
        card_layout = QVBoxLayout(main_card)
        card_layout.setSpacing(5)  # 15에서 5로 줄임 (약 3분의 1)

        # 3개 섹션을 가로로 나열 (균등한 공간 배분)
        sections_layout = QHBoxLayout()
        sections_layout.setSpacing(10)  # 30에서 10으로 줄임 (약 3분의 1)

        # URL 섹션 (균등 배분)
        url_section = QVBoxLayout()
        url_section.setSpacing(3)  # 8에서 3으로 줄임

        url_row = QHBoxLayout()
        # URL에서 https:// 제거
        raw_url = self.site_data.get('url', '설정되지 않음')
        if raw_url != '설정되지 않음':
            display_url = raw_url.replace('https://', '').replace('http://', '')
        else:
            display_url = raw_url
        url_info = QLabel(display_url)
        url_info.setFont(QFont("맑은 고딕", 10))
        url_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_info.setStyleSheet(f"""
            color: {COLORS['info']};
            text-decoration: underline;
        """)
        url_info.setCursor(Qt.CursorShape.PointingHandCursor)
        url_info.mousePressEvent = lambda event: self.open_wp_admin()
        url_row.addWidget(url_info, 1)

        url_row.addStretch()

        # 편집 버튼
        edit_btn = QPushButton("편집")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.site_data["id"]))
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 5px 15px;
                font-weight: normal;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
                border: none;
            }}
        """)
        url_row.addWidget(edit_btn)
        url_section.addLayout(url_row)
        sections_layout.addLayout(url_section, 1)

        # 키워드 섹션 (균등 배분)
        keyword_section = QVBoxLayout()
        keyword_section.setSpacing(3)  # 8에서 3으로 줄임

        keyword_row = QHBoxLayout()
        keywords_count = self.get_keywords_count()
        keyword_info = QLabel(f"키워드 {keywords_count}개")
        keyword_info.setFont(QFont("맑은 고딕", 10))
        keyword_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keyword_info.setStyleSheet(f"""
            color: {COLORS['info']};
            text-decoration: underline;
        """)
        keyword_info.setCursor(Qt.CursorShape.PointingHandCursor)
        keyword_info.mousePressEvent = lambda event: self.open_keyword_file()
        keyword_row.addWidget(keyword_info, 1)

        keyword_row.addStretch()

        # 파일 선택 버튼
        keyword_btn = QPushButton("파일 선택")
        keyword_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        keyword_btn.clicked.connect(lambda: self.keywords_requested.emit(self.site_data["id"]))
        keyword_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['warning']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 5px 15px;
                font-weight: normal;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {COLORS['warning_hover']};
                border: none;
            }}
        """)
        keyword_row.addWidget(keyword_btn)
        keyword_section.addLayout(keyword_row)
        sections_layout.addLayout(keyword_section, 1)

        # 썸네일 섹션 (균등 배분)
        thumbnail_section = QVBoxLayout()
        thumbnail_section.setSpacing(3)  # 8에서 3으로 줄임

        thumbnail_row = QHBoxLayout()
        thumbnail_info = self.get_thumbnail_info()
        thumbnail_label = QLabel(f"썸네일 {thumbnail_info}")
        thumbnail_label.setFont(QFont("맑은 고딕", 10))
        thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumbnail_label.setStyleSheet(f"""
            color: {COLORS['info']};
            text-decoration: underline;
        """)
        thumbnail_label.setCursor(Qt.CursorShape.PointingHandCursor)
        thumbnail_label.mousePressEvent = lambda event: self.open_thumbnail_file()
        thumbnail_row.addWidget(thumbnail_label, 1)

        thumbnail_row.addStretch()

        # 파일 선택 버튼
        thumbnail_btn = QPushButton("파일 선택")
        thumbnail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        thumbnail_btn.clicked.connect(lambda: self.thumbnails_requested.emit(self.site_data["id"]))
        thumbnail_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['info']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 5px 15px;
                font-weight: normal;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {COLORS['info_hover']};
                border: none;
            }}
        """)
        thumbnail_row.addWidget(thumbnail_btn)
        thumbnail_section.addLayout(thumbnail_row)
        sections_layout.addLayout(thumbnail_section, 1)

        # 액션 섹션 (활성화·비활성화 + 삭제) (균등 배분)
        action_section = QVBoxLayout()
        action_section.setSpacing(3)

        action_row = QHBoxLayout()
        action_row.setSpacing(5)

        # 활성화·비활성화 버튼
        is_active = self.site_data.get("active", True)
        toggle_btn = QPushButton("🟢 활성화" if is_active else "🔴 비활성화")
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_btn.clicked.connect(lambda: self.toggle_site_status())
        toggle_btn.setMinimumSize(90, 30)
        toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {'#A3BE8C' if is_active else '#BF616A'};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {'#B48EAD' if is_active else '#D08770'};
            }}
        """)
        action_row.addWidget(toggle_btn)

        # 삭제 버튼 (크기 줄임)
        delete_btn = QPushButton("🗑️ 삭제")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.site_data["id"]))
        delete_btn.setMinimumSize(70, 30)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #BF616A;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: #D08770;
            }}
        """)
        action_row.addWidget(delete_btn)

        action_section.addLayout(action_row)
        sections_layout.addLayout(action_section, 1)

        card_layout.addLayout(sections_layout)

        # 위젯이 제대로 정리됨
        layout.addWidget(main_card)

        # 카드 전체 스타일링
        self.setStyleSheet(f"""
            SiteWidget {{
                background-color: {COLORS['surface']};
                border: 2px solid {COLORS['border']};
                border-radius: 15px;
                margin: 8px;
                padding: 5px;
            }}
            SiteWidget:hover {{
                border-color: {COLORS['primary']};
                background-color: {COLORS['surface_light']};
            }}
        """)

        self.setLayout(layout)

    def open_wp_admin(self):
        """워드프레스 관리자 페이지 열기"""
        try:
            import webbrowser
            url = self.site_data.get('url', '')
            if url:
                if not url.endswith('/'):
                    url += '/'
                wp_admin_url = url + 'wp-admin'
                webbrowser.open(wp_admin_url)
        except Exception as e:
            print(f"URL 열기 실패: {e}")

    def get_keywords_count(self):
        """키워드 개수 조회 - 사용자가 선택한 키워드 파일만 사용"""
        try:
            keyword_file = self.site_data.get("keyword_file", "")
            if not keyword_file:
                return 0

            keyword_path = os.path.join(get_base_path(), "keywords", keyword_file)
            if not os.path.exists(keyword_path):
                return 0

            with open(keyword_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 주석 제거하고 빈 줄 제거
            keyword_count = 0
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    keyword_count += 1

            return keyword_count

        except Exception as e:
            print(f"키워드 개수 조회 오류: {e}")
            return 0

    def move_keyword_to_used(self, keyword, keyword_file):
        """사용한 키워드를 used 파일로 이동 - 'used_' 접두사 붙인 파일로 이동"""
        try:
            base_path = get_base_path()
            keywords_dir = os.path.join(base_path, "keywords")

            # 원본 키워드 파일 경로
            original_file = os.path.join(keywords_dir, keyword_file)
            if not os.path.exists(original_file):
                print(f"❌ 키워드 파일이 존재하지 않습니다: {keyword_file}")
                return False

            # 'used_' 접두사가 붙은 파일명 생성 (예: ai-news_keywords.txt -> used_ai-news_keywords.txt)
            used_filename = f"used_{keyword_file}"
            used_file = os.path.join(keywords_dir, used_filename)

            # 원본 파일에서 키워드 제거
            with open(original_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 키워드가 포함된 라인 찾아서 제거 (정확히 일치하는 라인만)
            new_lines = []
            keyword_removed = False
            for line in lines:
                if line.strip() == keyword.strip():
                    keyword_removed = True
                    print(f"🔍 키워드 '{keyword}' 발견하여 제거")
                    continue
                new_lines.append(line)

            if keyword_removed:
                # 원본 파일에 업데이트된 내용 저장
                with open(original_file, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)

                # used 파일에 키워드 추가 (파일이 없으면 자동 생성)
                with open(used_file, 'a', encoding='utf-8') as f:
                    f.write(f"{keyword.strip()}\n")

                print(f"✅ 키워드 '{keyword}' 이동 완료: {keyword_file} -> {used_filename}")
                return True
            else:
                print(f"📌 키워드 '{keyword}'를 {keyword_file}에서 찾을 수 없습니다.")
                return False

        except Exception as e:
            print(f"❌ 키워드 이동 중 오류: {e}")
            return False

    def get_next_keyword(self, keyword_file):
        """키워드 파일에서 다음 키워드 가져오기"""
        try:
            keywords_dir = os.path.join(get_base_path(), "keywords")
            keyword_path = os.path.join(keywords_dir, keyword_file)

            if not os.path.exists(keyword_path):
                return None

            with open(keyword_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 첫 번째 유효한 키워드 찾기
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    return line

            return None

        except Exception as e:
            print(f"키워드 가져오기 오류: {e}")
            return None

    def get_thumbnails_count(self):
        """썸네일 개수 조회 (자동 생성되므로 항상 충분)"""
        return "자동생성"

    def get_thumbnail_info(self):
        """썸네일 정보 조회 - 사용자가 선택한 썸네일 파일만 사용"""
        try:
            thumbnail_image = self.site_data.get("thumbnail_image", "")
            if thumbnail_image:
                thumbnail_path = os.path.join(get_base_path(), "images", thumbnail_image)
                if os.path.exists(thumbnail_path):
                    return thumbnail_image
                else:
                    return f"파일 없음 {thumbnail_image}"
            else:
                return "선택 안됨"

        except Exception as e:
            print(f"썸네일 정보 조회 오류: {e}")
            return "조회 실패"

    def toggle_site_status(self):
        """사이트 활성화/비활성화 토글"""
        self.toggle_requested.emit(self.site_data["id"])

    def create_info_widget(self, icon, label, value, color):
        """정보 위젯 생성"""
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # 아이콘
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 14px; color: {color};")
        layout.addWidget(icon_label)

        # 라벨
        label_widget = QLabel(label)
        label_widget.setStyleSheet(f"font-weight: bold; color: {COLORS['text']};")
        layout.addWidget(label_widget)

        layout.addStretch()

        # 값
        value_widget = QLabel(str(value))
        value_widget.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(value_widget)

        widget.setLayout(layout)
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['surface_light']};
                border: 1px solid {color};
                border-radius: 8px;
                margin: 2px;
            }}
        """)

        return widget

    def get_button_style(self, color):
        """버튼 스타일 생성"""
        return f"""
            QPushButton {{
                background-color: {color};
                color: {COLORS['text']};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 10pt;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['surface_dark']};
            }}
        """

    def open_keyword_file(self):
        """키워드 파일 열기"""
        try:
            import subprocess
            import os
            
            keyword_file = self.site_data.get("keyword_file", "")
            if not keyword_file:
                QMessageBox.information(None, "알림", "키워드 파일이 설정되지 않았습니다.")
                return
                
            # keywords 폴더에서 파일 찾기
            keyword_path = os.path.join(get_base_path(), "keywords", keyword_file)
            
            if not os.path.exists(keyword_path):
                QMessageBox.warning(None, "파일 없음", f"키워드 파일을 찾을 수 없습니다:\n{keyword_path}")
                return
                
            # Windows에서 기본 프로그램으로 파일 열기
            subprocess.run(['start', keyword_path], shell=True, check=True)
            
        except Exception as e:
            QMessageBox.critical(None, "오류", f"키워드 파일을 열 수 없습니다:\n{e}")

    def open_thumbnail_file(self):
        """썸네일 파일 열기"""
        try:
            import subprocess
            import os
            
            thumbnail_file = self.site_data.get("thumbnail_file", "")
            if not thumbnail_file:
                QMessageBox.information(None, "알림", "썸네일 파일이 설정되지 않았습니다.")
                return
                
            # images 폴더에서 파일 찾기
            thumbnail_path = os.path.join(get_base_path(), "images", thumbnail_file)
            
            if not os.path.exists(thumbnail_path):
                QMessageBox.warning(None, "파일 없음", f"썸네일 파일을 찾을 수 없습니다:\n{thumbnail_path}")
                return
                
            # Windows에서 기본 프로그램으로 파일 열기
            subprocess.run(['start', thumbnail_path], shell=True, check=True)
            
        except Exception as e:
            QMessageBox.critical(None, "오류", f"썸네일 파일을 열 수 없습니다:\n{e}")
            
class MainWindow(QMainWindow):
    """메인 윈도우"""

    # 시그널 정의
    update_buttons_signal = pyqtSignal()  # 버튼 상태 업데이트용

    def __init__(self):
        super().__init__()
        
        self.config_manager = ConfigManager()
        
        self.resource_scanner = ResourceScanner(get_base_path())

        # 포스팅 상태 변수
        self.is_posting = False
        self.is_paused = False
        self.posting_thread = None
        self.posting_worker = None  # 포스팅 워커 추가
        self.remaining_keywords = []
        self.current_keyword = ""
        self.config_data = {}  # 설정 데이터 초기화
        self.used_keywords = set()  # 사용한 키워드 추적
        self.keyword_to_file = {}  # 키워드 -> 파일명 매핑
        
        # 다음 포스팅 시간 추적 변수들
        self.next_posting_time = None
        self.posting_interval_seconds = 0
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_next_posting_countdown)
        
        # 현재 포스팅 중인 사이트 추적
        self.current_posting_site = None

        self.setup_ui()
        
        try:
            self.load_sites()
        except Exception as e:
            print(f"⚠️ 사이트 로드 실패 (무시하고 계속): {e}", flush=True)

        # API 키 상태 확인
        QTimer.singleShot(500, self.check_and_update_api_status)

        # 시그널 연결

    # ==================== 중앙 집중식 스타일 관리 ====================
    
    def get_card_container_style(self):
        """카드 컨테이너 공통 스타일 반환"""
        return {
            'max_height': 180,  # 160에서 180으로 증가
            'min_height': 140,  # 120에서 140으로 증가
            'min_width': 300,
            'size_policy': (QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred),
            'contents_margins': (20, 20, 20, 20),
            'spacing': 12,
            'stylesheet': f"""
                QWidget {{
                    background-color: {COLORS['background']};
                    border: 2px solid {COLORS['surface']};
                    border-radius: 12px;
                    margin: 5px;
                }}
                QWidget:hover {{
                    border-color: {COLORS['primary']};
                    background-color: {COLORS['surface_light']};
                }}
            """
        }
    
    def get_card_title_style(self):
        """카드 제목 공통 스타일 반환"""
        return f"""
            QPushButton {{
                color: {COLORS['primary']};
                font-size: 14px;
                font-weight: normal;
                background: transparent;
                border: none;
                padding: 0px;
                text-align: center;
            }}
            QPushButton:hover {{
                color: {COLORS['primary_hover']};
                text-decoration: underline;
            }}
        """
    
    def get_card_button_style(self):
        """카드 버튼 공통 스타일 반환"""
        return {
            'fixed_height': 55,
            'size_policy': (QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed),
            'stylesheet': f"""
                QPushButton {{
                    background-color: {COLORS['surface']};
                    color: {COLORS['text']};
                    border: 2px solid {COLORS['primary']};
                    border-radius: 10px;
                    padding: 15px 20px;
                    font-weight: normal;
                    font-size: 10pt;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['primary']};
                    color: white;
                    border-color: {COLORS['info']};
                }}
            """
        }
    
    def get_card_combobox_style(self):
        """카드 콤보박스 공통 스타일 반환"""
        return {
            'fixed_height': 60,  # 65에서 60으로 줄임
            'min_width': 290,    # 280에서 290으로 증가
            'size_policy': (QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed),
            'stylesheet': f"""
                QComboBox {{
                    background-color: {COLORS['surface']};
                    color: white;
                    border: 2px solid {COLORS['primary']};
                    border-radius: 10px;
                    padding: 17px 15px;  # 좌우 패딩을 줄여서 중앙정렬 맞춤
                    font-weight: normal;
                    font-size: 10pt;
                }}
                QComboBox:hover {{
                    background-color: {COLORS['primary']};
                    color: white;
                    border-color: {COLORS['info']};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 20px;
                }}
                QComboBox::down-arrow {{
                    image: none;
                    border: none;
                    width: 0px;
                    height: 0px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {COLORS['surface']};
                    color: white;
                    selection-background-color: {COLORS['primary']};
                    selection-color: white;
                    outline: none;
                    border: 1px solid {COLORS['border']};
                    border-radius: 5px;
                    font-size: 10pt;
                    font-weight: normal;
                    padding: 5px;
                }}
                QComboBox QAbstractItemView::item {{
                    color: white;
                    padding: 8px;
                }}
                QComboBox QAbstractItemView::item:selected {{
                    background-color: {COLORS['primary']};
                    color: white;
                }}
            """
        }

    def create_unified_card(self, title, value, callback=None, widget_type="button"):
        """통합된 카드 생성 함수 - 모든 카드가 동일한 스타일 사용"""
        # 컨테이너 설정
        container = QWidget()
        container_style = self.get_card_container_style()
        
        container.setMaximumHeight(container_style['max_height'])
        container.setMinimumHeight(container_style['min_height'])
        container.setMinimumWidth(container_style['min_width'])
        container.setSizePolicy(*container_style['size_policy'])
        container.setStyleSheet(container_style['stylesheet'])
        
        # 레이아웃 설정
        layout = QVBoxLayout(container)
        layout.setContentsMargins(*container_style['contents_margins'])
        layout.setSpacing(container_style['spacing'])

        # 제목 라벨
        title_label = QPushButton(title)
        title_label.setFlat(True)
        title_label.setStyleSheet(self.get_card_title_style())
        
        if callback:
            title_label.clicked.connect(callback)
            title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout.addWidget(title_label)

        # 값 위젯 (버튼 또는 콤보박스)
        if widget_type == "combobox":
            value_widget = QComboBox()
            style_config = self.get_card_combobox_style()
            
            value_widget.setFixedHeight(style_config['fixed_height'])
            value_widget.setMinimumWidth(style_config['min_width'])
            value_widget.setSizePolicy(*style_config['size_policy'])
            value_widget.setStyleSheet(style_config['stylesheet'])
            value_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # 콤보박스를 편집 가능하게 만들고 텍스트 중앙 정렬
            value_widget.setEditable(True)
            value_widget.lineEdit().setReadOnly(True)
            value_widget.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
            # lineEdit의 패딩도 조정하여 제목과 정확히 맞춤
            value_widget.lineEdit().setStyleSheet("""
                QLineEdit {
                    background: transparent;
                    border: none;
                    color: white;
                    padding: 0px 2px;
                    margin: 0px;
                }
            """)
            
            # 스크롤 기능 비활성화
            value_widget.wheelEvent = lambda event: None
            
        else:  # button
            value_widget = QPushButton(value)
            style_config = self.get_card_button_style()
            
            value_widget.setFixedHeight(style_config['fixed_height'])
            value_widget.setSizePolicy(*style_config['size_policy'])
            value_widget.setStyleSheet(style_config['stylesheet'])
            
            if callback:
                value_widget.clicked.connect(callback)
                value_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                value_widget.setEnabled(False)

        layout.addWidget(value_widget)

        # value_widget을 container의 속성으로 저장
        container.value_button = value_widget
        container.value_widget = value_widget  # 콤보박스용 별칭
        
        return container
        self.update_buttons_signal.connect(self._safe_update_button_states)

        # 상태 정보 초기화(UI 생성 후 실행)
        QTimer.singleShot(500, self.refresh_all_status)  # 0.5초 뒤 실행
        
        # 포스팅 제어 버튼 초기 상태 설정
        QTimer.singleShot(600, self.initialize_posting_buttons)  # 0.6초 뒤 실행

        # 🔒 마지막 포스팅 상태 복원
        QTimer.singleShot(700, self.restore_last_posting_state)  # 0.7초 뒤 실행

        # 키보드 단축키 설정
        self.setup_keyboard_shortcuts()
        
        # 초기화 완료 테스트 메시지 (디버깅용) - 프로그램 시작 시에만 한 번 실행
        # 시스템 초기화 완료 (시작 메시지에서 이미 표시되므로 제거)
        # 상태 복원 메시지는 제거 (불필요하고 간섭 발생)

    def restore_last_posting_state(self):
        """마지막 포스팅 상태 복원 - 포스팅 중이 아닐 때만 실행"""
        try:
            # 포스팅 중이면 상태 복원하지 않음 (간섭 방지)
            if self.is_posting:
                return
                
            posting_state = self.config_manager.get_posting_state()
            last_site_url = posting_state.get("last_site_url", "")
            
            if last_site_url:
                # 현재 사이트 표시 업데이트
                self.current_posting_site = self.clean_url_for_display(last_site_url)
                
                # 콤보박스에서 해당 사이트 선택
                if hasattr(self, 'current_site_combo'):
                    start_site_id = self.config_manager.get_start_site_id()
                    if start_site_id:
                        for i in range(self.current_site_combo.count()):
                            if self.current_site_combo.itemData(i) == start_site_id:
                                self.current_site_combo.setCurrentIndex(i)
                                break
                
                # 상태 메시지 표시
                if posting_state.get("posting_in_progress", False):
                    self.update_posting_status(f"🔗 마지막으로 {self.current_posting_site}에서 포스팅이 중단되었습니다.")
                else:
                    self.update_posting_status(f"🔗 다음 포스팅 예정 사이트: {self.current_posting_site}")
            else:
                self.update_posting_status("📍 새로운 포스팅 세션을 시작합니다.")
                
        except Exception as e:
            print(f"마지막 포스팅 상태 복원 오류: {e}")
            self.update_posting_status("⚠️ 포스팅 상태 복원 중 오류가 발생했습니다.")

    def setup_keyboard_shortcuts(self):
        """키보드 단축키 설정"""
        from PyQt6.QtGui import QShortcut, QKeySequence
        
        # F5 키로 새로고침
        refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_shortcut.activated.connect(self.refresh_monitoring_tab)

    def refresh_monitoring_tab(self):
        """모니터링 탭 전용 새로고침 (키워드와 썸네일 포함)"""
        try:
            # 기존 상태 새로고침
            self.refresh_all_status()
            
            # 키워드 파일과 썸네일 파일 다시 스캔
            self.reload_keyword_files()
            self.reload_thumbnail_files()
            
            self.update_posting_status("🔄 F5 새로고침 완료 - 키워드와 썸네일 목록이 업데이트되었습니다!")
            print("🔄 F5 새로고침 완료")
            
        except Exception as e:
            self.update_posting_status(f"❌ 새로고침 중 오류: {str(e)}")
            print(f"❌ 새로고침 중 오류: {e}")

    def reload_keyword_files(self):
        """키워드 파일 목록 다시 로드"""
        try:
            keywords_dir = os.path.join(get_base_path(), "keywords")
            if os.path.exists(keywords_dir):
                # 키워드 파일 목록 업데이트 로직
                print("📝 키워드 파일 목록 새로고침 완료")
        except Exception as e:
            print(f"키워드 파일 새로고침 오류: {e}")

    def reload_thumbnail_files(self):
        """썸네일 파일 목록 다시 로드"""
        try:
            thumbnails_dir = os.path.join(get_base_path(), "thumbnails")
            images_dir = os.path.join(get_base_path(), "images")
            
            # 썸네일 파일 목록 업데이트 로직
            if os.path.exists(thumbnails_dir):
                print("🖼️ 썸네일 파일 목록 새로고침 완료")
            if os.path.exists(images_dir):
                print("🖼️ 이미지 파일 목록 새로고침 완료")
                
        except Exception as e:
            print(f"썸네일 파일 새로고침 오류: {e}")

    def resizeEvent(self, event):
        """창 크기 변경 이벤트 - 반응형 레이아웃 적용"""
        super().resizeEvent(event)
        
        try:
            # 창 크기 정보
            width = event.size().width()
            height = event.size().height()
            
            # 반응형 레이아웃 적용 (안전한 방법)
            self.apply_responsive_layout(width, height)
            
        except Exception as e:
            print(f"창 크기 변경 처리 오류: {e}")

    def apply_responsive_layout(self, width, height):
        """반응형 레이아웃 적용 - 안전한 방법으로 구현"""
        try:
            # 모니터링 탭의 그리드 레이아웃 조정
            if hasattr(self, 'settings_grid'):
                self.adjust_monitoring_grid(width)
                
            # 사이트 관리 탭의 버튼 레이아웃 조정
            if hasattr(self, 'add_site_btn'):
                self.adjust_site_buttons_layout(width)
                
        except Exception as e:
            print(f"반응형 레이아웃 적용 오류: {e}")

    def adjust_monitoring_grid(self, width):
        """모니터링 탭 그리드 조정 - 안전한 방법"""
        try:
            if not hasattr(self, 'settings_grid'):
                return
                
            # 창 너비에 따라 그리드 열 수 결정
            if width < 600:
                # 작은 화면: 1열
                columns = 1
            elif width < 900:
                # 중간 화면: 2열  
                columns = 2
            else:
                # 큰 화면: 3열
                columns = 3
                
            # 현재 그리드와 다른 경우에만 재배치
            if not hasattr(self, '_current_grid_columns') or self._current_grid_columns != columns:
                self._current_grid_columns = columns
                self.rearrange_monitoring_widgets(columns)
                
        except Exception as e:
            print(f"모니터링 그리드 조정 오류: {e}")

    def rearrange_monitoring_widgets(self, columns):
        """모니터링 위젯들을 새로운 열 수로 재배치"""
        try:
            if not hasattr(self, 'settings_grid'):
                return
                
            # 기존 위젯들을 임시로 저장
            widgets = []
            
            # 그리드에서 위젯들을 제거하고 저장
            if hasattr(self, 'ai_model_label'):
                widgets.append(self.ai_model_label)
                self.settings_grid.removeWidget(self.ai_model_label)
            if hasattr(self, 'posting_mode_label'):
                widgets.append(self.posting_mode_label)
                self.settings_grid.removeWidget(self.posting_mode_label)
            if hasattr(self, 'total_keywords_label'):
                widgets.append(self.total_keywords_label)
                self.settings_grid.removeWidget(self.total_keywords_label)
            if hasattr(self, 'site_label'):
                widgets.append(self.site_label)
                self.settings_grid.removeWidget(self.site_label)
            if hasattr(self, 'next_posting_label'):
                widgets.append(self.next_posting_label)
                self.settings_grid.removeWidget(self.next_posting_label)
            if hasattr(self, 'refresh_container'):
                widgets.append(self.refresh_container)
                self.settings_grid.removeWidget(self.refresh_container)
                
            # 새로운 열 수로 재배치
            for i, widget in enumerate(widgets):
                row = i // columns
                col = i % columns
                self.settings_grid.addWidget(widget, row, col)
                
            print(f"모니터링 그리드를 {columns}열로 재배치 완료")
            
        except Exception as e:
            print(f"모니터링 위젯 재배치 오류: {e}")

    def adjust_site_buttons_layout(self, width):
        """사이트 관리 탭 버튼 레이아웃 및 여백 조정"""
        try:
            # 창 크기에 따른 여백 조정
            if hasattr(self, 'sites_main_layout'):
                if width < 600:
                    # 작은 화면: 여백 최소화
                    margin = 8
                elif width < 900:
                    # 중간 화면: 적당한 여백
                    margin = 15
                else:
                    # 큰 화면: 충분한 여백
                    margin = 20
                
                self.sites_main_layout.setContentsMargins(margin, margin, margin, margin)
                print(f"사이트 관리 탭 여백을 {margin}px로 조정")
            
            # 버튼 크기나 간격 조정
            if width < 700:
                # 작은 화면에서는 버튼 텍스트 줄이기
                if hasattr(self, 'add_site_btn'):
                    self.add_site_btn.setText("➕ 추가")
                if hasattr(self, 'keywords_folder_btn'):
                    self.keywords_folder_btn.setText("📂 키워드")
                if hasattr(self, 'images_folder_btn'):
                    self.images_folder_btn.setText("🖼️ 이미지")
            else:
                # 큰 화면에서는 전체 텍스트
                if hasattr(self, 'add_site_btn'):
                    self.add_site_btn.setText("➕ 새 사이트 추가")
                if hasattr(self, 'keywords_folder_btn'):
                    self.keywords_folder_btn.setText("📂 Keywords 폴더 열기")
                if hasattr(self, 'images_folder_btn'):
                    self.images_folder_btn.setText("🖼️ Images 폴더 열기")
                    
        except Exception as e:
            print(f"사이트 버튼 레이아웃 조정 오류: {e}")

    def setup_ui(self):
        """UI 설정 - 간단한 레이아웃"""
        self.setWindowTitle("Auto WP multi-site - 멀티 사이트 관리 시스템")
        
        # 기본 창 크기 설정 (반응형 복잡성 제거)
        self.setGeometry(50, 50, 1400, 900)
        
        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 메인 레이아웃 (기본 설정)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 탭 위젯 (기본 설정)
        self.tab_widget = QTabWidget()

        # 모니터링 탭 (원래 버전으로 복원)
        try:
            self.monitoring_tab = self.create_monitoring_tab()
            self.tab_widget.addTab(self.monitoring_tab, "📊 모니터링")
        except Exception as e:
            print(f"⚠️ 모니터링 탭 생성 실패, 간단한 버전 사용: {e}", flush=True)
            self.monitoring_tab = self.create_simple_monitoring_tab()
            self.tab_widget.addTab(self.monitoring_tab, "📊 모니터링")

        # 사이트 관리 탭 (원래 버전으로 복원, 하지만 안전하게)
        try:
            self.sites_tab = self.create_sites_tab()
            self.tab_widget.addTab(self.sites_tab, "🌍 사이트 관리")
        except Exception as e:
            print(f"⚠️ 사이트 관리 탭 생성 실패, 간단한 버전 사용: {e}", flush=True)
            self.sites_tab = self.create_simple_sites_tab()
            self.tab_widget.addTab(self.sites_tab, "🌍 사이트 관리")

        # 설정 탭 (원래 버전으로 복원)
        self.settings_tab = self.create_settings_tab()
        self.tab_widget.addTab(self.settings_tab, "⚙️ 설정")

        main_layout.addWidget(self.tab_widget)
        central_widget.setLayout(main_layout)

        # 다크 모드 스타일 적용
        self.setStyleSheet(f"""
            /* 메인 윈도우 */
            QMainWindow {{
                background-color: {COLORS['background']};
                color: {COLORS['text']};
            }}

            /* 입력 필드 */
            QLineEdit {{
                background-color: {COLORS['surface']};
                border: 2px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {COLORS['text']};
                selection-background-color: {COLORS['primary']};
            }}
            QLineEdit:focus {{
                border-color: {COLORS['primary']};
                background-color: {COLORS['surface_light']};
            }}
            QLineEdit:hover {{
                border-color: {COLORS['primary_hover']};
            }}

            /* 텍스트 에디터 */
            QTextEdit {{
                background-color: {COLORS['surface']};
                border: 2px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px;
                color: {COLORS['text']};
                selection-background-color: {COLORS['primary']};
            }}
            QTextEdit:focus {{
                border-color: {COLORS['primary']};
            }}

            /* 콤보박스 */
            QComboBox {{
                background-color: {COLORS['surface']};
                border: 2px solid {COLORS['border']};
                border-radius: 6px;
                padding: 6px 12px;
                color: {COLORS['text']};
                min-width: 120px;
            }}
            QComboBox:focus {{
                border-color: {COLORS['primary']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {COLORS['text']};
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                selection-background-color: {COLORS['primary']};
                color: {COLORS['text']};
            }}

            /* 스핀박스 */
            QSpinBox {{
                background-color: {COLORS['surface']};
                border: 2px solid {COLORS['border']};
                border-radius: 6px;
                padding: 6px;
                color: {COLORS['text']};
            }}
            QSpinBox:focus {{
                border-color: {COLORS['primary']};
            }}

            /* 버튼 */
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
                min-height: 16px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['accent']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['border']};
                color: {COLORS['text_muted']};
            }}

            /* 체크박스 */
            QCheckBox {{
                color: {COLORS['text']};
                spacing: 8px;
                font-size: 13px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 3px;
            }}
            QCheckBox::indicator:unchecked {{
                border: 2px solid {COLORS['border']};
                background-color: {COLORS['surface']};
            }}
            QCheckBox::indicator:unchecked:hover {{
                border-color: {COLORS['primary']};
            }}
            QCheckBox::indicator:checked {{
                border: 2px solid {COLORS['primary']};
                background-color: {COLORS['primary']};
                image: none;
            }}

            /* 라벨 */
            QLabel {{
                color: {COLORS['text']};
                background-color: transparent;
                font-size: 13px;
            }}

            /* 탭 위젯 */
            QTabWidget::pane {{
                border: 1px solid {COLORS['border']};
                background-color: {COLORS['surface']};
                border-radius: 6px;
                margin-top: 2px;
            }}
            QTabBar::tab {{
                background-color: {COLORS['surface_dark']};
                color: {COLORS['text_muted']};
                padding: 12px 24px;
                margin-right: 2px;
                border: 1px solid {COLORS['border']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                background-color: {COLORS['primary']};
                color: white;
                border-color: {COLORS['primary']};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {COLORS['hover']};
                color: {COLORS['text']};
            }}

            /* 그룹박스 - 곡선 스타일 */
            QGroupBox {{
                font-weight: 600;
                font-size: 14px;
                color: {COLORS['text']};
                border: 2px solid {COLORS['border']};
                border-radius: 15px;
                margin-top: 12px;
                padding-top: 16px;
                background-color: {COLORS['surface']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: {COLORS['primary']};
                font-weight: 700;
                background-color: {COLORS['surface']};
            }}

            /* 스크롤 영역 */
            QScrollArea {{
                background-color: {COLORS['background']};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['surface_dark']};
                width: 12px;
                border-radius: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['border']};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['primary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
        """)

    def create_sites_tab(self):
        """사이트 관리 탭 생성 - 반응형 스크롤 지원"""
        print("🌍 사이트 탭: 스크롤 영역 생성 중...", flush=True)
        # 스크롤 영역 생성
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        print("🌍 사이트 탭: 스크롤 스타일 설정 중...", flush=True)
        # 스크롤 스타일
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #3B4252;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #5E81AC;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #81A1C1;
            }
        """)

        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['surface']};
            }}
        """)
        # 사이트 관리 탭의 메인 레이아웃 (반응형 여백 적용)
        self.sites_main_layout = QVBoxLayout()
        self.sites_main_layout.setContentsMargins(20, 20, 20, 20)  # 기본 여백
        self.sites_main_layout.setSpacing(20)
        layout = self.sites_main_layout

        # 새 사이트 추가 폼 (처음에는 숨김) - 임시로 간단한 위젯으로 대체
        try:
            self.add_site_form = self.create_add_site_form()
            self.add_site_form.hide()
            layout.addWidget(self.add_site_form)
        except Exception as e:
            print(f"⚠️ 사이트 탭: 새 사이트 추가 폼 생성 실패 - {e}", flush=True)
            # 임시 위젯으로 대체
            self.add_site_form = QWidget()
            self.add_site_form.hide()
            layout.addWidget(self.add_site_form)

        # 상단 버튼 (간소화)
        button_layout = QHBoxLayout()

        self.add_site_btn = QPushButton("➕ 새 사이트 추가")
        self.add_site_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.add_site_btn.setMinimumWidth(120)  # 최소 너비 설정
        self.add_site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_site_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #B48EAD;
                color: white;
                font-weight: normal;
                padding: 10px 15px;
                border-radius: 8px;
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #C4A2B8;
            }}
        """)
        self.add_site_btn.clicked.connect(self.toggle_add_site_form)
        button_layout.addWidget(self.add_site_btn)

        self.keywords_folder_btn = QPushButton("📂 Keywords 폴더 열기")
        self.keywords_folder_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.keywords_folder_btn.setMinimumWidth(100)  # 최소 너비 설정
        self.keywords_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keywords_folder_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #D08770;
                color: white;
                font-weight: normal;
                padding: 10px 15px;
                border-radius: 8px;
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #D89B82;
            }}
        """)
        self.keywords_folder_btn.clicked.connect(self.open_keywords_folder)
        button_layout.addWidget(self.keywords_folder_btn)

        self.images_folder_btn = QPushButton("🖼️ Images 폴더 열기")
        self.images_folder_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.images_folder_btn.setMinimumWidth(100)  # 최소 너비 설정
        self.images_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.images_folder_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #A3BE8C;
                color: white;
                font-weight: normal;
                padding: 10px 15px;
                border-radius: 8px;
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #B5CCA3;
            }}
        """)
        self.images_folder_btn.clicked.connect(self.open_images_folder)
        button_layout.addWidget(self.images_folder_btn)

        # 새로고침 버튼 추가
        self.refresh_sites_btn = QPushButton("🔄 새로고침")
        self.refresh_sites_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.refresh_sites_btn.setMinimumWidth(100)  # 최소 너비 설정
        self.refresh_sites_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_sites_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #5E81AC;
                color: white;
                font-weight: normal;
                padding: 10px 15px;
                border-radius: 8px;
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #7093C0;
            }}
        """)
        self.refresh_sites_btn.clicked.connect(self.refresh_site_list)
        button_layout.addWidget(self.refresh_sites_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # 사이트 목록 스크롤 영역 (간소화)
        sites_scroll = QScrollArea()
        sites_scroll.setWidgetResizable(True)
        sites_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.sites_container = QWidget()
        self.sites_layout = QVBoxLayout()
        self.sites_layout.addStretch()
        self.sites_container.setLayout(self.sites_layout)

        sites_scroll.setWidget(self.sites_container)
        layout.addWidget(sites_scroll)

        widget.setLayout(layout)
        
        # 외부 스크롤 영역에 위젯 설정
        scroll_area.setWidget(widget)
        
        return scroll_area

    def create_add_site_form(self):
        """인라인 사이트 추가 폼 생성"""
        form_widget = QWidget()
        form_widget.setObjectName("addSiteForm")
        form_widget.setStyleSheet(f"""
            QWidget#addSiteForm {{
                background-color: {COLORS['surface']};
                border: 2px solid {COLORS['border']};
                border-radius: 8px;
                padding: 16px;
                margin: 8px 0;
            }}
        """)

        layout = QVBoxLayout()

        # 폼 타이틀
        title_label = QLabel("새 사이트 추가")
        title_label.setStyleSheet(f"""
            QLabel {{
                font-size: 16px;
                font-weight: bold;
                color: {COLORS['accent']};
                margin-bottom: 16px;
            }}
        """)
        layout.addWidget(title_label)

        # 폼 레이아웃
        form_layout = QFormLayout()

        # WordPress URL
        self.inline_url_edit = QLineEdit()
        self.inline_url_edit.setPlaceholderText("https://yoursite.com")
        form_layout.addRow("WordPress URL:", self.inline_url_edit)

        # 카테고리 ID
        self.inline_category_edit = QSpinBox()
        self.inline_category_edit.setRange(1, 9999)
        self.inline_category_edit.setValue(1)
        form_layout.addRow("카테고리 ID:", self.inline_category_edit)

        # 썸네일 이미지 선택
        thumbnail_layout = QHBoxLayout()
        self.inline_thumbnail_edit = QLineEdit()
        self.inline_thumbnail_edit.setPlaceholderText("썸네일 이미지 파일 (.jpg)")
        thumbnail_layout.addWidget(self.inline_thumbnail_edit)

        browse_thumbnail_btn = QPushButton("📂 찾아보기")
        browse_thumbnail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_thumbnail_btn.clicked.connect(self.browse_thumbnail_for_site)
        thumbnail_layout.addWidget(browse_thumbnail_btn)

        thumbnail_widget = QWidget()
        thumbnail_widget.setLayout(thumbnail_layout)
        form_layout.addRow("썸네일 이미지:", thumbnail_widget)

        # 키워드 파일 선택
        keywords_layout = QHBoxLayout()
        self.inline_keywords_edit = QLineEdit()
        self.inline_keywords_edit.setPlaceholderText("키워드 파일 (.txt)")
        keywords_layout.addWidget(self.inline_keywords_edit)

        browse_keywords_btn = QPushButton("📂 찾아보기")
        browse_keywords_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_keywords_btn.clicked.connect(self.browse_keywords_for_site)
        keywords_layout.addWidget(browse_keywords_btn)

        keywords_widget = QWidget()
        keywords_widget.setLayout(keywords_layout)
        form_layout.addRow("키워드 파일:", keywords_widget)

        layout.addLayout(form_layout)

        # 버튼 레이아웃
        button_layout = QHBoxLayout()

        # 연결 테스트 버튼
        test_btn = QPushButton("🔗 연결 테스트")
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.clicked.connect(self.test_inline_connection)
        button_layout.addWidget(test_btn)

        button_layout.addStretch()

        # 저장 버튼
        save_btn = QPushButton("💾 저장")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setObjectName("successButton")
        save_btn.setStyleSheet(f"""
            QPushButton#successButton {{
                background-color: {COLORS['success']};
                color: {COLORS['background']};
                padding: 8px 16px;
                border-radius: 4px;
                border: none;
                font-weight: bold;
            }}
            QPushButton#successButton:hover {{
                background-color: #8FBCBB;
            }}
        """)
        save_btn.clicked.connect(self.save_inline_site)
        button_layout.addWidget(save_btn)

        # 취소 버튼
        cancel_btn = QPushButton("❌ 취소")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setObjectName("dangerButton")
        cancel_btn.setStyleSheet(f"""
            QPushButton#dangerButton {{
                background-color: {COLORS['warning']};
                color: {COLORS['background']};
                padding: 8px 16px;
                border-radius: 4px;
                border: none;
                font-weight: bold;
            }}
            QPushButton#dangerButton:hover {{
                background-color: #D08770;
            }}
        """)
        cancel_btn.clicked.connect(self.cancel_inline_site)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        form_widget.setLayout(layout)
        return form_widget

    def create_monitoring_tab(self):
        """모니터링 탭 생성 - 설정 탭과 동일한 카드 스타일 적용"""
        # 스크롤 영역으로 전체 감싸기
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 스크롤 영역 부드럽게 설정
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #3B4252;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #5E81AC;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #81A1C1;
            }
        """)

        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['background']};
            }}
        """)
        layout = QVBoxLayout()
        layout.setSpacing(10)  # 20에서 10으로 줄임
        layout.setContentsMargins(20, 20, 20, 20)

        # 현재 설정 상태 카드
        status_group = QGroupBox("📊 현재 설정 상태")
        status_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600;
                font-size: 14px;
                color: {COLORS['text']};
                border: 2px solid {COLORS['border']};
                border-radius: 15px;
                margin-top: 12px;
                padding-top: 16px;
                background-color: {COLORS['surface']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: {COLORS['primary']};
                font-weight: 700;
                background-color: {COLORS['surface']};
            }}
        """)
        status_layout = QVBoxLayout()
        status_layout.setSpacing(25)
        status_layout.setContentsMargins(20, 20, 20, 20)

        # 설정 정보 표시 - 3x2 그리드
        self.settings_grid = QGridLayout()
        self.settings_grid.setSpacing(15)
        
        # 컬럼 스트레치 설정 (균등 분배)
        self.settings_grid.setColumnStretch(0, 1)
        self.settings_grid.setColumnStretch(1, 1)
        self.settings_grid.setColumnStretch(2, 1)
        
        # 첫 번째 행
        self.ai_model_label = self.create_unified_card("🤖 AI 모델", "", self.goto_settings_ai, "combobox")
        self.ai_model_combo = self.ai_model_label.value_widget
        self.settings_grid.addWidget(self.ai_model_label, 0, 0)
        
        self.posting_mode_label = self.create_unified_card("📝 포스팅 모드", "", self.goto_settings_posting_mode, "combobox")
        self.posting_mode_combo = self.posting_mode_label.value_widget
        self.settings_grid.addWidget(self.posting_mode_label, 0, 1)
        
        self.total_keywords_label = self.create_unified_card("📊 총 키워드", "", self.goto_site_management, "combobox")
        self.total_keywords_combo = self.total_keywords_label.value_widget
        self.settings_grid.addWidget(self.total_keywords_label, 0, 2)
        
        # 두 번째 행
        # 사이트 선택 ('다른 설정 라벨과 동일한 스타일')
        self.site_label = self.create_site_selector_label()
        self.settings_grid.addWidget(self.site_label, 1, 0)
        
        self.next_posting_label = self.create_unified_card("⏰ 다음 포스팅", "대기중", self.goto_settings_interval, "button")
        self.settings_grid.addWidget(self.next_posting_label, 1, 1)
        
        # 새로고침 카드
        self.refresh_container = self.create_unified_card("🔄 새로고침", "", self.refresh_all_status, "combobox")
        self.refresh_combo = self.refresh_container.value_widget
        self.settings_grid.addWidget(self.refresh_container, 1, 2)
        
        status_layout.addLayout(self.settings_grid)
        
        # 포스팅 제어 버튼들
        status_layout.addSpacing(20)
        control_layout = QHBoxLayout()
        control_layout.setSpacing(15)
        
        # 시작 버튼
        self.start_btn = QPushButton("▶️ 시작")
        self.start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['success']};
                color: white;
                font-weight: bold;
                padding: 15px 25px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: #8FBCBB;
            }}
        """)
        self.start_btn.clicked.connect(self.start_posting)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        control_layout.addWidget(self.start_btn)
        
        # 중지 버튼
        self.stop_btn = QPushButton("🛑 중지")
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['danger']};
                color: white;
                font-weight: bold;
                padding: 15px 25px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: #D08770;
            }}
        """)
        self.stop_btn.clicked.connect(self.stop_posting)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        control_layout.addWidget(self.stop_btn)
        
        # 재개 버튼 (파란색으로 변경)
        self.resume_btn = QPushButton("⏯️ 재개")
        self.resume_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                font-weight: bold;
                padding: 15px 25px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: #7C9CBF;
            }}
        """)
        self.resume_btn.clicked.connect(self.resume_posting)
        self.resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        control_layout.addWidget(self.resume_btn)
        
        # 일시정지 버튼 (노란색으로 변경)
        self.pause_btn = QPushButton("⏸️ 일시정지")
        self.pause_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['warning']};
                color: white;
                font-weight: bold;
                padding: 15px 25px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: #EBCB8B;
            }}
        """)
        self.pause_btn.clicked.connect(self.pause_posting)
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        control_layout.addWidget(self.pause_btn)
        
        status_layout.addLayout(control_layout)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # 진행 상태 카드
        progress_group = QGroupBox("📜 진행 상태")
        progress_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600;
                font-size: 14px;
                color: {COLORS['text']};
                border: 2px solid {COLORS['border']};
                border-radius: 15px;
                margin-top: 12px;
                padding-top: 16px;
                background-color: {COLORS['surface']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: {COLORS['primary']};
                font-weight: 700;
                background-color: {COLORS['surface']};
            }}
        """)
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(15)
        progress_layout.setContentsMargins(15, 15, 15, 15)

        self.progress_text = QTextEdit()
        self.progress_text.setReadOnly(True)
        self.progress_text.setMinimumHeight(400)
        
        # 폰트 설정
        font = self.progress_text.font()
        font.setFamily("Segoe UI")
        font.setPointSize(10)
        self.progress_text.setFont(font)
        
        # 단순 텍스트만 사용 (HTML 비활성화)

        # 진행 상태 텍스트 영역 스타일 설정
        self.progress_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['surface']};
                color: {COLORS['text']};
                border: 2px solid {COLORS['border']};
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', monospace;
            }}
            QScrollBar:vertical {{
                border: none;
                background-color: {COLORS['surface_dark']};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['primary']};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['primary_hover']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
        """)

        # Ctrl+휠 확대/축소 기능 비활성화하고 커스텀 휠 이벤트 적용
        self.progress_text.wheelEvent = self.progress_wheel_event

        # 시작 메시지
        from datetime import datetime
        startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        startup_time_short = datetime.now().strftime("%H:%M:%S")
        base_path = get_base_path()
        
        # 마지막 포스팅 상태 확인
        last_posting_state = self.config_manager.get_posting_state()
        last_site_info = ""
        if last_posting_state.get('site_url'):
            last_site_info = f"\n[{startup_time_short}] 🔗 마지막으로 {last_posting_state['site_url']}에서 포스팅이 중단되었습니다."
        
        # 활성 사이트 수 확인
        active_sites = [site for site in self.config_manager.data.get('sites', []) if site.get('active', True)]
        active_sites_count = len(active_sites)
        
        # API 키 상태 확인
        openai_key = self.config_manager.data.get('api_keys', {}).get('openai', '')
        gemini_key = self.config_manager.data.get('api_keys', {}).get('gemini', '')
        openai_status = "✅" if openai_key.startswith('sk-') else "❌"
        gemini_status = "✅" if gemini_key.startswith('AIza') else "❌"
        
        # 설정 탭 정보와 JSON 연동 상태 체크
        config_check_result = self.check_settings_sync()
        
        startup_text = f"""🚀 Auto WP - 워드프레스 자동 포스팅
✨ 제작자 : 데이비

=====================================================================================
[{startup_time}] 📱 프로그램이 시작되었습니다.
[{startup_time}] 📂 기본 경로: {base_path}
[{startup_time}] ▶️ 포스팅 시작 버튼을 눌러 자동 포스팅을 시작하세요.
[{startup_time}] 📋 진행 상태가 이곳에 실시간으로 표시됩니다.{last_site_info}
[{startup_time_short}] 🔧 시스템 초기화가 완료되었습니다.
[{startup_time_short}] 🔧 마지막 포스팅 상태가 복원되었습니다.
[{startup_time_short}] 🔧 총 {active_sites_count}개의 활성 사이트 발견
[{startup_time_short}] 🔧 API 키 확인 - OpenAI: {openai_status}, Gemini: {gemini_status}
[{startup_time_short}] 🔧 총 {len(self.config_manager.data.get('sites', []))}개 사이트 등록됨
{config_check_result}
=====================================================================================
"""
        self.progress_text.setPlainText(startup_text)
        
        # GUI 업데이트 처리
        self.progress_text.repaint()

        progress_layout.addWidget(self.progress_text)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        widget.setLayout(layout)
        
        # 카드 색상과 동일한 배경색 적용 (모니터링 탭)
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['surface']};
            }}
        """)
        
        scroll_area.setWidget(widget)
        
        # 콤보박스들 초기화
        self.initialize_monitoring_combos()
        
        return scroll_area

    def initialize_monitoring_combos(self):
        """모니터링 탭의 콤보박스들 초기화"""
        try:
            # AI 모델 콤보박스 초기화
            if hasattr(self, 'ai_model_combo'):
                self.ai_model_combo.clear()
                ai_provider = self.config_manager.data["global_settings"].get("default_ai", "gemini")
                if ai_provider == "gemini":
                    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
                else:
                    models = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
                
                self.ai_model_combo.addItems(models)
                current_model = self.config_manager.data["global_settings"].get("ai_model", models[0])
                if current_model in models:
                    self.ai_model_combo.setCurrentText(current_model)
                else:
                    self.ai_model_combo.setCurrentIndex(0)
                
                # AI 모델 변경 시 설정 업데이트
                self.ai_model_combo.currentTextChanged.connect(self.on_ai_model_changed)
            
            # 포스팅 모드 콤보박스 초기화
            if hasattr(self, 'posting_mode_combo'):
                self.posting_mode_combo.clear()
                self.posting_mode_combo.addItems(["승인용", "수익용"])
                current_mode = self.config_manager.data["global_settings"].get("posting_mode", "승인용")
                self.posting_mode_combo.setCurrentText(current_mode)
                
                # 포스팅 모드 변경 시 설정 업데이트
                self.posting_mode_combo.currentTextChanged.connect(self.on_posting_mode_changed)
            
            # 다음 포스팅 카운트다운 초기화
            if hasattr(self, 'next_posting_label') and hasattr(self.next_posting_label, 'value_button'):
                self.next_posting_label.value_button.setText("대기중")
            
            # 총 키워드 콤보박스 초기화
            if hasattr(self, 'total_keywords_combo'):
                self.total_keywords_combo.clear()
                self.total_keywords_combo.addItems(["로딩 중", "키워드 없음", "오류 발생"])
                self.total_keywords_combo.setCurrentText("로딩 중")
            
            # 새로고침 콤보박스 초기화
            if hasattr(self, 'refresh_combo'):
                self.refresh_combo.clear()
                self.refresh_combo.addItems(["상태 갱신", "갱신 완료", "갱신 중"])
                self.refresh_combo.setCurrentText("상태 갱신")
                
        except Exception as e:
            print(f"콤보박스 초기화 오류: {e}")

    def on_ai_model_changed(self, model):
        """AI 모델 변경 시 설정 업데이트"""
        try:
            self.config_manager.data["global_settings"]["ai_model"] = model
            self.config_manager.save_config()
        except Exception as e:
            print(f"AI 모델 설정 저장 오류: {e}")

    def on_posting_mode_changed(self, mode):
        """포스팅 모드 변경 시 설정 업데이트"""
        try:
            self.config_manager.data["global_settings"]["posting_mode"] = mode
            self.config_manager.save_config()
        except Exception as e:
            print(f"포스팅 모드 설정 저장 오류: {e}")

    def create_clickable_setting_label(self, title, value, callback):
        """클릭 가능한 설정 라벨 생성 - 통합된 스타일 사용"""
        return self.create_unified_card(title, value, callback, "button")

    def create_site_selector_label(self):
        """사이트 선택을 위한 라벨 생성 - 통합된 스타일 사용"""
        container = self.create_unified_card("🌐 사이트", "", self.goto_site_management, "combobox")
        
        # 콤보박스 참조 저장
        self.current_site_combo = container.value_widget
        
        return container
        layout.setSpacing(2)

        # 제목
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt; font-weight: bold;")
        layout.addWidget(title_label)

        # 값(클릭 가능한 버튼으로 만들기)
        value_btn = QPushButton(value)
        value_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['surface']};
                color: {COLORS['text']};
                padding: 4px 8px;
                border-radius: 4px;
                border: 1px solid {COLORS['border']};
                font-size: 8pt;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {COLORS['surface_light']};
                border: 1px solid {COLORS['info']};
            }}
        """)

        if callback:
            value_btn.clicked.connect(callback)
            value_btn.setToolTip(f"{title} 설정 변경하기")

        layout.addWidget(value_btn)

        # 값 업데이트를 위한 참조 저장
        container.value_button = value_btn

        return container

    def check_settings_sync(self):
        """설정 탭 정보와 JSON 파일 연동 상태 체크"""
        try:
            from datetime import datetime
            startup_time_short = datetime.now().strftime("%H:%M:%S")
            check_results = []
            
            # AI 설정 체크
            ai_provider = self.config_manager.data["global_settings"].get("default_ai", "gemini")
            ai_model = self.config_manager.data["global_settings"].get("ai_model", "")
            
            openai_key = self.config_manager.data.get('api_keys', {}).get('openai', '')
            gemini_key = self.config_manager.data.get('api_keys', {}).get('gemini', '')
            
            if ai_provider == "openai" and not openai_key.startswith('sk-'):
                check_results.append(f"[{startup_time_short}] ⚠️ OpenAI 선택되었으나 API 키가 없습니다")
            elif ai_provider == "gemini" and not gemini_key.startswith('AIza'):
                check_results.append(f"[{startup_time_short}] ⚠️ Gemini 선택되었으나 API 키가 없습니다")
            
            # 포스팅 간격 체크
            interval = self.config_manager.data["global_settings"].get("posting_interval", 30)
            if interval < 10:
                check_results.append(f"[{startup_time_short}] ⚠️ 포스팅 간격이 너무 짧습니다 (10분 이상 권장)")
            
            # 사이트 설정 체크
            sites = self.config_manager.data.get('sites', [])
            active_sites = [site for site in sites if site.get('active', True)]
            
            for i, site in enumerate(active_sites):
                site_name = site.get('url', f'사이트{i+1}')
                if not site.get('keyword_file'):
                    check_results.append(f"[{startup_time_short}] ⚠️ {site_name}: 키워드 파일이 설정되지 않았습니다")
                if not site.get('thumbnail_image'):
                    check_results.append(f"[{startup_time_short}] ⚠️ {site_name}: 썸네일 이미지가 설정되지 않았습니다")
            
            # 결과 반환
            if check_results:
                return "\n" + "\n".join(check_results)
            else:
                return f"\n[{startup_time_short}] ✅ 모든 설정이 정상적으로 연동되어 있습니다"
                
        except Exception as e:
            return f"\n[{startup_time_short}] ❌ 설정 체크 중 오류 발생: {e}"

    def refresh_all_status(self):
        """F5 새로고침: 모든 설정값을 파일에서 다시 로드하고 UI 갱신"""
        try:
            # 1. 설정 파일 다시 로드
            self.config_manager.reload_config()
            
            # 2. 사이트 목록 다시 로드
            self.load_sites()
            
            # 3. 키워드 파일 다시 스캔
            self.reload_keyword_files()
            
            # 4. 썸네일 파일 다시 스캔  
            self.reload_thumbnail_files()
            
            # 5. UI 상태 업데이트
            self.update_all_ui_status()
            
            # 6. 포스팅 버튼 상태 갱신
            self.update_button_states()
            
            self.update_posting_status("🔄 새로고침 완료 - 모든 설정값이 최신 버전으로 업데이트되었습니다!")
            print("🔄 F5 새로고침 완료 - 전체 설정 다시 로드됨")
            
        except Exception as e:
            self.update_posting_status(f"❌ 새로고침 중 오류: {str(e)}")
            print(f"❌ 새로고침 중 오류: {e}")

    def update_all_ui_status(self):
        """모든 UI 상태 정보 업데이트"""
        try:
            # AI 모델 업데이트 - 더 정확한 표시
            ai_provider = self.config_manager.data["global_settings"].get("default_ai", "gemini")
            ai_model = self.config_manager.data["global_settings"].get("ai_model", "")
            
            if ai_provider == "openai":
                if ai_model:
                    ai_display = ai_model
                else:
                    ai_display = "GPT 4o-mini"
            else:
                if ai_model:
                    ai_display = ai_model
                else:
                    ai_display = "gemini-2.5-flash-lite"
            
            # AI 모델 업데이트는 콤보박스에서 자동 처리됨
            # 포스팅 모드 업데이트도 콤보박스에서 자동 처리됨

            # 총 키워드 개수 업데이트
            total_keywords = 0
            # sites 데이터 직접 접근
            sites_data = self.config_manager.data.get("sites", [])
                
            for site_data in sites_data:
                keyword_file = site_data.get("keyword_file", "")
                if keyword_file:
                    keyword_path = os.path.join(get_base_path(), "keywords", keyword_file)
                    if os.path.exists(keyword_path):
                        try:
                            with open(keyword_path, 'r', encoding='utf-8') as f:
                                lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith('#')]
                                total_keywords += len(lines)
                        except:
                            pass

            self.total_keywords_label.value_button.setText(f"{total_keywords}개")

            # 현재 포스팅 중인 사이트 정보 업데이트는 드롭다운에서 생략
            # (사용자가 직접 선택할 수 있으므로)

        except Exception as e:
            print(f"🔥 상태 새로고침 중 오류: {e}")

    def clean_url_for_display(self, url):
        """URL에서 프로토콜 부분을 제거하여 깔끔하게 표시"""
        if not url:
            return ""
        # https://, http://, www. 제거
        clean_url = url.replace("https://", "").replace("http://", "").replace("www.", "")
        return clean_url

    def goto_settings_ai(self):
        """설정 탭의 AI 모델 설정으로 이동"""
        self.tab_widget.setCurrentIndex(2)  # 설정 탭으로 이동

    def goto_settings_posting_mode(self):
        """설정 탭의 포스팅 모드 설정으로 이동"""
        self.tab_widget.setCurrentIndex(2)  # 설정 탭으로 이동

    def goto_site_management(self):
        """사이트 관리 탭으로 이동"""
        self.tab_widget.setCurrentIndex(1)  # 사이트 관리 탭으로 이동

    def goto_settings_interval(self):
        """설정 탭의 간격 설정으로 이동"""
        self.tab_widget.setCurrentIndex(2)  # 설정 탭으로 이동

    def goto_current_site(self):
        """현재 포스팅 중인 사이트로 이동"""
        self.tab_widget.setCurrentIndex(1)  # 사이트 관리 탭으로 이동
        
        if self.current_posting_site:
            # 현재 포스팅 중인 사이트를 찾아서 해당 위치로 스크롤
            self.scroll_to_site(self.current_posting_site)
    
    def scroll_to_site(self, site_name):
        """특정 사이트 위젯으로 스크롤"""
        try:
            # 사이트 관리 탭의 스크롤 영역 찾기
            sites_tab = self.tab_widget.widget(1)  # 사이트 관리 탭
            if not sites_tab:
                return
                
            # 스크롤 영역과 사이트 컨테이너 찾기
            scroll_area = None
            for child in sites_tab.findChildren(QScrollArea):
                scroll_area = child
                break
                
            if not scroll_area:
                return
                
            # 사이트 위젯들 중에서 현재 포스팅 중인 사이트 찾기
            sites_container = scroll_area.widget()
            if sites_container:
                for widget in sites_container.findChildren(SiteWidget):
                    if hasattr(widget, 'site_data') and widget.site_data:
                        widget_url = widget.site_data.get('url', '')
                        # URL에서 사이트 이름 추출해서 비교
                        if site_name in widget_url or widget_url in site_name:
                            # 해당 위젯의 위치로 스크롤
                            widget_pos = widget.pos()
                            scroll_area.ensureWidgetVisible(widget)
                            break
                            
        except Exception as e:
            print(f"사이트 스크롤 오류: {e}")

    def toggle_add_site_form(self):
        """사이트 추가 폼 토글"""
        if self.add_site_form.isVisible():
            self.add_site_form.hide()
            self.add_site_btn.setText("➕ 새 사이트 추가")
            # 보라색으로 다시 변경
            self.add_site_btn.setObjectName("purpleButton")
            self.add_site_btn.setStyleSheet(f"""
                QPushButton#purpleButton {{
                    background-color: #8B5A9C;
                    color: white;
                    font-weight: bold;
                    padding: 12px 24px;
                    border-radius: 6px;
                    border: none;
                    font-size: 14px;
                }}
                QPushButton#purpleButton:hover {{
                    background-color: #9B6AAC;
                }}
            """)
        else:
            self.add_site_form.show()
            self.add_site_btn.setText("➖ 폼 닫기")
            # 닫기 버튼은 빨간색으로
            self.add_site_btn.setObjectName("closeButton")
            self.add_site_btn.setStyleSheet(f"""
                QPushButton#closeButton {{
                    background-color: #BF616A;
                    color: white;
                    font-weight: bold;
                    padding: 12px 24px;
                    border-radius: 6px;
                    border: none;
                    font-size: 14px;
                }}
                QPushButton#closeButton:hover {{
                    background-color: #CF717A;
                }}
            """)

    def browse_thumbnail_for_site(self):
        """사이트용 썸네일 이미지 선택"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "썸네일 이미지 선택", 
            os.path.join(get_base_path(), "images"),
            "이미지 파일 (*.jpg *.jpeg *.png)"
        )
        if file_path:
            filename = os.path.basename(file_path)
            self.inline_thumbnail_edit.setText(filename)

    def browse_keywords_for_site(self):
        """사이트용 키워드 파일 선택"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "키워드 파일 선택",
            os.path.join(get_base_path(), "keywords"),
            "텍스트 파일 (*.txt)"
        )
        if file_path:
            filename = os.path.basename(file_path)
            self.inline_keywords_edit.setText(filename)

    def test_inline_connection(self):
        """인라인 폼의 연결 테스트 - 다중 인증 방법 지원"""
        url = self.inline_url_edit.text().strip()
        username = self.config_manager.data["global_settings"].get("common_username", "")
        password = self.config_manager.data["global_settings"].get("common_password", "")

        if not all([url, username, password]):
            QMessageBox.warning(self, "경고", "URL과 전역 사용자명/비밀번호가 모두 설정되어야 합니다.")
            return

        # 진행 상황 다이얼로그 생성
        progress_dialog = QProgressDialog("WordPress 연결 테스트 중", "취소", 0, 100, self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.show()

        try:
            import requests
            session = requests.Session()
            
            # 1. 기본 사이트 접근 테스트 (10%)
            progress_dialog.setValue(10)
            progress_dialog.setLabelText("사이트 접근성 확인 중")
            QApplication.processEvents()
            
            try:
                response = session.get(url, timeout=10)
                if response.status_code != 200:
                    progress_dialog.close()
                    QMessageBox.warning(self, "연결 경고", f"사이트 접근 시 HTTP {response.status_code} 응답을 받았습니다.")
                    return
            except Exception as e:
                progress_dialog.close()
                QMessageBox.critical(self, "연결 실패", f"사이트에 접근할 수 없습니다:\n{str(e)}")
                return
            
            # 2. WordPress REST API 확인 (30%)
            progress_dialog.setValue(30)
            progress_dialog.setLabelText("WordPress REST API 확인 중")
            QApplication.processEvents()
            
            api_test_url = f"{url.rstrip('/')}/wp-json/wp/v2/"
            try:
                api_response = session.get(api_test_url, timeout=10)
                if api_response.status_code != 200:
                    progress_dialog.close()
                    QMessageBox.warning(self, "API 오류", f"WordPress REST API에 접근할 수 없습니다.\nHTTP {api_response.status_code}")
                    return
                
                api_info = api_response.json()
                wp_description = api_info.get('description', 'Unknown WordPress site')
            except Exception as e:
                progress_dialog.close()
                QMessageBox.critical(self, "API 오류", f"WordPress REST API 확인 실패:\n{str(e)}")
                return
            
            # 3. 다중 인증 방법 테스트 (50%)
            progress_dialog.setValue(50)
            progress_dialog.setLabelText("인증 방법 테스트 중")
            QApplication.processEvents()
            
            user_url = f"{url.rstrip('/')}/wp-json/wp/v2/users/me"
            auth_success = False
            user_info = None
            successful_method = ""
            
            # 인증 방법들
            auth_methods = [
                ("Application Password (공백 포함)", username, password),
                ("Application Password (공백 제거)", username, password.replace(" ", "")),
                ("Basic Authentication", username, password)
            ]
            
            for i, (method_name, user, pwd) in enumerate(auth_methods):
                progress_dialog.setValue(50 + (i * 15))
                progress_dialog.setLabelText(f"{method_name} 테스트 중")
                QApplication.processEvents()
                
                if progress_dialog.wasCanceled():
                    return
                
                try:
                    import base64
                    credentials = f"{user}:{pwd}"
                    token = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
                    headers = {
                        'Authorization': f'Basic {token}',
                        'User-Agent': 'Auto-WP/1.0'
                    }
                    
                    auth_response = session.get(user_url, headers=headers, timeout=10)
                    
                    if auth_response.status_code == 200:
                        user_info = auth_response.json()
                        auth_success = True
                        successful_method = method_name
                        break
                        
                except Exception:
                    continue
            
            # 4. 결과 표시 (100%)
            progress_dialog.setValue(100)
            progress_dialog.close()
            
            if auth_success and user_info:
                user_name = user_info.get('name', 'Unknown')
                user_roles = user_info.get('roles', [])
                capabilities = user_info.get('capabilities', {})
                
                # 권한 확인
                can_publish = capabilities.get('publish_posts', False)
                can_edit = capabilities.get('edit_posts', False)
                can_upload = capabilities.get('upload_files', False)
                
                message = f"✅ 연결 성공!\n\n"
                message += f"WordPress: {wp_description}\n"
                message += f"인증 방법: {successful_method}\n\n"
                message += f"사용자 정보:\n"
                message += f"  이름: {user_name}\n"
                message += f"  역할: {', '.join(user_roles)}\n\n"
                message += f"권한 확인:\n"
                message += f"  포스트 작성: {'✅' if can_edit else '❌'}\n"
                message += f"  포스트 발행: {'✅' if can_publish else '❌'}\n"
                message += f"  파일 업로드: {'✅' if can_upload else '❌'}"
                
                if not (can_edit and can_publish):
                    message += f"\n\n⚠️ 경고: 포스트 작성/발행 권한이 부족합니다.\n사용자를 '편집자' 이상 권한으로 설정해주세요."
                
                QMessageBox.information(self, "연결 테스트 결과", message)
            else:
                # 인증 실패 시 상세 가이드
                error_msg = "❌ 모든 인증 방법 실패!\n\n"
                error_msg += "해결 방법:\n"
                error_msg += "1. WordPress 관리자 로그인\n"
                error_msg += "2. 사용자 > 프로필 메뉴로 이동\n"
                error_msg += "3. 'Application Passwords' 섹션 찾기\n"
                error_msg += "4. 앱 이름 입력 (예: Auto-WP)\n"
                error_msg += "5. '새 Application Password 추가' 클릭\n"
                error_msg += "6. 생성된 패스워드를 복사하여 설정에 입력\n\n"
                error_msg += "⚠️ 주의: Application Password는 일반 로그인 패스워드와 다릅니다!"
                
                QMessageBox.warning(self, "인증 실패", error_msg)
                
        except Exception as e:
            if 'progress_dialog' in locals():
                progress_dialog.close()
            QMessageBox.critical(self, "오류", f"연결 테스트 중 오류가 발생했습니다:\n{str(e)}")

    def save_inline_site(self):
        """인라인 폼으로 사이트 저장"""
        url = self.inline_url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "경고", "URL을 입력해주세요.")
            return

        # URL에서 사이트 이름 생성
        site_name = url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        
        # 도메인에서 키워드 파일명 생성
        domain_parts = site_name.split('.')
        keyword_prefix = domain_parts[0] if domain_parts else site_name

        site_data = {
            "name": site_name,
            "url": url,
            "username": self.config_manager.data["global_settings"].get("common_username", ""),
            "password": self.config_manager.data["global_settings"].get("common_password", ""),
            "category_id": self.inline_category_edit.value(),
            "ai_provider": self.config_manager.data["global_settings"].get("default_ai", "gemini"),
            "wait_time": self.config_manager.data["global_settings"].get("default_wait_time", "47~50"),
            "thumbnail_image": self.inline_thumbnail_edit.text() or f"{keyword_prefix}.jpg",
            "keyword_file": self.inline_keywords_edit.text() or f"{keyword_prefix}_keywords.txt",
            "keywords": []
        }

        try:
            site_id = self.config_manager.add_site(site_data)
            QMessageBox.information(self, "성공", f"사이트가 추가되었습니다! (ID: {site_id})\n\n전역 설정에서 사용자명/비밀번호가 자동으로 적용되었습니다.")
            self.cancel_inline_site()  # 폼 초기화 및 닫기
            self.load_sites()  # 사이트 목록 새로고침
        except Exception as e:
            QMessageBox.critical(self, "오류", f"사이트 추가 실패: {str(e)}")

    def cancel_inline_site(self):
        """인라인 폼 취소 및 초기화"""
        self.inline_url_edit.clear()
        self.inline_category_edit.setValue(1)
        self.inline_thumbnail_edit.clear()
        self.inline_keywords_edit.clear()
        self.add_site_form.hide()
        self.add_site_btn.setText("➕ 새 사이트 추가")
        # 보라색 스타일로 복원
        self.add_site_btn.setObjectName("purpleButton")
        self.add_site_btn.setStyleSheet(f"""
            QPushButton#purpleButton {{
                background-color: #8B5A9C;
                color: white;
                font-weight: bold;
                padding: 12px 24px;
                border-radius: 6px;
                border: none;
                font-size: 14px;
            }}
            QPushButton#purpleButton:hover {{
                background-color: #9B6AAC;
            }}
        """)

    def refresh_site_list(self):
        """사이트 목록 새로고침"""
        try:
            # 설정 다시 로드
            self.config_manager.load_config()
            # 사이트 목록 다시 로드
            self.load_sites()
            # 썸네일 콤보박스도 새로고침
            if hasattr(self, 'populate_thumbnail_combo'):
                self.populate_thumbnail_combo()
            print("🔄 사이트 목록이 새로고침되었습니다.")
        except Exception as e:
            print(f"새로고침 오류: {e}")

    def load_sites(self):
        """사이트 목록 로드"""
        # 기존 사이트 위젯들 제거
        for i in reversed(range(self.sites_layout.count() - 1)):  # stretch 제외하고 제거
            child = self.sites_layout.itemAt(i)
            if child.widget():
                child.widget().deleteLater()

        # 새 사이트 위젯들 추가
        try:
            # sites 데이터 직접 접근
            sites_data = self.config_manager.data.get("sites", [])
                
            print(f"사이트 데이터 타입: {type(sites_data)}, 개수: {len(sites_data)}")
            
            for site in sites_data:
                # 모든 사이트를 표시 (활성화된 사이트와 비활성화된 사이트 모두)
                site_widget = SiteWidget(site)
                site_widget.edit_requested.connect(self.edit_site)
                site_widget.keywords_requested.connect(self.manage_site_keywords)
                site_widget.thumbnails_requested.connect(self.manage_site_thumbnails)
                site_widget.delete_requested.connect(self.delete_site)
                site_widget.toggle_requested.connect(self.toggle_site_active)
                self.sites_layout.insertWidget(self.sites_layout.count() - 1, site_widget)
            
            # 시작 사이트 드롭다운 업데이트
            self.update_start_site_combo(sites_data)
        except Exception as e:
            print(f"사이트 로드 오류: {e}")

    def update_start_site_combo(self, sites_data):
        """사이트 드롭다운 업데이트"""
        try:
            if hasattr(self, 'current_site_combo'):
                self.current_site_combo.clear()
                self.current_site_combo.addItem("🔄 전체 사이트 순환", "all")
                
                for i, site in enumerate(sites_data):
                    if site.get("active", True):
                        site_name = site.get("name", f"사이트 {i+1}")
                        site_url = site.get("wp_url", "")
                        # URL이 있으면 도메인만 표시, 없으면 사이트명 표시
                        if site_url:
                            import re
                            domain = re.sub(r'https?://', '', site_url).split('/')[0]
                            display_text = f"{domain}"
                        else:
                            display_text = f"{site_name}"
                        self.current_site_combo.addItem(display_text, site.get("id", i))
                
                # 기본 선택을 첫 번째 사이트로 설정 (전체 순환 다음)
                if len(sites_data) > 0:
                    self.current_site_combo.setCurrentIndex(1)  # 첫 번째 사이트 선택
        except Exception as e:
            print(f"드롭다운 업데이트 오류: {e}")

    def edit_site(self, site_id):
        """사이트 편집"""
        site_data = self.config_manager.get_site(site_id)
        if site_data:
            dialog = SiteEditDialog(self, site_data)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                updated_data = dialog.get_site_data()
                if self.config_manager.update_site(site_id, updated_data):
                    QMessageBox.information(self, "성공", "사이트가 업데이트되었습니다!")
                    self.load_sites()
                else:
                    QMessageBox.critical(self, "오류", "사이트 업데이트에 실패했습니다.")

    def manage_site_keywords(self, site_id):
        """사이트 키워드 파일 관리"""
        site_data = self.config_manager.get_site(site_id)
        if site_data:
            file_path, _ = QFileDialog.getOpenFileName(
                self, f"{site_data['name']} 키워드 파일 선택",
                os.path.join(get_base_path(), "keywords"),
                "텍스트 파일 (*.txt)"
            )
            if file_path:
                filename = os.path.basename(file_path)
                site_data["keyword_file"] = filename
                if self.config_manager.update_site(site_id, site_data):
                    QMessageBox.information(self, "성공", f"키워드 파일이 '{filename}'로 변경되었습니다!")
                    self.load_sites()

    def manage_site_thumbnails(self, site_id):
        """사이트 썸네일 이미지 관리"""
        site_data = self.config_manager.get_site(site_id)
        if site_data:
            file_path, _ = QFileDialog.getOpenFileName(
                self, f"{site_data['name']} 썸네일 이미지 선택",
                os.path.join(get_base_path(), "images"),
                "이미지 파일 (*.jpg *.jpeg *.png)"
            )
            if file_path:
                filename = os.path.basename(file_path)
                site_data["thumbnail_image"] = filename
                if self.config_manager.update_site(site_id, site_data):
                    QMessageBox.information(self, "성공", f"썸네일 이미지가 '{filename}'로 변경되었습니다!")
                    self.load_sites()

    def delete_site(self, site_id):
        """사이트 삭제"""
        print(f"🗑️ [GUI DEBUG] delete_site 호출됨 - ID: {site_id}")
        log_to_file(f"GUI delete_site 호출됨 - ID: {site_id}")
        
        site_data = self.config_manager.get_site(site_id)
        if site_data:
            log_to_file(f"사이트 데이터 확인됨: {site_data['name']}")
            
            reply = QMessageBox.question(
                self, "사이트 삭제 확인",
                f"'{site_data['name']}' 사이트를 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            log_to_file(f"사용자 응답: {reply}")
            
            if reply == QMessageBox.StandardButton.Yes:
                log_to_file(f"삭제 확인됨, config_manager.delete_site 호출")
                
                if self.config_manager.delete_site(site_id):
                    log_to_file(f"삭제 성공")
                    QMessageBox.information(self, "완료", "사이트가 삭제되었습니다.")
                    self.load_sites()
                else:
                    log_to_file(f"삭제 실패")
                    QMessageBox.critical(self, "오류", "사이트 삭제에 실패했습니다.")
        else:
            log_to_file(f"사이트 데이터를 찾을 수 없음")

    def toggle_site_active(self, site_id):
        """사이트 활성화/비활성화 토글"""
        site_data = self.config_manager.get_site(site_id)
        if site_data:
            current_status = site_data.get("active", True)
            new_status = not current_status
            status_text = "활성화" if new_status else "비활성화"
            
            reply = QMessageBox.question(
                self, "상태 변경 확인",
                f"'{site_data['name']}' 사이트를 {status_text}하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                if self.config_manager.update_site_active(site_id, new_status):
                    QMessageBox.information(self, "완료", f"사이트가 {status_text}되었습니다.")
                    self.load_sites()
                else:
                    QMessageBox.critical(self, "오류", f"사이트 {status_text}에 실패했습니다.")

    def create_settings_tab(self):
        """설정 탭 생성 - 간소화된 버전"""
        # 스크롤 영역 생성 (간소화)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['surface']};
            }}
        """)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # API 키 설정
        api_group = QGroupBox("🔑 API 키 설정")
        api_layout = QFormLayout()

        # OpenAI API 키
        openai_row = QHBoxLayout()
        self.openai_key_edit = QLineEdit()
        self.openai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        openai_key_value = self.config_manager.data["api_keys"].get("openai", "")
        self.openai_key_edit.setText(openai_key_value)
        openai_row.addWidget(self.openai_key_edit, 1)
        
        # OpenAI 공개/비공개 토글 버튼
        self.openai_toggle_btn = QPushButton("👁️")
        self.openai_toggle_btn.setMaximumWidth(40)
        self.openai_toggle_btn.setToolTip("클릭하여 API 키 표시/숨김")
        try:
            self.openai_toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(self.openai_key_edit, self.openai_toggle_btn))
        except:
            pass  # 메서드가 없으면 무시
        openai_row.addWidget(self.openai_toggle_btn)
        
        # OpenAI 상태 표시 라벨
        self.openai_status_label = QLabel("❌ 미설정")
        self.openai_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
        openai_row.addWidget(self.openai_status_label)
        
        openai_widget = QWidget()
        openai_widget.setLayout(openai_row)
        api_layout.addRow("OpenAI API 키:", openai_widget)

        # Gemini API 키
        gemini_row = QHBoxLayout()
        self.gemini_key_edit = QLineEdit()
        self.gemini_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        gemini_key_value = self.config_manager.data["api_keys"].get("gemini", "")
        print(f"🔧 [LOAD] Gemini 키 로딩: '{gemini_key_value[:10]}'" if gemini_key_value else "🔧 [LOAD] Gemini 키: 빈 값")
        self.gemini_key_edit.setText(gemini_key_value)
        gemini_row.addWidget(self.gemini_key_edit, 1)
        
        # Gemini 공개/비공개 토글 버튼
        self.gemini_toggle_btn = QPushButton("👁️")
        self.gemini_toggle_btn.setMaximumWidth(40)
        self.gemini_toggle_btn.setToolTip("클릭하여 API 키 표시/숨김")
        try:
            self.gemini_toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(self.gemini_key_edit, self.gemini_toggle_btn))
        except:
            pass  # 메서드가 없으면 무시
        gemini_row.addWidget(self.gemini_toggle_btn)
        
        # Gemini 상태 표시 라벨
        self.gemini_status_label = QLabel("❌ 미설정")
        self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
        gemini_row.addWidget(self.gemini_status_label)
        
        gemini_widget = QWidget()
        gemini_widget.setLayout(gemini_row)
        api_layout.addRow("Gemini API 키:", gemini_widget)
        
        # API 테스트 버튼
        test_api_btn = QPushButton("🧪 API 연결 테스트")
        test_api_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #8FBCBB;
                color: white;
                font-weight: bold;
                padding: 12px 20px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: #88C0D0;
            }}
        """)
        try:
            test_api_btn.clicked.connect(self.test_api_connections)
        except:
            pass  # 메서드가 없으면 무시
        api_layout.addRow("", test_api_btn)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # AI 설정
        ai_group = QGroupBox("🤖 AI 설정")
        ai_layout = QFormLayout()

        # AI 제공자 선택
        self.default_ai_combo = QComboBox()
        self.default_ai_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.default_ai_combo.addItems(["gemini", "openai"])
        default_ai_value = self.config_manager.data["global_settings"].get("default_ai", "gemini")
        print(f"🔧 [LOAD] 기본 AI 로딩: '{default_ai_value}'")
        self.default_ai_combo.setCurrentText(default_ai_value)
        try:
            self.default_ai_combo.currentTextChanged.connect(self.update_ai_model_options)
            self.default_ai_combo.currentTextChanged.connect(self.on_setting_changed)
        except:
            pass  # 메서드가 없으면 무시
        ai_layout.addRow("AI 제공자:", self.default_ai_combo)

        # AI 모델 선택
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_layout.addRow("AI 모델:", self.ai_model_combo)

        ai_group.setLayout(ai_layout)
        layout.addWidget(ai_group)

        # 초기 AI 모델 옵션 설정
        try:
            self.update_ai_model_options()
        except:
            pass  # 메서드가 없으면 기본값 설정
            if self.default_ai_combo.currentText() == "gemini":
                self.ai_model_combo.addItems(["gemini-2.5-flash-lite", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"])
            else:
                self.ai_model_combo.addItems(["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"])

        # 전역 설정
        global_group = QGroupBox("🌐 전역 설정")
        global_layout = QFormLayout()

        # 포스팅 모드
        self.posting_mode_combo = QComboBox()
        self.posting_mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.posting_mode_combo.addItems(["승인용", "수익용"])
        posting_mode_value = self.config_manager.data["global_settings"].get("posting_mode", "수익형")
        print(f"🔧 [LOAD] 포스팅 모드 로딩: '{posting_mode_value}'")
        self.posting_mode_combo.setCurrentText(posting_mode_value)
        try:
            self.posting_mode_combo.currentTextChanged.connect(self.on_setting_changed)
        except:
            pass
        global_layout.addRow("포스팅 모드:", self.posting_mode_combo)

        # 포스팅 간격
        self.wait_time_edit = QLineEdit()
        wait_time_value = self.config_manager.data["global_settings"].get("default_wait_time", "47~50")
        print(f"🔧 [LOAD] 대기 시간 로딩: '{wait_time_value}'")
        self.wait_time_edit.setText(wait_time_value)
        try:
            self.wait_time_edit.textChanged.connect(self.on_setting_changed)
        except:
            pass
        global_layout.addRow("포스팅 간격(초):", self.wait_time_edit)
        
        # 사용자명
        self.common_username_edit = QLineEdit()
        loaded_username = self.config_manager.data["global_settings"].get("common_username", "")
        self.common_username_edit.setText(loaded_username)
        global_layout.addRow("사용자명:", self.common_username_edit)

        # 응용프로그램 비밀번호
        password_row = QHBoxLayout()
        self.common_password_edit = QLineEdit()
        self.common_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        loaded_password = self.config_manager.data["global_settings"].get("common_password", "")
        self.common_password_edit.setText(loaded_password)
        password_row.addWidget(self.common_password_edit, 1)
        
        # 응용프로그램 비밀번호 공개/비공개 토글 버튼
        self.password_toggle_btn = QPushButton("👁️")
        self.password_toggle_btn.setMaximumWidth(40)
        self.password_toggle_btn.setToolTip("클릭하여 비밀번호 표시/숨김")
        try:
            self.password_toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(self.common_password_edit, self.password_toggle_btn))
        except:
            pass
        password_row.addWidget(self.password_toggle_btn)
        
        password_widget = QWidget()
        password_widget.setLayout(password_row)
        global_layout.addRow("응용프로그램 비밀번호:", password_widget)

        global_group.setLayout(global_layout)
        layout.addWidget(global_group)

        # 저장 버튼
        save_btn = QPushButton("💾 설정 저장")
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #B48EAD;
                color: white;
                font-weight: bold;
                padding: 15px 25px;
                border-radius: 8px;
                border: none;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background-color: #C4A2B8;
            }}
        """)
        try:
            save_btn.clicked.connect(self.save_settings)
        except:
            pass  # 메서드가 없으면 무시
        layout.addWidget(save_btn)

        layout.addStretch()
        widget.setLayout(layout)
        
        # 스크롤 영역에 위젯 설정
        scroll_area.setWidget(widget)
        
        return scroll_area

        # Gemini API 키
        gemini_row = QHBoxLayout()
        self.gemini_key_edit = QLineEdit()
        self.gemini_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        gemini_key_value = self.config_manager.data["api_keys"].get("gemini", "")
        print(f"🔧 [LOAD] Gemini 키 로딩: '{gemini_key_value[:10]}'" if gemini_key_value else "🔧 [LOAD] Gemini 키: 빈 값")
        self.gemini_key_edit.setText(gemini_key_value)
        gemini_row.addWidget(self.gemini_key_edit, 1)
        
        # Gemini 공개/비공개 토글 버튼
        self.gemini_toggle_btn = QPushButton("👁️")
        self.gemini_toggle_btn.setMaximumWidth(40)
        self.gemini_toggle_btn.setToolTip("클릭하여 API 키 표시/숨김")
        self.gemini_toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(self.gemini_key_edit, self.gemini_toggle_btn))
        gemini_row.addWidget(self.gemini_toggle_btn)
        
        # Gemini 상태 표시 라벨
        self.gemini_status_label = QLabel("❌ 미설정")
        self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
        gemini_row.addWidget(self.gemini_status_label)
        
        gemini_widget = QWidget()
        gemini_widget.setLayout(gemini_row)
        api_layout.addRow("Gemini API 키:", gemini_widget)
        
        # API 테스트 버튼
        test_api_btn = QPushButton("🧪 API 연결 테스트")
        test_api_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_api_btn.clicked.connect(self.test_api_connections)
        api_layout.addRow("", test_api_btn)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # AI 설정
        ai_group = QGroupBox("🤖 AI 설정")
        ai_layout = QFormLayout()

        # AI 제공자 선택
        self.default_ai_combo = QComboBox()
        self.default_ai_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.default_ai_combo.wheelEvent = lambda event: None  # 스크롤 비활성화
        self.default_ai_combo.addItems(["gemini", "openai"])
        default_ai_value = self.config_manager.data["global_settings"].get("default_ai", "gemini")
        print(f"🔧 [LOAD] 기본 AI 로딩: '{default_ai_value}'")
        self.default_ai_combo.setCurrentText(default_ai_value)
        # 설정 변경 시 모니터링 탭 업데이트
        self.default_ai_combo.currentTextChanged.connect(self.update_ai_model_options)
        self.default_ai_combo.currentTextChanged.connect(self.on_setting_changed)
        ai_layout.addRow("AI 제공자:", self.default_ai_combo)

        # AI 모델 선택
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_model_combo.wheelEvent = lambda event: None  # 스크롤 비활성화
        self.ai_model_combo.currentTextChanged.connect(self.on_setting_changed)
        ai_layout.addRow("AI 모델 선택:", self.ai_model_combo)

        # 포스팅 모드
        self.posting_mode_combo = QComboBox()
        self.posting_mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.posting_mode_combo.wheelEvent = lambda event: None  # 스크롤 비활성화
        self.posting_mode_combo.addItems(["수익용", "승인용"])
        posting_mode_value = self.config_manager.data["global_settings"].get("posting_mode", "수익용")
        print(f"🔧 [LOAD] 포스팅 모드 로딩: '{posting_mode_value}'")
        self.posting_mode_combo.setCurrentText(posting_mode_value)
        self.posting_mode_combo.currentTextChanged.connect(self.on_setting_changed)
        ai_layout.addRow("포스팅 모드:", self.posting_mode_combo)

        ai_group.setLayout(ai_layout)
        layout.addWidget(ai_group)

        # WordPress 설정
        global_group = QGroupBox("🌐 WordPress 설정")
        global_layout = QFormLayout()

        # 포스팅 간격
        self.wait_time_edit = QLineEdit()
        wait_time_value = self.config_manager.data["global_settings"].get("default_wait_time", "47~50")
        print(f"🔧 [LOAD] 대기 시간 로딩: '{wait_time_value}'")
        self.wait_time_edit.setText(wait_time_value)
        self.wait_time_edit.textChanged.connect(self.on_setting_changed)
        global_layout.addRow("포스팅 간격(초):", self.wait_time_edit)
        
        # 사용자명
        self.common_username_edit = QLineEdit()
        loaded_username = self.config_manager.data["global_settings"].get("common_username", "")
        # 사용자명 로딩 완료
        self.common_username_edit.setText(loaded_username)
        global_layout.addRow("사용자명:", self.common_username_edit)

        # 응용프로그램 비밀번호
        password_row = QHBoxLayout()
        self.common_password_edit = QLineEdit()
        self.common_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        loaded_password = self.config_manager.data["global_settings"].get("common_password", "")
        self.common_password_edit.setText(loaded_password)
        password_row.addWidget(self.common_password_edit, 1)
        
        # 응용프로그램 비밀번호 공개/비공개 토글 버튼
        self.password_toggle_btn = QPushButton("👁️")
        self.password_toggle_btn.setMaximumWidth(40)
        self.password_toggle_btn.setToolTip("클릭하여 비밀번호 표시/숨김")
        self.password_toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(self.common_password_edit, self.password_toggle_btn))
        password_row.addWidget(self.password_toggle_btn)
        
        password_widget = QWidget()
        password_widget.setLayout(password_row)
        global_layout.addRow("응용프로그램 비밀번호:", password_widget)

        global_group.setLayout(global_layout)
        layout.addWidget(global_group)

        # 초기 AI 모델 옵션 설정
        self.update_ai_model_options()

        # 저장 버튼
        save_btn = QPushButton("💾 설정 저장")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

        layout.addStretch()
        widget.setLayout(layout)
        
        # 스크롤 영역에 위젯 설정
        scroll_area.setWidget(widget)
        
        # 초기 API 상태 설정
        QTimer.singleShot(100, self.update_api_status_labels)
        
        return scroll_area

    def test_api_connections(self):
        """API 연결 테스트"""
        self.update_posting_status("🧪 API 연결 테스트 시작")
        
        # OpenAI 테스트
        openai_key = self.openai_key_edit.text().strip()
        if openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": "안녕"}],
                    max_tokens=10,
                    timeout=10
                )
                self.openai_status_label.setText("✅ 연결됨")
                self.openai_status_label.setStyleSheet("color: #A3BE8C; font-weight: bold;")
                self.update_posting_status("✅ OpenAI API 연결 성공!")
            except Exception as e:
                self.openai_status_label.setText("❌ 실패")
                self.openai_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
                self.update_posting_status(f"❌ OpenAI API 연결 실패: {str(e)}")
        else:
            self.openai_status_label.setText("❌ 미설정")
            self.openai_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
            
        # Gemini 테스트
        gemini_key = self.gemini_key_edit.text().strip()
        if gemini_key:
            try:
                if GEMINI_AVAILABLE:
                    import google.generativeai as genai
                    genai.configure(api_key=gemini_key)
                    # 최신 모델들 순서대로 시도
                    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
                    
                    for model_name in models_to_try:
                        try:
                            model = genai.GenerativeModel(model_name)
                            response = model.generate_content(
                                "테스트", 
                                generation_config=genai.types.GenerationConfig(max_output_tokens=10)
                            )
                            if hasattr(response, 'text') and response.text:
                                self.gemini_status_label.setText("✅ 연결됨")
                                self.gemini_status_label.setStyleSheet("color: #A3BE8C; font-weight: bold;")
                                self.update_posting_status(f"✅ Gemini API 연결 성공! (모델: {model_name})")
                                break
                        except Exception as model_error:
                            continue
                    else:
                        # 모든 모델 실패
                        raise Exception("사용 가능한 Gemini 모델이 없습니다")
                else:
                    self.gemini_status_label.setText("❌ 라이브러리 없음")
                    self.gemini_status_label.setStyleSheet("color: #EBCB8B; font-weight: bold;")
                    self.update_posting_status("❌ google-generativeai 라이브러리가 설치되지 않음")
            except Exception as e:
                self.gemini_status_label.setText("❌ 실패")
                self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
                self.update_posting_status(f"❌ Gemini API 연결 실패: {str(e)}")
        else:
            self.gemini_status_label.setText("❌ 미설정")
            self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
            
        self.update_posting_status("🧪 API 연결 테스트 완료!")

    def save_settings(self):
        """설정 저장"""
        try:
            
            # GUI 위젯 존재 여부 확인
            
            if not hasattr(self, 'openai_key_edit'):
                print("❌ [ERROR] openai_key_edit 위젯이 존재하지 않습니다!")
                return
            
            # API 키 저장 - data 직접 수정
            openai_key = self.openai_key_edit.text()
            gemini_key = self.gemini_key_edit.text()
            
            self.config_manager.data["api_keys"]["openai"] = openai_key
            self.config_manager.data["api_keys"]["gemini"] = gemini_key

            # AI 설정 저장 - data 직접 수정
            default_ai = self.default_ai_combo.currentText()
            ai_model = self.ai_model_combo.currentText()
            posting_mode = self.posting_mode_combo.currentText()
            
            self.config_manager.data["global_settings"]["default_ai"] = default_ai
            self.config_manager.data["global_settings"]["ai_model"] = ai_model
            self.config_manager.data["global_settings"]["posting_mode"] = posting_mode
            
            # WordPress 설정 저장 - data 직접 수정
            wait_time = self.wait_time_edit.text()
            username = self.common_username_edit.text()
            password = self.common_password_edit.text()
            
            self.config_manager.data["global_settings"]["default_wait_time"] = wait_time
            self.config_manager.data["global_settings"]["common_username"] = username
            self.config_manager.data["global_settings"]["common_password"] = password

            # 🔥 중요: 기존 사이트들의 사용자명/비밀번호를 새로운 공통 설정으로 업데이트
            self.update_all_sites_credentials(username, password)
            
            # 파일 저장 - save_setting 직접 호출
            result = self.config_manager.save_setting()
            
            # 저장 후 JSON 파일 재로딩해서 검증
            if result:
                self.verify_saved_settings()
                
                # API 상태 업데이트
                self.update_api_status_labels()
                
                self.update_posting_status("✅ 설정이 저장되었습니다!")
                print("✅ 설정이 저장되었습니다!")
                
                # 상태 새로고침
                self.refresh_all_status()
                
                # 모니터링 탭으로 자동 이동하여 변경사항 확인
                self.tab_widget.setCurrentIndex(0)  # 모니터링 탭으로 이동
                
                # 추가 확인 메시지
                self.update_posting_status("📊 모니터링 탭으로 이동했습니다. 변경된 설정을 확인!")
            else:
                print("❌ 파일 저장에 실패했습니다!")
                self.update_posting_status("❌ 설정 저장에 실패했습니다!")
            
            
        except Exception as e:
            self.update_posting_status(f"❌ 설정 저장 실패: {str(e)}")
            print(f"❌ 설정 저장 실패: {str(e)}")
            import traceback
            traceback.print_exc()

    def verify_saved_settings(self):
        """저장된 설정이 JSON 파일에 올바르게 반영되었는지 검증"""
        try:
            print(f"🔍 [VERIFY] JSON 파일에서 설정 재검증 중")
            
            # JSON 파일 다시 읽기
            import json
            with open(self.config_manager.setting_file, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            # GUI에서 현재 입력된 값들
            gui_values = {
                'openai_key': self.openai_key_edit.text().strip(),
                'gemini_key': self.gemini_key_edit.text().strip(),
                'default_ai': self.default_ai_combo.currentText(),
                'ai_model': self.ai_model_combo.currentText(),
                'posting_mode': self.posting_mode_combo.currentText(),
                'wait_time': self.wait_time_edit.text().strip(),
                'username': self.common_username_edit.text().strip(),
                'password': self.common_password_edit.text().strip()
            }
            
            # JSON에서 저장된 값들
            json_values = {
                'openai_key': saved_data.get('api_keys', {}).get('openai', ''),
                'gemini_key': saved_data.get('api_keys', {}).get('gemini', ''),
                'default_ai': saved_data.get('global_settings', {}).get('default_ai', ''),
                'ai_model': saved_data.get('global_settings', {}).get('ai_model', ''),
                'posting_mode': saved_data.get('global_settings', {}).get('posting_mode', ''),
                'wait_time': saved_data.get('global_settings', {}).get('default_wait_time', ''),
                'username': saved_data.get('global_settings', {}).get('common_username', ''),
                'password': saved_data.get('global_settings', {}).get('common_password', '')
            }
            
            # 검증 결과
            verification_passed = True
            print(f"🔍 [VERIFY] ===== 설정 검증 결과 =====")
            
            for key in gui_values:
                gui_val = gui_values[key]
                json_val = json_values[key]
                
                if gui_val == json_val:
                    if key in ['openai_key', 'gemini_key', 'password']:
                        print(f"✅ [VERIFY] {key}: GUI와 JSON 일치 (길이: {len(gui_val)})")
                    else:
                        print(f"✅ [VERIFY] {key}: '{gui_val}' == '{json_val}'")
                else:
                    verification_passed = False
                    if key in ['openai_key', 'gemini_key', 'password']:
                        print(f"❌ [VERIFY] {key}: GUI(길이:{len(gui_val)}) != JSON(길이:{len(json_val)})")
                    else:
                        print(f"❌ [VERIFY] {key}: GUI='{gui_val}' != JSON='{json_val}'")
            
            if verification_passed:
                print(f"🎉 [VERIFY] 모든 설정이 올바르게 저장되었습니다!")
                self.update_posting_status("🎉 모든 설정이 JSON에 올바르게 저장되었습니다!")
            else:
                print(f"⚠️ [VERIFY] 일부 설정이 올바르게 저장되지 않았습니다!")
                self.update_posting_status("⚠️ 일부 설정이 올바르게 저장되지 않았습니다!")
            
            print(f"🔍 [VERIFY] ===== 검증 완료 =====")
            
        except Exception as e:
            print(f"❌ [VERIFY] 설정 검증 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

    def update_all_sites_credentials(self, new_username, new_password):
        """모든 사이트의 사용자명과 비밀번호를 새로운 공통 설정으로 업데이트"""
        try:
            if not new_username or not new_password:
                return
                
            sites = self.config_manager.data.get("sites", [])
            updated_count = 0
            
            for i, site in enumerate(sites):
                old_username = site.get('username', '')
                old_password = site.get('password', '')
                site_name = site.get('name', f'Site-{i+1}')
                
                # 사용자명과 비밀번호 업데이트
                site['username'] = new_username
                site['password'] = new_password
                
                updated_count += 1
            
            # 사이트 관리 탭의 UI도 새로고침 (존재하는 경우)
            if hasattr(self, 'refresh_sites_list'):
                self.refresh_sites_list()
                print(f"🔄 [DEBUG] 사이트 관리 탭 UI 새로고침 완료")
                
        except Exception as e:
            print(f"❌ [ERROR] 사이트 인증 정보 업데이트 실패: {e}")
            import traceback
            traceback.print_exc()

    def update_api_status_labels(self):
        """API 상태 라벨 업데이트"""
        # OpenAI 상태 확인
        openai_key = self.openai_key_edit.text().strip()
        if openai_key and len(openai_key) > 10:
            self.openai_status_label.setText("🔑 설정됨")
            self.openai_status_label.setStyleSheet("color: #88C0D0; font-weight: bold;")
        else:
            self.openai_status_label.setText("❌ 미설정")
            self.openai_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
            
        # Gemini 상태 확인
        gemini_key = self.gemini_key_edit.text().strip()
        if gemini_key and len(gemini_key) > 10:
            self.gemini_status_label.setText("🔑 설정됨")
            self.gemini_status_label.setStyleSheet("color: #88C0D0; font-weight: bold;")
        else:
            self.gemini_status_label.setText("❌ 미설정")
            self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")

    def update_ai_model_options(self):
        """AI 제공자에 따라 모델 옵션 업데이트"""
        self.ai_model_combo.clear()
        ai_provider = self.default_ai_combo.currentText()
        
        if ai_provider == "openai":
            models = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
            default_model = "gpt-4o-mini"  # OpenAI 기본 모델
        else:  # gemini
            models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
            default_model = "gemini-2.5-flash-lite"  # Gemini 기본 모델
        
        self.ai_model_combo.addItems(models)
        
        # 저장된 모델이 있으면 선택, 없으면 기본 모델 선택
        saved_model = self.config_manager.data["global_settings"].get("ai_model", "")
        if saved_model in models:
            self.ai_model_combo.setCurrentText(saved_model)
        else:
            # 저장된 모델이 없거나 유효하지 않으면 기본 모델 선택
            self.ai_model_combo.setCurrentText(default_model)
            print(f"🔧 [AI MODEL] {ai_provider} 기본 모델 설정: {default_model}")

    def on_setting_changed(self):
        """설정 변경 시 호출되는 함수 - 모니터링 탭 실시간 업데이트"""
        try:
            # 잠깐 후에 모니터링 탭 업데이트 (UI가 완전히 업데이트된 후)
            QTimer.singleShot(100, self.refresh_all_status)
        except Exception as e:
            print(f"설정 변경 시 업데이트 오류: {e}")

    def toggle_password_visibility(self, line_edit, toggle_button):
        """비밀번호 필드의 표시/숨김 상태를 토글하는 함수"""
        try:
            if line_edit.echoMode() == QLineEdit.EchoMode.Password:
                # 비밀번호 모드에서 일반 텍스트 모드로 변경
                line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
                toggle_button.setText("🙈")  # 숨김 아이콘
                toggle_button.setToolTip("클릭하여 숨김")
            else:
                # 일반 텍스트 모드에서 비밀번호 모드로 변경
                line_edit.setEchoMode(QLineEdit.EchoMode.Password)
                toggle_button.setText("👁️")  # 보기 아이콘
                toggle_button.setToolTip("클릭하여 표시")
        except Exception as e:
            print(f"토글 기능 오류: {e}")

    def start_posting(self):
        """포스팅 시작 - 마지막 포스팅 상태 기반으로 시작 사이트 결정"""
        try:
            # EXE 환경에서도 콘솔 출력 강제
            import sys
            import traceback
            
            debug_msg = "🚀 [DEBUG] start_posting 함수가 호출되었습니다."
            print("=" * 80, flush=True)
            print(debug_msg, flush=True)
            print(f"🚀 [DEBUG] self.is_posting = {self.is_posting}", flush=True)
            print("=" * 80, flush=True)
            
            # EXE 실행 시 로그 파일에도 기록
            log_to_file(debug_msg)
            log_to_file(f"start_posting 호출됨 - is_posting: {self.is_posting}")
            
            if self.is_posting:
                msg = "⚠️ 이미 포스팅이 진행 중입니다."
                print(msg)
                log_to_file(msg)
                self.update_posting_status(msg)
                return

            # 활성 사이트 확인
            # sites 데이터 직접 접근
            sites_data = self.config_manager.data.get("sites", [])
                
            active_sites = [site for site in sites_data if site.get("active", True)]
            
            if not active_sites:
                self.update_posting_status("⚠️ 활성화된 사이트가 없습니다.")
                return

            # API 키 확인 (시작 메시지에서 이미 표시됨)
            openai_key = self.config_manager.data["api_keys"].get("openai", "")
            gemini_key = self.config_manager.data["api_keys"].get("gemini", "")
            
            if not openai_key and not gemini_key:
                print("⚠️ OpenAI 또는 Gemini API 키가 설정되지 않았습니다.")
                self.update_posting_status("⚠️ API 키가 설정되지 않았습니다.")
                return

            # 🔒 마지막 포스팅 상태에 따라 시작 사이트 결정
            start_site_id = self.config_manager.get_start_site_id()
            if start_site_id:
                start_site = next((site for site in active_sites if site.get("id") == start_site_id), None)
                if start_site:
                    site_name = start_site.get("name", "Unknown")
                    site_url = start_site.get("url", "")
                    posting_state = self.config_manager.get_posting_state()
                    
                    if posting_state.get("posting_in_progress", False):
                        self.update_posting_status(f"� 포스팅 재시작: {site_name}에서 계속")
                    elif posting_state.get("next_site_id") == start_site_id:
                        self.update_posting_status(f"🔄 다음 사이트에서 시작: {site_name}")
                    else:
                        self.update_posting_status(f"🔗 {site_name}에서 포스팅 시작")
                    
                    # 현재 사이트 콤보박스 업데이트
                    if hasattr(self, 'current_site_combo'):
                        for i in range(self.current_site_combo.count()):
                            if self.current_site_combo.itemData(i) == start_site_id:
                                self.current_site_combo.setCurrentIndex(i)
                                break
                else:
                    print(f"⚠️ 저장된 시작 사이트 ID({start_site_id})를 활성 사이트에서 찾을 수 없음, 첫 번째 사이트로 시작")
                    start_site_id = active_sites[0].get("id", "all")
            else:
                print("📍 저장된 상태가 없어 첫 번째 사이트부터 시작")
                start_site_id = active_sites[0].get("id", "all")

            self.is_posting = True
            self.is_paused = False
            
            # 기존 워커가 있다면 정리
            if hasattr(self, 'posting_worker') and self.posting_worker:
                print("🔄 기존 포스팅 워커를 정리합니다")
                try:
                    self.posting_worker.stop()
                    self.posting_worker.wait(1000)  # 1초 대기
                    self.posting_worker.deleteLater()
                except:
                    pass
                self.posting_worker = None
            
            self._safe_update_button_states()
            
            # 포스팅 스레드 시작
            self.posting_worker = PostingWorker(self.config_manager, active_sites, start_site_id)
            
            # 신호 연결
            self.posting_worker.status_update.connect(self.update_posting_status)
            self.posting_worker.posting_complete.connect(self.on_posting_complete)
            self.posting_worker.single_posting_complete.connect(self.on_single_posting_complete)
            self.posting_worker.error_occurred.connect(self.on_posting_error)
            
            self.posting_worker.start()
            
            print("🚀 포스팅이 시작되었습니다!")
                
        except Exception as e:
            print(f"❌ [ERROR] start_posting 에러: {e}")
            print(f"❌ [ERROR] 상세 오류: {traceback.format_exc()}")
            sys.stdout.flush()
            self.update_posting_status(f"❌ 시작 오류: {e}")
            self.is_posting = False
            self._safe_update_button_states()

    def update_posting_status(self, message):
        """포스팅 상태 업데이트"""
        try:
            # 현재 포스팅 중인 사이트 정보 파싱 및 업데이트
            self.parse_and_update_current_site(message)
            
            # "포스트 업로드 성공" 메시지 감지 시 카운트다운 시작
            if "포스트 업로드 성공" in message:
                self.set_next_posting_time()
            
            
            # GUI 업데이트는 항상 메인 스레드에서 실행
            if hasattr(self, 'progress_text') and self.progress_text is not None:
                from datetime import datetime
                timestamp = datetime.now().strftime("%H:%M:%S")
                simple_message = f"[{timestamp}] {message}"
                
                try:
                    current_text = self.progress_text.toPlainText()
                    
                    # 새 메시지 추가
                    if current_text.strip():
                        new_text = current_text + "\n" + simple_message
                    else:
                        new_text = simple_message
                    
                    # 텍스트 업데이트
                    self.progress_text.setPlainText(new_text)
                    
                    # 스크롤을 맨 아래로
                    scrollbar = self.progress_text.verticalScrollBar()
                    if scrollbar:
                        scrollbar.setValue(scrollbar.maximum())
                    
                    # GUI 갱신
                    self.progress_text.update()
                    self.progress_text.repaint()
                    QApplication.processEvents()
                    
                    # GUI 업데이트 로그 제거 (너무 많아서 번잡함)
                    
                except Exception as gui_error:
                    print(f"[GUI ERROR] {gui_error}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"progress_text 없음 또는 None")
                    
        except Exception as e:
            print(f"❌ update_posting_status 전체 오류: {e}")
            import traceback
            traceback.print_exc()

    def parse_and_update_current_site(self, message):
        """메시지에서 현재 포스팅 중인 사이트 정보를 파싱하고 업데이트"""
        try:
            # "📝 사이트명 포스팅 중" 패턴 매칭
            if "📝" in message and "포스팅 중" in message:
                # 사이트명 추출
                site_name = message.replace("📝", "").replace("포스팅 중", "").strip()
                if site_name:
                    self.current_posting_site = site_name
                    # 드롭다운에서는 별도 업데이트 불필요 (사용자가 선택한 상태 유지)
            
            # 포스팅 완료나 오류가 발생해도 사이트 정보는 계속 표시
            # 실제 포스팅 중지(stop_posting) 시에만 "대기중"으로 변경
            elif "포스팅 중지" in message or "🛑" in message:
                self.current_posting_site = None
                # 드롭다운은 사용자 선택 상태 유지
                    
        except Exception as e:
            print(f"현재 사이트 파싱 오류: {e}")
    
    def find_site_url_by_name(self, site_name):
        """사이트명으로 URL 찾기"""
        try:
            sites_data = self.config_manager.data.get("sites", [])
            for site in sites_data:
                site_url = site.get('url', '')
                # URL에서 도메인 부분만 추출해서 비교
                if site_name in site_url or site_url in site_name:
                    return site_url
            return None
        except Exception as e:
            print(f"URL 찾기 오류: {e}")
            return None
        
    def on_posting_complete(self):
        """포스팅 완료"""
        self.is_posting = False
        self.is_paused = False
        self.stop_next_posting_timer()
        
        # 워커 정리
        if hasattr(self, 'posting_worker') and self.posting_worker:
            try:
                self.posting_worker.deleteLater()
            except:
                pass
            self.posting_worker = None
        
        # 다음 포스팅까지 대기 시간 계산 및 카운트다운 시작
        self.start_next_posting_countdown()
        
        self._safe_update_button_states()
        print("🎉 모든 포스팅이 완료되었습니다!")
        
    def on_single_posting_complete(self):
        """개별 포스팅 완료 후 카운트다운 시작"""
        # 아직 포스팅이 진행 중이라면 (다른 사이트들이 남아있음) 카운트다운 시작
        if self.is_posting:
            self.start_next_posting_countdown()
        
    def on_posting_error(self, error_message):
        """포스팅 오류 처리"""
        print(f"❌ 포스팅 중 오류 발생: {error_message}")
        
        # 워커 정리
        if hasattr(self, 'posting_worker') and self.posting_worker:
            try:
                self.posting_worker.deleteLater()
            except:
                pass
            self.posting_worker = None
            
        self.stop_posting()

    def pause_posting(self):
        """포스팅 일시정지/재개"""
        try:
            # EXE 환경 디버깅
            print("⏸️ [DEBUG] pause_posting 함수 호출됨", flush=True)
            print(f"⏸️ [DEBUG] is_posting={self.is_posting}, is_paused={self.is_paused}", flush=True)
            
            if not self.is_posting:
                print("⚠️ 포스팅이 진행 중이 아닙니다.")
                return

            if hasattr(self, 'posting_worker') and self.posting_worker:
                if not self.is_paused:
                    # 일시정지 실행
                    self.is_paused = True
                    self.posting_worker.pause()
                    self.pause_btn.setText("▶️ 재개")
                    
                    # 일시정지 시 현재 포스팅 중이던 사이트를 콤보박스에서 선택
                    if hasattr(self, 'current_posting_site') and hasattr(self, 'current_site_combo') and self.current_posting_site:
                        index = self.current_site_combo.findText(self.current_posting_site)
                        if index >= 0:
                            self.current_site_combo.setCurrentIndex(index)
                    
                    print("⏸️ 포스팅이 일시정지되었습니다.")
                    self.update_posting_status("⏸️ 포스팅이 일시정지되었습니다.")
                else:
                    # 재개 실행
                    self.is_paused = False
                    self.posting_worker.resume()
                    self.pause_btn.setText("⏸️ 일시정지")
                    print("▶️ 포스팅이 재개되었습니다.")
                    self.update_posting_status("▶️ 포스팅이 재개되었습니다.")
            
            # 버튼 상태 업데이트
            self._safe_update_button_states()
            
        except Exception as e:
            print(f"❌ [ERROR] pause_posting 에러: {e}", flush=True)
            import traceback
            print(f"❌ [ERROR] 상세 오류: {traceback.format_exc()}", flush=True)
            self.update_posting_status(f"❌ 일시정지/재개 오류: {e}")

    def resume_posting(self):
        """포스팅 재개"""
        try:
            # EXE 환경 디버깅
            print("▶️ [DEBUG] resume_posting 함수 호출됨", flush=True)
            
            if not self.is_posting:
                print("⚠️ 포스팅이 시작되지 않았습니다. 먼저 시작 버튼을 누르세요.")
                return
                
            if not self.is_paused:
                print("⚠️ 포스팅이 일시정지 상태가 아닙니다.")
                return

            self.is_paused = False
            if hasattr(self, 'posting_worker') and self.posting_worker:
                self.posting_worker.resume()
            self.pause_btn.setText("⏸️ 일시정지")
            print("▶️ 포스팅이 재개되었습니다!")
            self.update_posting_status("▶️ 포스팅이 재개되었습니다!")
            
            # 버튼 상태 업데이트
            self._safe_update_button_states()
            
        except Exception as e:
            print(f"❌ [ERROR] resume_posting 에러: {e}", flush=True)
            import traceback
            print(f"❌ [ERROR] 상세 오류: {traceback.format_exc()}", flush=True)
            self.update_posting_status(f"❌ 재개 오류: {e}")

    def stop_posting(self):
        """포스팅 중지"""
        try:
            # EXE 환경 디버깅
            print("🛑 [DEBUG] stop_posting 함수 호출됨", flush=True)
            
            if not self.is_posting:
                print("⚠️ 포스팅이 진행 중이 아닙니다.")
                return

            if hasattr(self, 'posting_worker') and self.posting_worker:
                print("🛑 포스팅 워커를 중지합니다")
                self.posting_worker.stop()
                # wait 호출하지 않고 바로 삭제 - 프로그램 종료 방지
                try:
                    if self.posting_worker.isRunning():
                        self.posting_worker.terminate()  # 강제 종료
                    self.posting_worker.deleteLater()
                except:
                    pass
                self.posting_worker = None

            self.is_posting = False
            self.is_paused = False
            self.stop_next_posting_timer()
            self.pause_btn.setText("⏸️ 일시정지")
            
            # 포스팅 중지 시 현재 포스팅 중이던 사이트를 콤보박스에서 선택
            if hasattr(self, 'current_posting_site') and hasattr(self, 'current_site_combo') and self.current_posting_site:
                index = self.current_site_combo.findText(self.current_posting_site)
                if index >= 0:
                    self.current_site_combo.setCurrentIndex(index)
            
            print("🛑 포스팅이 중지되었습니다.")
            self.update_posting_status("🛑 포스팅이 중지되었습니다.")
            
            # 버튼 상태 업데이트
            self._safe_update_button_states()
            
            # 현재 포스팅 사이트 초기화는 하지 않음 (URL 표시 유지용)
            
        except Exception as e:
            print(f"❌ [ERROR] stop_posting 에러: {e}", flush=True)
            import traceback
            print(f"❌ [ERROR] 상세 오류: {traceback.format_exc()}", flush=True)
            self.update_posting_status(f"❌ 중지 오류: {e}")

    def _safe_update_button_states(self):
        """안전한 버튼 상태 업데이트"""
        try:
            if hasattr(self, 'start_btn'):
                self.start_btn.setEnabled(not self.is_posting)
            if hasattr(self, 'pause_btn'):
                self.pause_btn.setEnabled(self.is_posting)
                # 일시정지 버튼의 텍스트 업데이트
                if self.is_posting:
                    if self.is_paused:
                        self.pause_btn.setText("▶️ 재개")
                    else:
                        self.pause_btn.setText("⏸️ 일시정지")
            if hasattr(self, 'resume_btn'):
                self.resume_btn.setEnabled(self.is_posting and self.is_paused)
            if hasattr(self, 'stop_btn'):
                self.stop_btn.setEnabled(self.is_posting)
                
        except Exception as e:
            print(f"❌ 버튼 상태 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()

    def progress_wheel_event(self, event):
        """프로그레스 텍스트 휠 이벤트 - 스마트 스크롤"""
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QWheelEvent
            
            # 현재 스크롤 위치 정보 가져오기
            scrollbar = self.progress_text.verticalScrollBar()
            current_value = scrollbar.value()
            min_value = scrollbar.minimum()
            max_value = scrollbar.maximum()
            
            # 휠 방향 및 강도 확인
            wheel_delta = event.angleDelta().y()
            
            # 스크롤할 내용이 없는 경우 (텍스트가 짧은 경우)
            if max_value <= min_value:
                # 바로 상위 위젯으로 이벤트 전파
                event.ignore()
                return
            
            # 스크롤 단위 계산 (휠 움직임에 비례)
            scroll_step = abs(wheel_delta) // 40  # 더 부드러운 스크롤
            if scroll_step < 1:
                scroll_step = 1
            scroll_amount = scroll_step * 20
            
            # 스크롤 방향에 따른 처리
            if wheel_delta > 0:  # 위로 스크롤
                if current_value > min_value:
                    # progress_text에 위로 스크롤할 내용이 있음
                    new_value = max(min_value, current_value - scroll_amount)
                    scrollbar.setValue(new_value)
                    event.accept()  # 이벤트 처리 완료
                    return
                else:
                    # progress_text가 맨 위에 도달 - 상위로 전파
                    event.ignore()
                    return
                    
            elif wheel_delta < 0:  # 아래로 스크롤
                if current_value < max_value:
                    # progress_text에 아래로 스크롤할 내용이 있음
                    new_value = min(max_value, current_value + scroll_amount)
                    scrollbar.setValue(new_value)
                    event.accept()  # 이벤트 처리 완료
                    return
                else:
                    # progress_text가 맨 아래에 도달 - 상위로 전파
                    event.ignore()
                    return
            
            # 기본적으로 상위로 전파
            event.ignore()
            
        except Exception as e:
            print(f"휠 이벤트 처리 오류: {e}")
            # 오류 발생 시 상위로 전파
            event.ignore()

    def initialize_posting_buttons(self):
        """포스팅 제어 버튼 초기 상태 설정"""
        try:
            self.is_posting = False
            self.is_paused = False
            self._safe_update_button_states()
            print("🔧 포스팅 제어 버튼이 초기화되었습니다.")
            
        except Exception as e:
            print(f"버튼 초기화 오류: {e}")

    def set_next_posting_time(self):
        """다음 포스팅 시간 설정 및 카운트다운 시작"""
        try:
            # 포스팅 간격 가져오기 (올바른 키 사용)
            posting_interval = self.config_manager.data.get("global_settings", {}).get("default_wait_time", "47~50")
            
            if "~" in posting_interval or "-" in posting_interval:
                # ~ 또는 - 구분자 처리
                separator = "~" if "~" in posting_interval else "-"
                min_val, max_val = map(int, posting_interval.split(separator))
                self.posting_interval_seconds = random.randint(min_val, max_val)
            else:
                self.posting_interval_seconds = int(posting_interval)
                
            # 다음 포스팅 시간 계산
            from datetime import datetime, timedelta
            self.next_posting_time = datetime.now() + timedelta(seconds=self.posting_interval_seconds)
            
            # 초기 카운트다운 표시
            if hasattr(self, 'next_posting_label') and hasattr(self.next_posting_label, 'value_button'):
                # 시간, 분, 초로 나누어 표시
                hours = self.posting_interval_seconds // 3600
                minutes = (self.posting_interval_seconds % 3600) // 60
                seconds = self.posting_interval_seconds % 60
                
                if hours > 0:
                    time_str = f"{hours}시간 {minutes}분 {seconds}초"
                elif minutes > 0:
                    time_str = f"{minutes}분 {seconds}초"
                else:
                    time_str = f"{seconds}초"
                
                # 다음 포스팅 예정 사이트 정보 추가
                next_site = ""
                if hasattr(self, 'current_posting_site') and self.current_posting_site:
                    next_site = f"\n다음: {self.current_posting_site}"
                
                display_text = f"{time_str}{next_site}"
                self.next_posting_label.value_button.setText(display_text)
            
            # 카운트다운 타이머 시작 (1초마다 업데이트)
            self.countdown_timer.start(1000)
            
        except Exception as e:
            print(f"다음 포스팅 시간 설정 오류: {e}")
            import traceback
            traceback.print_exc()

    def update_next_posting_countdown(self):
        """다음 포스팅까지 남은 시간 실시간 업데이트"""
        try:
            # next_posting_time이나 next_posting_label이 없으면 리턴
            if not self.next_posting_time or not hasattr(self, 'next_posting_label'):
                return
                
            from datetime import datetime
            now = datetime.now()
            
            if now >= self.next_posting_time:
                # 카운트다운 완료 - 다음 포스팅 시작
                if hasattr(self.next_posting_label, 'value_button'):
                    self.next_posting_label.value_button.setText("포스팅 시작!")
                
                self.countdown_timer.stop()
                self.next_posting_time = None
                
                # 다음 포스팅 시작 메시지 출력
                if hasattr(self, 'is_posting') and self.is_posting:
                    print("⏰ 카운트다운 완료! 다음 사이트 포스팅을 시작합니다.")
                    self.update_posting_status("⏰ 카운트다운 완료! 다음 사이트 포스팅을 시작합니다.")
                    
                    # 잠시 후 다시 "대기중"으로 변경
                    QTimer.singleShot(2000, lambda: (
                        self.next_posting_label.value_button.setText("대기중") 
                        if hasattr(self, 'next_posting_label') and hasattr(self.next_posting_label, 'value_button') 
                        else None
                    ))
                else:
                    # 포스팅이 중지된 상태라면 "대기중"으로 표시
                    if hasattr(self.next_posting_label, 'value_button'):
                        self.next_posting_label.value_button.setText("대기중")
                return
                
            # 남은 시간 계산
            remaining = self.next_posting_time - now
            total_seconds = int(remaining.total_seconds())
            
            # 시간, 분, 초로 나누어 표시
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            # 시간 형식 구성
            if hours > 0:
                time_str = f"{hours}시간 {minutes}분 {seconds}초"
            elif minutes > 0:
                time_str = f"{minutes}분 {seconds}초"
            else:
                time_str = f"{seconds}초"
            
            # 다음 포스팅 예정 사이트 정보 추가
            next_site = ""
            if hasattr(self, 'current_posting_site') and self.current_posting_site:
                next_site = f"\n다음: {self.current_posting_site}"
            
            display_text = f"{time_str}{next_site}"
                
            if hasattr(self.next_posting_label, 'value_button'):
                self.next_posting_label.value_button.setText(display_text)
            
        except Exception as e:
            print(f"카운트다운 업데이트 오류: {e}")

    def open_keywords_folder(self):
        """keywords 폴더 열기"""
        try:
            import subprocess
            import os
            keywords_path = os.path.join(get_base_path(), "keywords")
            
            # 폴더가 없으면 생성
            if not os.path.exists(keywords_path):
                os.makedirs(keywords_path, exist_ok=True)
            
            # Windows에서 폴더 열기
            subprocess.run(['explorer', keywords_path], check=True)
            
        except Exception as e:
            QMessageBox.warning(self, "오류", f"keywords 폴더를 열 수 없습니다:\n{e}")

    def open_images_folder(self):
        """images 폴더 열기"""
        try:
            import subprocess
            import os
            images_path = os.path.join(get_base_path(), "images")
            
            # 폴더가 없으면 생성
            if not os.path.exists(images_path):
                os.makedirs(images_path, exist_ok=True)
            
            # Windows에서 폴더 열기
            subprocess.run(['explorer', images_path], check=True)
            
        except Exception as e:
            QMessageBox.warning(self, "오류", f"images 폴더를 열 수 없습니다:\n{e}")

    def start_next_posting_countdown(self):
        """다음 포스팅까지 카운트다운 시작"""
        try:
            # 대기 시간 설정 가져오기 (초 단위)
            wait_time_setting = self.config_manager.data.get("global_settings", {}).get("default_wait_time", "47~50")
            
            # 대기 시간 파싱 (초 단위)
            if "~" in wait_time_setting:
                min_wait, max_wait = map(int, wait_time_setting.split("~"))
                import random
                wait_seconds = random.randint(min_wait, max_wait)
            else:
                wait_seconds = int(wait_time_setting)
            
            # 다음 포스팅 시간 계산
            from datetime import datetime, timedelta
            self.next_posting_time = datetime.now() + timedelta(seconds=wait_seconds)
            self.posting_interval_seconds = wait_seconds
            
            # 초기 카운트다운 표시
            if hasattr(self, 'next_posting_label') and hasattr(self.next_posting_label, 'value_button'):
                # 시간, 분, 초로 나누어 표시
                hours = wait_seconds // 3600
                minutes = (wait_seconds % 3600) // 60
                seconds = wait_seconds % 60
                
                if hours > 0:
                    time_str = f"{hours}시간 {minutes}분 {seconds}초"
                elif minutes > 0:
                    time_str = f"{minutes}분 {seconds}초"
                else:
                    time_str = f"{seconds}초"
                
                # 다음 포스팅 예정 사이트 정보 추가
                next_site = ""
                if hasattr(self, 'current_posting_site') and self.current_posting_site:
                    next_site = f"\n다음: {self.current_posting_site}"
                
                display_text = f"{time_str}{next_site}"
                self.next_posting_label.value_button.setText(display_text)
            
            # 카운트다운 시작 (1초마다 업데이트)
            self.countdown_timer.start(1000)
            
            # 분과 초로 표시 (로그용)
            wait_minutes = wait_seconds // 60
            wait_secs = wait_seconds % 60
            if wait_minutes > 0:
                print(f"⏰ 다음 포스팅까지 {wait_minutes}분 {wait_secs}초 대기 중")
                self.update_posting_status(f"⏰ 다음 포스팅까지 {wait_minutes}분 {wait_secs}초 대기 중")
            else:
                print(f"⏰ 다음 포스팅까지 {wait_secs}초 대기 중")
                self.update_posting_status(f"⏰ 다음 포스팅까지 {wait_secs}초 대기 중")
            
        except Exception as e:
            print(f"카운트다운 시작 오류: {e}")

    def stop_next_posting_timer(self):
        """다음 포스팅 타이머 중지"""
        if hasattr(self, 'countdown_timer'):
            self.countdown_timer.stop()
            
        # 다음 포스팅 카드를 "대기중"으로 리셋
        if hasattr(self, 'next_posting_label') and hasattr(self.next_posting_label, 'value_button'):
            self.next_posting_label.value_button.setText("대기중")
            
        # 다음 포스팅 시간 초기화
        self.next_posting_time = None

    def check_and_update_api_status(self):
        """API 키 상태를 확인하고 UI 업데이트"""
        try:
            # OpenAI API 키 확인
            openai_key = self.config_manager.data.get("api_keys", {}).get("openai", "")
            if hasattr(self, 'openai_status_label'):
                if openai_key and len(openai_key.strip()) > 10:
                    self.openai_status_label.setText("✅ 설정됨")
                    self.openai_status_label.setStyleSheet("color: #A3BE8C; font-weight: bold;")
                else:
                    self.openai_status_label.setText("❌ 미설정")
                    self.openai_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
            
            # Gemini API 키 확인
            gemini_key = self.config_manager.data.get("api_keys", {}).get("gemini", "")
            if hasattr(self, 'gemini_status_label'):
                if gemini_key and len(gemini_key.strip()) > 10:
                    self.gemini_status_label.setText("✅ 설정됨")
                    self.gemini_status_label.setStyleSheet("color: #A3BE8C; font-weight: bold;")
                else:
                    self.gemini_status_label.setText("❌ 미설정")
                    self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
            
            print("🔍 API 키 상태 확인 완료")
            
        except Exception as e:
            print(f"API 키 상태 확인 오류: {e}")

    def create_simple_monitoring_tab(self):
        """간단한 모니터링 탭 생성"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("📊 모니터링")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        info_text = QTextEdit()
        info_text.setPlainText("모니터링 정보가 여기에 표시됩니다.\n프로그램이 정상적으로 실행되었습니다!")
        layout.addWidget(info_text)
        
        widget.setLayout(layout)
        return widget

    def create_simple_sites_tab(self):
        """간단한 사이트 관리 탭 생성"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("🌍 사이트 관리")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        add_btn = QPushButton("새 사이트 추가")
        layout.addWidget(add_btn)
        
        sites_text = QTextEdit()
        sites_text.setPlainText("사이트 목록이 여기에 표시됩니다.")
        layout.addWidget(sites_text)
        
        widget.setLayout(layout)
        return widget

    def create_simple_settings_tab(self):
        """간단한 설정 탭 생성"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("⚙️ 설정")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        settings_text = QTextEdit()
        settings_text.setPlainText("설정 옵션들이 여기에 표시됩니다.\n- API 키 설정\n- 포스팅 간격 설정\n- 기타 옵션들")
        layout.addWidget(settings_text)
        
        widget.setLayout(layout)
        return widget

    def update_button_states(self):
        """버튼 상태 업데이트 (간단 버전)"""
        try:
            # 포스팅 관련 버튼 상태를 업데이트하는 간단한 구현
            pass
        except Exception as e:
            print(f"버튼 상태 업데이트 오류: {e}")

def main():
    """메인 함수"""
    # EXE 환경 디버깅 - 프로그램 시작 확인
    print("="*60, flush=True)
    # 프로그램 시작
    print("="*60, flush=True)
    
    import sys
    import io
    
    # EXE 실행 시 stdout 리다이렉트 설정 (--windowed 옵션 대응)
    if getattr(sys, 'frozen', False):  # PyInstaller로 빌드된 EXE인 경우
        try:
            # stdout과 stderr를 로그 파일로 리다이렉트
            log_file_path = os.path.join(get_base_path(), "app.log")
            log_file = open(log_file_path, "w", encoding="utf-8")
            sys.stdout = log_file
            sys.stderr = log_file
        except Exception as e:
            pass  # 리다이렉트 실패 시 무시
    
    # sys, io 모듈 import
    
    # UTF-8 인코딩 강제 설정 (이모지 지원을 위해)
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        else:
            # Python 3.6 이하 호환성
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        # 인코딩 설정 실패 시 무시하고 계속 진행
        pass
    
    try:
        # QApplication 생성
        app = QApplication(sys.argv)
        # QApplication 생성 완료
        
        app.setStyle('Fusion')
        # 스타일 설정
        
        # 폰트 설정
        font = QFont("맑은 고딕", 9)
        app.setFont(font)

        # 아이콘 설정 (있는 경우)
        icon_path = os.path.join(get_base_path(), "daivd153.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

        # 예외 처리 핸들러 추가 (UTF-8 안전)
        def handle_exception(exc_type, exc_value, exc_traceback):
            try:
                print(f"예상치 못한 오류 발생: {exc_type.__name__}: {exc_value}")
            except UnicodeEncodeError:
                print("예상치 못한 오류 발생 (인코딩 문제)")
            import traceback
            traceback.print_exception(exc_type, exc_value, exc_traceback)

        sys.excepthook = handle_exception

        # MainWindow 생성
        window = MainWindow()
        # MainWindow 생성 완료
        
        window.show()
        window.raise_()  # 창을 앞으로 가져오기
        window.activateWindow()  # 창을 활성화
        # MainWindow 표시
        
        try:
            print("Auto WP multi-site 프로그램 시작")
            # 프로그램 실행
        except UnicodeEncodeError:
            print("Auto WP multi-site program started")
            # 프로그램 실행
            
        sys.exit(app.exec())

    except Exception as e:
        try:
            print(f"프로그램 시작 중 오류: {e}")
        except UnicodeEncodeError:
            print("Error starting program")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

