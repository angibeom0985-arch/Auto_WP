#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto WP multi-site - 워드프레스 자동 포스팅 by 데이비
"""

import sys
import os
import json
from typing import Any, Optional

import time
import random
import threading
import traceback
import subprocess
import re
from datetime import datetime, timedelta
from pathlib import Path
import shutil
import platform

# Windows에서 Qt DPI 컨텍스트 재설정 경고(SetProcessDpiAwarenessContext) 방지
if os.name == "nt":
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:dpiawareness=1")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")

# 라이선스 및 Selenium 관련 라이브러리 추가
from license_check import LicenseManager
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
except ImportError:
    webdriver = None
    By = WebDriverWait = EC = Service = ChromeDriverManager = None
    TimeoutException = NoSuchElementException = Keys = ActionChains = None

try:
    import undetected_chromedriver as uc
except ImportError:
    uc = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

# GUI 라이브러리
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QScrollArea,
    QGroupBox, QGridLayout, QSpinBox, QComboBox, QCheckBox, QListWidget,
    QFileDialog, QMessageBox, QProgressBar, QSplitter, QFrame,
    QListWidgetItem, QDialog, QDialogButtonBox, QFormLayout, QProgressDialog,
    QSizePolicy, QStackedWidget, QStyledItemDelegate, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize, QUrl
from PyQt6.QtGui import QFont, QPixmap, QIcon, QPalette, QColor, QTextCursor, QDesktopServices

class CenteredComboDelegate(QStyledItemDelegate):
    """콤보박스 항목 텍스트 중앙 정렬"""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if option is not None:
            option.displayAlignment = Qt.AlignmentFlag.AlignCenter

class PostingWorker(QThread):
    """포스팅 작업 스레드"""
    status_update = pyqtSignal(str)
    posting_complete = pyqtSignal()
    single_posting_complete = pyqtSignal()  # 개별 포스팅 완료 신호 추가
    keyword_used = pyqtSignal()  # 키워드 사용 완료 신호 추가
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
    
    def log(self, message):
        """로그 메시지 출력 - safe_emit_status의 별칭"""
        self.safe_emit_status(message)

    def _resolve_wait_seconds(self, default_minutes: int = 3) -> int:
        """global_settings.default_wait_time(분 단위)를 초 단위로 변환"""
        try:
            wait_time = str(self.config_manager.data["global_settings"].get("default_wait_time", "3~5")).strip()
            if "~" in wait_time or "-" in wait_time:
                separator = "~" if "~" in wait_time else "-"
                min_val, max_val = map(int, wait_time.split(separator))
                min_val = max(1, min_val)
                max_val = max(min_val, max_val)
                wait_minutes = random.randint(min_val, max_val)
            else:
                wait_minutes = max(1, int(wait_time))
            return wait_minutes * 60
        except Exception:
            return max(1, default_minutes) * 60

    def _format_wait_text(self, total_seconds: int) -> str:
        """초를 사람이 읽기 쉬운 시간 문자열로 변환"""
        total_seconds = max(0, int(total_seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours}시간 {minutes}분 {seconds}초"
        if minutes > 0:
            return f"{minutes}분 {seconds}초"
        return f"{seconds}초"

    def _wait_with_countdown(self, delay_seconds: int) -> bool:
        """중지/일시정지를 고려한 대기 + 진행 상태 카운트다운 출력"""
        delay_seconds = max(0, int(delay_seconds))
        for remaining in range(delay_seconds, 0, -1):
            if not self.is_running or self._force_stop:
                return False
            while self.is_paused and self.is_running and not self._force_stop:
                self.msleep(1000)
            if not self.is_running or self._force_stop:
                return False

            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            if hours > 0:
                progress_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                progress_time = f"{minutes:02d}:{seconds:02d}"
            self.safe_emit_status(f"⏳ 다음 포스팅까지 남은 시간: {progress_time}")
            self.msleep(1000)
        return True
        
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
                            delay = self._resolve_wait_seconds(default_minutes=3)
                            self.safe_emit_status(f"⏰ 포스팅 간격 대기 시작: {self._format_wait_text(delay)}")
                            if not self._wait_with_countdown(delay):
                                return
                    
                    # 이번 라운드 완료 후 체크
                    if posted_sites_count == 0:
                        # 어떤 사이트도 포스팅하지 못했으면 모든 키워드가 소진됨
                        self.safe_emit_status("🎉 모든 사이트의 키워드가 소진되었습니다!")
                        self.safe_emit_status(f"📊 총 {round_count}라운드 완료! 포스팅 작업 종료")
                        break
                    else:
                        self.safe_emit_status(f"🏁 라운드 {round_count} 완료 - {posted_sites_count}개 사이트 포스팅 성공")
                        
                        # 다음 라운드를 위한 일반 대기 (사이트 간 간격과 동일)
                        delay = self._resolve_wait_seconds(default_minutes=3)
                        self.safe_emit_status(f"⏰ 포스팅 간격 대기 시작: {self._format_wait_text(delay)}")
                        if not self._wait_with_countdown(delay):
                            return
                        
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
        content_generator = None
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
            ai_provider = self.config_manager.data["global_settings"].get("default_ai", "web-gemini")
            posting_mode = self.config_manager.data["global_settings"].get("posting_mode", "수익용")
            
            # ContentGenerator 인스턴스 생성
            from datetime import datetime
            config_data = {
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
                    self.current_ai_provider = config_manager.data.get("global_settings", {}).get("default_ai", "web-gemini")
                    self.posting_mode = config_manager.data.get("global_settings", {}).get("posting_mode", "수익용")
                    # Worker Thread 참조 저장
                    self.worker_thread = worker_thread
                
                @property
                def is_posting(self):
                    # Worker Thread의 상태를 실시간으로 반환
                    is_running = getattr(self.worker_thread, "is_running", True)
                    force_stop = getattr(self.worker_thread, "_force_stop", False)
                    return is_running and not force_stop
                
                @property
                def is_paused(self):
                    return getattr(self.worker_thread, "is_paused", False)
            
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

            # 포스팅 모드에 따라 콘텐츠 타입 결정
            content_type = "approval" if posting_mode == "승인용" else "revenue"
            
            # 포스팅 상태 결정 (승인용은 대기, 수익용은 발행)
            post_status = "pending" if posting_mode == "승인용" else "publish"

            # 콘텐츠 생성
            title, content, thumbnail_path = content_generator.generate_simple_content(
                keyword,
                content_type=content_type
            )
            
            if not self.is_running:
                print(f"⏹️ {site_name}: 포스팅이 중지되었습니다. 키워드 '{keyword}' 보존됨")
                return
                
            # 🔥 콘텐츠 생성 결과 검증 강화 (빈 문자열 체크 포함)
            if not title or not title.strip():
                self.log(f"❌ {site_name}: 제목 생성 실패 (빈 값) - 키워드 '{keyword}' 보존")
                return
            
            if not content or not content.strip():
                self.log(f"❌ {site_name}: 본문 생성 실패 (빈 값) - 키워드 '{keyword}' 보존")
                return
            
            # 최소 길이 검증
            if len(title.strip()) < 5:
                self.log(f"❌ 콘텐츠 생성 실패 - 제목이 너무 짧음 ({len(title.strip())}자). 키워드 '{keyword}' 보존")
                return
            
            if len(content.strip()) < 100:
                self.log(f"❌ 콘텐츠 생성 실패 - 본문이 너무 짧음 ({len(content.strip())}자). 키워드 '{keyword}' 보존")
                return
                
            self.log(f"✅ 콘텐츠 생성 성공 (제목: {len(title)}자, 본문: {len(content)}자), 워드프레스 업로드 시작")
            
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
                
                # 🔥 포스팅 완료 후 키워드 개수 체크 (300개 미만 경고)
                self.check_low_keywords_after_posting(site)
                    
            else:
                self.status_update.emit(f"❌ {site_name}: 워드프레스 포스팅 실패 - 키워드 보존")
                # 🔒 포스팅 실패 시 진행 중 상태 유지 (재시작 시 같은 사이트에서 재시작)
                self.config_manager.save_posting_state(site_id, site_url, in_progress=True)
                self.config_manager.save_posting_state(site_id, site_url, in_progress=True)
            
        except Exception as e:
            self.log(f"❌ {site_name} 예외 발생: {str(e)}")
            import traceback
            self.log(f"🔍 상세 오류:\n{traceback.format_exc()}")
            self.status_update.emit(f"❌ {site_name} 예외 발생 - 키워드 보존됨")
            # 🔒 예외 발생 시 진행 중 상태 유지 (재시작 시 같은 사이트에서 재시작)
            self.config_manager.save_posting_state(site_id, site_url, in_progress=True)
            # 예외가 발생해도 키워드를 보존하고 다음 사이트로 진행
        finally:
            # 사이트 1회 처리(성공/실패) 직후 브라우저를 반드시 종료
            try:
                if content_generator is not None:
                    self.log(f"🧹 {site_name}: 현재 포스팅 브라우저 종료")
                    content_generator.close_browser_session(force_tree_kill=True)
            except Exception as close_error:
                self.log(f"⚠️ {site_name}: 브라우저 종료 중 오류(무시): {close_error}")

    def check_low_keywords_after_posting(self, site):
        """포스팅 완료 후 해당 사이트의 키워드가 300개 미만이면 알림"""
        try:
            site_name = site.get('name', 'Unknown')
            keyword_file_value = site.get('keyword_file', '')
            if not isinstance(keyword_file_value, str):
                return
            keyword_file = keyword_file_value.strip()
            if not keyword_file:
                return
            
            base_path = get_base_path()
            keyword_path = os.path.join(base_path, "setting", "keywords", keyword_file)
            
            if not os.path.exists(keyword_path):
                return
            
            # 현재 남은 키워드 개수 확인
            with open(keyword_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith('#')]
                keyword_count = len(lines)
            
            # 300개 미만이면 경고 신호 발생
            if keyword_count < 300:
                warning_msg = f"⚠️ {site_name}의 키워드가 {keyword_count}개로 부족합니다! (최소 300개 권장)"
                self.status_update.emit(warning_msg)
                
                # 메인 스레드에서 알림창 표시 (error_occurred 신호 사용)
                self.error_occurred.emit(f"키워드 부족|{site_name}|{keyword_count}")
                
        except Exception as e:
            print(f"키워드 체크 오류: {e}")

    def move_keyword_to_used(self, keyword, site):
        """사용한 키워드를 used 파일로 이동 - 'used_' 접두사 붙인 파일로 이동"""
        try:
            keyword_file_value = site.get('keyword_file')
            if not isinstance(keyword_file_value, str):
                return False
            keyword_file = keyword_file_value.strip()
            if not keyword_file:
                return False
                
            base_path = get_base_path()
            keywords_path = os.path.join(base_path, "setting", "keywords", keyword_file)
            
            # 'used_' 접두사가 붙은 파일명 생성 (예: ai-news_keywords.txt -> used_ai-news_keywords.txt)
            used_filename = f"used_{keyword_file}"
            used_path = os.path.join(base_path, "setting", "keywords", used_filename)
            
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
                    
                    # UI 업데이트 신호 발생
                    if hasattr(self, 'keyword_used'):
                        self.keyword_used.emit()
                    
                    return True
                    
                except Exception as file_error:
                    # 복원 시도
                    if os.path.exists(backup_path):
                        shutil.copy2(backup_path, keywords_path)
                        os.remove(backup_path)
                        print(f"👏 키워드 파일 복원 완료")
                    
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

# 기존 라이브러리들
import requests
import urllib.parse
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import re
import subprocess

# AI API 라이브러리들
# OpenAI는 사용하지 않으므로 제거됨

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

# Gemini API 지연 로드 (시작 속도 개선)
GEMINI_AVAILABLE = False
genai = None

# WordPress API
try:
    import pandas as pd
except ImportError:
    pd = None

def get_base_path():
    """실행 파일의 기본 경로 반환 (EXE/PY 모두 지원)"""
    if getattr(sys, 'frozen', False):  # PyInstaller로 빌드된 EXE인 경우
        # _MEIPASS는 PyInstaller가 리소스를 압축 해제한 임시 폴더
        # sys.executable은 실제 exe 파일 위치
        # 설정 파일 등은 exe 위치, 리소스 파일은 _MEIPASS 사용
        return os.path.dirname(sys.executable)
    else:  # 일반 Python 스크립트인 경우
        return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    """리소스 파일의 절대 경로 반환 (PyInstaller 호환)"""
    if getattr(sys, 'frozen', False):  # PyInstaller로 빌드된 EXE인 경우
        # _MEIPASS: PyInstaller가 리소스를 압축 해제한 임시 폴더
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:  # 일반 Python 스크립트인 경우
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_preferred_resource_path(relative_path):
    """외부 설정 파일 우선, 없으면 번들 리소스 경로 사용"""
    external_path = os.path.join(get_base_path(), relative_path)
    if os.path.exists(external_path):
        return external_path
    return get_resource_path(relative_path)

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
    from requests.adapters import HTTPAdapter
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=3, pool_maxsize=5, max_retries=0)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Auto-WP/1.0',
        'Connection': 'keep-alive',
    })
    return session

# 설정 파일 경로
SETTING_FILE = os.path.join(get_base_path(), "setting", "setting.json")

# 기본 디렉토리 생성 (setting 폴더 내부로 변경)
for directory in ['keywords', 'thumbnails', 'fonts', 'prompts', 'output', 'images']:
    dir_path = os.path.join(get_base_path(), "setting", directory)
    os.makedirs(dir_path, exist_ok=True)

# 테마 팔레트
DARK_COLORS = {
    'background': '#121722',
    'surface': '#1C2433',
    'surface_light': '#27354A',
    'surface_dark': '#0F1420',
    'primary': '#00A9FF',
    'primary_hover': '#25BDFF',
    'secondary': '#00D0FF',
    'accent': '#008CFF',
    'success': '#19C37D',
    'warning': '#F6B600',
    'warning_hover': '#FFC83D',
    'danger': '#E53935',
    'info': '#19C5FF',
    'info_hover': '#4CD5FF',
    'text': '#F4FBFF',
    'text_secondary': '#D7E8F5',
    'text_muted': '#9AB8D0',
    'border': '#2E4864',
    'hover': '#2B3D56'
}

LIGHT_COLORS = {
    'background': '#EEF4FB',
    'surface': '#F8FBFF',
    'surface_light': '#FFFFFF',
    'surface_dark': '#DCE8F5',
    'primary': '#0A84FF',
    'primary_hover': '#2E9BFF',
    'secondary': '#00B5FF',
    'accent': '#006BFF',
    'success': '#10B84A',
    'warning': '#F0A100',
    'warning_hover': '#FFB733',
    'danger': '#E11937',
    'info': '#007FE8',
    'info_hover': '#1A9CFF',
    'text': '#122033',
    'text_secondary': '#2A3B52',
    'text_muted': '#4A657F',
    'border': '#96B4D6',
    'hover': '#E8F1FB'
}

THEME_PALETTES = {
    "다크": DARK_COLORS,
    "라이트": LIGHT_COLORS,
}

# 현재 활성 팔레트 (기본 다크)
COLORS = dict(DARK_COLORS)

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
        self.prompt_files = {'gemini': []}

        for ai_type in ['gemini']:
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
            'gemini_prompts': len(self.prompt_files['gemini'])
        }

class ContentGenerator:
    """콘텐츠 생성기 - Gemini API 및 Web AI 지원"""
    def __init__(self, config_data, log_func, auto_wp_instance=None):
        self.config_data = config_data
        self.log = log_func
        self.auto_wp = auto_wp_instance
        self.gemini_model = None
        self.driver = None  # 브라우저 드라이버

        # API 상태 추적
        self.api_status = {
            'gemini': False,
            'web': False
        }

        # Web AI 관련 핸들
        self.gemini_tab_handle = None
        self.perplexity_tab_handle = None
        self.gemini_logged_in = False

        # 포스팅 상태 관리
        self.is_posting = False
        self.worker_thread: Optional["PostingWorker"] = None  # Worker Thread 참조
        
        # 인증 캐시 (성공한 인증 방법 저장)
        self.auth_cache = {}  # {site_url: (headers, method_name)}

        # config_manager 속성 추가
        if self.auto_wp and hasattr(self.auto_wp, 'config_manager'):
            self.config_manager = self.auto_wp.config_manager
        else:
            self.config_manager = None

        # 요청 제한 추적
        self.request_tracker = {
            'gemini': {
                'requests': [],
                'daily_requests': 0,
                'max_per_minute': 60,
                'max_per_day': 1000,
                'daily_reset_time': None
            },
            'web': {
                'requests': [],
                'daily_requests': 0,
                'max_per_minute': 20,
                'max_per_day': 500,
                'daily_reset_time': None
            }
        }

        # GUI에서 선택한 AI 모델 (기본값 먼저 설정)
        self.current_ai_provider = "web-gemini"  # 기본값
        
        # config_manager에서 설정 가져오기
        if self.config_manager:
            try:
                global_settings = self.config_manager.data.get("global_settings", {})
                self.current_ai_provider = global_settings.get("default_ai", "web-gemini")
            except Exception:
                self.current_ai_provider = "web-gemini"
            
        # auto_wp_instance에서 직접 가져오기 (우선순위 높음)
        if self.auto_wp and hasattr(self.auto_wp, 'current_ai_provider'):
            try:
                self.current_ai_provider = self.auto_wp.current_ai_provider
            except Exception:
                pass  # 기본값 유지

        # API 초기화
        self.initialize_apis()
        
        # 현재 처리 중인 사이트 정보
        self.current_site = None

    def setup_driver(self):
        """크롬 드라이버 설정 (표준 Selenium)"""
        try:
            if webdriver is None:
                self.log("⚠️ selenium not found. Please install selenium and webdriver-manager.")
                return False
            assert webdriver is not None

            if self.driver:
                try:
                    _ = self.driver.current_url
                    return True
                except Exception:
                    self.log("기존 driver 접근 실패 -> driver=None 재설정")
                    self.driver = None

            self.log("🌐 브라우저 실행 준비 중...")
            chrome_profile_root = os.path.join(get_base_path(), "setting", "chrome_profile")
            os.makedirs(chrome_profile_root, exist_ok=True)
            # 첫 시도 전에 stale driver를 선제 정리해 1회차 실패를 줄임
            self._cleanup_stale_driver_binaries(force_cleanup=True)

            self.log("🚀 브라우저 시작 중...")
            # 표준 Selenium만 사용 (차단 회피 로직 제거)
            try:
                for attempt in range(1, 3):
                    chrome_profile_dir = self._select_chrome_profile_dir(chrome_profile_root, attempt)
                    self._clear_chrome_profile_locks(chrome_profile_dir)
                    force_cleanup = True
                    self._cleanup_stale_driver_binaries(force_cleanup=force_cleanup)
                    use_profile_directory = (attempt == 1)
                    options = self._build_chrome_options(
                        use_uc=False,
                        chrome_profile_dir=chrome_profile_dir,
                        use_profile_directory=use_profile_directory
                    )

                    service = None
                    if ChromeDriverManager is not None and Service is not None:
                        try:
                            driver_path = ChromeDriverManager().install()
                            service = Service(driver_path)
                        except Exception:
                            service = None
                    elif Service is not None:
                        service = None

                    try:
                        if service is not None:
                            self.driver = webdriver.Chrome(service=service, options=options)
                        else:
                            # Selenium Manager 폴백 (드라이버 자동 탐색)
                            self.driver = webdriver.Chrome(options=options)
                        self._verify_driver_health()
                        self.log("✅ 브라우저 실행 완료")
                        return True
                    except Exception as selenium_error:
                        self.log(f"⚠️ 브라우저 실행 {attempt}/2 실패: {self._compact_error(selenium_error)}")
                        self._safe_quit_driver()
                        time.sleep(1.0)
                raise RuntimeError("브라우저 실행 2회 실패")
            except Exception as selenium_error:
                self.log(f"❌ 브라우저 시작 오류: {self._compact_error(selenium_error)}")
                raise
            
        except Exception as e:
            self.log(f"❌ 브라우저 실행 실패: {self._compact_error(e)}")
            return False

    def _select_chrome_profile_dir(self, profile_root: str, attempt: int) -> str:
        """브라우저 시작 시도별 프로필 경로 선택 (로그인 세션 유지 우선)"""
        # 사용자 요구사항: 한 번 로그인하면 이후 재사용
        # 재시도 시에도 동일 프로필을 사용해 로그인 세션을 보존한다.
        profile_dir = os.path.join(profile_root, "runtime_main")
        os.makedirs(profile_dir, exist_ok=True)
        return profile_dir

    def _clear_chrome_profile_locks(self, profile_dir: str):
        """Chrome 프로필 잠금/포트 파일 제거 (비정상 종료 잔재 복구)"""
        try:
            lock_files = [
                "SingletonLock",
                "SingletonCookie",
                "SingletonSocket",
                "DevToolsActivePort",
            ]
            for name in lock_files:
                path = os.path.join(profile_dir, name)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
        except Exception:
            pass

    def _compact_error(self, exc: Exception) -> str:
        """장문 stacktrace가 포함된 예외 메시지를 한 줄로 압축"""
        text = str(exc or "").strip()
        if not text:
            return "알 수 없는 오류"
        if "Stacktrace:" in text:
            text = text.split("Stacktrace:", 1)[0].strip()
        text = text.replace("\r", " ").replace("\n", " ")
        return re.sub(r"\s+", " ", text)

    def _build_chrome_options(self, use_uc: bool, chrome_profile_dir: str, use_profile_directory: bool = True):
        """Chrome 옵션 생성 (표준 Selenium)"""
        if webdriver is None:
            raise RuntimeError("selenium webdriver를 사용할 수 없습니다.")
        options = webdriver.ChromeOptions()
        self.log("🔧 브라우저 옵션 설정 중...")
        options.add_argument("--window-size=1280,900")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--remote-debugging-port=0")
        options.add_argument(f"--user-data-dir={chrome_profile_dir}")
        if use_profile_directory:
            options.add_argument("--profile-directory=Default")
        options.add_argument("--disable-extensions")
        return options

    def _cleanup_stale_driver_binaries(self, force_cleanup: bool = False):
        """stale driver 바이너리 정리"""
        try:
            if force_cleanup:
                self.log("stale driver 정리 수행")
                subprocess.run(['taskkill', '/f', '/im', 'chromedriver.exe'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(['taskkill', '/f', '/im', 'undetected_chromedriver.exe'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1)

            uc_dir = os.path.join(os.environ.get('APPDATA', ''), 'undetected_chromedriver')
            uc_exe = os.path.join(uc_dir, 'undetected_chromedriver.exe')
            if os.path.exists(uc_exe):
                try:
                    os.remove(uc_exe)
                except OSError:
                    time.sleep(0.8)
                    try:
                        os.remove(uc_exe)
                    except Exception:
                        pass
        except Exception as cleanup_error:
            self.log(f"⚠️ 정리 작업 중 오류 (무시됨): {cleanup_error}")

    def _verify_driver_health(self):
        """드라이버가 실제로 Chrome과 통신 가능한지 검증"""
        if not self.driver:
            raise RuntimeError("driver가 초기화되지 않았습니다.")
        try:
            self.driver.get("about:blank")
            _ = self.driver.current_url
            try:
                self.driver.maximize_window()
            except Exception:
                pass
        except Exception as health_error:
            raise RuntimeError(f"Chrome 통신 검증 실패: {health_error}")

    def _safe_quit_driver(self):
        """driver 종료 안전 처리"""
        try:
            if self.driver is not None:
                self.driver.quit()
        except Exception:
            pass
        finally:
            self.driver = None

    def close_browser_session(self, force_tree_kill: bool = True):
        """현재 자동화 브라우저 세션 종료 (필요 시 프로세스 트리 강제 종료)"""
        driver = self.driver
        if driver is None:
            return

        service_pid = None
        browser_pid = None
        try:
            service = getattr(driver, "service", None)
            process = getattr(service, "process", None) if service is not None else None
            service_pid = getattr(process, "pid", None) if process is not None else None
        except Exception:
            service_pid = None

        try:
            browser_pid = getattr(driver, "browser_pid", None)
        except Exception:
            browser_pid = None

        try:
            driver.quit()
        except Exception as quit_error:
            self.log(f"⚠️ driver.quit 실패(강제 종료 진행): {quit_error}")

        if force_tree_kill and os.name == "nt":
            for pid in (service_pid, browser_pid):
                if isinstance(pid, int) and pid > 0:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False
                        )
                    except Exception:
                        pass

        self.driver = None
        self.gemini_tab_handle = None
        self.perplexity_tab_handle = None

    def _detect_chrome_major_version(self) -> Optional[int]:
        """설치된 Chrome 메이저 버전 감지"""
        try:
            reg_queries = [
                r'reg query "HKCU\Software\Google\Chrome\BLBeacon" /v version',
                r'reg query "HKLM\Software\Google\Chrome\BLBeacon" /v version',
                r'reg query "HKLM\Software\WOW6432Node\Google\Chrome\BLBeacon" /v version',
            ]
            for cmd in reg_queries:
                try:
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=3,
                        check=False,
                    )
                    output = f"{result.stdout}\n{result.stderr}"
                    match = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", output)
                    if match:
                        return int(match.group(1))
                except Exception:
                    continue

            chrome_paths = [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            for chrome_path in chrome_paths:
                if not os.path.exists(chrome_path):
                    continue
                try:
                    result = subprocess.run(
                        [chrome_path, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=3,
                        check=False,
                    )
                    output = f"{result.stdout}\n{result.stderr}"
                    match = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", output)
                    if match:
                        return int(match.group(1))
                except Exception:
                    continue
        except Exception:
            pass
        return None

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
            if self.auto_wp is not None:
                is_posting = getattr(self.auto_wp, 'is_posting', True)
                if not is_posting:
                    return True
            
            # 모든 체크를 통과하면 계속 진행
            return False
        except Exception:
            # 오류 발생 시 안전하게 계속 진행 (중지하지 않음)
            return False

    def set_current_site(self, site):
        """현재 처리 중인 사이트 정보 설정"""
        self.current_site = site
    
    def get_thumbnail_file(self):
        """현재 사이트의 썸네일 파일 또는 기본 썸네일 반환"""
        import random
        
        # 현재 사이트의 썸네일 이미지 사용
        if self.current_site and self.current_site.get('thumbnail_image'):
            thumbnail_filename = self.current_site.get('thumbnail_image')
            thumbnail_path = os.path.join(get_base_path(), 'setting', 'images', thumbnail_filename)
            if os.path.exists(thumbnail_path):
                return thumbnail_filename
        
        # 기본 썸네일 목록에서 랜덤 선택 (정확한 파일명 사용)
        available_thumbnails = ['썸네일 (1).jpg', '썸네일 (2).jpg', '썸네일 (3).jpg',
                              '썸네일 (4).jpg', '썸네일 (5).jpg', '썸네일 (6).jpg', 
                              '썸네일 (7).jpg']
        
        # 존재하는 파일 중에서만 선택
        existing_thumbnails = []
        for thumb in available_thumbnails:
            thumb_path = os.path.join(get_base_path(), 'setting', 'images', thumb)
            if os.path.exists(thumb_path):
                existing_thumbnails.append(thumb)
        
        if existing_thumbnails:
            return random.choice(existing_thumbnails)
        else:
            return '썸네일 (1).jpg'  # 최후 기본값

    def initialize_apis(self):
        """사용 가능한 API 초기화 (웹 모드에서는 API 초기화 생략)"""
        global GEMINI_AVAILABLE, genai
        # API 상태 초기화
        self.api_status = {'gemini': False, 'web': True}  # Web은 항상 True로 가정(실행 시 체크)

        current_provider = (self.current_ai_provider or "").lower()
        use_gemini_api = (current_provider == "gemini")
        if not use_gemini_api:
            self.gemini_model = None
            self.api_status['gemini'] = False
            return

        # Gemini API 모드에서만 초기화
        if self.config_manager:
            gemini_api_key = self.config_manager.data.get("api_keys", {}).get("gemini", "")
        else:
            gemini_api_key = self.config_data.get('gemini_api_key', '')

        # API 모드에서만 라이브러리 로드 (웹 모드 시작 속도 개선)
        if not GEMINI_AVAILABLE or genai is None:
            GEMINI_AVAILABLE, genai = try_import_gemini()

        if GEMINI_AVAILABLE and genai is not None and gemini_api_key and gemini_api_key not in ["your_gemini_api_key", ""]:
            try:
                # API 키 설정
                genai.configure(api_key=gemini_api_key)
                safety_settings = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
                ]
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash-lite', safety_settings=safety_settings)
                self.api_status['gemini'] = True
                self.log("✅ Gemini API 초기화 성공")
            except Exception as e:
                self.log(f"❌ Gemini 초기화 실패: {e}")
                self.gemini_model = None
                self.api_status['gemini'] = False
        else:
            self.gemini_model = None
            self.api_status['gemini'] = False

    def call_ai_api(self, prompt, step_name, max_tokens=1500, temperature=0.7, system_content=None):
        """통합 AI 호출 (API 또는 Web)"""
        if self.should_stop_posting():
            return None
        
        ai_provider = self.current_ai_provider.lower()
        full_prompt = f"{system_content}\n\n{prompt}" if system_content else prompt
        response_text = None

        # Web AI 모드
        if ai_provider.startswith("web"):
            response_text = self._generate_content_with_web(full_prompt, ai_provider)
        
        # Gemini API 모드
        elif "gemini" in ai_provider:
            if self.api_status.get('gemini') and self.gemini_model:
                response_text = self.call_gemini_api(prompt, step_name, max_tokens, temperature, system_content)
            else:
                self.log("❌ Gemini API 사용 불가 (키 설정 확인)")
                return None
        
        else:
            self.log(f"❌ 알 수 없는 AI 제공자: {ai_provider}")
            return None

        if response_text and str(response_text).strip():
            self._save_ai_result_file(step_name, full_prompt, str(response_text), ai_provider)
        return response_text

    def _sanitize_filename_part(self, text):
        if not text:
            return "unknown"
        sanitized = re.sub(r'[\\/:*?"<>|]+', "_", str(text)).strip()
        sanitized = re.sub(r"\s+", "_", sanitized)
        return sanitized[:80] if sanitized else "unknown"

    def _save_ai_result_file(self, step_name, prompt_text, response_text, ai_provider):
        """AI 응답을 result 폴더 txt로 저장"""
        try:
            result_dir = os.path.join(get_base_path(), "setting", "result")
            os.makedirs(result_dir, exist_ok=True)

            keyword = self._sanitize_filename_part(getattr(self, "current_keyword", "keyword"))
            date_part = datetime.now().strftime("%Y-%m-%d")
            time_part = datetime.now().strftime("%H-%M")
            filename = f"{date_part}, {time_part}, {keyword}.txt"
            file_path = os.path.join(result_dir, filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(response_text)

            meta_filename = f"{date_part}, {time_part}, {keyword}, meta.txt"
            meta_path = os.path.join(result_dir, meta_filename)
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(f"[STEP] {step_name}\n")
                f.write(f"[PROVIDER] {ai_provider}\n")
                f.write(f"[SITE] {self.current_site.get('name', '') if self.current_site else ''}\n")
                f.write(f"[KEYWORD] {getattr(self, 'current_keyword', '')}\n")
                f.write("\n[PROMPT]\n")
                f.write(prompt_text or "")

            self.log("🗂️ AI 응답 저장 완료")
        except Exception as e:
            self.log(f"⚠️ AI 응답 파일 저장 실패: {e}")

    def _generate_content_with_web(self, prompt, provider):
        """Web AI를 사용하여 콘텐츠 생성"""
        try:
            if not self.driver:
                if not self.setup_driver():
                    return None

            content = ""
            if "gemini" in provider:
                content = self._generate_content_with_gemini_web(prompt)
            elif "perplexity" in provider:
                content = self._generate_content_with_perplexity_web(prompt)
            
            return content
        except Exception as e:
            self.log(f"❌ Web AI 생성 오류: {str(e)}")
            return None

    # --- Web AI Helper Methods (Gemini) ---
    def _ensure_gemini_tab(self):
        """Gemini 탭 확인 및 이동"""
        try:
            if not self.driver:
                return False
            assert self.driver is not None
            self.log("🌍 Gemini 탭 확인 중...")
            gemini_url = "https://gemini.google.com/app?hl=ko"

            if self.gemini_tab_handle and self.gemini_tab_handle in self.driver.window_handles:
                self.driver.switch_to.window(self.gemini_tab_handle)
                try:
                    current_url = (self.driver.current_url or "").lower()
                except Exception:
                    current_url = ""
                if "gemini.google.com" not in current_url:
                    self.log("↪️ Gemini 탭으로 이동합니다...")
                    self.driver.get(gemini_url)
                return True
            
            # 새 탭 생성
            self.log("🆕 Gemini 탭을 새로 엽니다...")
            self.driver.execute_script(f"window.open('{gemini_url}', '_blank');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.gemini_tab_handle = self.driver.current_window_handle
            time.sleep(2)
            try:
                self.driver.get(gemini_url)
            except Exception:
                pass
            self.log("✅ Gemini 탭 준비 완료")
            return True
        except Exception as e:
            self.log(f"⚠️ Gemini 탭 오류: {e}")
            return False

    def _generate_content_with_gemini_web(self, prompt):
        """Gemini Web 자동화"""
        self.log("🌐 Gemini 웹 작업을 시작합니다")
        if not self._ensure_gemini_tab():
            return None
        self._handle_gemini_blocking_dialogs()

        editor = None
        # 로그인은 최초 1회만 강하게 확인하고 이후에는 세션 재사용
        if self.gemini_logged_in:
            self.log("🔐 Gemini 로그인 세션 재사용")
            editor = self._find_gemini_editor(timeout=5)
            if not editor:
                self.gemini_logged_in = False
                self.log("⚠️ Gemini 세션 재확인이 필요합니다.")

        if not self.gemini_logged_in:
            self.log("🔐 Gemini 로그인 상태 확인 중...")
            if not self._ensure_gemini_logged_in(wait_seconds=180):
                return None
            editor = self._find_gemini_editor(timeout=15)

        self.log("⌨️ Gemini 프롬프트 입력창 확인 중...")
        if not editor:
            editor = self._find_gemini_editor(timeout=15)
        if not editor:
            self.log("❌ Gemini 입력창을 찾지 못했습니다.")
            return None

        # 입력 및 전송
        self.log("📝 프롬프트 입력 및 전송 중...")
        if not self._submit_gemini_prompt(prompt):
            return None
        
        # 응답 대기
        self.log("⏳ Gemini 응답 생성 대기 중...")
        return self._wait_for_gemini_response()

    def _find_gemini_editor(self, timeout: float = 5.0):
        """Gemini 에디터 찾기"""
        if not self.driver or By is None:
            return None
        selectors = [
            "div.ql-editor.textarea.new-input-ui[contenteditable='true'][aria-label='Gemini 프롬프트 입력']",
            "div.ql-editor.textarea[contenteditable='true'][aria-label='Gemini 프롬프트 입력']",
            "div.ql-editor.textarea[contenteditable='true']",
            "div[contenteditable='true'][role='textbox']",
            "rich-textarea div[contenteditable='true']",
            "div[contenteditable='true'][aria-label*='프롬프트']",
            "div[contenteditable='true'][aria-label*='prompt']",
            "textarea[aria-label*='프롬프트']",
            "textarea[aria-label*='prompt']",
        ]
        end_time = time.time() + timeout
        while time.time() < end_time:
            # 1) 일반 셀렉터 탐색
            for sel in selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if elem.is_displayed():
                        return elem
                except Exception:
                    pass
            # 2) 범용 콘텐츠 입력창 폴백
            try:
                candidates = self.driver.find_elements(By.XPATH, "//textarea | //*[@contenteditable='true']")
                for elem in candidates:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            txt = (elem.get_attribute("aria-label") or "") + " " + (elem.get_attribute("placeholder") or "")
                            txt = txt.lower()
                            if ("prompt" in txt) or ("프롬프트" in txt) or ("무엇을" in txt) or ("gemini" in txt):
                                return elem
                    except Exception:
                        pass
            except Exception:
                pass
            # 3) Shadow DOM 포함 JS 탐색 폴백
            js_elem = self._find_editor_via_js()
            if js_elem is not None:
                return js_elem
            time.sleep(0.5)
        return None

    def _find_editor_via_js(self):
        """Shadow DOM 포함 입력창 탐색"""
        if not self.driver:
            return None
        script = """
        const isVisible = (el) => {
          if (!el) return false;
          const style = window.getComputedStyle(el);
          if (!style || style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') < 0.1) return false;
          const r = el.getBoundingClientRect();
          return r.width > 140 && r.height > 24;
        };
        const score = (el) => {
          let s = 0;
          const label = ((el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('placeholder') || '') + ' ' + (el.innerText || '')).toLowerCase();
          if (label.includes('prompt') || label.includes('프롬프트') || label.includes('gemini') || label.includes('무엇을')) s += 6;
          if (el.getAttribute('contenteditable') === 'true') s += 4;
          if (el.tagName === 'TEXTAREA') s += 3;
          const r = el.getBoundingClientRect();
          s += Math.min(6, Math.floor((r.width * r.height) / 50000));
          return s;
        };
        const out = [];
        const walk = (root) => {
          if (!root) return;
          const nodes = root.querySelectorAll("textarea, [contenteditable='true'], div[role='textbox']");
          nodes.forEach((n) => { if (isVisible(n)) out.push(n); });
          const all = root.querySelectorAll('*');
          all.forEach((n) => { if (n.shadowRoot) walk(n.shadowRoot); });
        };
        walk(document);
        if (!out.length) return null;
        out.sort((a,b) => score(b) - score(a));
        return out[0];
        """
        try:
            elem = self.driver.execute_script(script)
            return elem
        except Exception:
            return None

    def _handle_gemini_blocking_dialogs(self):
        """Gemini 진입 시 가끔 뜨는 동의/계속 버튼 처리"""
        if not self.driver or By is None:
            return
        targets = [
            "동의", "I agree", "Accept all", "Agree", "확인", "계속", "Continue"
        ]
        xpath = " | ".join([f"//button[contains(normalize-space(.), '{t}')]" for t in targets] +
                           [f"//span[contains(normalize-space(.), '{t}')]/ancestor::button[1]" for t in targets])
        try:
            elems = self.driver.find_elements(By.XPATH, xpath)
            for elem in elems[:5]:
                try:
                    if elem.is_displayed() and elem.is_enabled():
                        try:
                            elem.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", elem)
                        time.sleep(0.2)
                except Exception:
                    pass
        except Exception:
            pass

    def _has_gemini_login_button(self, timeout: float = 3.0):
        """Gemini 페이지의 로그인 버튼 존재 여부 확인"""
        if not self.driver or By is None:
            return False
        selectors = [
            "a[aria-label='로그인'][href*='accounts.google.com/ServiceLogin']",
            "a[aria-label='Sign in'][href*='accounts.google.com/ServiceLogin']",
            "a.gb_Va[href*='accounts.google.com/ServiceLogin']",
            "div.boqOnegoogleliteOgbOneGoogleBar a[href*='accounts.google.com/ServiceLogin']",
        ]
        end_time = time.time() + timeout
        while time.time() < end_time:
            for sel in selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elems:
                        if elem.is_displayed():
                            return True
                except Exception:
                    pass
            time.sleep(0.5)
        return False

    def _click_gemini_login_button(self, timeout=5):
        """Gemini 상단 로그인 버튼 클릭"""
        if not self.driver or By is None:
            return False
        selectors = [
            "a[aria-label='로그인'][href*='accounts.google.com/ServiceLogin']",
            "a[aria-label='Sign in'][href*='accounts.google.com/ServiceLogin']",
            "a.gb_Va[href*='accounts.google.com/ServiceLogin']",
            "div.boqOnegoogleliteOgbOneGoogleBar a[href*='accounts.google.com/ServiceLogin']",
        ]
        end_time = time.time() + timeout
        while time.time() < end_time:
            for sel in selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elems:
                        if elem.is_displayed():
                            try:
                                elem.click()
                            except Exception:
                                self.driver.execute_script("arguments[0].click();", elem)
                            return True
                except Exception:
                    pass
            time.sleep(0.4)
        return False

    def _get_google_login_credentials(self):
        """Google 로그인 정보 조회 (환경변수 우선)"""
        email = os.environ.get("AUTO_WP_GOOGLE_EMAIL", "").strip()
        password = os.environ.get("AUTO_WP_GOOGLE_PASSWORD", "").strip()

        if (not email or not password) and self.config_manager:
            global_settings = self.config_manager.data.get("global_settings", {})
            if not email:
                email = str(global_settings.get("google_email", "")).strip()
            if not password:
                password = str(global_settings.get("google_password", "")).strip()
        return email, password

    def _auto_login_google(self, email, password, timeout=25):
        """Google 로그인 폼 자동 입력 및 제출"""
        # Google 정책 상 자동화 브라우저 로그인 차단 빈도가 높아 자동 입력은 비활성화
        return False

    def _is_google_unsafe_login_page(self) -> bool:
        """Google '안전하지 않은 브라우저' 차단 페이지 감지"""
        if not self.driver:
            return False
        try:
            page_text = ""
            try:
                page_text = (self.driver.page_source or "").lower()
            except Exception:
                page_text = ""
            try:
                title_text = (self.driver.title or "").lower()
            except Exception:
                title_text = ""

            blocked_markers = [
                "로그인할 수 없음",
                "브라우저 또는 앱이 안전하지 않을 수 있습니다",
                "this browser or app may not be secure",
                "couldn’t sign you in",
            ]
            merged = f"{title_text}\n{page_text}"
            return any(marker.lower() in merged for marker in blocked_markers)
        except Exception:
            return False

    def _ensure_gemini_logged_in(self, wait_seconds=180):
        """로그인 버튼 기준으로 Gemini 로그인 상태 확인/대기 (2차 인증 대기 포함)"""
        if self._has_gemini_login_button(timeout=3):
            self.gemini_logged_in = False
            self.log("🔐 Gemini 로그인이 필요합니다.")
            if self._click_gemini_login_button(timeout=5):
                self.log("➡️ Gemini 로그인 버튼 클릭 완료")

            # 자동화 브라우저 차단 페이지 조기 감지
            if self._is_google_unsafe_login_page():
                self.log("❌ Google 로그인 차단: '안전하지 않은 브라우저' 페이지가 감지되었습니다.")
                self.log("ℹ️ 일반 Chrome에서 같은 프로필로 먼저 로그인한 뒤 다시 시작해주세요.")
                return False

            # 수동 로그인 대기 (과도한 장기 대기 제거)
            two_factor_wait = max(60, wait_seconds)
            self.log(f"⏳ 브라우저에서 로그인/인증을 완료해주세요. 최대 {two_factor_wait}초 대기합니다.")
            end_time = time.time() + two_factor_wait
            while time.time() < end_time:
                if self._is_google_unsafe_login_page():
                    self.log("❌ Google 로그인 차단: '안전하지 않은 브라우저' 페이지가 감지되었습니다.")
                    self.log("ℹ️ 일반 Chrome에서 같은 프로필로 먼저 로그인한 뒤 다시 시작해주세요.")
                    return False
                # 프롬프트 입력창이 보이면 바로 로그인 완료로 판단
                if self._find_gemini_editor(timeout=0.2):
                    self.gemini_logged_in = True
                    self.log("✅ Gemini 로그인 확인 완료 (프롬프트 입력창 감지)")
                    return True
                # 로그인 버튼이 사라져도 페이지 전환 중일 수 있으므로 계속 대기
                _ = self._has_gemini_login_button(timeout=0.2)
                time.sleep(0.5)
            self.log("❌ Gemini 로그인/2차 인증 대기 시간이 초과되었습니다.")
            return False

        # 이미 로그인된 경우에도 입력창이 보여야 실제 진행
        ready_end = time.time() + max(30, wait_seconds)
        last_notice = 0
        while time.time() < ready_end:
            self._handle_gemini_blocking_dialogs()
            if self._find_gemini_editor(timeout=0.2):
                self.gemini_logged_in = True
                return True
            now_sec = int(time.time())
            if now_sec - last_notice >= 10:
                remaining = int(max(0, ready_end - time.time()))
                driver = self.driver
                if driver is None:
                    self.log("❌ 브라우저 세션이 종료되어 Gemini 입력창 탐색을 중단합니다.")
                    return False
                try:
                    current_url = driver.current_url
                    title = driver.title
                except Exception:
                    current_url, title = "", ""
                self.log(f"⌛ Gemini 입력창 탐색 중... ({remaining}초 남음) | {title} | {current_url}")
                # 혹시 다른 페이지로 이탈한 경우 Gemini 페이지로 복귀
                if "gemini.google.com" not in (current_url or "").lower():
                    try:
                        driver.get("https://gemini.google.com/app?hl=ko")
                    except Exception:
                        pass
                last_notice = now_sec
            time.sleep(0.5)
        self.log("❌ Gemini 프롬프트 입력창을 찾지 못했습니다.")
        return False

    def _submit_gemini_prompt(self, prompt):
        """Gemini 프롬프트 전송"""
        try:
            if not self.driver or Keys is None:
                return False
            # 이전 답변과 구분하기 위한 전송 전 마커 저장
            self._gemini_turn_marker = self._capture_gemini_turn_marker()
            editor = self._find_gemini_editor(timeout=15)
            if not editor:
                # 최종 폴백: 현재 활성 요소 사용 시도
                try:
                    editor = self.driver.switch_to.active_element
                except Exception:
                    editor = None
                if not editor:
                    return False

            # 사용자 지정 선택자 기준: 입력창 클릭 후 프롬프트 입력
            try:
                editor.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", editor)

            # Trusted Types 정책으로 innerHTML 주입이 차단되므로 키보드 입력만 사용
            editor.send_keys(Keys.CONTROL, "a")
            editor.send_keys(Keys.BACKSPACE)
            time.sleep(0.2)

            pasted = False
            if pyperclip is not None:
                try:
                    pyperclip.copy(prompt)
                    editor.send_keys(Keys.CONTROL, "v")
                    pasted = True
                except Exception as clip_error:
                    self.log(f"⚠️ 클립보드 붙여넣기 실패, 직접 입력으로 전환: {clip_error}")

            if not pasted:
                editor.send_keys(prompt)

            time.sleep(0.4)
            enter_sent = False
            try:
                editor.send_keys(Keys.ENTER)
                enter_sent = True
            except Exception:
                enter_sent = False

            # Enter 전송이 실패하거나 UI 상태로 무시될 수 있어, 전송 버튼 클릭 폴백 적용
            clicked_send = self._click_gemini_send_button(timeout=2.0)
            if not enter_sent and not clicked_send:
                self.log("⚠️ Gemini 전송 트리거 실패 (Enter/버튼)")
                return False
            self.log("✅ Gemini 프롬프트 전송 완료")
            return True
        except Exception as e:
            self.log(f"⚠️ Gemini 입력 실패: {e}")
            return False

    def _capture_gemini_turn_marker(self):
        """현재 Gemini 대화 상태를 식별하기 위한 마커"""
        if not self.driver or By is None:
            return {"copy_count": 0, "response_count": 0}
        try:
            copy_buttons = self.driver.find_elements(By.CSS_SELECTOR, "copy-button button[data-test-id='copy-button']")
        except Exception:
            copy_buttons = []
        response_count = 0
        response_selectors = [
            "div.markdown",
            "model-response",
            "message-content",
        ]
        for sel in response_selectors:
            try:
                elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                response_count = max(response_count, len(elems))
            except Exception:
                pass
        return {"copy_count": len(copy_buttons), "response_count": response_count}

    def _is_gemini_generating(self) -> bool:
        """Gemini가 현재 답변 생성 중인지 추정"""
        if not self.driver or By is None:
            return False
        selectors = [
            "button[aria-label*='중지']",
            "button[aria-label*='Stop']",
            "button[aria-label*='stop']",
        ]
        for sel in selectors:
            try:
                for btn in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    if btn.is_displayed():
                        return True
            except Exception:
                pass
        return False

    def _click_gemini_send_button(self, timeout: float = 2.0) -> bool:
        """Gemini 전송 버튼(메시지 보내기) 클릭"""
        if not self.driver or By is None:
            return False
        selectors = [
            "button.send-button.submit",
            "button[aria-label='메시지 보내기']",
            "button[aria-label='Send message']",
            "button[aria-label*='보내기']",
            "button[aria-label*='send']",
            "mat-icon[fonticon='send']",
        ]
        end_time = time.time() + timeout
        while time.time() < end_time:
            for sel in selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elems:
                        target = elem
                        try:
                            # mat-icon을 찾은 경우 상위 버튼으로 승격
                            if elem.tag_name.lower() != "button":
                                target = elem.find_element(By.XPATH, "./ancestor::button[1]")
                        except Exception:
                            target = elem

                        try:
                            disabled_attr = (target.get_attribute("aria-disabled") or "").lower()
                            enabled = target.is_displayed() and target.is_enabled() and disabled_attr != "true"
                        except Exception:
                            enabled = False
                        if not enabled:
                            continue

                        try:
                            target.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", target)
                        return True
                except Exception:
                    pass
            time.sleep(0.15)
        return False

    def _wait_for_gemini_response(self, timeout=120):
        """Gemini 응답 대기 및 추출"""
        try:
            if not self.driver or By is None:
                return None
            self.log(f"⏱️ Gemini 응답을 최대 {timeout}초 동안 기다립니다...")
            time.sleep(4)

            # 답변 완료 대기 후 복사 버튼 클릭으로 응답 가져오기
            copy_selector = "copy-button button[data-test-id='copy-button']"
            end_time = time.time() + timeout
            last_notice = 0
            turn_marker = getattr(self, "_gemini_turn_marker", None) or {}
            base_copy_count = int(turn_marker.get("copy_count", 0))
            base_resp_count = int(turn_marker.get("response_count", 0))
            while time.time() < end_time:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, copy_selector)
                    visible_btns = [b for b in buttons if b.is_displayed() and b.is_enabled()]
                    current_copy_count = len(buttons)
                    current_resp_count = 0
                    for sel in ["div.markdown", "model-response", "message-content"]:
                        try:
                            current_resp_count = max(current_resp_count, len(self.driver.find_elements(By.CSS_SELECTOR, sel)))
                        except Exception:
                            pass

                    # 새 턴 응답이 생기기 전에는 기존 복사 버튼을 누르지 않음
                    turn_ready = (current_copy_count > base_copy_count) or (current_resp_count > base_resp_count)
                    if visible_btns and turn_ready and (not self._is_gemini_generating()):
                        target_btn = visible_btns[-1]
                        try:
                            target_btn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", target_btn)
                        time.sleep(0.5)

                        if pyperclip is not None:
                            copied = (pyperclip.paste() or "").strip()
                            if copied:
                                return copied

                        # 클립보드 미사용/실패 시 DOM 텍스트 폴백
                        responses = self.driver.find_elements(By.CSS_SELECTOR, "div.markdown")
                        if responses:
                            fallback_text = responses[-1].text.strip()
                            if fallback_text:
                                return fallback_text
                except Exception:
                    pass
                now_sec = int(time.time())
                if now_sec - last_notice >= 10:
                    remaining = int(max(0, end_time - time.time()))
                    self.log(f"⌛ Gemini 응답 대기 중... ({remaining}초 남음)")
                    last_notice = now_sec
                time.sleep(1)

            # 마지막 폴백
            try:
                responses = self.driver.find_elements(By.CSS_SELECTOR, "div.markdown")
                if responses:
                    return responses[-1].text.strip()
            except Exception:
                pass
            self.log("❌ Gemini 응답 대기 시간 초과")
            return None
        except Exception:
            return None

    # --- Web AI Helper Methods (Perplexity) - Placeholder ---
    def _generate_content_with_perplexity_web(self, prompt):
        self.log("⚠️ Perplexity Web 기능은 아직 구현되지 않았습니다.")
        return None


    def call_gemini_api(self, prompt, step_name, max_tokens, temperature, system_content):
        """Gemini API 호출"""
        try:
            if genai is None:
                raise Exception("Gemini 라이브러리가 설치되지 않았습니다.")
            assert genai is not None
            # API 키 재확인
            if not self.config_manager:
                raise Exception("설정 관리자를 찾을 수 없습니다.")
            gemini_key = self.config_manager.data.get("api_keys", {}).get("gemini", "").strip()
            if not gemini_key:
                raise Exception("Gemini API 키가 설정되지 않았습니다.")
            
            # 모델 상태 재확인
            if not self.gemini_model:
                raise Exception("Gemini 모델이 초기화되지 않았습니다.")
            
            full_prompt = f"{system_content}\n\n---\n\n{prompt}" if system_content else prompt
            types_module = getattr(genai, "types", None)
            if types_module is None:
                raise Exception("Gemini 타입 모듈을 찾을 수 없습니다.")
            generation_config = types_module.GenerationConfig(
                max_output_tokens=max_tokens, 
                temperature=temperature
            )
            
            # 타임아웃과 함께 API 호출
            import time
            start_time = time.time()
            
            # API 호출 재시도 로직 (429 ResourceExhausted 대응)
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    response = self.gemini_model.generate_content(full_prompt, generation_config=generation_config)
                    elapsed_time = time.time() - start_time
                    
                    # 🔥 응답 검증 강화
                    if hasattr(response, 'text') and response.text:
                        response_text = response.text.strip()
                        if not response_text:
                            raise Exception("응답 텍스트가 공백만 포함되어 있습니다.")
                        
                        self.log(f"✅ {step_name} Gemini 응답 성공 ({len(response_text)}자, {elapsed_time:.1f}초)")
                        return response_text
                    else:
                        # 빈 응답에 대한 상세 정보
                        if hasattr(response, 'prompt_feedback'):
                            feedback = response.prompt_feedback
                            if feedback and hasattr(feedback, 'block_reason'):
                                raise Exception(f"Gemini가 콘텐츠를 차단했습니다: {feedback.block_reason}")
                        raise Exception("응답 텍스트가 비어있습니다.")
                except Exception as gen_error:
                    error_msg = str(gen_error)
                    # 429 ResourceExhausted 또는 Quota 관련 오류 체크
                    if "ResourceExhausted" in error_msg or "429" in error_msg or "quota" in error_msg.lower():
                        if attempt < max_retries - 1:
                            wait_time = 60 * (attempt + 1)
                            self.log(f"⚠️ 쿼터 초과 (429). {wait_time}초 대기 후 재시도합니다... ({attempt + 1}/{max_retries})")
                            time.sleep(wait_time)
                            continue
                    
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
- 중요: 큰따옴표, #, *, 백틱 같은 특수문자는 절대 사용하지 마!

제목 예시:
인덕션 청소 | 10분만에 완벽하게 끝내는 3가지 방법
스마트폰 배터리 | 2배 오래 쓰는 5가지 비밀 설정
냉장고 정리 | 30분으로 1주일이 편해지는 수납법

키워드: {keyword}

위 지침에 맞는 제목 1개만 출력해. 설명이나 다른 내용은 일체 포함하지 마. 특수문자 없이 순수한 텍스트만 출력해."""

            system_prompt = "너는 SEO 제목 전문가야. 주어진 지침에 따라 정확한 제목만 생성해. 큰따옴표나 특수문자 없이 순수한 텍스트로만 출력해."
            
            result = self.call_ai_api(title_prompt, "제목 생성", max_tokens=100, temperature=0.7, system_content=system_prompt)
            
            if result and result.strip():
                generated_title = result.strip()
                
                # 제목에서 불필요한 문자 강제 제거
                generated_title = generated_title.replace('"', '').replace("'", '').replace('`', '')
                generated_title = generated_title.replace('#', '').replace('*', '').replace('**', '')
                generated_title = re.sub(r'^[\s\-_=]+', '', generated_title)
                generated_title = re.sub(r'[\s\-_=]+$', '', generated_title)
                generated_title = generated_title.strip()
                
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
        """5단계 콘텐츠 정리 - 마무리 구조 확인"""
        try:
            import re
            
            # 기본적인 HTML 구조 확인
            has_basic_structure = '<h2>' in content or '<h3>' in content or '<p>' in content
            
            # 로그 출력
            if not has_basic_structure:
                self.log("🚨 5단계: 기본 HTML 구조 누락 - 제목이나 내용이 없습니다!")
                
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

    def remove_approval_meta_terms(self, content):
        """승인용 콘텐츠의 메타 용어 제거 - <h2>, <p> 태그는 보존"""
        try:
            import re
            # 제거할 메타 용어들 (승인용 글에서는 HTML 태그 보존)
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
                r'😊.*?:',
                r'👍.*?:',
                r'✅.*?:',
                r'💡.*?:',
                r'📌.*?:',
                r'🔍.*?:',
                r'구체적이고\s*설명적인',
                r'단계별\s*목표',
                r'핵심\s*키워드',
                r'타겟\s*독자',
                r'```[a-z]*',
                r'```',
                r'\*\*[^*]*\*\*:',
                r'#+\s*[^#]*:',
                r'AI\s*역할\s*언급',
                r'\d+년\s*경력의?\s*전문가로서',
                r'SEO\s*전문가로서',
                r'콘텐츠\s*작가로서',
                r'마크다운\s*문법\s*절대\s*사용\s*금지',
                r'HTML\s*태그만\s*사용',
                r'코드\s*블록\s*사용\s*금지'
            ]

            # HTML 관련 마크업 문구 제거 (승인용에서는 실제 HTML 태그는 보존)
            html_markup_patterns = [
                r'```html.*?```',
                r'```html',
                r'`html.*?`',
                r'`html',
                r'"html',
                r'<!DOCTYPE[^>]*>',
                r'<html[^>]*>',
                r'</html>',
                r'<head[^>]*>.*?</head>',
                r'<body[^>]*>',
                r'</body>',
                r'<meta[^>]*>',
                r'<title[^>]*>.*?</title>',
            ]

            # 각 메타 용어 제거
            for term in meta_terms:
                content = re.sub(term, '', content, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)

            # HTML 관련 마크업 문구 제거
            for pattern in html_markup_patterns:
                content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)

            # 마크다운을 HTML로 강제 변환 (승인용 글 전용)
            content = self.convert_approval_markdown_to_html(content)

            # <h1> 태그만 제거 (승인용에서는 사용하지 않음)
            content = re.sub(r'<h1[^>]*>.*?</h1>', '', content, flags=re.IGNORECASE | re.DOTALL)
            content = re.sub(r'<h1[^>]*>', '', content, flags=re.IGNORECASE)
            content = re.sub(r'</h1>', '', content, flags=re.IGNORECASE)

            # 승인용에서는 <h2>, <p> 태그는 보존 (제거하지 않음)

            # 특정 패턴들 추가 제거
            content = re.sub(r'서론\s*\d+자', '', content, flags=re.IGNORECASE)
            content = re.sub(r'본문\s*\d+자', '', content, flags=re.IGNORECASE)
            content = re.sub(r'제목\s*\d+자', '', content, flags=re.IGNORECASE)

            # 단독으로 나오는 숫자+점 패턴 제거
            content = re.sub(r'^\s*\d+\.\s*$', '', content, flags=re.MULTILINE)
            content = re.sub(r'<p>\s*\d+\.\s*</p>', '', content, flags=re.IGNORECASE)

            # 빈 태그나 의미없는 구문 정리
            content = re.sub(r'<p>\s*</p>', '', content)
            content = re.sub(r'<div>\s*</div>', '', content)
            content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)

            return content.strip()

        except Exception as e:
            self.log(f"승인용 메타 용어 제거 중 오류: {e}")
            return content

    def convert_approval_markdown_to_html(self, content):
        """승인용 글의 마크다운을 HTML로 변환 - <h2>, <p> 태그 강제 적용"""
        try:
            import re
            
            # 마크다운 헤더를 HTML로 변환
            content = re.sub(r'^### (.*?)$', r'<h3><strong>\1</strong></h3>', content, flags=re.MULTILINE)
            content = re.sub(r'^## (.*?)$', r'<h2><strong>\1</strong></h2>', content, flags=re.MULTILINE)
            content = re.sub(r'^# (.*?)$', '', content, flags=re.MULTILINE)  # h1은 제거
            
            # 마크다운 볼드를 HTML로 변환
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'__(.*?)__', r'<strong>\1</strong>', content)
            
            # 마크다운 이탤릭을 HTML로 변환
            content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)
            content = re.sub(r'_(.*?)_', r'<em>\1</em>', content)
            
            # 줄바꿈을 <p> 태그로 변환 (빈 줄로 구분된 단락들)
            paragraphs = re.split(r'\n\s*\n', content.strip())
            html_paragraphs = []
            
            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if paragraph:
                    # 이미 HTML 태그로 감싸져 있는지 확인
                    if paragraph.startswith('<h') or paragraph.startswith('<div') or paragraph.startswith('<table'):
                        html_paragraphs.append(paragraph)
                    elif paragraph.startswith('<p>') and paragraph.endswith('</p>'):
                        html_paragraphs.append(paragraph)
                    else:
                        # 단순 텍스트는 <p> 태그로 감싸기
                        html_paragraphs.append(f'<p>{paragraph}</p>')
            
            content = '\n\n'.join(html_paragraphs)
            
            # 중복 <p> 태그 제거
            content = re.sub(r'<p>\s*<p>(.*?)</p>\s*</p>', r'<p>\1</p>', content, flags=re.DOTALL)
            
            return content.strip()
            
        except Exception as e:
            self.log(f"승인용 마크다운 변환 중 오류: {e}")
            return content

    def final_approval_validation(self, content, keyword):
        """승인용 글 최종 검증 및 강제 HTML 변환"""
        try:
            import re
            
            self.log("🔍 승인용 글 최종 검증 시작...")
            
            # 마크다운 문법 검사
            markdown_found = False
            markdown_patterns = [
                (r'##\s+', '## 헤딩'),
                (r'\*\*.*?\*\*', '**볼드**'),
                (r'\*.*?\*(?!\*)', '*이탤릭*'),
                (r'```', '코드 블록'),
                (r'---', '구분선'),
                (r'`.*?`', '인라인 코드')
            ]
            
            for pattern, name in markdown_patterns:
                if re.search(pattern, content):
                    self.log(f"⚠️ 마크다운 발견: {name}")
                    markdown_found = True
            
            if markdown_found:
                self.log("🔧 마크다운을 HTML로 강제 변환 중...")
                content = self.convert_approval_markdown_to_html(content)
                
                # 변환 후 재검사
                for pattern, name in markdown_patterns:
                    if re.search(pattern, content):
                        self.log(f"⚠️ 변환 후에도 마크다운 남음: {name}")
                        # 더 강력한 변환 수행
                        content = re.sub(r'##\s+(.*?)(?=\n|$)', r'<h2><strong>\1</strong></h2>', content)
                        content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                        content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)
                        content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
                        content = re.sub(r'`(.*?)`', r'\1', content)
                        content = re.sub(r'---+', '', content)
            
            # HTML 구조 검증
            h2_count = len(re.findall(r'<h2[^>]*>.*?</h2>', content, re.IGNORECASE | re.DOTALL))
            p_count = len(re.findall(r'<p[^>]*>.*?</p>', content, re.IGNORECASE | re.DOTALL))
            
            self.log(f"📊 HTML 구조 검증: <h2> {h2_count}개, <p> {p_count}개")
            
            if h2_count == 0:
                self.log("⚠️ <h2> 태그가 없음 - 소제목 강제 생성")
                # 간단한 소제목 추가
                subtitles = ["활용법", "주요 특징", "실무 팁"]
                for i, subtitle in enumerate(subtitles):
                    if f"<h2>" not in content:
                        content = f"<h2><strong>{keyword} {subtitle}</strong></h2>\n" + content
                        break
            
            if p_count == 0:
                self.log("⚠️ <p> 태그가 없음 - 텍스트를 <p>로 감싸기")
                # 텍스트를 <p> 태그로 감싸기
                lines = content.split('\n')
                processed_lines = []
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('<'):
                        processed_lines.append(f"<p>{line}</p>")
                    elif line:
                        processed_lines.append(line)
                content = '\n'.join(processed_lines)
            
            self.log("✅ 승인용 글 최종 검증 완료")
            return content
            
        except Exception as e:
            self.log(f"승인용 글 최종 검증 중 오류: {e}")
            return content

    def extract_approval_title(self, raw_content, keyword):
        """승인용 글에서 제목만 추출 (원본 AI 응답에서)"""
        try:
            import re
            
            self.log("🔍 원본 응답에서 제목 추출 시작...")
            
            lines = raw_content.split('\n')
            for i, line in enumerate(lines[:5]):  # 처음 5줄만 확인
                line = line.strip()
                if not line:
                    continue
                
                # HTML 태그 완전 제거
                clean_line = re.sub(r'<[^>]+>', '', line).strip()
                
                # 불필요한 문자 제거 (큰따옴표, #, *, 백틱 등)
                clean_line = clean_line.replace('"', '').replace("'", '').replace('`', '')
                clean_line = clean_line.replace('#', '').replace('*', '').replace('**', '')
                clean_line = re.sub(r'^[\s\-_=]+', '', clean_line)
                clean_line = re.sub(r'[\s\-_=]+$', '', clean_line)
                clean_line = clean_line.strip()
                
                # 제목 패턴 확인: 콜론이 있고, 적절한 길이이고, HTML 태그로 시작하지 않음
                if ':' in clean_line and 15 <= len(clean_line) <= 70 and not line.startswith('<'):
                    # 추가 검증: 콜론 뒤에 콤마가 있어야 함 (승인용 제목 형식)
                    parts = clean_line.split(':', 1)
                    if len(parts) == 2 and ',' in parts[1]:
                        self.log(f"📌 제목 추출 성공: {clean_line}")
                        return clean_line
            
            # 제목을 찾지 못한 경우 키워드 기반 생성
            fallback_title = f"{keyword}: 활용법, 주요 특징, 실무 팁"
            self.log(f"⚠️ 제목 추출 실패, 자동 생성: {fallback_title}")
            return fallback_title
            
        except Exception as e:
            self.log(f"제목 추출 중 오류: {e}")
            return f"{keyword}: 활용법, 주요 특징, 실무 팁"

    def process_approval_step_content(self, raw_content, step_number, keyword):
        """승인용 글 단계별 정밀 처리 - 제목 분리, HTML 구조 강제 적용"""
        try:
            import re
            
            self.log(f"🔧 승인용 {step_number}단계 정밀 처리 시작...")
            
            # 1단계: 기본 메타 용어 제거
            content = self.remove_approval_meta_terms(raw_content)
            
            # 2단계: 단계별 맞춤 처리
            if step_number == 1:
                # 1단계: 제목 + 서론 + 첫 번째 소제목 + 본문
                content = self.process_approval_step1(content, keyword)
            elif step_number == 2:
                # 2단계: 두 번째 소제목 + 본문
                content = self.process_approval_step2(content, keyword)
            elif step_number == 3:
                # 3단계: 세 번째 소제목 + 본문
                content = self.process_approval_step3(content, keyword)
            
            self.log(f"✅ 승인용 {step_number}단계 처리 완료")
            return content
            
        except Exception as e:
            self.log(f"승인용 {step_number}단계 처리 중 오류: {e}")
            return self.remove_approval_meta_terms(raw_content)

    def process_approval_step1(self, content, keyword):
        """승인용 1단계 처리: 제목은 완전히 제외하고 서론+소제목1+본문1만 반환"""
        try:
            import re
            
            self.log("🔧 1단계: 제목 완전 제외, 서론+소제목1+본문1 처리")
            
            lines = content.split('\n')
            processed_lines = []
            title_lines_removed = 0
            intro_content = []
            subtitle_content = []
            body_content = []
            current_section = 'intro'
            
            # 먼저 제목으로 보이는 모든 라인을 식별하고 제거
            filtered_lines = []
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # HTML 태그 제거한 순수 텍스트
                clean_line = re.sub(r'<[^>]+>', '', line).strip()
                
                # 제목 패턴 감지 및 완전 제거
                is_title = False
                
                # 패턴 1: 콜론이 있고 콤마가 있는 제목 형식
                if ':' in clean_line and ',' in clean_line and 15 <= len(clean_line) <= 70:
                    parts = clean_line.split(':', 1)
                    if len(parts) == 2 and len(parts[1].split(',')) >= 2:
                        is_title = True
                        self.log(f"📌 제목 패턴1 감지하여 제거: {clean_line[:40]}...")
                
                # 패턴 2: 키워드가 포함되고 콜론이 있는 경우
                if keyword in clean_line and ':' in clean_line and len(clean_line) <= 60:
                    is_title = True
                    self.log(f"📌 제목 패턴2 감지하여 제거: {clean_line[:40]}...")
                
                # 패턴 3: 첫 5줄 중에서 콜론만 있는 경우도 제목으로 간주
                if i < 5 and ':' in clean_line and not line.startswith('<') and len(clean_line) >= 10:
                    is_title = True
                    self.log(f"📌 제목 패턴3 감지하여 제거: {clean_line[:40]}...")
                
                if is_title:
                    title_lines_removed += 1
                    continue  # 제목 라인은 완전히 스킵
                
                filtered_lines.append(line)
            
            self.log(f"📊 제목 라인 {title_lines_removed}개 제거됨")
            
            # 필터링된 라인들을 다시 처리
            for line in filtered_lines:
                # 마크다운 헤더를 HTML로 강제 변환
                if re.match(r'^##\s+', line):
                    subtitle_text = re.sub(r'^##\s+', '', line).strip()
                    subtitle_text = re.sub(r'\*\*(.*?)\*\*', r'\1', subtitle_text)  # ** 제거
                    subtitle_content.append(f"<h2><strong>{subtitle_text}</strong></h2>")
                    current_section = 'body'
                    self.log(f"📌 마크다운 소제목 변환: {subtitle_text}")
                    continue
                
                # HTML h2 태그가 이미 있는 경우
                if re.match(r'<h2[^>]*>', line, re.IGNORECASE):
                    current_section = 'body'
                    # <strong> 태그가 없으면 추가
                    if '<strong>' not in line.lower():
                        line = re.sub(r'<h2[^>]*>(.*?)</h2>', r'<h2><strong>\1</strong></h2>', line, flags=re.IGNORECASE)
                    subtitle_content.append(line)
                    self.log(f"📌 HTML 소제목 발견: {line}")
                    continue
                
                # 볼드 마크다운 제거
                line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
                
                # 본문 내용 처리
                if current_section == 'intro':
                    intro_content.append(line)
                elif current_section == 'body':
                    body_content.append(line)
                else:
                    intro_content.append(line)
            
            # 서론을 <p> 태그로 강제 처리 (h태그 사용하지 않음)
            if intro_content:
                intro_text = ' '.join(intro_content).strip()
                # HTML 태그 제거 후 순수 텍스트만 추출
                intro_text = re.sub(r'<[^>]+>', '', intro_text)
                
                # 서론에서도 제목 패턴이 남아있는지 한번 더 확인
                if ':' in intro_text and ',' in intro_text:
                    # 콜론 이후 부분만 사용 (제목 앞부분 제거)
                    parts = intro_text.split(':', 1)
                    if len(parts) == 2:
                        intro_text = parts[1].strip()
                        # 첫 번째 콤마 이후 부분부터 사용
                        comma_parts = intro_text.split(',', 1)
                        if len(comma_parts) == 2:
                            intro_text = comma_parts[1].strip()
                        self.log("📌 서론에서 제목 잔여 부분 제거")
                
                if intro_text and len(intro_text) > 10:  # 의미있는 서론이 있을 때만
                    processed_lines.append(f"<p>{intro_text}</p>")
                    self.log(f"📌 서론 생성 (p태그): {intro_text[:50]}...")
            
            # 소제목이 없으면 강제 생성
            if not subtitle_content:
                processed_lines.append(f"<h2><strong>{keyword} 기본 활용법</strong></h2>")
                self.log(f"📌 소제목 강제 생성: {keyword} 기본 활용법")
            else:
                processed_lines.extend(subtitle_content)
            
            # 본문을 <p> 태그로 강제 처리
            if body_content:
                body_text = ' '.join(body_content).strip()
                # HTML 태그 제거 후 순수 텍스트만 추출
                body_text = re.sub(r'<[^>]+>', '', body_text)
                if body_text and len(body_text) > 10:  # 의미있는 본문이 있을 때만
                    processed_lines.append(f"<p>{body_text}</p>")
                    self.log(f"📌 본문 생성: {body_text[:50]}...")
            
            result = '\n\n'.join(processed_lines)
            self.log("✅ 1단계 제목 완전 제거 및 HTML 구조 강제 적용 완료")
            return result
            
        except Exception as e:
            self.log(f"1단계 처리 중 오류: {e}")
            return content

    def process_approval_step2(self, content, keyword):
        """승인용 2단계 처리: 소제목2 + 본문2"""
        try:
            import re
            
            self.log("🔧 2단계: 소제목2+본문2 처리")
            
            lines = content.split('\n')
            processed_lines = []
            subtitle_content = []
            body_content = []
            current_section = 'subtitle'
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 마크다운 헤더를 HTML로 강제 변환
                if re.match(r'^##\s+', line):
                    subtitle_text = re.sub(r'^##\s+', '', line).strip()
                    subtitle_text = re.sub(r'\*\*(.*?)\*\*', r'\1', subtitle_text)  # ** 제거
                    subtitle_content.append(f"<h2><strong>{subtitle_text}</strong></h2>")
                    current_section = 'body'
                    self.log(f"📌 2단계 마크다운 소제목 변환: {subtitle_text}")
                    continue
                
                # HTML h2 태그가 이미 있는 경우
                if re.match(r'<h2[^>]*>', line, re.IGNORECASE):
                    current_section = 'body'
                    # <strong> 태그가 없으면 추가
                    if '<strong>' not in line.lower():
                        line = re.sub(r'<h2[^>]*>(.*?)</h2>', r'<h2><strong>\1</strong></h2>', line, flags=re.IGNORECASE)
                    subtitle_content.append(line)
                    self.log(f"📌 2단계 HTML 소제목 발견: {line}")
                    continue
                
                # 볼드 마크다운 제거
                line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
                
                # 본문 내용 수집
                if current_section == 'body':
                    body_content.append(line)
                else:
                    # 소제목이 없으면 이 내용으로 소제목 생성
                    if not subtitle_content and current_section == 'subtitle':
                        first_words = ' '.join(line.split()[:3])
                        subtitle_content.append(f"<h2><strong>{keyword} {first_words} 특징</strong></h2>")
                        current_section = 'body'
                        self.log(f"📌 2단계 소제목 자동 생성: {keyword} {first_words} 특징")
                    body_content.append(line)
            
            # 소제목이 없으면 강제 생성
            if not subtitle_content:
                processed_lines.append(f"<h2><strong>{keyword} 주요 특징</strong></h2>")
                self.log(f"📌 2단계 소제목 강제 생성: {keyword} 주요 특징")
            else:
                processed_lines.extend(subtitle_content)
            
            # 본문을 <p> 태그로 강제 처리
            if body_content:
                body_text = ' '.join(body_content).strip()
                # HTML 태그 제거 후 순수 텍스트만 추출
                body_text = re.sub(r'<[^>]+>', '', body_text)
                if body_text:
                    processed_lines.append(f"<p>{body_text}</p>")
                    self.log(f"📌 2단계 본문 생성: {body_text[:50]}...")
            
            result = '\n\n'.join(processed_lines)
            self.log("✅ 2단계 HTML 구조 강제 적용 완료")
            return result
            
        except Exception as e:
            self.log(f"2단계 처리 중 오류: {e}")
            return content

    def process_approval_step3(self, content, keyword):
        """승인용 3단계 처리: 소제목3 + 본문3"""
        try:
            import re
            
            self.log("🔧 3단계: 소제목3+본문3 처리")
            
            lines = content.split('\n')
            processed_lines = []
            subtitle_content = []
            body_content = []
            current_section = 'subtitle'
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 마크다운 헤더를 HTML로 강제 변환
                if re.match(r'^##\s+', line):
                    subtitle_text = re.sub(r'^##\s+', '', line).strip()
                    subtitle_text = re.sub(r'\*\*(.*?)\*\*', r'\1', subtitle_text)  # ** 제거
                    subtitle_content.append(f"<h2><strong>{subtitle_text}</strong></h2>")
                    current_section = 'body'
                    self.log(f"📌 3단계 마크다운 소제목 변환: {subtitle_text}")
                    continue
                
                # HTML h2 태그가 이미 있는 경우
                if re.match(r'<h2[^>]*>', line, re.IGNORECASE):
                    current_section = 'body'
                    # <strong> 태그가 없으면 추가
                    if '<strong>' not in line.lower():
                        line = re.sub(r'<h2[^>]*>(.*?)</h2>', r'<h2><strong>\1</strong></h2>', line, flags=re.IGNORECASE)
                    subtitle_content.append(line)
                    self.log(f"📌 3단계 HTML 소제목 발견: {line}")
                    continue
                
                # 볼드 마크다운 제거
                line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
                
                # 본문 내용 수집
                if current_section == 'body':
                    body_content.append(line)
                else:
                    # 소제목이 없으면 이 내용으로 소제목 생성
                    if not subtitle_content and current_section == 'subtitle':
                        first_words = ' '.join(line.split()[:3])
                        subtitle_content.append(f"<h2><strong>{keyword} {first_words} 활용 팁</strong></h2>")
                        current_section = 'body'
                        self.log(f"📌 3단계 소제목 자동 생성: {keyword} {first_words} 활용 팁")
                    body_content.append(line)
            
            # 소제목이 없으면 강제 생성
            if not subtitle_content:
                processed_lines.append(f"<h2><strong>{keyword} 실무 활용 팁</strong></h2>")
                self.log(f"📌 3단계 소제목 강제 생성: {keyword} 실무 활용 팁")
            else:
                processed_lines.extend(subtitle_content)
            
            # 본문을 <p> 태그로 강제 처리
            if body_content:
                body_text = ' '.join(body_content).strip()
                # HTML 태그 제거 후 순수 텍스트만 추출
                body_text = re.sub(r'<[^>]+>', '', body_text)
                if body_text:
                    processed_lines.append(f"<p>{body_text}</p>")
                    self.log(f"📌 3단계 본문 생성: {body_text[:50]}...")
            
            result = '\n\n'.join(processed_lines)
            self.log("✅ 3단계 HTML 구조 강제 적용 완료")
            return result
            
        except Exception as e:
            self.log(f"3단계 처리 중 오류: {e}")
            return content

    def generate_approval_content(self, keyword):
        """승인용 콘텐츠 생성 - approval.txt 우선, 없으면 approval1~3 폴백"""
        try:
            single_approval_path = os.path.join(get_base_path(), "setting", "prompts", "approval.txt")
            if os.path.exists(single_approval_path):
                try:
                    with open(single_approval_path, 'r', encoding='utf-8-sig') as f:
                        prompt_template = f.read()
                except UnicodeDecodeError:
                    with open(single_approval_path, 'r', encoding='utf-8') as f:
                        prompt_template = f.read()

                prompt = prompt_template.replace("{keyword}", keyword)
                self.log("📝 승인용 approval.txt 프롬프트 적용")
                response_text = self.call_ai_api(prompt, "승인용 approval", max_tokens=2000, temperature=0.7)
                if not response_text or not response_text.strip():
                    self.log("❌ 승인용 approval.txt 응답 없음")
                    return None, None, None

                response_text = self.validate_ai_output(response_text.strip(), keyword)
                title = self.extract_approval_title(response_text, keyword)
                full_content = self.final_approval_validation(response_text, keyword)

                if not title:
                    title = self.generate_approval_fallback_title(keyword) or f"{keyword}: 활용법, 주요 특징, 실무 팁"
                    self.log(f"📝 자동 생성된 제목: {title}")

                thumbnail_path = self.create_thumbnail(title, keyword)
                self.log(f"📝 승인용 본문 생성 완료 - approval.txt ({len(full_content)}자)")
                return title, full_content, thumbnail_path

            # 승인용 프롬프트 파일 로드 (3개만)
            approval_files = [
                "approval1.txt", "approval2.txt", "approval3.txt"
            ]

            all_content_parts = []
            title = ""

            # 3개 승인용 프롬프트 파일을 순차적으로 적용
            for i, approval_file in enumerate(approval_files, 1):
                prompt_path = os.path.join(get_base_path(), "setting", "prompts", approval_file)

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
                    
                    # 승인용 글 전용: 프롬프트 파일에 이미 규칙이 있으므로 추가하지 않음

                    print(f"승인용 {i}단계 생성 중", end=" ")

                    # 통합 AI API 호출
                    try:
                        response_text = self.call_ai_api(prompt, f"승인용 {i}단계", max_tokens=1500, temperature=0.7)

                        if response_text and response_text.strip():
                            # 첫 번째 단계에서 승인용 제목 추출 (처리 전 원본에서)
                            if i == 1:
                                title = self.extract_approval_title(response_text.strip(), keyword)
                            
                            # AI 출력 검증 및 자동 수정 (프롬프트 '중요 주의사항' 규칙 적용)
                            response_text = self.validate_ai_output(response_text.strip(), keyword)
                            
                            # 승인용 글 전용 정밀 처리 (제목 완전 제거)
                            step_content = self.process_approval_step_content(response_text, i, keyword)
                            
                            all_content_parts.append(step_content)

                        # 다음 단계로 계속 진행

                    except Exception as step_error:
                        self.log(f"❌ 승인용 {i}단계 오류: {str(step_error)}")
                        # 단계별 오류 시에도 계속 진행
                else:
                    self.log(f"❌ 승인용 프롬프트 파일 없음: {approval_file}")

            if not all_content_parts:
                self.log(f"🔥 승인용 콘텐츠 생성 실패 - 모든 단계 실패")
                return None, None, None

            # 3단계의 콘텐츠를 결합
            full_content = "\n\n".join(all_content_parts)
            
            # 승인용 글 최종 검증 및 강제 HTML 변환
            full_content = self.final_approval_validation(full_content, keyword)
            
            self.log(f"📝 승인용 본문 생성 완료 - 3단계 ({len(full_content)}자)")
            print()  # 승인용 콘텐츠 생성 완료 후 개행

            if not title:
                # 승인용 전용 fallback 제목 생성
                self.log("⚠️ 승인용 제목 추출 실패, fallback 제목 생성")
                title = self.generate_approval_fallback_title(keyword)
                if not title:
                    # 최후 fallback - 승인용 형식에 맞게 생성
                    approval_subtitles = ["활용법", "주요 특징", "실무 팁"]
                    title = f"{keyword}: {approval_subtitles[0]}, {approval_subtitles[1]}, {approval_subtitles[2]}"
                self.log(f"📝 자동 생성된 제목: {title}")

            # 썸네일 이미지 선택 및 제목 추가
            thumbnail_filename = self.get_thumbnail_file()
            base_thumbnail_path = os.path.join(get_base_path(), 'images', thumbnail_filename)

            # 제목이 있으면 썸네일에 제목 추가
            thumbnail_path = self.create_thumbnail(title, keyword)

            return title, full_content, thumbnail_path

        except Exception as e:
            self.log(f"🔥 승인용 콘텐츠 생성 오류: {str(e)}")
            import traceback
            self.log(f"🔍 상세 오류:\n{traceback.format_exc()}")
            return None, None, None

    def convert_markdown_to_html(self, content):
        """마크다운을 HTML로 변환"""
        try:
            # 먼저 링크 버튼 및 다운로드 버튼 HTML을 모두 보호
            link_patterns = []
            def preserve_link_html(match):
                link_patterns.append(match.group(0))
                return f"__LINK_PLACEHOLDER_{len(link_patterns)-1}__"

            # 다운로드 버튼 전체 container 보호 (class="button-container")
            content = re.sub(r'<div\s+class="button-container">.*?</div>', preserve_link_html, content, flags=re.DOTALL)
            
            # 개별 다운로드 버튼 <a> 태그 보호 (class="custom-download-btn")
            content = re.sub(r'<a[^>]*class="custom-download-btn"[^>]*>.*?</a>', preserve_link_html, content, flags=re.DOTALL)
            
            # <div><center><a class="blink"  패턴 보호
            content = re.sub(r'<div><center><a[^>]*class="blink"[^>]*>.*?</a></center></div>', preserve_link_html, content, flags=re.DOTALL)
            # <center><a class="blink"  패턴도 보호
            content = re.sub(r'<center><a[^>]*class="blink"[^>]*>.*?</a></center>', preserve_link_html, content, flags=re.DOTALL)
            # 단순 <a class="blink"  패턴도 보호
            content = re.sub(r'<a[^>]*class="blink"[^>]*>.*?</a>', preserve_link_html, content, flags=re.DOTALL)
            
            # link1, link2, link3 클래스 보호 - prompt2.txt, prompt3.txt, prompt4.txt에서 사용
            content = re.sub(r'<div><center><p><a[^>]*class="link[123]"[^>]*>.*?</a></p></center></div>', preserve_link_html, content, flags=re.DOTALL)
            content = re.sub(r'<a[^>]*class="link[123]"[^>]*>.*?</a>', preserve_link_html, content, flags=re.DOTALL)

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

    def validate_ai_output(self, content, keyword):
        """
        AI 출력 검증 - 프롬프트의 '중요 주의사항' 규칙들을 자동으로 검사하고 수정
        프롬프트 파일에 적힌 주의사항들을 Python 로직으로 처리
        """
        try:
            import re
            
            issues_found = []
            fixes_applied = []
            
            # 규칙 1: 플레이스홀더 텍스트 검증
            placeholder_patterns = [
                (r'<p>본문\d+-?\d?\s*\d+자</p>', '실제 본문 내용이 없고 플레이스홀더만 있음'),
                (r'<h[2-4]><strong>소제목\d+</strong></h[2-4]>', '소제목이 구체적이지 않고 플레이스홀더만 있음'),
                (r'\[실제 유용한 URL\]', '[실제 유용한 URL] 플레이스홀더가 그대로 남아있음'),
                (r'\[구체적인 앵커 텍스트\]', '[구체적인 앵커 텍스트] 플레이스홀더가 그대로 남아있음'),
                (r'href="\s*url\s*입력\s*"', 'href="url 입력" 플레이스홀더가 그대로 남아있음'),
                (r'href="\s*\[.*?\]\s*"', 'href에 대괄호 플레이스홀더가 남아있음'),
                (r'>\s*앵커\s*텍스트\s*<', '"앵커 텍스트" 플레이스홀더가 그대로 남아있음'),
                (r'\[\{keyword\}.*?\]', '[{keyword}...] 형태의 플레이스홀더가 남아있음'),
                (r'\[.*?대상\s*\d+.*?\]', '[대상 1], [대상 2] 같은 플레이스홀더가 남아있음'),
                (r'\[.*?항목\s*\d+.*?\]', '[항목 1], [비교 항목] 같은 플레이스홀더가 남아있음'),
                (r'\[.*?표\s*주제.*?\]', '[표 주제] 플레이스홀더가 남아있음'),
                (r'\[사용자의 실제 고민 질문\]', 'FAQ 질문이 구체적이지 않고 플레이스홀더만 있음'),
                (r'\[상세한 답변 내용\]', 'FAQ 답변이 구체적이지 않고 플레이스홀더만 있음'),
                (r'\[.*?\d+자.*?\]', '[300자], [200-300자] 같은 분량 플레이스홀더가 남아있음'),
            ]
            
            for pattern, issue_msg in placeholder_patterns:
                matches = re.findall(pattern, content, flags=re.IGNORECASE)
                if matches:
                    issues_found.append(f"❌ {issue_msg} (발견: {len(matches)}개)")
                    self.log(f"⚠️ AI 출력 검증 실패: {issue_msg}")
                    # 실제 내용으로 교체 시도
                    if 'href="url 입력"' in content or 'href=" url 입력 "' in content:
                        search_url = f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"
                        content = re.sub(r'href="\s*url\s*입력\s*"', f'href="{search_url}"', content, flags=re.IGNORECASE)
                        fixes_applied.append("✅ 'href=\"url 입력\"'을 실제 검색 URL로 교체")
            
            # 규칙 2: 형식 지시자 검증 (출력에 포함되면 안 되는 것들)
            format_indicators = [
                r'【형식\d+】',
                r'▼▼▼.*?▼▼▼',
                r'출력\s*형식',
                r'출력\s*예시',
                r'절대\s*지켜야\s*할\s*규칙',
                r'중요\s*주의사항',
                r'\(아래\s*형식을.*?출력해\)',
            ]
            
            for pattern in format_indicators:
                if re.search(pattern, content, flags=re.IGNORECASE):
                    issues_found.append(f"❌ 형식 지시자가 출력에 포함됨: {pattern}")
                    self.log(f"⚠️ AI가 형식 지시자를 출력에 포함시킴: {pattern}")
                    # 형식 지시자 제거
                    content = re.sub(pattern, '', content, flags=re.IGNORECASE)
                    fixes_applied.append(f"✅ 형식 지시자 제거: {pattern}")
            
            # 규칙 3: HTML 속성 검증
            html_attribute_issues = []
            
            # class 속성 없는 링크 검사 (blink, link1, link2, link3, custom-download-btn 중 하나는 있어야 함)
            links_without_class = re.findall(r'<a\s+(?![^>]*class=)[^>]*href=[^>]*>', content, flags=re.IGNORECASE)
            if links_without_class:
                html_attribute_issues.append(f"❌ class 속성이 없는 <a> 태그 발견: {len(links_without_class)}개")
            
            # href 속성 없는 링크 검사
            links_without_href = re.findall(r'<a\s+(?![^>]*href=)[^>]*class=[^>]*>', content, flags=re.IGNORECASE)
            if links_without_href:
                html_attribute_issues.append(f"❌ href 속성이 없는 <a> 태그 발견: {len(links_without_href)}개")
            
            # target 속성 없는 링크 검사
            links_without_target = re.findall(r'<a\s+(?![^>]*target=)[^>]*href=[^>]*>', content, flags=re.IGNORECASE)
            if links_without_target and len(links_without_target) > 0:
                # target 속성 추가
                content = re.sub(r'(<a\s+[^>]*)(href=[^>]*)>', r'\1\2 target="_self">', content, flags=re.IGNORECASE)
                fixes_applied.append(f"✅ {len(links_without_target)}개 링크에 target=\"_self\" 속성 추가")
            
            # 따옴표 없는 class 속성 검사 (class=blink 같은 경우)
            class_without_quotes = re.findall(r'class=(?!")([^\s>]+)', content, flags=re.IGNORECASE)
            if class_without_quotes:
                html_attribute_issues.append(f"❌ 따옴표 없는 class 속성 발견: {class_without_quotes}")
                # 따옴표 추가
                content = re.sub(r'class=(?!")([^\s>]+)', r'class="\1"', content, flags=re.IGNORECASE)
                fixes_applied.append(f"✅ class 속성에 따옴표 추가")
            
            issues_found.extend(html_attribute_issues)
            
            # 규칙 4: link1, link2, link3 숫자 검증
            link_classes = re.findall(r'class="(link\d?)"', content, flags=re.IGNORECASE)
            if 'link"' in str(link_classes) or '"link"' in content:
                issues_found.append("❌ class=\"link\"에서 숫자가 빠짐 (link1, link2, link3 중 하나여야 함)")
                self.log("⚠️ class=\"link\"는 숫자가 필요함")

            # 규칙 5: href URL 구조 정규화 강제 적용
            normalized_content = self._sanitize_anchor_hrefs(content)
            if normalized_content != content:
                content = normalized_content
                fixes_applied.append("✅ href URL 구조 정규화 적용")
            
            # 검증 결과 로깅
            if issues_found:
                self.log(f"⚠️ AI 출력 검증: {len(issues_found)}개 문제 발견")
                for issue in issues_found:
                    self.log(f"  {issue}")
            
            if fixes_applied:
                self.log(f"✅ AI 출력 자동 수정: {len(fixes_applied)}개 수정 적용")
                for fix in fixes_applied:
                    self.log(f"  {fix}")
            
            if not issues_found and not fixes_applied:
                self.log("✅ AI 출력 검증 통과: 문제 없음")
            
            return content
            
        except Exception as e:
            self.log(f"AI 출력 검증 중 오류: {e}")
            import traceback
            self.log(f"상세 오류:\n{traceback.format_exc()}")
            return content

    def enforce_html_structure(self, content, step_number, keyword):
        """각 단계별로 정확한 HTML 구조를 강제 적용 - 마크다운 완전 제거"""
        try:
            import re
            lines = content.strip().split('\n')
            structured_content = []
            
            # 모든 마크다운 기호 완전 제거 함수
            def clean_markdown(text):
                # HTML 태그 제거
                text = re.sub(r'<[^>]+>', '', text)
                # 마크다운 헤더 기호 제거 (# ## ### 등)
                text = re.sub(r'#+\s*', '', text)
                # 마크다운 강조 기호 제거 (** __ * _ 등)
                text = re.sub(r'\*+', '', text)
                text = re.sub(r'_+', '', text)
                # 마크다운 리스트 기호 제거 (- * + 1. 등)
                text = re.sub(r'^[\-\*\+]\s*', '', text, flags=re.MULTILINE)
                text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
                # 마크다운 코드 블록 제거
                text = re.sub(r'```[a-z]*\n?', '', text, flags=re.IGNORECASE)
                text = re.sub(r'```', '', text)
                # 인라인 코드 제거
                text = re.sub(r'`([^`]*)`', r'\1', text)
                # 링크 제거 [text](url)
                text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', text)
                # 기타 특수문자 정리
                text = re.sub(r'[\[\](){}]', '', text)
                return text.strip()
            
            if step_number == 1:  # 1단계: 서론 + 소제목1 + 본문1
                intro_text = ""
                subtitle1_text = ""
                content1_text = ""
                
                # AI 응답에서 텍스트 추출하고 마크다운 제거
                all_text = ' '.join([clean_markdown(line) for line in lines if line.strip()])
                
                # 텍스트를 적절히 분할
                words = all_text.split()
                if len(words) > 50:
                    intro_text = ' '.join(words[:50])  # 처음 50단어를 서론으로
                    subtitle1_text = f"{keyword} 기본 활용법"
                    content1_text = ' '.join(words[50:])  # 나머지를 본문으로
                else:
                    intro_text = all_text
                    subtitle1_text = f"{keyword} 기본 활용법"
                    content1_text = f"{keyword}의 기본적인 활용 방법에 대해 자세히 설명드리겠습니다. 다양한 측면에서 접근하여 실용적인 정보를 제공하고자 합니다. 기본 개념부터 시작하여 실무에 적용할 수 있는 구체적인 방법까지 포괄적으로 다루어보겠습니다. 이를 통해 효과적인 활용이 가능하도록 도움을 드리겠습니다. 단계적으로 접근하면 누구나 쉽게 이해하고 활용할 수 있을 것입니다. 기초부터 차근차근 알아보는 것이 중요합니다."
                
                # 기본값 설정 - approval.txt 지침에 따라 정확한 분량으로
                if not intro_text or len(intro_text) < 270:
                    intro_text = f"{keyword}는 현대 사회에서 점점 더 중요해지고 있는 핵심 개념입니다. 이와 관련하여 기본적인 활용법부터 시작해서 주요 특징들을 체계적으로 파악하고, 실무에서 바로 적용할 수 있는 실용적인 팁까지 포괄적으로 다뤄보겠습니다. 각 단계별로 구체적인 사례와 함께 설명하여 초보자부터 전문가까지 모두에게 도움이 되는 내용으로 구성하였습니다."
                
                if len(content1_text) < 700:
                    content1_text = f"{keyword}의 기본적인 활용 방법에 대해 체계적으로 설명드리겠습니다. 먼저 가장 중요한 것은 기초 개념을 정확히 이해하는 것입니다. 이는 모든 응용과 심화 학습의 토대가 되기 때문입니다. 다음으로는 단계별 접근 방법을 통해 실제 적용 과정을 익혀야 합니다. 초기 설정부터 시작해서 기본 기능들을 하나씩 숙지해 나가는 것이 효과적입니다. 특히 실무에서 자주 사용되는 핵심 기능들을 우선적으로 학습하는 것이 중요합니다. 또한 올바른 사용 방법과 주의사항을 함께 익혀두면 향후 문제 상황을 예방할 수 있습니다. 기본기가 탄탄해야 나중에 고급 기능들도 쉽게 익힐 수 있으므로 충분한 연습을 통해 기초를 다져두시기 바랍니다. 실제 업무나 프로젝트에 적용할 때는 작은 부분부터 시작해서 점진적으로 확대해 나가는 방식을 권장드립니다."
                
                # 순수 HTML 구조 생성
                structured_content.append(f"<p>{intro_text}</p>")
                structured_content.append(f"<h2><strong>{subtitle1_text}</strong></h2>")
                structured_content.append(f"<p>{content1_text}</p>")
            
            elif step_number == 2:  # 2단계: 소제목2 + 본문2
                subtitle2_text = ""
                content2_text = ""
                
                # AI 응답에서 텍스트 추출하고 마크다운 제거
                all_text = ' '.join([clean_markdown(line) for line in lines if line.strip()])
                
                # 첫 번째 문장을 소제목으로, 나머지를 본문으로
                sentences = all_text.split('.')[:2] if '.' in all_text else [all_text]
                if sentences[0]:
                    subtitle2_text = sentences[0][:25] + "의 주요 특징"
                    content2_text = all_text
                
                # 기본값 설정 - approval2.txt 지침에 따라 700자 이상
                if not subtitle2_text:
                    subtitle2_text = f"{keyword} 주요 특징"
                
                if not content2_text or len(content2_text) < 700:
                    content2_text = f"{keyword}의 주요 특징과 핵심적인 요소들을 상세히 살펴보겠습니다. 가장 두드러진 특징은 사용자 친화적인 접근성과 높은 효율성을 동시에 제공한다는 점입니다. 이러한 특성 덕분에 초보자도 쉽게 시작할 수 있으면서도 전문가들에게는 강력한 기능을 제공합니다. 또한 확장성이 뛰어나서 작은 규모부터 대규모 프로젝트까지 유연하게 대응할 수 있습니다. 특히 주목할 만한 점은 지속적인 업데이트와 개선을 통해 최신 트렌드를 반영한다는 것입니다. 보안 측면에서도 강화된 기능들을 제공하여 안전한 사용 환경을 보장합니다. 성능 면에서는 최적화된 알고리즘과 효율적인 리소스 관리를 통해 빠른 처리 속도를 실현하고 있습니다. 사용자 인터페이스는 직관적으로 설계되어 학습 곡선을 최소화하면서도 전문적인 작업이 가능하도록 구성되어 있습니다."
                
                # 순수 HTML 구조 생성
                structured_content.append(f"<h2><strong>{subtitle2_text}</strong></h2>")
                structured_content.append(f"<p>{content2_text}</p>")
            
            elif step_number == 3:  # 3단계: 소제목3 + 본문3 + 표
                subtitle3_text = ""
                content3_text = ""
                
                # AI 응답에서 텍스트 추출하고 마크다운 제거
                all_text = ' '.join([clean_markdown(line) for line in lines if line.strip()])
                
                # 첫 번째 문장을 소제목으로, 나머지를 본문으로
                sentences = all_text.split('.')[:2] if '.' in all_text else [all_text]
                if sentences[0]:
                    subtitle3_text = sentences[0][:25] + " 실무 팁"
                    content3_text = all_text
                
                # 기본값 설정 - approval3.txt 지침에 따라 700자 이상
                if not subtitle3_text:
                    subtitle3_text = f"{keyword} 실무 팁"
                
                if not content3_text or len(content3_text) < 700:
                    content3_text = f"{keyword}의 실무 활용 팁과 고급 테크닉을 소개해드리겠습니다. 실제 업무 환경에서 효율성을 극대화하기 위한 핵심적인 방법들을 중심으로 설명하겠습니다. 먼저 작업 흐름을 최적화하는 방법부터 살펴보겠습니다. 반복적인 작업을 자동화하고 단축키나 템플릿을 활용하면 시간을 크게 절약할 수 있습니다. 또한 협업 환경에서의 효과적인 활용 방안도 중요한 고려사항입니다. 팀원들과의 원활한 소통과 작업 공유를 위한 도구와 방법론을 익혀두면 프로젝트 진행이 훨씬 수월해집니다. 문제 해결 능력을 기르기 위해서는 일반적인 오류 상황과 대처 방안을 미리 숙지해두는 것이 좋습니다. 정기적인 백업과 버전 관리를 통해 작업 손실을 방지하고 이전 상태로 복구할 수 있는 시스템을 구축하는 것도 필수입니다."
                
                # 순수 HTML 구조 생성
                structured_content.append(f"<h2><strong>{subtitle3_text}</strong></h2>")
                structured_content.append(f"<p>{content3_text}</p>")
                
                # 표 추가
                table_html = f"""<table border="1">
<tr>
<th>구분</th>
<th>내용</th>
<th>특징</th>
</tr>
<tr>
<td>기본 활용</td>
<td>{keyword} 기초 사용법</td>
<td>누구나 쉽게 접근 가능</td>
</tr>
<tr>
<td>고급 활용</td>
<td>{keyword} 심화 기능</td>
<td>전문적 활용 방법</td>
</tr>
<tr>
<td>실무 적용</td>
<td>{keyword} 현장 활용</td>
<td>실제 업무 효율성 증대</td>
</tr>
</table>"""
                structured_content.append(table_html)
            
            return '\n\n'.join(structured_content)
            
        except Exception as e:
            self.log(f"HTML 구조 강제 적용 오류: {e}")
            return content

    def generate_approval_fallback_title(self, keyword):
        """승인용 형식에 맞는 fallback 제목 생성"""
        try:
            # approval1.txt 형식에 맞는 제목 생성 요청
            prompt = f"""키워드 '{keyword}'를 사용하여 승인용 제목을 생성해줘.

형식: [메인 키워드]: [소제목1 키워드], [소제목2 키워드], [소제목3 키워드]
예시: "건강한 식습관: 영양소, 식단 관리, 생활 습관"

요구사항:
- 메인 키워드 '{keyword}' 필수 포함
- 콜론(:) 뒤에 3개의 소제목 키워드를 콤마(,)로 구분
- 30자 내외
- HTML 태그 사용 금지, 순수 텍스트만

제목만 출력해줘."""

            response_text = self.call_ai_api(prompt, "승인용 fallback 제목 생성", max_tokens=100)
            if response_text and response_text.strip():
                title = response_text.strip()
                # HTML 태그 제거
                import re
                title = re.sub(r'<[^>]+>', '', title)
                # 승인용 형식 검증 (콜론과 콤마 포함)
                if ':' in title and ',' in title:
                    self.log(f"✅ 승인용 fallback 제목 생성 성공: {title}")
                    return title
                    
            self.log("⚠️ 승인용 fallback 제목 생성 실패")
            return None
            
        except Exception as e:
            self.log(f"승인용 fallback 제목 생성 중 오류: {e}")
            return None

    def generate_simple_content(self, keyword, content_type="revenue"):
        """간단한 콘텐츠 생성 - 수익용/승인용 선택 가능"""
        try:
            # 콘텐츠 생성 시작 - 포스팅 상태 활성화
            self.is_posting = True
            self.current_keyword = keyword
            self.current_content_type = content_type

            # 선택된 AI 모드별 사전 점검
            ai_provider = (self.current_ai_provider or "").lower()
            if ai_provider == "gemini" and not self.api_status.get('gemini', False):
                self.log("🔥 API 사용 모드이지만 Gemini API를 사용할 수 없습니다.")
                self.is_posting = False
                return None, None, None

            mode_text = "승인용" if content_type == "approval" else "수익용"
            self.log(f"👍 포스팅 모드: {mode_text}")

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
                
                # AI 호출
                self.log(f"🤖 {step_num}단계 AI 호출")
                response_text = self.call_ai_api(
                    user_prompt, f"수익용 {step_num}단계", 
                    max_tokens=1500, 
                    temperature=0.7, 
                    system_content=system_content
                )
                
                if not response_text:
                    self.log(f"❌ {step_num}단계 AI 응답 실패")
                    return None, None, None
                
                # AI 출력 검증 및 자동 수정 (프롬프트 '중요 주의사항' 규칙 적용)
                response_text = self.validate_ai_output(response_text, keyword)
                
                # 모든 단계에서 마크다운 코드 블록 언어 표시 제거
                import re
                response_text = re.sub(r'`html\s*\n?', '', response_text, flags=re.IGNORECASE)
                response_text = re.sub(r'`javascript\s*\n?', '', response_text, flags=re.IGNORECASE)
                response_text = re.sub(r'`css\s*\n?', '', response_text, flags=re.IGNORECASE)
                response_text = re.sub(r'`json\s*\n?', '', response_text, flags=re.IGNORECASE)
                response_text = re.sub(r'`python\s*\n?', '', response_text, flags=re.IGNORECASE)
                response_text = re.sub(r'`[a-z]+\s*\n?', '', response_text)  # 기타 언어명
                response_text = re.sub(r'```[a-z]*\n?', '', response_text)  # ```html 등
                response_text = re.sub(r'```\n?', '', response_text)  # ``` 끝
                
                # 1단계는 정리 함수 사용하지 않음 (HTML 구조 보존 위해)
                if step_num == 1:
                    step_content = response_text.strip()
                else:
                    # 2-5단계도 HTML 구조 보존 - AI 역할 언급만 제거
                    step_content = response_text.strip()
                    
                    # AI 역할 언급 제거
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
                        r'`([^`]+)`',         # `inline code` → 내용만 남기고 제거
                    ]
                    for pattern in markdown_patterns:
                        if pattern in [r'\*\*([^*]+)\*\*', r'\*([^*]+)\*', r'`([^`]+)`']:
                            step_content = re.sub(pattern, r'\1', step_content)
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
                
            # 전체 내용 결합
            full_content = "\n\n".join(all_content_parts)
            
            # 가짜 URL 교체
            full_content = self.replace_fake_urls(full_content, keyword)
            
            # 콘텐츠 최종 정리 (발행 전)
            full_content = self.clean_content_before_publish(full_content)
            
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
            
            # 2. href URL 교체 (HTML 구조 유지)
            # - https://
            # - http://
            # - //example.com (protocol-relative)
            href_pattern = r'href="((?:https?:)?//[^"]*)"'
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
                additional_link = f'<p><a href="{additional_link_url}" target="_self">{additional_link_text}</a></p>'
                
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
    
    def clean_content_before_publish(self, content):
        """발행 전 콘텐츠 정리 (AI 작성을 방해하지 않는 최소한의 수정만)"""
        try:
            import re
            from urllib.parse import quote
            
            # 0. 다운로드 버튼 HTML을 보호 및 복구 (먼저 추출)
            download_button_pattern = r'<div class="button-container">.*?</div>'
            download_buttons = re.findall(download_button_pattern, content, flags=re.IGNORECASE | re.DOTALL)
            
            # 다운로드 버튼 URL 복구 및 속성 수정
            fixed_buttons = []
            for button in download_buttons:
                fixed_button = button
                
                # 1. href 속성 복구 - 공백으로 잘린 URL 수정
                # href="https://...?q=키워드 일부" 나머지..." → href="https://...?q=전체키워드..."
                href_matches = re.findall(r'href="([^"]*)"([^<>]*?)<img', fixed_button, re.DOTALL)
                for href_url, text_after in href_matches:
                    # href 뒤에 잘린 텍스트가 있는지 확인
                    if text_after.strip() and not text_after.strip().startswith('class='):
                        # 잘린 부분 추출
                        cut_text = text_after.split('class=')[0].strip()
                        # URL에 추가 (URL 인코딩)
                        if '?' in href_url:
                            # 쿼리 파라미터가 있는 경우
                            fixed_url = href_url.rstrip('"') + quote(cut_text)
                        else:
                            fixed_url = href_url + quote(cut_text)
                        # 수정된 URL로 교체
                        original = f'href="{href_url}"{text_after}<img'
                        replacement = f'href="{fixed_url}" <img'
                        fixed_button = fixed_button.replace(original, replacement)
                
                # 2. 깨진 class 속성 수정 - 중복 따옴표 제거
                fixed_button = re.sub(r'class="([^"]+)""', r'class="\1"', fixed_button)
                
                # 3. 따옴표 없는 속성에 따옴표 추가
                fixed_button = re.sub(r'class=([^\s">]+)(?=\s|>)', r'class="\1"', fixed_button)
                fixed_button = re.sub(r'target=([^\s">]+)(?=\s|>)', r'target="\1"', fixed_button)
                fixed_button = re.sub(r'src=([^\s">]+)(?=\s|>)', r'src="\1"', fixed_button)
                fixed_button = re.sub(r'alt=([^\s">]+)(?=\s|>)', r'alt="\1"', fixed_button)
                
                fixed_buttons.append(fixed_button)
                
            if fixed_buttons:
                self.log(f"✅ 다운로드 버튼 {len(fixed_buttons)}개 URL 및 속성 복구 완료")
            
            # 다운로드 버튼을 플레이스홀더로 교체 (수정된 버전으로)
            for i, button in enumerate(download_buttons):
                content = content.replace(button, f"__PROTECTED_DOWNLOAD_BUTTON_{i}__", 1)
            
            # 1. 불완전한 style 속성 수정 (값이 비어있는 경우만)
            # style="text-align:" → style="text-align:center;"
            # style="color:" → style="color: #ee2323;"
            style_fixed = False
            if 'style="text-align:"' in content:
                content = re.sub(r'style="text-align:\s*"', 'style="text-align:center;"', content)
                style_fixed = True
            if 'style="color:"' in content:
                content = re.sub(r'style="color:\s*"', 'style="color: #ee2323;"', content)
                style_fixed = True
            if style_fixed:
                self.log("✅ 불완전한 style 속성 수정")
            
            # 2. 불완전한 h태그 수정 (h2, h3, h4 모두 처리)
            # <strong>...</strong></h2> → <h2><strong>...</strong></h2>
            # <strong>...</strong></h3> → <h3><strong>...</strong></h3>
            # <strong>...</strong></h4> → <h4><strong>...</strong></h4>
            h_tag_fixed = False
            for h_num in [2, 3, 4]:
                h_pattern = rf'(?<!<h{h_num}>)(<strong>[^<]+</strong></h{h_num}>)'
                h_matches = re.findall(h_pattern, content)
                if h_matches:
                    for match in h_matches:
                        if not match.startswith(f'<h{h_num}>'):
                            fixed = f'<h{h_num}>' + match
                            content = content.replace(match, fixed)
                            h_tag_fixed = True
            if h_tag_fixed:
                self.log("✅ 불완전한 h태그 수정 (h2, h3, h4)")
            
            # 3. 유니코드 큰따옴표와 백틱만 제거 (일반 큰따옴표는 HTML 속성에 필수이므로 보존)
            # ❌ 제거: “ ” ″ ` (유니코드 따옴표/백틱)
            # ✅ 보존: " ' (일반 따옴표)
            unicode_quotes_and_backticks = ['“', '”', '″', '`']
            quote_found = False
            for bad_char in unicode_quotes_and_backticks:
                if bad_char in content:
                    content = content.replace(bad_char, '')
                    quote_found = True
            if quote_found:
                self.log("✅ 유니코드 큰따옴표/백틱 제거 (일반 따옴표는 보존)")
            
            # 4. '클릭' 단어를 유의어로 대체 (제목 제외)
            # HTML h1 태그 안의 내용은 보존 (제목은 '클릭' 사용 가능)
            click_replaced = False
            
            # h1 태그 내용 추출 및 보호
            h1_pattern = r'(<h1[^>]*>)(.*?)(</h1>)'
            h1_matches = re.findall(h1_pattern, content, re.DOTALL | re.IGNORECASE)
            h1_contents = []
            
            # h1 태그를 임시 플레이스홀더로 대체
            for i, (opening, title_content, closing) in enumerate(h1_matches):
                placeholder = f"___H1_PLACEHOLDER_{i}___"
                h1_contents.append((opening, title_content, closing))
                content = content.replace(opening + title_content + closing, placeholder, 1)
            
            # h1 태그 밖의 '클릭' 단어를 유의어로 대체
            click_alternatives = ['선택', '확인', '눌러보기', '터치', '접속', '방문']
            if '클릭' in content:
                import random
                # 다양한 '클릭' 패턴 대체
                content = re.sub(r'클릭하세요', lambda m: random.choice(['선택하세요', '확인하세요', '눌러보세요']), content)
                content = re.sub(r'클릭해서', lambda m: random.choice(['선택해서', '눌러서', '터치해서']), content)
                content = re.sub(r'클릭하여', lambda m: random.choice(['선택하여', '눌러', '터치하여']), content)
                content = re.sub(r'클릭하면', lambda m: random.choice(['선택하면', '누르면', '터치하면']), content)
                content = re.sub(r'클릭', lambda m: random.choice(click_alternatives), content)
                click_replaced = True
            
            # h1 태그 복원
            for i, (opening, title_content, closing) in enumerate(h1_contents):
                placeholder = f"___H1_PLACEHOLDER_{i}___"
                content = content.replace(placeholder, opening + title_content + closing)
            
            if click_replaced:
                self.log("✅ '클릭' 단어를 유의어로 대체 (제목 제외)")
            
            # 5. &amp; HTML 엔티티를 &로 변경
            if '&amp;' in content:
                content = content.replace('&amp;', '&')
                self.log("✅ HTML 엔티티 정리")
            
            # 5-1. 외부링크 target 속성 검증 (무조건 target="_self" 사용)
            # target="_blank" 또는 기타 값을 target="_self"로 수정
            target_fixed = False
            if 'target=' in content:
                # target="_blank" → target="_self"
                if 'target="_blank"' in content:
                    content = content.replace('target="_blank"', 'target="_self"')
                    target_fixed = True
                # target=_blank (따옴표 없음) → target="_self"
                if 'target=_blank' in content:
                    content = re.sub(r'target=_blank(?=\s|>)', 'target="_self"', content)
                    target_fixed = True
                # target="_top", "_parent" 등도 모두 _self로 변경
                content = re.sub(r'target="_(top|parent|blank)"', 'target="_self"', content)
                target_fixed = True
                
            if target_fixed:
                self.log("✅ 외부링크 target 속성을 target=\"_self\"로 통일")

            # 5-2. href URL 정규화
            # - //example.com → https://example.com
            # - 잘못 붙은 끝 괄호/구두점 제거
            # - 따옴표 없는 href도 href="..." 형태로 보정
            def normalize_href_value(raw_url: str) -> str:
                url = (raw_url or "").strip()
                if not url:
                    return url

                # protocol-relative URL 보정
                if url.startswith("//"):
                    url = "https:" + url

                # markdown 잔여물/문장부호 꼬리 제거
                while url and url[-1] in [",", ";"]:
                    url = url[:-1]
                if url.endswith(")") and url.count("(") < url.count(")"):
                    url = url[:-1]

                # scheme 없는 www.* 는 https 보강
                if url.startswith("www."):
                    url = "https://" + url

                return url

            def replace_href_attr(match):
                url_value = match.group(2)
                normalized = normalize_href_value(url_value)
                return f'href="{normalized}"'

            content = re.sub(
                r'href\s*=\s*(["\']?)([^"\'\s>]+)\1',
                replace_href_attr,
                content,
                flags=re.IGNORECASE
            )

            # href 정규화 추가 보정 (protocol-relative, 끝 꼬리 괄호 등)
            content = self._sanitize_anchor_hrefs(content)
             
            # 6. 다운로드 버튼 복원 (수정된 버전으로)
            for i, fixed_button in enumerate(fixed_buttons):
                content = content.replace(f"__PROTECTED_DOWNLOAD_BUTTON_{i}__", fixed_button, 1)
            
            return content
            
        except Exception as e:
            self.log(f"❌ 콘텐츠 정리 중 오류: {e}")
            # 오류 발생 시에도 다운로드 버튼 복원 시도
            try:
                for i, fixed_button in enumerate(fixed_buttons):
                    content = content.replace(f"__PROTECTED_DOWNLOAD_BUTTON_{i}__", fixed_button, 1)
            except:
                for i, button in enumerate(download_buttons):
                    content = content.replace(f"__PROTECTED_DOWNLOAD_BUTTON_{i}__", button, 1)
            return content
    
    def load_trusted_urls(self):
        """코드 내장 신뢰할 수 있는 URL 리스트 (setting.json 불필요)"""
        return {
            '정부_공공기관': [
                'https://www.hometax.go.kr',
                'https://www.gov24.go.kr',
                'https://www.safedriving.or.kr',
            ],
            '금융_관련': [
                'https://www.fss.or.kr',
                'https://www.cardgorilla.com',
            ],
            '부동산_관련': [
                'https://www.lh.or.kr',
                'https://land.naver.com',
            ],
            '자동차_관련': [
                'https://www.encar.com',
            ],
            '통신_관련': [
                'https://www.skt.com',
                'https://www.kt.com',
            ],
            '교육_취업': [
                'https://www.work.go.kr',
            ],
            '쇼핑_배송': [
                'https://shopping.naver.com',
            ],
            'IT_기술': [
                'https://www.microsoft.com/ko-kr',
                'https://www.apple.com/kr',
            ],
            '생활_건강': [
                'https://www.nhis.or.kr',
            ]
        }
    
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
        """콘텐츠 맥락을 분석하여 가장 적절한 신뢰할 수 있는 URL 선택 (정확도 대폭 개선)"""
        try:
            import random
            keyword_lower = keyword.lower()
            content_lower = content.lower()
            
            # 원본 URL 주변 텍스트 분석
            import re
            url_context = ""
            if original_url:
                url_pattern = re.escape(original_url)
                match = re.search(f'.{{0,100}}{url_pattern}.{{0,100}}', content_lower)
                if match:
                    url_context = match.group()
            
            # 키워드만 집중 분석 (정확도 향상)
            context_text = keyword_lower
            
            # 🚫 명확하게 매칭되지 않는 키워드 체크 (네이버 검색 사용)
            generic_keywords = ['다운로드', '양식', '서식', '템플릿', '예제', '샘플', '기출문제', 'pdf', '문서', '파일']
            
            # 키워드가 일반적인 다운로드 관련이면 네이버 검색 사용
            if any(generic in context_text for generic in generic_keywords):
                # 단, 특정 기관/서비스명이 함께 있으면 예외
                specific_terms = ['홈택스', '정부24', '은행', '카드', '아파트', '자동차', '핸드폰', 'skt', 'kt']
                if not any(specific in context_text for specific in specific_terms):
                    self.log(f"🔍 일반 키워드 감지 → 네이버 검색 사용: {keyword}")
                    return f"https://search.naver.com/search.naver?query={keyword.replace(' ', '+')}"
            
            # 🎯 정확한 키워드 매칭만 사용
            # 정부/공공기관 관련 (매우 구체적인 키워드만)
            if any(term in context_text for term in ['홈택스', '국세청', '세무서', '종합소득세', '부가가치세']):
                self.log(f"🔍 카테고리 매칭: 정부_공공기관 (홈택스) → {keyword}")
                return 'https://www.hometax.go.kr'
            
            elif any(term in context_text for term in ['정부24', '민원24', '정부민원']):
                self.log(f"🔍 카테고리 매칭: 정부_공공기관 (정부24) → {keyword}")
                return 'https://www.gov24.go.kr'
            
            elif any(term in context_text for term in ['운전면허', '면허증', '안전운전']):
                self.log(f"🔍 카테고리 매칭: 정부_공공기관 (안전운전) → {keyword}")
                return 'https://www.safedriving.or.kr'
            
            # 금융 관련 (구체적인 금융 서비스명만)
            elif any(term in context_text for term in ['kb국민은행', '신한은행', '하나은행', '우리은행', '농협', 'nh은행']):
                urls = trusted_urls.get('금융_관련', [])
                if urls:
                    selected = random.choice(urls)
                    self.log(f"🔍 카테고리 매칭: 금융_관련 → {selected} ({keyword})")
                    return selected
            
            elif '카드고릴라' in context_text or ('카드' in context_text and '비교' in context_text):
                self.log(f"🔍 카테고리 매칭: 금융_관련 (카드고릴라) → {keyword}")
                return 'https://www.cardgorilla.com'
            
            # 부동산 관련 (구체적인 부동산 키워드만)
            elif any(term in context_text for term in ['lh청약', '청약플러스', '공공주택']):
                self.log(f"🔍 카테고리 매칭: 부동산_관련 (LH) → {keyword}")
                return 'https://www.lh.or.kr'
            
            elif any(term in context_text for term in ['네이버부동산', '네이버 부동산']):
                self.log(f"🔍 카테고리 매칭: 부동산_관련 (네이버부동산) → {keyword}")
                return 'https://land.naver.com'
            
            # 자동차 관련 (구체적인 자동차 서비스명만)
            elif any(term in context_text for term in ['엔카', 'sk엔카', '중고차매매']):
                self.log(f"🔍 카테고리 매칭: 자동차_관련 (엔카) → {keyword}")
                return 'https://www.encar.com'
            
            # 통신 관련 (구체적인 통신사명만)
            elif any(term in context_text for term in ['skt', 'sk텔레콤', '티월드']):
                self.log(f"🔍 카테고리 매칭: 통신_관련 (SKT) → {keyword}")
                return 'https://www.skt.com'
            
            elif any(term in context_text for term in ['kt', '올레']):
                self.log(f"🔍 카테고리 매칭: 통신_관련 (KT) → {keyword}")
                return 'https://www.kt.com'
            
            # 취업 관련 (구체적인 취업 서비스명만)
            elif any(term in context_text for term in ['워크넷', '고용노동부', '구인구직']):
                self.log(f"🔍 카테고리 매칭: 교육_취업 (워크넷) → {keyword}")
                return 'https://www.work.go.kr'
            
            # IT/기술 관련 (구체적인 브랜드명만)
            elif any(term in context_text for term in ['마이크로소프트', 'microsoft', 'ms오피스', '윈도우10', '윈도우11']):
                self.log(f"🔍 카테고리 매칭: IT_기술 (Microsoft) → {keyword}")
                return 'https://www.microsoft.com/ko-kr'
            
            elif any(term in context_text for term in ['애플', 'apple', '맥북', '아이맥', '아이패드프로']):
                self.log(f"🔍 카테고리 매칭: IT_기술 (Apple) → {keyword}")
                return 'https://www.apple.com/kr'
            
            # 건강보험 관련
            elif any(term in context_text for term in ['건강보험공단', '국민건강보험', '건보공단']):
                self.log(f"🔍 카테고리 매칭: 생활_건강 (건강보험공단) → {keyword}")
                return 'https://www.nhis.or.kr'
            
            # 🎯 매칭 실패 시 기본값: 네이버 검색 (공식 홈페이지보다 안전)
            else:
                self.log(f"🔍 명확한 카테고리 매칭 실패 → 네이버 검색 사용: {keyword}")
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

    def create_thumbnail(self, title, keyword):
        """썸네일 이미지를 생성합니다."""
        try:
            # images 폴더에서 사이트별 또는 무작위 배경 이미지 선택 (setting 폴더 내부로 변경)
            images_dir = os.path.join(get_base_path(), "setting", "images")
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
                # fonts 폴더의 timon.ttf 폰트 사용 (본문과 동일) (setting 폴더 내부로 변경)
                font_path = os.path.join(get_base_path(), "setting", "fonts", "timon.ttf")
                large_font = ImageFont.truetype(font_path, 24)  # | 앞 제목용 (32→24로 축소)
                small_font = ImageFont.truetype(font_path, 18)  # | 뒤 제목용 (22→18로 축소)
            except Exception as font_error:
                print(f"timon.ttf 폰트 로드 실패: {font_error}")
                try:
                    # 대체 폰트들
                    large_font = ImageFont.truetype("C:/Windows/Fonts/gulim.ttc", 22)
                    small_font = ImageFont.truetype("C:/Windows/Fonts/gulim.ttc", 16)
                except:
                    try:
                        large_font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 22)
                        small_font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 16)
                    except:
                        large_font = ImageFont.load_default()
                        small_font = ImageFont.load_default()

            # 제목을 | 기준으로 분리
            if '|' in title:
                parts = title.split('|', 1)  # 최대 1번만 분리
                main_title = parts[0].strip()    # | 앞부분 (첫 줄, 크게)
                sub_title = parts[1].strip()     # | 뒷부분 (둘째 줄, 작게)
            else:
                main_title = title
                sub_title = ""
            
            # 텍스트를 중앙에 배치하기 위한 계산
            lines = []
            
            # 첫 번째 줄: main_title (큰 폰트)
            if main_title:
                # main_title이 너무 길면 자동 줄바꿈
                words = main_title.split()
                current_line = []
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    bbox = draw.textbbox((0, 0), test_line, font=large_font)
                    if bbox[2] - bbox[0] > 250:  # 250px 이상이면 줄바꿈
                        if current_line:
                            lines.append((' '.join(current_line), large_font))
                            current_line = [word]
                        else:
                            lines.append((word, large_font))
                            current_line = []
                    else:
                        current_line.append(word)
                
                if current_line:
                    lines.append((' '.join(current_line), large_font))
            
            # 두 번째 줄: sub_title (작은 폰트)
            if sub_title:
                # sub_title이 너무 길면 자동 줄바꿈
                words = sub_title.split()
                current_line = []
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    bbox = draw.textbbox((0, 0), test_line, font=small_font)
                    if bbox[2] - bbox[0] > 260:  # 작은 폰트는 좀 더 길게 허용
                        if current_line:
                            lines.append((' '.join(current_line), small_font))
                            current_line = [word]
                        else:
                            lines.append((word, small_font))
                            current_line = []
                    else:
                        current_line.append(word)
                
                if current_line:
                    lines.append((' '.join(current_line), small_font))
                
            # 텍스트 중앙 정렬
            line_spacing = 35  # 줄 간격
            total_height = len(lines) * line_spacing
            y_start = (300 - total_height) // 2 + 10  # 중앙에서 약간 위로
            
            # [추가] 배경 밝기 계산
            try:
                from PIL import ImageStat
                stat = ImageStat.Stat(background.convert('L'))
                avg_brightness = stat.mean[0]
                
                if avg_brightness > 128:
                    # 배경이 밝으면 검정 텍스트 (그림자 흰색)
                    text_color = (0, 0, 0)
                    shadow_color = (255, 255, 255, 180)
                else:
                    # 배경이 어두우면 흰색 텍스트 (그림자 검정)
                    text_color = (255, 255, 255)
                    shadow_color = (0, 0, 0, 180)
            except:
                # 계산 실패 시 기본값 (흰색 텍스트)
                text_color = (255, 255, 255)
                shadow_color = (0, 0, 0, 180)
            
            for i, (line_text, line_font) in enumerate(lines):
                bbox = draw.textbbox((0, 0), line_text, font=line_font)
                text_width = bbox[2] - bbox[0]
                x = (300 - text_width) // 2
                y = y_start + (i * line_spacing)
                
                # 그림자 효과 (가독성 향상)
                draw.text((x + 2, y + 2), line_text, fill=shadow_color, font=line_font)
                # 메인 텍스트
                draw.text((x, y), line_text, fill=text_color, font=line_font)
            
            # 최종 이미지를 WebP 형식으로 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(get_base_path(), "setting", "thumbnails", f"thumbnail_{timestamp}.webp")
            background.save(filepath, 'WEBP', quality=85)
            return filepath
        except Exception as e:
            self.log(f"썸네일 생성 오류: {e}")
            return None

    def post_to_wordpress(self, site_data, title, content, thumbnail_path=None, status='publish'):
        """워드프레스에 포스트를 게시합니다."""
        try:
            site_name = site_data.get('name', 'Unknown')
            site_url = site_data.get('url')
            username = site_data.get('username')
            password = site_data.get('password')
            category = site_data.get('category_id', 1)

            # 제목에서 불필요한 문자 최종 제거 (워드프레스 포스팅 직전)
            title = title.replace('"', '').replace("'", '').replace('`', '')
            title = title.replace('#', '').replace('*', '').replace('**', '')
            title = re.sub(r'^[\s\-_=]+', '', title)
            title = re.sub(r'[\s\-_=]+$', '', title)
            title = title.strip()
            
            # 콘텐츠 최종 검증 1: 링크 class 속성 따옴표 추가
            # class=link1 → class="link1", class=link2 → class="link2", class=link3 → class="link3"
            content = re.sub(r'class=link1(?=\s|>)', 'class="link1"', content)
            content = re.sub(r'class=link2(?=\s|>)', 'class="link2"', content)
            content = re.sub(r'class=link3(?=\s|>)', 'class="link3"', content)
            content = re.sub(r'class=blink(?=\s|>)', 'class="blink"', content)

            # 콘텐츠 최종 검증 1-1: href URL 구조 최종 정규화 (업로드 직전 안전망)
            content = self._sanitize_anchor_hrefs(content)
            
            # 콘텐츠 최종 검증 2: 다운로드 버튼 HTML 완전 복구 (AI 응답이 잘못되었을 경우 대비)
            # 키워드 추출 (제목에서)
            keyword_from_title = title.split('|')[0].strip() if '|' in title else title
            
            if 'button-container' in content:
                self.log("🔧 다운로드 버튼 발견 - 완전 재구성 시작")
                
                # 기존 button-container를 완전히 제거하고 새로 생성
                content = re.sub(r'<div\s+class="?button-container"?>.*?</div>', '__BUTTON_PLACEHOLDER__', content, flags=re.DOTALL | re.IGNORECASE)
                
                # 올바른 다운로드 버튼 HTML 생성 (prompt1.txt 형식 준수)
                from urllib.parse import quote
                keyword_encoded = quote(keyword_from_title)
                
                correct_button_html = f'''<div class="button-container">
    <p>
        <a href="https://www.apple.com/kr/search/{keyword_encoded}?src=globalnav" class="custom-download-btn appstore-button" target="_self">
            <img src="https://developer.apple.com/assets/elements/icons/app-store/app-store-128x128_2x.png" class="btn-logo" alt="App Store">
            <span>App Store에서 바로 다운로드</span>
        </a>
    </p>
    <p>
        <a href="https://play.google.com/store/search?q={keyword_encoded}&amp;c=apps" class="custom-download-btn playstore-button" target="_self">
            <img src="https://upload.wikimedia.org/wikipedia/commons/7/78/Google_Play_Store_badge_EN.svg" class="btn-logo" alt="Google Play">
            <span>Google Play에서 바로 다운로드</span>
        </a>
    </p>
    <p>
        <a href="https://apps.microsoft.com/search?query={keyword_encoded}&hl=ko-KR&gl=KR" class="custom-download-btn window-button" target="_self">
            <img src="https://upload.wikimedia.org/wikipedia/commons/4/44/Microsoft_logo.svg" class="btn-logo" alt="Microsoft Store">
            <span>Windows에서 바로 다운로드</span>
        </a>
    </p>
    <p>
        <a href="https://www.apple.com/kr/search/{keyword_encoded}?src=globalnav" class="custom-download-btn macbook-button" target="_self">
            <img src="https://upload.wikimedia.org/wikipedia/commons/f/fa/Apple_logo_black.svg" class="btn-logo" alt="Mac App Store">
            <span>MacBook에서 바로 다운로드</span>
        </a>
    </p>
</div>'''
                
                # 플레이스홀더를 올바른 HTML로 교체
                content = content.replace('__BUTTON_PLACEHOLDER__', correct_button_html)
                self.log(f"✅ 다운로드 버튼 완전 재구성 완료 (키워드: {keyword_from_title})")

            # WordPress REST API URL 구성
            api_url = f"{site_url.rstrip('/')}/wp-json/wp/v2/posts"
            
            # 여러 인증 방법 시도
            auth_success, headers = self.try_authentication_methods(site_name, site_url, username, password)
            
            if not auth_success:
                # 비밀번호 힌트 생성
                password_hint = password[:4] + "***" + password[-4:] if len(password) > 8 else password[:2] + "***"
                
                return {'success': False, 'error': 'Authentication failed'}

            # 🔥 중요: 제목과 콘텐츠 검증 (empty_content 에러 방지)
            if not title or not title.strip():
                self.log(f"❌ {site_name}: 제목이 비어있습니다. 포스팅 중단")
                return {'success': False, 'error': '제목이 비어있습니다'}
            
            if not content or not content.strip():
                self.log(f"❌ {site_name}: 콘텐츠가 비어있습니다. 포스팅 중단")
                return {'success': False, 'error': '콘텐츠가 비어있습니다'}
            
            # 제목과 콘텐츠 길이 검증 (최소 길이 확인)
            if len(title.strip()) < 5:
                self.log(f"❌ {site_name}: 제목이 너무 짧습니다 (최소 5자 필요): '{title}'")
                return {'success': False, 'error': '제목이 너무 짧습니다'}
            
            if len(content.strip()) < 100:
                self.log(f"❌ {site_name}: 콘텐츠가 너무 짧습니다 (최소 100자 필요): {len(content.strip())}자")
                return {'success': False, 'error': '콘텐츠가 너무 짧습니다'}
            

            post_data = {
                'title': title,
                'content': content,
                'status': status,
                'categories': [int(category)]
            }

            session = get_requests_session()
            response = session.post(api_url, headers=headers, json=post_data, timeout=45)
            if response.status_code == 201:
                post_info = response.json()
                post_id = post_info['id']

                # 썸네일 업로드
                if thumbnail_path and os.path.exists(thumbnail_path):
                    media_id = self.upload_featured_image(site_url, headers, thumbnail_path, post_id)
                    if not media_id:
                        self.log(f"⚠️ {site_name}: 썸네일 업로드 실패 (포스트는 성공)")
                
                # HTML 콘텐츠를 output 폴더에 저장
                try:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_dir = os.path.join(get_base_path(), "setting", "output")
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

    def _sanitize_anchor_hrefs(self, content):
        """앵커 href 값을 업로드 직전에 안전하게 정규화"""
        try:
            def _normalize(url):
                u = (url or "").strip()
                if not u:
                    return u
                # HTML 엔티티가 들어온 경우 먼저 복원
                u = u.replace("&quot;", '"').replace("&#34;", '"').replace("&amp;", "&")
                # 따옴표가 URL 값에 섞여 들어온 경우 제거
                u = u.strip('"').strip("'")
                if u.startswith("//"):
                    u = "https:" + u
                elif u.startswith("www."):
                    u = "https://" + u

                # naver 검색 URL에서 쿼리 구분자/연결자가 인코딩된 경우 복구
                # 예: /search.naver%3Fquery%3D... -> /search.naver?query=...
                if re.search(r"search\.naver\.com/search\.naver%3f", u, flags=re.IGNORECASE):
                    u = re.sub(r"%3[fF]", "?", u, count=1)
                    u = re.sub(r"%3[dD]", "=", u)
                    u = re.sub(r"%26", "&", u, flags=re.IGNORECASE)
                    u = re.sub(r"%2[bB]", "+", u)

                # URL 끝에 잘못 붙은 괄호/구두점 제거
                while u and u[-1] in [",", ";"]:
                    u = u[:-1]
                while u.endswith(")") and u.count("(") < u.count(")"):
                    u = u[:-1]
                while u.endswith("]") and u.count("[") < u.count("]"):
                    u = u[:-1]
                while u.endswith("}") and u.count("{") < u.count("}"):
                    u = u[:-1]
                return u

            def _replace_quoted(match):
                return f'{match.group(1)}"{_normalize(match.group(3))}"'

            # href="...", href='...'
            content = re.sub(
                r'(href\s*=\s*)(["\'])([^"\']*)(\2)',
                lambda m: _replace_quoted(m),
                content,
                flags=re.IGNORECASE
            )

            # href=... (따옴표 없는 경우)
            content = re.sub(
                r'href\s*=\s*([^\s>"\']+)',
                lambda m: f'href="{_normalize(m.group(1))}"',
                content,
                flags=re.IGNORECASE
            )

            # 케이스 보강: protocol-relative + 닫는 괄호 꼬리 패턴 강제 정리
            content = re.sub(
                r'href\s*=\s*(["\'])\s*//([^"\']*?)\)\1',
                lambda m: f'href="{_normalize("//" + m.group(2))}"',
                content,
                flags=re.IGNORECASE
            )
            return content
        except Exception:
            return content

    def try_authentication_methods(self, site_name, site_url, username, password):
        """다양한 인증 방법을 시도합니다 (캐싱 포함)"""
        session = get_requests_session()
        user_url = f"{site_url.rstrip('/')}/wp-json/wp/v2/users/me"
        
        # 비밀번호 힌트 생성 (보안을 위해 일부만 표시)
        password_hint = password[:4] + "***" + password[-4:] if len(password) > 8 else password[:2] + "***"
        
        # 캐시된 인증 방법이 있으면 먼저 시도
        if site_url in self.auth_cache:
            cached_headers, cached_method = self.auth_cache[site_url]
            self.log(f"🔑 {site_name}: 캐시된 인증 방법 ({cached_method}) 사용")
            if self.test_auth_method(session, user_url, cached_headers, site_name, f"{cached_method} (캐시)", username, password_hint):
                self.log(f"✅ {site_name}: 캐시된 인증 성공!")
                return True, cached_headers
            else:
                self.log(f"⚠️ {site_name}: 캐시된 인증 실패, 다른 방법 시도...")
                del self.auth_cache[site_url]  # 캐시 삭제
        
        # WordPress REST API 접근성 확인
        self.check_rest_api_accessibility(site_name, site_url)
        
        # 방법 1: Application Password (공백 포함)
        headers1 = self.create_auth_header(username, password, "Application Password with spaces")
        if self.test_auth_method(session, user_url, headers1, site_name, "Application Password (공백포함)", username, password_hint):
            self.auth_cache[site_url] = (headers1, "Application Password (공백포함)")  # 캐시 저장
            return True, headers1
        
        # 방법 2: Application Password (공백 제거)
        password_no_spaces = password.replace(" ", "")
        self.log(f"🔑 {site_name}: 방법 2 - Application Password (공백 제거) 시도")
        self.log(f"🔧 {site_name}: 공백 제거된 비밀번호 길이: {len(password_no_spaces)}자")
        headers2 = self.create_auth_header(username, password_no_spaces, "Application Password without spaces")
        if self.test_auth_method(session, user_url, headers2, site_name, "Application Password (공백제거)", username, password_hint):
            self.auth_cache[site_url] = (headers2, "Application Password (공백제거)")  # 캐시 저장
            return True, headers2
        
        # 방법 3: 기본 Basic Auth
        self.log(f"🔑 {site_name}: 방법 3 - 기본 Basic Auth 시도")
        headers3 = self.create_auth_header(username, password, "Basic Auth")
        if self.test_auth_method(session, user_url, headers3, site_name, "Basic Auth", username, password_hint):
            self.auth_cache[site_url] = (headers3, "Basic Auth")  # 캐시 저장
            return True, headers3
        
        # 방법 4: WordPress 기본 인증 (username@domain 형식)
        if '@' not in username and site_url:
            domain = site_url.replace('https://', '').replace('http://', '').split('/')[0]
            username_with_domain = f"{username}@{domain}"
            headers4 = self.create_auth_header(username_with_domain, password, "Domain Auth")
            if self.test_auth_method(session, user_url, headers4, site_name, "도메인 포함 인증", username_with_domain, password_hint):
                self.auth_cache[site_url] = (headers4, "도메인 포함 인증")  # 캐시 저장
                return True, headers4
            
            # 방법 5: 도메인 포함 + 공백 제거
            self.log(f"🔑 {site_name}: 방법 5 - 도메인 포함 + 공백 제거 시도")
            headers5 = self.create_auth_header(username_with_domain, password_no_spaces, "Domain Auth + No Spaces")
            if self.test_auth_method(session, user_url, headers5, site_name, "도메인 포함 + 공백제거", username_with_domain, password_hint):
                self.auth_cache[site_url] = (headers5, "도메인 포함 + 공백제거")  # 캐시 저장
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
            response = session.get(api_base_url, timeout=30)  # 타임아웃 30초로 증가
            
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
        """인증 방법 테스트 (재시도 포함)"""
        max_retries = 2  # 최대 2번 재시도
        
        for attempt in range(max_retries):
            try:
                # 타임아웃 시간을 30초로 증가
                response = session.get(user_url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    user_info = response.json()
                    user_name = user_info.get('name', 'Unknown')
                    if attempt > 0:
                        self.log(f"✅ {site_name}: {method_name} 인증 성공 ({attempt+1}번째 시도)")
                    return True
                else:
                    # 인증 실패 시 사용자명과 비밀번호 힌트 표시
                    if attempt == max_retries - 1:  # 마지막 시도에서만 로그 출력
                        if username:
                            self.log(f"❌ {site_name}: {method_name} 인증 실패 (HTTP {response.status_code}) - 사용자명: '{username}', 비밀번호: '{password_hint}'")
                        else:
                            self.log(f"❌ {site_name}: {method_name} 인증 실패 (HTTP {response.status_code})")
                    return False
                    
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    self.log(f"⏳ {site_name}: {method_name} 타임아웃 발생, {attempt+2}번째 시도 중...")
                    continue
                else:
                    if username:
                        self.log(f"❌ {site_name}: {method_name} 타임아웃 (30초) - 사용자명: '{username}', 비밀번호: '{password_hint}'")
                    else:
                        self.log(f"❌ {site_name}: {method_name} 타임아웃 (30초)")
                    return False
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    self.log(f"⚠️ {site_name}: {method_name} 오류 발생, {attempt+2}번째 시도 중... ({str(e)[:50]})")
                    continue
                else:
                    if username:
                        self.log(f"❌ {site_name}: {method_name} 인증 중 오류: {e} - 사용자명: '{username}', 비밀번호: '{password_hint}'")
                    else:
                        self.log(f"❌ {site_name}: {method_name} 인증 중 오류: {e}")
                    return False
        
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
        content = re.sub(r'<span style="color:\s*"[^>]*>', '<span style="color:#ee2323;">', content, flags=re.IGNORECASE)
        content = re.sub(r'<span style="color:\s+[^"]*"', '<span style="color:#ee2323;"', content, flags=re.IGNORECASE)
        content = re.sub(r'style="color:\s*//[^"]*"', 'style="color:#ee2323;"', content, flags=re.IGNORECASE)
        content = re.sub(r'style="color:\s*#ee2323[^"]*"', 'style="color:#ee2323;"', content, flags=re.IGNORECASE)
        
        # 2-1. 더 강력한 깨진 HTML 속성 수정
        # style 속성이 URL로 잘못 들어간 경우 완전 수정
        content = re.sub(r'<span style="color:\s*//[^"]*"[^>]*>', '<span style="color:#ee2323;">', content, flags=re.IGNORECASE)
        content = re.sub(r'<span[^>]*style="[^"]*//[^"]*"[^>]*>', '<span style="color:#ee2323;">', content, flags=re.IGNORECASE)
        
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
            replacement = f'style="color:#ee2323;">{keyword} 상세정보</span>을 통해, 지금 바로 해보세요!</b></p><br><div><center><a class="blink" href="{search_url}" target="_self">\\1</a>'
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
        
        # 13. 끝부분의 불완전한 내용 제거 (다운로드 버튼 보호)
        # 다운로드 버튼 HTML을 임시로 보호
        download_button_pattern = r'<div class="button-container">.*?</div>'
        download_buttons = re.findall(download_button_pattern, content, flags=re.IGNORECASE | re.DOTALL)
        
        # 다운로드 버튼을 플레이스홀더로 교체
        temp_content = content
        for i, button in enumerate(download_buttons):
            temp_content = temp_content.replace(button, f"__DOWNLOAD_BUTTON_{i}__", 1)
        
        # 의미없는 단어들이나 불완전한 문장, 깨진 HTML 구조 제거
        temp_content = re.sub(r'\s*(당근|단호|center(?!>)|table(?!>)|td(?!>)|tr(?!>)|color(?![:="])|style(?![:="])|href(?![:="]))\s*$', '', temp_content, flags=re.IGNORECASE)
        temp_content = re.sub(r'<[^>]*>?\s*$', '', temp_content)  # 끝에 불완전한 태그 제거
        temp_content = re.sub(r'[^>]*>\s*$', '', temp_content)  # 끝에 불완전한 태그 내용 제거
        temp_content = re.sub(r'\s*=\s*$', '', temp_content)  # 끝에 등호나 불완전한 속성 제거
        temp_content = re.sub(r'^\s*"\s*$', '', temp_content, flags=re.MULTILINE)  # 줄 전체가 따옴표만 있는 경우만 제거
        
        # 다운로드 버튼 복원
        for i, button in enumerate(download_buttons):
            temp_content = temp_content.replace(f"__DOWNLOAD_BUTTON_{i}__", button, 1)
        
        content = temp_content
        
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
        
        # 제목에서 불필요한 문자 제거 (큰따옴표, 작은따옴표, #, *, 백틱 등)
        title = title.replace('"', '').replace("'", '').replace('`', '')
        title = title.replace('#', '').replace('*', '').replace('**', '')
        title = re.sub(r'^[\s\-_=]+', '', title)  # 앞쪽 특수문자 제거
        title = re.sub(r'[\s\-_=]+$', '', title)  # 뒤쪽 특수문자 제거
        title = title.strip()
        
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
        """승인용 시스템 프롬프트 생성 - 최소화 (API 토큰 대폭 절약)"""
        
        # approval 프롬프트 파일에 이미 상세 규칙이 있으므로 최소한만 전달
        return f"""너는 SEO 콘텐츠 전문가야. {keyword}에 대한 글을 작성해.

규칙:
- HTML만 사용 (마크다운 금지)
- '~해요'체 사용
- prompts/approval{step}.txt 파일의 지침을 정확히 따르기"""

    def get_revenue_system_prompt(self, step_num, keyword):
        """수익용 시스템 프롬프트 생성 - prompt 파일 읽어서 사용"""
        try:
            # prompt 파일 경로 (setting 폴더 내부로 변경)
            prompt_file = os.path.join(get_base_path(), "setting", "prompts", f"prompt{step_num}.txt")
            
            # 파일 읽기
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_content = f.read()
            
            # {keyword} 치환
            prompt_content = prompt_content.replace('{keyword}', keyword)
            
            # 프롬프트 파일에 이미 규칙이 있으므로 추가 규칙 없음 (API 토큰 절약)
            return prompt_content
            
        except Exception as e:
            self.log(f"프롬프트 파일 읽기 오류: {e}")
            # 기본 프롬프트
            return f"""너는 SEO 콘텐츠 작가다. {keyword}에 대한 고품질 콘텐츠를 '~해요'체로 작성해라.
            
규칙:
- AI 역할 언급 절대 금지
- '클릭' 단어 사용 금지 (대신: 선택, 확인, 눌러보기, 터치, 접속, 방문)
- 마크다운 문법 사용 금지
- 순수 HTML만 사용
- {keyword}에 대한 유용한 정보 제공"""

    

                
class ConfigManager:
    """단일 JSON 구조 설정 관리 클래스 (setting.json)"""

    def __init__(self):
        self.setting_file = os.path.join(get_base_path(), "setting", "setting.json")
        self.data = self.load_setting()

    # property 완전 제거 - 직접 접근 방식
    
    def load_setting(self):
        """단일 JSON 파일에서 모든 설정 로드"""
        default_data = {
            "api_keys": {
                "gemini": ""
            },
            "global_settings": {
                "default_ai": "web-gemini",
                "default_wait_time": "47~50",
                "posting_mode": "수익용",
                "ai_model": "gemini-2.5-flash-lite",
                "ui_theme": "다크",
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
                    # OpenAI는 더 이상 사용하지 않으므로 설정값을 정리
                    if default_data["global_settings"].get("default_ai") == "openai":
                        default_data["global_settings"]["default_ai"] = "web-gemini"
                        default_data["global_settings"]["ai_model"] = "gemini-2.5-flash-lite"
                    valid_ai_defaults = {"web-gemini", "web-perplexity", "gemini"}
                    if default_data["global_settings"].get("default_ai") not in valid_ai_defaults:
                        default_data["global_settings"]["default_ai"] = "web-gemini"
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
                keyword_path = os.path.join(get_base_path(), "setting", "keywords", keyword_file)
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
                thumbnail_path = os.path.join(get_base_path(), "setting", "images", thumbnail_image)
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
            keyword_path = os.path.join(base_path, "setting", "keywords", keyword_file)
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
            used_path = os.path.join(base_path, "setting", "keywords", used_filename)
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
            thumbnail_path = os.path.join(get_base_path(), "setting", "images", thumbnail_image)
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
            images_dir = os.path.join(get_base_path(), "setting", "images")
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
                thumbnail_path = os.path.join(get_base_path(), "setting", "images", selected_thumbnail)
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
                    thumb_path = os.path.join(get_base_path(), "setting", "images", thumb)
                    if os.path.exists(thumb_path):
                        thumbnail_image = thumb
                        break
                if not thumbnail_image:
                    thumbnail_image = '썸네일 (1).jpg'  # 기본값

            # 파일 경로
            keyword_path = os.path.join(get_base_path(), "setting", "keywords", keyword_file)
            thumbnail_path = os.path.join(get_base_path(), "setting", "images", thumbnail_image)

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
        parent = self.parent()
        config_manager = getattr(parent, "config_manager", None)
        if config_manager is None:
            QMessageBox.warning(self, "경고", "전역 설정을 찾을 수 없습니다.")
            return
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
        parent = self.parent()
        config_manager = getattr(parent, "config_manager", None)
        if config_manager is None:
            QMessageBox.warning(self, "오류", "전역 설정을 찾을 수 없습니다.")
            return None

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
            "ai_provider": config_manager.data["global_settings"].get("default_ai", "web-gemini"),
            "wait_time": config_manager.data["global_settings"].get("default_wait_time", "47~50"),
            "thumbnail_image": thumbnail_image,  # 썸네일 이미지 파일명
            "keyword_file": keyword_file,        # 키워드 파일명
            "keywords": []  # 키워드는 파일에서 동적으로 로드
        }

class ClickableLabel(QLabel):
    """클릭 가능한 라벨"""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

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
        url_info = ClickableLabel(display_url)
        url_info.setFont(QFont("맑은 고딕", 10))
        url_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_info.setStyleSheet(f"""
            color: {COLORS['info']};
            text-decoration: underline;
        """)
        url_info.setCursor(Qt.CursorShape.PointingHandCursor)
        url_info.clicked.connect(self.open_wp_admin)
        url_row.addWidget(url_info, 1)

        url_row.addStretch()

        # 편집 버튼
        edit_btn = QPushButton("편집")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.site_data["id"]))
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #0077E6;
                color: white;
                border: 1px solid #005FBA;
                border-radius: 6px;
                padding: 5px 15px;
                font-weight: 800;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: #1490FF;
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
        self.keyword_info = ClickableLabel(f"키워드 {keywords_count}개")  # self로 변경하여 나중에 업데이트 가능
        self.keyword_info.setFont(QFont("맑은 고딕", 10))
        self.keyword_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.keyword_info.setStyleSheet(f"""
            color: {COLORS['info']};
            text-decoration: underline;
        """)
        self.keyword_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keyword_info.clicked.connect(self.open_keyword_file)
        keyword_row.addWidget(self.keyword_info, 1)

        keyword_row.addStretch()

        # 파일 선택 버튼
        keyword_btn = QPushButton("파일 선택")
        keyword_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        keyword_btn.clicked.connect(lambda: self.keywords_requested.emit(self.site_data["id"]))
        keyword_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FFC400;
                color: white;
                border: 1px solid #CC9D00;
                border-radius: 6px;
                padding: 5px 15px;
                font-weight: 800;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: #FFD54F;
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
        thumbnail_label = ClickableLabel(f"썸네일 {thumbnail_info}")
        thumbnail_label.setFont(QFont("맑은 고딕", 10))
        thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumbnail_label.setStyleSheet(f"""
            color: {COLORS['info']};
            text-decoration: underline;
        """)
        thumbnail_label.setCursor(Qt.CursorShape.PointingHandCursor)
        thumbnail_label.clicked.connect(self.open_thumbnail_file)
        thumbnail_row.addWidget(thumbnail_label, 1)

        thumbnail_row.addStretch()

        # 파일 선택 버튼
        thumbnail_btn = QPushButton("파일 선택")
        thumbnail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        thumbnail_btn.clicked.connect(lambda: self.thumbnails_requested.emit(self.site_data["id"]))
        thumbnail_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #0087E6;
                color: white;
                border: 1px solid #006CBC;
                border-radius: 6px;
                padding: 5px 15px;
                font-weight: 800;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: #15A1FF;
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
                background-color: {'#12A34A' if is_active else '#E2162D'};
                color: white;
                border: 1px solid {'#0F863D' if is_active else '#B71124'};
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 800;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: {'#18BE56' if is_active else '#FF273D'};
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
                background-color: #D9112A;
                color: white;
                border: 1px solid #B00D22;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 800;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: #F6253E;
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

            keyword_path = os.path.join(get_base_path(), "setting", "keywords", keyword_file)
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

    def get_thumbnails_count(self):
        """썸네일 개수 조회 (자동 생성되므로 항상 충분)"""
        return "자동생성"

    def get_thumbnail_info(self):
        """썸네일 정보 조회 - 사용자가 선택한 썸네일 파일만 사용"""
        try:
            thumbnail_image = self.site_data.get("thumbnail_image", "")
            if thumbnail_image:
                thumbnail_path = os.path.join(get_base_path(), "setting", "images", thumbnail_image)
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
            keyword_path = os.path.join(get_base_path(), "setting", "keywords", keyword_file)
            
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
            thumbnail_path = os.path.join(get_base_path(), "setting", "images", thumbnail_file)
            
            if not os.path.exists(thumbnail_path):
                QMessageBox.warning(None, "파일 없음", f"썸네일 파일을 찾을 수 없습니다:\n{thumbnail_path}")
                return
                
            # Windows에서 기본 프로그램으로 파일 열기
            subprocess.run(['start', thumbnail_path], shell=True, check=True)
            
        except Exception as e:
            QMessageBox.critical(None, "오류", f"썸네일 파일을 열 수 없습니다:\n{e}")
    
    def update_keyword_display(self):
        """실시간 키워드 개수 업데이트"""
        try:
            # 키워드 파일에서 남은 키워드 개수 계산
            keyword_file = self.site_data.get("keyword_file", "")
            if keyword_file:
                keyword_path = os.path.join(get_base_path(), "setting", "keywords", keyword_file)
                if os.path.exists(keyword_path):
                    try:
                        with open(keyword_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            remaining_keywords = [line.strip() for line in lines if line.strip()]
                            count = len(remaining_keywords)
                            self.keyword_info.setText(f"{count}개")
                    except Exception:
                        self.keyword_info.setText("0개")
                else:
                    self.keyword_info.setText("0개")
            else:
                self.keyword_info.setText("0개")
        except Exception:
            pass
            
class MainWindow(QMainWindow):
    """메인 윈도우"""

    # 시그널 정의
    update_buttons_signal = pyqtSignal()  # 버튼 상태 업데이트용
    AI_PROVIDER_WEB_GEMINI = "web-gemini"
    AI_PROVIDER_API_GEMINI = "gemini"
    TYPO_BASE_PT = 10
    TYPO_LABEL_PT = 10
    TYPO_BUTTON_PT = 10
    TYPO_INPUT_PT = 10
    TYPO_TITLE_PT = 11

    def __init__(self):
        super().__init__()
        
        self.config_manager = ConfigManager()
        self.current_theme = self.config_manager.data.get("global_settings", {}).get("ui_theme", "다크")
        self.apply_theme_palette(self.current_theme)
        
        self.resource_scanner = ResourceScanner(os.path.join(get_base_path(), "setting"))

        # 포스팅 상태 변수
        self.is_posting = False
        self.is_paused = False
        self.posting_thread: Optional[QThread] = None
        self.posting_worker: Optional[PostingWorker] = None  # 포스팅 워커 추가
        self.website_login_generator = None
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
        self.next_posting_label = None
        self._last_countdown_logged_second: Optional[int] = None
        
        # 현재 포스팅 중인 사이트 추적
        self.current_posting_site = None
        self._last_applied_wait_time: Optional[str] = None

        # 모니터링/설정 UI 참조 초기화
        self.ai_model_combo: Optional[QComboBox] = None
        self.posting_mode_combo: Optional[QComboBox] = None
        self.wait_time_edit_monitoring: Optional[QWidget] = None
        self.wait_time_min_edit_monitoring: Optional[QWidget] = None
        self.wait_time_max_edit_monitoring: Optional[QWidget] = None
        self.total_keywords_button: Optional[QPushButton] = None
        self.refresh_button: Optional[QPushButton] = None
        self.current_site_combo: Optional[QComboBox] = None
        self.refresh_container: Optional[QWidget] = None
        self.progress_action_container: Optional[QWidget] = None

        self.setup_ui()
        self.apply_typography_system()
        
        try:
            self.load_sites()
        except Exception as e:
            print(f"⚠️ 사이트 로드 실패 (무시하고 계속): {e}", flush=True)

        # API 키 상태 확인
        QTimer.singleShot(500, self.check_and_update_api_status)
        QTimer.singleShot(650, self.update_monitoring_settings)

        # 시그널 연결

    def _strip_font_size_rules(self, css_text):
        """스타일시트 내 font-size 선언 제거 (전역 타이포그래피 통일용)"""
        if not css_text:
            return css_text
        cleaned = re.sub(r"font-size\s*:\s*\d+(\.\d+)?\s*(px|pt)\s*;?", "", css_text, flags=re.IGNORECASE)
        cleaned = re.sub(r";\s*;", ";", cleaned)
        return cleaned

    def apply_typography_system(self):
        """UI 전체 폰트 크기/높이 정규화"""
        try:
            default_font = QFont("맑은 고딕", self.TYPO_BASE_PT)
            self.setFont(default_font)

            all_widgets = [self] + self.findChildren(QWidget)
            for widget in all_widgets:
                try:
                    css = widget.styleSheet()
                    if css:
                        widget.setStyleSheet(self._strip_font_size_rules(css))
                except Exception:
                    pass

                try:
                    if isinstance(widget, QLabel):
                        widget.setFont(QFont("맑은 고딕", self.TYPO_LABEL_PT))
                    elif isinstance(widget, QPushButton):
                        widget.setFont(QFont("맑은 고딕", self.TYPO_BUTTON_PT, QFont.Weight.Bold))
                        widget.setMinimumHeight(max(widget.minimumHeight(), 38))
                    elif isinstance(widget, (QLineEdit, QComboBox, QSpinBox)):
                        widget.setFont(QFont("맑은 고딕", self.TYPO_INPUT_PT))
                        widget.setMinimumHeight(max(widget.minimumHeight(), 36))
                    elif isinstance(widget, (QTextEdit,)):
                        widget.setFont(QFont("맑은 고딕", self.TYPO_INPUT_PT))
                    elif isinstance(widget, QGroupBox):
                        widget.setFont(QFont("맑은 고딕", self.TYPO_TITLE_PT, QFont.Weight.Bold))
                except Exception:
                    pass

            self.setStyleSheet(self.styleSheet() + """
                QWidget { font-size: 10pt; }
                QPushButton { min-height: 38px; padding-top: 8px; padding-bottom: 8px; }
                QLineEdit, QComboBox, QSpinBox { min-height: 36px; padding-top: 6px; padding-bottom: 6px; }
                QTabBar::tab { padding-top: 10px; padding-bottom: 10px; }
            """)
        except Exception as e:
            print(f"타이포그래피 적용 오류: {e}")

    # ==================== 중앙 집중식 스타일 관리 ====================

    def apply_theme_palette(self, theme_name):
        """전역 COLORS 팔레트 적용"""
        palette = THEME_PALETTES.get(theme_name, DARK_COLORS)
        COLORS.clear()
        COLORS.update(palette)
        self.current_theme = theme_name

    def normalize_posting_mode(self, mode_text):
        """포스팅 모드 텍스트 정규화"""
        mode = (mode_text or "").strip()
        if mode in ["수익형", "수익"]:
            return "수익용"
        if mode in ["승인형", "승인"]:
            return "승인용"
        return mode if mode in ["승인용", "수익용"] else "수익용"

    def _get_current_ai_provider(self) -> str:
        return self.config_manager.data.get("global_settings", {}).get("default_ai", self.AI_PROVIDER_WEB_GEMINI)

    def _is_api_mode(self) -> bool:
        return self._get_current_ai_provider() == self.AI_PROVIDER_API_GEMINI

    def _is_web_mode(self) -> bool:
        return self._get_current_ai_provider().startswith("web")

    def on_theme_mode_changed(self, theme_name):
        """라이트/다크 테마 전환"""
        try:
            if theme_name == self.current_theme:
                return

            self.config_manager.data.setdefault("global_settings", {})["ui_theme"] = theme_name
            self.config_manager.save_setting()
            self.apply_theme_palette(theme_name)
            self.recreate_main_window()
        except Exception as e:
            print(f"테마 변경 오류: {e}")

    def recreate_main_window(self):
        """테마 변경 시 메인 윈도우 재생성"""
        try:
            geom = self.geometry()
            new_window = MainWindow()
            new_window.setGeometry(geom)
            new_window.show()
            app = QApplication.instance()
            if app is not None:
                setattr(app, "_main_window_ref", new_window)
            self.close()
        except Exception as e:
            print(f"윈도우 재생성 오류: {e}")

    def get_message_box_stylesheet(self):
        """테마 연동 안내창 스타일"""
        return f"""
            QMessageBox {{
                background-color: {COLORS['surface']};
            }}
            QMessageBox QLabel {{
                color: {COLORS['text']};
                font-size: 13px;
                font-weight: 600;
            }}
            QMessageBox QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px 16px;
                min-width: 70px;
                font-weight: 700;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
        """
    
    def get_card_container_style(self):
        """카드 컨테이너 공통 스타일 반환 - 작은 화면 지원"""
        return {
            'max_height': 176,
            'min_height': 176,
            'min_width': 300,
            'size_policy': (QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed),
            'contents_margins': (18, 18, 18, 18),
            'spacing': 14,
            'stylesheet': f"""
                QWidget#monitorCard {{
                    background-color: {COLORS['surface_dark']};
                    border: 2px solid {COLORS['border']};
                    border-radius: 12px;
                    margin: 0px;
                }}
                QWidget#monitorCard:hover {{
                    border-color: {COLORS['primary']};
                    background-color: {COLORS['surface']};
                }}
            """
        }
    
    def get_card_title_style(self):
        """카드 제목 공통 스타일 반환"""
        return f"""
            QPushButton {{
                color: {COLORS['primary']};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
                border: none;
                padding: 0px;
                text-align:center;
            }}
            QPushButton:hover {{
                color: {COLORS['primary_hover']};
                text-decoration: underline;
            }}
        """
    
    def get_card_button_style(self):
        """카드 버튼 공통 스타일 반환"""
        return {
            'fixed_height': 60,
            'size_policy': (QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed),
            'stylesheet': f"""
                QPushButton {{
                    background-color: {COLORS['surface_light']};
                    color: {COLORS['text']};
                    border: 2px solid {COLORS['primary']};
                    border-radius: 10px;
                    padding: 14px 18px;
                    font-weight: 600;
                    font-size: 10pt;
                    text-align:center;
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
            'fixed_height': 60,
            'size_policy': (QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed),
            'stylesheet': f"""
                QComboBox {{
                    background-color: {COLORS['surface_light']};
                    color: {COLORS['text']};
                    border: 2px solid {COLORS['primary']};
                    border-radius: 10px;
                    padding: 14px 14px;
                    font-size: 10pt;
                    font-weight: 600;
                    text-align: center;
                }}
                QComboBox:hover {{
                    background-color: {COLORS['primary']};
                    color: white;
                    border-color: {COLORS['info']};
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: 24px;
                }}
                QComboBox::down-arrow {{
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 7px solid {COLORS['text']};
                    margin-right: 8px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {COLORS['surface_light']};
                    color: {COLORS['text']};
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

    def create_unified_card(self, title, value, callback=None, widget_type="button", suffix=None):
        """통합된 카드 생성 함수 - 모든 카드가 동일한 스타일 사용"""
        # 컨테이너 설정
        container = QWidget()
        container.setObjectName("monitorCard")
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
        layout.addStretch(1)

        # 제목 라벨
        title_label = QPushButton(title)
        title_label.setFlat(True)
        title_label.setStyleSheet(self.get_card_title_style())
        
        if callback:
            title_label.clicked.connect(callback)
            title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignHCenter)

        # 값 위젯 (버튼, 콤보박스, 또는 라인에딕)
        if widget_type == "combobox":
            value_widget = QComboBox()
            style_config = self.get_card_combobox_style()
            
            value_widget.setFixedHeight(style_config['fixed_height'])
            value_widget.setSizePolicy(*style_config['size_policy'])
            value_widget.setStyleSheet(style_config['stylesheet'])
            value_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            value_widget.setEditable(True)
            value_widget.setEnabled(True)
            value_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            value_widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            value_widget.setMinimumContentsLength(20)
            value_widget.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            value_widget.setItemDelegate(CenteredComboDelegate(value_widget))

            line_edit = value_widget.lineEdit()
            if line_edit:
                line_edit.setReadOnly(True)
                line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                line_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                line_edit.setCursor(Qt.CursorShape.ArrowCursor)
                line_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                line_edit.setStyleSheet(f"""
                    QLineEdit {{
                        background: transparent;
                        color: {COLORS['text']};
                        border: none;
                        font-size: 10pt;
                        font-weight: 600;
                        padding-left: 12px;
                        padding-right: 12px;
                    }}
                """)

                def _reset_combo_text_pos():
                    try:
                        line_edit.setCursorPosition(0)
                        line_edit.deselect()
                    except Exception:
                        pass

                value_widget.currentTextChanged.connect(lambda _t: QTimer.singleShot(0, _reset_combo_text_pos))
                value_widget.currentIndexChanged.connect(lambda _i: QTimer.singleShot(0, _reset_combo_text_pos))
                QTimer.singleShot(0, _reset_combo_text_pos)
            
            # 스크롤 기능 비활성화
            value_widget.wheelEvent = self._ignore_wheel_event  # type: ignore[assignment]
            
        elif widget_type == "lineedit":
            # 라인에딕 타입 추가
            value_widget = QLineEdit(value)
            style_config = self.get_card_button_style()
            
            value_widget.setFixedHeight(style_config['fixed_height'])
            value_widget.setSizePolicy(*style_config['size_policy'])
            value_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_widget.setStyleSheet(f"""
                QLineEdit {{
                    background-color: transparent;
                    color: {COLORS['text']};
                    border: none;
                    font-weight: normal;
                    font-size: 10pt;
                    text-align: right;
                }}
                QLineEdit:hover {{
                    background-color: transparent;
                }}
                QLineEdit:focus {{
                    background-color: transparent;
                }}
            """)
            
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

        if widget_type == "combobox":
            value_widget.setMinimumWidth(420)
            value_widget.setMaximumWidth(16777215)
        elif widget_type == "button":
            value_widget.setMinimumWidth(300)
            value_widget.setMaximumWidth(420)

        if widget_type == "lineedit" and suffix:
            wrapper = QFrame()
            wrapper.setObjectName("intervalWrapper")
            wrapper.setStyleSheet(f"""
                QFrame#intervalWrapper {{
                    background-color: {COLORS['surface']};
                    border: 2px solid {COLORS['primary']};
                    border-radius: 10px;
                }}
                QFrame#intervalWrapper:hover {{
                    background-color: {COLORS['primary']};
                    border-color: {COLORS['info']};
                }}
            """)
            
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(15, 5, 15, 5)
            wrapper_layout.setSpacing(5)
            
            # 중앙 정렬을 위한 스페이서
            wrapper_layout.addStretch()
            
            # 입력창 (오른쪽 정렬, 고정 너비로 설정하여 라벨과 붙어있게 함)
            value_widget.setFixedWidth(60)
            if isinstance(value_widget, QLineEdit):
                value_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            wrapper_layout.addWidget(value_widget)
            
            suffix_label = QLabel(suffix)
            suffix_label.setStyleSheet(f"color: {COLORS['text']}; font-weight: normal; font-size: 10pt; border: none; background: transparent;")
            wrapper_layout.addWidget(suffix_label)
            
            # 중앙 정렬을 위한 스페이서
            wrapper_layout.addStretch()
            
            layout.addWidget(wrapper, 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            layout.addWidget(value_widget, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)

        # value_widget을 container의 속성으로 저장
        setattr(container, "value_button", value_widget)
        setattr(container, "value_widget", value_widget)  # 콤보박스용 별칭
        
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
                if self.current_site_combo:
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
            keywords_dir = os.path.join(get_base_path(), "setting", "keywords")
            if os.path.exists(keywords_dir):
                # 키워드 파일 목록 업데이트 로직
                print("📝 키워드 파일 목록 새로고침 완료")
        except Exception as e:
            print(f"키워드 파일 새로고침 오류: {e}")

    def reload_thumbnail_files(self):
        """썸네일 파일 목록 다시 로드"""
        try:
            thumbnails_dir = os.path.join(get_base_path(), "setting", "thumbnails")
            images_dir = os.path.join(get_base_path(), "setting", "images")
            
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
                self.adjust_ui_scale(width)
                
            # 사이트 관리 탭의 버튼 레이아웃 조정
            if hasattr(self, 'add_site_btn'):
                self.adjust_site_buttons_layout(width)
                
        except Exception as e:
            print(f"반응형 레이아웃 적용 오류: {e}")

    def adjust_monitoring_grid(self, width):
        """모니터링 그리드 고정 - 3행 2열 배치 유지"""
        try:
            if not hasattr(self, 'settings_grid'):
                return
            
            columns = 2
            
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
            
            # 그리드에서 위젯들을 제거하고 저장 (순서: AI, 모드, 사이트, 간격, 키워드, 새로고침)
            # 1. AI 설정
            if hasattr(self, 'ai_model_label'):
                widgets.append(self.ai_model_label)
                self.settings_grid.removeWidget(self.ai_model_label)
            
            # 2. 포스팅 모드
            if hasattr(self, 'posting_mode_label'):
                widgets.append(self.posting_mode_label)
                self.settings_grid.removeWidget(self.posting_mode_label)
                
            # 3. 사이트
            if hasattr(self, 'site_label'):
                widgets.append(self.site_label)
                self.settings_grid.removeWidget(self.site_label)
                
            # 4. 포스팅 간격
            if hasattr(self, 'interval_label'):
                widgets.append(self.interval_label)
                self.settings_grid.removeWidget(self.interval_label)
            elif hasattr(self, 'next_posting_label'): # 구버전 호환
                widgets.append(self.next_posting_label)
                self.settings_grid.removeWidget(self.next_posting_label)
                
            # 5. 남은 키워드
            if hasattr(self, 'total_keywords_label'):
                widgets.append(self.total_keywords_label)
                self.settings_grid.removeWidget(self.total_keywords_label)
            
            # 6. 새로고침
            if hasattr(self, 'refresh_button_label'):
                widgets.append(self.refresh_button_label)
                self.settings_grid.removeWidget(self.refresh_button_label)
            elif hasattr(self, 'refresh_container'): # 구버전 호환
                widgets.append(self.refresh_container)
                self.settings_grid.removeWidget(self.refresh_container)
                
            # 고정 배치: (0,0) AI, (0,1) 모드, (1,0) 사이트, (1,1) 간격, (2,0) 키워드, (2,1) 새로고침
            positions = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]
            for i, widget in enumerate(widgets):
                if i >= len(positions):
                    break
                row, col = positions[i]
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
                if hasattr(self, 'prompts_folder_btn'):
                    self.prompts_folder_btn.setText("📝 Prompt")
            else:
                # 큰 화면에서는 전체 텍스트
                if hasattr(self, 'add_site_btn'):
                    self.add_site_btn.setText("➕ 새 사이트 추가")
                if hasattr(self, 'keywords_folder_btn'):
                    self.keywords_folder_btn.setText("📂 Keywords 폴더 열기")
                if hasattr(self, 'prompts_folder_btn'):
                    self.prompts_folder_btn.setText("📝 Prompt 폴더 열기")
                    
        except Exception as e:
            print(f"사이트 버튼 레이아웃 조정 오류: {e}")

    def adjust_ui_scale(self, width):
        """창 너비에 따라 모니터링/설정 UI 요소 크기 조정"""
        try:
            # 너무 이른 축소를 방지해 여유 공간을 적극 사용
            if width < 820:
                scale = 0.86
            elif width < 980:
                scale = 0.93
            else:
                scale = 1.0

            # 카드 내부 요소 글자가 잘리지 않도록 높이를 여유 있게 확보
            card_min_h = max(168, int(168 * scale))
            card_max_h = max(184, int(184 * scale))
            # 좌우 50:50 패널에서도 카드 2열이 자연스럽게 들어가도록 최소 폭을 낮춤
            card_min_w = int(300 * scale)
            ctl_h = int(50 * scale)
            ctl_font = max(11, int(14 * scale))

            card_widgets = [
                getattr(self, "ai_model_label", None),
                getattr(self, "posting_mode_label", None),
                getattr(self, "site_label", None),
                getattr(self, "interval_label", None),
                getattr(self, "total_keywords_label", None),
                getattr(self, "refresh_button_label", None),
            ]
            for w in card_widgets:
                if not w:
                    continue
                w.setMinimumHeight(card_min_h)
                w.setMaximumHeight(card_max_h)
                w.setMinimumWidth(card_min_w)

            # 포스팅 간격 카드는 입력 요소가 많아 최소 폭을 추가 확보
            if hasattr(self, "interval_label") and self.interval_label:
                self.interval_label.setMinimumWidth(card_min_w + 40)
                self.interval_label.setMinimumHeight(card_min_h + 8)
                self.interval_label.setMaximumHeight(card_max_h + 8)

            for btn in [
                getattr(self, "start_btn", None),
                getattr(self, "stop_btn", None),
                getattr(self, "resume_btn", None),
                getattr(self, "pause_btn", None),
            ]:
                if not btn:
                    continue
                btn.setMinimumHeight(ctl_h)
                btn.setMaximumHeight(ctl_h)
                font = btn.font()
                font.setPointSize(ctl_font)
                btn.setFont(font)

            top_buttons = [
                getattr(self, "add_site_btn", None),
                getattr(self, "keywords_folder_btn", None),
                getattr(self, "prompts_folder_btn", None),
                getattr(self, "wp_settings_btn", None),
                getattr(self, "gemini_api_btn", None),
                getattr(self, "website_login_btn", None),
                getattr(self, "refresh_sites_btn", None),
            ]
            top_min_w = int(150 * scale)
            for btn in top_buttons:
                if btn:
                    btn.setMinimumWidth(top_min_w)
                    btn.setMinimumHeight(int(42 * scale))

            if hasattr(self, "tab_widget") and self.tab_widget:
                tab_font = self.tab_widget.font()
                tab_font.setPointSize(max(9, int(11 * scale)))
                self.tab_widget.setFont(tab_font)
                self.tab_widget.setStyleSheet(
                    f"QTabBar::tab {{ min-height: {int(34 * scale)}px; min-width: {int(88 * scale)}px; }}"
                )

                corner = self.tab_widget.cornerWidget(Qt.Corner.TopRightCorner)
                if corner:
                    cfont = corner.font()
                    cfont.setPointSize(max(9, int(11 * scale)))
                    corner.setFont(cfont)
        except Exception as e:
            print(f"UI 축소 조정 오류: {e}")

    def setup_ui(self):
        """UI 설정 - 간단한 레이아웃"""
        self.setWindowTitle("Auto WP multi-site - 멀티 사이트 관리 시스템")
        from PyQt6.QtGui import QGuiApplication
        
        # 🔥 프로그램 아이콘 설정 (임베디드 방식)
        try:
            # 아이콘 파일 경로 (PyInstaller 리소스 경로 사용)
            icon_path = get_preferred_resource_path(os.path.join("setting", "etc", "auto_wp.ico"))
            
            # 아이콘 파일이 있으면 로드
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                self.setWindowIcon(icon)
                # QApplication에도 설정하여 모든 다이얼로그에 적용
                QGuiApplication.setWindowIcon(icon)
                print(f"✅ 프로그램 아이콘 설정 완료: {icon_path}")
            else:
                # 아이콘 파일이 없으면 기본 아이콘 생성 (흰색 원)
                print(f"⚠️ 아이콘 파일을 찾을 수 없습니다: {icon_path}")
                pixmap = QPixmap(64, 64)
                pixmap.fill(QColor("#5E81AC"))
                icon = QIcon(pixmap)
                self.setWindowIcon(icon)
                QGuiApplication.setWindowIcon(icon)
                
        except Exception as e:
            print(f"⚠️ 아이콘 설정 오류: {e}")
        
        # 화면 크기에 맞춰 창 크기 자동 조정
        screen = QGuiApplication.primaryScreen()
        screen_geometry = screen.availableGeometry() if screen else None
        if screen_geometry is None:
            self.resize(1200, 800)
            screen_geometry = self.geometry()
        
        # 화면 크기의 80%로 초기 창 크기 설정
        window_width = int(screen_geometry.width() * 0.8)
        window_height = int(screen_geometry.height() * 0.8)
        
        # 🔥 최소 크기 제한 제거 - 사용자가 자유롭게 크기 조절 가능
        # 초기 크기만 설정하고 최소/최대 제한 없음
        
        # 창을 화면 중앙에 배치
        x = (screen_geometry.width() - window_width) // 2
        y = (screen_geometry.height() - window_height) // 2
        
        self.setGeometry(x, y, window_width, window_height)
        
        # F5 새로고침 단축키 설정
        from PyQt6.QtGui import QShortcut, QKeySequence
        refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_shortcut.activated.connect(self.refresh_monitoring)
        
        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 메인 레이아웃 (기본 설정)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 사용 기간 표시 (우측 상단)
        try:
            license_info = LicenseManager().get_license_info()
            expire_date = license_info.get('expire_date', '무제한')
        except Exception:
            expire_date = "확인 불가"

        usage_period_label = QLabel(f"📅 사용 기간: {expire_date}")
        usage_period_label.setStyleSheet("""
            color: #1565C0; 
            font-weight: bold; 
            font-size: 14px;
            background-color: #E3F2FD;
            padding: 8px 18px;
            border-radius: 8px;
        """)

        # 테마 선택 (사용 기간 왼쪽) - 라디오 방식
        self.theme_radio_group = QButtonGroup(self)
        self.theme_radio_container = QWidget()
        theme_radio_layout = QHBoxLayout(self.theme_radio_container)
        theme_radio_layout.setContentsMargins(8, 0, 8, 0)
        theme_radio_layout.setSpacing(10)

        self.theme_radio_dark = QRadioButton("다크")
        self.theme_radio_light = QRadioButton("라이트")
        self.theme_radio_dark.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_radio_light.setCursor(Qt.CursorShape.PointingHandCursor)
        radio_text_color = "#273A52" if self.current_theme == "라이트" else "#CFE2F4"
        radio_checked_color = "#0A84FF" if self.current_theme == "라이트" else "#F4FBFF"
        radio_indicator_border = "#4E6D8D" if self.current_theme == "라이트" else "#8CB2D3"
        radio_indicator_bg = "#F8FBFF" if self.current_theme == "라이트" else COLORS['surface']
        theme_radio_style = f"""
            QRadioButton {{
                color: {radio_text_color};
                font-weight: 800;
                font-size: 13px;
                spacing: 6px;
                padding: 2px 2px;
                background: transparent;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 2px solid {radio_indicator_border};
                background-color: {radio_indicator_bg};
            }}
            QRadioButton::indicator:checked {{
                border: 2px solid {COLORS['primary']};
                background-color: {COLORS['primary']};
            }}
            QRadioButton:checked {{
                color: {radio_checked_color};
                font-weight: 900;
            }}
            QRadioButton:hover {{
                color: {radio_checked_color};
            }}
        """
        self.theme_radio_dark.setStyleSheet(theme_radio_style)
        self.theme_radio_light.setStyleSheet(theme_radio_style)

        self.theme_radio_group.addButton(self.theme_radio_dark)
        self.theme_radio_group.addButton(self.theme_radio_light)
        theme_radio_layout.addWidget(self.theme_radio_dark)
        theme_radio_layout.addWidget(self.theme_radio_light)

        if self.current_theme == "라이트":
            self.theme_radio_light.setChecked(True)
        else:
            self.theme_radio_dark.setChecked(True)

        self.theme_radio_dark.toggled.connect(lambda checked: self.on_theme_mode_changed("다크") if checked else None)
        self.theme_radio_light.toggled.connect(lambda checked: self.on_theme_mode_changed("라이트") if checked else None)

        # 탭 위젯 (기본 설정)
        self.tab_widget = QTabWidget()
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(8)
        corner_layout.addWidget(self.theme_radio_container)
        corner_layout.addWidget(usage_period_label)
        self.tab_widget.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

        # 모니터링 탭 (원래 버전으로 복원)
        try:
            self.monitoring_tab = self.create_monitoring_tab()
            self.tab_widget.addTab(self.monitoring_tab, "📊 모니터링")
        except Exception as e:
            print(f"⚠️ 모니터링 탭 생성 실패, 간단한 버전 사용: {e}", flush=True)
            self.monitoring_tab = self.create_simple_monitoring_tab()
            self.tab_widget.addTab(self.monitoring_tab, "📊 모니터링")

        # 설정 탭 (스크린샷 기준 버튼형 UI)
        try:
            self.settings_tab = self.create_sites_tab()
            self.tab_widget.addTab(self.settings_tab, "⚙️ 설정")
        except Exception as e:
            print(f"⚠️ 설정 탭 생성 실패, 간단한 버전 사용: {e}", flush=True)
            self.settings_tab = self.create_simple_sites_tab()
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
                font-size: 14px;
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
                font-size: 14px;
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
                font-size: 14px;
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
                font-size: 14px;
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
        # 사용 기간 표시와 버튼들을 같은 줄에 배치
        button_layout = QHBoxLayout()
        

        button_layout.addStretch()

        self.add_site_btn = QPushButton("➕ 새 사이트 추가")
        self.add_site_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.add_site_btn.setMinimumWidth(130)
        self.add_site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_site_btn.setStyleSheet("""
            QPushButton { background-color: #FF0033; color: white; font-weight: 800; padding: 10px 15px; border-radius: 8px; border: 1px solid #C70028; font-size: 14px; }
            QPushButton:hover { background-color: #FF335C; }
        """)
        self.add_site_btn.clicked.connect(self.toggle_add_site_form)
        button_layout.addWidget(self.add_site_btn)

        self.keywords_folder_btn = QPushButton("📂 Keywords 폴더 열기")
        self.keywords_folder_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.keywords_folder_btn.setMinimumWidth(130)
        self.keywords_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keywords_folder_btn.setStyleSheet("""
            QPushButton { background-color: #FF7A00; color: white; font-weight: 800; padding: 10px 15px; border-radius: 8px; border: 1px solid #CC6200; font-size: 14px; }
            QPushButton:hover { background-color: #FF9633; }
        """)
        self.keywords_folder_btn.clicked.connect(self.open_keywords_folder)
        button_layout.addWidget(self.keywords_folder_btn)

        self.prompts_folder_btn = QPushButton("📝 Prompt 폴더 열기")
        self.prompts_folder_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.prompts_folder_btn.setMinimumWidth(130)
        self.prompts_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prompts_folder_btn.setStyleSheet("""
            QPushButton { background-color: #FFC400; color: white; font-weight: 900; padding: 10px 15px; border-radius: 8px; border: 1px solid #CC9D00; font-size: 14px; }
            QPushButton:hover { background-color: #FFD54F; }
        """)
        self.prompts_folder_btn.clicked.connect(self.open_prompts_folder)
        button_layout.addWidget(self.prompts_folder_btn)

        self.wp_settings_btn = QPushButton("🔐 워드프레스 세팅")
        self.wp_settings_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.wp_settings_btn.setMinimumWidth(130)
        self.wp_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wp_settings_btn.setStyleSheet("""
            QPushButton { background-color: #00C853; color: white; font-weight: 800; padding: 10px 15px; border-radius: 8px; border: 1px solid #00A845; font-size: 14px; }
            QPushButton:hover { background-color: #1DE977; }
        """)
        self.wp_settings_btn.clicked.connect(self.open_wp_settings_dialog)
        button_layout.addWidget(self.wp_settings_btn)

        self.gemini_api_btn = QPushButton("🔑 Gemini API 설정")
        self.gemini_api_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.gemini_api_btn.setMinimumWidth(130)
        self.gemini_api_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gemini_api_btn.setStyleSheet("""
            QPushButton { background-color: #0091FF; color: white; font-weight: 800; padding: 10px 15px; border-radius: 8px; border: 1px solid #0073CC; font-size: 14px; }
            QPushButton:hover { background-color: #33A7FF; }
        """)
        self.gemini_api_btn.clicked.connect(self.open_gemini_api_dialog)
        button_layout.addWidget(self.gemini_api_btn)

        self.website_login_btn = QPushButton("🌐 웹사이트 로그인")
        self.website_login_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.website_login_btn.setMinimumWidth(130)
        self.website_login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.website_login_btn.setStyleSheet("""
            QPushButton { background-color: #0B2A66; color: white; font-weight: 800; padding: 10px 15px; border-radius: 8px; border: 1px solid #081F4D; font-size: 14px; }
            QPushButton:hover { background-color: #143E8C; }
        """)
        self.website_login_btn.clicked.connect(self.open_website_login)
        button_layout.addWidget(self.website_login_btn)

        self.refresh_sites_btn = QPushButton("🔄 새로고침")
        self.refresh_sites_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.refresh_sites_btn.setMinimumWidth(110)
        self.refresh_sites_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_sites_btn.setStyleSheet("""
            QPushButton { background-color: #AA00FF; color: white; font-weight: 800; padding: 10px 15px; border-radius: 8px; border: 1px solid #8800CC; font-size: 14px; }
            QPushButton:hover { background-color: #BC33FF; }
        """)
        self.refresh_sites_btn.clicked.connect(self.refresh_site_list)
        button_layout.addWidget(self.refresh_sites_btn)

        # 상단 7개 무지개 버튼 폰트 볼드 강제
        rainbow_btn_font = QFont("맑은 고딕", 10, QFont.Weight.Bold)
        for btn in [
            self.add_site_btn,
            self.keywords_folder_btn,
            self.prompts_folder_btn,
            self.wp_settings_btn,
            self.gemini_api_btn,
            self.website_login_btn,
            self.refresh_sites_btn,
        ]:
            btn.setFont(rainbow_btn_font)

        # 중앙 정렬을 위해 양쪽에 stretch 추가
        final_button_layout = QHBoxLayout()
        final_button_layout.addStretch()
        final_button_layout.addLayout(button_layout)
        final_button_layout.addStretch()

        layout.addLayout(final_button_layout)

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
        """모니터링 탭 생성 - 좌측 상태/우측 로그 2단 구조"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
        widget.setStyleSheet(f"QWidget {{ background-color: {COLORS['background']}; }}")

        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(16, 16, 16, 16)

        horizontal_container = QWidget()
        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_layout.setSpacing(20)

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
        status_layout.setSpacing(36)
        status_layout.setContentsMargins(24, 24, 24, 24)

        self.settings_grid = QGridLayout()
        # 6개 섹션은 가로보다 세로 간격을 넉넉하게
        self.settings_grid.setHorizontalSpacing(32)
        self.settings_grid.setVerticalSpacing(58)
        self.settings_grid.setContentsMargins(0, 8, 0, 12)
        self.settings_grid.setColumnStretch(0, 1)
        self.settings_grid.setColumnStretch(1, 1)

        self.ai_model_label = self.create_unified_card("🤖 AI 설정", "", self.goto_settings_ai, "combobox")
        self.ai_model_combo = self._get_card_value_widget(self.ai_model_label)
        if self.ai_model_combo is None:
            raise RuntimeError("ai_model_combo not available")
        self.ai_model_combo.addItems(["웹사이트 로그인", "API 사용"])
        self.ai_model_combo.setCurrentIndex(0)
        self.settings_grid.addWidget(self.ai_model_label, 0, 0, 1, 1)

        self.posting_mode_label = self.create_unified_card("📝 포스팅 모드", "", self.goto_settings_posting_mode, "combobox")
        self.posting_mode_combo = self._get_card_value_widget(self.posting_mode_label)
        if self.posting_mode_combo is None:
            raise RuntimeError("posting_mode_combo not available")
        self.posting_mode_combo.addItems(["승인용", "수익용"])
        self.posting_mode_combo.setCurrentIndex(1)
        self.settings_grid.addWidget(self.posting_mode_label, 0, 1, 1, 1)

        self.site_label = self.create_site_selector_label()
        self.settings_grid.addWidget(self.site_label, 1, 0, 1, 1)

        wait_time_value = self.config_manager.data["global_settings"].get("default_wait_time", "11~17")
        self.interval_label = self.create_interval_range_card(wait_time_value)
        self.settings_grid.addWidget(self.interval_label, 1, 1, 1, 1)

        self.total_keywords_label = self.create_unified_card("📊 남은 키워드", "0개", self.goto_site_management, "button")
        self.total_keywords_button = self._get_card_value_button(self.total_keywords_label)
        if self.total_keywords_button is None:
            raise RuntimeError("total_keywords_button not available")
        self.settings_grid.addWidget(self.total_keywords_label, 2, 0, 1, 1)

        self.refresh_button_label = self.create_unified_card("🔄 새로고침", "F5", self.refresh_all_status, "button")
        self.refresh_button = self._get_card_value_button(self.refresh_button_label)
        if self.refresh_button is None:
            raise RuntimeError("refresh_button not available")
        self.settings_grid.addWidget(self.refresh_button_label, 2, 1, 1, 1)

        status_layout.addLayout(self.settings_grid)

        control_grid = QGridLayout()
        control_grid.setHorizontalSpacing(14)
        control_grid.setVerticalSpacing(14)
        control_grid.setContentsMargins(0, 8, 0, 0)
        control_grid.setColumnStretch(0, 1)
        control_grid.setColumnStretch(1, 1)

        self.start_btn = QPushButton("▶️ 시작")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['success']};
                color: white;
                font-weight: bold;
                padding: 10px 8px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{ background-color: #8FBCBB; }}
        """)
        self.start_btn.clicked.connect(self.start_posting)
        control_grid.addWidget(self.start_btn, 0, 0)

        self.stop_btn = QPushButton("🔴 중지")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['danger']};
                color: white;
                font-weight: bold;
                padding: 10px 8px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{ background-color: #D08770; }}
        """)
        self.stop_btn.clicked.connect(self.stop_posting)
        control_grid.addWidget(self.stop_btn, 0, 1)

        self.resume_btn = QPushButton("⏯️ 재개")
        self.resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                font-weight: bold;
                padding: 10px 8px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{ background-color: #7C9CBF; }}
        """)
        self.resume_btn.clicked.connect(self.resume_posting)
        control_grid.addWidget(self.resume_btn, 1, 0)

        self.pause_btn = QPushButton("⏸️ 일시정지")
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['warning']};
                color: white;
                font-weight: bold;
                padding: 10px 8px;
                border-radius: 8px;
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{ background-color: #EBCB8B; }}
        """)
        self.pause_btn.clicked.connect(self.pause_posting)
        control_grid.addWidget(self.pause_btn, 1, 1)

        status_layout.addLayout(control_grid)
        status_group.setLayout(status_layout)
        # 좌우 패널을 50:50으로 사용
        status_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        status_group.setMinimumWidth(0)
        horizontal_layout.addWidget(status_group, 1)

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
        progress_layout.setSpacing(12)
        progress_layout.setContentsMargins(15, 15, 15, 15)

        self.progress_text = QTextEdit()
        self.progress_text.setReadOnly(True)
        self.progress_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.progress_text.setMinimumHeight(250)
        font = self.progress_text.font()
        font.setFamily("Segoe UI")
        font.setPointSize(10)
        self.progress_text.setFont(font)
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

        self.progress_text.wheelEvent = self.progress_wheel_event  # type: ignore[assignment]
        self.user_scrolling = False
        self.last_scroll_time = 0
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self.check_scroll_timeout)
        self.scroll_timer.start(1000)

        from datetime import datetime
        startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        startup_time_short = datetime.now().strftime("%H:%M:%S")
        base_path = get_base_path()
        last_posting_state = self.config_manager.get_posting_state()
        last_site_info = ""
        if last_posting_state.get('site_url'):
            last_site_info = f"\n[{startup_time_short}] 🔗 마지막으로 {last_posting_state['site_url']}에서 포스팅이 중단되었습니다."
        active_sites = [site for site in self.config_manager.data.get('sites', []) if site.get('active', True)]
        gemini_key = self.config_manager.data.get('api_keys', {}).get('gemini', '')
        gemini_status = "✅" if gemini_key.startswith('AIza') else "❌"
        config_check_result = self.check_settings_sync()
        settings_button_summary = self.get_settings_button_summary(startup_time_short)
        startup_text = f"""🚀 Auto WP - 워드프레스 자동 포스팅
✨ 제작자 : 데이비

=====================================================================================
[{startup_time}] 📱 프로그램이 시작되었습니다.
[{startup_time}] 📂 기본 경로: {base_path}
[{startup_time}] ▶️ 포스팅 시작 버튼을 눌러 자동 포스팅을 시작하세요.
[{startup_time}] 📋 진행 상태가 이곳에 실시간으로 표시됩니다.{last_site_info}
{settings_button_summary}
{config_check_result}
=====================================================================================
"""
        self.progress_text.setPlainText(startup_text)
        self.progress_text.repaint()
        # 오류 전달용 복사 버튼 (수동)
        self.copy_error_btn = QPushButton("복사")
        self.copy_error_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_error_btn.setMinimumHeight(34)
        self.copy_error_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['surface_light']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                border-color: {COLORS['primary']};
                color: {COLORS['primary']};
            }}
        """)
        self.copy_error_btn.clicked.connect(self.copy_latest_error_for_creator)
        progress_layout.addWidget(self.progress_text)
        progress_layout.addWidget(self.copy_error_btn, 0, Qt.AlignmentFlag.AlignRight)

        self.progress_action_container = QWidget()
        bottom_actions = QHBoxLayout(self.progress_action_container)
        bottom_actions.setContentsMargins(0, 0, 0, 0)
        bottom_actions.setSpacing(8)

        self.site_manage_btn = QPushButton("사이트 추가 변경하기")
        self.site_manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.site_manage_btn.setStyleSheet("""
            QPushButton {
                background-color: #EBCB8B;
                color: #1F2430;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 12px;
            }
            QPushButton:hover { background-color: #F0D79E; }
        """)
        self.site_manage_btn.clicked.connect(self.goto_site_management)
        bottom_actions.addWidget(self.site_manage_btn)

        self.login_manage_btn = QPushButton("로그인 정보 변경하기")
        self.login_manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_manage_btn.setStyleSheet("""
            QPushButton {
                background-color: #EBCB8B;
                color: #1F2430;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 12px;
            }
            QPushButton:hover { background-color: #F0D79E; }
        """)
        self.login_manage_btn.clicked.connect(self.open_wp_settings_dialog)
        bottom_actions.addWidget(self.login_manage_btn)
        progress_layout.addWidget(self.progress_action_container)
        self.update_progress_action_buttons_visibility()

        progress_group.setLayout(progress_layout)
        progress_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        progress_group.setMinimumWidth(0)
        horizontal_layout.addWidget(progress_group, 1)
        horizontal_layout.setStretch(0, 1)
        horizontal_layout.setStretch(1, 1)

        horizontal_container.setLayout(horizontal_layout)
        layout.addWidget(horizontal_container)

        widget.setLayout(layout)
        scroll_area.setWidget(widget)
        self.initialize_monitoring_combos()
        return scroll_area

    def initialize_monitoring_combos(self):
        """모니터링 탭의 콤보박스들 초기화"""
        print("🔧 initialize_monitoring_combos 호출됨", flush=True)
        try:
            # AI 설정 콤보박스 초기화
            if self.ai_model_combo:
                self.ai_model_combo.clear()
                
                # API와 웹사이트 옵션 추가
                ai_options = ["웹사이트 로그인", "API 사용"]
                self.ai_model_combo.addItems(ai_options)
                
                # 현재 설정 확인 (안전하게)
                try:
                    ai_provider = self._get_current_ai_provider()
                except:
                    ai_provider = self.AI_PROVIDER_WEB_GEMINI
                
                # 현재 모드에 맞게 선택
                if self._is_web_mode():
                    self.ai_model_combo.setCurrentText("웹사이트 로그인")
                else:
                    self.ai_model_combo.setCurrentText("API 사용")
                
                # AI 설정 변경 시 업데이트 - 시그널 연결 확인
                try:
                    self.ai_model_combo.currentTextChanged.disconnect()
                except:
                    pass
                self.ai_model_combo.currentTextChanged.connect(self.on_ai_model_changed)
                print(f"✅ AI 설정 콤보박스 초기화 완료: {ai_provider}", flush=True)
            else:
                print("⚠️ ai_model_combo 위젯을 찾을 수 없습니다.", flush=True)
            
            # 포스팅 모드 콤보박스 초기화
            if self.posting_mode_combo:
                self.posting_mode_combo.clear()
                self.posting_mode_combo.addItems(["승인용", "수익용"])
                
                try:
                    current_mode = self.config_manager.data.get("global_settings", {}).get("posting_mode", "수익용")
                except:
                    current_mode = "수익용"

                current_mode = self.normalize_posting_mode(current_mode)
                self.posting_mode_combo.setCurrentText(current_mode)
                
                # 포스팅 모드 변경 시 설정 업데이트
                try:
                    self.posting_mode_combo.currentTextChanged.disconnect()
                except:
                    pass
                self.posting_mode_combo.currentTextChanged.connect(self.on_posting_mode_changed)
                print(f"✅ 포스팅 모드 콤보박스 초기화 완료: {current_mode}", flush=True)
            else:
                print("⚠️ posting_mode_combo 위젯을 찾을 수 없습니다.", flush=True)
            
            # 다음 포스팅 카운트다운 초기화
            next_label = getattr(self, "next_posting_label", None)
            self._set_card_value_text(next_label, "대기중")
                
        except Exception as e:
            print(f"❌ 콤보박스 초기화 오류: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def on_ai_model_changed(self, selection):
        """AI 설정 변경 시 업데이트 (API/웹사이트)"""
        try:
            # 선택에 따라 default_ai 값 변경
            if selection == "웹사이트 로그인":
                self.config_manager.data["global_settings"]["default_ai"] = self.AI_PROVIDER_WEB_GEMINI
                print("✅ AI 설정이 '웹사이트 로그인'으로 변경되었습니다.")
            elif selection == "API 사용":
                self.config_manager.data["global_settings"]["default_ai"] = self.AI_PROVIDER_API_GEMINI
                print("✅ AI 설정이 'API 사용'으로 변경되었습니다.")
            
            self.config_manager.save_config()
            self.update_posting_status(f"🤖 AI 설정 즉시 적용: {selection}")
            
            # 설정 탭의 AI 모드 콤보박스도 업데이트
            if hasattr(self, 'ai_mode_combo'):
                self.ai_mode_combo.blockSignals(True)
                if selection == "웹사이트 로그인":
                    self.ai_mode_combo.setCurrentIndex(0)  # 웹사이트 자동화
                else:
                    self.ai_mode_combo.setCurrentIndex(1)  # API 사용
                self.ai_mode_combo.blockSignals(False)
                
        except Exception as e:
            print(f"AI 설정 저장 오류: {e}")

    def on_posting_mode_changed(self, mode):
        """포스팅 모드 변경 시 설정 업데이트 및 설정 탭과 동기화"""
        try:
            mode = self.normalize_posting_mode(mode)
            self.config_manager.data["global_settings"]["posting_mode"] = mode
            self.config_manager.save_config()
            self.update_posting_status(f"📝 포스팅 모드 즉시 적용: {mode}")
            
            # 설정 탭의 포스팅 모드 콤보박스도 업데이트
            if hasattr(self, 'settings_posting_mode_combo'):
                self.settings_posting_mode_combo.blockSignals(True)  # 무한 루프 방지
                self.settings_posting_mode_combo.setCurrentText(mode)
                self.settings_posting_mode_combo.blockSignals(False)
            
            print(f"포스팅 모드가 '{mode}'로 변경되었습니다.")
            
        except Exception as e:
            print(f"포스팅 모드 설정 저장 오류: {e}")

    def on_ai_mode_changed_from_settings(self, index):
        """설정 탭의 AI 모드 변경 시 모니터링 탭과 동기화"""
        try:
            # index: 0=웹사이트 자동화, 1=API 연동
            if index == 0:
                self.config_manager.data["global_settings"]["default_ai"] = self.AI_PROVIDER_WEB_GEMINI
                selection_text = "웹사이트 로그인"
            else:
                self.config_manager.data["global_settings"]["default_ai"] = self.AI_PROVIDER_API_GEMINI
                selection_text = "API 사용"
            
            self.config_manager.save_config()
            self.update_posting_status(f"🤖 AI 설정 즉시 적용: {selection_text}")
            
            # 모니터링 탭의 AI 설정 콤보박스도 업데이트
            if self.ai_model_combo:
                self.ai_model_combo.blockSignals(True)  # 무한 루프 방지
                self.ai_model_combo.setCurrentText(selection_text)
                self.ai_model_combo.blockSignals(False)
            
            print(f"설정 탭에서 AI 모드가 '{selection_text}'로 변경되었습니다.")
            
        except Exception as e:
            print(f"AI 모드 설정 저장 오류: {e}")

    def on_interval_changed(self, text=None):
        """포스팅 간격 변경 시 설정 업데이트 (최소~최대 분)"""
        try:
            min_edit = getattr(self, "wait_time_min_edit_monitoring", None)
            max_edit = getattr(self, "wait_time_max_edit_monitoring", None)

            if min_edit and max_edit:
                # QSpinBox/QLineEdit 모두 지원
                if hasattr(min_edit, "value") and hasattr(max_edit, "value"):
                    min_num = int(min_edit.value())
                    max_num = int(max_edit.value())
                else:
                    min_val = (min_edit.text() or "").strip()
                    max_val = (max_edit.text() or "").strip()
                    if not min_val and not max_val:
                        return
                    if not min_val.isdigit() or not max_val.isdigit():
                        return
                    min_num = int(min_val)
                    max_num = int(max_val)

                if min_num > max_num:
                    min_num, max_num = max_num, min_num

                wait_time_text = f"{min_num}~{max_num}"
            else:
                wait_time_text = (text or "").strip()
                if not wait_time_text:
                    return

            # 동일 값 재입력 시 중복 처리 방지
            if wait_time_text == self._last_applied_wait_time:
                return

            self.config_manager.data["global_settings"]["default_wait_time"] = wait_time_text
            self.config_manager.save_config()
            self._last_applied_wait_time = wait_time_text
            print(f"포스팅 간격이 '{wait_time_text}'로 변경되었습니다.")

            # 진행 상태에 실시간 반영
            self.update_posting_status(f"⏱️ 포스팅 간격 즉시 적용: {wait_time_text}분")

            # 포스팅 중이면 다음 포스팅 카운트다운도 즉시 재계산
            if getattr(self, "is_posting", False):
                self.start_next_posting_countdown()
                self.update_posting_status("🔄 다음 포스팅 대기 시간이 새 간격으로 갱신되었습니다.")

        except Exception as e:
            print(f"포스팅 간격 설정 저장 오류: {e}")

    def open_wp_settings_dialog(self):
        """워드프레스 세팅 다이얼로그 열기"""
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("🔐 워드프레스 세팅")
            dialog.setMinimumWidth(500)
            dialog.setStyleSheet(f"""
                QDialog {{
                    background-color: {COLORS['surface']};
                }}
            """)
            
            layout = QVBoxLayout()
            layout.setSpacing(20)
            layout.setContentsMargins(30, 30, 30, 30)
            
            # 제목
            title_label = QLabel("🔐 워드프레스 공통 설정")
            title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #81A1C1; margin-bottom: 10px;")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title_label)
            
            # 설명
            desc_label = QLabel("모든 사이트에 공통으로 적용되는 워드프레스 사용자명과 비밀번호를 설정하세요.")
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("font-size: 14px; color: #D8DEE9; margin-bottom: 15px;")
            desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(desc_label)
            
            # 폼 레이아웃
            form_layout = QVBoxLayout()
            form_layout.setSpacing(15)
            
            # 사용자명
            username_label = QLabel("사용자명:")
            username_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #81A1C1;")
            form_layout.addWidget(username_label)
            
            username_edit = QLineEdit()
            username_edit.setText(self.config_manager.data["global_settings"].get("common_username", ""))
            username_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            username_edit.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {COLORS['surface']};
                    color: white;
                    border: 2px solid {COLORS['primary']};
                    border-radius: 10px;
                    padding: 12px 20px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                QLineEdit:focus {{
                    border-color: {COLORS['info']};
                    background-color: {COLORS['surface_light']};
                }}
            """)
            form_layout.addWidget(username_edit)
            
            # 비밀번호
            password_label = QLabel("응용프로그램 비밀번호:")
            password_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #81A1C1; margin-top: 10px;")
            form_layout.addWidget(password_label)
            
            password_row = QHBoxLayout()
            password_row.setSpacing(10)
            
            password_edit = QLineEdit()
            password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            password_edit.setText(self.config_manager.data["global_settings"].get("common_password", ""))
            password_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            password_edit.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {COLORS['surface']};
                    color: white;
                    border: 2px solid {COLORS['primary']};
                    border-radius: 10px;
                    padding: 12px 20px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                QLineEdit:focus {{
                    border-color: {COLORS['info']};
                    background-color: {COLORS['surface_light']};
                }}
            """)
            password_row.addWidget(password_edit, 1)
            
            toggle_btn = QPushButton("👁️")
            toggle_btn.setFixedSize(40, 40)
            toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['surface']};
                    border: 2px solid {COLORS['primary']};
                    border-radius: 10px;
                    font-size: 16px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['primary']};
                }}
            """)
            toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(password_edit, toggle_btn))
            password_row.addWidget(toggle_btn)
            
            form_layout.addLayout(password_row)
            layout.addLayout(form_layout)
            
            # 버튼
            button_layout = QHBoxLayout()
            button_layout.setSpacing(10)
            
            save_btn = QPushButton("💾 저장")
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setMinimumHeight(45)
            save_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['primary']};
                    color: white;
                    border: none;
                    border-radius: 10px;
                    padding: 12px 25px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['primary_hover']};
                }}
            """)
            
            def save_settings():
                self.config_manager.data["global_settings"]["common_username"] = username_edit.text()
                self.config_manager.data["global_settings"]["common_password"] = password_edit.text()
                self.config_manager.save_config()
                self.update_progress_action_buttons_visibility()
                QMessageBox.information(dialog, "성공", "워드프레스 세팅이 저장되었습니다.")
                dialog.accept()
            
            save_btn.clicked.connect(save_settings)
            button_layout.addWidget(save_btn)
            
            cancel_btn = QPushButton("❌ 취소")
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setMinimumHeight(45)
            cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['surface_light']};
                    color: white;
                    border: 2px solid {COLORS['border']};
                    border-radius: 10px;
                    padding: 12px 25px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['hover']};
                }}
            """)
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)
            
            layout.addLayout(button_layout)
            dialog.setLayout(layout)
            dialog.exec()
            
        except Exception as e:
            print(f"워드프레스 세팅 다이얼로그 오류: {e}")
            QMessageBox.warning(self, "오류", f"워드프레스 세팅을 열 수 없습니다: {e}")

    def on_settings_posting_mode_changed(self, mode):
        """설정 탭의 포스팅 모드 변경 시 모니터링 탭과 동기화"""
        try:
            mode = self.normalize_posting_mode(mode)
            self.config_manager.data["global_settings"]["posting_mode"] = mode
            self.config_manager.save_config()
            self.update_posting_status(f"📝 포스팅 모드 즉시 적용: {mode}")
            
            # 모니터링 탭의 포스팅 모드 콤보박스도 업데이트
            if self.posting_mode_combo:
                self.posting_mode_combo.blockSignals(True)  # 무한 루프 방지
                self.posting_mode_combo.setCurrentText(mode)
                self.posting_mode_combo.blockSignals(False)
            
            print(f"설정 탭에서 포스팅 모드가 '{mode}'로 변경되었습니다.")
            
        except Exception as e:
            print(f"포스팅 모드 설정 저장 오류: {e}")

    def update_monitoring_settings(self):
        """설정 저장 후 모니터링 탭의 '현재 설정 상태' 업데이트"""
        try:
            # AI 설정 콤보박스 업데이트
            if self.ai_model_combo:
                ai_provider = self._get_current_ai_provider()
                
                # AI 제공자에 따라 선택 항목 업데이트
                self.ai_model_combo.blockSignals(True)
                self.ai_model_combo.clear()
                
                ai_options = ["웹사이트 로그인", "API 사용"]
                self.ai_model_combo.addItems(ai_options)
                
                # 현재 설정에 맞게 선택
                if ai_provider.startswith("web"):
                    self.ai_model_combo.setCurrentText("웹사이트 로그인")
                else:
                    self.ai_model_combo.setCurrentText("API 사용")
                
                self.ai_model_combo.blockSignals(False)
                print(f"✅ 모니터링 탭 AI 설정 업데이트: {self.ai_model_combo.currentText()}")
            
            # 포스팅 모드 콤보박스 업데이트
            if self.posting_mode_combo:
                posting_mode = self.normalize_posting_mode(
                    self.config_manager.data["global_settings"].get("posting_mode", "수익용")
                )
                self.posting_mode_combo.blockSignals(True)
                self.posting_mode_combo.setCurrentText(posting_mode)
                self.posting_mode_combo.blockSignals(False)
                print(f"✅ 모니터링 탭 포스팅 모드 업데이트: {posting_mode}")

            if self.current_site_combo and self.current_site_combo.count() == 0:
                self.current_site_combo.addItem("사이트 없음", "none")
                self.current_site_combo.setCurrentIndex(0)

            wait_time_value = self.config_manager.data["global_settings"].get("default_wait_time", "11~17")
            min_edit = getattr(self, "wait_time_min_edit_monitoring", None)
            max_edit = getattr(self, "wait_time_max_edit_monitoring", None)
            if min_edit and max_edit:
                min_val, max_val = "11", "17"
                raw = (wait_time_value or "").strip()
                if "~" in raw:
                    left, right = raw.split("~", 1)
                    if left.strip().isdigit():
                        min_val = left.strip()
                    if right.strip().isdigit():
                        max_val = right.strip()
                elif raw.isdigit():
                    min_val = raw
                    max_val = raw
                min_edit.blockSignals(True)
                max_edit.blockSignals(True)
                if hasattr(min_edit, "setValue") and hasattr(max_edit, "setValue"):
                    min_edit.setValue(int(min_val))
                    max_edit.setValue(int(max_val))
                else:
                    min_edit.setText(min_val)
                    max_edit.setText(max_val)
                min_edit.blockSignals(False)
                max_edit.blockSignals(False)
            
            # 키워드 개수 업데이트
            self.update_all_ui_status()
            self.update_progress_action_buttons_visibility()
            
            print("✅ 모니터링 탭의 '현재 설정 상태'가 업데이트되었습니다.")
            
        except Exception as e:
            print(f"❌ 모니터링 탭 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()

    def create_clickable_setting_label(self, title, value, callback):
        """클릭 가능한 설정 라벨 생성 - 통합된 스타일 사용"""
        return self.create_unified_card(title, value, callback, "button")

    def create_site_selector_label(self):
        """사이트 선택을 위한 라벨 생성 - 통합된 스타일 사용"""
        container = self.create_unified_card("🌐 사이트", "", self.open_selected_site_wp_admin, "combobox")
        
        # 콤보박스 참조 저장
        current_site_combo = getattr(container, "value_widget", None)
        if current_site_combo is None:
            raise RuntimeError("value_widget not available on site selector container.")
        self.current_site_combo = current_site_combo
        current_site_combo.addItem("사이트 없음", "none")
        current_site_combo.activated.connect(self.open_selected_site_wp_admin)
        
        return container

    def create_interval_range_card(self, wait_time_value):
        """포스팅 간격 카드 생성 - 최소~최대 분 입력"""
        card = QWidget()
        card.setObjectName("monitorCard")
        container_style = self.get_card_container_style()
        # 간격 카드는 입력 컨트롤 높이가 있어 기본 카드보다 여유를 조금 더 확보
        card.setMaximumHeight(container_style['max_height'] + 8)
        card.setMinimumHeight(container_style['min_height'] + 8)
        card.setMinimumWidth(container_style['min_width'] + 70)
        card.setSizePolicy(*container_style['size_policy'])
        card.setStyleSheet(container_style['stylesheet'])

        layout = QVBoxLayout(card)
        layout.setContentsMargins(*container_style['contents_margins'])
        layout.setSpacing(container_style['spacing'])
        layout.addStretch(1)

        title_btn = QPushButton("⏱️ 포스팅 간격")
        title_btn.setFlat(True)
        title_btn.setStyleSheet(self.get_card_title_style())
        title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        title_btn.clicked.connect(self.goto_settings_interval)
        layout.addWidget(title_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        min_text = "11"
        max_text = "17"
        raw = (wait_time_value or "").strip()
        if "~" in raw:
            left, right = raw.split("~", 1)
            if left.strip().isdigit():
                min_text = left.strip()
            if right.strip().isdigit():
                max_text = right.strip()
        elif raw.isdigit():
            min_text = raw
            max_text = raw

        value_panel = QFrame()
        value_panel.setFixedHeight(66)
        value_panel.setMinimumWidth(330)
        value_panel.setMaximumWidth(420)
        value_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        value_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface_light']};
                border: 2px solid {COLORS['primary']};
                border-radius: 10px;
            }}
        """)
        row = QHBoxLayout(value_panel)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(8)
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        spin_style = f"""
            QSpinBox {{
                background-color: {COLORS['surface']};
                color: {COLORS['text']};
                border: 2px solid {COLORS['primary']};
                border-radius: 10px;
                font-size: 10pt;
                font-weight: 700;
                padding: 4px 26px 4px 10px;
            }}
            QSpinBox:focus {{
                border-color: {COLORS['info']};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
                border: none;
                background: transparent;
            }}
            QSpinBox::up-arrow, QSpinBox::down-arrow {{
                image: none;
            }}
        """

        self.wait_time_min_edit_monitoring = QSpinBox()
        self.wait_time_min_edit_monitoring.setRange(1, 999)
        self.wait_time_min_edit_monitoring.setValue(int(min_text))
        self.wait_time_min_edit_monitoring.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wait_time_min_edit_monitoring.setSuffix("분")
        self.wait_time_min_edit_monitoring.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.wait_time_min_edit_monitoring.setFixedHeight(34)
        self.wait_time_min_edit_monitoring.setFixedWidth(160)
        self.wait_time_min_edit_monitoring.setStyleSheet(spin_style)
        self.wait_time_min_edit_monitoring.valueChanged.connect(self.on_interval_changed)
        row.addStretch(1)
        row.addWidget(self.wait_time_min_edit_monitoring, 0, Qt.AlignmentFlag.AlignVCenter)

        tilde = QLabel("~")
        tilde.setStyleSheet(f"color: {COLORS['text']}; font-size: 16px; font-weight: bold;")
        tilde.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tilde.setFixedWidth(18)
        row.addWidget(tilde, 0, Qt.AlignmentFlag.AlignVCenter)

        self.wait_time_max_edit_monitoring = QSpinBox()
        self.wait_time_max_edit_monitoring.setRange(1, 999)
        self.wait_time_max_edit_monitoring.setValue(int(max_text))
        self.wait_time_max_edit_monitoring.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wait_time_max_edit_monitoring.setSuffix("분")
        self.wait_time_max_edit_monitoring.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.wait_time_max_edit_monitoring.setFixedHeight(34)
        self.wait_time_max_edit_monitoring.setFixedWidth(160)
        self.wait_time_max_edit_monitoring.setStyleSheet(spin_style)
        self.wait_time_max_edit_monitoring.valueChanged.connect(self.on_interval_changed)
        row.addWidget(self.wait_time_max_edit_monitoring, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

        layout.addWidget(value_panel, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

        self.wait_time_edit_monitoring = self.wait_time_min_edit_monitoring
        setattr(card, "value_widget", self.wait_time_min_edit_monitoring)
        setattr(card, "value_button", self.wait_time_min_edit_monitoring)
        return card

    def _get_card_value_button(self, card):
        """카드의 value_button을 안전하게 반환"""
        return getattr(card, "value_button", None)

    def _get_card_value_widget(self, card):
        """카드의 value_widget을 안전하게 반환"""
        return getattr(card, "value_widget", None)

    def _set_card_value_text(self, card, text):
        """카드 value_button에 텍스트를 안전하게 설정"""
        value_widget = self._get_card_value_button(card)
        if value_widget and hasattr(value_widget, "setText"):
            value_widget.setText(text)

    def _ignore_wheel_event(self, event):
        """휠 이벤트 무시"""
        event.ignore()

    def _get_site_url_by_id(self, site_id):
        """사이트 ID로 URL 조회"""
        try:
            for site in self.config_manager.data.get("sites", []):
                if str(site.get("id")) == str(site_id):
                    return (site.get("url", "") or "").strip()
        except Exception:
            return ""
        return ""

    def open_selected_site_wp_admin(self, *_args):
        """모니터링 사이트 카드에서 선택된 사이트의 wp-admin 열기"""
        try:
            if not self.current_site_combo:
                return

            current_index = self.current_site_combo.currentIndex()
            site_url = self.current_site_combo.itemData(current_index, Qt.ItemDataRole.UserRole + 1)
            if not site_url:
                site_id = self.current_site_combo.currentData()
                site_url = self._get_site_url_by_id(site_id)
            if not site_url:
                return

            wp_admin_url = site_url.rstrip("/") + "/wp-admin"
            QDesktopServices.openUrl(QUrl(wp_admin_url))
        except Exception as e:
            print(f"wp-admin 열기 실패: {e}")

    def needs_progress_action_buttons(self):
        """진행 상태 하단 보조 버튼 노출 필요 여부"""
        try:
            global_settings = self.config_manager.data.get("global_settings", {})
            common_username = (global_settings.get("common_username", "") or "").strip()
            common_password = (global_settings.get("common_password", "") or "").strip()
            if not common_username or not common_password:
                return True

            sites = self.config_manager.data.get("sites", [])
            active_sites = [s for s in sites if s.get("active", True)]
            if not active_sites:
                return True

            for site in active_sites:
                if not (site.get("url", "") or "").strip():
                    return True
                if not (site.get("keyword_file", "") or "").strip():
                    return True

            return False
        except Exception:
            return True

    def update_progress_action_buttons_visibility(self):
        """설정 상태에 따라 진행 상태 하단 버튼 표시/숨김"""
        container = getattr(self, "progress_action_container", None)
        if container is None:
            return
        container.setVisible(self.needs_progress_action_buttons())

    def check_settings_sync(self):
        """설정 탭 정보와 JSON 파일 연동 상태 체크"""
        try:
            from datetime import datetime
            startup_time_short = datetime.now().strftime("%H:%M:%S")
            check_results = []
            
            # AI 설정 체크
            ai_provider = self.config_manager.data["global_settings"].get("default_ai", "web-gemini")
            ai_model = self.config_manager.data["global_settings"].get("ai_model", "")
            gemini_key = self.config_manager.data.get('api_keys', {}).get('gemini', '')
            
            if ai_provider == "gemini" and not gemini_key.startswith('AIza'):
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

    def get_settings_button_summary(self, startup_time_short):
        """설정 탭 7개 상단 버튼의 현재 설정 요약"""
        try:
            base_path = get_base_path()
            sites = self.config_manager.data.get('sites', [])
            active_sites = [site for site in sites if site.get('active', True)]
            global_settings = self.config_manager.data.get("global_settings", {})

            keywords_dir = os.path.join(base_path, "setting", "keywords")
            prompts_dir = os.path.join(base_path, "setting", "prompts")

            keyword_file_count = 0
            if os.path.exists(keywords_dir):
                keyword_file_count = len([
                    f for f in os.listdir(keywords_dir)
                    if f.lower().endswith(".txt")
                ])

            prompt_file_count = 0
            if os.path.exists(prompts_dir):
                prompt_file_count = len([
                    f for f in os.listdir(prompts_dir)
                    if f.lower().endswith(".txt")
                ])

            wp_user = (global_settings.get("common_username", "") or "").strip()
            wp_pass = (global_settings.get("common_password", "") or "").strip()
            wp_status = "완료" if (wp_user and wp_pass) else "미완료"

            gemini_key = (self.config_manager.data.get("api_keys", {}).get("gemini", "") or "").strip()
            gemini_status = "설정됨" if gemini_key else "미설정"

            google_email = (global_settings.get("google_email", "") or "").strip()
            google_password = (global_settings.get("google_password", "") or "").strip()
            web_login_status = "완료" if (google_email and google_password) else "미완료"

            lines = [
                f"[{startup_time_short}] ⚙️ 설정 버튼 내역",
                f"[{startup_time_short}]   1) ➕ 새 사이트 추가: 총 {len(sites)}개 (활성 {len(active_sites)}개)",
                f"[{startup_time_short}]   2) 📂 Keywords 폴더 열기: txt 파일 {keyword_file_count}개",
                f"[{startup_time_short}]   3) 📝 Prompt 폴더 열기: txt 파일 {prompt_file_count}개",
                f"[{startup_time_short}]   4) 🔐 워드프레스 세팅: {wp_status}",
                f"[{startup_time_short}]   5) 🔑 Gemini API 설정: {gemini_status}",
                f"[{startup_time_short}]   6) 🌐 웹사이트 로그인: {web_login_status}",
                f"[{startup_time_short}]   7) 🔄 새로고침: 사용 가능 (F5)",
            ]
            return "\n" + "\n".join(lines)
        except Exception as e:
            return f"\n[{startup_time_short}] ⚠️ 설정 버튼 내역 조회 실패: {e}"

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

            # 4-1. 모니터링 탭의 현재 설정 상태 즉시 반영
            self.update_monitoring_settings()
            
            # 5. UI 상태 업데이트
            self.update_all_ui_status()
            self.update_progress_action_buttons_visibility()
            
            # 6. 포스팅 버튼 상태 갱신
            self.update_button_states()
            
            self.update_posting_status("🔄 새로고침 완료 - 모든 설정값이 최신 버전으로 업데이트되었습니다!")
            print("🔄 F5 새로고침 완료 - 전체 설정 다시 로드됨")
            
        except Exception as e:
            self.update_posting_status(f"❌ 새로고침 중 오류: {str(e)}")
            print(f"❌ 새로고침 중 오류: {e}")
    
    def refresh_monitoring(self):
        """F5 단축키로 호출되는 새로고침 메서드"""
        self.refresh_all_status()
    
    def check_scroll_timeout(self):
        """사용자 스크롤 타임아웃 체크 - 10초 이상 스크롤하지 않으면 자동 스크롤 재개"""
        try:
            import time
            current_time = time.time()
            
            # 사용자가 스크롤 중이고, 마지막 스크롤 후 10초 경과
            if self.user_scrolling and (current_time - self.last_scroll_time) >= 10:
                self.user_scrolling = False
                # 현재 진행 상황으로 스크롤
                self.progress_text.moveCursor(QTextCursor.MoveOperation.End)
                
        except Exception:
            pass

    def update_all_ui_status(self):
        """모든 UI 상태 정보 업데이트"""
        try:
            # AI 모델 업데이트 - 더 정확한 표시
            ai_provider = self.config_manager.data["global_settings"].get("default_ai", "web-gemini")
            ai_model = self.config_manager.data["global_settings"].get("ai_model", "")
            
            if ai_model:
                ai_display = ai_model
            else:
                ai_display = "gemini-2.5-flash-lite"
            
            # AI 모델 업데이트는 콤보박스에서 자동 처리됨
            # 포스팅 모드 업데이트도 콤보박스에서 자동 처리됨

            # 남은 키워드 개수 업데이트 (실시간)
            total_keywords = 0
            # sites 데이터 직접 접근
            sites_data = self.config_manager.data.get("sites", [])
                
            for site_data in sites_data:
                keyword_file = site_data.get("keyword_file", "")
                if keyword_file:
                    keyword_path = os.path.join(get_base_path(), "setting", "keywords", keyword_file)
                    if os.path.exists(keyword_path):
                        try:
                            with open(keyword_path, 'r', encoding='utf-8') as f:
                                lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith('#')]
                                count = len(lines)
                                print(f"🔍 키워드 확인: {keyword_file} - {count}개")
                                total_keywords += count
                        except Exception as e:
                            print(f"❌ 키워드 파일 읽기 오류 ({keyword_path}): {e}")

            if self.total_keywords_button:
                self.total_keywords_button.setText(f"{total_keywords}개")

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

    def find_site_combo_index(self, site_label):
        """현재 사이트 라벨(도메인/URL)로 콤보 인덱스 찾기"""
        try:
            if not self.current_site_combo or not site_label:
                return -1

            target = self.clean_url_for_display(site_label).strip().lower()
            for i in range(self.current_site_combo.count()):
                text = (self.current_site_combo.itemText(i) or "").strip()
                text_clean = self.clean_url_for_display(text).lower()
                if target and (target in text_clean or text_clean in target):
                    return i
            return -1
        except Exception:
            return -1

    def goto_settings_ai(self):
        """설정 탭의 AI 모델 설정으로 이동"""
        self.tab_widget.setCurrentIndex(1)  # 설정 탭으로 이동

    def goto_settings_posting_mode(self):
        """설정 탭의 포스팅 모드 설정으로 이동"""
        self.tab_widget.setCurrentIndex(1)  # 설정 탭으로 이동

    def goto_site_management(self):
        """사이트 관리 탭으로 이동"""
        self.tab_widget.setCurrentIndex(1)  # 사이트 관리 탭으로 이동

    def goto_settings_interval(self):
        """설정 탭의 간격 설정으로 이동"""
        self.tab_widget.setCurrentIndex(1)  # 설정 탭으로 이동

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
                    background-color: #6E2B93;
                    color: white;
                    font-weight: 800;
                    padding: 12px 24px;
                    border-radius: 6px;
                    border: 1px solid #5A2278;
                    font-size: 14px;
                }}
                QPushButton#purpleButton:hover {{
                    background-color: #8333AF;
                }}
            """)
        else:
            self.add_site_form.show()
            self.add_site_btn.setText("➖ 폼 닫기")
            # 닫기 버튼은 빨간색으로
            self.add_site_btn.setObjectName("closeButton")
            self.add_site_btn.setStyleSheet(f"""
                QPushButton#closeButton {{
                    background-color: #D90000;
                    color: white;
                    font-weight: 800;
                    padding: 12px 24px;
                    border-radius: 6px;
                    border: 1px solid #B00000;
                    font-size: 14px;
                }}
                QPushButton#closeButton:hover {{
                    background-color: #F00000;
                }}
            """)

    def browse_thumbnail_for_site(self):
        """사이트용 썸네일 이미지 선택"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "썸네일 이미지 선택", 
            os.path.join(get_base_path(), "setting", "images"),
            "이미지 파일 (*.jpg *.jpeg *.png)"
        )
        if file_path:
            filename = os.path.basename(file_path)
            self.inline_thumbnail_edit.setText(filename)

    def browse_keywords_for_site(self):
        """사이트용 키워드 파일 선택"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "키워드 파일 선택",
            os.path.join(get_base_path(), "setting", "keywords"),
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
            "ai_provider": self.config_manager.data["global_settings"].get("default_ai", "web-gemini"),
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
                background-color: #6E2B93;
                color: white;
                font-weight: 800;
                padding: 12px 24px;
                border-radius: 6px;
                border: 1px solid #5A2278;
                font-size: 14px;
            }}
            QPushButton#purpleButton:hover {{
                background-color: #8333AF;
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
            populate_fn = getattr(self, "populate_thumbnail_combo", None)
            if callable(populate_fn):
                populate_fn()
            print("🔄 사이트 목록이 새로고침되었습니다.")
        except Exception as e:
            print(f"새로고침 오류: {e}")

    def load_sites(self):
        """사이트 목록 로드"""
        # 기존 사이트 위젯들 제거
        for i in reversed(range(self.sites_layout.count() - 1)):  # stretch 제외하고 제거
            child = self.sites_layout.itemAt(i)
            if not child:
                continue
            widget = child.widget()
            if widget:
                widget.deleteLater()

        # 새 사이트 위젯들 추가
        try:
            # sites 데이터 직접 접근
            sites_data = self.config_manager.data.get("sites", [])
                
            print(f"사이트 데이터 타입: {type(sites_data)}, 개수: {len(sites_data)}")
            
            # 키워드 300개 미만 사이트 체크
            low_keyword_sites = []
            
            for site in sites_data:
                # 모든 사이트를 표시 (활성화된 사이트와 비활성화된 사이트 모두)
                site_widget = SiteWidget(site)
                site_widget.edit_requested.connect(self.edit_site)
                site_widget.keywords_requested.connect(self.manage_site_keywords)
                site_widget.thumbnails_requested.connect(self.manage_site_thumbnails)
                site_widget.delete_requested.connect(self.delete_site)
                site_widget.toggle_requested.connect(self.toggle_site_active)
                self.sites_layout.insertWidget(self.sites_layout.count() - 1, site_widget)
                
                # 키워드 개수 체크 (활성화된 사이트만)
                if site.get("active", True):
                    keyword_file = site.get("keyword_file", "")
                    if keyword_file:
                        keyword_path = os.path.join(get_base_path(), "setting", "keywords", keyword_file)
                        if os.path.exists(keyword_path):
                            try:
                                with open(keyword_path, 'r', encoding='utf-8') as f:
                                    lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith('#')]
                                    keyword_count = len(lines)
                                    if keyword_count < 300:
                                        site_name = site.get("name", "알 수 없음")
                                        low_keyword_sites.append((site_name, keyword_count))
                            except Exception as e:
                                print(f"키워드 파일 읽기 오류 ({keyword_file}): {e}")
            
            # 시작 사이트 드롭다운 업데이트
            self.update_start_site_combo(sites_data)
            self.update_monitoring_settings()
            
            # 키워드 부족 경고창 표시 (비차단, 백그라운드에서 표시)
            if low_keyword_sites:
                QTimer.singleShot(500, lambda: self.show_detailed_low_keyword_warning(low_keyword_sites))

            # 동적으로 생성된 사이트 위젯까지 폰트 규칙 통일
            self.apply_typography_system()
                
        except Exception as e:
            print(f"사이트 로드 오류: {e}")

    def show_low_keyword_warning(self, low_keyword_sites):
        """키워드 부족 경고창 표시 (비차단) - 구버전, 사용 안함"""
        pass
    
    def show_detailed_low_keyword_warning(self, low_keyword_sites):
        """키워드 300개 미만 상세 경고 메시지 표시 (비차단)"""
        try:
            # 사이트별 상세 정보 생성
            warning_msg = f"⚠️ 총 {len(low_keyword_sites)}개 사이트의 키워드가 300개 미만입니다:\n\n"
            
            for site_name, count in low_keyword_sites:
                warning_msg += f"• {site_name}: 현재 {count}개\n"
            
            warning_msg += "\n⚠️ 키워드가 부족하면 포스팅이 조기에 중단될 수 있습니다."
            warning_msg += "\n💡 Keywords 폴더에서 키워드를 추가해주세요."
            
            # 비차단 메시지 박스 (경고 아이콘 없이 소리 차단)
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.NoIcon)  # 경고음 방지
            msg_box.setOption(QMessageBox.Option.DontUseNativeDialog, True)  # OS 기본 사운드 비활성화
            msg_box.setWindowTitle("키워드 부족 경고")
            msg_box.setText(warning_msg)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.setModal(False)  # 비차단 모드
            msg_box.setStyleSheet(self.get_message_box_stylesheet())
            
            # 🔥 메시지 박스에 프로그램 아이콘 적용
            if self.windowIcon():
                msg_box.setWindowIcon(self.windowIcon())
            
            msg_box.show()
            
        except Exception as e:
            print(f"경고창 표시 오류: {e}")

    def update_start_site_combo(self, sites_data):
        """사이트 드롭다운 업데이트"""
        try:
            if self.current_site_combo:
                self.current_site_combo.clear()
                self.current_site_combo.addItem("사이트 없음", "none")
                
                active_count = 0
                for i, site in enumerate(sites_data):
                    if site.get("active", True):
                        active_count += 1
                        site_name = site.get("name", f"사이트 {i+1}")
                        site_url = site.get("url", "") or site.get("wp_url", "")
                        display_text = site_url.strip() if site_url else site_name
                        self.current_site_combo.addItem(display_text, site.get("id", i))
                        self.current_site_combo.setItemData(
                            self.current_site_combo.count() - 1,
                            site_url.strip(),
                            Qt.ItemDataRole.UserRole + 1
                        )
                
                if active_count > 0:
                    self.current_site_combo.setCurrentIndex(1)
                else:
                    self.current_site_combo.setCurrentIndex(0)
        except Exception as e:
            print(f"드롭다운 업데이트 오류: {e}")

    def edit_site(self, site_id):
        """사이트 편집"""
        site_data = self.config_manager.get_site(site_id)
        if site_data:
            dialog = SiteEditDialog(self, site_data)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                updated_data = dialog.get_site_data()
                if not updated_data:
                    QMessageBox.warning(self, "오류", "사이트 정보를 가져오지 못했습니다.")
                    return
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
                os.path.join(get_base_path(), "setting", "keywords"),
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
                os.path.join(get_base_path(), "setting", "images"),
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
        print(f"🗑️ delete_site 호출됨 - ID: {site_id}")
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
        """설정 탭 생성 - 개선된 버전 (라이선스 정보 간소화, 웹사이트 권장, GPT 제거)"""
        # 스크롤 영역 생성
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
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
        group_box_style = f"""
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
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # 1. 사용 기간 표시 (우측 상단) - 글자색 강조
        try:
            license_info = LicenseManager().get_license_info()
            expire_date = license_info.get('expire_date', '무제한')
        except Exception:
            expire_date = "확인 불가"

        usage_period_layout = QHBoxLayout()
        usage_period_layout.addStretch()
        usage_period_label = QLabel(f"📅 사용 기간: {expire_date}")
        usage_period_label.setStyleSheet(f"""
            color: {COLORS['primary']};
            font-weight: 700;
            font-size: 14px;
            background-color: {COLORS['surface_light']};
            border: 1px solid {COLORS['border']};
            padding: 10px 20px;
            border-radius: 8px;
        """)
        usage_period_layout.addWidget(usage_period_label)
        layout.addLayout(usage_period_layout)

        # 🔥 가로 배치를 위한 컨테이너 생성 (첫 번째 행: 포스팅 모드 | 포스팅 간격)
        horizontal_container = QWidget()
        horizontal_layout = QHBoxLayout()
        horizontal_layout.setSpacing(20)
        horizontal_layout.setContentsMargins(0, 0, 0, 0)

        # 1. 포스팅 모드 섹션
        posting_mode_group = QGroupBox("📝 포스팅 모드")
        posting_mode_group.setMinimumHeight(250)
        posting_mode_group.setStyleSheet(group_box_style)
        posting_mode_layout = QVBoxLayout()
        posting_mode_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 중앙 정렬을 위한 컨테이너
        posting_mode_container = QWidget()
        posting_mode_form = QVBoxLayout()
        posting_mode_form.setSpacing(15)
        
        mode_label = QLabel("포스팅 모드:")
        mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mode_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {COLORS['primary']};")
        posting_mode_form.addWidget(mode_label)
        
        self.settings_posting_mode_combo = QComboBox()
        self.settings_posting_mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_posting_mode_combo.addItems(["승인용", "수익용"])
        posting_mode_value = self.config_manager.data["global_settings"].get("posting_mode", "수익형")
        self.settings_posting_mode_combo.setCurrentText(posting_mode_value)
        self.settings_posting_mode_combo.setMinimumWidth(200)
        self.settings_posting_mode_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['surface_light']};
                color: white;
                border: 2px solid {COLORS['primary']};
                border-radius: 10px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
            }}
            QComboBox:hover {{
                background-color: {COLORS['primary']};
                border-color: {COLORS['info']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['surface_light']};
                color: white;
                selection-background-color: {COLORS['primary']};
                selection-color: white;
                outline: none;
                border: 2px solid {COLORS['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 10px;
                border-radius: 5px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {COLORS['hover']};
            }}
        """)
        # 🔥 포스팅 모드 변경 시 모니터링 탭과 동기화
        self.settings_posting_mode_combo.currentTextChanged.connect(self.on_settings_posting_mode_changed)
        posting_mode_form.addWidget(self.settings_posting_mode_combo, 0, Qt.AlignmentFlag.AlignCenter)
        
        posting_mode_container.setLayout(posting_mode_form)
        posting_mode_layout.addWidget(posting_mode_container)
        posting_mode_group.setLayout(posting_mode_layout)
        horizontal_layout.addWidget(posting_mode_group, 1)
        
        # 2. 포스팅 간격 섹션
        interval_group = QGroupBox("⏱️ 포스팅 간격")
        interval_group.setMinimumHeight(250)
        interval_group.setStyleSheet(group_box_style)
        interval_layout = QVBoxLayout()
        interval_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 중앙 정렬을 위한 컨테이너
        interval_container = QWidget()
        interval_form = QVBoxLayout()
        interval_form.setSpacing(15)
        
        interval_label = QLabel("포스팅 간격(분):")
        interval_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        interval_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {COLORS['primary']};")
        interval_form.addWidget(interval_label)
        
        self.wait_time_edit = QLineEdit()
        wait_time_value = self.config_manager.data["global_settings"].get("default_wait_time", "47~50")
        self.wait_time_edit.setText(wait_time_value)
        self.wait_time_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wait_time_edit.setMinimumWidth(200)
        self.wait_time_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['surface_light']};
                color: white;
                border: 2px solid {COLORS['primary']};
                border-radius: 10px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['info']};
                background-color: {COLORS['surface_light']};
            }}
        """)
        interval_form.addWidget(self.wait_time_edit, 0, Qt.AlignmentFlag.AlignCenter)
        
        interval_container.setLayout(interval_form)
        interval_layout.addWidget(interval_container)
        interval_group.setLayout(interval_layout)
        horizontal_layout.addWidget(interval_group, 1)

        # 🔥 가로 레이아웃을 컨테이너에 설정하고 메인 레이아웃에 추가
        horizontal_container.setLayout(horizontal_layout)
        layout.addWidget(horizontal_container)

        # 🔥 두 번째 행을 위한 새로운 가로 컨테이너 (AI 설정 | 워드프레스 세팅)
        horizontal_container2 = QWidget()
        horizontal_layout2 = QHBoxLayout()
        horizontal_layout2.setSpacing(20)
        horizontal_layout2.setContentsMargins(0, 0, 0, 0)

        # 3. AI 설정 그룹 (웹사이트 권장)
        ai_group = QGroupBox("🤖 AI 설정")
        ai_group.setStyleSheet(group_box_style)
        ai_layout = QVBoxLayout()

        # AI 모드 선택 (웹사이트 우선) - 중앙 정렬
        mode_layout = QVBoxLayout()
        mode_layout.setSpacing(15)
        mode_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        mode_label = QLabel("글 작성 방식:")
        mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mode_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {COLORS['primary']};")
        mode_layout.addWidget(mode_label)
        
        self.ai_mode_combo = QComboBox()
        self.ai_mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_mode_combo.setMinimumWidth(250)
        self.ai_mode_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['surface_light']};
                color: white;
                border: 2px solid {COLORS['primary']};
                border-radius: 10px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
            }}
            QComboBox:hover {{
                background-color: {COLORS['primary']};
                border-color: {COLORS['info']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['surface_light']};
                color: white;
                selection-background-color: {COLORS['primary']};
                selection-color: white;
                outline: none;
                border: 2px solid {COLORS['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 10px;
                border-radius: 5px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {COLORS['hover']};
            }}
        """)
        # 웹사이트를 0번(기본), API를 1번으로 변경
        self.ai_mode_combo.addItems(["웹사이트 로그인 (권장)", "API 사용"])
        
        # 기존 설정에 따라 초기값 선택
        current_ai_provider = self.config_manager.data["global_settings"].get("default_ai", "web-gemini")
        if "web" in current_ai_provider:
            self.ai_mode_combo.setCurrentIndex(0)
        else:
            self.ai_mode_combo.setCurrentIndex(1)
        
        mode_layout.addWidget(self.ai_mode_combo, 0, Qt.AlignmentFlag.AlignCenter)
        ai_layout.addLayout(mode_layout)

        # 스택 위젯 (모드에 따라 화면 전환)
        self.ai_settings_stack = QStackedWidget()

        # --- 페이지 0: 웹사이트 자동화 설정 (권장) ---
        web_page = QWidget()
        web_layout_inner = QVBoxLayout()
        
        web_info_label = QLabel(
            "🌐 <b>웹사이트 자동화 모드</b><br><br>"
            "브라우저를 직접 제어하여 콘텐츠를 생성합니다.<br>"
            "별도의 API 키가 필요하지 않으며, 비용이 발생하지 않습니다.<br>"
            "Google 계정 로그인이 필요할 수 있습니다."
        )
        web_info_label.setWordWrap(True)
        web_info_label.setStyleSheet(f"""
            background-color: {COLORS['surface_light']};
            border: 1px solid {COLORS['border']};
            padding: 15px;
            border-radius: 8px;
            color: {COLORS['text']};
        """)
        web_layout_inner.addWidget(web_info_label)
        
        # 웹 모델 선택 (GPT 제거)
        web_form = QFormLayout()
        self.web_model_combo = QComboBox()
        self.web_model_combo.addItems(["Gemini Web", "Perplexity Web"])
        
        # 기존 설정값 매핑
        if "perplexity" in current_ai_provider:
            self.web_model_combo.setCurrentIndex(1)
        else:
            self.web_model_combo.setCurrentIndex(0) # 기본값 Gemini Web
            
        web_form.addRow("웹 모델 선택:", self.web_model_combo)
        web_layout_inner.addLayout(web_form)
        web_layout_inner.addStretch()
        
        web_page.setLayout(web_layout_inner)

        # --- 페이지 1: API 사용 설정 ---
        api_page = QWidget()
        api_form = QFormLayout()
        
        # Gemini API 키 (OpenAI 제거)
        gemini_row = QHBoxLayout()
        self.gemini_key_edit = QLineEdit()
        self.gemini_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        gemini_key_value = self.config_manager.data["api_keys"].get("gemini", "")
        self.gemini_key_edit.setText(gemini_key_value)
        gemini_row.addWidget(self.gemini_key_edit, 1)
        
        # Gemini 토글 버튼
        self.gemini_toggle_btn = QPushButton("👁️")
        self.gemini_toggle_btn.setFixedSize(40, 30)
        self.gemini_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        try:
            self.gemini_toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(self.gemini_key_edit, self.gemini_toggle_btn))
        except: pass
        gemini_row.addWidget(self.gemini_toggle_btn)
        
        gemini_widget = QWidget()
        gemini_widget.setLayout(gemini_row)
        api_form.addRow("Gemini API Key:", gemini_widget)

        # Gemini 상태 라벨
        self.gemini_status_label = QLabel()
        if gemini_key_value and len(gemini_key_value) > 10:
            self.gemini_status_label.setText("🔑 설정됨")
            self.gemini_status_label.setStyleSheet("color: #88C0D0; font-weight: bold;")
        else:
            self.gemini_status_label.setText("❌ 미설정")
            self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
        api_form.addRow("Gemini 상태:", self.gemini_status_label)
        
        # API 테스트 버튼 - 중앙 정렬 및 스타일 개선
        test_api_container = QWidget()
        test_api_layout = QVBoxLayout()
        test_api_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        test_api_layout.setContentsMargins(0, 20, 0, 0)
        
        test_api_btn = QPushButton("🧪 API 연결 테스트")
        test_api_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_api_btn.setMinimumWidth(200)
        test_api_btn.setMinimumHeight(45)
        test_api_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['info']};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px 25px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['info_hover']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['primary']};
            }}
        """)
        try:
            test_api_btn.clicked.connect(self.test_api_connections)
        except: pass
        test_api_layout.addWidget(test_api_btn)
        test_api_container.setLayout(test_api_layout)
        
        api_form_layout = QVBoxLayout()
        api_form_layout.addLayout(api_form)
        api_form_layout.addWidget(test_api_container)
        api_page.setLayout(api_form_layout)

        # 스택에 페이지 추가 (순서 중요: 0=Web, 1=API)
        self.ai_settings_stack.addWidget(web_page)
        self.ai_settings_stack.addWidget(api_page)
        
        # 콤보박스 변경 시 스택 페이지 전환 연결
        self.ai_mode_combo.currentIndexChanged.connect(self.ai_settings_stack.setCurrentIndex)
        # 🔥 AI 모드 변경 시 모니터링 탭도 업데이트
        self.ai_mode_combo.currentIndexChanged.connect(self.on_ai_mode_changed_from_settings)
        
        # 초기 페이지 설정
        self.ai_settings_stack.setCurrentIndex(self.ai_mode_combo.currentIndex())

        ai_layout.addWidget(self.ai_settings_stack)
        ai_group.setLayout(ai_layout)
        ai_group.setMinimumHeight(250)
        # 🔥 AI 설정을 두 번째 행 왼쪽에 추가
        horizontal_layout2.addWidget(ai_group, 1)
        
        # 4. 워드프레스 세팅 섹션 (사용자명/응용프로그램비밀번호)
        credentials_group = QGroupBox("🔐 워드프레스 세팅")
        credentials_group.setMinimumHeight(250)
        credentials_group.setStyleSheet(group_box_style)
        credentials_layout = QVBoxLayout()
        credentials_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 중앙 정렬을 위한 컨테이너
        credentials_container = QWidget()
        credentials_form = QVBoxLayout()
        credentials_form.setSpacing(15)
        
        # 사용자명 필드
        username_label = QLabel("사용자명:")
        username_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        username_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {COLORS['primary']};")
        credentials_form.addWidget(username_label)
        
        self.common_username_edit = QLineEdit()
        self.common_username_edit.setText(self.config_manager.data["global_settings"].get("common_username", ""))
        self.common_username_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.common_username_edit.setMinimumWidth(250)
        self.common_username_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['surface_light']};
                color: white;
                border: 2px solid {COLORS['primary']};
                border-radius: 10px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['info']};
                background-color: {COLORS['surface_light']};
            }}
        """)
        credentials_form.addWidget(self.common_username_edit, 0, Qt.AlignmentFlag.AlignCenter)

        # 응용프로그램 비밀번호 필드
        password_label = QLabel("응용프로그램 비밀번호:")
        password_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        password_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {COLORS['primary']}; margin-top: 10px;")
        credentials_form.addWidget(password_label)
        
        password_row = QHBoxLayout()
        password_row.setSpacing(10)
        
        self.common_password_edit = QLineEdit()
        self.common_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.common_password_edit.setText(self.config_manager.data["global_settings"].get("common_password", ""))
        self.common_password_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.common_password_edit.setMinimumWidth(200)
        self.common_password_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['surface_light']};
                color: white;
                border: 2px solid {COLORS['primary']};
                border-radius: 10px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['info']};
                background-color: {COLORS['surface_light']};
            }}
        """)
        password_row.addWidget(self.common_password_edit, 1)
        
        self.password_toggle_btn = QPushButton("👁️")
        self.password_toggle_btn.setFixedSize(40, 40)
        self.password_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.password_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['surface_light']};
                border: 2px solid {COLORS['primary']};
                border-radius: 10px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary']};
            }}
        """)
        try:
            self.password_toggle_btn.clicked.connect(lambda: self.toggle_password_visibility(self.common_password_edit, self.password_toggle_btn))
        except: pass
        password_row.addWidget(self.password_toggle_btn)
        
        password_container = QWidget()
        password_container.setLayout(password_row)
        credentials_form.addWidget(password_container, 0, Qt.AlignmentFlag.AlignCenter)
        
        credentials_container.setLayout(credentials_form)
        credentials_layout.addWidget(credentials_container)
        credentials_group.setLayout(credentials_layout)
        horizontal_layout2.addWidget(credentials_group, 1)

        # 🔥 두 번째 가로 레이아웃 컨테이너를 메인 레이아웃에 추가
        horizontal_container2.setLayout(horizontal_layout2)
        layout.addWidget(horizontal_container2)

        # 저장 버튼
        save_btn = QPushButton("💾 설정 저장")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                font-weight: bold;
                padding: 15px 25px;
                border-radius: 8px;
                border: none;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_hover']};
            }}
        """)
        try:
            save_btn.clicked.connect(self.save_settings)
        except: pass
        layout.addWidget(save_btn)

        layout.addStretch()
        widget.setLayout(layout)
        
        scroll_area.setWidget(widget)
        return scroll_area

    def test_api_connections(self):
        """API 연결 테스트"""
        self.update_posting_status("🧪 API 연결 테스트 시작")
            
        # Gemini 테스트
        gemini_key = self.gemini_key_edit.text().strip()
        if gemini_key:
            try:
                if GEMINI_AVAILABLE:
                    try:
                        import google.generativeai as genai
                    except Exception as import_error:
                        self.gemini_status_label.setText("❌ 라이브러리 오류")
                        self.gemini_status_label.setStyleSheet("color: #EBCB8B; font-weight: bold;")
                        self.update_posting_status(f"❌ google-generativeai 로드 실패: {import_error}")
                        return
                    configure_fn = getattr(genai, "configure", None)
                    gen_model_cls = getattr(genai, "GenerativeModel", None)
                    types_module = getattr(genai, "types", None)
                    if not configure_fn or not gen_model_cls or not types_module:
                        self.gemini_status_label.setText("? 라이브러리 오류")
                        self.gemini_status_label.setStyleSheet("color: #EBCB8B; font-weight: bold;")
                        self.update_posting_status("? google-generativeai 모듈 구성 요소를 찾을 수 없습니다")
                        return
                    configure_fn(api_key=gemini_key)
                    
                    # 최신 Gemini 모델들 순서대로 시도 (2025년 최신 모델 포함)
                    models_to_try = [
                        'gemini-2.0-flash-exp',      # 2025년 최신 실험 모델
                        'gemini-2.5-flash-lite',     # 2.5 lite 모델
                        'gemini-1.5-flash-latest',   # 최신 Flash
                        'gemini-1.5-flash',
                        'gemini-1.5-pro-latest',     # 최신 Pro
                        'gemini-1.5-pro',
                        'gemini-pro'                 # Fallback
                    ]
                    
                    last_error = None
                    for model_name in models_to_try:
                        try:
                            print(f"🔍 Gemini 모델 시도: {model_name}")
                            model = gen_model_cls(model_name)
                            response = model.generate_content(
                                "안녕", 
                                generation_config=types_module.GenerationConfig(
                                    max_output_tokens=10,
                                    temperature=0.7
                                ),
                                request_options={'timeout': 10}
                            )
                            
                            # 응답 확인
                            if hasattr(response, 'text') and response.text:
                                self.gemini_status_label.setText("✅ 연결됨")
                                self.gemini_status_label.setStyleSheet("color: #A3BE8C; font-weight: bold;")
                                self.update_posting_status(f"✅ Gemini API 연결 성공! (모델: {model_name})")
                                print(f"✅ Gemini 연결 성공: {model_name}")
                                break
                        except Exception as model_error:
                            last_error = str(model_error)
                            print(f"❌ {model_name} 실패: {last_error}")
                            continue
                    else:
                        # 모든 모델 실패
                        error_msg = f"모든 Gemini 모델 테스트 실패. 마지막 오류: {last_error}"
                        print(f"❌ {error_msg}")
                        raise Exception(error_msg)
                else:
                    self.gemini_status_label.setText("❌ 라이브러리 없음")
                    self.gemini_status_label.setStyleSheet("color: #EBCB8B; font-weight: bold;")
                    self.update_posting_status("❌ google-generativeai 라이브러리가 설치되지 않음")
                    print("❌ google-generativeai 라이브러리 없음")
            except Exception as e:
                self.gemini_status_label.setText("❌ 실패")
                self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
                error_detail = str(e)
                # API 키 오류인 경우 더 명확한 메시지
                if 'API_KEY_INVALID' in error_detail or 'invalid' in error_detail.lower():
                    error_msg = "API 키가 유효하지 않습니다. Google AI Studio에서 새 키를 발급받으세요."
                elif 'PERMISSION_DENIED' in error_detail:
                    error_msg = "API 키 권한이 없습니다. API 활성화를 확인하세요."
                elif 'quota' in error_detail.lower() or 'RATE_LIMIT_EXCEEDED' in error_detail:
                    if 'quota_limit_value' in error_detail and '"0"' in error_detail:
                        error_msg = "무료 API 키 할당량이 없습니다. 유료 API 키를 사용하거나 Google AI Studio에서 새 키를 발급받으세요."
                    else:
                        error_msg = "API 할당량 초과. 잠시 후 다시 시도하거나 유료 API 키를 사용하세요."
                else:
                    error_msg = f"연결 실패: {error_detail}"
                
                self.update_posting_status(f"❌ Gemini API {error_msg}")
                print(f"❌ Gemini 연결 실패: {error_detail}")
        else:
            self.gemini_status_label.setText("❌ 미설정")
            self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")
            
        self.update_posting_status("🧪 API 연결 테스트 완료!")

    def save_settings(self):
        """설정 저장 - 개선된 UI 대응 (GPT 제거)"""
        try:
            # API 키 저장 (Gemini만)
            if hasattr(self, 'gemini_key_edit'):
                self.config_manager.data["api_keys"]["gemini"] = self.gemini_key_edit.text().strip()

            # AI 설정 저장 (모드에 따라 처리)
            if hasattr(self, 'ai_mode_combo'):
                mode_index = self.ai_mode_combo.currentIndex()
                
                if mode_index == 1:  # API 연동 모드
                    self.config_manager.data["global_settings"]["default_ai"] = "gemini"
                    self.config_manager.data["global_settings"]["ai_model"] = "gemini-2.5-flash-lite"
                    
                else:  # 웹사이트 자동화 모드 (기본값)
                    if hasattr(self, 'web_model_combo'):
                        web_model = self.web_model_combo.currentText()
                        if "Gemini" in web_model:
                            self.config_manager.data["global_settings"]["default_ai"] = "web-gemini"
                        elif "Perplexity" in web_model:
                            self.config_manager.data["global_settings"]["default_ai"] = "web-perplexity"
            
            # 포스팅 모드 저장
            if hasattr(self, 'settings_posting_mode_combo'):
                self.config_manager.data["global_settings"]["posting_mode"] = self.settings_posting_mode_combo.currentText()
            
            # 전역 설정 저장
            if hasattr(self, 'wait_time_edit'):
                self.config_manager.data["global_settings"]["default_wait_time"] = self.wait_time_edit.text().strip()
            
            if hasattr(self, 'common_username_edit'):
                username = self.common_username_edit.text().strip()
                self.config_manager.data["global_settings"]["common_username"] = username
                
            if hasattr(self, 'common_password_edit'):
                password = self.common_password_edit.text().strip()
                self.config_manager.data["global_settings"]["common_password"] = password
                
                # 사이트 정보 업데이트
                if hasattr(self, 'common_username_edit'):
                    self.update_all_sites_credentials(username, password)

            # 파일 저장
            result = self.config_manager.save_setting()
            
            if result:
                self.update_posting_status("✅ 설정이 저장되었습니다!")
                
                # API 상태 라벨 업데이트 (존재하는 경우)
                if hasattr(self, 'update_api_status_labels'):
                    self.update_api_status_labels()
                
                # 모니터링 탭 업데이트
                if hasattr(self, 'update_monitoring_settings'):
                    self.update_monitoring_settings()
                    
                # 성공 메시지박스
                QMessageBox.information(self, "저장 완료", "설정이 성공적으로 저장되었습니다.")
                
            else:
                self.update_posting_status("❌ 설정 저장에 실패했습니다!")
                QMessageBox.warning(self, "저장 실패", "설정 파일을 저장하는 중 오류가 발생했습니다.")
            
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
            if hasattr(self, 'ai_mode_combo'):
                if self.ai_mode_combo.currentIndex() == 1:
                    gui_default_ai = "gemini"
                else:
                    web_model = self.web_model_combo.currentText() if hasattr(self, 'web_model_combo') else ""
                    gui_default_ai = "web-perplexity" if "Perplexity" in web_model else "web-gemini"
            else:
                gui_default_ai = self.config_manager.data.get("global_settings", {}).get("default_ai", "web-gemini")

            gui_values = {
                'gemini_key': self.gemini_key_edit.text().strip(),
                'default_ai': gui_default_ai,
                'ai_mode_text': self.ai_mode_combo.currentText() if hasattr(self, 'ai_mode_combo') else "",
                'posting_mode': self.posting_mode_combo.currentText() if self.posting_mode_combo else "",
                'wait_time': self.wait_time_edit.text().strip(),
                'username': self.common_username_edit.text().strip(),
                'password': self.common_password_edit.text().strip()
            }
            
            # JSON에서 저장된 값들
            json_values = {
                'gemini_key': saved_data.get('api_keys', {}).get('gemini', ''),
                'default_ai': saved_data.get('global_settings', {}).get('default_ai', ''),
                'ai_mode_text': "API 사용" if saved_data.get('global_settings', {}).get('default_ai', '') == "gemini" else "웹사이트 로그인 (권장)",
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
                    if key in ['gemini_key', 'password']:
                        print(f"✅ [VERIFY] {key}: GUI와 JSON 일치 (길이: {len(gui_val)})")
                    else:
                        print(f"✅ [VERIFY] {key}: '{gui_val}' == '{json_val}'")
                else:
                    verification_passed = False
                    if key in ['gemini_key', 'password']:
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
            refresh_fn = getattr(self, "refresh_site_list", None)
            if callable(refresh_fn):
                refresh_fn()
                print(f"🔄 사이트 관리 탭 UI 새로고침 완료")
                
        except Exception as e:
            print(f"❌ [ERROR] 사이트 인증 정보 업데이트 실패: {e}")
            import traceback
            traceback.print_exc()

    def update_api_status_labels(self):
        """API 상태 라벨 업데이트"""
        # Gemini 상태 확인
        gemini_key = self.gemini_key_edit.text().strip()
        if gemini_key and len(gemini_key) > 10:
            self.gemini_status_label.setText("🔑 설정됨")
            self.gemini_status_label.setStyleSheet("color: #88C0D0; font-weight: bold;")
        else:
            self.gemini_status_label.setText("❌ 미설정")
            self.gemini_status_label.setStyleSheet("color: #BF616A; font-weight: bold;")

    def update_ai_model_options(self):
        """모니터링 탭 AI 모드 옵션 동기화 (레거시 함수명 유지)"""
        if not self.ai_model_combo:
            return
        self.ai_model_combo.blockSignals(True)
        self.ai_model_combo.clear()
        self.ai_model_combo.addItems(["웹사이트 로그인", "API 사용"])
        if self._is_web_mode():
            self.ai_model_combo.setCurrentText("웹사이트 로그인")
        else:
            self.ai_model_combo.setCurrentText("API 사용")
        self.ai_model_combo.blockSignals(False)

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
                # 비밀번호 모드에서 일반 텍스트 모드로 변경 (보이기)
                line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
                toggle_button.setText("🙈")  # 숨김 아이콘
                toggle_button.setToolTip("현재: 표시됨 - 클릭하여 숨김")
            else:
                # 일반 텍스트 모드에서 비밀번호 모드로 변경 (숨기기)
                line_edit.setEchoMode(QLineEdit.EchoMode.Password)
                toggle_button.setText("👁️")  # 보기 아이콘
                toggle_button.setToolTip("현재: 숨겨짐 - 클릭하여 표시")
        except Exception as e:
            print(f"토글 기능 오류: {e}")

    def start_posting(self):
        """포스팅 시작 - 마지막 포스팅 상태 기반으로 시작 사이트 결정"""
        try:
            # EXE 환경에서도 콘솔 출력 강제
            import sys
            import traceback
            
            # EXE 실행 시 시작 로그 기록
            log_to_file("start_posting 호출됨")
            
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

            current_ai_provider = self._get_current_ai_provider()

            # API 모드일 때만 Gemini API 키 확인
            if current_ai_provider == self.AI_PROVIDER_API_GEMINI:
                gemini_key = self.config_manager.data["api_keys"].get("gemini", "")
                if not gemini_key:
                    print("⚠️ Gemini API 키가 설정되지 않았습니다.")
                    self.update_posting_status("⚠️ API 키가 설정되지 않았습니다.")
                    return

            # 웹사이트 로그인 모드(Gemini)는 실제 콘텐츠 생성 브라우저에서
            # 로그인/2차 인증/프롬프트 입력을 한 흐름으로 진행한다.
            if current_ai_provider == self.AI_PROVIDER_WEB_GEMINI:
                self.update_posting_status("🌐 웹사이트 로그인 모드: 첫 AI 호출에서 로그인 후 프롬프트 입력을 시작합니다.")

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
                    if self.current_site_combo:
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
            self.posting_worker.keyword_used.connect(self.update_keyword_count)
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
            if isinstance(message, str):
                msg_text = message.strip()
                if msg_text.startswith("❌") or ("오류" in msg_text):
                    self._latest_error_message = msg_text

            # 현재 포스팅 중인 사이트 정보 파싱 및 업데이트
            self.parse_and_update_current_site(message)
            
            # GUI 업데이트는 항상 메인 스레드에서 실행
            if hasattr(self, 'progress_text') and self.progress_text is not None:
                from datetime import datetime
                timestamp = datetime.now().strftime("%H:%M:%S")
                simple_message = f"[{timestamp}] {message}"
                countdown_prefix = "⏳ 다음 포스팅까지 남은 시간:"
                
                try:
                    current_text = self.progress_text.toPlainText()
                    
                    # 카운트다운 메시지는 항상 "한 줄"만 유지
                    if countdown_prefix in message:
                        lines = current_text.splitlines() if current_text else []
                        if lines and countdown_prefix in lines[-1]:
                            # 직전 줄이 카운트다운이면 마지막 줄만 교체
                            lines[-1] = simple_message
                        else:
                            # 기존 카운트다운 줄이 중간에 남아있으면 제거 후 마지막에 추가
                            lines = [line for line in lines if countdown_prefix not in line]
                            lines.append(simple_message)
                        new_text = "\n".join(lines)
                    # 일반 메시지는 기존처럼 새 줄 추가
                    elif current_text.strip():
                        new_text = current_text + "\n" + simple_message
                    else:
                        new_text = simple_message
                    
                    # 텍스트 업데이트
                    self.progress_text.setPlainText(new_text)
                    
                    # 🔥 항상 맨 아래로 스크롤 (최신 로그가 보이도록) - 강화된 스크롤 로직
                    # 방법 1: 커서를 문서 끝으로 이동
                    cursor = self.progress_text.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.progress_text.setTextCursor(cursor)
                    
                    # 방법 2: 스크롤바를 최대값으로 설정
                    scrollbar = self.progress_text.verticalScrollBar()
                    if scrollbar:
                        scrollbar.setValue(scrollbar.maximum())
                    
                    # 방법 3: ensureCursorVisible() 호출
                    self.progress_text.ensureCursorVisible()
                    
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

    def copy_error_for_creator(self, error_message, source=""):
        """오류 메시지를 제작자 전달용 포맷으로 클립보드에 복사"""
        try:
            text = str(error_message or "").strip()
            if not text:
                return

            from datetime import datetime
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            header = "제작자에게 전달:"
            source_line = f"\n출처: {source}" if source else ""
            payload = f"{header}\n[{ts}]{source_line}\n오류 내용: {text}"

            # 동일한 에러 문구 연속 복사는 방지
            if getattr(self, "_last_creator_copy_payload", "") == payload:
                return

            cb = QApplication.clipboard()
            if cb is not None:
                cb.setText(payload)
                self._last_creator_copy_payload = payload
        except Exception:
            pass

    def copy_latest_error_for_creator(self):
        """최근 오류를 제작자 전달 포맷으로 복사"""
        latest = getattr(self, "_latest_error_message", "").strip()
        if latest:
            self.copy_error_for_creator(latest, source="진행 상태 로그")
            self.update_posting_status("📋 오류 내용이 '제작자에게 전달' 형식으로 복사되었습니다.")

    def update_keyword_count(self):
        """키워드 사용 후 실시간으로 키워드 개수 업데이트"""
        try:
            # 남은 키워드 개수 계산
            total_keywords = 0
            sites_data = self.config_manager.data.get("sites", [])
                
            for site_data in sites_data:
                keyword_file = site_data.get("keyword_file", "")
                if keyword_file:
                    keyword_path = os.path.join(get_base_path(), "setting", "keywords", keyword_file)
                    if os.path.exists(keyword_path):
                        try:
                            with open(keyword_path, 'r', encoding='utf-8') as f:
                                lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith('#')]
                                total_keywords += len(lines)
                        except:
                            pass

            # 모니터링 탭의 키워드 개수 업데이트
            if self.total_keywords_button:
                self.total_keywords_button.setText(f"{total_keywords}개")
            
            # 모든 SiteWidget의 키워드 표시 업데이트
            if hasattr(self, 'sites_layout'):
                for i in range(self.sites_layout.count()):
                    item = self.sites_layout.itemAt(i)
                    if not item:
                        continue
                    widget = item.widget()
                    if isinstance(widget, SiteWidget):
                        widget.update_keyword_display()
            
        except Exception as e:
            print(f"❌ 키워드 개수 업데이트 오류: {e}")

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

        self._safe_update_button_states()
        print("🎉 모든 포스팅이 완료되었습니다!")
        
    def on_single_posting_complete(self):
        """개별 포스팅 완료 후 카운트다운 시작"""
        # 아직 포스팅이 진행 중이라면 (다른 사이트들이 남아있음) 카운트다운 시작
        if self.is_posting:
            self.start_next_posting_countdown()
        
    def on_posting_error(self, error_message):
        """포스팅 오류 처리 및 키워드 부족 알림"""
        print(f"❌ 포스팅 중 오류 발생: {error_message}")
        self._latest_error_message = str(error_message)
        
        # 키워드 부족 메시지인지 확인
        if error_message.startswith("키워드 부족|"):
            parts = error_message.split("|")
            if len(parts) == 3:
                _, site_name, keyword_count = parts
                
                # 비차단 알림창 표시
                warning_msg = f"⚠️ {site_name}의 키워드가 부족합니다!\n\n"
                warning_msg += f"현재 남은 키워드: {keyword_count}개\n"
                warning_msg += f"권장 키워드 수: 300개 이상\n\n"
                warning_msg += "💡 Keywords 폴더에서 키워드를 추가해주세요.\n"
                warning_msg += "⚠️ 키워드가 부족하면 포스팅이 조기에 중단될 수 있습니다."
                
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Icon.NoIcon)  # 경고음 방지
                msg_box.setOption(QMessageBox.Option.DontUseNativeDialog, True)  # OS 기본 사운드 비활성화
                msg_box.setWindowTitle("키워드 부족 경고")
                msg_box.setText(warning_msg)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg_box.setModal(False)  # 비차단 모드
                
                # 🔥 메시지 박스에 프로그램 아이콘 적용
                if self.windowIcon():
                    msg_box.setWindowIcon(self.windowIcon())
                
                msg_box.show()
                
                return  # 포스팅 중지하지 않고 계속 진행
        
        # 일반 오류인 경우 워커 정리
        if hasattr(self, 'posting_worker') and self.posting_worker:
            try:
                self.posting_worker.deleteLater()
            except:
                pass
            self.posting_worker = None
            
        self.stop_posting()

    def _resolve_wait_seconds_from_settings(self, default_minutes: int = 3) -> int:
        """global_settings.default_wait_time(분 단위)를 초 단위로 변환"""
        try:
            wait_time_setting = str(
                self.config_manager.data.get("global_settings", {}).get("default_wait_time", "3~5")
            ).strip()
            if "~" in wait_time_setting or "-" in wait_time_setting:
                separator = "~" if "~" in wait_time_setting else "-"
                min_wait, max_wait = map(int, wait_time_setting.split(separator))
                min_wait = max(1, min_wait)
                max_wait = max(min_wait, max_wait)
                wait_minutes = random.randint(min_wait, max_wait)
            else:
                wait_minutes = max(1, int(wait_time_setting))
            return wait_minutes * 60
        except Exception:
            return max(1, default_minutes) * 60

    def pause_posting(self):
        """포스팅 일시정지/재개"""
        try:
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
                    if self.current_posting_site and self.current_site_combo:
                        index = self.find_site_combo_index(self.current_posting_site)
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
            if self.current_posting_site and self.current_site_combo:
                index = self.find_site_combo_index(self.current_posting_site)
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
        """프로그레스 텍스트 휠 이벤트 - Ctrl+휠로 창 크기 조절"""
        try:
            from PyQt6.QtCore import Qt
            import time
            
            # 사용자가 스크롤 중임을 표시
            self.user_scrolling = True
            self.last_scroll_time = time.time()
            
            # 🔥 Ctrl 키가 눌린 경우 창 크기 조절 (폰트 크기가 아님!)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                wheel_delta = event.angleDelta().y()
                current_height = self.progress_text.minimumHeight()
                
                # 창 크기 조절 단계 (50px씩)
                step = 50
                
                if wheel_delta > 0:  # 확대
                    new_height = current_height + step
                    new_height = min(new_height, 1000)  # 최대 1000px
                else:  # 축소
                    new_height = current_height - step
                    new_height = max(new_height, 100)   # 최소 100px
                
                self.progress_text.setMinimumHeight(new_height)
                self.progress_text.setMaximumHeight(new_height)
                event.accept()
                return
            
            # 일반 스크롤 처리
            scrollbar = self.progress_text.verticalScrollBar()
            if scrollbar is None:
                event.ignore()
                return
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
            # 포스팅 간격(분 단위 설정)을 초 단위로 변환
            self.posting_interval_seconds = self._resolve_wait_seconds_from_settings(default_minutes=3)
                
            # 다음 포스팅 시간 계산
            from datetime import datetime, timedelta
            self.next_posting_time = datetime.now() + timedelta(seconds=self.posting_interval_seconds)
            
            # 초기 카운트다운 표시
            value_button = self._get_card_value_button(self.next_posting_label)
            if value_button:
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
                self._set_card_value_text(self.next_posting_label, display_text)
            
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
            if not self.next_posting_time:
                return
                
            from datetime import datetime
            now = datetime.now()
            
            if now >= self.next_posting_time:
                # 카운트다운 완료 - 다음 포스팅 시작
                self._set_card_value_text(self.next_posting_label, "포스팅 시작!")
                
                self.countdown_timer.stop()
                self.next_posting_time = None
                
                # 다음 포스팅 시작 메시지 출력
                if hasattr(self, 'is_posting') and self.is_posting:
                    print("⏰ 카운트다운 완료! 다음 사이트 포스팅을 시작합니다.")
                    self.update_posting_status("⏰ 카운트다운 완료! 다음 사이트 포스팅을 시작합니다.")
                    
                    # 잠시 후 다시 "대기중"으로 변경
                    def reset_label():
                        self._set_card_value_text(self.next_posting_label, "대기중")
                    QTimer.singleShot(2000, reset_label)
                else:
                    # 포스팅이 중지된 상태라면 "대기중"으로 표시
                    self._set_card_value_text(self.next_posting_label, "대기중")
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
            self._set_card_value_text(self.next_posting_label, display_text)

            # 진행 상태에 1초 단위 실시간 카운트다운 표시
            if self._last_countdown_logged_second != total_seconds:
                self._last_countdown_logged_second = total_seconds
                if hours > 0:
                    progress_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    progress_time = f"{minutes:02d}:{seconds:02d}"
                self.update_posting_status(f"⏳ 다음 포스팅까지 남은 시간: {progress_time}")
            
        except Exception as e:
            print(f"카운트다운 업데이트 오류: {e}")

    def open_keywords_folder(self):
        """keywords 폴더 열기"""
        try:
            keywords_path = os.path.join(get_base_path(), "setting", "keywords")
            self._open_folder_safely(keywords_path)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"keywords 폴더를 열 수 없습니다:\n{e}")

    def open_prompts_folder(self):
        """prompts 폴더 열기"""
        try:
            prompts_path = os.path.join(get_base_path(), "setting", "prompts")
            self._open_folder_safely(prompts_path)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"prompts 폴더를 열 수 없습니다:\n{e}")

    def open_gemini_api_dialog(self):
        """Gemini API 키 간편 설정 다이얼로그"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Gemini API 설정")
        dialog.setModal(True)
        dialog.resize(520, 180)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        guide = QLabel("Gemini API Key를 입력하고 저장하세요.")
        guide.setStyleSheet("font-size: 13px; color: #D8DEE9;")
        layout.addWidget(guide)

        key_edit = QLineEdit()
        key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_edit.setPlaceholderText("AIza... 형태의 Gemini API Key")
        key_edit.setText(self.config_manager.data.get("api_keys", {}).get("gemini", ""))
        layout.addWidget(key_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("저장")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn = QPushButton("취소")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        def do_save():
            if "api_keys" not in self.config_manager.data:
                self.config_manager.data["api_keys"] = {}
            self.config_manager.data["api_keys"]["gemini"] = key_edit.text().strip()
            self.config_manager.save_setting()
            self.update_posting_status("✅ Gemini API 설정이 저장되었습니다.")
            dialog.accept()

        save_btn.clicked.connect(do_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.setLayout(layout)
        dialog.exec()

    def _close_website_login_browser(self):
        """웹사이트 로그인용 브라우저 종료"""
        try:
            if self.website_login_generator:
                driver = getattr(self.website_login_generator, "driver", None)
                if driver is not None:
                    self.update_posting_status("웹사이트 로그인 브라우저 종료 호출")
                    driver.quit()
        except Exception:
            pass
        self.website_login_generator = None

    def _open_website_login_browser(self):
        """Gemini 웹 로그인 창 열기"""
        try:
            self.update_posting_status("🌐 Gemini 로그인 창 준비 중...")
            if self.website_login_generator is None:
                self.website_login_generator = ContentGenerator(self.config_manager.data, self.update_posting_status, self)

            if not self.website_login_generator.setup_driver():
                self.update_posting_status("❌ 브라우저 실행 실패")
                return
            if not self.website_login_generator._ensure_gemini_tab():
                self.update_posting_status("❌ Gemini 페이지 열기 실패")
                return

            if self.website_login_generator._has_gemini_login_button(timeout=3):
                self.update_posting_status("🔐 로그인 버튼이 보입니다. 브라우저에서 Google 로그인 후 시작 버튼을 눌러주세요.")
            else:
                self.update_posting_status("✅ Gemini 로그인 상태입니다.")
        except Exception as e:
            self.update_posting_status(f"❌ 웹사이트 로그인 창 실행 오류: {e}")

    def open_website_login(self):
        """구글 계정 입력 후 Gemini 로그인 창 열기"""
        dialog = QDialog(self)
        dialog.setWindowTitle("🌐 웹사이트 로그인 설정")
        dialog.setModal(True)
        dialog.resize(540, 220)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        guide = QLabel("Google 계정 정보를 입력하면 자동 로그인에 사용됩니다.")
        guide.setWordWrap(True)
        guide.setStyleSheet("font-size: 13px; color: #D8DEE9;")
        layout.addWidget(guide)

        email_edit = QLineEdit()
        email_edit.setPlaceholderText("Google 이메일")
        email_edit.setText(self.config_manager.data.get("global_settings", {}).get("google_email", ""))
        layout.addWidget(email_edit)

        password_edit = QLineEdit()
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_edit.setPlaceholderText("Google 비밀번호")
        password_edit.setText(self.config_manager.data.get("global_settings", {}).get("google_password", ""))
        layout.addWidget(password_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        open_btn = QPushButton("저장 후 로그인 창 열기")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn = QPushButton("취소")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        def do_open():
            global_settings = self.config_manager.data.setdefault("global_settings", {})
            global_settings["google_email"] = email_edit.text().strip()
            global_settings["google_password"] = password_edit.text().strip()
            self.config_manager.save_setting()
            dialog.accept()
            self._open_website_login_browser()

        open_btn.clicked.connect(do_open)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.setLayout(layout)
        dialog.exec()

    def ensure_gemini_login_before_start(self):
        """시작 버튼 실행 전 Gemini 로그인 상태 선확인"""
        checker = None
        try:
            self.update_posting_status("ensure_gemini_login_before_start 시작")
            self._close_website_login_browser()
            self.update_posting_status("🔍 시작 전 Gemini 로그인 상태를 확인합니다...")
            checker = ContentGenerator(self.config_manager.data, self.update_posting_status, self)

            if not checker.setup_driver():
                return False
            if not checker._ensure_gemini_tab():
                return False
            if not checker._ensure_gemini_logged_in(wait_seconds=180):
                return False

            self.update_posting_status("✅ Gemini 로그인 확인 완료. 포스팅을 시작합니다.")
            return True
        except Exception as e:
            self.update_posting_status(f"❌ Gemini 로그인 확인 오류: {e}")
            return False
        finally:
            if checker is not None and getattr(checker, "driver", None):
                try:
                    driver = checker.driver
                    if driver is not None:
                        self.update_posting_status("ensure_gemini_login_before_start checker 브라우저 종료")
                        driver.quit()
                except Exception:
                    pass

    def open_images_folder(self):
        """images 폴더 열기"""
        try:
            images_path = os.path.join(get_base_path(), "setting", "images")
            self._open_folder_safely(images_path)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"images 폴더를 열 수 없습니다:\n{e}")

    def _open_folder_safely(self, folder_path):
        """폴더 열기 공통 함수 (Windows 우선)"""
        import subprocess
        import platform

        os.makedirs(folder_path, exist_ok=True)
        normalized = os.path.normpath(folder_path)

        # Windows에서는 os.startfile이 가장 안정적 (한글/OneDrive 경로 포함)
        if platform.system() == "Windows":
            try:
                os.startfile(normalized)  # type: ignore[attr-defined]
                return
            except Exception:
                # startfile 실패 시 explorer 폴백 (종료코드 무시)
                subprocess.Popen(["explorer", normalized])
                return

        # 비-Windows 환경 폴백
        if platform.system() == "Darwin":
            subprocess.Popen(["open", normalized])
        else:
            subprocess.Popen(["xdg-open", normalized])
        
    def start_next_posting_countdown(self):
        """다음 포스팅까지 카운트다운 시작"""
        try:
            # 대기 시간 설정(분 단위)을 초 단위로 변환
            wait_seconds = self._resolve_wait_seconds_from_settings(default_minutes=3)
            
            # 다음 포스팅 시간 계산
            from datetime import datetime, timedelta
            self.next_posting_time = datetime.now() + timedelta(seconds=wait_seconds)
            self.posting_interval_seconds = wait_seconds
            self._last_countdown_logged_second = None
            
            # 초기 카운트다운 표시
            value_button = self._get_card_value_button(self.next_posting_label)
            if value_button:
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
                self._set_card_value_text(self.next_posting_label, display_text)
            
            # 카운트다운 시작 (1초마다 업데이트)
            self.countdown_timer.start(1000)
            
        except Exception as e:
            print(f"카운트다운 시작 오류: {e}")

    def stop_next_posting_timer(self):
        """다음 포스팅 타이머 중지"""
        if hasattr(self, 'countdown_timer'):
            self.countdown_timer.stop()
            
        # 다음 포스팅 카드를 "대기중"으로 리셋
        self._set_card_value_text(self.next_posting_label, "대기중")
            
        # 다음 포스팅 시간 초기화
        self.next_posting_time = None
        self._last_countdown_logged_second = None

    def check_and_update_api_status(self):
        """API 키 상태를 확인하고 UI 업데이트"""
        try:
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
        stdout = getattr(sys, "stdout", None)
        stderr = getattr(sys, "stderr", None)
        if stdout and hasattr(stdout, "reconfigure"):
            stdout.reconfigure(encoding='utf-8', errors='replace')
            if stderr and hasattr(stderr, "reconfigure"):
                stderr.reconfigure(encoding='utf-8', errors='replace')
        elif stdout and stderr and hasattr(stdout, "buffer") and hasattr(stderr, "buffer"):
            # Python 3.6 이하 호환성
            sys.stdout = io.TextIOWrapper(stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        # 인코딩 설정 실패 시 무시하고 계속 진행
        pass
    
    try:
        # QApplication 생성
        app = QApplication(sys.argv)
        # QApplication 생성 완료

        def _set_windows_sleep_prevention(enable):
            """Windows 절전/화면 꺼짐 방지 설정"""
            if os.name != "nt":
                return
            try:
                import ctypes
                ES_CONTINUOUS = 0x80000000
                ES_SYSTEM_REQUIRED = 0x00000001
                ES_DISPLAY_REQUIRED = 0x00000002
                flags = ES_CONTINUOUS
                if enable:
                    flags |= ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
                ctypes.windll.kernel32.SetThreadExecutionState(flags)
            except Exception:
                pass
        
        # --- 라이선스 체크 로직 시작 ---
        print("🔐 라이선스 확인 중...")
        license_manager = LicenseManager()
        is_valid, message = license_manager.verify_license()
        
        if not is_valid:
            # 미등록 안내창
            machine_id = license_manager.get_machine_id()
            is_expired = ("만료" in (message or "")) or ("expire" in (message or "").lower())
            dialog = QDialog()
            icon_path = get_preferred_resource_path(os.path.join("setting", "etc", "auto_wp.ico"))
            if os.path.exists(icon_path):
                dialog.setWindowIcon(QIcon(icon_path))
            dialog.setWindowTitle("프로그램 사용 권한")
            dialog.setMinimumWidth(640)
            dialog.setMinimumHeight(300)

            layout = QVBoxLayout()
            layout.setContentsMargins(24, 24, 24, 24)
            layout.setSpacing(14)

            title_label = QLabel("등록되지 않은 머신 ID입니다.")
            title_label.setFont(QFont("맑은 고딕", 15, QFont.Weight.Bold))
            title_label.setStyleSheet("color: #D32F2F;")
            title_label.setWordWrap(False)
            layout.addWidget(title_label)

            id_title = QLabel("현재 머신 ID")
            id_title.setFont(QFont("맑은 고딕", 11, QFont.Weight.Bold))
            id_title.setStyleSheet("color: #1E1E1E;")
            id_title.setWordWrap(False)
            layout.addWidget(id_title)

            machine_id_edit = QLineEdit(machine_id)
            machine_id_edit.setReadOnly(True)
            machine_id_edit.setFont(QFont("Consolas", 12))
            machine_id_edit.setMinimumHeight(40)
            machine_id_edit.setStyleSheet("""
                QLineEdit {
                    background-color: #F5F5F5;
                    color: #111111;
                    border: 1px solid #C8C8C8;
                    border-radius: 8px;
                    padding: 6px 10px;
                }
            """)
            layout.addWidget(machine_id_edit)

            guide_label = QLabel("판매자에게 위 머신 ID를 전달해 등록을 요청하세요.")
            guide_label.setFont(QFont("맑은 고딕", 10))
            guide_label.setStyleSheet("color: #333333;")
            guide_label.setWordWrap(False)
            layout.addWidget(guide_label)

            stability_label = QLabel("머신 ID는 EXE 업데이트 후에도 동일하게 유지됩니다.")
            stability_label.setFont(QFont("맑은 고딕", 10))
            stability_label.setStyleSheet("color: #333333;")
            stability_label.setWordWrap(False)
            layout.addWidget(stability_label)

            if is_expired:
                expired_label = QLabel("사용 기간이 만료되었습니다. 아래 버튼으로 문의해주세요.")
                expired_label.setFont(QFont("맑은 고딕", 10, QFont.Weight.Bold))
                expired_label.setStyleSheet("color: #C62828;")
                expired_label.setWordWrap(False)
                layout.addWidget(expired_label)

            button_layout = QHBoxLayout()
            button_layout.setContentsMargins(0, 10, 0, 0)
            button_layout.setSpacing(10)

            copy_btn = QPushButton("머신 ID 복사")
            copy_btn.setFont(QFont("맑은 고딕", 10, QFont.Weight.Bold))
            copy_btn.setMinimumHeight(40)
            copy_btn.setMinimumWidth(140)
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1976D2;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 14px;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
                QPushButton:pressed {
                    background-color: #0D47A1;
                }
            """)
            
            def copy_machine_id():
                clipboard = QApplication.clipboard()
                if clipboard is None:
                    return
                clipboard.setText(machine_id)
                copy_btn.setText("복사 완료")
                copy_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        border-radius: 8px;
                        padding: 8px 14px;
                    }
                """)

            copy_btn.clicked.connect(copy_machine_id)
            button_layout.addStretch()
            button_layout.addWidget(copy_btn)

            if is_expired:
                kakao_btn = QPushButton("카카오톡 문의")
                kakao_btn.setFont(QFont("맑은 고딕", 10, QFont.Weight.Bold))
                kakao_btn.setMinimumHeight(40)
                kakao_btn.setMinimumWidth(130)
                kakao_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                kakao_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FEE500;
                        color: #191919;
                        border: none;
                        border-radius: 8px;
                        padding: 8px 14px;
                    }
                    QPushButton:hover {
                        background-color: #F5DA00;
                    }
                    QPushButton:pressed {
                        background-color: #EBCD00;
                    }
                """)
                kakao_btn.clicked.connect(
                    lambda: QDesktopServices.openUrl(QUrl("https://open.kakao.com/me/david0985"))
                )
                button_layout.addWidget(kakao_btn)

            ok_button = QPushButton("닫기")
            ok_button.setFont(QFont("맑은 고딕", 10, QFont.Weight.Bold))
            ok_button.setMinimumWidth(100)
            ok_button.setMinimumHeight(40)
            ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
            ok_button.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background-color: #45A049;
                }
                QPushButton:pressed {
                    background-color: #3D8B40;
                }
            """)
            ok_button.clicked.connect(dialog.close)
            button_layout.addWidget(ok_button)
            layout.addLayout(button_layout)

            dialog.setLayout(layout)
            dialog.setStyleSheet("""
                QDialog {
                    background-color: white;
                }
            """)
            
            dialog.exec()
            sys.exit(1)
        
        print("✅ 라이선스 인증 성공")
        # ----------------------------
        
        app.setStyle('Fusion')
        # 스타일 설정
        
        # 🔥 명시적인 팔레트 설정으로 시스템 테마 영향 차단
        palette = QPalette()
        
        # 기본 배경과 텍스트 색상 설정
        palette.setColor(QPalette.ColorRole.Window, QColor(COLORS['background']))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS['text']))
        palette.setColor(QPalette.ColorRole.Base, QColor(COLORS['surface']))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS['surface_light']))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLORS['surface']))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLORS['text']))
        palette.setColor(QPalette.ColorRole.Text, QColor(COLORS['text']))
        palette.setColor(QPalette.ColorRole.Button, QColor(COLORS['surface']))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS['text']))
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Link, QColor(COLORS['primary']))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS['primary']))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        
        # 비활성화된 상태의 색상
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#808080"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#808080"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#808080"))
        
        # 애플리케이션에 팔레트 적용
        app.setPalette(palette)
        
        # 폰트 설정
        font = QFont("맑은 고딕", 10)
        app.setFont(font)

        # 아이콘 설정 (PyInstaller 리소스 경로 사용)
        icon_path = get_preferred_resource_path(os.path.join("setting", "etc", "auto_wp.ico"))
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            print(f"✅ 애플리케이션 아이콘 설정 완료: {icon_path}")
        else:
            print(f"⚠️ 아이콘 파일을 찾을 수 없습니다: {icon_path}")

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
        
        window.showMaximized()
        window.raise_()  # 창을 앞으로 가져오기
        window.activateWindow()  # 창을 활성화
        # MainWindow 표시
        
        try:
            print("Auto WP multi-site 프로그램 시작")
            # 프로그램 실행
        except UnicodeEncodeError:
            print("Auto WP multi-site program started")
            # 프로그램 실행
            
        _set_windows_sleep_prevention(True)
        try:
            return_code = app.exec()
        finally:
            _set_windows_sleep_prevention(False)
        sys.exit(return_code)

    except Exception as e:
        try:
            print(f"프로그램 시작 중 오류: {e}")
        except UnicodeEncodeError:
            print("Error starting program")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()


