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
from openai import OpenAI
import time
import os
import traceback
import platform
from datetime import datetime
from license_check import LicenseManager
from PIL import Image, ImageDraw, ImageFont
import random
import pyautogui

# moviepy import (PyInstaller 감지용 - moviepy 2.x 호환)
try:
    # moviepy 2.x 방식
    from moviepy import ImageClip
    import moviepy
    import moviepy.video.io.VideoFileClip
    import moviepy.video.VideoClip
    import imageio
    import imageio_ffmpeg
    print("✅ moviepy 로드 성공")
except ImportError as e:
    print(f"⚠️ moviepy 로드 실패: {e}")
    ImageClip = None


class NaverBlogAutomation:
    """네이버 블로그 자동 포스팅 클래스"""
    
    def __init__(self, naver_id, naver_pw, api_key, ai_model="gemini", theme="일상", 
                 open_type="전체공개", external_link=None, external_link_text="더 알아보기",
                 publish_time="즉시발행", scheduled_hour=12, scheduled_minute=0, 
                 related_posts_title="함께 보면 좋은 글", blog_address="",
                 callback=None, config=None):
        """초기화 함수"""
        self.naver_id = naver_id
        self.naver_pw = naver_pw
        self.api_key = api_key
        self.ai_model = ai_model
        self.theme = theme
        self.open_type = open_type
        self.external_link = external_link
        self.external_link_text = external_link_text
        self.publish_time = publish_time
        self.scheduled_hour = scheduled_hour
        self.scheduled_minute = scheduled_minute
        self.related_posts_title = related_posts_title
        self.blog_address = blog_address
        self.callback = callback
        self.config = config or {}  # config 저장
        self.driver: webdriver.Chrome | None = None
        self.should_stop = False  # 정지 플래그
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
        
        # AI 모델 설정
        if ai_model == "gemini":
            genai.configure(api_key=api_key)  # type: ignore
            self.model = genai.GenerativeModel('gemini-2.5-flash-lite')  # type: ignore
        elif ai_model == "gpt":
            self.client = OpenAI(api_key=api_key)
            self.model = "gpt-4o"
        
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
    
    def generate_content_with_ai(self):
        """AI를 사용하여 블로그 글 생성 (Gemini 또는 GPT)"""
        try:
            model_name = "Gemini 2.5 Flash-Lite" if self.ai_model == "gemini" else "GPT-4o"
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
- **가능한 한 많은 토큰을 사용하여 길게 작성하세요**
"""
                print(f"📄 프롬프트에 키워드 '{keyword}' 삽입 완료")
            else:
                self._update_status("❌ 프롬프트 파일을 찾을 수 없습니다")
                return None, None
            
            # AI 모델에 따라 호출
            self._update_status(f"🔄 AI에게 글 생성 요청 중... (모델: {model_name})")
            if self.ai_model == "gemini":
                response = self.model.generate_content(full_prompt)  # type: ignore
                content = response.text  # type: ignore
            elif self.ai_model == "gpt":
                response = self.client.chat.completions.create(
                    model=self.model,  # type: ignore
                    messages=[
                        {"role": "system", "content": "당신은 블로그 글 작성 전문가입니다. 사용자가 제공하는 프롬프트의 모든 지시사항을 정확히 준수하여 글을 작성하세요. 특히 제목 형식은 반드시 '키워드, 후킹문구' 형식을 지켜야 합니다. 가능한 한 상세하고 길게 작성하세요."},
                        {"role": "user", "content": full_prompt}
                    ],
                    max_tokens=4000  # 최대 토큰 수 증가
                )
                content = response.choices[0].message.content
            
            self._update_status("📝 AI 응답 처리 중...")
            
            # 제목과 본문 분리
            lines = content.strip().split('\n')
            if len(lines) < 2:
                self._update_status("❌ AI 응답 형식 오류")
                return None, None
            
            title = lines[0].strip()
            body_lines = [line for line in lines[1:] if line.strip()]
            body = '\n'.join(body_lines)
            
            # AI 생성 글을 result 폴더에 저장
            try:
                result_folder = os.path.join("setting", "result")
                os.makedirs(result_folder, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
            
        except Exception as e:
            self._report_error("AI 글 생성", e)
            return None, None
    
    def create_thumbnail(self, title):
        """setting/image 폴더의 jpg를 배경으로 300x300 썸네일 생성"""
        try:
            # 썸네일 기능이 OFF인 경우 None 반환
            if not self.config.get("use_thumbnail", True):
                self._update_status("⚪ 썸네일 기능 OFF - 스킵")
                return None
            
            self._update_status("🎨 썸네일 생성 중...")
            
            # setting/image 폴더의 jpg 파일 찾기
            image_folder = os.path.join(self.data_dir, "setting", "image")
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
            except ImportError as import_error:
                raise ImportError(f"moviepy 라이브러리를 import할 수 없습니다: {str(import_error)}")
            
            if not thumbnail_path or not os.path.exists(thumbnail_path):
                raise FileNotFoundError(f"썸네일 이미지를 찾을 수 없습니다: {thumbnail_path}")
            
            self._update_status("🎬 동영상 생성 시작...")
            print(f"VIDEO: Creating video from {thumbnail_path}")
            
            # 결과 파일 경로 설정
            result_folder = os.path.join("setting", "result")
            os.makedirs(result_folder, exist_ok=True)
            
            # 파일명 생성 (썸네일과 동일한 이름으로)
            base_name = os.path.splitext(os.path.basename(thumbnail_path))[0]
            video_filename = f"{base_name}.mp4"
            video_filepath = os.path.join(result_folder, video_filename)
            
            print(f"VIDEO: Saving to {video_filepath}")
            
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
            print(f"VIDEO: Successfully created {video_filepath}")
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
            if not self.blog_address:
                self._update_status("⚠️ 블로그 주소가 설정되지 않았습니다")
                return []
            
            self._update_status(f"🔍 블로그 크롤링 시작: {self.blog_address}")
            
            posts = []
            
            # 현재 창 핸들 저장
            original_window = self.driver.current_window_handle
            
            # 새 탭에서 블로그 열기
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            try:
                # 블로그 접속
                self.driver.get(self.blog_address)
                time.sleep(3)
                
                # 최신글 목록에서 링크 찾기 (여러 선택자 시도)
                post_selectors = [
                    "a.post_tit",  # 일반적인 포스트 제목 링크
                    "a.pcol1",  # 다른 스타일의 블로그
                    ".blog2_series a",  # 시리즈형 블로그
                    "a[href*='PostView']",  # PostView가 포함된 모든 링크
                    "a[href*='logNo=']",  # logNo가 포함된 모든 링크
                ]
                
                post_elements = []
                for selector in post_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements and len(elements) >= 1:
                            self._update_status(f"🔍 셀렉터 '{selector}'로 {len(elements)}개 발견")
                            # 충분한 개수가 발견되면 사용
                            post_elements = elements[:10]  # 여유있게 10개까지 찾음
                            break
                    except Exception as e:
                        self._update_status(f"⚠️ 셀렉터 '{selector}' 실패: {str(e)[:30]}")
                        continue
                
                if not post_elements:
                    self._update_status("⚠️ 블로그 포스트를 찾을 수 없습니다")
                    return []
                
                self._update_status(f"📋 총 {len(post_elements)}개 요소 발견, 최신 3개 추출 시작")
                
                # 각 포스트의 URL과 제목 수집
                for idx, element in enumerate(post_elements):
                    if len(posts) >= 3:  # 3개 수집하면 중단
                        break
                        
                    try:
                        post_title = element.text.strip()
                        post_url = element.get_attribute("href")
                        
                        # 제목과 URL이 유효한지 확인
                        if not post_title or not post_url:
                            self._update_status(f"⚠️ 요소 {idx+1}: 제목 또는 URL 없음 - 스킵")
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
                self.driver.close()
                self.driver.switch_to.window(original_window)
            
            self._update_status(f"✅ 총 {len(posts)}개의 최신글 수집 완료")
            return posts[:3]  # 최대 3개만 반환
            
        except Exception as e:
            self._report_error("블로그 크롤링", e, show_traceback=False)
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
    
    def write_post(self, title, content, thumbnail_path=None, video_path=None, is_first_post=True):
        """블로그 글 작성"""
        try:
            # 첫 포스팅인 경우 블로그 홈으로 바로 이동
            if is_first_post:
                self._update_status("📝 첫 포스팅: 블로그 홈으로 이동 중...")
                self.driver.get("https://section.blog.naver.com/BlogHome.naver?directoryNo=0&currentPage=1&groupId=0")
                time.sleep(3)
                
                # 블로그 주소가 설정되어 있으면 최신글 크롤링
                if self.blog_address:
                    self._update_status("🔍 블로그 최신글 크롤링 시작...")
                    latest_posts = self.crawl_latest_blog_posts()
                    if latest_posts:
                        self.save_latest_posts_to_file(latest_posts)
                        self._update_status(f"✅ {len(latest_posts)}개 최신글 저장 완료")
                    else:
                        self._update_status("⚠️ 최신글 크롤링 실패 - '함께 보면 좋은 글' 섹션 생략")
                

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
                            time.sleep(3)
                            self._update_status("✅ 블로그 홈에서 글쓰기 버튼 클릭 성공")
                            
                            # 새 창이 열렸다면 전환
                            if len(self.driver.window_handles) > 1:
                                self.driver.switch_to.window(self.driver.window_handles[-1])
                                time.sleep(2)
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
                    time.sleep(2)
            
            # mainFrame으로 전환
            self._update_status("🖼️ 에디터 프레임으로 전환 중...")
            try:
                mainframe = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "mainFrame"))
                )
                self.driver.switch_to.frame(mainframe)
                time.sleep(1)
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
                time.sleep(1)
            except:
                pass
            
            # 도움말 패널 닫기
            self._update_status("📚 도움말 패널 확인 중...")
            try:
                help_close = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-help-panel-close-button"))
                )
                help_close.click()
                self._update_status("✅ 도움말 닫기 완료")
                time.sleep(1)
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
                time.sleep(1)
                
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
                time.sleep(0.5)
                
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
                    if self.should_stop:
                        self._update_status("⏹️ 사용자가 포스팅을 중지했습니다.")
                        return False
                    
                    if line.strip():
                        current_line += 1
                        
                        # ActionChains로 직접 타이핑
                        ActionChains(self.driver).send_keys(line).perform()
                        time.sleep(0.1)
                        # 줄바꿈
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        time.sleep(0.1)
                
                # 서론 작성 후 Enter 한번 더
                actions = ActionChains(self.driver)
                actions.send_keys(Keys.ENTER).perform()
                time.sleep(0.3)
                
                # 2. 외부 링크 삽입 (설정된 경우)
                if use_external_link:
                    self._update_status("🔗 외부 링크 삽입 중...")
                    
                    # 앵커 텍스트 클립보드로 복사
                    pyperclip.copy(self.external_link_text)
                    
                    # Ctrl+V로 붙여넣기
                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    time.sleep(0.5)
                    
                    # 앵커 텍스트만 선택 (Home으로 이동 후 Shift+End로 줄 끝까지 선택)
                    actions = ActionChains(self.driver)
                    actions.send_keys(Keys.HOME).perform()
                    time.sleep(0.1)
                    actions.key_down(Keys.SHIFT).send_keys(Keys.END).key_up(Keys.SHIFT).perform()
                    time.sleep(0.5)
                    
                    # 중앙 정렬 버튼 클릭
                    try:
                        align_dropdown = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-property-toolbar-drop-down-button.se-align-left-toolbar-button"))
                        )
                        align_dropdown.click()
                        time.sleep(0.3)
                        
                        center_align_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-align-center-button"))
                        )
                        center_align_btn.click()
                        time.sleep(0.3)
                        self._update_status("✅ 중앙 정렬 완료")
                    except Exception as e:
                        self._update_status(f"⚠️ 중앙 정렬 실패: {str(e)}")
                    
                    # 앵커 텍스트 다시 선택
                    actions = ActionChains(self.driver)
                    actions.send_keys(Keys.HOME).perform()
                    time.sleep(0.1)
                    actions.key_down(Keys.SHIFT).send_keys(Keys.END).key_up(Keys.SHIFT).perform()
                    time.sleep(0.3)
                    
                    # 폰트 크기 24 설정
                    try:
                        font_size_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-font-size-code-toolbar-button.se-property-toolbar-label-select-button"))
                        )
                        font_size_btn.click()
                        time.sleep(0.3)
                        
                        fs24_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-font-size-code-fs24-button"))
                        )
                        fs24_btn.click()
                        time.sleep(0.3)
                        self._update_status("✅ 폰트 크기 24 적용")
                    except Exception as e:
                        self._update_status(f"⚠️ 폰트 크기 변경 실패: {str(e)}")
                    
                    # 앵커 텍스트 다시 선택
                    actions = ActionChains(self.driver)
                    actions.send_keys(Keys.HOME).perform()
                    time.sleep(0.1)
                    actions.key_down(Keys.SHIFT).send_keys(Keys.END).key_up(Keys.SHIFT).perform()
                    time.sleep(0.3)
                    
                    # 볼드체 적용 (Ctrl+B)
                    actions = ActionChains(self.driver)
                    actions.key_down(Keys.CONTROL).send_keys('b').key_up(Keys.CONTROL).perform()
                    time.sleep(0.3)
                    self._update_status("✅ 볼드체 적용")
                    
                    # 텍스트 끝으로 이동
                    actions = ActionChains(self.driver)
                    actions.send_keys(Keys.END).perform()
                    time.sleep(0.3)
                    
                    # 앵커 텍스트 전체 선택 (링크 삽입을 위해)
                    actions = ActionChains(self.driver)
                    actions.send_keys(Keys.HOME).perform()
                    time.sleep(0.1)
                    actions.key_down(Keys.SHIFT).send_keys(Keys.END).key_up(Keys.SHIFT).perform()
                    time.sleep(0.3)
                    
                    # 링크 버튼 클릭
                    try:
                        link_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-link-toolbar-button.se-property-toolbar-custom-layer-button"))
                        )
                        link_btn.click()
                        time.sleep(0.5)
                        
                        # URL 입력
                        link_input = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "input.se-custom-layer-link-input"))
                        )
                        link_input.clear()
                        link_input.send_keys(self.external_link)
                        time.sleep(0.3)
                        
                        # Enter로 확인
                        actions = ActionChains(self.driver)
                        actions.send_keys(Keys.ENTER).perform()
                        time.sleep(0.5)
                        
                        self._update_status(f"✅ 외부 링크 삽입 완료: {self.external_link_text}")
                        
                    except Exception as e:
                        self._update_status(f"⚠️ 링크 삽입 실패: {str(e)}")
                        actions = ActionChains(self.driver)
                        actions.send_keys(Keys.ESCAPE).perform()
                        time.sleep(0.3)
                    
                    # 링크 삽입 후 Enter
                    actions = ActionChains(self.driver)
                    actions.send_keys(Keys.END).perform()
                    time.sleep(0.2)
                    actions.send_keys(Keys.ENTER).perform()
                    time.sleep(0.3)
                    
                    # 폰트 크기 16으로 변경
                    try:
                        font_size_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-font-size-code-toolbar-button.se-property-toolbar-label-select-button"))
                        )
                        font_size_btn.click()
                        time.sleep(0.3)
                        
                        fs16_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-font-size-code-fs16-button"))
                        )
                        fs16_btn.click()
                        time.sleep(0.3)
                        self._update_status("✅ 폰트 크기 16 적용")
                    except Exception as e:
                        self._update_status(f"⚠️ 폰트 크기 변경 실패: {str(e)}")
                    
                    # Ctrl+B로 볼드체 해제
                    actions = ActionChains(self.driver)
                    actions.key_down(Keys.CONTROL).send_keys('b').key_up(Keys.CONTROL).perform()
                    time.sleep(0.3)
                    self._update_status("✅ 볼드체 해제")
                
                # '함께 보면 좋은 글' 섹션 추가
                self._update_status("📚 '함께 보면 좋은 글' 섹션 확인 중...")
                try:
                    latest_posts_file = os.path.join(self.data_dir, "setting", "latest_posts.txt")
                    
                    # 파일이 존재하는지 확인
                    if os.path.exists(latest_posts_file):
                        with open(latest_posts_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            posts = []
                            
                            # 각 줄을 파싱 (제목|||링크|||설명)
                            for line in lines:
                                line = line.strip()
                                if line and '|||' in line:
                                    parts = line.split('|||')
                                    if len(parts) >= 3:
                                        post_title = parts[0].strip()
                                        post_link = parts[1].strip()
                                        post_desc = parts[2].strip()
                                        posts.append({
                                            'title': post_title,
                                            'link': post_link,
                                            'description': post_desc
                                        })
                            
                            # 최대 3개까지만 사용
                            posts = posts[:3]
                            
                            if posts:
                                self._update_status(f"📚 {len(posts)}개의 관련 글 추가 중...")
                                
                                # 줄 띄우기 (Enter 2번)
                                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                                time.sleep(0.3)
                                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                                time.sleep(0.3)
                                
                                # 사용자 지정 제목 추가 (기본값: "함께 보면 좋은 글")
                                title_text = self.related_posts_title if self.related_posts_title else "함께 보면 좋은 글"
                                ActionChains(self.driver).send_keys(title_text).perform()
                                time.sleep(0.2)
                                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                                time.sleep(0.2)
                                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                                time.sleep(0.2)
                                
                                # 각 글 정보 추가 (제목에 링크 앵커로 삽입)
                                for i, post in enumerate(posts, 1):
                                    self._update_status(f"📝 관련 글 {i} 추가 중...")
                                    
                                    # 제목 작성
                                    post_title = post['title']
                                    ActionChains(self.driver).send_keys(post_title).perform()
                                    time.sleep(0.3)
                                    
                                    # 제목 전체 드래그 (Shift + Home으로 왼쪽 끝까지 선택)
                                    ActionChains(self.driver).key_down(Keys.SHIFT).send_keys(Keys.HOME).key_up(Keys.SHIFT).perform()
                                    time.sleep(0.3)
                                    
                                    # 링크 버튼 클릭 (Ctrl+K 단축키 사용)
                                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('k').key_up(Keys.CONTROL).perform()
                                    time.sleep(0.5)
                                    
                                    # 링크 URL 입력
                                    try:
                                        # 링크 입력 필드 찾기
                                        link_input = WebDriverWait(self.driver, 3).until(
                                            EC.presence_of_element_located((By.CSS_SELECTOR, "input.se-custom-layer-link-input"))
                                        )
                                        link_input.clear()
                                        link_input.send_keys(post['link'])
                                        time.sleep(0.2)
                                        
                                        # 확인 버튼 클릭 (Enter)
                                        link_input.send_keys(Keys.ENTER)
                                        time.sleep(0.3)
                                    except Exception as e:
                                        self._update_status(f"⚠️ 링크 삽입 실패, 수동 입력: {str(e)[:30]}")
                                        # 실패 시 ESC로 대화상자 닫고 계속 진행
                                        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                        time.sleep(0.2)
                                    
                                    # 커서를 줄 끝으로 이동
                                    ActionChains(self.driver).send_keys(Keys.END).perform()
                                    time.sleep(0.1)
                                    
                                    # 줄바꿈
                                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                                    time.sleep(0.1)
                                    
                                    # 마지막 글이 아니면 추가 줄바꿈
                                    if i < len(posts):
                                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                                        time.sleep(0.2)
                                
                                self._update_status("✅ '함께 보면 좋은 글' 섹션 추가 완료")
                            else:
                                self._update_status("⚠️ latest_posts.txt 파일에 유효한 데이터가 없습니다")
                    else:
                        self._update_status("⚪ latest_posts.txt 파일 없음 - '함께 보면 좋은 글' 섹션 스킵")
                        
                except Exception as e:
                    self._update_status(f"⚠️ '함께 보면 좋은 글' 섹션 추가 실패(진행 계속): {str(e)[:100]}")
                
                # 썸네일 삽입 (외부 링크 설정과 무관하게 항상 실행)
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
                                time.sleep(0.3)
                                
                                center_align_btn = WebDriverWait(self.driver, 3).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-align-center-button"))
                                )
                                center_align_btn.click()
                                time.sleep(0.3)
                                self._update_status("✅ 중앙 정렬 완료")
                            except Exception as e:
                                self._update_status(f"⚠️ 중앙 정렬 실패: {str(e)}")
                        
                        # -----------------------------------------------------------
                        # [수정됨] 사진 버튼 클릭 로직 삭제 (윈도우 탐색기 방지)
                        # 바로 숨겨진 파일 입력창(input type='file')을 찾아 전송합니다.
                        # -----------------------------------------------------------

                        # 파일 입력 요소 찾기
                        self._update_status("📂 파일 입력 요소 찾는 중...")
                        file_input = None
                        
                        # 네이버 에디터의 파일 업로드 요소 후보군
                        selectors = [
                            "input[type='file']",
                            "input[id*='file']",
                            ".se-file-input", 
                            "input[accept*='image']"
                        ]
                        
                        for selector in selectors:
                            try:
                                # 숨겨진 요소일 수 있으므로 presence_of_element_located 사용
                                file_input = WebDriverWait(self.driver, 3).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                )
                                if file_input:
                                    self._update_status(f"✅ 파일 입력 요소 찾음: {selector}")
                                    break
                            except:
                                continue
                        
                        # 파일 입력 요소를 못 찾았을 경우 폴백: 사진 버튼 클릭 시도
                        if not file_input:
                            self._update_status("⚠️ 파일 입력 요소를 못 찾음 - 사진 버튼 클릭 시도...")
                            try:
                                image_btn = WebDriverWait(self.driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "button.se-image-toolbar-button.se-document-toolbar-basic-button"))
                                )
                                self.driver.execute_script("arguments[0].click();", image_btn)
                                time.sleep(2)
                                
                                # 버튼 클릭 후 다시 파일 입력 찾기
                                for selector in selectors:
                                    try:
                                        file_input = WebDriverWait(self.driver, 3).until(
                                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                        )
                                        if file_input:
                                            self._update_status(f"✅ 버튼 클릭 후 파일 입력 요소 찾음: {selector}")
                                            break
                                    except:
                                        continue
                            except Exception as e:
                                self._update_status(f"⚠️ 사진 버튼 클릭 실패: {str(e)[:50]}")
                        
                        if not file_input:
                            raise Exception("파일 입력 요소를 찾을 수 없습니다 (모든 방법 실패)")
                        
                        # 절대 경로로 파일 전송 (버튼 클릭 없이 바로 전송)
                        abs_path = os.path.abspath(thumbnail_path)
                        self._update_status(f"⏳ 썸네일 업로드 중: {os.path.basename(abs_path)}")
                        
                        # 파일 경로 전송
                        file_input.send_keys(abs_path)
                        
                        # 업로드 대기
                        time.sleep(5)
                        self._update_status("✅ 썸네일 업로드 명령 전달 완료")
                        
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
                                "button[aria-label='닫기']"
                            ]
                            
                            popup_handled = False
                            for btn_sel in close_selectors:
                                try:
                                    btn = WebDriverWait(self.driver, 1).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, btn_sel))
                                    )
                                    btn.click()
                                    popup_handled = True
                                    time.sleep(1)
                                    break
                                except:
                                    continue
                            
                            # 버튼 처리가 안되었다면 ESC 키 한 번 전송 (안전장치)
                            if not popup_handled:
                                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                                time.sleep(0.5)
                                
                        except Exception:
                            pass # 팝업 없으면 통과

                        self._update_status("✅ 썸네일 삽입 완료")
                        
                        # Enter 키 2번으로 다음 줄로 이동 (줄 간격 확보)
                        time.sleep(1)
                        pyautogui.press('enter')
                        time.sleep(0.5)
                        pyautogui.press('enter')
                        time.sleep(0.5)
                        self._update_status("✅ 썸네일 다음 줄로 이동 (Enter 2번)")
                        
                        # 왼쪽 정렬로 복구
                        try:
                            self._update_status("⚙️ 왼쪽 정렬로 복구 중...")
                            
                            align_dropdown = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-property-toolbar-drop-down-button.se-align-center-toolbar-button"))
                            )
                            align_dropdown.click()
                            time.sleep(0.3)
                            
                            left_align_btn = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-align-left-button"))
                            )
                            left_align_btn.click()
                            time.sleep(0.3)
                            self._update_status("✅ 왼쪽 정렬 완료")
                        except Exception as e:
                            self._update_status(f"⚠️ 왼쪽 정렬 실패 (계속 진행): {str(e)[:50]}")
                        
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
                    
                    self._update_status("✍️ 소제목1 작성 중...")
                    ActionChains(self.driver).send_keys(subtitle1).perform()
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 소제목 후 ENTER 한 번 더
                    time.sleep(0.1)
                    
                    self._update_status("✍️ 본문1 작성 중...")
                    # 본문1을 문장 단위로 줄바꿈 (60자 이상이면)
                    self._write_body_with_linebreaks(body1)
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 본문 끝에 ENTER
                    time.sleep(0.3)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    time.sleep(0.2)
                    
                    self._update_status("✍️ 소제목2 작성 중...")
                    ActionChains(self.driver).send_keys(subtitle2).perform()
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 소제목 후 ENTER 한 번 더
                    time.sleep(0.1)
                    
                    self._update_status("✍️ 본문2 작성 중...")
                    # 본문2를 문장 단위로 줄바꿈 (60자 이상이면)
                    self._write_body_with_linebreaks(body2)
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 본문 끝에 ENTER
                    time.sleep(0.3)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    time.sleep(0.2)
                    
                    self._update_status("✍️ 소제목3 작성 중...")
                    ActionChains(self.driver).send_keys(subtitle3).perform()
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 소제목 후 ENTER 한 번 더
                    time.sleep(0.2)
                    
                    self._update_status("✍️ 본문3 작성 중...")
                    # 본문3을 문장 단위로 줄바꿈 (60자 이상이면)
                    self._write_body_with_linebreaks(body3)
                    time.sleep(0.1)
                    ActionChains(self.driver).send_keys(Keys.ENTER).perform()  # 본문 끝에 ENTER
                    time.sleep(0.3)
                    
                    # 7줄 이후의 추가 내용이 있으면 모두 입력
                    if len(content_lines) > 6:
                        self._update_status(f"✍️ 추가 내용 작성 중... ({len(content_lines) - 6}줄 남음)")
                        for i, line in enumerate(content_lines[6:], start=7):
                            if self.should_stop:
                                self._update_status("⏹️ 사용자가 포스팅을 중지했습니다.")
                                return False
                            
                            if line.strip():
                                ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                                time.sleep(0.1)
                                self._write_body_with_linebreaks(line)
                                time.sleep(0.1)
                                
                                # 진행 상황 표시 (매 5줄마다)
                                if i % 5 == 0:
                                    self._update_status(f"✍️ 추가 내용 작성 중... ({i}번째 줄)")
                    
                    self._update_status("✅ 소제목/본문 작성 완료!")
                else:
                    # 6줄 미만일 때 기본 방식으로 작성
                    self._update_status(f"⚠️ 내용이 6줄 미만입니다 ({len(content_lines)}줄). 기본 방식으로 작성합니다.")
                    for line in content_lines:
                        if self.should_stop:
                            self._update_status("⏹️ 사용자가 포스팅을 중지했습니다.")
                            return False
                        if line.strip():
                            ActionChains(self.driver).send_keys(line).perform()
                            time.sleep(0.1)
                            ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                            time.sleep(0.1)
                
                time.sleep(1)
                self._update_status("✅ 본문 입력 완료!")
                
                # 동영상 삽입 (본문 하단에 추가)
                if video_path:
                    self._update_status("🎬 동영상 삽입 중...")
                    try:
                        # Enter 2번으로 줄 띄우기
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        time.sleep(0.3)
                        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
                        time.sleep(0.3)
                        
                        # 중앙 정렬 설정
                        try:
                            self._update_status("⚙️ 중앙 정렬 설정 중...")
                            align_dropdown = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-property-toolbar-drop-down-button.se-align-left-toolbar-button"))
                            )
                            align_dropdown.click()
                            time.sleep(0.3)
                            
                            center_align_btn = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-align-center-button"))
                            )
                            center_align_btn.click()
                            time.sleep(0.3)
                            self._update_status("✅ 중앙 정렬 완료")
                        except Exception as e:
                            self._update_status(f"⚠️ 중앙 정렬 실패: {str(e)}")
                        
                        # 동영상 버튼 클릭
                        self._update_status("🎬 동영상 버튼 클릭 중...")
                        video_btn = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "button.se-video-toolbar-button.se-document-toolbar-basic-button"))
                        )
                        self.driver.execute_script("arguments[0].click();", video_btn)
                        time.sleep(2)
                        
                        # "동영상 추가" 버튼 클릭
                        self._update_status("📂 동영상 추가 버튼 클릭 중...")
                        add_video_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.nvu_btn_append.nvu_local[data-logcode='lmvup.attmv']"))
                        )
                        add_video_btn.click()
                        time.sleep(2)
                        
                        # 파일 입력 요소 찾기 (모든 input[type='file'] 중에서)
                        self._update_status("📂 파일 입력 요소 찾는 중...")
                        file_input = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
                        )
                        
                        # 절대 경로로 동영상 파일 전송
                        abs_path = os.path.abspath(video_path)
                        self._update_status(f"⏳ 동영상 업로드 중: {os.path.basename(abs_path)}")
                        file_input.send_keys(abs_path)
                        
                        # 동영상 업로드 대기 (동영상은 더 오래 걸릴 수 있음)
                        time.sleep(10)
                        self._update_status("✅ 동영상 업로드 명령 전달 완료")
                        
                        # Windows 탐색기 창 닫기 (pyautogui 사용 - OS 레벨 키보드 입력)
                        self._update_status("🔘 Windows 탐색기 창 닫는 중...")
                        try:
                            # ESC 키로 Windows 탐색기 창 닫기
                            self._update_status("⌨️ ESC 키로 탐색기 창 닫기 (pyautogui)")
                            pyautogui.press('esc')
                            time.sleep(1)
                            self._update_status("✅ 탐색기 창 닫기 성공")
                        except Exception as e:
                            self._update_status(f"⚠️ ESC 실패, Alt+F4 시도: {str(e)[:30]}")
                            try:
                                # Alt+F4로 시도
                                pyautogui.hotkey('alt', 'f4')
                                time.sleep(1)
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
                            time.sleep(0.5)
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
                            time.sleep(2)
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
                                    time.sleep(0.5)
                                    break
                                time.sleep(0.3)
                            
                            # 추가로 ESC 키도 전송
                            pyautogui.press('esc')
                            time.sleep(0.5)
                            
                        except ImportError:
                            self._update_status("⚠️ pywin32 없음, ESC로 시도")
                            pyautogui.press('esc')
                            time.sleep(0.5)
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
                self._update_status(f"⏰ 발행 전 {interval}분 대기 중...")
                
                for remaining in range(interval, 0, -1):
                    if self.should_stop:
                        self._update_status("⏹️ 대기 중 중지되었습니다")
                        return False
                    
                    self._update_status(f"⏰ 남은 시간: {remaining}분")
                    time.sleep(60)  # 1분 대기
                
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
                            time.sleep(2)
                            self._update_status(f"🪟 메인 창으로 전환 완료")
                        
                        # 블로그 홈으로 이동 후 글쓰기 버튼 클릭
                        self._update_status("📝 블로그 홈으로 이동 중...")
                        self.driver.get("https://section.blog.naver.com/BlogHome.naver?directoryNo=0&currentPage=1&groupId=0")
                        time.sleep(3)
                        
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
                                    self._update_status(f"✅ 글쓰기 버튼 발견 - 클릭 시도")
                                    write_btn.click()
                                    time.sleep(3)
                                    self._update_status("✅ 블로그 홈에서 글쓰기 버튼 클릭 성공")
                                    
                                    # 새 창이 열렸다면 전환
                                    if len(self.driver.window_handles) > 1:
                                        self._update_status("🪟 새 창으로 전환 중...")
                                        self.driver.switch_to.window(self.driver.window_handles[-1])
                                        time.sleep(2)
                                    break
                            except Exception as e:
                                self._update_status(f"⚠️ 선택자 실패: {selector[:30]}...")
                                continue
                        
                        self._update_status("✅ 발행 완료 - 다음 포스팅 준비 완료")
                    except Exception as e:
                        self._update_status(f"⚠️ 글쓰기 준비 중 오류 (계속 진행): {str(e)[:50]}")
                    
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
            
            self._update_status("⚙️ 크롬 드라이버 설치 중...")
            try:
                service = Service(ChromeDriverManager().install())
                self._update_status("✅ 크롬 드라이버 설치 완료")
            except Exception as e:
                self._update_status(f"⚠️ 크롬 드라이버 설치 오류: {str(e)}")
                self._update_status("🔄 기본 크롬 드라이버 사용 시도 중...")
                service = Service()
            
            self._update_status("🚀 브라우저 시작 중...")
            try:
                self.driver = webdriver.Chrome(service=service, options=options)
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
            return True
            
        except Exception as e:
            self._update_status(f"❌ 브라우저 실행 실패: {str(e)}")
            return False
    
    def login(self):
        """네이버 로그인"""
        try:
            self._update_status("🔐 네이버 로그인 페이지 접속 중...")
            
            # 직접 로그인 페이지로 이동
            self.driver.get("https://nid.naver.com/nidlogin.login")
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
            
            self._update_status("⏳ 로그인 처리 중... (5초 대기)")
            time.sleep(5)
            
            # 로그인 성공 확인
            current_url = self.driver.current_url
            
            if "nidlogin" not in current_url:
                self._update_status("✅ 로그인 성공!")
                return True
            else:
                # 2단계 인증 또는 오류 체크
                page_source = self.driver.page_source
                
                if "인증" in page_source or "확인" in page_source:
                    self._update_status("⚠️ 2단계 인증 필요 - 수동으로 인증을 완료해주세요 (30초 대기)")
                    time.sleep(30)
                    
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
            
            # 1단계: AI 글 생성
            self._update_status("📝 [1/5] AI 글 생성 단계")
            title, content = self.generate_content_with_ai()
            if not title or not content:
                self._update_status("❌ AI 글 생성 실패로 프로세스 중단")
                return False
            
            if self.should_stop:
                self._update_status("⏹️ 프로세스가 정지되었습니다.")
                return False
            
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
            if not self.write_post(title, content, thumbnail_path, video_path, is_first_post=is_first_run):
                self._update_status("⚠️ 포스팅 실패 - 브라우저는 열린 상태로 유지됩니다")
                return False
            
            # 포스팅 성공 시 키워드 이동
            if self.current_keyword:
                self.move_keyword_to_used(self.current_keyword)
            
            self._update_status("🎊 전체 프로세스 완료! 포스팅 성공!")
            self._update_status("✅ 브라우저는 열린 상태로 유지됩니다")
            time.sleep(2)
            return True
            
        except Exception as e:
            self._update_status(f"❌ 실행 오류: {str(e)}")
            return False
    
    def close(self):
        """브라우저 종료 (프로그램 종료 시에도 브라우저 유지)"""
        if self.driver:
            self._update_status("✅ 프로그램 종료 (브라우저는 계속 실행됩니다)")
            # self.driver.quit()  # 브라우저는 종료하지 않음


def start_automation(naver_id, naver_pw, api_key, ai_model="gemini", theme="", 
                     open_type="전체공개", external_link="", external_link_text="", 
                     publish_time="now", scheduled_hour="09", scheduled_minute="00", 
                     callback=None):
    """자동화 시작 함수"""
    automation = NaverBlogAutomation(
        naver_id, naver_pw, api_key, ai_model,
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
                              QFrame, QScrollArea, QButtonGroup, QStackedWidget,
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
        
        # 상태 변수
        self.is_running = False
        self.is_paused = False
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
<h3>🔑 API 키 발급 방법</h3>

<p><b>📌 GPT API 발급</b></p>
<ol>
<li>OpenAI 웹사이트 접속: <a href='https://platform.openai.com/api-keys'>https://platform.openai.com/api-keys</a></li>
<li>로그인 또는 회원가입</li>
<li>"Create new secret key" 버튼 클릭</li>
<li>생성된 API 키 복사 (한 번만 표시됨!)</li>
<li>위의 "GPT API" 입력란에 붙여넣기</li>
</ol>

<p><b>📌 Gemini API 발급</b></p>
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
<li>GPT API는 유료이며, 사용량에 따라 과금됩니다</li>
<li>Gemini API는 무료 할당량이 있으며, 초과 시 과금될 수 있습니다</li>
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
            self.config["gpt_api_key"] = self.gpt_api_entry.text()
            self.config["gemini_api_key"] = self.gemini_api_entry.text()
            self.config["ai_model"] = "gpt" if self.gpt_radio.isChecked() else "gemini"
            self.config["naver_id"] = self.naver_id_entry.text()
            self.config["naver_pw"] = self.naver_pw_entry.text()
            self.config["interval"] = int(self.interval_entry.text()) if self.interval_entry.text() else 30
            self.config["use_external_link"] = self.use_link_checkbox.isChecked()
            self.config["external_link"] = self.link_url_entry.text()
            self.config["external_link_text"] = self.link_text_entry.text()
            
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
        
        # 오른쪽 제작자 표시
        right_label = QLabel("제작자 : 데이비")
        right_label.setFont(QFont(self.font_family, 13, QFont.Weight.Bold))
        right_label.setStyleSheet("color: white; background-color: transparent; border: none;")
        right_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
        self.log_label.setFont(QFont(self.font_family, 13))
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
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)
        
        # 균등 분할
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        
        # === Row 0: 설정 상태 (가로로 길게) ===
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
        self.settings_log_label.setFont(QFont(self.font_family, 11))
        self.settings_log_label.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent; padding: 5px;")
        self.settings_log_label.setWordWrap(True)
        self.settings_log_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.settings_log_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.settings_log_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        settings_log_layout.addWidget(self.settings_log_label)
        
        self.settings_log_scroll.setWidget(settings_log_widget)
        log_container_layout.addWidget(self.settings_log_scroll)
        
        # 오른쪽: 모든 설정 상태 (50% 너비) - 2x2 그리드
        status_container = QWidget()
        status_container.setStyleSheet(f"QWidget {{ background-color: white; border: 2px solid {NAVER_BORDER}; border-radius: 8px; }}")
        status_layout = QGridLayout(status_container)
        status_layout.setContentsMargins(15, 15, 15, 15)
        status_layout.setHorizontalSpacing(15)
        status_layout.setVerticalSpacing(15)
        
        # API 상태 (0, 0)
        self.settings_api_status = QLabel("🔑 API: 미설정")
        self.settings_api_status.setFont(QFont(self.font_family, 12))
        self.settings_api_status.setStyleSheet(f"color: {NAVER_RED}; background-color: transparent; border: none; font-weight: bold;")
        self.settings_api_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.settings_api_status, 0, 0)
        
        # 로그인 상태 (0, 1)
        self.settings_login_status = QLabel("👤 로그인: 미설정")
        self.settings_login_status.setFont(QFont(self.font_family, 12))
        self.settings_login_status.setStyleSheet(f"color: {NAVER_RED}; background-color: transparent; border: none; font-weight: bold;")
        self.settings_login_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.settings_login_status, 0, 1)
        
        # 썸네일 상태 (1, 0)
        self.settings_thumbnail_status = QLabel("🖼️ 썸네일: OFF")
        self.settings_thumbnail_status.setFont(QFont(self.font_family, 12))
        self.settings_thumbnail_status.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent; border: none; font-weight: bold;")
        self.settings_thumbnail_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.settings_thumbnail_status, 1, 0)
        
        # 외부링크 상태 (1, 1)
        self.settings_link_status_label = QLabel("🔗 외부링크: OFF")
        self.settings_link_status_label.setFont(QFont(self.font_family, 12))
        self.settings_link_status_label.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent; border: none; font-weight: bold;")
        self.settings_link_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.settings_link_status_label, 1, 1)
        
        # 2단 레이아웃 추가 (50:50 비율)
        status_main_layout.addWidget(log_container, 50)
        status_main_layout.addWidget(status_container, 50)
        
        settings_progress_card.content_layout.addLayout(status_main_layout)
        
        # Row 0에 가로로 길게 (2칸럼 통합)
        layout.addWidget(settings_progress_card, 0, 0, 1, 2)
        
        # === Row 1, Col 0: 네이버 로그인 정보 ===
        login_card = PremiumCard("네이버 로그인 정보", "👤")
        
        # 경고 라벨
        warning_label = QLabel("⚠️ 2차 인증 해제 권장")
        warning_label.setStyleSheet(f"""
            background-color: {NAVER_ORANGE}; 
            color: white; 
            padding: 6px 14px; 
            border-radius: 8px;
            font-size: 13px;
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
        login_save_btn.setStyleSheet(f"background-color: {NAVER_GREEN}; padding: 10px 24px; font-size: 13px; font-weight: bold;")
        login_save_btn.clicked.connect(self.save_login_info)
        login_card.content_layout.addStretch()
        login_card.content_layout.addWidget(login_save_btn)
        
        login_card.setMinimumHeight(240)
        
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
        time_save_btn.setStyleSheet(f"background-color: {NAVER_GREEN}; padding: 10px 24px; font-size: 13px; font-weight: bold;")
        time_save_btn.clicked.connect(self.save_time_settings)
        time_card.content_layout.addStretch()
        time_card.content_layout.addWidget(time_save_btn)
        
        time_card.setMinimumHeight(240)
        
        layout.addWidget(time_card, 1, 1)
        
        # === Row 2, Col 0: 외부 링크 설정 ===
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
        
        url_widget = QWidget()
        url_widget.setStyleSheet("QWidget { background-color: transparent; }")
        url_layout = QVBoxLayout(url_widget)
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
                padding: 6px;
                background-color: {NAVER_BG};
                color: {NAVER_TEXT_SUB};
                font-size: 13px;
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
                padding: 6px;
                background-color: {NAVER_BG};
                color: {NAVER_TEXT_SUB};
                font-size: 13px;
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
        link_save_btn.setStyleSheet(f"background-color: {NAVER_GREEN}; padding: 10px 24px; font-size: 13px; font-weight: bold;")
        link_save_btn.clicked.connect(self.save_link_settings)
        link_card.content_layout.addStretch()
        link_card.content_layout.addWidget(link_save_btn)
        
        link_card.setMinimumHeight(240)
        
        layout.addWidget(link_card, 2, 0)
        
        # 초기 취소선 적용 (체크 해제 상태이므로)
        self.toggle_external_link()
        
        # === Row 2, Col 1: API 키 설정 ===
        api_card = PremiumCard("🔑 API 키 설정", "")
        
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
        api_card.header_layout.addWidget(api_help_btn_header)
        
        api_card.content_layout.addStretch()
        
        api_grid = QGridLayout()
        api_grid.setColumnStretch(0, 1)
        api_grid.setColumnStretch(1, 1)
        
        # GPT API
        gpt_api_widget = QWidget()
        gpt_api_widget.setStyleSheet("QWidget { background-color: transparent; }")
        gpt_api_layout = QVBoxLayout(gpt_api_widget)
        gpt_api_layout.setSpacing(5)
        
        gpt_api_label = PremiumCard.create_section_label("🧠 GPT API", self.font_family)
        gpt_api_layout.addWidget(gpt_api_label)
        
        gpt_api_input_layout = QHBoxLayout()
        self.gpt_api_entry = QLineEdit()
        self.gpt_api_entry.setPlaceholderText("GPT API 키")
        self.gpt_api_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.gpt_api_entry.setCursorPosition(0)
        self.gpt_api_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 8px;
                padding: 8px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.gpt_api_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        gpt_api_input_layout.addWidget(self.gpt_api_entry)
        
        # GPT 토글 버튼과 상태 라벨
        gpt_toggle_container = QVBoxLayout()
        gpt_toggle_container.setSpacing(2)
        
        self.gpt_toggle_btn = QPushButton("비공개")
        self.gpt_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gpt_toggle_btn.setMinimumSize(70, 34)
        self.gpt_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_TEXT_SUB};
                border: none;
                border-radius: 6px;
                color: white;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {NAVER_TEXT};
            }}
        """)
        self.gpt_toggle_btn.clicked.connect(self.toggle_gpt_api_key)
        gpt_toggle_container.addWidget(self.gpt_toggle_btn)
        
        gpt_api_input_layout.addLayout(gpt_toggle_container)
        gpt_api_layout.addLayout(gpt_api_input_layout)
        
        api_grid.addWidget(gpt_api_widget, 0, 0)
        
        # Gemini API
        gemini_api_widget = QWidget()
        gemini_api_widget.setStyleSheet("QWidget { background-color: transparent; }")
        gemini_api_layout = QVBoxLayout(gemini_api_widget)
        gemini_api_layout.setSpacing(5)
        
        gemini_api_label = PremiumCard.create_section_label("✨ Gemini API", self.font_family)
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
                padding: 8px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        self.gemini_api_entry.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        gemini_api_input_layout.addWidget(self.gemini_api_entry)
        
        # Gemini 토글 버튼과 상태 라벨
        gemini_toggle_container = QVBoxLayout()
        gemini_toggle_container.setSpacing(2)
        
        self.gemini_toggle_btn = QPushButton("비공개")
        self.gemini_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gemini_toggle_btn.setMinimumSize(70, 34)
        self.gemini_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_TEXT_SUB};
                border: none;
                border-radius: 6px;
                color: white;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {NAVER_TEXT};
            }}
        """)
        self.gemini_toggle_btn.clicked.connect(self.toggle_gemini_api_key)
        gemini_toggle_container.addWidget(self.gemini_toggle_btn)
        
        gemini_api_input_layout.addLayout(gemini_toggle_container)
        gemini_api_layout.addLayout(gemini_api_input_layout)
        
        api_grid.addWidget(gemini_api_widget, 0, 1)
        
        api_card.content_layout.addLayout(api_grid)
        
        # 버튼 레이아웃
        api_button_layout = QHBoxLayout()
        
        api_save_btn = QPushButton("💾 API 키 저장")
        api_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        api_save_btn.setStyleSheet(f"background-color: {NAVER_GREEN}; padding: 10px 24px; font-size: 13px; font-weight: bold;")
        api_save_btn.clicked.connect(self.save_api_key)
        api_button_layout.addWidget(api_save_btn)
        
        api_card.content_layout.addStretch()
        api_card.content_layout.addLayout(api_button_layout)
        
        api_card.setMinimumHeight(240)
        
        layout.addWidget(api_card, 2, 1)
        
        # === Row 3, Col 0: 파일 관리 ===
        file_card = PremiumCard("파일 관리", "📁")
        
        file_card.content_layout.addStretch()
        
        file_grid = QGridLayout()
        file_grid.setColumnStretch(0, 1)
        file_grid.setColumnStretch(1, 1)
        
        # Row 0: 키워드 파일 | 프롬프트1 (제목+서론)
        keyword_widget = QWidget()
        keyword_widget.setStyleSheet("QWidget { background-color: transparent; }")
        keyword_layout = QHBoxLayout(keyword_widget)
        keyword_layout.setContentsMargins(0, 0, 0, 0)
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
        prompt1_layout.setContentsMargins(0, 0, 0, 0)
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
        thumbnail_layout.setContentsMargins(0, 0, 0, 0)
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
        prompt2_layout.setContentsMargins(0, 0, 0, 0)
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
        
        file_card.setMinimumHeight(160)
        
        layout.addWidget(file_card, 3, 0)
        
        # === Row 3, Col 1: AI 모델 선택 ===
        ai_card = PremiumCard("AI 모델 선택", "🤖")
        
        from PyQt6.QtWidgets import QButtonGroup
        
        ai_card.content_layout.addStretch()
        
        ai_grid = QGridLayout()
        ai_grid.setColumnStretch(0, 1)
        ai_grid.setColumnStretch(1, 1)
        
        # 버튼 그룹 생성 (중복 선택 방지)
        self.ai_model_group = QButtonGroup(self)
        
        # Gemini (왼쪽)
        gemini_widget = QWidget()
        gemini_widget.setStyleSheet("QWidget { background-color: transparent; }")
        gemini_layout = QHBoxLayout(gemini_widget)
        gemini_layout.setContentsMargins(0, 0, 0, 0)
        
        self.gemini_radio = QRadioButton("✨ Gemini 2.5 Flash-Lite")
        self.gemini_radio.setChecked(True)
        self.gemini_radio.setFont(QFont(self.font_family, 13))
        self.gemini_radio.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent;")
        self.ai_model_group.addButton(self.gemini_radio)
        gemini_layout.addWidget(self.gemini_radio)
        gemini_layout.addStretch()
        
        ai_grid.addWidget(gemini_widget, 0, 0)
        
        # GPT-4o (오른쪽)
        gpt_widget = QWidget()
        gpt_widget.setStyleSheet("QWidget { background-color: transparent; }")
        gpt_layout = QHBoxLayout(gpt_widget)
        gpt_layout.setContentsMargins(0, 0, 0, 0)
        
        self.gpt_radio = QRadioButton("🧠 GPT-4o")
        self.gpt_radio.setFont(QFont(self.font_family, 13))
        self.gpt_radio.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent;")
        self.ai_model_group.addButton(self.gpt_radio)
        gpt_layout.addWidget(self.gpt_radio)
        gpt_layout.addStretch()
        
        ai_grid.addWidget(gpt_widget, 0, 1)
        
        ai_card.content_layout.addLayout(ai_grid)
        ai_card.content_layout.addStretch()
        
        ai_card.setMinimumHeight(160)
        
        layout.addWidget(ai_card, 3, 1)
        
        # ===== 함께 보면 좋은 글 제목 설정 카드 =====
        related_posts_card = PremiumCard("📚 함께 보면 좋은 글 제목 설정", "📚", self)
        
        # 섹션 제목 라벨
        section_label = QLabel("📚 섹션 제목")
        section_label.setFont(QFont(self.font_family, 12))
        section_label.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent;")
        related_posts_card.content_layout.addWidget(section_label)
        
        # 섹션 제목 입력 필드 (기본값: "함께 보면 좋은 글")
        self.related_posts_title_entry = QLineEdit()
        self.related_posts_title_entry.setPlaceholderText("함께 보면 좋은 글")
        self.related_posts_title_entry.setFont(QFont(self.font_family, 12))
        self.related_posts_title_entry.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 10px;
                border: 2px solid {NAVER_BORDER};
                border-radius: 5px;
                background-color: white;
                color: {NAVER_TEXT};
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        related_posts_card.content_layout.addWidget(self.related_posts_title_entry)
        
        # 블로그 주소 라벨
        blog_addr_label = QLabel("🌐 블로그 주소")
        blog_addr_label.setFont(QFont(self.font_family, 12))
        blog_addr_label.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent;")
        related_posts_card.content_layout.addWidget(blog_addr_label)
        
        # 블로그 주소 입력 필드
        self.blog_address_entry = QLineEdit()
        self.blog_address_entry.setPlaceholderText("yourname (예: david153official-ctrl)")
        self.blog_address_entry.setFont(QFont(self.font_family, 12))
        self.blog_address_entry.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 10px;
                border: 2px solid {NAVER_BORDER};
                border-radius: 5px;
                background-color: white;
                color: {NAVER_TEXT};
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        related_posts_card.content_layout.addWidget(self.blog_address_entry)
        
        # 설명 라벨
        desc_label = QLabel("💡 블로그 주소를 입력하면 최신글 3개를 자동으로 가져와 포스팅 하단에 추가합니다")
        desc_label.setFont(QFont(self.font_family, 11))
        desc_label.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent;")
        desc_label.setWordWrap(True)
        related_posts_card.content_layout.addWidget(desc_label)
        
        # 저장 버튼
        related_posts_save_btn = QPushButton("💾 설정 저장")
        related_posts_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        related_posts_save_btn.setFont(QFont(self.font_family, 13, QFont.Weight.Bold))
        related_posts_save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_GREEN};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                margin-top: 10px;
            }}
            QPushButton:hover {{
                background-color: #00C73C;
            }}
            QPushButton:pressed {{
                background-color: #009632;
            }}
        """)
        related_posts_save_btn.clicked.connect(self.save_related_posts_settings)
        related_posts_card.content_layout.addWidget(related_posts_save_btn)
        
        related_posts_card.setMinimumHeight(300)
        
        layout.addWidget(related_posts_card, 4, 0)
        
        tab.setWidget(content)
        return tab
    
    def _apply_config(self):
        """저장된 설정 적용"""
        if not self.config:
            return
        
        # API 키 (새로운 방식)
        if "gpt_api_key" in self.config:
            self.gpt_api_entry.setText(self.config["gpt_api_key"])
        if "gemini_api_key" in self.config:
            self.gemini_api_entry.setText(self.config["gemini_api_key"])
        
        # 구버전 호환성 (api_key만 있는 경우)
        if "api_key" in self.config and not ("gpt_api_key" in self.config or "gemini_api_key" in self.config):
            if self.config.get("ai_model") == "gpt":
                self.gpt_api_entry.setText(self.config["api_key"])
            else:
                self.gemini_api_entry.setText(self.config["api_key"])
        
        # AI 모델
        if self.config.get("ai_model") == "gpt":
            self.gpt_radio.setChecked(True)
        
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
        
        # API 키 상태 (UI 입력창에서 직접 읽기)
        gpt_key = self.gpt_api_entry.text().strip() if hasattr(self, 'gpt_api_entry') else ""
        gemini_key = self.gemini_api_entry.text().strip() if hasattr(self, 'gemini_api_entry') else ""
        
        if gpt_key or gemini_key:
            if gpt_key and gemini_key:
                self.api_status_label.setText("🔑 API: GPT + Gemini")
            elif gpt_key:
                self.api_status_label.setText("🔑 API: GPT")
            else:
                self.api_status_label.setText("🔑 API: Gemini")
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
            self.api_status_label.setText("🔑 API: 미설정")
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
    
    def toggle_gpt_api_key(self):
        """GPT API 키 표시/숨김"""
        if self.gpt_api_entry.echoMode() == QLineEdit.EchoMode.Password:
            self.gpt_api_entry.setEchoMode(QLineEdit.EchoMode.Normal)
            self.gpt_toggle_btn.setText("공개")
        else:
            self.gpt_api_entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.gpt_toggle_btn.setText("비공개")
    
    def toggle_gemini_api_key(self):
        """Gemini API 키 표시/숨김"""
        if self.gemini_api_entry.echoMode() == QLineEdit.EchoMode.Password:
            self.gemini_api_entry.setEchoMode(QLineEdit.EchoMode.Normal)
            self.gemini_toggle_btn.setText("공개")
        else:
            self.gemini_api_entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.gemini_toggle_btn.setText("비공개")
    
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
        """자동으로 닫히는 메시지 창 (1초 후)"""
        from PyQt6.QtCore import QTimer
        
        msg_box = QMessageBox(self)
        if icon:
            msg_box.setIcon(icon)
        
        msg_box.setText(message)
        msg_box.setWindowTitle("알림")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # 정사각형 모양 + 가독성 개선
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: white;
                min-width: 320px;
                min-height: 180px;
            }}
            QMessageBox QLabel {{
                font-size: 14px;
                font-weight: bold;
                color: {NAVER_TEXT};
                padding: 20px;
                min-width: 280px;
                min-height: 80px;
                qproperty-alignment: AlignCenter;
            }}
            QPushButton {{
                background-color: {NAVER_GREEN};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: #00C73C;
            }}
        """)
        
        # 1초 후 자동 닫기
        msg_box.show()
        QTimer.singleShot(1000, msg_box.close)
    
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
            # API 키 상태
            gpt_key = self.gpt_api_entry.text() if hasattr(self, 'gpt_api_entry') else ""
            gemini_key = self.gemini_api_entry.text() if hasattr(self, 'gemini_api_entry') else ""
            
            if gpt_key and gemini_key:
                api_text = "🔑 API: GPT + Gemini"
                api_color = NAVER_GREEN
            elif gpt_key:
                api_text = "🔑 API: GPT"
                api_color = NAVER_GREEN
            elif gemini_key:
                api_text = "🔑 API: Gemini"
                api_color = NAVER_GREEN
            else:
                api_text = "🔑 API: 미설정"
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
        """API 키 저장"""
        ai_model = "GPT" if self.gpt_radio.isChecked() else "Gemini"
        
        # 빈 칸 검증
        gpt_key = self.gpt_api_entry.text().strip()
        gemini_key = self.gemini_api_entry.text().strip()
        
        if self.gpt_radio.isChecked() and not gpt_key:
            self._show_auto_close_message("⚠️ GPT API 키를 입력해주세요", QMessageBox.Icon.Warning)
            return
        
        if self.gemini_radio.isChecked() and not gemini_key:
            self._show_auto_close_message("⚠️ Gemini API 키를 입력해주세요", QMessageBox.Icon.Warning)
            return
        
        self.config["gpt_api_key"] = gpt_key
        self.config["gemini_api_key"] = gemini_key
        self.config["api_key"] = gpt_key if self.gpt_radio.isChecked() else gemini_key
        self.config["ai_model"] = "gpt" if self.gpt_radio.isChecked() else "gemini"
        self._update_settings_status(f"🔑 {ai_model} API 키가 저장되었습니다")
        self.save_config_file()
        self.update_status_display()
        self._update_settings_summary()
        self._show_auto_close_message(f"✅ {ai_model} API 키가 저장되었습니다", QMessageBox.Icon.Information)
    
    def save_login_info(self):
        """로그인 정보 저장"""
        self.config["naver_id"] = self.naver_id_entry.text()
        self.config["naver_pw"] = self.naver_pw_entry.text()
        self._update_settings_status("👤 네이버 로그인 정보가 저장되었습니다")
        self.save_config_file()
        self.update_status_display()
        self._update_settings_summary()
    
    def save_time_settings(self):
        """발행 간격 저장"""
        interval = int(self.interval_entry.text() or "10")
        self.config["interval"] = interval
        self._update_settings_status(f"⏱️ 발행 간격이 {interval}분으로 저장되었습니다")
        self.save_config_file()
        self.update_status_display()
    
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
        self.config["external_link"] = self.link_url_entry.text()
        self.config["external_link_text"] = self.link_text_entry.text()
        status = "ON" if self.use_link_checkbox.isChecked() else "OFF"
        self._update_settings_status(f"🔗 외부 링크 설정이 저장되었습니다 (상태: {status})")
        self.save_config_file()
    
    def save_related_posts_settings(self):
        """함께 보면 좋은 글 설정 저장"""
        blog_address = self.blog_address_entry.text().strip()
        related_posts_title = self.related_posts_title_entry.text().strip()
        
        # blog_address가 비어있지 않으면 전체 URL로 변환
        if blog_address:
            if not blog_address.startswith("http"):
                # https://blog.naver.com/아이디 형식으로 변환
                blog_address = f"https://blog.naver.com/{blog_address}"
        
        self.config["blog_address"] = blog_address
        self.config["related_posts_title"] = related_posts_title if related_posts_title else "함께 보면 좋은 글"
        
        status_msg = f"📚 '함께 보면 좋은 글' 설정이 저장되었습니다"
        if blog_address:
            status_msg += f"\n   블로그: {blog_address}"
        else:
            status_msg += "\n   (블로그 주소 미설정 - 기능 비활성화)"
        
        self._update_settings_status(status_msg)
        self.save_config_file()
    

    def start_posting(self, is_first_start=True):
        """포스팅 시작"""
        
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
        
        # 설정 검증
        ai_model = "gpt" if self.gpt_radio.isChecked() else "gemini"
        api_key = self.gpt_api_entry.text() if ai_model == "gpt" else self.gemini_api_entry.text()
        
        # 선택된 AI 모델에 해당하는 API 키만 검증
        if not api_key:
            self.show_message("⚠️ 경고", f"선택된 AI 모델({ai_model.upper()})의 API 키를 입력해주세요!", "warning")
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
        self.update_progress_status("🚀 포스팅 프로세스를 시작합니다...")
        print("🚀 포스팅 프로세스를 시작합니다...")
        
        # 자동화 바로 시작 (별도 스레드)
        def run_automation():
            try:
                external_link = self.link_url_entry.text() if self.use_link_checkbox.isChecked() else ""
                external_link_text = self.link_text_entry.text() if self.use_link_checkbox.isChecked() else ""
                
                # 첫 실행시에만 자동화 인스턴스 생성
                if is_first_start:
                    # 블로그 주소 처음 (아이디만 있으면 전체 URL로 변환)
                    blog_address = self.config.get("blog_address", "")
                    related_posts_title = self.config.get("related_posts_title", "함께 보면 좋은 글")
                    
                    self.automation = NaverBlogAutomation(
                        naver_id=self.naver_id_entry.text(),
                        naver_pw=self.naver_pw_entry.text(),
                        api_key=api_key,
                        ai_model=ai_model,
                        theme="",
                        open_type="전체공개",
                        external_link=external_link,
                        external_link_text=external_link_text,
                        publish_time="now",
                        scheduled_hour="00",
                        scheduled_minute="00",
                        related_posts_title=related_posts_title,
                        blog_address=blog_address,
                        callback=self.log_message,
                        config=self.config
                    )
                
                # 자동화 실행 (첫 실행 여부 전달)
                result = self.automation.run(is_first_run=is_first_start)
                
                # 실패 시 원인 구분하여 처리
                if result is False:
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
                        return
                    else:
                        # 키워드는 있지만 다른 이유로 실패 (발행 실패 등)
                        self.update_progress_status("⚠️ 포스팅 중 오류가 발생했습니다.")
                        print("⚠️ 포스팅 실패 - 키워드는 유지되고 다음 시도에서 재사용됩니다")
                        return
                
                self.update_progress_status("✅ 포스팅이 완료되었습니다!")
                print("✅ 포스팅이 완료되었습니다!")
                
                # UI 상태 갱신 (키워드 개수 등 실시간 업데이트)
                QTimer.singleShot(0, lambda: self.update_status_display())
                
                # 포스팅 완료 후 다음 포스팅을 자동으로 시작
                if self.is_running and not self.is_paused:
                    self.update_progress_status("🔄 다음 포스팅을 준비합니다...")
                    print("🔄 다음 포스팅을 준비합니다...")
                    # 다음 포스팅은 첫 포스팅이 아님 (is_first_start=False)
                    self.start_posting(is_first_start=False)
            except Exception as e:
                self.update_progress_status(f"❌ 오류: {e}")
                print(f"❌ 자동화 오류: {e}")
                # 오류 발생 시에만 중지
                self.is_running = False
                self.stop_btn.setEnabled(False)
                self.pause_btn.setEnabled(False)
                self.start_btn.setEnabled(True)
        
        thread = threading.Thread(target=run_automation, daemon=True)
        thread.start()
    
    def stop_posting(self):
        """포스팅 정지"""
        self.is_running = False
        self.is_paused = False
        
        # 실행 중인 자동화 인스턴스 정지
        if self.automation:
            self.automation.should_stop = True
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
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(True)
        self.show_message("⏸️ 일시정지", "포스팅을 일시정지했습니다.", "info")
    
    def resume_posting(self):
        """포스팅 재개"""
        self.is_paused = False
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
            
            # 스크롤을 맨 아래로 이동 (직접 실행, 타이머 사용 안 함)
            try:
                # QScrollArea를 찾아서 스크롤 조정
                widget = self.log_label
                while widget:
                    if isinstance(widget, QScrollArea):
                        widget.verticalScrollBar().setValue(
                            widget.verticalScrollBar().maximum()
                        )
                        break
                    widget = widget.parent()
            except:
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
                        border: 2px solid #e0e0e0;
                        border-radius: 8px;
                        padding: 10px;
                        font-family: 'Consolas', 'Courier New', monospace;
                        font-size: 11px;
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
    
    # 스플래시 화면 닫고 메인 윈도우 표시
    splash.finish(window)
    window.show()
    
    sys.exit(app.exec())
