# -*- coding: utf-8 -*-
# type: ignore
"""
네이버 블로그 AI 자동 포스팅 통합 프로그램 v5.1

"""

import sys
import io
import locale
import json
import os
import threading
import ctypes
import pyperclip
import re

# UTF-8 환경 강제 설정
if sys.platform == 'win32':
    # Windows 콘솔 코드페이지를 UTF-8로 설정
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except:
        pass
    
    # 표준 입출력을 UTF-8로 재설정 (이미 래핑되어 있지 않은 경우에만)
    try:
        if hasattr(sys.stdout, 'buffer') and (not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

# 로케일 UTF-8 설정
try:
    locale.setlocale(locale.LC_ALL, 'ko_KR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'Korean_Korea.65001')
    except:
        pass

# 파일 I/O UTF-8 강제 설정
import builtins
_original_open = builtins.open
def utf8_open(*args, **kwargs):
    if 'encoding' not in kwargs and 'mode' in kwargs and 'b' not in kwargs['mode']:
        kwargs['encoding'] = 'utf-8'
    elif 'encoding' not in kwargs and (len(args) < 2 or 'b' not in str(args[1])):
        kwargs['encoding'] = 'utf-8'
    return _original_open(*args, **kwargs)
builtins.open = utf8_open

# 안전한 print 함수 (이모지 깨짐 방지)
_original_print = builtins.print
def safe_print(*args, **kwargs):
    """이모지가 포함된 메시지를 안전하게 출력"""
    try:
        _original_print(*args, **kwargs)
    except UnicodeEncodeError:
        # 이모지 등 특수 문자 출력 실패 시 대체 문자로 변환
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                # 출력 가능한 문자만 유지
                safe_str = arg.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                safe_args.append(safe_str)
            else:
                safe_args.append(arg)
        try:
            _original_print(*safe_args, **kwargs)
        except:
            # 최후의 수단: ASCII만 출력
            ascii_args = [str(arg).encode('ascii', errors='ignore').decode('ascii') for arg in args]
            _original_print(*ascii_args, **kwargs)
    except Exception:
        # 모든 출력 실패 시 무시
        pass

builtins.print = safe_print

from typing import TYPE_CHECKING
import time
import os
import traceback

class StopRequested(Exception):
    """사용자 정지 요청용 예외"""
    pass
import platform
from datetime import datetime
from license_check import LicenseManager
import random

if TYPE_CHECKING:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    import google.generativeai as genai
    from PIL import Image, ImageDraw, ImageFont
    import pyautogui
    # moviepy types handled separately

# Lazy loaded imports
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# ... (moved to _ensure_imports)

# moviepy import (PyInstaller 감지용 - moviepy 2.x 호환) - Now lazy loaded in method
imageio = None
imageio_ffmpeg = None



def normalize_blog_address(address: str) -> str:
    """Ensure a blog address has a full https://blog.naver.com/ prefix."""
    if not address:
        return ""
    address = address.strip()
    if not address:
        return ""

    lower_addr = address.lower()
    if lower_addr.startswith("http://") or lower_addr.startswith("https://"):
        return address

    if lower_addr.startswith("blog.naver.com/") or lower_addr.startswith("m.blog.naver.com/"):
        return f"https://{address}"

    return f"https://blog.naver.com/{address}"


class NaverBlogAutomation:
    """네이버 블로그 자동 포스팅 클래스"""
    
    def _ensure_imports(self):
        """Lazy load heavy imports"""
        global webdriver, By, WebDriverWait, EC, Service, ChromeDriverManager
        global TimeoutException, NoSuchElementException, Keys, ActionChains
        global genai, pyautogui

        if 'webdriver' not in globals() or 'genai' not in globals():
            print("⏳ Loading heavy libraries...")
            try:
                import google.generativeai as genai
                from selenium import webdriver
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.chrome.service import Service
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.common.exceptions import TimeoutException, NoSuchElementException
                from selenium.webdriver.common.keys import Keys
                from selenium.webdriver.common.action_chains import ActionChains
                import pyautogui
                print("✅ Heavy libraries loaded")
            except Exception as e:
                print(f"❌ Failed to load libraries: {e}")

        # Ensure correct FFmpeg path for moviepy in EXE environment
        import sys
        if getattr(sys, 'frozen', False):
            # PyInstaller logic for FFmpeg path
            imageio_ffmpeg_exe = os.path.join(sys._MEIPASS, 'imageio_ffmpeg', 'binaries', 'ffmpeg-win64-v4.2.2.exe')
            if os.path.exists(imageio_ffmpeg_exe):
                os.environ["IMAGEIO_FFMPEG_EXE"] = imageio_ffmpeg_exe

    def __init__(self, naver_id, naver_pw, api_key, ai_model="gemini", posting_method="search", theme="일상",
                 open_type="전체공개", external_link=None, external_link_text="더 알아보기",
                 publish_time="즉시발행", scheduled_hour=12, scheduled_minute=0,
                 related_posts_title="함께 보면 좋은 글", related_posts_mode="latest",
                 blog_address="",
                 callback=None, config=None):
        """초기화 함수"""
        self._ensure_imports()
        
        self.naver_id = naver_id
        self.naver_pw = naver_pw
        self.api_key = api_key
        # GPT 지원 종료: 내부적으로 Gemini만 사용
        self.ai_model = "gemini"
        self.theme = theme
        self.open_type = open_type
        self.external_link = external_link
        self.external_link_text = external_link_text
        self.publish_time = publish_time
        self.scheduled_hour = scheduled_hour
        self.scheduled_minute = scheduled_minute
        self.related_posts_title = related_posts_title
        self.related_posts_mode = (config or {}).get("related_posts_mode", related_posts_mode)
        self.blog_address = normalize_blog_address(blog_address)
        self.callback = callback
        self.config = config or {}  # config 저장
        self.gemini_mode = self.config.get("gemini_mode", "api")
        self.web_ai_provider = (self.config.get("web_ai_provider", "gemini") or "gemini").lower()
        self.gemini_tab_handle = None
        self.gpt_tab_handle = None
        self.perplexity_tab_handle = None
        self.gemini_first_open = True  # 첫 생성 여부 추적
        self.gpt_first_open = True
        self.perplexity_first_open = True
        self.gemini_logged_in = False
        self.blog_tab_handle = None
        self.posting_method = self.config.get(
            "posting_method",
            posting_method if posting_method in ("search", "home") else "search"
        )
        self.driver = None
        self.should_stop = False  # 정지 플래그
        self.should_pause = False  # 일시정지 플래그
        self.current_keyword = ""  # 현재 사용 중인 키워드
        
        # 디렉토리 설정 (exe 실행 시 고려)
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            # 쓰기 권한 테스트
            try:
                test_dir = os.path.join(exe_dir, "setting")
                os.makedirs(test_dir, exist_ok=True)
                test_file = os.path.join(test_dir, ".write_test")
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                self.data_dir = exe_dir
            except (PermissionError, OSError):
                import pathlib
                self.data_dir = str(pathlib.Path.home() / "Documents" / "Auto_Naver")
                os.makedirs(os.path.join(self.data_dir, "setting"), exist_ok=True)
        else:
            self.data_dir = os.path.dirname(os.path.abspath(__file__))
        
        # AI 모델 설정 (Gemini 고정)
        if self.gemini_mode != "web":
            genai.configure(api_key=api_key)  # type: ignore
            self.model = genai.GenerativeModel('gemini-2.5-flash-lite')  # type: ignore
        else:
            self.model = None
        
        # 초기화 시 오래된 파일 정리
        self.clean_old_files()
    
    def clean_old_files(self):
        """result 폴더의 1주일 이상 된 파일 자동 삭제"""
        try:
            result_folder = os.path.join(self.data_dir, "setting", "result")
            if not os.path.exists(result_folder):
                return
            
            import time as time_module
            current_time = time_module.time()
            one_week_ago = current_time - (7 * 24 * 60 * 60)  # 7일 전
            
            deleted_count = 0
            for filename in os.listdir(result_folder):
                file_path = os.path.join(result_folder, filename)
                
                # 파일인지 확인 (폴더 제외)
                if os.path.isfile(file_path):
                    # 파일 수정 시간 확인
                    file_mtime = os.path.getmtime(file_path)
                    
                    # 1주일 이상 지난 파일 삭제
                    if file_mtime < one_week_ago:
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                            self._update_status(f"🗑️ 오래된 파일 삭제: {filename}")
                        except Exception as e:
                            self._update_status(f"⚠️ 파일 삭제 실패: {filename} - {str(e)[:30]}")
            
            if deleted_count > 0:
                self._update_status(f"✅ 1주일 이상 된 파일 {deleted_count}개 삭제 완료")
        except Exception as e:
            self._update_status(f"⚠️ 파일 정리 중 오류: {str(e)[:50]}")
    
    def _update_status(self, message):
        """상태 메시지 업데이트 (중복 방지)"""
        # 마지막 메시지와 동일하면 출력하지 않음
        if not hasattr(self, '_last_status_message') or self._last_status_message != message:
            self._last_status_message = message
            # GUI와 터미널 모두에 출력
            if self.callback:
                self.callback(message)
            # 터미널에도 진행 현황 표시
            print(message)
    
    def _report_error(self, error_context, exception, show_traceback=True):
        """오류 상세 정보를 로그에 표시"""
        error_type = type(exception).__name__
        error_msg = str(exception)
        
        # 기본 오류 메시지
        self._update_status(f"❌ {error_context}: {error_type}")
        self._update_status(f"📝 오류 내용: {error_msg[:100]}")
        
        # 상세 traceback (옵션)
        if show_traceback:
            tb_lines = traceback.format_exc().strip().split('\n')
            # 마지막 5줄만 표시 (너무 길면 로그가 복잡해짐)
            for line in tb_lines[-5:]:
                if line.strip():
                    self._update_status(f"  {line.strip()[:80]}")
        
        # 터미널에도 전체 traceback 출력
        print(f"\n{'='*80}")
        print(f"❌ 오류 발생: {error_context}")
        print(f"{'='*80}")
        print(traceback.format_exc())
        print(f"{'='*80}\n")
    
    def load_keyword(self):
        """키워드를 keywords.txt 파일에서 로드 (개수 확인 및 경고)"""
        keywords_file = os.path.join(self.data_dir, "setting", "keywords.txt")
        
        # 파일 읽기 재시도 로직 (파일 동시 접근 문제 해결)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not os.path.exists(keywords_file):
                    self._update_status("오류: keywords.txt 파일이 없습니다.")
                    print(f"❌ keywords.txt 파일 경로: {keywords_file}")
                    if self.callback:
                        self.callback("KEYWORD_FILE_MISSING")
                    return None
                
                # 파일 읽기
                with open(keywords_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    keywords = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
                
                keyword_count = len(keywords)
                print(f"📖 키워드 파일 읽기 성공: {keyword_count}개 발견")
                
                # 키워드 개수 확인 및 경고
                if keyword_count == 0:
                    self._update_status("⚠️ 오류: 사용 가능한 키워드가 없습니다. 프로그램을 종료합니다.")
                    if self.callback:
                        self.callback("KEYWORD_EMPTY")
                    return None
                    
                elif keyword_count < 30:
                    self._update_status(f"⚠️ 경고: 키워드가 {keyword_count}개 남았습니다! 추가 등록이 필요합니다.")
                    # 팝업 제거: 상태 메시지만 표시하고 프로그램은 계속 진행
                
                # 첫 번째 키워드 선택
                selected_keyword = keywords[0]
                self._update_status(f"선택된 키워드: {selected_keyword} (남은 개수: {keyword_count}개)")
                return selected_keyword
                
            except PermissionError as e:
                print(f"⚠️ 파일 접근 권한 오류 (시도 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)  # 잠시 대기 후 재시도
                    continue
                else:
                    self._update_status(f"❌ 파일 접근 권한 오류: {str(e)}")
                    print(f"❌ 키워드 파일 접근 실패 (3회 재시도 후)")
                    return None
            except Exception as e:
                print(f"❌ 키워드 로드 예외 (시도 {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)  # 잠시 대기 후 재시도
                    continue
                else:
                    self._update_status(f"❌ 키워드 로드 중 예외 발생: {str(e)}")
                    print(f"❌ 키워드 로드 예외 상세: {type(e).__name__}: {str(e)}")
                    print(f"❌ keywords.txt 경로: {keywords_file}")
                    import traceback
                    traceback.print_exc()
                    if os.path.exists(keywords_file):
                        print(f"⚠️ 파일은 존재하지만 읽기 실패")
                    return None
        
        return None
    
    def move_keyword_to_used(self, keyword):
        """키워드를 keywords.txt에서 제거하고 used_keywords.txt로 이동"""
        keywords_file = os.path.join(self.data_dir, "setting", "keywords.txt")
        used_keywords_file = os.path.join(self.data_dir, "setting", "used_keywords.txt")
        
        # 파일 작업 재시도 로직
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not os.path.exists(keywords_file):
                    print(f"❌ keywords.txt 파일이 없습니다: {keywords_file}")
                    return
                
                # 파일 읽기
                with open(keywords_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    keywords = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
                
                # 사용한 키워드 제거
                remaining_keywords = [kw for kw in keywords if kw != keyword]
                
                # keywords.txt 업데이트
                with open(keywords_file, 'w', encoding='utf-8') as f:
                    for kw in remaining_keywords:
                        f.write(kw + '\n')
                
                # used_keywords.txt에 추가
                with open(used_keywords_file, 'a', encoding='utf-8') as f:
                    f.write(keyword + '\n')
                
                self._update_status(f"✅ 키워드 '{keyword}'를 사용 완료 목록으로 이동")
                print(f"✅ 키워드 이동 성공: '{keyword}' (남은 키워드: {len(remaining_keywords)}개)")
                return  # 성공시 바로 리턴
                
            except PermissionError as e:
                print(f"⚠️ 파일 접근 권한 오류 (시도 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)  # 잠시 대기 후 재시도
                    continue
                else:
                    self._update_status(f"❌ 키워드 이동 중 권한 오류: {str(e)}")
                    print(f"❌ 키워드 이동 실패 (3회 재시도 후)")
            except Exception as e:
                print(f"❌ 키워드 이동 예외 (시도 {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue
                else:
                    self._update_status(f"❌ 키워드 이동 중 예외 발생: {str(e)}")
                    print(f"❌ 키워드 이동 예외 상세: {type(e).__name__}: {str(e)}")
                    import traceback
                    traceback.print_exc()

    def _wait_if_paused(self):
        """일시정지 상태일 때 대기"""
        if self.should_stop:
            raise StopRequested()
        while self.should_pause and not self.should_stop:
            time.sleep(0.5)
        if self.should_stop:
            raise StopRequested()

    def _sleep_with_checks(self, seconds, step=0.2):
        """일시정지/정지 상태를 확인하며 대기"""
        end_time = time.time() + seconds
        while time.time() < end_time:
            self._wait_if_paused()
            remaining = end_time - time.time()
            if remaining <= 0:
                break
            time.sleep(min(step, remaining))

    def generate_content_with_ai(self):
        """AI를 사용하여 블로그 글 생성 (Gemini 고정)"""
        try:
            self._wait_if_paused()
            model_name = "Gemini 2.5 Flash-Lite"
            self._update_status(f"🤖 AI 모델 준비 중: {model_name}")
            
            # keywords.txt에서 키워드 로드
            self._update_status("📋 키워드 파일 읽는 중...")
            keyword = self.load_keyword()
            
            if keyword is None:
                self._update_status("❌ 사용 가능한 키워드가 없습니다! 프로그램을 중지합니다.")
                return None, None
            
            if not keyword:
                self._update_status("❌ 키워드 로드 실패!")
                return None, None
            
            self.current_keyword = keyword
            self._update_status(f"✅ 선택된 키워드: {keyword}")
            print(f"🎯 키워드 사용: {keyword}")
            
            # prompt1.txt와 prompt2.txt 파일 읽기
            self._update_status("📄 프롬프트 템플릿 로드 중...")
            prompt1_file = os.path.join(self.data_dir, "setting", "prompt1.txt")
            prompt2_file = os.path.join(self.data_dir, "setting", "prompt2.txt")
            
            prompt1_content = ""
            prompt2_content = ""
            
            # prompt1.txt 읽기 (제목+서론)
            if os.path.exists(prompt1_file):
                with open(prompt1_file, 'r', encoding='utf-8') as f:
                    prompt1_content = f.read().replace('{keywords}', keyword)
                self._update_status("✅ 프롬프트1 (제목+서론) 로드 완료")
            
            # prompt2.txt 읽기 (소제목+본문)
            if os.path.exists(prompt2_file):
                with open(prompt2_file, 'r', encoding='utf-8') as f:
                    prompt2_content = f.read().replace('{keywords}', keyword)
                self._update_status("✅ 프롬프트2 (소제목+본문) 로드 완료")
            
            if prompt1_content and prompt2_content:
                # 프롬프트 조합
                full_prompt = f"""당신은 블로그 글 작성 전문가입니다. 아래 두 개의 프롬프트를 정확히 따라 글을 작성하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[프롬프트 1 - 제목과 서론 작성]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{prompt1_content}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[프롬프트 2 - 소제목과 본문 작성]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{prompt2_content}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[출력 형식]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

제목
서론
소제목1
본문1
소제목2
본문2
소제목3
본문3

⚠️ 필수 준수사항: 
- **제목은 반드시 '{keyword}, 후킹문구' 형식을 정확히 따르세요**
- **제목 맨 앞에 반드시 {keyword}가 와야 합니다**
- 제목 예시: "{keyword}, 5가지 방법 총정리" 또는 "{keyword}, 최신 트렌드 10가지"
- 제목에서 키워드 뒤에 반드시 쉬표(,)를 넣고 공백 후 후킹문구(숫자 포함)를 작성하세요
- **서론은 정확히 200자 내외로 작성하세요 (180자~220자 범위)**
- 본문은 각각 **최소 500자 이상** 상세히 작성하세요
- 본문은 각각 **최소 500자 이상** 상세히 작성하세요
- 프롬프트 1의 모든 조건을 정확히 지켜 '제목'과 '서론'을 작성하세요
- 프롬프트 2의 모든 조건을 정확히 지켜 '소제목'과 '본문' 3세트를 작성하세요
- 두 프롬프트의 '절대 금지 사항'을 반드시 준수하세요
- 각 섹션 사이는 빈 줄 없이 줄바꿈 1번만 하세요
- 본문은 가능한 한 많은 토큰을 사용하여 길게 작성하세요
"""
                print(f"📄 프롬프트에 키워드 '{keyword}' 삽입 완료")
            else:
                self._update_status("❌ 프롬프트 파일을 찾을 수 없습니다")
                return None, None
            
            # Gemini 호출
            self._update_status(f"🔄 AI에게 글 생성 요청 중... (모델: {model_name})")
            if self.gemini_mode == "web":
                provider = (self.config.get("web_ai_provider", "gemini") or "gemini").lower()
                if provider == "gpt":
                    content = self._generate_content_with_chatgpt_web(full_prompt)
                elif provider == "perplexity":
                    content = self._generate_content_with_perplexity_web(full_prompt)
                else:
                    content = self._generate_content_with_gemini_web(full_prompt)
            else:
                response = self.model.generate_content(full_prompt)  # type: ignore
                content = getattr(response, "text", "")  # type: ignore

            if not content or not content.strip():
                self._update_status("❌ AI 응답이 비어 있습니다")
                return None, None
            
            self._update_status("📝 AI 응답 처리 중...")
            self._wait_if_paused()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_folder = os.path.join("setting", "result")
            os.makedirs(result_folder, exist_ok=True)

            # 원문 저장 (Gemini 복사본)
            try:
                raw_filename = f"{keyword}_{timestamp}_raw.txt"
                raw_filepath = os.path.join(result_folder, raw_filename)
                with open(raw_filepath, 'w', encoding='utf-8') as f:
                    f.write(content.strip() + "\n")
                self._update_status(f"✅ 원문 저장: {raw_filename}")
            except Exception as e:
                self._update_status(f"⚠️ 원문 저장 실패: {str(e)}")

            # 제목/서론/소제목/본문 분리
            title, intro, sections = self._parse_ai_response(content)
            if not title:
                for line in content.splitlines():
                    if line.strip():
                        title = line.strip()
                        break
            if not title:
                self._update_status("❌ 제목 추출 실패")
                return None, None

            body = self._build_body_text(intro, sections)
            if not body:
                # 폴백: 줄바꿈 기준으로 제목/본문 분리
                fallback_lines = [line.strip() for line in content.splitlines() if line.strip()]
                if len(fallback_lines) >= 2:
                    if not title:
                        title = fallback_lines[0]
                    body = "\n".join(fallback_lines[1:])
                else:
                    self._update_status("❌ 본문 추출 실패")
                    return None, None

            # AI 생성 글을 result 폴더에 저장
            try:
                result_filename = f"{keyword}_{timestamp}.txt"
                result_filepath = os.path.join(result_folder, result_filename)
                
                with open(result_filepath, 'w', encoding='utf-8') as f:
                    f.write(f"제목: {title}\n\n")
                    f.write(f"본문:\n{body}\n")
                
                self._update_status(f"✅ AI 생성 글 저장: {result_filename}")
            except Exception as e:
                self._update_status(f"⚠️ 글 저장 실패: {str(e)}")
            
            self._update_status(f"✅ AI 글 생성 완료! (제목: {title[:30]}...)")
            return title, body
        except StopRequested:
            return None, None
        except Exception as e:
            self._report_error("AI 글 생성", e)
            return None, None

    def _parse_ai_response(self, content):
        """AI 응답을 제목/서론/소제목/본문으로 분리"""
        raw = content.strip().replace("\r\n", "\n").replace("\r", "\n")
        if not raw:
            return "", "", []

        lines = [line.strip() for line in raw.splitlines()]
        label_map = {
            "제목": "title",
            "서론": "intro",
            "소제목": "subtitle",
            "본문": "body",
        }
        has_labels = any(line in label_map for line in lines)
        if has_labels:
            title = ""
            intro = ""
            sections = []
            current = None
            buffer = []

            def flush():
                nonlocal title, intro, sections, buffer, current
                text = "\n".join([b for b in buffer if b.strip()]).strip()
                if not text:
                    buffer = []
                    return
                if current == "title":
                    title = text.splitlines()[0].strip()
                elif current == "intro":
                    intro = text
                elif current == "subtitle":
                    sections.append([text.splitlines()[0].strip(), ""])
                elif current == "body":
                    if not sections:
                        sections.append(["", text])
                    else:
                        if sections[-1][1]:
                            sections[-1][1] += "\n" + text
                        else:
                            sections[-1][1] = text
                buffer = []

            for line in lines:
                if line in label_map:
                    flush()
                    current = label_map[line]
                    continue
                buffer.append(line)
            flush()
            return title, intro, [(s[0], s[1]) for s in sections]

        compact_lines = [line for line in lines if line]
        if len(compact_lines) >= 8:
            title = compact_lines[0].strip()
            intro = compact_lines[1].strip()
            sections = [
                (compact_lines[2].strip(), compact_lines[3].strip()),
                (compact_lines[4].strip(), compact_lines[5].strip()),
                (compact_lines[6].strip(), compact_lines[7].strip()),
            ]
            if len(compact_lines) > 8:
                extra = "\n".join(compact_lines[8:]).strip()
                if extra:
                    sub, body = sections[-1]
                    body = (body + "\n" + extra).strip() if body else extra
                    sections[-1] = (sub, body)
            return title, intro, sections

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
        if not paragraphs:
            return "", "", []

        title = paragraphs[0].splitlines()[0].strip()
        intro = paragraphs[1].strip() if len(paragraphs) > 1 else ""
        rest = paragraphs[2:] if len(paragraphs) > 2 else []
        sections = []
        i = 0
        while i < len(rest):
            subtitle = rest[i].splitlines()[0].strip()
            body = rest[i + 1].strip() if i + 1 < len(rest) else ""
            sections.append((subtitle, body))
            i += 2
        return title, intro, sections

    def _build_body_text(self, intro, sections):
        """서론/소제목/본문을 본문 문자열로 구성"""
        lines = []
        if intro:
            intro_line = " ".join(intro.splitlines()).strip()
            if intro_line:
                lines.append(intro_line)
        for subtitle, body in sections:
            sub_line = " ".join(subtitle.splitlines()).strip()
            body_line = " ".join(body.splitlines()).strip()
            if sub_line:
                lines.append(sub_line)
            if body_line:
                lines.append(body_line)
        return "\n".join(lines)

    def _looks_like_status_text(self, text):
        """Gemini 응답이 아닌 상태/로그 텍스트인지 확인"""
        if not text:
            return True
        markers = [
            "Gemini 응답 대기",
            "AI 응답 처리",
            "원문 저장",
            "본문 추출 실패",
            "AI 글 생성 실패",
            "포스팅 실패",
        ]
        return any(marker in text for marker in markers)

    def _looks_like_prompt_echo(self, text):
        """프롬프트가 그대로 돌아온 경우인지 확인"""
        if not text:
            return False
        markers = [
            "프롬프트 1",
            "프롬프트 2",
            "출력 형식",
            "필수 준수사항",
            "절대 금지 사항",
            "블로그 글 작성 전문가",
        ]
        return sum(marker in text for marker in markers) >= 2

    def _ensure_gemini_tab(self):
        """Gemini 웹 탭을 준비하고 포커스 (매번 새 탭 생성)"""
        if not self.driver:
            return False
        gemini_url = "https://gemini.google.com/app?hl=ko"
        try:
            # 항상 새 탭으로 열기 (기존 탭은 그대로 둘기)
            self.driver.execute_script("window.open(arguments[0], '_blank');", gemini_url)
            time.sleep(0.5)
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.gemini_tab_handle = self.driver.current_window_handle
            self._update_status("✅ 새 Gemini 탭 생성")
            time.sleep(2)  # 페이지 로딩 대기
            return True
        except Exception as e:
            self._update_status(f"⚠️ Gemini 탭 열기 실패: {str(e).split(chr(10))[0][:80]}")
            return False


    def _ensure_chatgpt_tab(self):
        """ChatGPT 웹 탭을 준비하고 포커스 (매번 새 탭 생성)"""
        if not self.driver:
            return False
        chatgpt_url = "https://chatgpt.com/"
        try:
            # 항상 새 탭으로 열기 (기존 탭은 그대로 둘기)
            self.driver.execute_script("window.open(arguments[0], '_blank');", chatgpt_url)
            time.sleep(0.5)
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.gpt_tab_handle = self.driver.current_window_handle
            self._update_status("✅ 새 ChatGPT 탭 생성")
            time.sleep(2)
            return True
        except Exception as e:
            self._update_status(f"⚠️ ChatGPT 탭 열기 실패: {str(e).split(chr(10))[0][:80]}")
            return False

    def _ensure_perplexity_tab(self):
        """Perplexity 웹 탭을 준비하고 포커스 (매번 새 탭 생성)"""
        if not self.driver:
            return False
        perplexity_url = "https://www.perplexity.ai/"
        try:
            # 항상 새 탭으로 열기 (기존 탭은 그대로 둘기)
            self.driver.execute_script("window.open(arguments[0], '_blank');", perplexity_url)
            time.sleep(0.5)
            self.driver.switch_to.window(self.driver.window_handles[-1])
            self.perplexity_tab_handle = self.driver.current_window_handle
            self._update_status("✅ 새 Perplexity 탭 생성")
            time.sleep(2)
            return True
        except Exception as e:
            self._update_status(f"⚠️ Perplexity 탭 열기 실패: {str(e).split(chr(10))[0][:80]}")
            return False

    def _ensure_blog_tab(self, url=None):
        """블로그 작업용 탭을 준비하고 포커스"""
        if not self.driver:
            return False
        try:
            if self.blog_tab_handle and self.blog_tab_handle in self.driver.window_handles:
                self.driver.switch_to.window(self.blog_tab_handle)
                if url:
                    self.driver.get(url)
                return True
            try:
                current_url = (self.driver.current_url or "").lower()
            except Exception:
                current_url = ""
            if current_url.startswith("data:") or current_url.startswith("about:blank"):
                if url:
                    self.driver.get(url)
            else:
                target_url = url if url else "about:blank"
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
                self.driver.switch_to.window(self.driver.window_handles[-1])
            self.blog_tab_handle = self.driver.current_window_handle
            return True
        except Exception as e:
            self._update_status(f"⚠️ 블로그 탭 준비 실패: {str(e)}")
            return False

    def _click_gemini_login(self):
        """Gemini 로그인 버튼 클릭"""
        try:
            login_link = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[aria-label='로그인'], a[href*='ServiceLogin']"))
            )
            login_link.click()
            return True
        except Exception:
            return False

    def _click_google_next(self):
        """Google 로그인 '다음' 버튼 클릭"""
        try:
            next_btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[normalize-space()='다음']]"))
            )
            next_btn.click()
            return True
        except Exception:
            return False

    def _click_google_later(self):
        """Google '나중에' 버튼 클릭"""
        try:
            later_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[normalize-space()='나중에']]"))
            )
            later_btn.click()
            return True
        except Exception:
            return False

    def _ensure_gemini_logged_in(self):
        """Gemini ??? ?? (? ?? ??)"""
        if self._find_gemini_editor(timeout=3):
            self.gemini_logged_in = True
            return True
        if self.gemini_logged_in:
            return bool(self._find_gemini_editor(timeout=3))
        self._update_status("?? Gemini ???? ????? (?????? ??? ? ?? ??)")
        return False

    def _find_gemini_editor(self, timeout=10):
        """Gemini 입력창 요소 찾기"""
        selectors = [
            "rich-textarea div.ql-editor",
            "rich-textarea [contenteditable='true']",
            "textarea",
        ]
        end_time = time.time() + timeout
        while time.time() < end_time:
            for selector in selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if elem and elem.is_displayed():
                        return elem
                except Exception:
                    continue
            time.sleep(0.2)
        return None

    def _submit_gemini_prompt(self, prompt):
        """Gemini 입력창에 프롬프트 입력 후 전송"""
        try:
            editor = self._find_gemini_editor(timeout=12)
            if not editor:
                return False
            for attempt in range(2):
                try:
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", editor)
                    except Exception:
                        pass
                    editor.click()
                    try:
                        editor.clear()
                    except Exception:
                        pass
                    pyperclip.copy(prompt)
                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    time.sleep(0.2)
                    current_text = self._get_gemini_editor_text(editor)
                    if not current_text or len(current_text) < 10:
                        if not self._set_gemini_editor_text(editor, prompt):
                            editor.send_keys(prompt)
                        time.sleep(0.1)
                    current_text = self._get_gemini_editor_text(editor)
                    if current_text and len(current_text) >= 10:
                        editor.send_keys(Keys.ENTER)
                        return True
                except Exception:
                    editor = self._find_gemini_editor(timeout=6)
                    if not editor:
                        break
            return False
        except Exception as e:
            self._update_status(f"⚠️ Gemini 프롬프트 입력 실패: {str(e)}")
            return False

    def _get_gemini_editor_text(self, editor):
        """Gemini 입력창 텍스트 읽기"""
        try:
            if editor.get_attribute("contenteditable") == "true":
                return editor.text.strip()
            return (editor.get_attribute("value") or "").strip()
        except Exception:
            return ""

    def _set_gemini_editor_text(self, editor, text):
        """Gemini 입력창에 텍스트 설정 (붙여넣기 실패 시 폴백)"""
        try:
            return bool(self.driver.execute_script("""
                const el = arguments[0];
                const value = arguments[1];
                if (!el) return false;
                el.focus();
                if (el.isContentEditable) {
                    el.textContent = value;
                } else {
                    el.value = value;
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            """, editor, text))
        except Exception:
            return False

    def _wait_for_gemini_response(self, before_count, timeout=120):
        """Gemini 응답 텍스트 대기"""
        selectors = [
            "div.markdown",
            "message-content",
            "div.response-container",
            "div.model-response",
            "div[role='article']",
        ]
        end_time = time.time() + timeout
        last_text = ""
        while time.time() < end_time:
            self._wait_if_paused()
            elements = []
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        break
                except Exception:
                    continue
            if elements and len(elements) > before_count:
                try:
                    text = elements[-1].text.strip()
                except Exception:
                    text = ""
                if text:
                    self._sleep_with_checks(1.5)
                    try:
                        text2 = elements[-1].text.strip()
                    except Exception:
                        text2 = ""
                    if text2 == text and text2:
                        return text2
                    last_text = text2 or last_text
            self._sleep_with_checks(1)
        return last_text

    def _scroll_gemini_to_bottom(self):
        """Gemini 페이지를 맨 아래로 스크롤"""
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
        except Exception:
            pass

    def _click_gemini_copy_latest(self):
        """최신 응답의 복사 버튼 클릭"""
        try:
            buttons = self.driver.find_elements(By.CSS_SELECTOR, "copy-button button, button[data-test-id='copy-button'], button[aria-label='복사']")
            if not buttons:
                return False
            buttons[-1].click()
            return True
        except Exception:
            return False

    def _count_gemini_copy_buttons(self):
        """Gemini 복사 버튼 개수"""
        try:
            return len(self.driver.find_elements(By.CSS_SELECTOR, "copy-button button, button[data-test-id='copy-button'], button[aria-label='복사']"))
        except Exception:
            return 0

    def _wait_for_gemini_copy_button(self, before_count, timeout=120):
        """Gemini 응답 복사 버튼 появление 대기"""
        end_time = time.time() + timeout
        while time.time() < end_time:
            self._wait_if_paused()
            if self._count_gemini_copy_buttons() > before_count:
                return True
            self._sleep_with_checks(1)
        return False

    def _generate_content_with_gemini_web(self, prompt):
        """Gemini 웹앱을 사용해 콘텐츠 생성"""
        try:
            self._wait_if_paused()
            self._update_status("🌐 Gemini 웹 사이트로 이동 중...")
            
            if not self.driver:
                self._update_status("🔄 Gemini 웹 모드: 브라우저 실행 중...")
                if not self.setup_driver():
                    self._update_status("❌ Gemini 웹 모드: 브라우저 실행 실패")
                    return ""

            if not self._ensure_gemini_tab():
                return ""

            self._update_status("🔄 Gemini 웹앱 입력창 확인 중...")
            before_count = 0
            try:
                before_count = len(self.driver.find_elements(By.CSS_SELECTOR, "div.markdown"))
            except Exception:
                before_count = 0

            before_copy_count = self._count_gemini_copy_buttons()
            
            self._update_status("📤 프롬프트 입력 중...")
            if not self._submit_gemini_prompt(prompt):
                self._update_status("❌ Gemini 웹앱 입력 실패 - 로그인 상태를 확인해주세요")
                return ""

            self._update_status("🔄 Gemini 응답 대기 중...")
            content = ""
            if self._wait_for_gemini_copy_button(before_copy_count, timeout=180):
                self._scroll_gemini_to_bottom()
                if self._click_gemini_copy_latest():
                    time.sleep(0.3)
                    try:
                        copied = pyperclip.paste().strip()
                        if copied and not self._looks_like_status_text(copied) and not self._looks_like_prompt_echo(copied):
                            content = copied
                            self._update_status("✅ Gemini 응답 복사 완료")
                    except Exception:
                        pass
            if not content:
                self._update_status("📝 응답 텍스트 직접 추출 중...")
                content = self._wait_for_gemini_response(before_count, timeout=120)
                if self._looks_like_prompt_echo(content):
                    content = ""
            if not content:
                self._update_status("❌ Gemini 응답 대기 실패 - 로그인/네트워크 확인 필요")
            else:
                self._update_status(f"✅ AI 글 생성 완료 (길이: {len(content)}자)")
            return content
        except StopRequested:
            return ""
        except Exception as e:
            self._update_status(f"⚠️ Gemini 웹 모드 오류: {str(e)}")
            return ""
    

    def _generate_content_with_chatgpt_web(self, prompt):
        try:
            self._wait_if_paused()
            self._update_status("🌐 ChatGPT 웹 사이트로 이동 중...")
            
            if not self.driver:
                self._update_status("🔄 ChatGPT 웹 모드: 브라우저 실행 중...")
                if not self.setup_driver():
                    self._update_status("❌ ChatGPT 웹 모드: 브라우저 실행 실패")
                    return ""

            if not self._ensure_chatgpt_tab():
                return ""

            self._update_status("🔄 ChatGPT 입력창 확인 중...")
            before_copy_count = self._count_chatgpt_copy_buttons()
            
            self._update_status("📤 프롬프트 입력 중...")
            if not self._submit_chatgpt_prompt(prompt):
                self._update_status("❌ ChatGPT 입력 실패 - 로그인 상태 확인 필요")
                return ""

            self._update_status("🔄 ChatGPT 응답 대기 중...")
            content = ""
            if self._wait_for_chatgpt_copy_button(before_copy_count, timeout=180):
                if self._click_chatgpt_copy_latest():
                    time.sleep(0.3)
                    try:
                        copied = pyperclip.paste().strip()
                        if copied and not self._looks_like_status_text(copied) and not self._looks_like_prompt_echo(copied):
                            content = copied
                            self._update_status("✅ ChatGPT 응답 복사 완료")
                    except Exception:
                        pass
            if not content:
                self._update_status("❌ ChatGPT 응답 대기 실패 - 로그인/네트워크 확인 필요")
            else:
                self._update_status(f"✅ AI 글 생성 완료 (길이: {len(content)}자)")
            return content
        except StopRequested:
            return ""
        except Exception as e:
            self._update_status(f"⚠️ ChatGPT 웹 모드 오류: {str(e)}")
            return ""

    def _generate_content_with_perplexity_web(self, prompt):
        try:
            self._wait_if_paused()
            self._update_status("🌐 Perplexity 웹 사이트로 이동 중...")
            
            if not self.driver:
                self._update_status("🔄 Perplexity 웹 모드: 브라우저 실행 중...")
                if not self.setup_driver():
                    self._update_status("❌ Perplexity 웹 모드: 브라우저 실행 실패")
                    return ""

            if not self._ensure_perplexity_tab():
                return ""

            self._update_status("🔄 Perplexity 입력창 확인 중...")
            before_copy_count = self._count_perplexity_copy_buttons()
            
            self._update_status("📤 프롬프트 입력 중...")
            if not self._submit_perplexity_prompt(prompt):
                self._update_status("❌ Perplexity 입력 실패 - 로그인 상태 확인 필요")
                return ""

            self._update_status("🔄 Perplexity 응답 대기 중...")
            content = ""
            if self._wait_for_perplexity_copy_button(before_copy_count, timeout=180):
                if self._click_perplexity_copy_latest():
                    time.sleep(0.3)
                    try:
                        copied = pyperclip.paste().strip()
                        if copied and not self._looks_like_status_text(copied) and not self._looks_like_prompt_echo(copied):
                            content = copied
                            self._update_status("✅ Perplexity 응답 복사 완료")
                    except Exception:
                        pass
            if not content:
                self._update_status("❌ Perplexity 응답 대기 실패 - 로그인/네트워크 확인 필요")
            else:
                self._update_status(f"✅ AI 글 생성 완료 (길이: {len(content)}자)")
            return content
        except StopRequested:
            return ""
        except Exception as e:
            self._update_status(f"⚠️ Perplexity 웹 모드 오류: {str(e)}")
            return ""

    def create_thumbnail(self, title):
        """setting/image 폴더의 jpg를 배경으로 300x300 썸네일 생성"""
        try:
            # 썸네일 기능이 OFF인 경우 None 반환
            if not self.config.get("use_thumbnail", True):
                self._update_status("⚪ 썸네일 기능 OFF - 스킵")
                return None
            
            # PIL imports 확인
            try:
                from PIL import Image, ImageDraw, ImageFont
                self._update_status("✅ PIL 모듈 로드 성공")
            except ImportError as ie:
                self._update_status(f"❌ PIL 임포트 실패: {str(ie)}")
                print(f"[PIL 임포트 오류]\n{traceback.format_exc()}")
                return None
            
            self._update_status("🎨 썸네일 생성 중...")
            
            # setting/image 폴더의 jpg 파일 찾기
            image_folder = os.path.join(self.data_dir, "setting", "image")
            self._update_status(f"📁 이미지 폴더 경로: {image_folder}")
            if not os.path.exists(image_folder):
                self._update_status(f"⚠️ {image_folder} 폴더가 없습니다.")
                return None
            
            # jpg 파일 검색
            jpg_files = [f for f in os.listdir(image_folder) if f.lower().endswith('.jpg')]
            
            if not jpg_files:
                self._update_status(f"⚠️ {image_folder} 폴더에 jpg 파일이 없습니다.")
                return None
            
            # 첫 번째 jpg 파일 사용
            source_image_path = os.path.join(image_folder, jpg_files[0])
            self._update_status(f"📷 배경 이미지: {jpg_files[0]}")
            
            # 이미지 열기 및 300x300으로 리사이즈
            img = Image.open(source_image_path)
            img = img.resize((300, 300), Image.Resampling.LANCZOS)
            
            # 이미지 위에 텍스트 그리기
            draw = ImageDraw.Draw(img)
            
            # 제목을 줄바꿈 처리 (글자 수 제한)
            max_chars_per_line = 10  # 한 줄당 최대 10자 (공백 포함)
            max_lines = 5  # 최대 5줄
            margin = 30  # 테두리 여백 (좌우상하)
            
            if ',' in title:
                # 쉼표가 있으면 쉼표 기준으로 먼저 분리
                parts = title.split(',')
                lines = []
                for part in parts:
                    part = part.strip()
                    if part:
                        # 각 파트가 8자를 넘으면 추가로 분할
                        if len(part) > max_chars_per_line:
                            for i in range(0, len(part), max_chars_per_line):
                                lines.append(part[i:i+max_chars_per_line])
                        else:
                            lines.append(part)
                title_text = '\n'.join(lines[:max_lines])
            else:
                # 쉼표가 없으면 글자 수로만 분할
                lines = []
                for i in range(0, len(title), max_chars_per_line):
                    lines.append(title[i:i+max_chars_per_line])
                title_text = '\n'.join(lines[:max_lines])
            
            # 폰트 설정 (고정 크기)
            font_size = 24  # 폰트 크기 약간 줄임
            
            try:
                # 맑은 고딕 폰트 사용
                font_path = "C:/Windows/Fonts/malgun.ttf"
                font = ImageFont.truetype(font_path, font_size)
            except:
                # 폰트 로드 실패 시 기본 폰트
                font = ImageFont.load_default()
            
            # 텍스트 바운딩 박스 계산
            bbox = draw.multiline_textbbox((0, 0), title_text, font=font, align='center', spacing=4)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # 중앙 위치 계산 (여백 고려)
            available_width = 300 - (margin * 2)
            available_height = 300 - (margin * 2)
            x = margin + (available_width - text_width) // 2
            y = margin + (available_height - text_height) // 2
            
            # 텍스트 그림자 (검정색)
            shadow_offset = 2
            draw.multiline_text(
                (x + shadow_offset, y + shadow_offset), 
                title_text, 
                fill=(50, 50, 50), 
                font=font, 
                align='center',
                spacing=4
            )
            
            # 텍스트 그리기 (흰색)
            draw.multiline_text(
                (x, y), 
                title_text, 
                fill=(255, 255, 255), 
                font=font, 
                align='center',
                spacing=4
            )
            
            # 이미지 저장
            result_folder = os.path.join("setting", "result")
            os.makedirs(result_folder, exist_ok=True)
            
            # 파일명 생성 (키워드 사용)
            # 현재 키워드를 파일명으로 사용 (파일명에 사용 불가한 문자 제거)
            safe_keyword = "".join(c for c in self.current_keyword if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_keyword = safe_keyword.replace(' ', '_')  # 공백을 언더스코어로 변경
            filename = f"{safe_keyword}.jpg"
            filepath = os.path.join(result_folder, filename)
            
            img.save(filepath, 'JPEG', quality=95)
            self._update_status(f"✅ 썸네일 생성 완료: {filename}")
            
            return filepath
            
        except Exception as e:
            self._report_error("썸네일 생성", e, show_traceback=False)
            return None
    
    def create_video_from_thumbnail(self, thumbnail_path):
        """썸네일 이미지를 3초 동영상으로 변환 (mp4 생성)"""
        try:
            # 동영상 기능이 OFF인 경우 생성하지 않음
            if not self.config.get("use_video", True):
                self._update_status("⚪ 동영상 기능 OFF - 스킵")
                return None
            
            # [추가] EXE 환경에서 FFmpeg 경로 강제 지정 로직
            import sys
            if getattr(sys, 'frozen', False):
                # PyInstaller가 파일을 푸는 임시 경로(_MEIPASS) 확인
                base_path = sys._MEIPASS
                ffmpeg_dir = os.path.join(base_path, "imageio_ffmpeg", "binaries")
                if os.path.exists(ffmpeg_dir):
                    # 해당 폴더 내의 ffmpeg-win64...exe 파일을 찾아서 경로 설정
                    for f in os.listdir(ffmpeg_dir):
                        if f.startswith("ffmpeg") and f.endswith(".exe"):
                            ffmpeg_path = os.path.join(ffmpeg_dir, f)
                            os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path
                            print(f"✅ EXE 내부 FFmpeg 경로 설정: {ffmpeg_path}")
                            self._update_status(f"✅ FFmpeg 경로 설정 완료")
                            break
            
            # moviepy 동적 import (실행 시점에 체크)
            try:
                from moviepy import ImageClip
                import moviepy.video.io.VideoFileClip
                import moviepy.video.VideoClip
                self._update_status("✅ moviepy 모듈 로드 성공")
            except ImportError as ie:
                self._update_status(f"❌ moviepy 임포트 실패: {str(ie)}")
                return None
            
            # FFmpeg는 moviepy가 자동으로 처리하므로 경로 확인 불필요
            
            if not thumbnail_path or not os.path.exists(thumbnail_path):
                raise FileNotFoundError(f"썸네일 이미지를 찾을 수 없습니다: {thumbnail_path}")
            
            self._update_status("🎬 동영상 생성 시작...")
            print(f"VIDEO: 동영상 생성 시작 (이미지: {thumbnail_path})")
            
            # 결과 파일 경로 설정
            result_folder = os.path.join("setting", "result")
            os.makedirs(result_folder, exist_ok=True)
            
            # 파일명 생성 (썸네일과 동일한 이름으로)
            base_name = os.path.splitext(os.path.basename(thumbnail_path))[0]
            video_filename = f"{base_name}.mp4"
            video_filepath = os.path.join(result_folder, video_filename)
            
            print(f"VIDEO: 동영상 저장 중: {video_filepath}")
            
            # exe 환경에서 stdout/stderr가 None일 때 처리
            import sys
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            
            class DummyFile:
                def write(self, x): pass
                def flush(self): pass
            
            if sys.stdout is None:
                sys.stdout = DummyFile()
            if sys.stderr is None:
                sys.stderr = DummyFile()
            
            try:
                # 썸네일 이미지로부터 3초 동영상 생성 (moviepy 2.x: duration을 생성자에 전달)
                clip = ImageClip(thumbnail_path, duration=3)
                
                # 동영상 저장 (moviepy 2.x)
                clip.write_videofile(
                    video_filepath, 
                    fps=24, 
                    codec='libx264', 
                    audio=False,
                    logger=None  # exe에서 안전하게 로깅 비활성화
                )
                
                # clip 리소스 해제
                clip.close()
            finally:
                # stdout/stderr 복원
                sys.stdout = original_stdout
                sys.stderr = original_stderr
            
            # 동영상 파일 생성 확인
            if not os.path.exists(video_filepath):
                raise FileNotFoundError(f"동영상 파일 생성 실패: {video_filepath}")
            
            self._update_status(f"✅ 동영상 생성 완료: {video_filename}")
            print(f"VIDEO: 동영상 생성 완료: {video_filepath}")
            return video_filepath
            
        except Exception as e:
            self._report_error("동영상 생성", e, show_traceback=True)
            print(f"VIDEO ERROR: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise  # 에러를 상위로 전달하여 명확히 실패 처리
    
    def crawl_latest_blog_posts(self):
        """네이버 블로그에서 최신글 3개의 URL과 제목을 크롤링"""
        try:
            blog_url = normalize_blog_address(self.blog_address)
            if not blog_url:
                self._update_status("⚠️ 블로그 주소가 설정되지 않았습니다")
                return []

            if blog_url != self.blog_address:
                self.blog_address = blog_url
                self._update_status(f"ℹ️ 블로그 주소 보정: {blog_url}")

            self._update_status(f"🔍 블로그 크롤링 시작: {blog_url}")

            posts = []
            blog_id = self._get_blog_id()

            # 현재 창 핸들 저장
            original_window = self.driver.current_window_handle
            
            # 새 탭에서 블로그 열기
            self.driver.execute_script("window.open(arguments[0], '_blank');", blog_url)
            self.driver.switch_to.window(self.driver.window_handles[-1])

            try:
                time.sleep(3)

                # mainFrame 전환 (데스크톱 블로그 기본 구조)
                try:
                    WebDriverWait(self.driver, 8).until(
                        EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame"))
                    )
                    self._update_status("✅ mainFrame 전환 완료")
                    time.sleep(1)
                except Exception:
                    self._update_status("ℹ️ mainFrame 전환 실패 - 현재 페이지에서 탐색")

                # "전체보기" 링크 클릭하여 전체 글 목록으로 이동
                try:
                    category_all_selectors = [
                        "a#category0",  # ID로 찾기
                        "a[href*='categoryNo=0'][href*='PostList.naver']",  # 전체보기 URL 패턴
                        "a.on[href*='categoryNo=0']",  # 활성화된 전체보기
                    ]
                    
                    category_clicked = False
                    for selector in category_all_selectors:
                        try:
                            category_link = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                            )
                            category_link.click()
                            self._update_status("✅ '전체보기' 클릭 완료")
                            time.sleep(2)
                            category_clicked = True
                            break
                        except Exception:
                            continue
                    
                    if not category_clicked:
                        self._update_status("ℹ️ 전체보기 버튼 없음 - 현재 페이지에서 크롤링")
                except Exception as e:
                    self._update_status(f"ℹ️ 전체보기 클릭 실패: {str(e)[:30]}")

                # 전체보기 목록 테이블에서 최신글 링크 찾기
                post_selectors = [
                    "a.pcol2._setTop._setTopListUrl",  # 전체보기 테이블 내 글 링크
                    "table.blog2_list.blog2_categorylist a.pcol2._setTop",  # 테이블 내 링크
                    "table.blog2_list a[href*='PostView.naver']",  # 테이블 내 PostView 링크
                    "a._setTopListUrl",  # _setTopListUrl 클래스
                    "a.pcol2[href*='PostView.naver'][href*='categoryNo=0']",  # categoryNo=0 포함
                ]
                
                post_elements = []
                seen_urls = set()
                for selector in post_selectors:
                    if len(post_elements) >= 6:
                        break
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            self._update_status(f"🔍 셀렉터 '{selector}'로 {len(elements)}개 발견")
                            for el in elements:
                                href = el.get_attribute("href")
                                if not href or href in seen_urls:
                                    continue
                                # PostView.naver 링크만 허용
                                if "PostView.naver" not in href and "postView.naver" not in href:
                                    continue
                                if blog_id and blog_id not in href and "blogId=" not in href:
                                    continue
                                seen_urls.add(href)
                                post_elements.append(el)
                                if len(post_elements) >= 6:
                                    break
                    except Exception as e:
                        self._update_status(f"⚠️ 셀렉터 '{selector}' 실패: {str(e)[:30]}")
                        continue
                
                if not post_elements:
                    try:
                        self._update_status("🧭 셀렉터 실패 - JS 수집 시도")
                        candidates = self.driver.execute_script("""
                            const blogId = arguments[0] || '';
                            const anchors = Array.from(document.querySelectorAll("a"));
                            const results = [];
                            const seen = new Set();
                            for (const a of anchors) {
                                const href = a.href || '';
                                if (!href) continue;
                                if (!/logno=|postview\\.naver|blog\\.naver\\.com\\//i.test(href)) continue;
                                if (blogId && !href.includes(blogId) && !href.includes('blogId=' + blogId)) continue;
                                if (seen.has(href)) continue;
                                const text = (a.textContent || '').trim();
                                if (!text) continue;
                                seen.add(href);
                                results.push({title: text, url: href});
                            }
                            return results.slice(0, 10);
                        """, blog_id)
                        if candidates:
                            self._update_status(f"🧭 JS 수집 {len(candidates)}개 발견")
                            for item in candidates:
                                post_elements.append(item)
                    except Exception as e:
                        self._update_status(f"⚠️ JS 수집 실패: {str(e)[:30]}")

                if not post_elements and blog_id:
                    try:
                        mobile_url = f"https://m.blog.naver.com/{blog_id}"
                        self._update_status(f"📱 모바일 페이지 재시도: {mobile_url}")
                        self.driver.get(mobile_url)
                        time.sleep(3)
                        mobile_elements = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            "a[href*='logNo='], a[href*='PostView.naver'], a[href*='m.blog.naver.com']"
                        )
                        if mobile_elements:
                            post_elements = mobile_elements[:10]
                    except Exception as e:
                        self._update_status(f"⚠️ 모바일 재시도 실패: {str(e)[:30]}")

                if not post_elements:
                    self._update_status("⚠️ 블로그 포스트를 찾을 수 없습니다")
                    return []
                
                self._update_status(f"📋 총 {len(post_elements)}개 요소 발견, 최신 3개 추출 시작")
                
                # 각 포스트의 URL과 제목 수집
                for idx, element in enumerate(post_elements):
                    if len(posts) >= 3:  # 3개 수집하면 중단
                        break
                        
                    try:
                        if isinstance(element, dict):
                            post_title = (element.get("title") or "").strip()
                            post_url = (element.get("url") or "").strip()
                        else:
                            post_title = (element.text or "").strip()
                            if not post_title:
                                post_title = (element.get_attribute("textContent") or "").strip()
                            post_url = element.get_attribute("href")

                        # 제목과 URL이 유효한지 확인
                        if not post_title or not post_url:
                            self._update_status(f"⚠️ 요소 {idx+1}: 제목 또는 URL 없음 - 스킵")
                            continue

                        # 카테고리/목록 링크 제외 (실제 포스트만 사용)
                        lower_url = post_url.lower()
                        if ("logno=" not in lower_url) and ("postview" not in lower_url) and ("blog.naver.com" not in lower_url):
                            self._update_status(f"⚠️ 요소 {idx+1}: 포스트 링크 아님 - 스킵")
                            continue

                        # 카테고리명 제외 (정교한 필터링)
                        lower_title = post_title.lower()
                        title_no_space = post_title.replace(" ", "")
                        
                        # 1. 카테고리 키워드 포함 여부
                        category_keywords = ["카테고리", "category", "전체보기", "분류", "목록"]
                        if any(keyword in lower_title for keyword in category_keywords):
                            self._update_status(f"⚠️ 요소 {idx+1}: 카테고리 키워드 포함 - 스킵 ('{post_title[:20]}')")
                            continue
                        
                        # 2. 너무 짧은 제목 (공백 제거 후 6자 미만)
                        if len(title_no_space) < 6:
                            self._update_status(f"⚠️ 요소 {idx+1}: 제목 너무 짧음 ({len(title_no_space)}자) - 스킵 ('{post_title}')")
                            continue
                        
                        # 3. 카테고리 패턴 (예: "XX 꿀팁", "XX 정보", "XX 모음")
                        category_patterns = ["꿀팁", "정보", "모음", "tip", "tips", "info"]
                        if len(title_no_space) <= 10 and any(post_title.endswith(pattern) or post_title.endswith(pattern.upper()) for pattern in category_patterns):
                            self._update_status(f"⚠️ 요소 {idx+1}: 카테고리 패턴 감지 - 스킵 ('{post_title}')")
                            continue

                        # 이미 추가된 URL인지 확인 (중복 방지)
                        if any(p['url'] == post_url for p in posts):
                            self._update_status(f"⚠️ 요소 {idx+1}: 중복 URL - 스킵")
                            continue
                        
                        posts.append({
                            'title': post_title,
                            'url': post_url,
                            'description': post_title  # 설명은 제목과 동일하게
                        })
                        
                        self._update_status(f"✅ 포스트 {len(posts)} 수집: {post_title[:30]}...")
                    except Exception as e:
                        self._update_status(f"⚠️ 요소 {idx+1} 처리 실패: {str(e)[:30]}")
                        continue
                
            except Exception as e:
                self._update_status(f"⚠️ 블로그 크롤링 중 오류: {str(e)[:50]}")

            finally:
                # 탭 닫고 원래 창으로 돌아가기
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
                self.driver.close()
                self.driver.switch_to.window(original_window)
            
            self._update_status(f"✅ 총 {len(posts)}개의 최신글 수집 완료")
            return posts[:3]  # 최대 3개만 반환
            
        except Exception as e:
            self._report_error("블로그 크롤링", e, show_traceback=False)
            return []

    def _get_blog_id(self):
        """블로그 주소에서 ID 추출"""
        blog_url = normalize_blog_address(self.blog_address)
        if not blog_url:
            return ""

        try:
            from urllib.parse import urlparse
            parsed = urlparse(blog_url)
            path = parsed.path.strip("/")
            if not path:
                return ""
            return path.split("/")[0]
        except Exception:
            return ""

    def crawl_popular_blog_posts(self):
        """네이버 블로그에서 인기글 3개의 URL과 제목을 크롤링 (모바일)"""
        try:
            blog_id = self._get_blog_id()
            if not blog_id:
                self._update_status("⚠️ 블로그 ID를 확인할 수 없습니다")
                return []

            popular_url = f"https://m.blog.naver.com/{blog_id}?tab=1"
            self._update_status(f"📊 인기글 크롤링 시작: {popular_url}")

            posts = []
            original_window = self.driver.current_window_handle

            self.driver.execute_script("window.open(arguments[0], '_blank');", popular_url)
            self.driver.switch_to.window(self.driver.window_handles[-1])

            try:
                time.sleep(3)

                selectors = [
                    "div.popular_block__QkTrS ul.list__Q47r_ li.item__axzBh a.link__dkflP",
                    "div[class*='popular_block'] ul[class*='list'] li[class*='item'] a[class*='link']",
                    "a[data-click-area='ppl.post']",
                ]

                post_elements = []
                seen_urls = set()
                for selector in selectors:
                    if len(post_elements) >= 6:
                        break
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            self._update_status(f"🔍 셀렉터 '{selector}'로 {len(elements)}개 발견")
                            for el in elements:
                                href = el.get_attribute("href")
                                if not href or href in seen_urls:
                                    continue
                                seen_urls.add(href)
                                post_elements.append(el)
                                if len(post_elements) >= 6:
                                    break
                    except Exception as e:
                        self._update_status(f"⚠️ 셀렉터 '{selector}' 실패: {str(e)[:30]}")
                        continue

                if not post_elements:
                    self._update_status("⚠️ 인기글 요소를 찾을 수 없습니다")
                    return []

                for idx, element in enumerate(post_elements):
                    if len(posts) >= 3:
                        break
                    try:
                        post_url = element.get_attribute("href")
                        if not post_url:
                            continue

                        post_title = ""
                        try:
                            title_el = element.find_element(By.CSS_SELECTOR, "strong.title__ItL9A")
                            post_title = title_el.text.strip()
                        except Exception:
                            try:
                                title_el = element.find_element(By.CSS_SELECTOR, "strong[class*='title']")
                                post_title = title_el.text.strip()
                            except Exception:
                                post_title = element.text.strip().split("\n")[0]

                        if not post_title:
                            post_title = post_url

                        desc_text = post_title
                        try:
                            desc_el = element.find_element(By.CSS_SELECTOR, "p.desc__Sxw5t")
                            desc_text = desc_el.text.strip() or post_title
                        except Exception:
                            pass

                        posts.append({
                            'title': post_title,
                            'url': post_url,
                            'description': desc_text
                        })
                        self._update_status(f"✅ 인기글 {len(posts)} 수집: {post_title[:30]}...")
                    except Exception as e:
                        self._update_status(f"⚠️ 인기글 {idx+1} 처리 실패: {str(e)[:30]}")
                        continue

            except Exception as e:
                self._update_status(f"⚠️ 인기글 크롤링 중 오류: {str(e)[:50]}")

            finally:
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
                self.driver.close()
                self.driver.switch_to.window(original_window)

            self._update_status(f"✅ 총 {len(posts)}개의 인기글 수집 완료")
            return posts[:3]
        except Exception as e:
            self._report_error("인기글 크롤링", e, show_traceback=False)
            return []
    
    def save_latest_posts_to_file(self, posts):
        """수집한 최신글 정보를 latest_posts.txt 파일에 저장"""
        try:
            if not posts:
                self._update_status("⚠️ 저장할 포스트가 없습니다")
                return False
            
            latest_posts_file = os.path.join(self.data_dir, "setting", "latest_posts.txt")
            
            # 파일에 저장 (제목|||링크|||설명 형식)
            with open(latest_posts_file, 'w', encoding='utf-8') as f:
                for post in posts:
                    # 제목|||링크|||설명 형식으로 저장
                    line = f"{post['title']}|||{post['url']}|||{post['description']}\n"
                    f.write(line)
            
            self._update_status(f"✅ latest_posts.txt 파일 저장 완료 ({len(posts)}개)")
            return True

        except Exception as e:
            self._report_error("최신글 파일 저장", e, show_traceback=False)
            return False

    def _load_related_posts_from_file(self):
        """latest_posts.txt에서 관련 글 목록을 로드"""
        posts = []
        try:
            latest_posts_file = os.path.join(self.data_dir, "setting", "latest_posts.txt")
            if not os.path.exists(latest_posts_file):
                return posts

            with open(latest_posts_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("|||")
                    if len(parts) < 2:
                        continue
                    title = parts[0].strip()
                    url = parts[1].strip()
                    if title and url:
                        posts.append({"title": title, "url": url})
            return posts
        except Exception:
            return posts
    

    def _write_body_with_linebreaks(self, text):
        """본문을 작성하면서 60자 이상이면 자동으로 줄바꿈"""
        max_length = 60
        
        # 이미 줄바꿈이 있으면 그대로 사용
        if '\n' in text:
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    # 줄 길이에 비례한 지연시간 (최소 0.1초, 최대 0.3초)
                    delay = max(0.1, min(0.3, len(line) / 200))
                    ActionChains(self.driver).send_keys(line).perform()
                    time.sleep(delay)
                    if i < len(lines) - 1:  # 마지막 줄이 아니면 Enter 2번
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        time.sleep(0.15)  # Enter 후 더 긴 대기
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        time.sleep(0.15)
        # 줄바꿈이 없고 60자 이상이면 자동 줄바꿈
        elif len(text) > max_length:
            # 문장 단위로 분리 (마침표, 느낌표, 물음표 기준 - 단, 따옴표 안은 제외)
            sentences = []
            current = ""
            in_quote = False  # 따옴표 안인지 체크
            quote_chars = ["'", '"', ''', ''', '"', '"']  # 작은따옴표, 큰따옴표 (일반/특수문자)
            
            for i, char in enumerate(text):
                current += char
                
                # 따옴표 상태 토글
                if char in quote_chars:
                    in_quote = not in_quote
                
                # 문장 종결 기호이면서 따옴표 밖에 있을 때만 문장 분리
                if char in ['.', '!', '?'] and len(current) > 0 and not in_quote:
                    # 다음 문자가 공백이거나 끝이면 문장 종료로 간주
                    if i + 1 >= len(text) or text[i + 1] in [' ', '\n', '\t']:
                        sentences.append(current.strip())
                        current = ""
            
            if current.strip():
                sentences.append(current.strip())
            
            # 각 문장을 입력하고 줄바꿈 (Enter 2번)
            for i, sentence in enumerate(sentences):
                if sentence:
                    # 문장 길이에 비례한 지연시간 (최소 0.1초, 최대 0.3초)
                    delay = max(0.1, min(0.3, len(sentence) / 200))
                    ActionChains(self.driver).send_keys(sentence).perform()
                    time.sleep(delay)
                    if i < len(sentences) - 1:  # 마지막 문장이 아니면 Enter 2번
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        time.sleep(0.15)  # Enter 후 더 긴 대기
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        time.sleep(0.15)
        else:
            # 짧은 문장은 그대로 입력
            ActionChains(self.driver).send_keys(text).perform()
            time.sleep(0.1)  # 안정성을 위해 대기시간 증가

    def _select_current_paragraph(self):
        """현재 커서가 있는 문단 전체 선택 (줄바꿈/모바일 래핑 대응)"""
        try:
            return bool(self.driver.execute_script("""
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return false;
                let node = sel.getRangeAt(0).startContainer;
                if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
                if (!node) return false;
                const block = node.closest('p, div, li');
                const target = block || node;
                const range = document.createRange();
                range.selectNodeContents(target);
                sel.removeAllRanges();
                sel.addRange(range);
                return true;
            """))
        except Exception:
            return False

    def _drag_select_current_paragraph(self):
        """현재 커서가 있는 문단을 마우스 드래그로 선택"""
        try:
            block = self.driver.execute_script("""
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return null;
                let node = sel.getRangeAt(0).startContainer;
                if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
                if (!node) return null;
                const block = node.closest('p, div, li') || node;
                block.scrollIntoView({block: 'center', inline: 'nearest'});
                return block;
            """)
            if not block:
                return False

            try:
                rect = block.rect
                start_x = 5
                start_y = max(5, int(rect.get("height", 20) / 2))
                end_x = max(10, int(rect.get("width", 200)) - 10)
                end_y = max(10, int(rect.get("height", 20)) - 5)
                actions = ActionChains(self.driver)
                actions.move_to_element_with_offset(
                    block, start_x, start_y
                ).click_and_hold().move_by_offset(
                    end_x - start_x, end_y - start_y
                ).release().perform()
                time.sleep(0.1)
                return True
            except Exception:
                pass

            try:
                actions = ActionChains(self.driver)
                # Shift+Home으로 문단 시작까지 드래그 선택
                actions.key_down(Keys.SHIFT).send_keys(Keys.HOME).key_up(Keys.SHIFT).perform()
                time.sleep(0.05)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def _selection_has_text(self):
        """현재 선택 영역에 텍스트가 있는지 확인"""
        try:
            return bool(self.driver.execute_script("""
                const sel = window.getSelection();
                if (!sel) return false;
                return sel.toString().trim().length > 0;
            """))
        except Exception:
            return False

    def _apply_link_to_selection(self, url):
        """현재 선택 영역에 링크 적용"""
        if not self._selection_has_text():
            return False
        try:
            success = bool(self.driver.execute_script("""
                const linkUrl = arguments[0];
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return false;
                try {
                    return document.execCommand('createLink', false, linkUrl);
                } catch (e) {
                    return false;
                }
            """, url))
            if success:
                return True
        except Exception:
            pass
        return self._apply_link_to_selection_ui(url)

    def _apply_link_to_selection_ui(self, url):
        """툴바를 이용해 링크 적용 (fallback)"""
        try:
            if not self._selection_has_text():
                return False
            if not self._save_selection():
                return False
            link_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-link-toolbar-button.se-property-toolbar-custom-layer-button"))
            )
            link_btn.click()
            self._sleep_with_checks(0.3)

            if not self._restore_selection():
                return False
            if not self._selection_has_text():
                return False
            link_input = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input.se-custom-layer-link-input"))
            )
            link_input.clear()
            link_input.send_keys(url)
            self._sleep_with_checks(0.1)

            try:
                apply_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-custom-layer-link-apply-button"))
                )
                apply_btn.click()
                self._sleep_with_checks(0.2)
            except Exception:
                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                self._sleep_with_checks(0.2)
            return True
        except Exception:
            return False

    def _apply_bold_to_selection(self):
        """현재 선택 영역에 볼드 적용 (에디터 기본 기능 활용)"""
        try:
            return bool(self.driver.execute_script("""
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return false;
                try {
                    return document.execCommand('bold', false, null);
                } catch (e) {
                    return false;
                }
            """))
        except Exception:
            return False

    def _apply_section_title_format(self):
        """현재 선택 영역에 소제목(문단 서식) 적용"""
        try:
            format_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-text-format-toolbar-button.se-property-toolbar-label-select-button"))
            )
            format_btn.click()
            time.sleep(0.2)

            subtitle_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-text-format-sectionTitle-button"))
            )
            subtitle_btn.click()
            time.sleep(0.2)
            return True
        except Exception:
            return False

    def _collapse_selection(self):
        """선택 영역을 커서로 해제"""
        try:
            self.driver.execute_script("""
                const sel = window.getSelection();
                if (sel && sel.rangeCount > 0) {
                    sel.collapseToEnd();
                }
            """)
        except Exception:
            pass
        try:
            ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
            time.sleep(0.05)
        except Exception:
            pass

    def _select_last_paragraph(self, collapse=False):
        """에디터 마지막 문단 선택 또는 커서 이동 (마우스 이동 없음)"""
        try:
            return bool(self.driver.execute_script("""
                const collapse = arguments[0];
                const candidates = document.querySelectorAll(
                  ".se-section-text p, .se-section-text, .se-component-content, .se-section"
                );
                if (!candidates || candidates.length === 0) return false;
                const target = candidates[candidates.length - 1];
                const range = document.createRange();
                range.selectNodeContents(target);
                if (collapse) range.collapse(false);
                const sel = window.getSelection();
                if (!sel) return false;
                sel.removeAllRanges();
                sel.addRange(range);
                return true;
            """, collapse))
        except Exception:
            return False

    def _focus_editor_end(self):
        """에디터 마지막 위치로 커서 이동"""
        try:
            return bool(self.driver.execute_script("""
                const body = document.querySelector("div.se-editor, div.se-content, .se-container");
                if (!body) return false;
                const candidates = body.querySelectorAll(
                  ".se-section-text p, .se-section-text, .se-component-content, .se-section"
                );
                const target = candidates && candidates.length ? candidates[candidates.length - 1] : body;
                try { target.scrollIntoView({block:'end', inline:'nearest'}); } catch (e) {}
                const range = document.createRange();
                range.selectNodeContents(target);
                range.collapse(false);
                const sel = window.getSelection();
                if (!sel) return false;
                sel.removeAllRanges();
                sel.addRange(range);
                return true;
            """))
        except Exception:
            return False

    def _insert_text_at_cursor(self, text):
        """현재 커서 위치에 텍스트 삽입"""
        try:
            return bool(self.driver.execute_script("""
                const value = arguments[0];
                try {
                    return document.execCommand('insertText', false, value);
                } catch (e) {
                    return false;
                }
            """, text))
        except Exception:
            return False

    def _focus_after_image_block(self):
        """마지막 이미지 블록 뒤로 커서 이동"""
        try:
            return bool(self.driver.execute_script("""
                const img = document.querySelectorAll(".se-section-image")?.length
                  ? document.querySelectorAll(".se-section-image")[document.querySelectorAll(".se-section-image").length - 1]
                  : null;
                if (!img) return false;
                const section = img.closest('.se-section') || img;
                const range = document.createRange();
                range.setStartAfter(section);
                range.collapse(true);
                const sel = window.getSelection();
                if (!sel) return false;
                sel.removeAllRanges();
                sel.addRange(range);
                return true;
            """))
        except Exception:
            return False

    def _set_text_align(self, align):
        """에디터 정렬 설정 (center/left)"""
        try:
            dropdown = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-property-toolbar-drop-down-button"))
            )
            dropdown.click()
            time.sleep(0.2)
            if align == "center":
                option_selector = "button.se-toolbar-option-align-center-button"
                cmd = "justifyCenter"
            else:
                option_selector = "button.se-toolbar-option-align-left-button"
                cmd = "justifyLeft"
            option_btn = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, option_selector))
            )
            option_btn.click()
            time.sleep(0.2)
            return True
        except Exception:
            try:
                cmd = "justifyCenter" if align == "center" else "justifyLeft"
                self.driver.execute_script("document.execCommand(arguments[0], false, null);", cmd)
                return True
            except Exception:
                return False

    def _insert_horizontal_line(self, line_choice=None):
        """구분선 삽입 (랜덤 선택 또는 고정 선택)"""
        try:
            line_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-document-toolbar-select-option-button[data-name='horizontal-line']"))
            )
            line_btn.click()
            time.sleep(0.2)

            if not line_choice:
                line_choice = random.choice(["default", "line1", "line1", "line3", "line4", "line5"])
            line_opt = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, f"button.se-toolbar-option-icon-button[data-name='horizontal-line'][data-value='{line_choice}']"))
            )
            line_opt.click()
            time.sleep(0.2)
            self._update_status(f"✅ 구분선 삽입 완료: {line_choice}")
            return line_choice
        except Exception as e:
            self._update_status(f"⚠️ 구분선 삽입 실패(계속 진행): {str(e)[:80]}")
            return None

    def _save_selection(self):
        """현재 선택 영역 저장 (링크 삽입 전용)"""
        try:
            return bool(self.driver.execute_script("""
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return false;
                window.__savedRange = sel.getRangeAt(0).cloneRange();
                return true;
            """))
        except Exception:
            return False

    def _restore_selection(self):
        """저장된 선택 영역 복원 (링크 삽입 전용)"""
        try:
            return bool(self.driver.execute_script("""
                const saved = window.__savedRange;
                const sel = window.getSelection();
                if (!saved || !sel) return false;
                sel.removeAllRanges();
                sel.addRange(saved);
                return true;
            """))
        except Exception:
            return False
    
    def write_post(self, title, content, thumbnail_path=None, video_path=None, is_first_post=True):
        """블로그 글 작성"""
        try:
            if not self._ensure_blog_tab():
                return False
            # 첫 포스팅인 경우 블로그 홈으로 바로 이동
            if is_first_post:
                self._update_status("📝 첫 포스팅: 블로그 홈으로 이동 중...")
                if not self._ensure_blog_tab("https://section.blog.naver.com/BlogHome.naver?directoryNo=0&currentPage=1&groupId=0"):
                    return False
                self._sleep_with_checks(3)
                self._wait_if_paused()
                
                # 블로그 주소가 설정되어 있으면 최신글 크롤링
                if self.blog_address:
                    if self.related_posts_mode == "popular":
                        self._update_status("📊 블로그 인기글 크롤링 시작...")
                        latest_posts = self.crawl_popular_blog_posts()
                    else:
                        self._update_status("🔍 블로그 최신글 크롤링 시작...")
                        latest_posts = self.crawl_latest_blog_posts()
                    if latest_posts:
                        self.save_latest_posts_to_file(latest_posts)
                        label = "인기글" if self.related_posts_mode == "popular" else "최신글"
                        self._update_status(f"✅ {len(latest_posts)}개 {label} 저장 완료")
                    else:
                        label = "인기글" if self.related_posts_mode == "popular" else "최신글"
                        self._update_status(f"⚠️ {label} 크롤링 실패 - '함께 보면 좋은 글' 섹션 생략")
                

                # 글쓰기 버튼 찾기
                write_btn_selectors = [
                    "a.item[ng-href*='GoBlogWrite']",
                    "a[href*='GoBlogWrite.naver']",
                    ".sp_common.icon_write"
                ]
                
                for selector in write_btn_selectors:
                    try:
                        write_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        if write_btn:
                            write_btn.click()
                            self._sleep_with_checks(3)
                            self._update_status("✅ 블로그 홈에서 글쓰기 버튼 클릭 성공")
                            
                            # 새 창이 열렸다면 전환
                            if len(self.driver.window_handles) > 1:
                                self.driver.switch_to.window(self.driver.window_handles[-1])
                                self._sleep_with_checks(2)
                            break
                    except:
                        continue
            else:
                # 두 번째 이후 포스팅: 페이지 확인만
                self._update_status("📝 글쓰기 페이지 확인 중...")
                
                # 프레임에서 빠져나오기 (이전 포스팅에서 프레임 안에 있을 수 있음)
                try:
                    self.driver.switch_to.default_content()
                except:
                    pass
                
                # 새 창이 열렸다면 전환
                if len(self.driver.window_handles) > 1:
                    self._update_status("🪟 새 창으로 전환 중...")
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    self._sleep_with_checks(2)
            
            # mainFrame으로 전환
            self._update_status("🖼️ 에디터 프레임으로 전환 중...")
            try:
                mainframe = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "mainFrame"))
                )
                self.driver.switch_to.frame(mainframe)
                self._sleep_with_checks(1)
                self._update_status("✅ 프레임 전환 완료")
            except:
                self._update_status("⚠️ 프레임 전환 실패 - 메인 페이지에서 진행")
            
            # 팝업창 확인 및 '취소' 버튼 클릭
            self._update_status("🔍 팝업 확인 중...")
            try:
                popup_cancel = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-popup-button.se-popup-button-cancel"))
                )
                popup_cancel.click()
                self._update_status("✅ 팝업 닫기 완료")
                self._sleep_with_checks(1)
            except:
                pass
            self._wait_if_paused()

            # 도움말 패널 닫기
            self._update_status("📚 도움말 패널 확인 중...")
            try:
                help_close = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-help-panel-close-button"))
                )
                help_close.click()
                self._update_status("✅ 도움말 닫기 완료")
                self._sleep_with_checks(1)
            except:
                pass

            # 제목 입력
            self._update_status("📌 제목 입력 중...")
            try:
                title_elem = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-documentTitle"))
                )
                
                actions = ActionChains(self.driver)
                actions.move_to_element(title_elem).click().send_keys(title).perform()
                self._sleep_with_checks(1)
                
                self._update_status(f"✅ 제목 입력 완료: {title[:30]}...")
            except Exception as e:
                self._update_status(f"❌ 제목 입력 실패: {str(e)}")
                return False
            
            # 본문 작성
            self._update_status("📄 본문 작성 시작...")
            
            try:
                content_elem = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text"))
                )
                
                actions = ActionChains(self.driver)
                actions.move_to_element(content_elem).click().perform()
                self._sleep_with_checks(0.5)
                
                # 본문을 줄 단위로 분리
                content_lines = content.split('\n')
                
                # 외부 링크 사용 여부 확인
                use_external_link = self.external_link and self.external_link_text
                
                # 서론 줄만 분리 (첫 줄)
                intro_lines = []
                body_lines = []
                
                first_content_found = False
                for line in content_lines:
                    if line.strip():
                        if not first_content_found:
                            intro_lines.append(line)
                            first_content_found = True
                        else:
                            body_lines.append(line)
                
                total_lines = len([l for l in intro_lines if l.strip()]) + len([l for l in body_lines if l.strip()])
                self._update_status(f"📝 총 {total_lines}줄 작성 시작...")
                
                current_line = 0
                
                # 1. 서론 작성 (ActionChains로 직접 타이핑)
                for line in intro_lines:
                    self._wait_if_paused()
                    if self.should_stop:
                        self._update_status("⏹️ 사용자가 포스팅을 중지했습니다.")
                        return False

                    if line.strip():
                        current_line += 1

                        # 본문과 동일하게 문장 길이에 따라 줄바꿈 처리
                        self._write_body_with_linebreaks(line)
                        # 서론 줄 간 구분
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        self._sleep_with_checks(0.1)
                
                # 서론 작성 후 Enter 한번 더
                actions = ActionChains(self.driver)
                actions.send_keys(Keys.ENTER).perform()
                self._sleep_with_checks(0.3)
                
                # 2. 외부 링크 삽입 (설정된 경우)
                if use_external_link:
                    self._update_status("🔗 외부 링크 삽입 중...")
                    
                    # 앵커 텍스트 클립보드로 복사
                    pyperclip.copy(self.external_link_text)
                    
                    # Ctrl+V로 붙여넣기
                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    self._sleep_with_checks(0.5)
                    
                    # 앵커 텍스트만 선택 (Home으로 이동 후 Shift+End로 줄 끝까지 선택)
                    if not self._select_current_paragraph():
                        actions = ActionChains(self.driver)
                        actions.send_keys(Keys.HOME).perform()
                        self._sleep_with_checks(0.1)
                        actions.key_down(Keys.SHIFT).send_keys(Keys.END).key_up(Keys.SHIFT).perform()
                    self._sleep_with_checks(0.5)
                    
                    # 중앙 정렬 버튼 클릭
                    try:
                        align_dropdown = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-property-toolbar-drop-down-button.se-align-left-toolbar-button"))
                        )
                        align_dropdown.click()
                        self._sleep_with_checks(0.3)
                        
                        center_align_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-align-center-button"))
                        )
                        center_align_btn.click()
                        self._sleep_with_checks(0.3)
                        self._update_status("✅ 중앙 정렬 완료")
                    except Exception as e:
                        self._update_status(f"⚠️ 중앙 정렬 실패: {str(e)}")
                    
                    # 앵커 텍스트 다시 선택
                    if not self._select_current_paragraph():
                        actions = ActionChains(self.driver)
                        actions.send_keys(Keys.HOME).perform()
                        self._sleep_with_checks(0.1)
                        actions.key_down(Keys.SHIFT).send_keys(Keys.END).key_up(Keys.SHIFT).perform()
                    self._sleep_with_checks(0.3)
                    
                    # 폰트 크기 24 설정
                    try:
                        font_size_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-font-size-code-toolbar-button.se-property-toolbar-label-select-button"))
                        )
                        font_size_btn.click()
                        self._sleep_with_checks(0.3)
                        
                        fs24_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-font-size-code-fs24-button"))
                        )
                        fs24_btn.click()
                        self._sleep_with_checks(0.3)
                        self._update_status("✅ 폰트 크기 24 적용")
                    except Exception as e:
                        self._update_status(f"⚠️ 폰트 크기 변경 실패: {str(e)}")
                    
                    # 앵커 텍스트 다시 선택
                    if not self._select_current_paragraph():
                        actions = ActionChains(self.driver)
                        actions.send_keys(Keys.HOME).perform()
                        self._sleep_with_checks(0.1)
                        actions.key_down(Keys.SHIFT).send_keys(Keys.END).key_up(Keys.SHIFT).perform()
                    self._sleep_with_checks(0.3)
                    
                    # 볼드체 적용 (Ctrl+B)
                    actions = ActionChains(self.driver)
                    actions.key_down(Keys.CONTROL).send_keys('b').key_up(Keys.CONTROL).perform()
                    self._sleep_with_checks(0.3)
                    self._update_status("✅ 볼드체 적용")
                    
                    # 텍스트 끝으로 이동
                    actions = ActionChains(self.driver)
                    actions.send_keys(Keys.END).perform()
                    self._sleep_with_checks(0.3)
                    
                    # 앵커 텍스트 전체 선택 (링크 삽입을 위해)
                    if not self._select_current_paragraph():
                        actions = ActionChains(self.driver)
                        actions.send_keys(Keys.HOME).perform()
                        self._sleep_with_checks(0.1)
                        actions.key_down(Keys.SHIFT).send_keys(Keys.END).key_up(Keys.SHIFT).perform()
                    self._sleep_with_checks(0.3)
                    
                    # 링크 버튼 클릭
                    try:
                        link_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-link-toolbar-button.se-property-toolbar-custom-layer-button"))
                        )
                        link_btn.click()
                        self._sleep_with_checks(0.5)
                        
                        # URL 입력
                        link_input = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "input.se-custom-layer-link-input"))
                        )
                        link_input.clear()
                        link_input.send_keys(self.external_link)
                        self._sleep_with_checks(0.3)
                        
                        # Enter로 확인
                        actions = ActionChains(self.driver)
                        actions.send_keys(Keys.ENTER).perform()
                        self._sleep_with_checks(0.5)
                        
                        self._update_status(f"✅ 외부 링크 삽입 완료: {self.external_link_text}")
                        
                    except Exception as e:
                        self._update_status(f"⚠️ 링크 삽입 실패: {str(e)}")
                        actions = ActionChains(self.driver)
                        actions.send_keys(Keys.ESCAPE).perform()
                        self._sleep_with_checks(0.3)
                    
                    # 링크 삽입 후 Enter
                    actions = ActionChains(self.driver)
                    actions.send_keys(Keys.END).perform()
                    self._sleep_with_checks(0.2)
                    actions.send_keys(Keys.ENTER).perform()
                    self._sleep_with_checks(0.3)
                    
                    # 폰트 크기 16으로 변경
                    try:
                        font_size_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-font-size-code-toolbar-button.se-property-toolbar-label-select-button"))
                        )
                        font_size_btn.click()
                        self._sleep_with_checks(0.3)
                        
                        fs16_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-font-size-code-fs16-button"))
                        )
                        fs16_btn.click()
                        self._sleep_with_checks(0.3)
                        self._update_status("✅ 폰트 크기 16 적용")
                    except Exception as e:
                        self._update_status(f"⚠️ 폰트 크기 변경 실패: {str(e)}")
                    
                    # Ctrl+B로 볼드체 해제
                    actions = ActionChains(self.driver)
                    actions.key_down(Keys.CONTROL).send_keys('b').key_up(Keys.CONTROL).perform()
                    self._sleep_with_checks(0.3)
                    self._update_status("✅ 볼드체 해제")
                
                # '함께 보면 좋은 글' 섹션 추가 - 중복 삽입 방지를 위해 제거됨
                # (소제목/본문 작성 후, 동영상 업로드 전에 한 번만 수행하도록 변경)
                pass
                
                # 썸네일 삽입 (외부 링크 설정과 무관하게 항상 실행)
                thumbnail_inserted = False
                if thumbnail_path:
                    self._update_status("🖼️ 썸네일 삽입 중...")
                    try:
                        # 외부 링크 없을 때만 중앙 정렬 먼저 수행
                        if not use_external_link:
                            try:
                                self._update_status("⚙️ 중앙 정렬 설정 중...")
                                align_dropdown = WebDriverWait(self.driver, 3).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-property-toolbar-drop-down-button.se-align-left-toolbar-button"))
                                )
                                align_dropdown.click()
                                self._sleep_with_checks(0.3)
                                
                                center_align_btn = WebDriverWait(self.driver, 3).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-align-center-button"))
                                )
                                center_align_btn.click()
                                self._sleep_with_checks(0.3)
                                self._update_status("✅ 중앙 정렬 완료")
                            except Exception as e:
                                self._update_status(f"⚠️ 중앙 정렬 실패: {str(e)}")
                        
                        # -----------------------------------------------------------
                        # 사진 버튼을 먼저 클릭하고 파일 입력 요소를 찾습니다.
                        # -----------------------------------------------------------
                        self._update_status("🖼️ 사진 버튼 클릭 중...")
                        image_btn = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "button.se-image-toolbar-button.se-document-toolbar-basic-button"))
                        )
                        self.driver.execute_script("arguments[0].click();", image_btn)
                        self._sleep_with_checks(2)

                        # 파일 입력 요소 찾기
                        self._update_status("📂 파일 입력 요소 찾는 중...")
                        file_input = None
                        selectors = [
                            "input[type='file']",
                            "input[id*='file']",
                            ".se-file-input",
                            "input[accept*='image']"
                        ]
                        for selector in selectors:
                            try:
                                file_input = WebDriverWait(self.driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                )
                                if file_input:
                                    self._update_status(f"✅ 파일 입력 요소 찾음: {selector}")
                                    break
                            except:
                                continue
                        
                        if not file_input:
                            raise Exception("파일 입력 요소를 찾을 수 없습니다 (모든 방법 실패)")
                        
                        # 절대 경로로 파일 전송 (버튼 클릭 없이 바로 전송)
                        abs_path = os.path.abspath(thumbnail_path)
                        self._update_status(f"⏳ 썸네일 업로드 중: {os.path.basename(abs_path)}")
                        
                        # 파일 경로 전송
                        file_input.send_keys(abs_path)
                        
                        # 업로드 대기
                        self._sleep_with_checks(5)
                        self._update_status("✅ 썸네일 업로드 명령 전달 완료")

                        # 탐색기 대화상자 닫기 (브라우저 종료 방지)
                        try:
                            pyautogui.press('esc')
                            self._sleep_with_checks(0.5)
                        except Exception:
                            pass
                        
                        # -----------------------------------------------------------
                        # [추가] 썸네일 편집 (액자/서명/폰트 크기) 및 사진 설명 입력
                        # -----------------------------------------------------------
                        try:
                            self._update_status("🖼️ 썸네일 편집 시작...")

                            try:
                                img = WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, ".se-section-image img.se-image-resource"))
                                )
                                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img)
                                try:
                                    ActionChains(self.driver).move_to_element(img).click().perform()
                                    self._sleep_with_checks(0.2)
                                except Exception:
                                    pass
                                self.driver.execute_script("""
                                    const img = arguments[0];
                                    const section = img.closest('.se-section-image') || img;
                                    section.click();
                                """, img)
                                WebDriverWait(self.driver, 3).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "li.se-toolbar-item-image-edit button"))
                                )
                                self._sleep_with_checks(0.3)
                            except Exception:
                                image_candidates = self.driver.find_elements(
                                    By.CSS_SELECTOR,
                                    "div.se-component-content img, img.se-image-resource, img.se-image"
                                )
                                if image_candidates:
                                    target_image = image_candidates[-1]
                                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target_image)
                                    try:
                                        ActionChains(self.driver).move_to_element(target_image).click().perform()
                                    except Exception:
                                        self.driver.execute_script("arguments[0].click();", target_image)
                                    self._sleep_with_checks(0.5)
                            except Exception:
                                pass
                            
                            edit_btn = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "li.se-toolbar-item-image-edit button"))
                            )
                            self.driver.execute_script("arguments[0].click();", edit_btn)
                            self._sleep_with_checks(5)
                            
                            frame_btn = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.npe_btn_control.npe_btn_frame"))
                            )
                            self.driver.execute_script("arguments[0].click();", frame_btn)
                            self._sleep_with_checks(0.5)
                            
                            frame_choice = random.choice(["1", "1", "4"])
                            frame_item = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, f"button.npe_btn_detail_thumb.npe_btn_detail_frame[data-frame='{frame_choice}']"))
                            )
                            self.driver.execute_script("arguments[0].click();", frame_item)
                            self._sleep_with_checks(0.5)
                            
                            sign_btn = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.npe_btn_control.npe_btn_sign"))
                            )
                            self.driver.execute_script("arguments[0].click();", sign_btn)
                            self._sleep_with_checks(0.5)
                            
                            sign_text_btn = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.npe_btn_icon_item.npe_btn_sign_text[data-signature='text']"))
                            )
                            self.driver.execute_script("arguments[0].click();", sign_text_btn)
                            self._sleep_with_checks(0.5)
                            
                            font_dropdown = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.npe_text_tool.npe_text_font_size"))
                            )
                            self.driver.execute_script("arguments[0].click();", font_dropdown)
                            self._sleep_with_checks(0.3)
                            
                            font_11 = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "li.npe_tool_item[data-type='11']"))
                            )
                            self.driver.execute_script("arguments[0].click();", font_11)
                            self._sleep_with_checks(0.3)
                            
                            done_btn = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.npe_btn_header.npe_btn_submit"))
                            )
                            self.driver.execute_script("arguments[0].click();", done_btn)
                            self._sleep_with_checks(2)
                            self._update_status("✅ 썸네일 편집 완료")
                        except Exception as e:
                            error_msg = str(e) if str(e) else type(e).__name__
                            self._update_status(f"⚠️ 썸네일 편집 실패(진행 계속): {error_msg[:100]}")
                            print(f"[썸네일 편집 실패 상세]\n{traceback.format_exc()}")
                        
                        try:
                            self._update_status("✍️ 사진 설명 입력 중...")
                            
                            # 사진 설명 영역 찾기 (다양한 선택자 시도)
                            caption_target = None
                            caption_selectors = [
                                "div.se-module.se-module-text.se-caption",
                                "div.se-caption",
                                "div[data-module='caption']",
                                ".se-section-image + div.se-module-text"
                            ]
                            
                            for selector in caption_selectors:
                                try:
                                    caption_target = WebDriverWait(self.driver, 3).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                    )
                                    self._update_status(f"✅ 사진 설명 영역 발견: {selector}")
                                    break
                                except Exception:
                                    continue
                            
                            if not caption_target:
                                raise Exception("사진 설명 영역을 찾을 수 없습니다")
                            
                            # 사진 설명 영역 클릭 (여러 방법 시도)
                            try:
                                placeholder = self.driver.find_element(
                                    By.CSS_SELECTOR,
                                    "div.se-module.se-caption span.se-placeholder.__se_placeholder"
                                )
                                self.driver.execute_script("""
                                    const el = arguments[0];
                                    el.scrollIntoView({block:'center', inline:'nearest'});
                                    el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                                    el.click();
                                    el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                                """, placeholder)
                                self._update_status("✅ placeholder 클릭 성공")
                            except Exception:
                                try:
                                    caption_p = caption_target.find_element(By.CSS_SELECTOR, "p.se-text-paragraph")
                                    self.driver.execute_script("""
                                        const el = arguments[0];
                                        el.scrollIntoView({block:'center', inline:'nearest'});
                                        el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                                        el.click();
                                        el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                                    """, caption_p)
                                    self._update_status("✅ caption_p 클릭 성공")
                                except Exception:
                                    self.driver.execute_script("""
                                        const el = arguments[0];
                                        el.scrollIntoView({block:'center', inline:'nearest'});
                                        el.click();
                                    """, caption_target)
                                    self._update_status("✅ caption_target 클릭 성공")
                            
                            self._sleep_with_checks(0.5)
                            
                            desc_text = self.current_keyword if self.current_keyword else title
                            self._update_status(f"⌨️ 입력할 텍스트: {desc_text}")
                            
                            # 텍스트 입력
                            ActionChains(self.driver).send_keys(desc_text).perform()
                            self._sleep_with_checks(0.3)
                            
                            # Enter 2번 입력하여 포커스 이동
                            ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                            self._sleep_with_checks(0.2)
                            ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                            self._sleep_with_checks(0.3)
                            
                            # 입력 확인
                            try:
                                result = self.driver.execute_script("""
                                    const captions = document.querySelectorAll("div.se-module.se-caption");
                                    if (captions.length === 0) return {found: false, reason: 'caption 모듈 없음'};
                                    
                                    for (const caption of captions) {
                                        const text = (caption.textContent || '').trim();
                                        if (text && !text.includes('사진 설명을 입력하세요')) {
                                            return {found: true, text: text};
                                        }
                                    }
                                    return {found: false, reason: 'placeholder 텍스트 또는 빈 내용'};
                                """)
                                
                                if result.get('found'):
                                    actual_text = result.get('text', '')[:50]
                                    self._update_status(f"✅ 사진 설명 입력 완료: {actual_text}")
                                else:
                                    reason = result.get('reason', '알 수 없음')
                                    self._update_status(f"⚠️ 사진 설명 입력 확인 실패: {reason} (계속 진행)")
                            except Exception as check_e:
                                self._update_status(f"⚠️ 사진 설명 확인 중 오류: {str(check_e)[:50]} (계속 진행)")
                            
                            self._set_text_align("left")
                            self._focus_after_image_block()
                            self._sleep_with_checks(0.3)
                        except Exception as e:
                            error_msg = str(e) if str(e) else type(e).__name__
                            self._update_status(f"⚠️ 사진 설명 입력 실패(계속 진행): {error_msg[:100]}")
                            print(f"[사진 설명 입력 실패 상세]\n{traceback.format_exc()}")
                        
                        # -----------------------------------------------------------
                        # [후속 처리] 혹시 뜰 수 있는 웹 이미지 편집기 팝업 닫기
                        # (윈도우 탐색기는 안 뜨지만, 네이버 웹 팝업이 뜰 경우 대비)
                        # -----------------------------------------------------------
                        try:
                            # 팝업 닫기/확인 버튼 시도
                            close_selectors = [
                                "button.se-popup-button-close", 
                                "button.se-popup-button-confirm",
                                ".se-image-edit-close",
                                "button[aria-label='닫기']",
                                "button.se-sidebar-close-button[data-log='llib.close']"
                            ]
                            
                            popup_handled = False
                            for btn_sel in close_selectors:
                                try:
                                    btn = WebDriverWait(self.driver, 1).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, btn_sel))
                                    )
                                    btn.click()
                                    popup_handled = True
                                    self._sleep_with_checks(1)
                                    break
                                except:
                                    continue
                            
                            # 버튼 처리가 안되었다면 ESC 키 한 번 전송 (안전장치)
                            if not popup_handled:
                                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                                self._sleep_with_checks(0.5)
                                
                        except Exception:
                            pass # 팝업 없으면 통과

                        self._update_status("✅ 썸네일 삽입 완료")
                        
                        # Enter 키는 사진 설명 입력 후 처리됨
                        
                        # 왼쪽 정렬로 복구
                        self._update_status("⚙️ 왼쪽 정렬로 복구 중...")
                        if self._set_text_align("left"):
                            self._update_status("✅ 왼쪽 정렬 완료")
                        else:
                            self._update_status("⚠️ 왼쪽 정렬 실패 (계속 진행)")
                        
                        thumbnail_inserted = True
                        
                    except Exception as e:
                        self._update_status(f"⚠️ 썸네일 삽입 실패(진행 계속): {str(e)[:100]}")
                        # 실패하더라도 멈추지 않고 다음 단계로 진행
                        pass
                
                # 3. 소제목/본문 작성
                # body_lines를 소제목과 본문으로 분리 (6줄씩: 소제목1, 본문1, 소제목2, 본문2, 소제목3, 본문3)
                
                # 먼저 빈 줄 제거하고 실제 내용만 추출
                content_lines = [line for line in body_lines if line.strip()]
                self._update_status(f"📋 본문 내용: {len(content_lines)}줄 (원본: {len(body_lines)}줄)")
                
                if len(content_lines) >= 6:
                    self._update_status("✅ 소제목/본문 형식으로 작성 시작...")
                    # 첫 6줄은 소제목/본문 형식으로 작성
                    subtitle1 = content_lines[0]
                    body1 = content_lines[1]
                    subtitle2 = content_lines[2]
                    body2 = content_lines[3]
                    subtitle3 = content_lines[4]
                    body3 = content_lines[5]

                    def _apply_subtitle_format():
                        try:
                            actions = ActionChains(self.driver)
                            actions.key_down(Keys.SHIFT).send_keys(Keys.HOME).key_up(Keys.SHIFT).perform()
                            self._sleep_with_checks(0.1)

                            if not self._apply_bold_to_selection():
                                actions = ActionChains(self.driver)
                                actions.key_down(Keys.CONTROL).send_keys('b').key_up(Keys.CONTROL).perform()
                                self._sleep_with_checks(0.1)

                            self._apply_section_title_format()
                            self._collapse_selection()
                        except Exception as e:
                            self._update_status(f"⚠️ 소제목 서식 적용 실패(계속 진행): {str(e)[:80]}")
                    
                    self._update_status("✍️ 소제목1 작성 중...")
                    if thumbnail_inserted:
                        self._focus_after_image_block()
                        self._sleep_with_checks(0.1)
                    else:
                        try:
                            content_focus = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-section-text"))
                            )
                            content_focus.click()
                            self._sleep_with_checks(0.1)
                        except Exception:
                            pass
                    ActionChains(self.driver).send_keys(subtitle1).perform()
                    self._sleep_with_checks(0.1)
                    _apply_subtitle_format()
                    self._collapse_selection()
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    self._sleep_with_checks(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 소제목 후 ENTER 한 번 더
                    self._sleep_with_checks(0.1)
                    
                    self._update_status("✍️ 본문1 작성 중...")
                    # 본문1을 문장 단위로 줄바꿈 (60자 이상이면)
                    self._write_body_with_linebreaks(body1)
                    self._sleep_with_checks(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 본문 끝에 ENTER
                    self._sleep_with_checks(0.3)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    self._sleep_with_checks(0.2)
                    
                    self._update_status("✍️ 소제목2 작성 중...")
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    self._sleep_with_checks(0.1)
                    ActionChains(self.driver).send_keys(subtitle2).perform()
                    self._sleep_with_checks(0.1)
                    _apply_subtitle_format()
                    self._collapse_selection()
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    self._sleep_with_checks(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 소제목 후 ENTER 한 번 더
                    self._sleep_with_checks(0.1)
                    
                    self._update_status("✍️ 본문2 작성 중...")
                    # 본문2를 문장 단위로 줄바꿈 (60자 이상이면)
                    self._write_body_with_linebreaks(body2)
                    self._sleep_with_checks(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 본문 끝에 ENTER
                    self._sleep_with_checks(0.3)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    self._sleep_with_checks(0.2)
                    
                    self._update_status("✍️ 소제목3 작성 중...")
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    self._sleep_with_checks(0.1)
                    ActionChains(self.driver).send_keys(subtitle3).perform()
                    self._sleep_with_checks(0.1)
                    _apply_subtitle_format()
                    self._collapse_selection()
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    self._sleep_with_checks(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 소제목 후 ENTER 한 번 더
                    self._sleep_with_checks(0.2)
                    
                    self._update_status("✍️ 본문3 작성 중...")
                    # 본문3을 문장 단위로 줄바꿈 (60자 이상이면)
                    self._write_body_with_linebreaks(body3)
                    self._sleep_with_checks(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 본문 끝에 ENTER
                    self._sleep_with_checks(0.3)
                    
                    # 구분선 삽입 (관련 글 전/후에만 사용)
                    related_line_choice = None
                    
                    # 7줄 이후의 추가 내용이 있으면 모두 입력
                    if len(content_lines) > 6:
                        self._update_status(f"✍️ 추가 내용 작성 중... ({len(content_lines) - 6}줄 남음)")
                        for i, line in enumerate(content_lines[6:], start=7):
                            self._wait_if_paused()
                            if self.should_stop:
                                self._update_status("⏹️ 사용자가 포스팅을 중지했습니다.")
                                return False
                            
                            if line.strip():
                                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                                self._sleep_with_checks(0.1)
                                self._write_body_with_linebreaks(line)
                                self._sleep_with_checks(0.1)
                                
                                # 진행 상황 표시 (매 5줄마다)
                                if i % 5 == 0:
                                    self._update_status(f"✍️ 추가 내용 작성 중... ({i}번째 줄)")
                    
                    self._update_status("✅ 소제목/본문 작성 완료!")
                else:
                    # 6줄 미만일 때 기본 방식으로 작성
                    self._update_status(f"⚠️ 내용이 6줄 미만입니다 ({len(content_lines)}줄). 기본 방식으로 작성합니다.")
                    for line in content_lines:
                        self._wait_if_paused()
                        if self.should_stop:
                            self._update_status("⏹️ 사용자가 포스팅을 중지했습니다.")
                            return False
                        if line.strip():
                            ActionChains(self.driver).send_keys(line).perform()
                            self._sleep_with_checks(0.1)
                            ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                            self._sleep_with_checks(0.1)
                
                self._sleep_with_checks(1)
                self._update_status("✅ 본문 입력 완료!")
                
                
                
# 4. 관련 글 섹션 추가
                try:
                    related_posts = self._load_related_posts_from_file()
                    section_title = ""
                    if self.config:
                        section_title = self.config.get("related_posts_title", "").strip()
                    if not section_title:
                        mode_value = (self.config.get("related_posts_mode", "latest") if self.config else "latest")
                        mode_text = "인기 글" if mode_value == "popular" else "최신 글"
                        section_title = mode_text if mode_text else "함께 보면 좋은 글"

                    if related_posts and section_title:
                        self._update_status("관련 글 섹션 추가 중...")

                        # 구분선 스타일 결정 (관련 글 앞/뒤 동일 적용)
                        if not related_line_choice:
                            related_line_choice = random.choice(["default", "line1", "line2", "line3", "line4", "line5"])

                        # [11번 로직 선반영] 관련 글 로직 시작 전 구분선 추가
                        self._select_last_paragraph(collapse=True)
                        self._set_text_align("center")
                        self._insert_horizontal_line(related_line_choice)
                        self._sleep_with_checks(0.2)

                        # --- '관련 글' 로직 시작 (1~5번) ---

                        # 1. 중앙 정렬
                        self._select_last_paragraph(collapse=True)
                        self._set_text_align("center")
                        
                        # 2. '섹션 제목' 입력
                        if not self._insert_text_at_cursor(section_title):
                            ActionChains(self.driver).send_keys(section_title).perform()
                        self._sleep_with_checks(0.2)

                        # 3. '섹션 제목' 현재 문단 전체 선택 (Shift+Home 우선)
                        actions = ActionChains(self.driver)
                        actions.key_down(Keys.SHIFT).send_keys(Keys.HOME).key_up(Keys.SHIFT).perform()
                        self._sleep_with_checks(0.1)
                        
                        # 4. 볼드체(Ctrl+B) 및 소제목 적용
                        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('b').key_up(Keys.CONTROL).perform()
                        self._sleep_with_checks(0.1)
                        self._apply_section_title_format() # 소제목 적용 함수 호출
                        self._sleep_with_checks(0.2)

                        # 5. 선택 해제(오른쪽 방향키) 후 Enter 2번
                        ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
                        self._sleep_with_checks(0.1)
                        ActionChains(self.driver).send_keys(Keys.ENTER).send_keys(Keys.ENTER).perform()
                        self._sleep_with_checks(0.2)

                        # --- 글 제목 루프 시작 (6~10번) ---
                        
                        # 최대 3개까지만 처리
                        for post in related_posts[:3]:
                            self._wait_if_paused()
                            if self.should_stop:
                                self._update_status("사용자가 포스팅을 중지했습니다.")
                                return False

                            title = post.get("title", "").strip()
                            url = post.get("url", "").strip()
                            if not title or not url:
                                continue

                            # 6. '글 제목' 입력
                            # (중앙 정렬 상태가 유지되므로 바로 입력)
                            if not self._insert_text_at_cursor(title):
                                ActionChains(self.driver).send_keys(title).perform()
                            self._sleep_with_checks(0.2)

                            # 7. '글 제목' 현재 문단 전체 선택 (Shift+Home으로 선택)
                            actions = ActionChains(self.driver)
                            actions.key_down(Keys.SHIFT).send_keys(Keys.HOME).key_up(Keys.SHIFT).perform()
                            self._sleep_with_checks(0.3)
                            
                            # 8. 선택된 상태에서 바로 링크 첨부
                            try:
                                self._update_status(f"🔗 링크 첨부 시도: {title[:30]}")
                                
                                # 링크 버튼 클릭 (선택 유지됨)
                                link_btn = WebDriverWait(self.driver, 3).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-link-toolbar-button"))
                                )
                                link_btn.click()
                                self._sleep_with_checks(0.3)

                                # URL 입력창 대기 및 입력
                                link_input = WebDriverWait(self.driver, 3).until(
                                    EC.visibility_of_element_located((By.CSS_SELECTOR, "input.se-custom-layer-link-input"))
                                )
                                link_input.clear()
                                link_input.send_keys(url)
                                self._sleep_with_checks(0.2)

                                # 적용 버튼 클릭
                                apply_btn = WebDriverWait(self.driver, 3).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-custom-layer-link-apply-button"))
                                )
                                apply_btn.click()
                                self._sleep_with_checks(0.3)
                                
                                self._update_status(f"✅ 링크 첨부 완료: {title[:30]}")

                            except Exception as link_e:
                                error_msg = str(link_e) if str(link_e) else type(link_e).__name__
                                self._update_status(f"⚠️ 링크 적용 실패: {error_msg[:50]}")
                                print(f"[링크 적용 실패 상세]\n{traceback.format_exc()}")
                                # ESC로 팝업 닫기 시도
                                try:
                                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                    self._sleep_with_checks(0.2)
                                except:
                                    pass

                            # 9. 선택 해제(오른쪽 방향키) 후 Enter 2번
                            ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
                            self._sleep_with_checks(0.1)
                            ActionChains(self.driver).send_keys(Keys.ENTER).send_keys(Keys.ENTER).perform()
                            self._sleep_with_checks(0.2)
                            
                            # 10. 위 방식으로 3개 반복 (for문 종료)

                        # 11. '관련 글' 로직 시작 전과 똑같은 구분선 넣기
                        # (현재 커서는 관련 글들 입력 후 엔터 2번 친 상태)
                        self._insert_horizontal_line(related_line_choice)
                        self._sleep_with_checks(0.2)
                        
                        # 정렬 초기화 (필요 시)
                        self._set_text_align("left")

                        # 12. '동영상 업로드'
                        # (여기에 동영상 업로드 관련 함수를 호출하거나 로직을 추가하세요)
                        self._update_status("관련 글 섹션 완료, 동영상 업로드 단계로 이동")
                        # self._upload_video_process() # 예시 함수

                except Exception as e:
                    self._update_status(f"관련 글 섹션 추가 실패: {str(e)[:80]}")

                # 동영상 삽입 (본문 하단에 추가)
                if video_path:
                    self._update_status("🎬 동영상 삽입 중...")
                    try:
                        # 관련 글 뒤에서 시작
                        self._focus_editor_end()
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        self._sleep_with_checks(0.3)
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        self._sleep_with_checks(0.3)
                        
                        # 중앙 정렬 설정
                        try:
                            self._update_status("⚙️ 중앙 정렬 설정 중...")
                            if self._set_text_align("center"):
                                self._update_status("✅ 중앙 정렬 완료")
                            else:
                                self._update_status("⚠️ 중앙 정렬 실패(계속 진행)")
                        except Exception as e:
                            self._update_status(f"⚠️ 중앙 정렬 실패(계속 진행): {str(e)[:80]}")
                        
                        # 동영상 버튼 클릭
                        self._update_status("🎬 동영상 버튼 클릭 중...")
                        video_btn = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "button.se-video-toolbar-button.se-document-toolbar-basic-button"))
                        )
                        self.driver.execute_script("arguments[0].click();", video_btn)
                        self._sleep_with_checks(2)
                        
                        # "동영상 추가" 버튼 클릭
                        self._update_status("📂 동영상 추가 버튼 클릭 중...")
                        add_video_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.nvu_btn_append.nvu_local[data-logcode='lmvup.attmv']"))
                        )
                        add_video_btn.click()
                        self._sleep_with_checks(2)
                        
                        # 파일 입력 요소 찾기 (모든 input[type='file'] 중에서)
                        self._update_status("📂 파일 입력 요소 찾는 중...")
                        file_input = None
                        try:
                            WebDriverWait(self.driver, 5).until(
                                lambda d: d.find_elements(By.CSS_SELECTOR, "input[type='file']")
                            )
                            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                            video_inputs = [i for i in inputs if (i.get_attribute("accept") or "").lower().find("video") >= 0]
                            file_input = (video_inputs[-1] if video_inputs else inputs[-1]) if inputs else None
                            self._update_status(f"✅ 파일 입력 요소 발견: {len(inputs)}개 (video: {len(video_inputs)}개)")
                        except Exception as e:
                            self._update_status(f"⚠️ 파일 입력 요소 대기 실패: {str(e)[:50]}")
                        
                        if not file_input:
                            raise Exception("동영상 파일 입력 요소를 찾을 수 없습니다")
                        
                        # 절대 경로로 동영상 파일 전송
                        abs_path = os.path.abspath(video_path)
                        self._update_status(f"⏳ 동영상 업로드 중: {os.path.basename(abs_path)}")
                        file_input.send_keys(abs_path)
                        
                        # 동영상 업로드 대기 (동영상은 더 오래 걸릴 수 있음)
                        self._sleep_with_checks(10)
                        self._update_status("✅ 동영상 업로드 명령 전달 완료")
                        
                        # Windows 탐색기 창 닫기 (pyautogui 사용 - OS 레벨 키보드 입력)
                        self._update_status("🔘 Windows 탐색기 창 닫는 중...")
                        try:
                            # ESC 키로 Windows 탐색기 창 닫기
                            self._update_status("⌨️ ESC 키로 탐색기 창 닫기 (pyautogui)")
                            pyautogui.press('esc')
                            self._sleep_with_checks(1)
                            self._update_status("✅ 탐색기 창 닫기 성공")
                        except Exception as e:
                            self._update_status(f"⚠️ ESC 실패, Alt+F4 시도: {str(e)[:30]}")
                            try:
                                # Alt+F4로 시도
                                pyautogui.hotkey('alt', 'f4')
                                self._sleep_with_checks(1)
                                self._update_status("✅ Alt+F4로 탐색기 창 닫기 성공")
                            except Exception as e2:
                                self._update_status(f"⚠️ 탐색기 창 닫기 실패: {str(e2)[:30]}")
                        
                        # 제목 입력란에 키워드 입력
                        self._update_status("✍️ 동영상 제목 입력 중...")
                        try:
                            title_input = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "input#nvu_inp_box_title.nvu_inp[data-logcode='lmvup.subject']"))
                            )
                            title_input.clear()
                            title_input.send_keys(self.current_keyword if self.current_keyword else "동영상")
                            self._sleep_with_checks(0.5)
                            self._update_status(f"✅ 동영상 제목 입력 완료: {self.current_keyword if self.current_keyword else '동영상'}")
                        except Exception as e:
                            self._update_status(f"⚠️ 제목 입력 실패: {str(e)[:50]}")
                        
                        # 완료 버튼 클릭
                        self._update_status("✅ 완료 버튼 클릭 중...")
                        try:
                            complete_btn = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.nvu_btn_submit.nvu_btn_type2"))
                            )
                            complete_btn.click()
                            self._sleep_with_checks(2)
                            self._update_status("✅ 동영상 완료 버튼 클릭 완료")
                        except Exception as e:
                            self._update_status(f"⚠️ 완료 버튼 클릭 실패: {str(e)[:50]}")
                        
                        # Win32 API로 동영상 업로드 대화상자 강제 닫기
                        self._update_status("🔘 동영상 대화상자 닫는 중...")
                        try:
                            import win32gui
                            import win32con
                            
                            def close_dialog_windows():
                                """동영상 업로드 관련 창 모두 닫기"""
                                def enum_callback(hwnd, results):
                                    window_text = win32gui.GetWindowText(hwnd)
                                    class_name = win32gui.GetClassName(hwnd)
                                    
                                    # 네이버 동영상 업로드 관련 창 찾기
                                    if any(keyword in window_text.lower() for keyword in ['동영상', 'video', '업로드', 'upload']) or \
                                       any(keyword in class_name.lower() for keyword in ['dialog', 'popup', '#32770']):
                                        try:
                                            # WM_CLOSE 메시지 전송
                                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                                            results.append(window_text or class_name)
                                        except:
                                            pass
                                
                                closed_windows = []
                                win32gui.EnumWindows(enum_callback, closed_windows)
                                return closed_windows
                            
                            # 대화상자 닫기 시도 (3번)
                            for attempt in range(3):
                                closed = close_dialog_windows()
                                if closed:
                                    self._update_status(f"✅ Win32 API로 창 닫기 성공 ({len(closed)}개)")
                                    self._sleep_with_checks(0.5)
                                    break
                                self._sleep_with_checks(0.3)
                            
                            # 추가로 ESC 키도 전송
                            pyautogui.press('esc')
                            self._sleep_with_checks(0.5)
                            
                        except ImportError:
                            self._update_status("⚠️ pywin32 없음, ESC로 시도")
                            pyautogui.press('esc')
                            self._sleep_with_checks(0.5)
                        except Exception as e:
                            self._update_status(f"⚠️ 대화상자 닫기 실패: {str(e)[:50]}")
                        
                        self._update_status("✅ 동영상 삽입 완료")
                            
                    except Exception as e:
                        self._update_status(f"⚠️ 동영상 삽입 실패(진행 계속): {str(e)[:100]}")
                
            except Exception as e:
                self._update_status(f"❌ 본문 입력 실패: {str(e)}")
                return False
            
            # 발행 간격만큼 대기
            interval = self.config.get("interval", 0)
            if interval > 0:
                total_seconds = interval * 60
                self._update_status(f"⏰ 발행 전 대기 중... {interval:02d}:00")
                
                for remaining in range(total_seconds, 0, -1):
                    if self.should_stop:
                        self._update_status("⏹️ 대기 중 중지되었습니다")
                        return False
                
                    minutes = remaining // 60
                    seconds = remaining % 60
                    self._update_status(f"⏰ 남은 시간: {minutes:02d}:{seconds:02d}")
                    self._sleep_with_checks(1)
                
                self._update_status("✅ 발행 간격 대기 완료!")
            # 발행 처리
            self._update_status("🚀 발행 처리 중...")
            success = self.publish_post()
            
            if success:
                self._update_status("🎉 포스팅 발행 완료!")
                return True
            else:
                self._update_status("⚠️ 발행 실패 - 수동으로 발행해주세요")
                return False
            
        except StopRequested:
            return False
        except Exception as e:
            self._update_status(f"❌ 포스팅 오류: {str(e)}")
            return False
    
    
    def publish_post(self):
        """발행 설정 및 발행"""
        try:
            time.sleep(2)
            
            # 발행 버튼 찾기
            publish_selectors = [
                "button.publish_btn__m9KHH",
                "button[data-click-area='tpb.publish']",
                "button.publish_btn",
                "[class*='publish_btn']"
            ]
            
            publish_btn = None
            for selector in publish_selectors:
                try:
                    publish_btn = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if publish_btn:
                        break
                except:
                    continue
            
            if not publish_btn:
                return False
            
            # 발행 버튼 클릭
            self.driver.execute_script("arguments[0].scrollIntoView(true);", publish_btn)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", publish_btn)
            time.sleep(3)
            
            # 태그 입력
            try:
                tag_input = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".tag_input__rvUB5"))
                )
                
                if self.current_keyword:
                    main_tag = self.current_keyword.replace(" ", "")
                    tag_input.send_keys(main_tag)
                    time.sleep(0.2)
                    tag_input.send_keys(Keys.ENTER)
                    time.sleep(0.5)
                    self._update_status(f"✅ 태그: #{main_tag}")
            except:
                pass
            
            # 발행 시간 설정
            time.sleep(1)
            if self.publish_time == "pre":
                # 예약 발행
                try:
                    schedule_radio = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#radio_time2"))
                    )
                    self.driver.execute_script("arguments[0].click();", schedule_radio)
                    time.sleep(1)
                    
                    # 시간 설정
                    hour_select = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".hour_option__J_heO"))
                    )
                    hour_select.click()
                    time.sleep(0.3)
                    hour_option = self.driver.find_element(By.XPATH, f"//option[@value='{self.scheduled_hour}']")
                    hour_option.click()
                    time.sleep(0.3)
                    
                    # 분 설정
                    minute_select = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".minute_option__Vb3xB"))
                    )
                    minute_select.click()
                    time.sleep(0.3)
                    minute_option = self.driver.find_element(By.XPATH, f"//option[@value='{self.scheduled_minute}']")
                    minute_option.click()
                    
                    self._update_status(f"✅ 예약: {self.scheduled_hour}:{self.scheduled_minute}")
                except:
                    pass
            
            # 최종 발행
            time.sleep(2)
            final_publish_selectors = [
                "button[data-testid='seOnePublishBtn']",
                "button.confirm_btn__WEaBq",
                "//button[contains(., '발행')]"
            ]
            
            for selector in final_publish_selectors:
                try:
                    if selector.startswith("//"):
                        final_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        final_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    
                    self.driver.execute_script("arguments[0].click();", final_btn)
                    time.sleep(3)
                    
                    # 발행 완료 후 다음 글쓰기 준비
                    try:
                        # 프레임에서 빠져나오기
                        self.driver.switch_to.default_content()
                        time.sleep(2)
                        
                        # 현재 URL 확인
                        current_url = self.driver.current_url
                        self._update_status(f"📍 현재 URL: {current_url[:50]}...")
                        
                        # 현재 창 닫기 (새 탭에서 글쓰기 했던 경우)
                        if len(self.driver.window_handles) > 1:
                            self._update_status("🪟 발행 완료 - 글쓰기 창 닫는 중...")
                            self.driver.close()
                            self.driver.switch_to.window(self.driver.window_handles[0])
                            time.sleep(1)
                            self._update_status(f"🪟 메인 창으로 전환 완료")
                        
                        self._update_status("✅ 발행 완료")
                    except Exception as e:
                        self._update_status(f"⚠️ 창 정리 중 오류 (계속 진행): {str(e)[:50]}")
                    
                    return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            self._update_status(f"❌ 발행 오류: {str(e)}")
            return False
    
    def setup_driver(self):
        """크롬 드라이버 설정"""
        try:
            if self.driver:
                try:
                    _ = self.driver.current_url
                    return True
                except Exception:
                    self.driver = None

            self._update_status("🌐 브라우저 실행 준비 중...")
            
            options = webdriver.ChromeOptions()
            
            self._update_status("🔧 브라우저 옵션 설정 중...")
            # 봇 탐지 우회 설정
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            # 📐 창 크기 설정
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--start-maximized")
            
            # 🔕 추가 설정
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-web-security")
            options.add_argument("--disable-features=IsolateOrigins,site-per-process")

            # 🔕 알림 및 권한 비활성화
            prefs = {
                "profile.default_content_setting_values.notifications": 2,
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            }
            options.add_experimental_option("prefs", prefs)
            # 브라우저 종료 방지 (프로세스는 사용자가 직접 종료)
            options.add_experimental_option("detach", True)
            
            # 크롬 드라이버 설치 (캐시 사용하여 매번 설치 방지)
            try:
                # ChromeDriverManager는 이미 설치된 드라이버를 캐시에서 가져옴
                driver_path = ChromeDriverManager().install()
                self._update_status("✅ 크롬 드라이버 준비 완료")
                service = Service(driver_path)
            except PermissionError as pe:
                # 권한 오류 시 기존 캐시된 드라이버 사용
                self._update_status("⚠️ 드라이버 업데이트 권한 없음 - 캐시된 버전 사용")
                import os
                cache_path = os.path.expanduser("~/.wdm/drivers/chromedriver")
                if os.path.exists(cache_path):
                    # 캐시 디렉토리에서 가장 최신 버전 찾기
                    versions = [d for d in os.listdir(cache_path) if os.path.isdir(os.path.join(cache_path, d))]
                    if versions:
                        latest_version = sorted(versions)[-1]
                        cached_driver = os.path.join(cache_path, latest_version, "chromedriver.exe")
                        if os.path.exists(cached_driver):
                            service = Service(cached_driver)
                            self._update_status(f"✅ 캐시된 드라이버 사용: {latest_version}")
                        else:
                            service = Service()
                    else:
                        service = Service()
                else:
                    service = Service()
            except Exception as e:
                self._update_status(f"⚠️ 드라이버 준비 중 오류: {str(e)[:80]}")
                self._update_status("🔄 시스템 기본 드라이버 사용 시도")
                service = Service()
            
            self._update_status("🚀 브라우저 시작 중...")
            try:
                self.driver = webdriver.Chrome(service=service, options=options)
                self.driver.maximize_window()  # Ensure window is maximized
            except Exception as e:
                self._update_status(f"❌ 브라우저 시작 오류: {str(e)}")
                raise
            
            self._update_status("🎭 봇 탐지 우회 설정 적용 중...")
            # 🎭 User-Agent 위장 (최신 Chrome)
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            })
            
            # 🔧 navigator.webdriver 및 기타 속성 숨기기
            self.driver.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US', 'en']});
                window.chrome = {runtime: {}};
            """)
            
            self._update_status("✅ 브라우저 실행 완료!")
            if self.gemini_mode == "web":
                self._ensure_gemini_tab()
            return True
            
        except Exception as e:
            self._update_status(f"❌ 브라우저 실행 실패: {str(e)}")
            return False
    
    def login(self):
        """네이버 로그인"""
        try:
            self._update_status("🔐 네이버 로그인 페이지 접속 중...")
            
            # 직접 로그인 페이지로 이동
            if not self._ensure_blog_tab("https://nid.naver.com/nidlogin.login"):
                return False
            time.sleep(3)
            
            self._update_status("📝 아이디 입력 중...")
            
            # 아이디 입력
            id_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#id"))
            )
            
            self.driver.execute_script("""
                var input = arguments[0];
                var value = arguments[1];
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                nativeInputValueSetter.call(input, value);
                var event = new Event('input', { bubbles: true});
                input.dispatchEvent(event);
            """, id_input, self.naver_id)
            
            time.sleep(1)
            
            self._update_status("🔑 비밀번호 입력 중...")
            # 비밀번호 입력
            pw_input = self.driver.find_element(By.CSS_SELECTOR, "#pw")
            self.driver.execute_script("""
                var input = arguments[0];
                var value = arguments[1];
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                nativeInputValueSetter.call(input, value);
                var event = new Event('input', { bubbles: true});
                input.dispatchEvent(event);
            """, pw_input, self.naver_pw)
            
            time.sleep(1)
            
            self._update_status("👆 로그인 버튼 클릭 중...")
            
            # 로그인 버튼 클릭
            login_button = self.driver.find_element(By.ID, "log.login")
            login_button.click()
            
            total_seconds = 120
            self._update_status("⏳ 로그인 처리 중... (02:00 대기)")
            for remaining in range(total_seconds, 0, -1):
                if "nidlogin" not in self.driver.current_url:
                    self._update_status("✅ 로그인 성공!")
                    return True
                minutes = remaining // 60
                seconds = remaining % 60
                self._update_status(f"⏳ 로그인 처리 중... {minutes:02d}:{seconds:02d}")
                time.sleep(1)
            
            # 로그인 성공 확인
            current_url = self.driver.current_url
            
            if "nidlogin" not in current_url:
                self._update_status("✅ 로그인 성공!")
                return True
            else:
                # 2단계 인증 또는 오류 체크
                page_source = self.driver.page_source
                
                if "인증" in page_source or "확인" in page_source:
                    try:
                        interval_minutes = int(self.config.get("interval", 2))
                    except Exception:
                        interval_minutes = 2
                    if interval_minutes < 1:
                        interval_minutes = 1
                    total_seconds = interval_minutes * 60
                    self._update_status(
                        f"⚠️ 2단계 인증 필요 - 수동으로 인증을 완료해주세요 ({interval_minutes:02d}:00 대기)"
                    )
                    for remaining in range(total_seconds, 0, -1):
                        if "nidlogin" not in self.driver.current_url:
                            self._update_status("✅ 로그인 성공!")
                            return True
                        minutes = remaining // 60
                        seconds = remaining % 60
                        self._update_status(f"⚠️ 2단계 인증 대기: {minutes:02d}:{seconds:02d} 남음")
                        time.sleep(1)
                    if "nidlogin" not in self.driver.current_url:
                        self._update_status("✅ 로그인 성공!")
                        return True
                self._update_status("❌ 로그인 실패: 아이디/비밀번호를 확인하거나 2단계 인증을 완료해주세요")
                return False
                
        except Exception as e:
            self._update_status(f"❌ 로그인 오류: {str(e)}")
            return False
    
    # 소제목 서식 적용 로직 제거됨
    
    # 블로그 글 작성 로직 제거됨
    
    def run(self, is_first_run=True):
        """전체 프로세스 실행"""
        try:
            self._update_status("🚀 자동 포스팅 프로세스 시작!")
            
            if self.should_stop:
                self._update_status("⏹️ 프로세스가 정지되었습니다.")
                return False

            self._wait_if_paused()

            # 1단계: AI 글 생성
            self._update_status("📝 [1/5] AI 글 생성 단계")
            title, content = self.generate_content_with_ai()
            if not title or not content:
                self._update_status("❌ AI 글 생성 실패로 프로세스 중단")
                return False
            
            if self.should_stop:
                self._update_status("⏹️ 프로세스가 정지되었습니다.")
                return False

            self._wait_if_paused()

            # 2단계: 썸네일 확인
            self._update_status("🎨 [2/5] 썸네일 확인 단계")
            thumbnail_path = self.create_thumbnail(title)
            if thumbnail_path:
                self._update_status(f"✅ 썸네일 확인 완료")
            else:
                self._update_status("⚠️ 썸네일 파일 없음 - 계속 진행")
            
            # 2-1단계: 동영상 생성 (use_video가 ON이고 썸네일이 있을 경우)
            video_path = None
            if self.config.get("use_video", True) and thumbnail_path:
                try:
                    self._update_status("🎬 [2-1/5] 동영상 생성 단계")
                    video_path = self.create_video_from_thumbnail(thumbnail_path)
                    self._update_status(f"✅ 동영상 생성 완료: {os.path.basename(video_path)}")
                except Exception as e:
                    # 동영상 생성 실패 시 명확한 에러 표시 후 중단
                    self._update_status(f"❌ 동영상 생성 실패: {str(e)}")
                    return False
            elif not self.config.get("use_video", True):
                self._update_status("⚪ 동영상 기능 OFF - 동영상 생성 스킵")
            
            if self.should_stop:
                self._update_status("⏹️ 프로세스가 정지되었습니다.")
                return False
            
            # 3단계: 브라우저 실행 (첫 실행시에만)
            if is_first_run:
                self._update_status("🌐 [3/5] 브라우저 실행 단계")
                if not self.setup_driver():
                    self._update_status("❌ 브라우저 실행 실패로 프로세스 중단")
                    return False
                
                if self.should_stop:
                    self._update_status("⏹️ 프로세스가 정지되었습니다.")
                    self.close()
                    return False
                
                # 4단계: 네이버 로그인 (첫 실행시에만)
                self._update_status("🔐 [4/5] 네이버 로그인 단계")
                if not self.login():
                    self._update_status("❌ 로그인 실패 - 브라우저는 열린 상태로 유지됩니다")
                    return False
                
                if self.should_stop:
                    self._update_status("⏹️ 프로세스가 정지되었습니다.")
                    return False
            else:
                # 후속 포스팅: 기존 브라우저 재사용
                self._update_status("🔄 [3/5] 기존 브라우저 세션 재사용")
                self._update_status("🔄 [4/5] 로그인 세션 유지 중")
                
                if self.should_stop:
                    self._update_status("⏹️ 프로세스가 정지되었습니다.")
                    return False
            
            # 5단계: 블로그 포스팅
            self._update_status("✍️ [5/5] 블로그 포스팅 단계")
            self._wait_if_paused()
            if not self.write_post(title, content, thumbnail_path, video_path, is_first_post=is_first_run):
                self._update_status("⚠️ 포스팅 실패 - 브라우저는 열린 상태로 유지됩니다")
                return False
            
            # 포스팅 성공 시 키워드 이동
            if self.current_keyword:
                self.move_keyword_to_used(self.current_keyword)
            
            # 남은 키워드 수 확인
            keywords_file = os.path.join(self.data_dir, "setting", "keywords.txt")
            try:
                with open(keywords_file, 'r', encoding='utf-8') as f:
                    remaining_keywords = [line.strip() for line in f if line.strip()]
                    keyword_count = len(remaining_keywords)
                    
                    self._update_status(f"📊 남은 키워드: {keyword_count}개")
                    
                    # 30개 미만일 때 경고 (콜백으로 GUI에 전달)
                    if keyword_count < 30 and keyword_count > 0:
                        if self.callback:
                            self.callback(f"⚠️ 경고: 키워드가 {keyword_count}개 남았습니다!")
                    
                    # 키워드가 없으면 종료 신호
                    if keyword_count == 0:
                        self._update_status("✅ 모든 키워드 포스팅 완료!")
                        return True
            except Exception as e:
                self._update_status(f"⚠️ 키워드 파일 확인 실패: {str(e)[:50]}")
            
            self._update_status("🎊 전체 프로세스 완료! 포스팅 성공!")
            self._update_status("✅ 브라우저는 열린 상태로 유지됩니다")
            time.sleep(2)
            return True
            
        except StopRequested:
            return False
        except Exception as e:
            self._update_status(f"❌ 실행 오류: {str(e)}")
            return False
    
    def _find_chatgpt_editor(self, timeout=12):
        selectors = [
            "div#prompt-textarea[contenteditable='true']",
            "div.ProseMirror#prompt-textarea",
            "div#prompt-textarea",
        ]
        end_time = time.time() + timeout
        while time.time() < end_time:
            for selector in selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if elem and elem.is_displayed():
                        self._update_status(f"✅ ChatGPT 입력창 발견: {selector}")
                        return elem
                except Exception:
                    continue
            time.sleep(0.3)
        return None

    def _submit_chatgpt_prompt(self, prompt):
        try:
            editor = self._find_chatgpt_editor(timeout=12)
            if not editor:
                self._update_status("❌ ChatGPT 입력창을 찾을 수 없습니다")
                return False
            
            # JavaScript로 직접 입력 (contenteditable div 방식)
            self.driver.execute_script("""
                const editor = arguments[0];
                const text = arguments[1];
                
                // 포커스
                editor.focus();
                
                // 기존 내용 삭제
                editor.innerHTML = '';
                
                // 텍스트 입력
                const p = document.createElement('p');
                p.textContent = text;
                editor.appendChild(p);
                
                // placeholder 클래스 제거
                const placeholder = editor.querySelector('.placeholder');
                if (placeholder) placeholder.remove();
                
                // 입력 이벤트 트리거
                editor.dispatchEvent(new Event('input', { bubbles: true }));
            """, editor, prompt)
            
            time.sleep(0.5)
            
            # Enter로 전송
            editor.send_keys(Keys.ENTER)
            self._update_status("✅ ChatGPT 프롬프트 전송 성공")
            return True
        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            self._update_status(f"❌ ChatGPT 프롬프트 전송 실패: {error_msg[:50]}")
            print(f"[ChatGPT 프롬프트 전송 실패]\n{traceback.format_exc()}")
            return False

    def _count_chatgpt_copy_buttons(self):
        try:
            # 다양한 복사 버튼 선택자
            selectors = [
                "button[data-testid='copy-turn-action-button']",
                "button[aria-label*='Copy']",
                "button[aria-label*='복사']",
            ]
            buttons = []
            for selector in selectors:
                try:
                    btns = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    buttons.extend(btns)
                except:
                    continue
            return len(buttons)
        except Exception:
            return 0

    def _click_chatgpt_copy_latest(self):
        try:
            # 다양한 복사 버튼 선택자
            selectors = [
                "button[data-testid='copy-turn-action-button']",
                "button[aria-label*='Copy']",
                "button[aria-label*='복사']",
            ]
            buttons = []
            for selector in selectors:
                try:
                    btns = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    buttons.extend(btns)
                except:
                    continue
            
            if not buttons:
                return False
            
            # 마지막 버튼 클릭
            self.driver.execute_script("arguments[0].click();", buttons[-1])
            return True
        except Exception:
            return False

    def _wait_for_chatgpt_copy_button(self, before_count, timeout=180):
        end_time = time.time() + timeout
        while time.time() < end_time:
            self._wait_if_paused()
            if self._count_chatgpt_copy_buttons() > before_count:
                return True
            self._sleep_with_checks(1)
        return False

    def _find_perplexity_editor(self, timeout=12):
        selectors = [
            "div#ask-input[contenteditable='true']",
            "#ask-input",
        ]
        end_time = time.time() + timeout
        while time.time() < end_time:
            for selector in selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if elem and elem.is_displayed():
                        return elem
                except Exception:
                    continue
            time.sleep(0.2)
        return None

    def _submit_perplexity_prompt(self, prompt):
        try:
            editor = self._find_perplexity_editor(timeout=12)
            if not editor:
                return False
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", editor)
            editor.click()
            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
            ActionChains(self.driver).send_keys(Keys.BACKSPACE).perform()
            pyperclip.copy(prompt)
            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            time.sleep(0.2)
            ActionChains(self.driver).send_keys(Keys.ENTER).perform()
            return True
        except Exception as e:
            self._update_status(f"?? Perplexity ???? ?? ??: {str(e)}")
            return False

    def _count_perplexity_copy_buttons(self):
        try:
            return len(self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label='??']"))
        except Exception:
            return 0

    def _click_perplexity_copy_latest(self):
        try:
            buttons = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label='??']")
            if not buttons:
                return False
            self.driver.execute_script("arguments[0].click();", buttons[-1])
            return True
        except Exception:
            return False

    def _wait_for_perplexity_copy_button(self, before_count, timeout=180):
        end_time = time.time() + timeout
        while time.time() < end_time:
            self._wait_if_paused()
            if self._count_perplexity_copy_buttons() > before_count:
                return True
            self._sleep_with_checks(1)
        return False

    def close(self):
        """브라우저 종료 (프로그램 종료 시에도 브라우저 유지)"""
        if self.driver:
            self._update_status("✅ 프로그램 종료 (브라우저는 계속 실행됩니다)")
            # self.driver.quit()  # 브라우저는 종료하지 않음


def start_automation(naver_id, naver_pw, api_key, ai_model="gemini", posting_method="search", theme="",
                     open_type="전체공개", external_link="", external_link_text="",
                     publish_time="now", scheduled_hour="09", scheduled_minute="00",
                     callback=None):
    """자동화 시작 함수"""
    automation = NaverBlogAutomation(
        naver_id, naver_pw, api_key, ai_model, posting_method,
        theme, open_type, external_link, external_link_text,
        publish_time, scheduled_hour, scheduled_minute, callback
    )
    # 자동화 실행
    automation.run()
    return automation


# ===========================
# GUI 부분
# ===========================

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QGridLayout, QPushButton, QLabel, 
                              QLineEdit, QTextEdit, QRadioButton, QCheckBox,
                              QComboBox, QGroupBox, QTabWidget, QMessageBox,
                              QListView, QButtonGroup,
                               QFrame, QScrollArea, QStackedWidget,
                              QSizePolicy, QSplashScreen)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QPixmap, QPainter

# 네이버 컬러 팔레트
NAVER_GREEN = "#03C75A"
NAVER_GREEN_HOVER = "#02B350"
NAVER_GREEN_LIGHT = "#E8F8EF"
NAVER_BG = "#F5F7FA"
NAVER_CARD_BG = "#FFFFFF"
NAVER_TEXT = "#000000"  # 검정색으로 통일
NAVER_TEXT_SUB = "#000000"  # 검정색으로 통일
NAVER_RED = "#E84F33"
NAVER_ORANGE = "#FF9500"
NAVER_BLUE = "#007AFF"
NAVER_TEAL = "#00CEC9"  # 청록색
NAVER_BORDER = "#E5E8EB"


class PremiumCard(QFrame):
    """프리미엄 카드 위젯"""
    def __init__(self, title, icon, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {NAVER_CARD_BG};
                border: 2px solid {NAVER_BORDER};
                border-radius: 12px;
                padding: 5px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 헤더
        self.header = QFrame()
        self.header.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border: none;
                border-bottom: 1px solid {NAVER_BORDER};
                padding: 6px 12px;
            }}
        """)
        self.header.setFixedHeight(54)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(10)
        
        # 카드 제목 통일 설정
        title_label = QLabel(f"{icon} {title}")
        title_label.setFont(QFont("맑은 고딕", 15, QFont.Weight.Bold))
        title_label.setStyleSheet(f"""
            color: #000000; 
            background-color: {NAVER_GREEN_LIGHT};
            border: 2px solid {NAVER_GREEN};
            border-radius: 8px;
            padding: 6px 14px;
        """)
        title_label.setFixedHeight(36)
        self.header_layout.addWidget(title_label)
        self.header_layout.addStretch()
        
        layout.addWidget(self.header)
        
        # 콘텐츠 영역
        self.content = QWidget()
        self.content.setStyleSheet("QWidget { background-color: transparent; border: none; }")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 10, 12, 12)
        self.content_layout.setSpacing(10)
        
        layout.addWidget(self.content)
    
    @staticmethod
    def create_section_label(text, font_family="맑은 고딕"):
        """카드 내부의 섹션 라벨 생성"""
        label = QLabel(text)
        label.setFont(QFont(font_family, 15, QFont.Weight.Bold))
        label.setStyleSheet(f"""
            color: {NAVER_TEXT}; 
            background-color: transparent;
            padding: 4px 0px;
        """)
        return label


class NaverBlogGUI(QMainWindow):
    """네이버 블로그 자동 포스팅 GUI 메인 클래스"""
    
    # 시그널 정의 (스레드에서 메인 스레드로 신호 전달)
    countdown_signal = pyqtSignal(int)
    progress_signal = pyqtSignal(str)  # 진행 상황 업데이트용
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NAVER 블로그 AI 자동 포스팅")
        
        # 베이스 디렉토리 설정 (가장 먼저)
        if getattr(sys, 'frozen', False):
            # PyInstaller로 빌드된 경우
            self.base_dir = sys._MEIPASS  # 임시 폴더 (읽기 전용 리소스)
            exe_dir = os.path.dirname(sys.executable)  # exe 파일이 있는 실제 디렉토리
            
            # 쓰기 권한 테스트
            try:
                test_dir = os.path.join(exe_dir, "setting")
                os.makedirs(test_dir, exist_ok=True)
                # 테스트 파일 생성 시도
                test_file = os.path.join(test_dir, ".write_test")
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                self.data_dir = exe_dir  # 쓰기 가능
            except (PermissionError, OSError):
                # 쓰기 권한 없으면 사용자 문서 폴더 사용
                import pathlib
                self.data_dir = str(pathlib.Path.home() / "Documents" / "Auto_Naver")
                os.makedirs(os.path.join(self.data_dir, "setting"), exist_ok=True)
                print(f"⚠️ exe 위치에 쓰기 권한이 없어 설정 폴더를 사용합니다: {self.data_dir}")
        else:
            # 개발 환경
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            self.data_dir = self.base_dir
        
        # 초기 크기 및 위치 설정 (더 작고 컴팩트하게)
        self.setGeometry(100, 100, 750, 600)
        
        # 리사이즈 가능하도록 설정 (기본값이지만 명시)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # 드래그 관련 변수 초기화
        self.drag_position = None
        
        # 시그널 연결
        self.countdown_signal.connect(self.start_countdown)
        self.progress_signal.connect(self._update_progress_status_safe)
        
        # 아이콘 설정 (모든 창에 적용)
        icon_path = os.path.join(self.base_dir, "setting", "david153.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            self.setWindowIcon(icon)
            QApplication.setWindowIcon(icon)
        
        # 폰트 설정
        self.font_family = "맑은 고딕"
        QApplication.setFont(QFont(self.font_family, 13))
        
        # 설정 로드
        self.config = self.load_config()
        self.posting_method = self.config.get("posting_method", "search")

        # 상태 변수
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.automation = None
        
        # 타이머 변수 (발행 간격 카운팅)
        self.countdown_seconds = 0
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._update_countdown)
        
        # 스타일시트 적용
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {NAVER_BG};
            }}
            QPushButton {{
                border: none;
                border-radius: 10px;
                padding: 10px 20px;
                font-weight: bold;
                color: white;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:disabled {{
                background-color: #CCCCCC;
                color: #888888;
            }}
            QLineEdit, QTextEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 6px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
                selection-background-color: {NAVER_GREEN};
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {NAVER_GREEN};
                background-color: white;
            }}
            QLineEdit:disabled {{
                background-color: {NAVER_BG};
                color: {NAVER_TEXT_SUB};
            }}
            QComboBox {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 8px;
                padding: 6px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
            }}
            QComboBox::drop-down {{
                border: none;
                background-color: {NAVER_GREEN};
                width: 30px;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: 2px solid white;
                width: 8px;
                height: 8px;
                border-top: none;
                border-left: none;
            }}
            QComboBox:focus {{
                border-color: {NAVER_GREEN};
            }}
            QLabel {{
                color: {NAVER_TEXT};
                font-size: 13px;
                background-color: transparent;
            }}
            QRadioButton {{
                color: {NAVER_TEXT};
                font-size: 13px;
                font-weight: bold;
                spacing: 8px;
                background-color: transparent;
            }}
            QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid {NAVER_BORDER};
                background-color: white;
            }}
            QRadioButton::indicator:checked {{
                background-color: {NAVER_GREEN};
                border: 2px solid {NAVER_GREEN};
            }}
            QRadioButton::indicator:hover {{
                border-color: {NAVER_GREEN};
            }}
            QCheckBox {{
                color: {NAVER_TEXT};
                font-size: 13px;
                font-weight: bold;
                spacing: 8px;
                background-color: transparent;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid {NAVER_BORDER};
                background-color: white;
            }}
            QCheckBox::indicator:checked {{
                background-color: {NAVER_GREEN};
                border: 2px solid {NAVER_GREEN};
            }}
            QCheckBox::indicator:hover {{
                border-color: {NAVER_GREEN};
            }}
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {NAVER_TEXT_SUB};
                padding: 12px 30px;
                margin-right: 5px;
                border: none;
                border-radius: 10px;
                font-weight: bold;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background-color: {NAVER_GREEN};
                color: white;
            }}
            QTabBar::tab:hover {{
                background-color: {NAVER_BORDER};
            }}
        """)
        
        # GUI 구성
        self._create_gui()
        self._apply_config()
    
    def load_config(self):
        """설정 파일 로드 (UTF-8)"""
        try:
            config_path = os.path.join(self.data_dir, "setting", "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ 설정 로드 실패: {e}")
        return {}
    
    def save_config_file(self):
        """설정 파일 저장 (UTF-8)"""
        try:
            setting_dir = os.path.join(self.data_dir, "setting")
            os.makedirs(setting_dir, exist_ok=True)
            config_path = os.path.join(setting_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            self._update_settings_status("✅ 설정이 성공적으로 저장되었습니다")
        except Exception as e:
            self._update_settings_status(f"❌ 설정 저장 실패: {str(e)}")
    
    def show_message(self, title, message, msg_type="info"):
        """스타일이 적용된 메시지 박스 표시"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        
        # 메시지 타입에 따라 아이콘 설정
        if msg_type == "warning":
            msg_box.setIcon(QMessageBox.Icon.Warning)
        elif msg_type == "error":
            msg_box.setIcon(QMessageBox.Icon.Critical)
        else:
            msg_box.setIcon(QMessageBox.Icon.Information)
        
        # 스타일 적용 (흰색 배경, 검은색 텍스트)
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: white;
            }}
            QMessageBox QLabel {{
                color: {NAVER_TEXT};
                font-size: 13px;
                background-color: white;
            }}
            QMessageBox QPushButton {{
                background-color: {NAVER_GREEN};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {NAVER_GREEN_HOVER};
            }}
        """)
        
        msg_box.exec()
    
    def show_api_help(self):
        """API 발급 방법 안내"""
        help_text = """
<h3>🔑 Gemini API 키 발급 방법</h3>

<ol>
<li>Google AI Studio 접속: <a href='https://aistudio.google.com/app/apikey'>https://aistudio.google.com/app/apikey</a></li>
<li>Google 계정으로 로그인</li>
<li>"Create API Key" 버튼 클릭</li>
<li>생성된 API 키 복사</li>
<li>위의 "Gemini API" 입력란에 붙여넣기</li>
</ol>

<p><b>⚠️ 주의사항</b></p>
<ul>
<li>API 키는 절대 타인과 공유하지 마세요</li>
<li>무료 할당량 초과 시 과금될 수 있습니다</li>
</ul>
        """
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("API 발급 방법 안내")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(help_text)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    
    def keyPressEvent(self, event):
        """키보드 이벤트 처리 (F5 = 설정 저장 + 새로고침)"""
        if event.key() == Qt.Key.Key_F5:
            self.refresh_settings()
        else:
            super().keyPressEvent(event)
    
    def refresh_settings(self):
        """설정 저장 후 새로고침"""
        try:
            # 1. 현재 입력된 설정 저장
            self.config["gemini_api_key"] = self.gemini_api_entry.text()
            self.config["api_key"] = self.gemini_api_entry.text()
            self.config["ai_model"] = "gemini"
            if hasattr(self, "gemini_web_radio") and self.gemini_web_radio.isChecked():
                self.config["gemini_mode"] = "web"
            else:
                self.config["gemini_mode"] = "api"
            if hasattr(self, "web_ai_gpt_radio"):
                if self.web_ai_gpt_radio.isChecked():
                    self.config["web_ai_provider"] = "gpt"
                elif self.web_ai_perplexity_radio.isChecked():
                    self.config["web_ai_provider"] = "perplexity"
                else:
                    self.config["web_ai_provider"] = "gemini"
            self.config["naver_id"] = self.naver_id_entry.text()
            self.config["naver_pw"] = self.naver_pw_entry.text()
            self.config["interval"] = int(self.interval_entry.text()) if self.interval_entry.text() else 30
            self.config["use_external_link"] = self.use_link_checkbox.isChecked()
            self.config["external_link"] = self.link_url_entry.text()
            self.config["external_link_text"] = self.link_text_entry.text()
            if hasattr(self, "posting_home_radio") and self.posting_home_radio.isChecked():
                self.config["posting_method"] = "home"
            else:
                self.config["posting_method"] = "search"
            self.posting_method = self.config["posting_method"]

            # 2. 설정 파일로 저장
            setting_dir = os.path.join(self.base_dir, "setting")
            os.makedirs(setting_dir, exist_ok=True)
            config_path = os.path.join(setting_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            
            # 3. UI 업데이트
            self._apply_config()
            
            self._update_settings_status("✅ 설정이 저장되고 업데이트되었습니다")
        except Exception as e:
            self._update_settings_status(f"❌ 새로고침 실패: {str(e)}")
    
    def _create_gui(self):
        """GUI 생성"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 헤더
        self._create_header(main_layout)
        
        # 탭
        self._create_tabs(main_layout)
    
    def _create_header(self, parent_layout):
        """헤더 생성"""
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {NAVER_GREEN};
                border: none;
                padding: 10px 30px;
            }}
        """)
        header.setFixedHeight(70)
        
        header_layout = QGridLayout(header)
        header_layout.setContentsMargins(30, 0, 30, 0)
        header_layout.setColumnStretch(0, 1)
        header_layout.setColumnStretch(1, 0)
        header_layout.setColumnStretch(2, 1)
        
        # 왼쪽 제목
        left_label = QLabel("Auto Naver Blog Program__V 5.1")
        left_label.setFont(QFont(self.font_family, 13, QFont.Weight.Bold))
        left_label.setStyleSheet("color: white; background-color: transparent; border: none;")
        left_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(left_label, 0, 0)
        
        # 중앙 탭 버튼
        tab_buttons_container = QWidget()
        tab_buttons_container.setStyleSheet("background-color: transparent;")
        tab_buttons_layout = QHBoxLayout(tab_buttons_container)
        tab_buttons_layout.setContentsMargins(0, 0, 0, 0)
        tab_buttons_layout.setSpacing(10)
        
        self.monitoring_tab_btn = QPushButton("📊 모니터링")
        self.monitoring_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.monitoring_tab_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid white;
                border-radius: 10px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
                outline: none;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:checked {{
                background-color: white;
                color: {NAVER_GREEN};
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """)
        self.monitoring_tab_btn.setCheckable(True)
        self.monitoring_tab_btn.setChecked(True)
        self.monitoring_tab_btn.clicked.connect(lambda: self._switch_tab(0))
        tab_buttons_layout.addWidget(self.monitoring_tab_btn)
        
        self.settings_tab_btn = QPushButton("⚙️ 설정")
        self.settings_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_tab_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid white;
                border-radius: 10px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
                outline: none;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:checked {{
                background-color: white;
                color: {NAVER_GREEN};
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """)
        self.settings_tab_btn.setCheckable(True)
        self.settings_tab_btn.clicked.connect(lambda: self._switch_tab(1))
        tab_buttons_layout.addWidget(self.settings_tab_btn)
        
        # 새로고침 버튼 추가
        self.refresh_btn = QPushButton("🔄 새로고침")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid white;
                border-radius: 10px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
                outline: none;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 0.4);
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """)
        self.refresh_btn.clicked.connect(self.refresh_settings)
        tab_buttons_layout.addWidget(self.refresh_btn)
        
        header_layout.addWidget(tab_buttons_container, 0, 1, Qt.AlignmentFlag.AlignCenter)
        
        # 오른쪽 제작자 표시 (하이퍼링크)
        right_label = QLabel('<a href="https://github.com/angibeom0985-arch" style="color: white; text-decoration: none;">제작자 : 데이비</a>')
        right_label.setFont(QFont(self.font_family, 13, QFont.Weight.Bold))
        right_label.setStyleSheet("color: white; background-color: transparent; border: none;")
        right_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right_label.setOpenExternalLinks(True)  # 외부 링크 열기 활성화
        right_label.setCursor(Qt.CursorShape.PointingHandCursor)  # 마우스 커서 손가락 모양으로
        header_layout.addWidget(right_label, 0, 2)
        
        parent_layout.addWidget(header)
    
    def _switch_tab(self, index):
        """탭 전환"""
        self.tab_stack.setCurrentIndex(index)
        self.monitoring_tab_btn.setChecked(index == 0)
        self.settings_tab_btn.setChecked(index == 1)
    
    def _create_tabs(self, parent_layout):
        """탭 생성 - 스택 위젯 사용"""
        self.tab_stack = QWidget()
        stack_layout = QVBoxLayout(self.tab_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(0)
        
        from PyQt6.QtWidgets import QStackedWidget
        self.tab_stack = QStackedWidget()
        
        # 모니터링 탭
        monitoring_tab = self._create_monitoring_tab()
        self.tab_stack.addWidget(monitoring_tab)
        
        # 설정 탭
        settings_tab = self._create_settings_tab()
        self.tab_stack.addWidget(settings_tab)
        
        # Enter 키 바인딩 (설정 탭 생성 후 적용)
        self.naver_id_entry.returnPressed.connect(self.save_login_info)
        self.naver_pw_entry.returnPressed.connect(self.save_login_info)
        self.gemini_api_entry.returnPressed.connect(self.save_api_key)
        self.related_posts_title_entry.returnPressed.connect(self.save_related_posts_settings)
        self.blog_address_entry.returnPressed.connect(self.save_related_posts_settings)
        self.link_url_entry.returnPressed.connect(self.save_link_settings)
        self.link_text_entry.returnPressed.connect(self.save_link_settings)
        self.interval_entry.returnPressed.connect(self.save_time_settings)
        
        parent_layout.addWidget(self.tab_stack)
    
    def _create_monitoring_tab(self):
        """모니터링 탭 생성"""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(16)
        
        # 좌측 컨테이너
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(16)
        
        # 포스팅 제어 카드
        control_card = PremiumCard("포스팅 제어", "🎮")
        control_layout = QGridLayout()
        control_card.content_layout.addLayout(control_layout)
        
        # 버튼 생성
        self.start_btn = QPushButton("▶️ 시작")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_GREEN};
                min-height: 28px;
                font-size: 13px;
                color: white;
                border: none;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background-color: {NAVER_GREEN_HOVER};
            }}
        """)
        self.start_btn.clicked.connect(self.start_posting)
        control_layout.addWidget(self.start_btn, 0, 0)
        
        self.stop_btn = QPushButton("⏹️ 정지")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_RED};
                min-height: 28px;
                font-size: 13px;
                color: white;
                border: none;
                opacity: 0.6;
                padding: 4px 12px;
            }}
            QPushButton:disabled {{
                background-color: {NAVER_RED};
                color: white;
                border: none;
                opacity: 0.5;
            }}
            QPushButton:enabled {{
                opacity: 1.0;
            }}
            QPushButton:enabled:hover {{
                background-color: #D32F2F;
            }}
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_posting)
        control_layout.addWidget(self.stop_btn, 0, 1)
        
        self.pause_btn = QPushButton("⏸️ 일시정지")
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_ORANGE};
                min-height: 28px;
                font-size: 13px;
                color: white;
                border: none;
                opacity: 0.6;
                padding: 4px 12px;
            }}
            QPushButton:disabled {{
                background-color: {NAVER_ORANGE};
                color: white;
                border: none;
                opacity: 0.5;
            }}
            QPushButton:enabled {{
                opacity: 1.0;
            }}
            QPushButton:enabled:hover {{
                background-color: #EF8A00;
            }}
        """)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self.pause_posting)
        control_layout.addWidget(self.pause_btn, 1, 0)
        
        self.resume_btn = QPushButton("▶️ 재개")
        self.resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_BLUE};
                min-height: 28px;
                font-size: 13px;
                color: white;
                border: none;
                opacity: 0.6;
                padding: 4px 12px;
            }}
            QPushButton:disabled {{
                background-color: {NAVER_BLUE};
                color: white;
                border: none;
                opacity: 0.5;
            }}
            QPushButton:enabled {{
                opacity: 1.0;
            }}
            QPushButton:enabled:hover {{
                background-color: #0066CC;
            }}
        """)
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self.resume_posting)
        control_layout.addWidget(self.resume_btn, 1, 1)
        
        left_layout.addWidget(control_card)
        
        # 설정 상태 카드
        status_card = PremiumCard("설정 상태", "⚙️")
        
        # 로그인 정보 상태
        login_status_layout = QHBoxLayout()
        self.login_status_label = QLabel("👤 로그인 정보: 미설정")
        self.login_status_label.setFont(QFont(self.font_family, 13))
        self.login_status_label.setStyleSheet(f"color: #000000; border: none;")
        login_status_layout.addWidget(self.login_status_label)
        
        self.login_setup_btn = QPushButton("설정하기")
        self.login_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_setup_btn.setMinimumHeight(25)
        self.login_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #C0392B;
            }}
        """)
        self.login_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        login_status_layout.addStretch()
        login_status_layout.addWidget(self.login_setup_btn)
        
        status_card.content_layout.addLayout(login_status_layout)
        
        # API 키 상태
        api_status_layout = QHBoxLayout()
        self.api_status_label = QLabel("🔑 API 키: 미설정")
        self.api_status_label.setFont(QFont(self.font_family, 13))
        self.api_status_label.setStyleSheet(f"color: #000000; border: none;")
        api_status_layout.addWidget(self.api_status_label)
        
        self.api_setup_btn = QPushButton("설정하기")
        self.api_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.api_setup_btn.setMinimumHeight(25)
        self.api_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        api_status_layout.addStretch()
        api_status_layout.addWidget(self.api_setup_btn)

        status_card.content_layout.addLayout(api_status_layout)

        # 포스팅 방법 상태
        posting_status_layout = QHBoxLayout()
        self.posting_status_label = QLabel("📰 포스팅: 검색 노출")
        self.posting_status_label.setFont(QFont(self.font_family, 13))
        self.posting_status_label.setStyleSheet(f"color: #000000; border: none;")
        posting_status_layout.addWidget(self.posting_status_label)

        self.posting_setup_btn = QPushButton("변경하기")
        self.posting_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.posting_setup_btn.setMinimumHeight(25)
        self.posting_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_GREEN};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: #00C73C;
            }}
        """)
        self.posting_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        posting_status_layout.addStretch()
        posting_status_layout.addWidget(self.posting_setup_btn)

        status_card.content_layout.addLayout(posting_status_layout)
        
        # 키워드 개수 상태
        keyword_status_layout = QHBoxLayout()
        self.keyword_count_label = QLabel("📦 키워드 개수: 0개")
        self.keyword_count_label.setFont(QFont(self.font_family, 13))
        self.keyword_count_label.setStyleSheet(f"color: #000000; border: none;")
        keyword_status_layout.addWidget(self.keyword_count_label)
        
        self.keyword_setup_btn = QPushButton("설정하기")
        self.keyword_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keyword_setup_btn.setMinimumHeight(25)
        self.keyword_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        keyword_status_layout.addStretch()
        keyword_status_layout.addWidget(self.keyword_setup_btn)
        
        status_card.content_layout.addLayout(keyword_status_layout)
        
        # 발행 간격 상태
        interval_status_layout = QHBoxLayout()
        self.interval_label = QLabel("⏱️ 발행 간격: 10분")
        self.interval_label.setFont(QFont(self.font_family, 13))
        self.interval_label.setStyleSheet(f"color: #000000; border: none;")
        interval_status_layout.addWidget(self.interval_label)
        
        self.interval_setup_btn = QPushButton("변경하기")
        self.interval_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.interval_setup_btn.setMinimumHeight(25)
        self.interval_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_GREEN};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: #00C73C;
            }}
        """)
        self.interval_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        interval_status_layout.addStretch()
        interval_status_layout.addWidget(self.interval_setup_btn)
        
        status_card.content_layout.addLayout(interval_status_layout)
        

        
        # 썸네일 기능 상태
        thumbnail_status_layout = QHBoxLayout()
        self.thumbnail_status_label = QLabel("🖼️ 썸네일: ON")
        self.thumbnail_status_label.setFont(QFont(self.font_family, 13))
        self.thumbnail_status_label.setStyleSheet(f"color: #000000; border: none;")
        thumbnail_status_layout.addWidget(self.thumbnail_status_label)
        
        self.thumbnail_setup_btn = QPushButton("설정하기")
        self.thumbnail_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumbnail_status_label.setFont(QFont(self.font_family, 13))
        self.thumbnail_setup_btn.setMinimumHeight(25)
        self.thumbnail_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_GREEN};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: #00C73C;
            }}
        """)
        self.thumbnail_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        thumbnail_status_layout.addStretch()
        thumbnail_status_layout.addWidget(self.thumbnail_setup_btn)
        
        status_card.content_layout.addLayout(thumbnail_status_layout)
        
        # 외부 링크 상태
        ext_link_status_layout = QHBoxLayout()
        self.ext_link_status_label = QLabel("🔗 외부 링크: OFF")
        self.ext_link_status_label.setFont(QFont(self.font_family, 13))
        self.ext_link_status_label.setStyleSheet(f"color: #000000; border: none;")
        ext_link_status_layout.addWidget(self.ext_link_status_label)
        
        self.ext_link_setup_btn = QPushButton("설정하기")
        self.ext_link_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ext_link_setup_btn.setMinimumHeight(25)
        self.ext_link_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        ext_link_status_layout.addStretch()
        ext_link_status_layout.addWidget(self.ext_link_setup_btn)
        
        status_card.content_layout.addLayout(ext_link_status_layout)
        
        # 함께 보면 좋은 글 상태
        related_posts_status_layout = QHBoxLayout()
        self.related_posts_status_label = QLabel("📚 관련 글: 미설정")
        self.related_posts_status_label.setFont(QFont(self.font_family, 13))
        self.related_posts_status_label.setStyleSheet(f"color: #000000; border: none;")
        related_posts_status_layout.addWidget(self.related_posts_status_label)
        
        self.related_posts_setup_btn = QPushButton("설정하기")
        self.related_posts_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.related_posts_setup_btn.setMinimumHeight(25)
        self.related_posts_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        related_posts_status_layout.addStretch()
        related_posts_status_layout.addWidget(self.related_posts_setup_btn)
        
        status_card.content_layout.addLayout(related_posts_status_layout)
        
        # 사용기간 표시 (라이선스 정보)
        self.license_period_label = QLabel("📅 사용기간: 확인 중...")
        self.license_period_label.setFont(QFont(self.font_family, 13))
        self.license_period_label.setStyleSheet(f"color: #000000; border: none;")
        status_card.content_layout.addWidget(self.license_period_label)
        
        # 라이선스 정보 로드
        self._update_license_info()
        
        # 카드 크기 최소화
        status_card.setMaximumHeight(status_card.sizeHint().height())
        
        left_layout.addWidget(status_card)
        left_layout.addStretch()
        
        layout.addWidget(left_widget)
        
        # 우측: 현재 진행 현황 카드
        progress_card = PremiumCard("진행 현황", "📋")
        
        # 진행 현황 스크롤 영역 (Ctrl+휠로 크기 조절)
        class ResizableScrollArea(QScrollArea):
            def wheelEvent(self, event):
                if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                    current_height = self.height()
                    delta = event.angleDelta().y()
                    scale_factor = 1.1 if delta > 0 else 0.9
                    new_height = max(100, min(int(current_height * scale_factor), 800))
                    self.setMinimumHeight(new_height)
                    self.setMaximumHeight(new_height)
                    event.accept()
                else:
                    super().wheelEvent(event)
        
        log_scroll = ResizableScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll.setMinimumHeight(300)
        log_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 8px;
                background-color: {NAVER_BG};
            }}
            QScrollBar:vertical {{
                border: none;
                background: {NAVER_BG};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {NAVER_GREEN};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {NAVER_GREEN_HOVER};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.log_label = QLabel("⏸️ 대기 중...")
        self.log_label.setFont(QFont("Segoe UI Emoji, " + self.font_family, 13))
        self.log_label.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent; padding: 10px;")
        self.log_label.setWordWrap(True)  # 자동 줄바꿈
        self.log_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.log_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)  # 드래그/복사 가능
        self.log_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)  # 너비 확장 가능
        self.log_label.setMaximumWidth(9999)  # 최대 너비 제한 제거
        self.log_label.setScaledContents(False)  # 콘텐츠 크기 조정 비활성화
        log_layout.addWidget(self.log_label)
        log_layout.addStretch()
        
        log_scroll.setWidget(log_widget)
        self.log_scroll = log_scroll
        progress_card.content_layout.addWidget(log_scroll)
        
        # 진행 현황 카드는 확장 가능하도록 유지
        
        layout.addWidget(progress_card)
        
        return tab
    
    def _create_settings_tab(self):
        """설정 탭 생성"""
        tab = QScrollArea()
        tab.setWidgetResizable(True)
        tab.setFrameShape(QFrame.Shape.NoFrame)
        tab.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        
        content = QWidget()
        content.setStyleSheet("QWidget { background-color: transparent; }")
        layout = QGridLayout(content)
        layout.setContentsMargins(24, 18, 24, 24)
        layout.setSpacing(16)

        save_btn_style = f"""
            QPushButton {{
                background-color: {NAVER_GREEN};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #00C73C;
            }}
            QPushButton:pressed {{
                background-color: #009632;
            }}
        """
        save_btn_height = 38
        card_min_height = 240
        
        # 균등 분할
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        
        # === Row 4, Col 1: 설정 상태 ===
        settings_progress_card = PremiumCard("설정 상태", "📊")
        
        # 2단 레이아웃: 왼쪽(로그) | 오른쪽(상태)
        status_main_layout = QHBoxLayout()
        status_main_layout.setSpacing(15)
        
        # 왼쪽: 로그 메시지 (50% 너비)
        log_container = QWidget()
        log_container.setStyleSheet("QWidget { background-color: transparent; }")
        log_container_layout = QVBoxLayout(log_container)
        log_container_layout.setContentsMargins(0, 0, 0, 0)
        log_container_layout.setSpacing(5)
        
        self.settings_log_scroll = QScrollArea()
        self.settings_log_scroll.setWidgetResizable(True)
        self.settings_log_scroll.setMinimumHeight(120)
        self.settings_log_scroll.setMaximumHeight(180)
        self.settings_log_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 8px;
                background-color: white;
            }}
            QScrollBar:vertical {{
                border: none;
                background: {NAVER_BG};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {NAVER_GREEN};
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {NAVER_GREEN_HOVER};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        
        settings_log_widget = QWidget()
        settings_log_layout = QVBoxLayout(settings_log_widget)
        settings_log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        settings_log_layout.setContentsMargins(10, 10, 10, 10)
        settings_log_layout.setSpacing(3)
        
        self.settings_log_label = QLabel("⏸️ 대기 중...")
        self.settings_log_label.setFont(QFont("Segoe UI Emoji, " + self.font_family, 11))
        self.settings_log_label.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent; padding: 5px;")
        self.settings_log_label.setWordWrap(True)
        self.settings_log_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.settings_log_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.settings_log_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        settings_log_layout.addWidget(self.settings_log_label)
        
        self.settings_log_scroll.setWidget(settings_log_widget)
        log_container_layout.addWidget(self.settings_log_scroll)
        
        # 로그 섹션만 추가 (오른쪽 상태 섹션 제거)
        settings_progress_card.content_layout.addWidget(self.settings_log_scroll)
        
        # === Row 1, Col 0: 네이버 로그인 정보 ===
        login_card = PremiumCard("네이버 로그인 정보", "👤")
        
        # 경고 라벨 (볼드체 추가)
        warning_label = QLabel("⚠️ 2차 인증 해제 권장")
        warning_label.setStyleSheet(f"""
            background-color: {NAVER_ORANGE}; 
            color: white; 
            padding: 6px 14px; 
            border-radius: 8px;
            font-size: 13px;
            font-weight: bold;
            border: none;
        """)
        warning_label.setFixedHeight(36)
        login_card.header.layout().addWidget(warning_label)
        
        login_card.content_layout.addStretch()
        
        login_grid = QGridLayout()
        login_grid.setColumnStretch(0, 1)
        login_grid.setColumnStretch(1, 1)
        
        id_widget = QWidget()
        id_widget.setStyleSheet("QWidget { background-color: transparent; }")
        id_layout = QVBoxLayout(id_widget)
        id_label = PremiumCard.create_section_label("🆔 아이디", self.font_family)
        id_layout.addWidget(id_label)
        self.naver_id_entry = QLineEdit()
        self.naver_id_entry.setPlaceholderText("네이버 아이디")
        self.naver_id_entry.setCursorPosition(0)
        self.naver_id_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 6px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
                min-height: 20px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.naver_id_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        id_layout.addWidget(self.naver_id_entry)
        login_grid.addWidget(id_widget, 0, 0)
        
        pw_widget = QWidget()
        pw_widget.setStyleSheet("QWidget { background-color: transparent; }")
        pw_layout = QVBoxLayout(pw_widget)
        pw_label = PremiumCard.create_section_label("🔒 비밀번호", self.font_family)
        pw_layout.addWidget(pw_label)
        pw_container = QHBoxLayout()
        self.naver_pw_entry = QLineEdit()
        self.naver_pw_entry.setPlaceholderText("비밀번호")
        self.naver_pw_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.naver_pw_entry.setCursorPosition(0)
        self.naver_pw_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 6px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
                min-height: 20px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.naver_pw_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        pw_container.addWidget(self.naver_pw_entry)
        
        # 비밀번호 토글 버튼
        pw_toggle_container = QHBoxLayout()
        pw_toggle_container.setSpacing(5)
        
        self.pw_toggle_btn = QPushButton("비공개")
        self.pw_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pw_toggle_btn.setMinimumSize(70, 34)
        self.pw_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_TEXT_SUB};
                border: none;
                border-radius: 8px;
                color: white;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {NAVER_TEXT};
            }}
        """)
        self.pw_toggle_btn.clicked.connect(self.toggle_password)
        pw_toggle_container.addWidget(self.pw_toggle_btn)
        
        pw_container.addLayout(pw_toggle_container)
        pw_layout.addLayout(pw_container)
        login_grid.addWidget(pw_widget, 0, 1)
        
        login_card.content_layout.addLayout(login_grid)
        
        login_save_btn = QPushButton("💾 로그인 정보 저장")
        login_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_save_btn.setStyleSheet(save_btn_style)
        login_save_btn.setMinimumHeight(save_btn_height)
        login_save_btn.clicked.connect(self.save_login_info)
        login_card.content_layout.addStretch()
        login_card.content_layout.addWidget(login_save_btn)
        
        login_card.setMinimumHeight(card_min_height)
        
        layout.addWidget(login_card, 1, 0)
        
        # === Row 1, Col 1: 발행 간격 설정 ===
        time_card = PremiumCard("발행 간격 설정", "⏱️")
        
        time_card.content_layout.addStretch()
        
        # 발행 간격 입력 레이아웃
        time_input_layout = QVBoxLayout()
        time_input_layout.setSpacing(10)
        
        # 발행 간격 라벨
        time_main_label = PremiumCard.create_section_label("⏱️ 발행 간격", self.font_family)
        time_input_layout.addWidget(time_main_label)
        
        # 입력 필드 레이아웃
        interval_input_layout = QHBoxLayout()
        interval_input_layout.setSpacing(10)
        
        self.interval_entry = QLineEdit()
        self.interval_entry.setPlaceholderText("10")
        self.interval_entry.setText("10")
        self.interval_entry.setFixedWidth(80)
        self.interval_entry.setCursorPosition(0)
        self.interval_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 6px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.interval_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        interval_input_layout.addWidget(self.interval_entry)
        
        interval_text_label = PremiumCard.create_section_label("분 간격", self.font_family)
        interval_input_layout.addWidget(interval_text_label)
        interval_input_layout.addStretch()
        
        time_input_layout.addLayout(interval_input_layout)
        time_card.content_layout.addLayout(time_input_layout)
        
        time_save_btn = QPushButton("💾 발행 간격 저장")
        time_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        time_save_btn.setStyleSheet(save_btn_style)
        time_save_btn.setMinimumHeight(save_btn_height)
        time_save_btn.clicked.connect(self.save_time_settings)
        time_card.content_layout.addStretch()
        time_card.content_layout.addWidget(time_save_btn)
        
        time_card.setMinimumHeight(card_min_height)
        
        layout.addWidget(time_card, 1, 1)
        
        # === Row 3, Col 0: 외부 링크 설정 ===
        link_card = PremiumCard("외부 링크 설정", "🔗")
        
        # 헤더에 체크박스와 ON/OFF 상태 표시 추가
        checkbox_container = QWidget()
        checkbox_container.setStyleSheet("QWidget { background-color: transparent; border: none; }")
        checkbox_layout = QHBoxLayout(checkbox_container)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setSpacing(10)
        
        self.use_link_checkbox = QCheckBox("사용")
        self.use_link_checkbox.setChecked(False)
        self.use_link_checkbox.setFont(QFont(self.font_family, 13, QFont.Weight.Bold))
        self.use_link_checkbox.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent; border: none;")
        self.use_link_checkbox.stateChanged.connect(self.toggle_external_link)
        checkbox_layout.addWidget(self.use_link_checkbox)
        
        self.link_status_label = QLabel("OFF")
        self.link_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.link_status_label.setMinimumWidth(40)
        self.link_status_label.setMaximumHeight(22)
        self.link_status_label.setStyleSheet(f"""
            QLabel {{
                background-color: {NAVER_RED};
                color: white;
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 13px;
                font-weight: bold;
            }}
        """)
        checkbox_layout.addWidget(self.link_status_label)
        
        link_card.header.layout().insertWidget(1, checkbox_container)
        
        # 공백 유지를 위한 더미 위젯 (항상 표시)
        link_card.header.layout().addStretch()
        
        link_grid = QGridLayout()
        link_grid.setColumnStretch(0, 1)
        link_grid.setColumnStretch(1, 1)
        link_grid.setHorizontalSpacing(12)
        link_grid.setVerticalSpacing(8)
        link_grid.setContentsMargins(0, 6, 0, 0)
        
        url_widget = QWidget()
        url_widget.setStyleSheet("QWidget { background-color: transparent; }")
        url_layout = QVBoxLayout(url_widget)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)
        self.url_label = PremiumCard.create_section_label("🌐 링크 URL", self.font_family)
        url_layout.addWidget(self.url_label)
        self.link_url_entry = QLineEdit()
        self.link_url_entry.setPlaceholderText("https://example.com")
        self.link_url_entry.setText("https://example.com")
        self.link_url_entry.setEnabled(False)
        self.link_url_entry.setCursorPosition(0)
        self.link_url_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 6px 10px;
                background-color: {NAVER_BG};
                color: {NAVER_TEXT_SUB};
                font-size: 13px;
                min-height: 32px;
            }}
            QLineEdit:enabled {{
                background-color: white;
                color: {NAVER_TEXT};
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.link_url_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.link_url_entry.focusInEvent = lambda e: self._clear_example_text(self.link_url_entry, "https://example.com") if self.link_url_entry.isEnabled() else None
        url_layout.addWidget(self.link_url_entry)
        link_grid.addWidget(url_widget, 0, 0)
        
        text_widget = QWidget()
        text_widget.setStyleSheet("QWidget { background-color: transparent; }")
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)
        self.text_label = PremiumCard.create_section_label("✏️ 앵커 텍스트", self.font_family)
        text_layout.addWidget(self.text_label)
        self.link_text_entry = QLineEdit()
        self.link_text_entry.setPlaceholderText("더 알아보기 ✨")
        self.link_text_entry.setText("더 알아보기")
        self.link_text_entry.setEnabled(False)
        
        # 이모지 지원을 위한 폰트 설정
        emoji_font = QFont("Segoe UI Emoji, " + self.font_family, 13)
        self.link_text_entry.setFont(emoji_font)
        
        self.link_text_entry.setCursorPosition(0)
        self.link_text_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 6px 10px;
                background-color: {NAVER_BG};
                color: {NAVER_TEXT_SUB};
                font-size: 13px;
                min-height: 32px;
            }}
            QLineEdit:enabled {{
                background-color: white;
                color: {NAVER_TEXT};
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.link_text_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.link_text_entry.focusInEvent = lambda e: self._clear_example_text(self.link_text_entry, "더 알아보기") if self.link_text_entry.isEnabled() else None
        text_layout.addWidget(self.link_text_entry)
        link_grid.addWidget(text_widget, 0, 1)
        
        link_card.content_layout.addLayout(link_grid)
        
        link_save_btn = QPushButton("💾 링크 설정 저장")
        link_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        link_save_btn.setStyleSheet(save_btn_style)
        link_save_btn.setMinimumHeight(save_btn_height)
        link_save_btn.clicked.connect(self.save_link_settings)
        link_card.content_layout.addStretch()
        link_card.content_layout.addWidget(link_save_btn)
        
        link_card.setMinimumHeight(card_min_height)
        
        layout.addWidget(link_card, 3, 0)
        
        # 초기 취소선 적용 (체크 해제 상태이므로)
        self.toggle_external_link()
        
        # === Row 4, Col 0: AI 설정 (Gemini 전용) ===
        api_card = PremiumCard("🤖 AI 설정", "")
        
        # 카드 헤더에 API 발급 방법 버튼 추가
        api_help_btn_header = QPushButton("❓ API 발급 방법")
        api_help_btn_header.setCursor(Qt.CursorShape.PointingHandCursor)
        api_help_btn_header.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_BLUE};
                border: none;
                border-radius: 8px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: #0066E6;
            }}
        """)
        api_help_btn_header.clicked.connect(self.show_api_help)

        gemini_mode_header_container = QWidget()
        gemini_mode_header_container.setStyleSheet("QWidget { background-color: transparent; }")
        gemini_mode_header_layout = QHBoxLayout(gemini_mode_header_container)
        gemini_mode_header_layout.setContentsMargins(0, 0, 0, 0)
        gemini_mode_header_layout.setSpacing(12)

        self.gemini_web_radio = QRadioButton("웹사이트")
        self.gemini_api_radio = QRadioButton("Gemini API")
        for radio in (self.gemini_web_radio, self.gemini_api_radio):
            radio.setFont(QFont(self.font_family, 12))
            radio.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent;")
            gemini_mode_header_layout.addWidget(radio)

        api_card.header_layout.insertWidget(1, gemini_mode_header_container)
        api_card.header_layout.addStretch()
        api_card.header_layout.addWidget(api_help_btn_header)
        
        api_card.content_layout.setSpacing(12)

        api_grid = QGridLayout()
        api_grid.setColumnStretch(0, 1)
        api_grid.setHorizontalSpacing(12)
        api_grid.setVerticalSpacing(4)  # 웹사이트와 Gemini API 사이 간격 축소

        gemini_web_widget = QWidget()
        gemini_web_widget.setStyleSheet("QWidget { background-color: transparent; }")
        gemini_web_layout = QVBoxLayout(gemini_web_widget)
        gemini_web_layout.setSpacing(4)
        gemini_web_layout.setContentsMargins(0, 0, 0, 0)
        gemini_web_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        web_provider_label = PremiumCard.create_section_label("🌐 웹사이트", self.font_family)
        web_provider_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        web_provider_header = QHBoxLayout()
        web_provider_header.setSpacing(8)
        web_provider_header.setContentsMargins(0, 0, 0, 0)
        web_provider_header.addWidget(web_provider_label)
        gemini_web_layout.addLayout(web_provider_header)

        web_provider_row = QHBoxLayout()
        web_provider_row.setSpacing(10)
        web_provider_row.setContentsMargins(0, 4, 0, 0)

        self.web_ai_gpt_radio = QRadioButton("GPT")
        self.web_ai_gemini_radio = QRadioButton("Gemini")
        self.web_ai_perplexity_radio = QRadioButton("Perplexity")
        for radio in (self.web_ai_gpt_radio, self.web_ai_gemini_radio, self.web_ai_perplexity_radio):
            radio.setFont(QFont(self.font_family, 12))
            radio.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent;")
            web_provider_row.addWidget(radio)

        gemini_web_layout.addLayout(web_provider_row)
        
        # 웹사이트 섬션 아래 여백
        gemini_web_layout.addSpacing(12)
        
        self.web_ai_group = QButtonGroup(self)
        self.web_ai_group.addButton(self.web_ai_gpt_radio)
        self.web_ai_group.addButton(self.web_ai_gemini_radio)
        self.web_ai_group.addButton(self.web_ai_perplexity_radio)

        # --- Left: Gemini API 입력 ---
        gemini_api_widget = QWidget()
        gemini_api_widget.setStyleSheet("QWidget { background-color: transparent; }")
        gemini_api_layout = QVBoxLayout(gemini_api_widget)
        gemini_api_layout.setSpacing(4)
        gemini_api_layout.setContentsMargins(0, 0, 0, 0)
        
        # 구분선
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet(f"QFrame {{ border: 1px solid {NAVER_BORDER}; }}")
        gemini_api_layout.addWidget(separator)
        
        # Gemini API 섬션 위 여백
        gemini_api_layout.addSpacing(8)
        
        gemini_api_label = PremiumCard.create_section_label("✨ Gemini API (2.5 Flash-Lite)", self.font_family)
        gemini_api_layout.addWidget(gemini_api_label)
        
        gemini_api_input_layout = QHBoxLayout()
        self.gemini_api_entry = QLineEdit()
        self.gemini_api_entry.setPlaceholderText("Gemini API 키")
        self.gemini_api_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_api_entry.setCursorPosition(0)
        self.gemini_api_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
                min-height: 32px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.gemini_api_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        gemini_api_input_layout.addWidget(self.gemini_api_entry)
        
        gemini_toggle_container = QVBoxLayout()
        gemini_toggle_container.setSpacing(2)
        
        self.gemini_toggle_btn = QPushButton("비공개")
        self.gemini_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gemini_toggle_btn.setMinimumSize(64, 30)
        self.gemini_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_TEXT};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {NAVER_TEXT};
            }}
        """)
        self.gemini_toggle_btn.clicked.connect(self.toggle_gemini_api_key)
        gemini_toggle_container.addWidget(self.gemini_toggle_btn)

        gemini_api_input_layout.addLayout(gemini_toggle_container)
        gemini_api_layout.addLayout(gemini_api_input_layout)

        self.gemini_mode_group = QButtonGroup(self)
        self.gemini_mode_group.addButton(self.gemini_api_radio)
        self.gemini_mode_group.addButton(self.gemini_web_radio)

        if self.config.get("gemini_mode", "api") == "web":
            self.gemini_web_radio.setChecked(True)
        else:
            self.gemini_api_radio.setChecked(True)

        self.gemini_api_radio.toggled.connect(self.on_gemini_mode_changed)
        self.gemini_web_radio.toggled.connect(self.on_gemini_mode_changed)

        web_provider = (self.config.get("web_ai_provider", "gemini") or "gemini").lower()
        if web_provider == "gpt":
            self.web_ai_gpt_radio.setChecked(True)
        elif web_provider == "perplexity":
            self.web_ai_perplexity_radio.setChecked(True)
        else:
            self.web_ai_gemini_radio.setChecked(True)

        self.web_ai_gpt_radio.toggled.connect(self.on_web_ai_provider_changed)
        self.web_ai_gemini_radio.toggled.connect(self.on_web_ai_provider_changed)
        self.web_ai_perplexity_radio.toggled.connect(self.on_web_ai_provider_changed)

        api_grid.addWidget(gemini_web_widget, 0, 0)
        api_grid.addWidget(gemini_api_widget, 1, 0)

        api_card.content_layout.addLayout(api_grid)

        # 버튼 레이아웃
        api_button_layout = QHBoxLayout()

        api_save_btn = QPushButton("💾 AI 설정 저장")
        api_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        api_save_btn.setStyleSheet(save_btn_style)
        api_save_btn.setMinimumHeight(save_btn_height)
        api_save_btn.clicked.connect(self.save_api_key)
        api_button_layout.addWidget(api_save_btn)
        
        api_card.content_layout.addStretch()
        api_card.content_layout.addLayout(api_button_layout)
        
        api_card.setMinimumHeight(420)
        
        layout.addWidget(api_card, 4, 0)
        
        # === Row 2, Col 1: 파일 관리 ===
        file_card = PremiumCard("파일 관리", "📁")
        
        file_card.content_layout.addStretch()
        
        file_grid = QGridLayout()
        file_grid.setColumnStretch(0, 1)
        file_grid.setColumnStretch(1, 1)
        file_grid.setVerticalSpacing(16)
        
        # Row 0: 키워드 파일 | 프롬프트1 (제목+서론)
        keyword_widget = QWidget()
        keyword_widget.setStyleSheet("QWidget { background-color: transparent; }")
        keyword_layout = QHBoxLayout(keyword_widget)
        keyword_layout.setContentsMargins(0, 6, 0, 6)
        keyword_layout.setSpacing(10)
        
        keyword_label = PremiumCard.create_section_label("📝 키워드 파일", self.font_family)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addStretch()
        
        keyword_open_btn = QPushButton("📂 열기")
        keyword_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        keyword_open_btn.setFixedSize(75, 24)
        keyword_open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_BLUE};
                border: none;
                border-radius: 6px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: #0066E6;
            }}
        """)
        keyword_open_btn.clicked.connect(lambda: self.open_file("setting/keywords.txt"))
        keyword_layout.addWidget(keyword_open_btn)
        
        file_grid.addWidget(keyword_widget, 0, 0)
        
        prompt1_widget = QWidget()
        prompt1_widget.setStyleSheet("QWidget { background-color: transparent; }")
        prompt1_layout = QHBoxLayout(prompt1_widget)
        prompt1_layout.setContentsMargins(0, 6, 0, 6)
        prompt1_layout.setSpacing(10)
        
        prompt1_label = PremiumCard.create_section_label("💬 프롬프트1 (제목+서론)", self.font_family)
        prompt1_layout.addWidget(prompt1_label)
        prompt1_layout.addStretch()
        
        prompt1_open_btn = QPushButton("📂 열기")
        prompt1_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prompt1_open_btn.setFixedSize(75, 24)
        prompt1_open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_BLUE};
                border: none;
                border-radius: 6px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: #0066E6;
            }}
        """)
        prompt1_open_btn.clicked.connect(lambda: self.open_file("setting/prompt1.txt"))
        prompt1_layout.addWidget(prompt1_open_btn)
        
        file_grid.addWidget(prompt1_widget, 0, 1)
        
        # Row 1: 썸네일 폴더 | 프롬프트2 (소제목+본문)
        thumbnail_widget = QWidget()
        thumbnail_widget.setStyleSheet("QWidget { background-color: transparent; }")
        thumbnail_layout = QHBoxLayout(thumbnail_widget)
        thumbnail_layout.setContentsMargins(0, 6, 0, 6)
        thumbnail_layout.setSpacing(10)
        
        thumbnail_label = PremiumCard.create_section_label("🖼️ 썸네일 폴더", self.font_family)
        thumbnail_layout.addWidget(thumbnail_label)
        thumbnail_layout.addStretch()
        
        # 썸네일 ON/OFF 토글 버튼
        self.thumbnail_toggle_btn = QPushButton("ON")
        self.thumbnail_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumbnail_toggle_btn.setFixedSize(60, 24)
        self.thumbnail_toggle_btn.setCheckable(True)
        self.thumbnail_toggle_btn.setChecked(self.config.get("use_thumbnail", True))
        self.thumbnail_toggle_btn.clicked.connect(self.toggle_thumbnail)
        self.update_thumbnail_button_style()
        thumbnail_layout.addWidget(self.thumbnail_toggle_btn)
        
        thumbnail_open_btn = QPushButton("📂 열기")
        thumbnail_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        thumbnail_open_btn.setFixedSize(75, 24)
        thumbnail_open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_BLUE};
                border: none;
                border-radius: 6px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: #0066E6;
            }}
        """)
        thumbnail_open_btn.clicked.connect(lambda: self.open_file("setting/image"))
        thumbnail_layout.addWidget(thumbnail_open_btn)
        
        file_grid.addWidget(thumbnail_widget, 1, 0)
        
        prompt2_widget = QWidget()
        prompt2_widget.setStyleSheet("QWidget { background-color: transparent; }")
        prompt2_layout = QHBoxLayout(prompt2_widget)
        prompt2_layout.setContentsMargins(0, 6, 0, 6)
        prompt2_layout.setSpacing(10)
        
        prompt2_label = PremiumCard.create_section_label("💬 프롬프트2 (소제목+본문)", self.font_family)
        prompt2_layout.addWidget(prompt2_label)
        prompt2_layout.addStretch()
        
        prompt2_open_btn = QPushButton("📂 열기")
        prompt2_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prompt2_open_btn.setFixedSize(75, 24)
        prompt2_open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_BLUE};
                border: none;
                border-radius: 6px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: #0066E6;
            }}
        """)
        prompt2_open_btn.clicked.connect(lambda: self.open_file("setting/prompt2.txt"))
        prompt2_layout.addWidget(prompt2_open_btn)
        
        file_grid.addWidget(prompt2_widget, 1, 1)
        
        file_card.content_layout.addLayout(file_grid)
        file_card.content_layout.addStretch()
        
        file_card.setMinimumHeight(card_min_height)
        
        layout.addWidget(file_card, 2, 1)
        
        # === Row 2, Col 0: 포스팅 방법 ===
        posting_card = PremiumCard("포스팅 방법", "📰")
        posting_card.content_layout.addStretch()

        posting_desc = QLabel("포스팅 작성 방식을 선택하세요.")
        posting_desc.setFont(QFont(self.font_family, 12))
        posting_desc.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent;")
        posting_card.content_layout.addWidget(posting_desc)

        posting_layout = QHBoxLayout()
        posting_layout.setSpacing(20)

        self.posting_search_radio = QRadioButton("정보성 포스팅")
        self.posting_search_radio.setFont(QFont(self.font_family, 13))
        self.posting_search_radio.setChecked(True)

        self.posting_home_radio = QRadioButton("네쇼커 (업뎻 예정)")
        self.posting_home_radio.setFont(QFont(self.font_family, 13))

        for radio in (self.posting_search_radio, self.posting_home_radio):
            radio.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent;")
            posting_layout.addWidget(radio)

        self.posting_search_radio.toggled.connect(self.on_posting_method_changed)
        self.posting_home_radio.toggled.connect(self.on_posting_method_changed)

        posting_card.content_layout.addLayout(posting_layout)
        posting_card.content_layout.addStretch()

        posting_save_btn = QPushButton("💾 포스팅 방법 저장")
        posting_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        posting_save_btn.setStyleSheet(save_btn_style)
        posting_save_btn.setMinimumHeight(save_btn_height)
        posting_save_btn.clicked.connect(self.save_posting_method)
        posting_card.content_layout.addWidget(posting_save_btn)

        posting_card.setMinimumHeight(card_min_height)

        layout.addWidget(posting_card, 2, 0)
        
        # ===== 관련 글 설정 카드 =====
        related_posts_card = PremiumCard("관련 글 설정", "", self)
        related_posts_header = related_posts_card.header_layout.itemAt(0).widget()
        related_posts_header.setText("📚 관련 글 설정")

        mode_header_container = QWidget()
        mode_header_container.setStyleSheet("QWidget { background-color: transparent; }")
        mode_header_layout = QHBoxLayout(mode_header_container)
        mode_header_layout.setContentsMargins(0, 0, 0, 0)
        mode_header_layout.setSpacing(12)

        self.related_posts_mode_latest = QRadioButton("최신 글")
        self.related_posts_mode_popular = QRadioButton("인기 글")
        for radio in (self.related_posts_mode_latest, self.related_posts_mode_popular):
            radio.setFont(QFont(self.font_family, 13, QFont.Weight.Bold))
            radio.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent;")
            radio.toggled.connect(lambda checked, r=radio: self._sync_related_posts_title(r.text()) if checked else None)
            mode_header_layout.addWidget(radio)

        related_posts_card.header_layout.insertWidget(1, mode_header_container)
        related_posts_card.header_layout.addStretch()

        # 2열 그리드 레이아웃 생성
        inputs_grid = QGridLayout()
        inputs_grid.setHorizontalSpacing(12)
        inputs_grid.setVerticalSpacing(8)
        inputs_grid.setContentsMargins(0, 12, 0, 0)
        
        # 왼쪽 열: 섹션 제목
        section_container = QWidget()
        section_container.setStyleSheet("QWidget { background-color: transparent; }")
        section_layout = QVBoxLayout(section_container)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(6)
        
        section_label = PremiumCard.create_section_label("📚 섹션 제목", self.font_family)
        section_layout.addWidget(section_label)
        
        self.related_posts_title_entry = QLineEdit()
        self.related_posts_title_entry.setPlaceholderText("함께 보면 좋은 글")
        self.related_posts_title_entry.setFont(QFont(self.font_family, 12))
        self.related_posts_title_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 6px 10px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
                min-height: 32px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.related_posts_title_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.related_posts_title_entry.returnPressed.connect(self.save_related_posts_settings)
        section_layout.addWidget(self.related_posts_title_entry)
        
        inputs_grid.addWidget(section_container, 0, 0)

        # 오른쪽 열: 블로그 주소
        blog_container = QWidget()
        blog_container.setStyleSheet("QWidget { background-color: transparent; }")
        blog_layout = QVBoxLayout(blog_container)
        blog_layout.setContentsMargins(0, 0, 0, 0)
        blog_layout.setSpacing(6)
        
        blog_addr_label = PremiumCard.create_section_label("🌐 블로그 주소", self.font_family)
        blog_layout.addWidget(blog_addr_label)
        
        self.blog_address_entry = QLineEdit()
        self.blog_address_entry.setPlaceholderText("yourname (예: david153official)")
        self.blog_address_entry.setFont(QFont(self.font_family, 12))
        self.blog_address_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 6px 10px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
                min-height: 32px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.blog_address_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        blog_layout.addWidget(self.blog_address_entry)
        
        inputs_grid.addWidget(blog_container, 0, 1)
        
        related_posts_card.content_layout.addLayout(inputs_grid)

        # 저장 버튼
        related_posts_save_btn = QPushButton("💾 설정 저장")
        related_posts_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        related_posts_save_btn.setStyleSheet(save_btn_style)
        related_posts_save_btn.setMinimumHeight(save_btn_height)
        related_posts_save_btn.clicked.connect(self.save_related_posts_settings)
        related_posts_card.content_layout.addWidget(related_posts_save_btn)

        related_posts_card.setMinimumHeight(card_min_height)
        layout.addWidget(related_posts_card, 3, 1)

        # 설정 변경 시 모니터링 상태를 실시간으로 갱신
        def _refresh_settings_status():
            self.update_status_display()
            self._update_settings_summary()

        for widget in (
            self.naver_id_entry,
            self.naver_pw_entry,
            self.gemini_api_entry,
            self.interval_entry,
            self.link_url_entry,
            self.link_text_entry,
            self.related_posts_title_entry,
            self.blog_address_entry,
        ):
            widget.textChanged.connect(_refresh_settings_status)

        for radio in (
            self.gemini_api_radio,
            self.gemini_web_radio,
            self.web_ai_gpt_radio,
            self.web_ai_gemini_radio,
            self.web_ai_perplexity_radio,
            self.posting_search_radio,
            self.posting_home_radio,
            self.related_posts_mode_latest,
            self.related_posts_mode_popular,
        ):
            radio.toggled.connect(_refresh_settings_status)

        self.use_link_checkbox.stateChanged.connect(_refresh_settings_status)
        self.thumbnail_toggle_btn.clicked.connect(_refresh_settings_status)

        # 설정 탭 클릭 즉시 로그 표시
        def _log_settings_click(message):
            self._update_settings_status(message)

        self.gemini_api_radio.toggled.connect(
            lambda checked: _log_settings_click("🔑 AI 설정: Gemini API 선택") if checked else None
        )
        self.gemini_web_radio.toggled.connect(
            lambda checked: _log_settings_click("🔑 AI 설정: 웹사이트 선택") if checked else None
        )
        self.web_ai_gpt_radio.toggled.connect(
            lambda checked: _log_settings_click("🌐 웹사이트 AI: GPT 선택") if checked else None
        )
        self.web_ai_gemini_radio.toggled.connect(
            lambda checked: _log_settings_click("🌐 웹사이트 AI: Gemini 선택") if checked else None
        )
        self.web_ai_perplexity_radio.toggled.connect(
            lambda checked: _log_settings_click("🌐 웹사이트 AI: Perplexity 선택") if checked else None
        )
        self.posting_search_radio.toggled.connect(
            lambda checked: _log_settings_click("📰 포스팅 방식: 정보성 포스팅 선택") if checked else None
        )
        self.posting_home_radio.toggled.connect(
            lambda checked: _log_settings_click("📰 포스팅 방식: 네쇼커 선택") if checked else None
        )
        self.related_posts_mode_latest.toggled.connect(
            lambda checked: _log_settings_click("📚 관련 글: 최신 글 선택") if checked else None
        )
        self.related_posts_mode_popular.toggled.connect(
            lambda checked: _log_settings_click("📚 관련 글: 인기 글 선택") if checked else None
        )
        self.use_link_checkbox.stateChanged.connect(
            lambda state: _log_settings_click("🔗 외부 링크: 사용" if state else "🔗 외부 링크: 미사용")
        )
        self.thumbnail_toggle_btn.clicked.connect(
            lambda: _log_settings_click("🖼️ 썸네일: ON" if self.thumbnail_toggle_btn.isChecked() else "🖼️ 썸네일: OFF")
        )
        
        # 설정 로그 카드를 'AI 설정' 오른쪽에 배치
        settings_progress_card.setMinimumHeight(card_min_height)
        layout.addWidget(settings_progress_card, 4, 1)
        
        tab.setWidget(content)
        return tab
    
    def _apply_config(self):
        """저장된 설정 적용"""
        if not self.config:
            return
        
        # API 키 (Gemini)
        if "gemini_api_key" in self.config:
            self.gemini_api_entry.setText(self.config["gemini_api_key"])
        
        # 구버전 호환성 (api_key만 있는 경우)
        if "api_key" in self.config and "gemini_api_key" not in self.config:
            self.gemini_api_entry.setText(self.config["api_key"])

        # AI 모델 (고정)
        self.config["ai_model"] = "gemini"
        
        # Gemini ??
        gemini_mode = self.config.get("gemini_mode", "api")
        if hasattr(self, "gemini_web_radio"):
            if gemini_mode == "web":
                self.gemini_web_radio.setChecked(True)
            else:
                self.gemini_api_radio.setChecked(True)

        web_provider = (self.config.get("web_ai_provider", "gemini") or "gemini").lower()
        if hasattr(self, "web_ai_gpt_radio"):
            if web_provider == "gpt":
                self.web_ai_gpt_radio.setChecked(True)
            elif web_provider == "perplexity":
                self.web_ai_perplexity_radio.setChecked(True)
            else:
                self.web_ai_gemini_radio.setChecked(True)


        # 포스팅 방법
        posting_method = self.config.get("posting_method", "search")
        if hasattr(self, "posting_home_radio"):
            if posting_method == "home":
                self.posting_home_radio.setChecked(True)
            else:
                self.posting_search_radio.setChecked(True)
        self.posting_method = "home" if posting_method == "home" else "search"

        # 로그인 정보
        if "naver_id" in self.config:
            self.naver_id_entry.setText(self.config["naver_id"])
        if "naver_pw" in self.config:
            self.naver_pw_entry.setText(self.config["naver_pw"])
        
        # 발행 간격
        if "interval" in self.config:
            self.interval_entry.setText(str(self.config["interval"]))
        
        # 외부 링크
        if self.config.get("use_external_link"):
            self.use_link_checkbox.setChecked(True)
        if "external_link" in self.config:
            self.link_url_entry.setText(self.config["external_link"])
        if "external_link_text" in self.config:
            self.link_text_entry.setText(self.config["external_link_text"])
        
        # 함께 보면 좋은 글 설정
        if "blog_address" in self.config:
            blog_address = self.config["blog_address"]
            # 전체 URL에서 아이디만 추출해서 표시
            if blog_address.startswith("https://blog.naver.com/"):
                blog_id = blog_address.replace("https://blog.naver.com/", "")
                self.blog_address_entry.setText(blog_id)
            else:
                self.blog_address_entry.setText(blog_address)
        if "related_posts_title" in self.config:
            self.related_posts_title_entry.setText(self.config["related_posts_title"])
        mode_value = self.config.get("related_posts_mode", "latest")
        if hasattr(self, "related_posts_mode_popular") and hasattr(self, "related_posts_mode_latest"):
            if mode_value == "popular":
                self.related_posts_mode_popular.setChecked(True)
            else:
                self.related_posts_mode_latest.setChecked(True)
        

        # Qt 이벤트 루프가 텍스트를 완전히 반영한 후 상태 업데이트
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.update_status_display)
        QTimer.singleShot(0, self._update_settings_summary)
    
    def update_status_display(self):
        """상태 표시 업데이트"""
        # 로그인 정보 상태 (UI 입력창에서 직접 읽기)
        naver_id = self.naver_id_entry.text().strip()
        naver_pw = self.naver_pw_entry.text().strip()
        
        if naver_id and naver_pw:
            self.login_status_label.setText("👤 로그인: 설정 완료")
            self.login_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.login_setup_btn.setText("변경하기")
            self.login_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_GREEN};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #00C73C;
                }}
            """)
            self.login_setup_btn.show()
        else:
            self.login_status_label.setText("👤 로그인: 미설정")
            self.login_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.login_setup_btn.setText("설정하기")
            self.login_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_RED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #D32F2F;
                }}
            """)
            self.login_setup_btn.show()
        
        # API ? ?? (UI ????? ?? ??)
        gemini_key = self.gemini_api_entry.text().strip() if hasattr(self, 'gemini_api_entry') else ""
        gemini_mode = self.config.get("gemini_mode", "api")
        web_provider = (self.config.get("web_ai_provider", "gemini") or "gemini").lower()
        provider_label = "GPT" if web_provider == "gpt" else ("Perplexity" if web_provider == "perplexity" else "Gemini")

        if gemini_mode == "web":
            self.api_status_label.setText(f"🔑 AI 설정: 웹사이트({provider_label})")
            self.api_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.api_setup_btn.setText("변경하기")
            self.api_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_GREEN};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #00C73C;
                }}
            """)
            self.api_setup_btn.show()
        elif gemini_key:
            self.api_status_label.setText("🔑 AI 설정: Gemini")
            self.api_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.api_setup_btn.setText("변경하기")
            self.api_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_GREEN};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #00C73C;
                }}
            """)
            self.api_setup_btn.show()
        else:
            self.api_status_label.setText("🔑 AI 설정: 미설정")
            self.api_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.api_setup_btn.setText("설정하기")
            self.api_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_RED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #D32F2F;
                }}
            """)
            self.api_setup_btn.show()

        method = "home" if self.posting_home_radio.isChecked() else "search"
        method_label = "네쇼커" if method == "home" else "정보성 포스팅"
        self.posting_status_label.setText(f"📰 포스팅: {method_label}")
        self.posting_status_label.setStyleSheet(f"color: #000000; border: none;")
        self.posting_setup_btn.setText("변경하기")
        self.posting_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_GREEN};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: #00C73C;
            }}
        """)

        # 키워드 개수
        keyword_count = self.count_keywords()
        self.keyword_count_label.setText(f"📦 키워드 개수: {keyword_count}개")
        
        if keyword_count > 0:
            self.keyword_count_label.setStyleSheet(f"color: #000000; border: none;")
            self.keyword_setup_btn.setText("변경하기")
            self.keyword_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_GREEN};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #00C73C;
                }}
            """)
            self.keyword_setup_btn.show()
        else:
            self.keyword_count_label.setStyleSheet(f"color: #000000; border: none;")
            self.keyword_setup_btn.setText("설정하기")
            self.keyword_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_RED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #D32F2F;
                }}
            """)
            self.keyword_setup_btn.show()
        
        # 발행 간격
        interval = self.interval_entry.text() or "10"
        self.interval_label.setText(f"⏱️ 발행 간격: {interval}분")
        
        # 썸네일 기능 상태
        use_thumbnail = self.config.get("use_thumbnail", True)
        if use_thumbnail:
            self.thumbnail_status_label.setText("🖼️ 썸네일: ON")
            self.thumbnail_setup_btn.setText("설정하기")
            self.thumbnail_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_GREEN};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #00C73C;
                }}
            """)
        else:
            self.thumbnail_status_label.setText("🖼️ 썸네일: OFF")
            self.thumbnail_setup_btn.setText("설정하기")
            self.thumbnail_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_RED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #D32F2F;
                }}
            """)
        
        # 외부 링크 상태
        use_external_link = self.config.get("use_external_link", False)
        if use_external_link:
            self.ext_link_status_label.setText("🔗 외부 링크: ON")
            self.ext_link_setup_btn.setText("변경하기")
            self.ext_link_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_GREEN};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #00C73C;
                }}
            """)
        else:
            self.ext_link_status_label.setText("🔗 외부 링크: OFF")
            self.ext_link_setup_btn.setText("설정하기")
            self.ext_link_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_RED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #D32F2F;
                }}
            """)
        
        # 관련 글 상태
        blog_address = (self.blog_address_entry.text().strip() if hasattr(self, "blog_address_entry") else "").strip()
        if blog_address:
            if self.related_posts_mode_popular.isChecked():
                mode_text = "인기 글"
            else:
                mode_text = "최신 글"
            self.related_posts_status_label.setText(f"📚 관련 글: ON ({mode_text})")
            self.related_posts_setup_btn.setText("변경하기")
            self.related_posts_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_GREEN};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #00C73C;
                }}
            """)
        else:
            self.related_posts_status_label.setText("📚 관련 글: 미설정")
            self.related_posts_setup_btn.setText("설정하기")
            self.related_posts_setup_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_RED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #D32F2F;
                }}
            """)
    
    def _update_license_info(self):
        """라이선스 정보 업데이트"""
        try:
            license_manager = LicenseManager()
            license_info = license_manager.get_license_info()
            
            if license_info:
                expire_date = license_info.get("expire_date", "")
                if expire_date:
                    # 날짜 파싱 및 포맷팅
                    try:
                        from datetime import datetime
                        expire_dt = datetime.strptime(expire_date, "%Y-%m-%d")
                        today = datetime.now()
                        days_left = (expire_dt - today).days
                        
                        if days_left > 0:
                            self.license_period_label.setText(f"📅 사용기간: ~ {expire_date} (D-{days_left})")
                            self.license_period_label.setStyleSheet(f"color: #2E7D32; border: none;")
                        elif days_left == 0:
                            self.license_period_label.setText(f"📅 사용기간: 오늘까지")
                            self.license_period_label.setStyleSheet(f"color: #F57C00; border: none;")
                        else:
                            self.license_period_label.setText(f"📅 사용기간: 만료됨")
                            self.license_period_label.setStyleSheet(f"color: #D32F2F; border: none;")
                    except:
                        self.license_period_label.setText(f"📅 사용기간: ~ {expire_date}")
                        self.license_period_label.setStyleSheet(f"color: #000000; border: none;")
                else:
                    self.license_period_label.setText("📅 사용기간: 무제한")
                    self.license_period_label.setStyleSheet(f"color: #2E7D32; border: none;")
            else:
                self.license_period_label.setText("📅 사용기간: 확인 실패")
                self.license_period_label.setStyleSheet(f"color: #D32F2F; border: none;")
        except Exception as e:
            self.license_period_label.setText("📅 사용기간: 확인 실패")
            self.license_period_label.setStyleSheet(f"color: #D32F2F; border: none;")
    
    def count_keywords(self):
        """키워드 개수 카운트"""
        try:
            keywords_file = os.path.join("setting", "keywords.txt")
            if os.path.exists(keywords_file):
                with open(keywords_file, "r", encoding="utf-8") as f:
                    return len([line.strip() for line in f if line.strip() and not line.strip().startswith('#')])
        except:
            pass
        return 0
    
    def toggle_api_key(self):
        """API 키 표시/숨김 (구버전 호환)"""
        # 기존 코드와의 호환성 유지
        if hasattr(self, 'api_key_entry'):
            if self.api_key_entry.echoMode() == QLineEdit.EchoMode.Password:
                self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Normal)
            else:
                self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
    
    def toggle_gemini_api_key(self):
        """Gemini API 키 표시/숨김"""
        if self.gemini_api_entry.echoMode() == QLineEdit.EchoMode.Password:
            self.gemini_api_entry.setEchoMode(QLineEdit.EchoMode.Normal)
            self.gemini_toggle_btn.setText("공개")
        else:
            self.gemini_api_entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.gemini_toggle_btn.setText("비공개")

    def on_gemini_mode_changed(self):
        """Gemini 방식 변경"""
        mode = "web" if self.gemini_web_radio.isChecked() else "api"
        self.config["gemini_mode"] = mode
        label = "웹사이트" if mode == "web" else "API"
        self._update_settings_status(f"🔑 AI 설정: {label}")
        self.save_config_file()
        self.update_status_display()
        self._update_settings_summary()

    def on_web_ai_provider_changed(self):
        if self.web_ai_gpt_radio.isChecked():
            provider = "gpt"
        elif self.web_ai_perplexity_radio.isChecked():
            provider = "perplexity"
        else:
            provider = "gemini"
        self.config["web_ai_provider"] = provider
        self._update_settings_status(f"🌐 웹사이트 AI: {provider.upper()}")
        self.save_config_file()
        self.update_status_display()
        self._update_settings_summary()

    def toggle_password(self):
        """비밀번호 표시/숨김"""
        if self.naver_pw_entry.echoMode() == QLineEdit.EchoMode.Password:
            self.naver_pw_entry.setEchoMode(QLineEdit.EchoMode.Normal)
            self.pw_toggle_btn.setText("공개")
        else:
            self.naver_pw_entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.pw_toggle_btn.setText("비공개")
    
    def toggle_external_link(self):
        """외부 링크 활성화/비활성화"""
        enabled = self.use_link_checkbox.isChecked()
        
        # 활성화 상태 설정
        self.link_url_entry.setEnabled(enabled)
        self.link_text_entry.setEnabled(enabled)
        
        # ON/OFF 라벨 업데이트
        if enabled:
            self.link_status_label.setText("ON")
            self.link_status_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {NAVER_GREEN};
                    color: white;
                    border-radius: 8px;
                    padding: 4px 8px;
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
            self.link_url_entry.setFocus()
            self.link_url_entry.selectAll()
            self._update_settings_status("🔗 외부 링크 기능 ON")
        else:
            self.link_status_label.setText("OFF")
            self.link_status_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {NAVER_RED};
                    color: white;
                    border-radius: 8px;
                    padding: 4px 8px;
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
            self._update_settings_status("🔗 외부 링크 기능 OFF")
    
    def _clear_example_text(self, widget, example_text):
        """예시 텍스트 삭제"""
        if widget.text() == example_text:
            widget.clear()
    
    def _show_auto_close_message(self, message, icon=None):
        """자동으로 닫히는 메시지 창 (1초 후, 소리 없음)"""
        # 소리가 나지 않도록 QMessageBox 대신 QDialog 사용
        from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout
        
        msg_dialog = QDialog(self)
        msg_dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        
        # 스타일 설정
        msg_dialog.setStyleSheet(f"""
            QDialog {{
                background-color: rgba(255, 255, 255, 0.95);
                border: 2px solid {NAVER_GREEN};
                border-radius: 12px;
            }}
            QLabel {{
                font-size: 14px;
                font-weight: bold;
                color: {NAVER_TEXT};
                padding: 15px 30px;
                background-color: transparent;
            }}
        """)
        
        layout = QVBoxLayout(msg_dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        # 중앙 배치
        msg_dialog.adjustSize()
        parent_geo = self.geometry()
        x = parent_geo.x() + (parent_geo.width() - msg_dialog.width()) // 2
        y = parent_geo.y() + (parent_geo.height() - msg_dialog.height()) // 2
        msg_dialog.move(x, y)
        
        msg_dialog.show()
        QTimer.singleShot(1000, msg_dialog.close)
    
    def _update_settings_status(self, message):
        """설정 탭 진행 현황 업데이트"""
        if not hasattr(self, 'settings_log_label'):
            return
        
        try:
            # 현재 시간 추가
            from datetime import datetime
            current_time = datetime.now().strftime("%H:%M:%S")
            message_with_time = f"{message} ({current_time})"
            
            current_log = self.settings_log_label.text()
            
            # 초기 상태
            if current_log == "⏸️ 대기 중...":
                new_log = message_with_time
            else:
                lines = current_log.split("\n")
                last_message = lines[-1].strip() if lines else ""
                
                # 완전히 동일한 메시지는 무시 (시간 제외)
                if last_message.startswith(message.strip()):
                    return
                
                # 최근 10개 메시지만 유지
                if len(lines) >= 10:
                    lines = lines[-9:]
                
                new_log = "\n".join(lines) + "\n" + message_with_time
            
            self.settings_log_label.setText(new_log)
            self.settings_log_label.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent; padding: 5px;")
            
            # 스크롤을 맨 하단으로 이동 (새 로그 메시지가 온전히 보이도록)
            if hasattr(self, 'settings_log_scroll'):
                scrollbar = self.settings_log_scroll.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
            
            # 상태 요약 업데이트
            self._update_settings_summary()
        except Exception as e:
            print(f"설정 로그 업데이트 오류: {e}")
    
    def _update_settings_summary(self):
        """설정 상태 요약 업데이트"""
        if not hasattr(self, 'settings_api_status'):
            return
        try:
        
            # API ? ??
            gemini_key = self.gemini_api_entry.text() if hasattr(self, 'gemini_api_entry') else ""
            gemini_mode = self.config.get("gemini_mode", "api")
            web_provider = (self.config.get("web_ai_provider", "gemini") or "gemini").lower()
            provider_label = "GPT" if web_provider == "gpt" else ("Perplexity" if web_provider == "perplexity" else "Gemini")

            if gemini_mode == "web":
                api_text = f"🔑 AI 설정: 웹사이트({provider_label})"
                api_color = NAVER_GREEN
            elif gemini_key:
                api_text = "🔑 AI 설정: Gemini"
                api_color = NAVER_GREEN
            else:
                api_text = "🔑 AI 설정: 미설정"
                api_color = NAVER_RED

            
            self.settings_api_status.setText(api_text)
            self.settings_api_status.setStyleSheet(f"color: {api_color}; background-color: transparent; border: none; font-weight: bold;")
            
            # 로그인 상태
            naver_id = self.naver_id_entry.text() if hasattr(self, 'naver_id_entry') else ""
            naver_pw = self.naver_pw_entry.text() if hasattr(self, 'naver_pw_entry') else ""
            
            if naver_id and naver_pw:
                login_text = "👤 로그인: 설정 완료"
                login_color = NAVER_GREEN
            else:
                login_text = "👤 로그인: 미설정"
                login_color = NAVER_RED
            
            self.settings_login_status.setText(login_text)
            self.settings_login_status.setStyleSheet(f"color: {login_color}; background-color: transparent; border: none; font-weight: bold;")
            
            # 썸네일 상태
            use_thumbnail = self.config.get("use_thumbnail", True)
            if use_thumbnail:
                thumb_text = "🖼️ 썸네일: ON (동영상 ON)"
                thumb_color = NAVER_GREEN
            else:
                thumb_text = "🖼️ 썸네일: OFF (동영상 OFF)"
                thumb_color = NAVER_TEXT_SUB
            
            self.settings_thumbnail_status.setText(thumb_text)
            self.settings_thumbnail_status.setStyleSheet(f"color: {thumb_color}; background-color: transparent; border: none; font-weight: bold;")
            
            # 외부 링크 상태 (체크박스 상태를 직접 확인)
            use_link = self.use_link_checkbox.isChecked() if hasattr(self, 'use_link_checkbox') else self.config.get("use_external_link", False)
            if use_link:
                link_text = "🔗 외부링크: ON"
                link_color = NAVER_GREEN
            else:
                link_text = "🔗 외부링크: OFF"
                link_color = NAVER_TEXT_SUB
            
            self.settings_link_status_label.setText(link_text)
            self.settings_link_status_label.setStyleSheet(f"color: {link_color}; background-color: transparent; border: none; font-weight: bold;")
            
        except Exception as e:
            print(f"설정 상태 요약 업데이트 오류: {e}")
    
    def open_file(self, filename):
        """파일 또는 폴더 열기"""
        import subprocess
        import platform
        
        file_path = os.path.join(self.data_dir, filename)
        
        # 폴더인 경우
        if filename.endswith(('image', 'result')) or os.path.isdir(file_path):
            if not os.path.exists(file_path):
                try:
                    os.makedirs(file_path, exist_ok=True)
                    self._update_settings_status(f"📁 {filename} 폴더를 생성했습니다")
                except Exception as e:
                    self._update_settings_status(f"❌ 폴더 생성 실패: {str(e)}")
                    return
            
            # 폴더 열기
            try:
                if platform.system() == 'Windows':
                    os.startfile(file_path)
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.run(['open', file_path])
                else:  # Linux
                    subprocess.run(['xdg-open', file_path])
                self._update_settings_status(f"📂 {filename} 폴더를 열었습니다")
            except Exception as e:
                self._update_settings_status(f"❌ 폴더 열기 실패: {str(e)}")
            return
        
        # 파일인 경우
        if not os.path.exists(file_path):
            # 파일이 없으면 생성
            try:
                # 디렉토리 생성
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    if "keywords.txt" in filename:
                        f.write("# 키워드를 한 줄에 하나씩 입력하세요\n")
                    elif "prompt1.txt" in filename:
                        f.write("# 제목과 서론 생성을 위한 AI 프롬프트를 입력하세요\n")
                    elif "prompt2.txt" in filename:
                        f.write("# 소제목과 본문 생성을 위한 AI 프롬프트를 입력하세요\n")
                self._update_settings_status(f"📝 {os.path.basename(filename)} 파일을 생성했습니다")
            except Exception as e:
                self._update_settings_status(f"❌ 파일 생성 실패: {str(e)}")
                return
        
        # 파일 열기
        try:
            if platform.system() == 'Windows':
                os.startfile(file_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', file_path])
            else:  # Linux
                subprocess.run(['xdg-open', file_path])
            self._update_settings_status(f"📂 {os.path.basename(filename)} 파일을 열었습니다")
        except Exception as e:
            self._update_settings_status(f"❌ 파일 열기 실패: {str(e)}")
    
    def save_api_key(self):
        """API ? ??"""
        gemini_key = self.gemini_api_entry.text().strip()
        gemini_mode = self.config.get("gemini_mode", "api")
        if self.web_ai_gpt_radio.isChecked():
            web_provider = "gpt"
        elif self.web_ai_perplexity_radio.isChecked():
            web_provider = "perplexity"
        else:
            web_provider = "gemini"

        if not gemini_key and gemini_mode != "web":
            self._show_auto_close_message("⚠️ Gemini API 키를 입력해주세요", QMessageBox.Icon.Warning)
            return

        self.config["gemini_api_key"] = gemini_key
        self.config["api_key"] = gemini_key
        self.config["ai_model"] = "gemini"
        self.config["web_ai_provider"] = web_provider
        if gemini_key:
            self._update_settings_status("🔑 Gemini API 키가 저장되었습니다")
        else:
            self._update_settings_status(f"🌐 웹사이트 모드 ({web_provider.upper()})")
        self.save_config_file()
        self.update_status_display()
        self._update_settings_summary()
        if gemini_key:
            self._show_auto_close_message("✅ Gemini API 키가 저장되었습니다", QMessageBox.Icon.Information)
        else:
            self._show_auto_close_message("✅ 웹사이트 모드로 저장되었습니다", QMessageBox.Icon.Information)

    def on_posting_method_changed(self):
        """포스팅 방법 라디오 변경 시 상태 반영"""
        method = "home" if self.posting_home_radio.isChecked() else "search"
        self.posting_method = method
        self.config["posting_method"] = method

    def save_posting_method(self):
        """포스팅 방법 저장"""
        method = "home" if self.posting_home_radio.isChecked() else "search"
        self.posting_method = method
        self.config["posting_method"] = method
        label = "네쇼커" if method == "home" else "검색 노출"
        self._update_settings_status(f"📰 포스팅 방법이 '{label}'로 설정되었습니다")
        self.save_config_file()
        self._update_settings_summary()
        self._show_auto_close_message(f"✅ 포스팅 방법이 '{label}'로 저장되었습니다", QMessageBox.Icon.Information)

    def save_login_info(self):
        """로그인 정보 저장"""
        naver_id = self.naver_id_entry.text().strip()
        naver_pw = self.naver_pw_entry.text().strip()
        
        if not naver_id or not naver_pw:
            self._show_auto_close_message("⚠️ 아이디와 비밀번호를 모두 입력해주세요", QMessageBox.Icon.Warning)
            return
        
        self.config["naver_id"] = naver_id
        self.config["naver_pw"] = naver_pw
        self._update_settings_status("👤 로그인 정보가 저장되었습니다")
        self.save_config_file()
        self.update_status_display()
        self._update_settings_summary()
        self._show_auto_close_message("✅ 로그인 정보가 저장되었습니다", QMessageBox.Icon.Information)
    
    def save_time_settings(self):
        """발행 간격 저장"""
        interval_text = self.interval_entry.text().strip()
        
        if not interval_text:
            self._show_auto_close_message("⚠️ 발행 간격을 입력해주세요", QMessageBox.Icon.Warning)
            return
        
        try:
            interval = int(interval_text)
            if interval < 1:
                self._show_auto_close_message("⚠️ 발행 간격은 1분 이상이어야 합니다", QMessageBox.Icon.Warning)
                return
        except ValueError:
            self._show_auto_close_message("⚠️ 숫자를 입력해주세요", QMessageBox.Icon.Warning)
            return
        
        self.config["interval"] = interval
        self._update_settings_status(f"⏰ 발행 간격: {interval}분")
        self.save_config_file()
        self.update_status_display()
        self._show_auto_close_message(f"✅ 발행 간격이 {interval}분으로 저장되었습니다", QMessageBox.Icon.Information)
    
    def toggle_thumbnail(self):
        """썸네일 ON/OFF 토글"""
        is_on = self.thumbnail_toggle_btn.isChecked()
        self.config["use_thumbnail"] = is_on
        self.thumbnail_toggle_btn.setText("ON" if is_on else "OFF")
        self.update_thumbnail_button_style()
        if is_on:
            self._update_settings_status("🖼️ 썸네일 기능 ON, 🎬 동영상 기능 ON")
        else:
            self._update_settings_status("🖼️ 썸네일 기능 OFF, 🎬 동영상 기능 OFF")
        self.save_config_file()
        self.update_status_display()
    
    def update_thumbnail_button_style(self):
        """썸네일 토글 버튼 스타일 업데이트"""
        is_on = self.thumbnail_toggle_btn.isChecked()
        if is_on:
            self.thumbnail_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {NAVER_GREEN};
                    border: none;
                    border-radius: 6px;
                    color: white;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    background-color: {NAVER_GREEN_HOVER};
                }}
            """)
        else:
            self.thumbnail_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #CCCCCC;
                    border: none;
                    border-radius: 6px;
                    color: white;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    background-color: #BBBBBB;
                }}
            """)
    
    def toggle_time_selection(self):
        """더 이상 사용하지 않는 함수 (호환성 유지)"""
        pass
    
    def save_link_settings(self):
        """링크 설정 저장"""
        self.config["use_external_link"] = self.use_link_checkbox.isChecked()
        self.config["external_link"] = self.link_url_entry.text().strip()
        self.config["external_link_text"] = self.link_text_entry.text().strip()
        status = "ON" if self.use_link_checkbox.isChecked() else "OFF"
        self._update_settings_status(f"🔗 외부 링크 설정이 저장되었습니다 (상태: {status})")
        self.save_config_file()
        self._show_auto_close_message(f"✅ 외부 링크 설정이 저장되었습니다 ({status})", QMessageBox.Icon.Information)

    def _sync_related_posts_title(self, text):
        """관련 글 종류 선택 시 제목 기본값 동기화"""
        if not text:
            return
        current = self.related_posts_title_entry.text().strip()
        if not current or current in ("최신 글", "인기 글", "함께 보면 좋은 글"):
            self.related_posts_title_entry.setText(text)
    
    def save_related_posts_settings(self):
        """함께 보면 좋은 글 설정 저장"""
        title = self.related_posts_title_entry.text().strip()
        blog_address = normalize_blog_address(self.blog_address_entry.text().strip())
        mode_text = "인기 글" if self.related_posts_mode_popular.isChecked() else "최신 글"
        mode_value = "popular" if self.related_posts_mode_popular.isChecked() else "latest"

        if not title:
            title = mode_text if mode_text else "함께 보면 좋은 글"
            self.related_posts_title_entry.setText(title)

        self.config["blog_address"] = blog_address
        self.config["related_posts_title"] = title
        self.config["related_posts_mode"] = mode_value
        
        status_msg = f"📚 '함께 보면 좋은 글' 설정이 저장되었습니다"
        if blog_address:
            status_msg += f"\n   블로그: {blog_address}"
            status_msg += f"\n   모드: {mode_text}"
        else:
            status_msg += "\n   (블로그 주소 미설정 - 기능 비활성화)"
        
        self._update_settings_status(status_msg)
        self.save_config_file()
    

    def start_posting(self, is_first_start=True):
        """포스팅 시작"""
        self.stop_requested = False
        
        if self.is_running:
            # 이미 실행 중이면 자동 재시작 (카운트다운 후)
            pass
        else:
            # 첫 시작
            is_first_start = True
            self.is_running = True
            self.is_paused = False
            
            # 버튼 상태 변경
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
        
        # 설정 검증 (Gemini 전용)
        ai_model = "gemini"
        api_key = self.gemini_api_entry.text()
        gemini_mode = self.config.get("gemini_mode", "api")
        
        if gemini_mode != "web" and not api_key:
            self.show_message("⚠️ 경고", "Gemini API 키를 입력해주세요!", "warning")
            return
        if not self.naver_id_entry.text() or not self.naver_pw_entry.text():
            self.show_message("⚠️ 경고", "네이버 로그인 정보를 입력해주세요!", "warning")
            return
        
        # 발행 간격 설정
        try:
            interval = int(self.interval_entry.text())
        except:
            interval = 10
        
        wait_interval = interval
        
        # 진행 상태 업데이트
        if is_first_start:
            self.update_progress_status("🚀 포스팅 프로세스를 시작합니다...")
            print("🚀 포스팅 프로세스를 시작합니다...")
        else:
            self.update_progress_status("🔄 다음 포스팅을 시작합니다...")
            print("🔄 다음 포스팅을 시작합니다...")
        
        # 자동화 바로 시작 (별도 스레드)
        def run_automation():
            # 무한 반복 (is_running이 False가 될 때까지)
            is_first_run_flag = is_first_start
            
            while self.is_running and not self.stop_requested:
                try:
                    if not is_first_run_flag:
                        print("🔄 [DEBUG] 다음 포스팅 시작")
                    
                    external_link = self.link_url_entry.text() if self.use_link_checkbox.isChecked() else ""
                    external_link_text = self.link_text_entry.text() if self.use_link_checkbox.isChecked() else ""
                    
                    # 첫 실행시 또는 인스턴스가 없을 때 자동화 인스턴스 생성
                    if is_first_run_flag or not self.automation:
                        # 블로그 주소 처음 (아이디만 있으면 전체 URL로 변환)
                        blog_address = self.config.get("blog_address", "")
                        related_posts_title = self.config.get("related_posts_title", "함께 보면 좋은 글")
                        posting_method = "home" if self.config.get("posting_method") == "home" else "search"

                        self.automation = NaverBlogAutomation(
                            naver_id=self.naver_id_entry.text(),
                            naver_pw=self.naver_pw_entry.text(),
                            api_key=api_key,
                            ai_model=ai_model,
                            posting_method=posting_method,
                            theme="",
                            open_type="전체공개",
                            external_link=external_link,
                            external_link_text=external_link_text,
                            publish_time="now",
                            scheduled_hour="00",
                            scheduled_minute="00",
                            related_posts_title=related_posts_title,
                            related_posts_mode=self.config.get("related_posts_mode", "latest"),
                            blog_address=blog_address,
                            callback=self.log_message,
                            config=self.config
                        )
                        
                        if not is_first_run_flag:
                            print("⚠️ 자동화 인스턴스가 없어서 재생성했습니다")
                    
                    # 자동화 실행
                    if not is_first_run_flag:
                        print(f"🔄 [DEBUG] automation.run(is_first_run={is_first_run_flag}) 호출")
                    
                    result = self.automation.run(is_first_run=is_first_run_flag)
                    
                    # 첫 실행 플래그 해제 (두 번째부터는 False)
                    is_first_run_flag = False
                    
                    # 실패 시 원인 구분하여 처리
                    if result is False:
                        if self.stop_requested or not self.is_running or not self.automation:
                            break
                        # 키워드가 없어서 실패한 경우
                        if not self.automation.current_keyword:
                            self.update_progress_status("⏹️ 키워드가 없어 프로그램을 중지합니다.")
                            print("⏹️ 키워드 부족으로 자동 중지됨")
                            
                            # 중지 처리
                            self.is_running = False
                            self.start_btn.setEnabled(True)
                            self.stop_btn.setEnabled(False)
                            self.pause_btn.setEnabled(False)
                            self.resume_btn.setEnabled(False)
                            
                            # 키워드 소진 알림
                            QTimer.singleShot(100, lambda: self.show_message(
                                "✅ 완료",
                                "모든 키워드의 포스팅이 완료되었습니다!",
                                "info"
                            ))
                            break
                        else:
                            # 키워드는 있지만 다른 이유로 실패 (발행 실패 등)
                            self.update_progress_status("⚠️ 포스팅 중 오류가 발생했습니다.")
                            print("⚠️ 포스팅 실패 - 키워드는 유지되고 다음 시도에서 재사용됩니다")
                            break
                    
                    self.update_progress_status("✅ 포스팅이 완료되었습니다!")
                    print("✅ 포스팅이 완료되었습니다!")
                    
                    # UI 상태 갱신 (키워드 개수 등 실시간 업데이트)
                    QTimer.singleShot(0, lambda: self.update_status_display())
                    
                    # 남은 키워드 수 확인 및 30개 미만 경고
                    try:
                        keywords_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setting", "keywords.txt")
                        with open(keywords_file, 'r', encoding='utf-8') as f:
                            remaining_keywords = [line.strip() for line in f if line.strip()]
                            keyword_count = len(remaining_keywords)
                            
                            if keyword_count < 30 and keyword_count > 0:
                                # 30개 미만 경고창
                                QTimer.singleShot(100, lambda: self.show_message(
                                    "⚠️ 경고",
                                    f"키워드가 {keyword_count}개 남았습니다!\n\n키워드를 추가하시기 바랍니다.",
                                    "warning"
                                ))
                            elif keyword_count == 0:
                                # 키워드 소진 시 자동 중지
                                self.update_progress_status("✅ 모든 키워드 포스팅 완료!")
                                self.is_running = False
                                self.start_btn.setEnabled(True)
                                self.stop_btn.setEnabled(False)
                                self.pause_btn.setEnabled(False)
                                self.resume_btn.setEnabled(False)
                                
                                QTimer.singleShot(100, lambda: self.show_message(
                                    "✅ 완료",
                                    "모든 키워드의 포스팅이 완료되었습니다!",
                                    "info"
                                ))
                                break
                    except Exception as e:
                        print(f"⚠️ 키워드 파일 확인 실패: {e}")
                    
                    # 다음 포스팅 대기
                    if self.is_running and not self.is_paused:
                        self.update_progress_status("🔄 2초 후 다음 포스팅을 시작합니다...")
                        print("🔄 2초 후 다음 포스팅을 시작합니다...")
                        time.sleep(2)
                        # 루프 계속 (다시 while 조건 체크 후 automation.run 실행)
                        
                except Exception as e:
                    if self.stop_requested:
                        break
                    self.update_progress_status(f"❌ 오류: {e}")
                    print(f"❌ 자동화 오류: {e}")
                    traceback.print_exc()
                    # 오류 발생 시에만 중지
                    self.is_running = False
                    self.stop_btn.setEnabled(False)
                    self.pause_btn.setEnabled(False)
                    self.start_btn.setEnabled(True)
                    break
        
        thread = threading.Thread(target=run_automation, daemon=True)
        thread.start()
    
    def stop_posting(self):
        """포스팅 정지"""
        self.is_running = False
        self.is_paused = False
        self.stop_requested = True
        
        # 실행 중인 자동화 인스턴스 정지
        if self.automation:
            self.automation.should_stop = True
            self.automation.should_pause = False
            self.update_progress_status("⏹️ 포스팅 중지 요청됨...")
            print("⏹️ 포스팅 중지 요청됨...")
            # 브라우저 자원 해제 시도
            try:
                if self.automation.driver:
                    self.automation.close()
            except:
                pass
            self.automation = None  # 객체 초기화하여 다음 시작시 새로 생성되도록
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.update_progress_status("⏹️ 포스팅을 정지했습니다.")
        print("⏹️ 포스팅을 정지했습니다.")
        # UI 상태 갱신 (키워드 개수 등)
        self.update_status_display()
    
    def pause_posting(self):
        """포스팅 일시정지"""
        self.is_paused = True
        if self.countdown_timer.isActive():
            self.countdown_timer.stop()
        if self.automation:
            self.automation.should_pause = True
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(True)
        self.show_message("⏸️ 일시정지", "포스팅을 일시정지했습니다.", "info")

    def resume_posting(self):
        """포스팅 재개"""
        self.is_paused = False
        if self.automation:
            self.automation.should_pause = False
        if self.countdown_seconds > 0 and not self.countdown_timer.isActive():
            self.countdown_timer.start(1000)
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)
        self.show_message("▶️ 재개", "포스팅을 재개합니다.", "info")
    
    def start_countdown(self, minutes):
        """발행 간격 카운트다운 시작"""
        self.countdown_seconds = minutes * 60
        self.countdown_timer.start(1000)  # 1초마다 업데이트
    
    def stop_countdown(self):
        """발행 간격 카운트다운 중지"""
        self.countdown_timer.stop()
        self.countdown_seconds = 0
        try:
            interval = int(self.interval_entry.text())
        except:
            interval = 10
        self.interval_label.setText(f"⏱️ 발행 간격: {interval}분")
    
    def _update_countdown(self):
        """카운트다운 업데이트 (1초마다 호출)"""
        if self.countdown_seconds > 0:
            self.countdown_seconds -= 1
            minutes = self.countdown_seconds // 60
            seconds = self.countdown_seconds % 60
            self.interval_label.setText(f"⏱️ 남은 시간: {minutes:02d}:{seconds:02d}")
        else:
            self.countdown_timer.stop()
            try:
                interval = int(self.interval_entry.text())
            except:
                interval = 10
            self.interval_label.setText(f"⏱️ 발행 간격: {interval}분")
            
            # 카운트다운 완료 후 자동으로 다음 포스팅 시작
            if self.is_running and not self.is_paused:
                self.update_progress_status("⏰ 발행 간격 완료 - 다음 포스팅을 시작합니다")
                print("⏰ 발행 간격 완료 - 다음 포스팅을 시작합니다")
                # start_posting()을 호출하지 않고 직접 실행 (is_first_start=False)
                self.start_posting(is_first_start=False)
    
    def log_message(self, message):
        """로그 메시지 출력 및 진행 상태 업데이트 (중복 방지)"""
        # 키워드 관련 특수 메시지 처리 (알림창 없이 로그만 표시)
        if message.startswith("KEYWORD_"):
            # KEYWORD_EMPTY, KEYWORD_LOW, KEYWORD_FILE_MISSING 등은 로그에만 표시
            print(f"📋 키워드 상태: {message}")
            return
        
        # 중복 메시지 방지
        if not hasattr(self, '_last_log_message') or self._last_log_message != message:
            self._last_log_message = message
            
            # 진행 현황을 실시간으로 업데이트
            self.update_progress_status(message)
            
            # 터미널에도 출력 (이미 _update_status에서 print 됨)
    
    def update_progress_status(self, message):
        """진행 현황 로그 메시지 추가 (스레드 안전)"""
        # 시그널을 통해 메인 스레드에서 실행
        self.progress_signal.emit(message)
    
    def _update_progress_status_safe(self, message):
        """진행 현황 로그 메시지 추가 (메인 스레드에서 실행)"""
        try:
            # 기존 로그에 새 메시지 추가 (중복 방지 강화)
            current_log = self.log_label.text()
            
            # 초기 상태
            if current_log == "⏸️ 대기 중...":
                new_log = message
            else:
                lines = current_log.split("\n")
                last_message = lines[-1].strip() if lines else ""
                
                # 완전히 동일한 메시지는 무시
                if last_message == message.strip():
                    return
                
                # 같은 단계의 진행 상황 업데이트 (이모지로 판단)
                # 예: "✍️ 작성 중... (10/100줄)" → "✍️ 작성 중... (20/100줄)"
                last_emoji = last_message.split()[0] if last_message else ""
                current_emoji = message.split()[0] if message else ""
                
                if last_emoji == current_emoji and last_emoji in ["✍️", "⏰", "🔄", "📋", "🤖", "🌐", "🔐"]:
                    # 같은 단계의 세부 진행 상황은 마지막 줄을 덮어씀
                    # 단, "완료" 메시지는 덮어쓰지 않음
                    if "완료" not in last_message and "성공" not in last_message:
                        lines[-1] = message
                        new_log = "\n".join(lines)
                    else:
                        new_log = current_log + "\n" + message
                else:
                    # 다른 단계의 메시지는 새 줄로 추가
                    new_log = current_log + "\n" + message
            
            self.log_label.setText(new_log)
            
            # 사용자가 스크롤을 올린 경우 자동 스크롤 방지
            try:
                scroll_area = getattr(self, "log_scroll", None)
                if scroll_area is None:
                    widget = self.log_label
                    while widget:
                        if isinstance(widget, QScrollArea):
                            scroll_area = widget
                            break
                        widget = widget.parent()

                if scroll_area:
                    bar = scroll_area.verticalScrollBar()
                    at_bottom = bar.value() >= bar.maximum() - 5
                    if at_bottom:
                        bar.setValue(bar.maximum())
            except Exception:
                pass  # 스크롤 실패는 무시
        except Exception as e:
            print(f"로그 업데이트 오류: {e}")
            print(f"⚠️ 진행 상태 업데이트 오류: {e}")
    
    def show_keyword_empty_dialog(self):
        """키워드 없음 다이얼로그 표시 (메인 스레드)"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("키워드 없음")
        msg.setText("키워드가 모두 소진되었습니다.")
        msg.setInformativeText("setting/keywords.txt 파일에 키워드를 추가해주세요.\n\n프로그램을 종료합니다.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # 글자 크기 줄이기
        msg.setStyleSheet("""
            QMessageBox {
                font-size: 11px;
            }
            QMessageBox QLabel {
                font-size: 11px;
            }
        """)
        
        msg.exec()
    
    def show_keyword_low_dialog(self, keyword_count):
        """키워드 부족 다이얼로그 표시 (메인 스레드)"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("키워드 부족 경고")
        msg.setText(f"키워드가 {keyword_count}개 남았습니다!")
        msg.setInformativeText("30개 미만으로 키워드가 부족합니다.\nsetting/keywords.txt 파일에 키워드를 추가해주세요.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # 글자 크기 줄이기
        msg.setStyleSheet("""
            QMessageBox {
                font-size: 11px;
            }
            QMessageBox QLabel {
                font-size: 11px;
            }
        """)
        
        msg.exec()
    
    def show_keyword_file_missing_dialog(self):
        """키워드 파일 없음 다이얼로그 표시 (메인 스레드)"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("파일 없음")
        msg.setText("keywords.txt 파일이 없습니다.")
        msg.setInformativeText("setting/keywords.txt 파일을 만들고 키워드를 추가해주세요.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # 글자 크기 줄이기
        msg.setStyleSheet("""
            QMessageBox {
                font-size: 11px;
            }
            QMessageBox QLabel {
                font-size: 11px;
            }
        """)
        
        msg.exec()
    
    def mousePressEvent(self, event):
        """마우스 클릭 시 드래그 시작"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """마우스 이동 시 창 이동"""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """마우스 릴리즈 시 드래그 종료"""
        self.drag_position = None
        event.accept()


if __name__ == "__main__":
    # multiprocessing 콘솔창 방지
    import multiprocessing
    multiprocessing.freeze_support()
    
    # QApplication 최우선 생성 (스플래시 화면을 가장 먼저 띄우기 위해)
    app = QApplication(sys.argv)
    
    # Windows 작업 표시줄 아이콘 설정 (AppUserModelID)
    if sys.platform == 'win32':
        try:
            myappid = 'naver.autoblog.v5.1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except:
            pass
    
    # 애플리케이션 아이콘 설정
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    icon_path = os.path.join(base_dir, "setting", "david153.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 스플래시 스크린 즉시 생성 및 표시
    splash_pix = QPixmap(400, 200)
    splash_pix.fill(QColor("#03C75A"))
    
    painter = QPainter(splash_pix)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("맑은 고딕", 16, QFont.Weight.Bold))
    painter.drawText(splash_pix.rect(), Qt.AlignmentFlag.AlignCenter, 
                    "프로그램 실행 중이니,\n잠시만 기다려주세요 :)")
    painter.end()
    
    splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()  # 즉시 화면에 표시
    
    # 1. 라이선스 체크 (Google Spreadsheet 기반)
    license_manager = LicenseManager()
    is_valid, message = license_manager.verify_license()
    
    if not is_valid:
        splash.close()  # 스플래시 닫기
        # GUI 에러 메시지 표시
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QWidget, QHBoxLayout
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        
        # 커스텀 다이얼로그 생성
        dialog = QDialog()
        dialog.setWindowTitle("🔒 프로그램 사용 권한")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(350)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # 경고 아이콘과 제목
        warning_container = QWidget()
        warning_layout = QHBoxLayout(warning_container)
        warning_layout.setContentsMargins(0, 0, 0, 0)
        warning_layout.setSpacing(15)
        
        warning_icon = QLabel("⚠")
        warning_icon.setFont(QFont("Segoe UI Emoji", 36))
        warning_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_layout.addWidget(warning_icon)
        
        warning_text = QLabel("등록되지 않은 사용자입니다.")
        warning_text.setFont(QFont("맑은 고딕", 16, QFont.Weight.Bold))
        warning_text.setStyleSheet("color: #D32F2F;")
        warning_layout.addWidget(warning_text)
        warning_layout.addStretch()
        
        layout.addWidget(warning_container)
        
        # IP 정보 카드
        ip_card = QWidget()
        ip_card.setStyleSheet("""
            QWidget {
                background-color: #FFF3E0;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        ip_layout = QVBoxLayout(ip_card)
        ip_layout.setSpacing(10)
        
        machine_id_label = QLabel(f"현재 머신 ID: {license_manager.get_machine_id()}")
        machine_id_label.setFont(QFont("맑은 고딕", 14, QFont.Weight.Bold))
        machine_id_label.setStyleSheet("color: #E65100; background: transparent; padding: 0;")
        machine_id_label.setWordWrap(True)
        ip_layout.addWidget(machine_id_label)
        
        info_label = QLabel("판매자에게 위 머신 ID를 알려주세요.")
        info_label.setFont(QFont("맑은 고딕", 12))
        info_label.setStyleSheet("color: #424242; background: transparent; padding: 0;")
        ip_layout.addWidget(info_label)
        
        layout.addWidget(ip_card)
        
        # 안내 카드
        guide_card = QWidget()
        guide_card.setStyleSheet("""
            QWidget {
                background-color: #E3F2FD;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setSpacing(8)
        
        guide_title = QLabel("📋 판매자에게 다음 정보를 전달하세요")
        guide_title.setFont(QFont("맑은 고딕", 11, QFont.Weight.Bold))
        guide_title.setStyleSheet("color: #1565C0; background: transparent; padding: 0;")
        guide_layout.addWidget(guide_title)
        
        # 머신 ID와 복사 버튼
        machine_row = QWidget()
        machine_row.setStyleSheet("background: transparent;")
        machine_row_layout = QHBoxLayout(machine_row)
        machine_row_layout.setContentsMargins(0, 0, 0, 0)
        machine_row_layout.setSpacing(15)
        
        machine_info = QLabel(f"🔑 머신 ID    {license_manager.get_machine_id()}")
        machine_info.setFont(QFont("맑은 고딕", 10))
        machine_info.setStyleSheet("color: #424242; background: transparent; padding: 0;")
        machine_info.setWordWrap(True)
        machine_row_layout.addWidget(machine_info)
        
        copy_btn = QPushButton("📋 복사")
        copy_btn.setFont(QFont("맑은 고딕", 9, QFont.Weight.Bold))
        copy_btn.setMinimumHeight(28)
        copy_btn.setMinimumWidth(70)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        
        def copy_machine_id():
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(license_manager.get_machine_id())
            copy_btn.setText("✓ 복사됨")
            copy_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 5px 10px;
                }
            """)
        
        copy_btn.clicked.connect(copy_machine_id)
        machine_row_layout.addWidget(copy_btn)
        machine_row_layout.addStretch()
        
        guide_layout.addWidget(machine_row)
        
        layout.addWidget(guide_card)
        
        # 참고 메시지
        note_label = QLabel("💡 참고: 위 머신 ID를 판매자에게 보내면 프로그램 사용 권한을 등록할 수 있습니다.\n(와이파이 변경, 재부팅 시에도 머신 ID는 변경되지 않습니다)")
        note_label.setFont(QFont("맑은 고딕", 9))
        note_label.setStyleSheet("color: #757575;")
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
        
        layout.addStretch()
        
        # 확인 버튼
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch()
        
        ok_button = QPushButton("확인")
        ok_button.setFont(QFont("맑은 고딕", 11, QFont.Weight.Bold))
        ok_button.setMinimumWidth(120)
        ok_button.setMinimumHeight(45)
        ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 30px;
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
        
        layout.addWidget(button_container)
        
        dialog.setLayout(layout)
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
            }
        """)
        
        dialog.exec()
        
        sys.exit(1)
    
    # 전역 예외 처리기 설정
    def handle_exception(exc_type, exc_value, exc_traceback):
        """전역 예외 처리기"""
        if issubclass(exc_type, KeyboardInterrupt):
            # Ctrl+C 중단은 무시
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # 오류 상세 정보 수집
        error_details = {
            "type": exc_type.__name__,
            "message": str(exc_value),
            "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "python_version": platform.python_version(),
            "os": platform.platform(),
        }
        
        # 콘솔에 출력
        print("\n" + "="*80)
        print("❌ 심각한 오류 발생!")
        print("="*80)
        print(error_details["traceback"])
        print("="*80)
        
        # GUI가 생성되어 있으면 다이얼로그 표시
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QApplication
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QFont
            
            # QApplication이 있는지 확인
            if QApplication.instance() is not None:
                error_dialog = QDialog()
                error_dialog.setWindowTitle("❌ 심각한 오류 발생")
                error_dialog.setMinimumSize(700, 500)
                error_dialog.setStyleSheet("""
                    QDialog {
                        background-color: white;
                    }
                    QLabel {
                        color: #1a1a1a;
                    }
                    QTextEdit {
                        background-color: #f5f5f5;
                        color: #1a1a1a;
                        border: 2px solid #e0e0e0;
                        border-radius: 8px;
                        padding: 10px;
                        font-family: 'Consolas', 'Courier New', monospace;
                        font-size: 11px;
                        selection-background-color: #cfe9d9;
                        selection-color: #1a1a1a;
                    }
                    QPushButton {
                        background-color: #03c75a;
                        color: white;
                        border: none;
                        border-radius: 8px;
                        padding: 10px 20px;
                        font-size: 13px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #02b350;
                    }
                """)
                
                layout = QVBoxLayout(error_dialog)
                layout.setSpacing(15)
                layout.setContentsMargins(20, 20, 20, 20)
                
                # 제목
                title_label = QLabel("🛑 프로그램 오류 발생")
                title_label.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
                title_label.setStyleSheet("color: #d32f2f;")
                layout.addWidget(title_label)
                
                # 오류 설명
                desc_label = QLabel(
                    f"🔴 오류 종류: {error_details['type']}\n"
                    f"📝 메시지: {error_details['message']}\n"
                    f"⏰ 발생 시간: {error_details['timestamp']}\n\n"
                    f"👇 아래 내용을 복사하여 제작자에게 전달해주세요."
                )
                desc_label.setFont(QFont("Malgun Gothic", 11))
                desc_label.setWordWrap(True)
                layout.addWidget(desc_label)
                
                # 제작자 전달용 내용
                report_content = (
                    f"=" * 80 + "\n"
                    f"🚨 NAVER BLOG AUTO POSTING ERROR REPORT\n"
                    f"=" * 80 + "\n\n"
                    f"📅 발생 시간: {error_details['timestamp']}\n"
                    f"💻 프로그램 버전: v5.1\n"
                    f"🐍 Python 버전: {error_details['python_version']}\n"
                    f"💾 운영체제: {error_details['os']}\n\n"
                    f"❌ 오류 종류: {error_details['type']}\n"
                    f"📝 오류 메시지:\n{error_details['message']}\n\n"
                    f"📄 상세 스택 트레이스:\n"
                    f"{error_details['traceback']}\n"
                    f"=" * 80
                )
                
                report_text = QTextEdit()
                report_text.setPlainText(report_content)
                report_text.setReadOnly(True)
                report_text.setMinimumHeight(250)
                layout.addWidget(report_text)
                
                # 버튼 영역
                button_layout = QHBoxLayout()
                button_layout.setSpacing(10)
                
                copy_btn = QPushButton("📋 오류 내용 복사")
                copy_btn.clicked.connect(lambda: pyperclip.copy(report_content))
                copy_btn.clicked.connect(lambda: copy_btn.setText("✅ 복사 완료!"))
                button_layout.addWidget(copy_btn)
                
                close_btn = QPushButton("프로그램 종료")
                close_btn.clicked.connect(error_dialog.accept)
                button_layout.addWidget(close_btn)
                
                layout.addLayout(button_layout)
                
                error_dialog.exec()
        except Exception as e:
            print(f"오류 다이얼로그 표시 실패: {e}")
        
        # 기본 예외 처리기 호출
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    # 전역 예외 처리기 등록
    sys.excepthook = handle_exception
    
    # UTF-8 환경 확인
    print(f"✅ 시스템 인코딩: {sys.getdefaultencoding()}")
    print(f"✅ 파일 시스템 인코딩: {sys.getfilesystemencoding()}")
    print(f"✅ {message}")
    
    # 라이선스 정보 출력
    license_info = license_manager.get_license_info()
    if license_info.get("name"):
        print(f"✅ 구매자: {license_info['name']}")
    print(f"✅ 머신 ID: {license_info['machine_id'][:32]}...")
    print(f"✅ MAC 주소: {license_info.get('mac_address', 'N/A')}")
    
    # 메인 윈도우 생성
    window = NaverBlogGUI()
    
    # 스플래시 화면 닫고 메인 윈도우 최대화 표시
    splash.finish(window)
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    
    sys.exit(app.exec())
