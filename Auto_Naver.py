# -*- coding: utf-8 -*-
"""
네이버 블로그 AI 자동 포스팅 통합 프로그램 v5.0
- Selenium을 사용한 네이버 블로그 자동화
- Gemini AI / GPT-4o를 활용한 콘텐츠 생성
- PyQt6 GUI
"""

import sys
import io
import locale
import json
import os
import threading

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
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        except:
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


class NaverBlogAutomation:
    """네이버 블로그 자동 포스팅 클래스"""
    
    def __init__(self, naver_id, naver_pw, api_key, ai_model="gemini", theme="", 
                 open_type="전체공개", external_link="", external_link_text="", 
                 publish_time="now", scheduled_hour="09", scheduled_minute="00", callback=None):
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
        self.callback = callback
        self.driver = None
        self.should_stop = False  # 정지 플래그
        self.current_keyword = ""  # 현재 사용 중인 키워드
        
        # AI 모델 설정
        if ai_model == "gemini":
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
        elif ai_model == "gpt":
            self.client = OpenAI(api_key=api_key)
            self.model = "gpt-4o"
    
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
    
    def load_keywords(self):
        """keywords.txt 파일에서 하나의 키워드 로드하고 used_keywords.txt로 이동"""
        try:
            keywords_file = "keywords.txt"
            used_keywords_file = "used_keywords.txt"
            
            if os.path.exists(keywords_file):
                with open(keywords_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    keywords = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
                
                if keywords:
                    # 첫 번째 키워드 선택
                    selected_keyword = keywords[0]
                    
                    # 남은 키워드들
                    remaining_keywords = keywords[1:]
                    
                    # keywords.txt 업데이트 (사용한 키워드 제거)
                    with open(keywords_file, 'w', encoding='utf-8') as f:
                        for kw in remaining_keywords:
                            f.write(kw + '\n')
                    
                    # used_keywords.txt에 추가
                    with open(used_keywords_file, 'a', encoding='utf-8') as f:
                        f.write(selected_keyword + '\n')
                    
                    self._update_status(f"선택된 키워드: {selected_keyword}")
                    return selected_keyword
                else:
                    self._update_status("경고: 사용 가능한 키워드가 없습니다.")
                    return ""
            else:
                self._update_status("경고: keywords.txt 파일이 없습니다.")
                return ""
        except Exception as e:
            self._update_status(f"키워드 로드 오류: {str(e)}")
            return ""
    
    def generate_content_with_ai(self):
        """AI를 사용하여 블로그 글 생성 (Gemini 또는 GPT)"""
        try:
            model_name = "Gemini 2.5 Flash-Lite" if self.ai_model == "gemini" else "GPT-4o"
            self._update_status(f"🤖 AI 모델 준비 중: {model_name}")
            
            # keywords.txt에서 키워드 로드 및 저장
            self._update_status("📋 키워드 파일 읽는 중...")
            keywords = self.load_keywords()
            self.current_keyword = keywords
            self._update_status(f"✅ 선택된 키워드: {keywords}")
            
            # prompt.txt 파일 읽기
            self._update_status("📄 프롬프트 템플릿 로드 중...")
            prompt_file = "prompt.txt"
            if os.path.exists(prompt_file):
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_template = f.read()
                prompt = prompt_template.replace('{keywords}', keywords)
                self._update_status("✅ 사용자 정의 프롬프트 로드 완료")
            else:
                # 기본 프롬프트
                prompt = f"""
다음 키워드로 블로그 글을 작성해주세요:
키워드: {keywords}

요구사항:
1. 제목: 간단하고 매력적인 제목 (한 줄)
2. 서론: 160자 정도의 흥미로운 도입부
3. 본문: 2000자 이상의 유익하고 흥미로운 내용
4. 자연스러운 문체 사용
5. 적절한 문단 나누기
6. **소제목 표시**: 소제목으로 강조하고 싶은 줄의 앞에 느낌표(!) 기호를 붙여주세요
   예: !첫 번째 핵심 포인트
   예: !두 번째 핵심 포인트
"""
                self._update_status("✅ 기본 프롬프트 사용")
            
            # AI 모델에 따라 호출
            self._update_status(f"🔄 AI에게 글 생성 요청 중... (모델: {model_name})")
            if self.ai_model == "gemini":
                response = self.model.generate_content(prompt)
                content = response.text
            elif self.ai_model == "gpt":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "당신은 전문 블로그 작가입니다."},
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.choices[0].message.content
            
            self._update_status("📝 AI 응답 처리 중...")
            # 제목과 본문 분리
            lines = content.strip().split('\n')
            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()
            
            self._update_status(f"✅ AI 글 생성 완료! (제목: {title[:30]}...)")
            return title, body
            
        except Exception as e:
            self._update_status(f"❌ AI 글 생성 오류: {str(e)}")
            return None, None
    
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
            service = Service(ChromeDriverManager().install())
            
            self._update_status("🚀 브라우저 시작 중...")
            self.driver = webdriver.Chrome(service=service, options=options)
            
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
    
    def apply_subtitle_format(self, subtitle_lines, content_lines):
        """소제목에 서식 적용"""
        try:
            for line_num in subtitle_lines:
                subtitle_with_marker = content_lines[line_num].strip()
                subtitle_text = subtitle_with_marker.replace('!', '').strip()
                
                self._update_status(f"소제목 서식 적용: {subtitle_text[:20]}")
                
                # 1. Ctrl+F로 찾기
                actions = ActionChains(self.driver)
                actions.key_down(Keys.CONTROL).send_keys('f').key_up(Keys.CONTROL).perform()
                time.sleep(0.5)
                
                # 2. 검색창에 입력
                actions = ActionChains(self.driver)
                actions.send_keys(subtitle_with_marker).perform()
                time.sleep(0.5)
                
                # 3. ESC로 찾기 닫기
                actions = ActionChains(self.driver)
                actions.send_keys(Keys.ESCAPE).perform()
                time.sleep(0.3)
                
                # 4. 트리플 클릭으로 줄 전체 선택
                try:
                    text_elem = self.driver.find_element(By.XPATH, f"//*[contains(text(), '{subtitle_with_marker[:15]}')]")
                    actions = ActionChains(self.driver)
                    actions.move_to_element(text_elem).click().click().click().perform()
                    time.sleep(0.5)
                    
                    # 5. 서식 툴바 컨테이너 버튼 클릭
                    format_dropdown = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-text-format-toolbar-button.se-property-toolbar-label-select-button"))
                    )
                    format_dropdown.click()
                    time.sleep(0.5)
                    
                    # 6. 소제목 버튼 클릭
                    section_title_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.se-toolbar-option-text-button.se-toolbar-option-text-format-sectionTitle-button[data-value='sectionTitle']"))
                    )
                    section_title_btn.click()
                    time.sleep(0.5)
                    
                    # 7. ! 기호 제거
                    actions = ActionChains(self.driver)
                    actions.move_to_element(text_elem).click().click().click().perform()
                    time.sleep(0.3)
                    
                    actions = ActionChains(self.driver)
                    actions.send_keys(subtitle_text).perform()
                    time.sleep(0.3)
                    
                    self._update_status(f"소제목 완료: {subtitle_text[:20]}")
                    
                except Exception as e:
                    self._update_status(f"소제목 서식 실패: {subtitle_text[:20]}")
                    continue
                    
        except Exception as e:
            self._update_status(f"소제목 처리 오류: {str(e)}")
    
    def write_post(self, title, content, wait_interval=0):
        """블로그 글 작성"""
        try:
            self._update_status("📝 블로그 페이지로 이동 중...")
            
            self.driver.get("https://section.blog.naver.com/BlogHome.naver?directoryNo=0&currentPage=1&groupId=0")
            time.sleep(3)
            
            self._update_status("✍️ 글쓰기 버튼 찾는 중...")
            
            try:
                write_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".sp_common.icon_write"))
                )
                self._update_status("👆 글쓰기 버튼 클릭...")
                write_btn.click()
                time.sleep(3)
            except:
                self._update_status("📝 직접 글쓰기 페이지로 이동...")
                self.driver.get("https://blog.naver.com/my/post/write.naver")
                time.sleep(3)
            
            if len(self.driver.window_handles) > 1:
                self._update_status("🪟 새 창으로 전환 중...")
                self.driver.switch_to.window(self.driver.window_handles[-1])
                time.sleep(2)
            
            # ⚠️ 1단계: mainFrame으로 먼저 전환
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
            
            # ⚠️ 2단계: 팝업창 확인 및 '취소' 버튼 클릭
            self._update_status("🔍 팝업 확인 중...")
            try:
                popup_container = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".se-popup-container.__se-pop-layer"))
                )
                time.sleep(0.5)
                
                popup_cancel = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-popup-button.se-popup-button-cancel"))
                )
                popup_cancel.click()
                self._update_status("✅ 팝업 닫기 완료")
                time.sleep(1)
            except:
                pass
            
            # 📚 3단계: 도움말 패널 존재 확인 및 처리
            self._update_status("📚 도움말 패널 확인 중...")
            try:
                help_header = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".se-help-header.se-help-header-dark"))
                )
                
                help_close = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".se-help-panel-close-button"))
                )
                help_close.click()
                self._update_status("✅ 도움말 닫기 완료")
                time.sleep(1)
            except:
                pass
            
            # 4단계: 제목 입력
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
                subtitle_lines = []
                total_lines = len([line for line in content_lines if line.strip()])
                
                self._update_status(f"📝 총 {total_lines}줄 작성 시작...")
                
                # 1단계: 먼저 모든 내용 입력
                current_line = 0
                for i, line in enumerate(content_lines):
                    if line.strip():
                        current_line += 1
                        is_subtitle = line.strip().startswith('!')
                        
                        if is_subtitle:
                            subtitle_lines.append(i)
                        
                        # 진행률 표시 (10줄마다)
                        if current_line % 10 == 0 or current_line == total_lines:
                            self._update_status(f"✍️ 작성 중... ({current_line}/{total_lines}줄)")
                        
                        # 줄 내용 입력
                        actions = ActionChains(self.driver)
                        actions.send_keys(line).perform()
                        time.sleep(0.3)
                        
                        # 본문의 긴 문장(50자 이상)인 경우에만 Enter 2번
                        if not is_subtitle and len(line.strip()) >= 50:
                            actions = ActionChains(self.driver)
                            actions.send_keys(Keys.ENTER).perform()
                            time.sleep(0.1)
                            actions.send_keys(Keys.ENTER).perform()
                            time.sleep(0.3)
                
                time.sleep(1)
                self._update_status("✅ 본문 입력 완료!")
                
                # 2단계: 소제목 서식 적용
                if subtitle_lines:
                    self._update_status(f"🎨 소제목 서식 적용 중... ({len(subtitle_lines)}개)")
                    self.apply_subtitle_format(subtitle_lines, content_lines)
                
            except Exception as e:
                self._update_status(f"❌ 본문 입력 실패: {str(e)}")
            
            # mainFrame 안에서 계속 작업
            self._update_status("⚙️ 발행 설정 준비 중...")
            time.sleep(2)
            
            # 발행 버튼 클릭
            self._update_status("🔍 발행 버튼 찾는 중...")
            try:
                # 1. 먼저 여러 셀렉터로 시도
                publish_selectors = [
                    "button.publish_btn__m9KHH",
                    "button[data-click-area='tpb.publish']",
                    "button.publish_btn",
                    "[class*='publish_btn']",
                    "//button[contains(@class, 'publish_btn')]"
                ]
                
                publish_btn = None
                found_selector = None
                
                for selector in publish_selectors:
                    try:
                        if selector.startswith("//"):
                            publish_btn = WebDriverWait(self.driver, 3).until(
                                EC.presence_of_element_located((By.XPATH, selector))
                            )
                        else:
                            publish_btn = WebDriverWait(self.driver, 3).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                        
                        if publish_btn:
                            found_selector = selector
                            break
                    except:
                        continue
                
                if not publish_btn:
                    self._update_status("❌ 발행 버튼을 찾을 수 없습니다")
                    return False
                
                # JavaScript로 클릭
                self.driver.execute_script("arguments[0].scrollIntoView(true);", publish_btn)
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].click();", publish_btn)
                self._update_status("✅ 발행 설정 팝업 열림")
                time.sleep(3)
                
                # 발행 팝업에서 설정
                time.sleep(3)
                
                # 1. 태그 입력
                try:
                    self._update_status("🏷️ 태그 입력 중...")
                    tag_input = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".tag_input__rvUB5"))
                    )
                    
                    if self.current_keyword:
                        main_tag = self.current_keyword.replace(" ", "")
                        tag_input.send_keys(main_tag)
                        tag_input.send_keys(Keys.ENTER)
                        time.sleep(0.3)
                        
                        related_tags = [f"{main_tag}정보", f"{main_tag}추천"]
                        for tag in related_tags:
                            tag_input.send_keys(tag)
                            tag_input.send_keys(Keys.ENTER)
                            time.sleep(0.3)
                        
                        self._update_status(f"✅ 태그 입력 완료: #{main_tag} #{main_tag}정보 #{main_tag}추천")
                except Exception as e:
                    self._update_status(f"⚠️ 태그 입력 실패: {str(e)}")
                
                # 2. 발행 시간 설정
                try:
                    self._update_status(f"⏰ 발행 시간 설정: {'예약 발행' if self.publish_time == 'pre' else '즉시 발행'}")
                    time.sleep(1)
                    
                    if self.publish_time == "pre":
                        self._update_status("📅 예약 발행 옵션 선택 중...")
                        schedule_selectors = [
                            "#radio_time2",
                            "input[value='pre'][name='radio_time']",
                            "input[data-testid='preTimeRadioBtn']",
                            "input.radio_item__PIBr7[value='pre']",
                            "//input[@id='radio_time2']"
                        ]
                        
                        schedule_clicked = False
                        for selector in schedule_selectors:
                            try:
                                if selector.startswith("//"):
                                    schedule_radio = WebDriverWait(self.driver, 5).until(
                                        EC.presence_of_element_located((By.XPATH, selector))
                                    )
                                else:
                                    schedule_radio = WebDriverWait(self.driver, 5).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                    )
                                
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", schedule_radio)
                                time.sleep(0.3)
                                
                                self.driver.execute_script("arguments[0].click();", schedule_radio)
                                time.sleep(0.5)
                                
                                is_checked = self.driver.execute_script("return arguments[0].checked;", schedule_radio)
                                if is_checked:
                                    schedule_clicked = True
                                    self._update_status("✅ 예약 발행 선택 완료")
                                    time.sleep(1.5)
                                    break
                                    
                            except:
                                continue
                        
                        if not schedule_clicked:
                            raise Exception("예약 라디오 버튼을 찾을 수 없습니다")
                        
                        # 시간 설정
                        self._update_status(f"🕐 시간 설정 중: {self.scheduled_hour}시...")
                        hour_selectors = [
                            ".hour_option__J_heO",
                            "select[name='hour']",
                            "//select[contains(@class, 'hour')]"
                        ]
                        
                        for selector in hour_selectors:
                            try:
                                if selector.startswith("//"):
                                    hour_select = WebDriverWait(self.driver, 3).until(
                                        EC.element_to_be_clickable((By.XPATH, selector))
                                    )
                                else:
                                    hour_select = WebDriverWait(self.driver, 3).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                    )
                                hour_select.click()
                                time.sleep(0.3)
                                
                                hour_option = self.driver.find_element(By.XPATH, f"//option[@value='{self.scheduled_hour}']")
                                hour_option.click()
                                time.sleep(0.3)
                                break
                            except:
                                continue
                        
                        # 분 설정
                        self._update_status(f"⏰ 분 설정 중: {self.scheduled_minute}분...")
                        minute_selectors = [
                            ".minute_option__Vb3xB",
                            "select[name='minute']",
                            "//select[contains(@class, 'minute')]"
                        ]
                        
                        for selector in minute_selectors:
                            try:
                                if selector.startswith("//"):
                                    minute_select = WebDriverWait(self.driver, 3).until(
                                        EC.element_to_be_clickable((By.XPATH, selector))
                                    )
                                else:
                                    minute_select = WebDriverWait(self.driver, 3).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                    )
                                minute_select.click()
                                time.sleep(0.3)
                                
                                minute_option = self.driver.find_element(By.XPATH, f"//option[@value='{self.scheduled_minute}']")
                                minute_option.click()
                                break
                            except:
                                continue
                        
                        self._update_status(f"✅ 예약 시간 설정 완료: {self.scheduled_hour}시 {self.scheduled_minute}분")
                    else:
                        self._update_status("⚡ 즉시 발행 옵션 선택 중...")
                        now_selectors = [
                            "#radio_time1",
                            "input[value='now'][name='radio_time']",
                            "input[data-testid='nowTimeRadioBtn']",
                            "input.radio_item__PIBr7[value='now']",
                            "//input[@id='radio_time1']"
                        ]
                        
                        now_clicked = False
                        for selector in now_selectors:
                            try:
                                if selector.startswith("//"):
                                    now_radio = WebDriverWait(self.driver, 5).until(
                                        EC.presence_of_element_located((By.XPATH, selector))
                                    )
                                else:
                                    now_radio = WebDriverWait(self.driver, 5).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                    )
                                
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", now_radio)
                                time.sleep(0.3)
                                
                                self.driver.execute_script("arguments[0].click();", now_radio)
                                time.sleep(0.5)
                                
                                is_checked = self.driver.execute_script("return arguments[0].checked;", now_radio)
                                if is_checked:
                                    now_clicked = True
                                    self._update_status("✅ 즉시 발행 선택 완료")
                                    break
                                    
                            except:
                                continue
                        
                        if not now_clicked:
                            self._update_status("⚠️ 즉시 발행 선택 실패 (기본값 사용)")
                    
                    time.sleep(1)
                except Exception as e:
                    self._update_status(f"❌ 발행 시간 설정 실패: {str(e)}")
                
                # 2.5. 발행 간격 대기 (첫 포스팅이 아닌 경우에만)
                if wait_interval > 0:
                    self._update_status(f"⏰ 발행 간격 대기 중: {wait_interval}분")
                    print(f"⏰ 발행 간격 대기 중: {wait_interval}분")
                    
                    # 1분 단위로 대기하면서 상태 업데이트
                    for remaining in range(wait_interval, 0, -1):
                        if self.should_stop:
                            self._update_status("⏹️ 사용자가 중지했습니다")
                            return False
                        
                        self._update_status(f"⏰ 남은 시간: {remaining}분")
                        print(f"⏰ 남은 시간: {remaining}분")
                        time.sleep(60)  # 1분 대기
                    
                    self._update_status("✅ 발행 간격 대기 완료!")
                    print("✅ 발행 간격 대기 완료!")
                
                # 3. 최종 발행 버튼 클릭
                self._update_status("🚀 최종 발행 버튼 찾는 중...")
                time.sleep(2)
                
                # 여러 셀렉터 시도
                final_publish_selectors = [
                    "button.confirm_btn__WEaBq[data-testid='seOnePublishBtn']",
                    "button[data-testid='seOnePublishBtn']",
                    "button[data-click-area='tpb*i.publish']",
                    ".confirm_btn__WEaBq",
                    "//button[contains(@class, 'confirm_btn')]",
                    "//button[contains(., '발행')]",
                ]
                
                published = False
                for selector in final_publish_selectors:
                    try:
                        if selector.startswith("//"):
                            final_publish_btn = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.XPATH, selector))
                            )
                        else:
                            final_publish_btn = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                            )
                        
                        # JavaScript로 클릭
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", final_publish_btn)
                        time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", final_publish_btn)
                        self._update_status("🎉 포스팅 발행 완료!")
                        published = True
                        time.sleep(3)
                        break
                    except:
                        continue
                
                if published:
                    return True
                else:
                    self._update_status("⚠️ 발행 버튼을 찾을 수 없습니다 - 수동으로 발행해주세요")
                    time.sleep(10)
                    return False
                
            except Exception as e:
                self._update_status(f"❌ 발행 설정 오류: {str(e)[:100]}")
                self._update_status("⏸️ 10초 대기 - 수동으로 발행해주세요")
                time.sleep(10)
                return False
            
        except Exception as e:
            self._update_status(f"❌ 포스팅 오류: {str(e)}")
            return False
    
    def run(self, wait_interval=0):
        """전체 프로세스 실행"""
        try:
            self._update_status("🚀 자동 포스팅 프로세스 시작!")
            
            if self.should_stop:
                self._update_status("⏹️ 프로세스가 정지되었습니다.")
                return False
            
            # 1단계: AI 글 생성
            self._update_status("📝 [1/4] AI 글 생성 단계")
            title, content = self.generate_content_with_ai()
            if not title or not content:
                self._update_status("❌ AI 글 생성 실패로 프로세스 중단")
                return False
            
            if self.should_stop:
                self._update_status("⏹️ 프로세스가 정지되었습니다.")
                return False
            
            # 2단계: 브라우저 실행
            self._update_status("🌐 [2/4] 브라우저 실행 단계")
            if not self.setup_driver():
                self._update_status("❌ 브라우저 실행 실패로 프로세스 중단")
                return False
            
            if self.should_stop:
                self._update_status("⏹️ 프로세스가 정지되었습니다.")
                self.close()
                return False
            
            # 3단계: 네이버 로그인
            self._update_status("🔐 [3/4] 네이버 로그인 단계")
            if not self.login():
                self._update_status("❌ 로그인 실패 - 브라우저는 열린 상태로 유지됩니다")
                return False
            
            if self.should_stop:
                self._update_status("⏹️ 프로세스가 정지되었습니다.")
                return False
            
            # 4단계: 블로그 포스팅 (발행 간격 전달)
            self._update_status("✍️ [4/4] 블로그 포스팅 단계")
            if not self.write_post(title, content, wait_interval):
                self._update_status("⚠️ 포스팅 실패 - 브라우저는 열린 상태로 유지됩니다")
                return False
            
            self._update_status("🎊 전체 프로세스 완료! 포스팅 성공!")
            self._update_status("✅ 브라우저는 열린 상태로 유지됩니다")
            time.sleep(2)
            return True
            
        except Exception as e:
            self._update_status(f"❌ 실행 오류: {str(e)}")
            return False
    
    def close(self):
        """브라우저 종료"""
        if self.driver:
            self._update_status("🔒 브라우저 종료 중...")
            self.driver.quit()
            self._update_status("✅ 모든 작업 완료")


def start_automation(naver_id, naver_pw, api_key, ai_model="gemini", theme="", 
                     open_type="전체공개", external_link="", external_link_text="", 
                     publish_time="now", scheduled_hour="09", scheduled_minute="00", 
                     wait_interval=0, callback=None):
    """자동화 시작 함수"""
    automation = NaverBlogAutomation(
        naver_id, naver_pw, api_key, ai_model,
        theme, open_type, external_link, external_link_text, 
        publish_time, scheduled_hour, scheduled_minute, callback
    )
    # 자동화 실행 (발행 간격 전달)
    automation.run(wait_interval)
    return automation


# ===========================
# GUI 부분
# ===========================

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QGridLayout, QPushButton, QLabel, 
                              QLineEdit, QTextEdit, QRadioButton, QCheckBox,
                              QComboBox, QGroupBox, QTabWidget, QMessageBox,
                              QFrame, QScrollArea, QButtonGroup, QStackedWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor

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
NAVER_BORDER = "#E5E8EB"


# ===========================
# GUI 부분
# ===========================

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QGridLayout, QPushButton, QLabel, 
                              QLineEdit, QTextEdit, QRadioButton, QCheckBox,
                              QComboBox, QGroupBox, QTabWidget, QMessageBox,
                              QFrame, QScrollArea, QButtonGroup, QStackedWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor

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
                padding: 8px 20px;
            }}
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        
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
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        layout.addWidget(self.header)
        
        # 콘텐츠 영역
        self.content = QWidget()
        self.content.setStyleSheet("QWidget { background-color: transparent; border: none; }")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 10, 20, 20)
        self.content_layout.setSpacing(10)
        
        layout.addWidget(self.content)
    
    @staticmethod
    def create_section_label(text, font_family="맑은 고딕"):
        """카드 내부의 섹션 라벨 생성"""
        label = QLabel(text)
        label.setFont(QFont(font_family, 13, QFont.Weight.Bold))
        label.setStyleSheet(f"""
            color: {NAVER_TEXT}; 
            background-color: transparent;
            padding: 2px 0px;
        """)
        return label
        
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
                padding: 10px;
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
                padding: 8px;
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
        """설정 파일 로드"""
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ 설정 로드 실패: {e}")
        return {}
    
    def save_config_file(self):
        """설정 파일 저장"""
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            self.show_message("✅ 저장 완료", "설정이 성공적으로 저장되었습니다!", "info")
        except Exception as e:
            self.show_message("❌ 저장 실패", f"설정 저장 중 오류:\n{str(e)}", "error")
    
    def show_message(self, title, message, msg_type="info"):
        """스타일이 적용된 메시지 박스 표시"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        
        if msg_type == "warning":
            msg_box.setIcon(QMessageBox.Icon.Warning)
        elif msg_type == "error":
            msg_box.setIcon(QMessageBox.Icon.Critical)
        else:
            msg_box.setIcon(QMessageBox.Icon.Information)
        
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {NAVER_CARD_BG};
            }}
            QMessageBox QLabel {{
                color: {NAVER_TEXT};
                font-size: 13px;
                padding: 10px;
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
    
    def _create_gui(self):
        """GUI 생성"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self._create_header(main_layout)
        self._create_tabs(main_layout)
    
    def _create_header(self, parent_layout):
        """헤더 생성"""
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {NAVER_GREEN};
                border: none;
                padding: 15px 30px;
            }}
        """)
        header.setFixedHeight(90)
        
        header_layout = QGridLayout(header)
        header_layout.setContentsMargins(30, 0, 30, 0)
        header_layout.setColumnStretch(0, 1)
        header_layout.setColumnStretch(1, 0)
        header_layout.setColumnStretch(2, 1)
        
        # 왼쪽 제목
        left_label = QLabel("Auto Naver Blog Program__V 5.0")
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
                padding: 10px 25px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:checked {{
                background-color: white;
                color: {NAVER_GREEN};
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
                padding: 10px 25px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:checked {{
                background-color: white;
                color: {NAVER_GREEN};
            }}
        """)
        self.settings_tab_btn.setCheckable(True)
        self.settings_tab_btn.clicked.connect(lambda: self._switch_tab(1))
        tab_buttons_layout.addWidget(self.settings_tab_btn)
        
        header_layout.addWidget(tab_buttons_container, 0, 1, Qt.AlignmentFlag.AlignCenter)
        
        # 오른쪽 제작자
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
        """탭 생성"""
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
        
        # 좌측
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(16)
        
        # 포스팅 제어 카드
        control_card = PremiumCard("포스팅 제어", "🎮")
        control_layout = QGridLayout()
        control_card.content_layout.addLayout(control_layout)
        
        self.start_btn = QPushButton("▶️ 시작")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_GREEN};
                min-height: 28px;
                font-size: 13px;
                color: white;
                border: 3px solid #018541;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                border: 3px solid #016A34;
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
                border: 3px solid #B71C1C;
            }}
            QPushButton:enabled:hover {{
                border: 3px solid #A01818;
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
                border: 3px solid #CC7A00;
            }}
            QPushButton:enabled:hover {{
                border: 3px solid #B36A00;
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
                border: 3px solid #0047A3;
            }}
            QPushButton:enabled:hover {{
                border: 3px solid #003A85;
            }}
        """)
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self.resume_posting)
        control_layout.addWidget(self.resume_btn, 1, 1)
        
        left_layout.addWidget(control_card)
        
        # 설정 상태 카드
        status_card = PremiumCard("설정 상태", "⚙️")
        
        login_status_layout = QHBoxLayout()
        self.login_status_label = QLabel("👤 로그인 정보: 미설정")
        self.login_status_label.setFont(QFont(self.font_family, 13))
        self.login_status_label.setStyleSheet(f"color: {NAVER_RED}; border: none;")
        login_status_layout.addWidget(self.login_status_label)
        
        self.login_setup_btn = QPushButton("➡️ 설정하기")
        self.login_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_setup_btn.setFixedHeight(25)
        self.login_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_ORANGE};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #E68900;
            }}
        """)
        self.login_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        login_status_layout.addWidget(self.login_setup_btn)
        login_status_layout.addStretch()
        
        status_card.content_layout.addLayout(login_status_layout)
        
        api_status_layout = QHBoxLayout()
        self.api_status_label = QLabel("🔑 API 키: 미설정")
        self.api_status_label.setFont(QFont(self.font_family, 13))
        self.api_status_label.setStyleSheet(f"color: {NAVER_RED}; border: none;")
        api_status_layout.addWidget(self.api_status_label)
        
        self.api_setup_btn = QPushButton("➡️ 설정하기")
        self.api_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.api_setup_btn.setFixedHeight(25)
        self.api_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_ORANGE};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #E68900;
            }}
        """)
        self.api_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        api_status_layout.addWidget(self.api_setup_btn)
        api_status_layout.addStretch()
        
        status_card.content_layout.addLayout(api_status_layout)
        
        keyword_status_layout = QHBoxLayout()
        self.keyword_count_label = QLabel("📦 키워드 개수: 0개")
        self.keyword_count_label.setFont(QFont(self.font_family, 13))
        self.keyword_count_label.setStyleSheet(f"color: {NAVER_GREEN}; border: none;")
        keyword_status_layout.addWidget(self.keyword_count_label)
        
        self.keyword_setup_btn = QPushButton("➡️ 설정하기")
        self.keyword_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keyword_setup_btn.setFixedHeight(25)
        self.keyword_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_ORANGE};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #E68900;
            }}
        """)
        self.keyword_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        keyword_status_layout.addWidget(self.keyword_setup_btn)
        keyword_status_layout.addStretch()
        
        status_card.content_layout.addLayout(keyword_status_layout)
        
        self.interval_label = QLabel("⏱️ 대기 시간: 10분")
        self.interval_label.setFont(QFont(self.font_family, 13))
        self.interval_label.setStyleSheet(f"color: #000000; border: none;")
        status_card.content_layout.addWidget(self.interval_label)
        
        # 카드 크기 최소화
        status_card.setMaximumHeight(status_card.sizeHint().height())
        
        left_layout.addWidget(status_card)
        left_layout.addStretch()
        
        layout.addWidget(left_widget)
        
        # 우측: 진행 현황
        progress_card = PremiumCard("진행 현황", "📋")
        
        log_scroll = QScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll.setMinimumHeight(300)
        log_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 8px;
                background-color: {NAVER_BG};
            }}
        """)
        
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.log_label = QLabel("⏸️ 대기 중...")
        self.log_label.setFont(QFont(self.font_family, 13))
        self.log_label.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent; padding: 10px;")
        self.log_label.setWordWrap(True)
        self.log_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        log_layout.addWidget(self.log_label)
        log_layout.addStretch()
        
        log_scroll.setWidget(log_widget)
        progress_card.content_layout.addWidget(log_scroll)
        progress_card.content_layout.addStretch()
        
        layout.addWidget(progress_card)
        
        return tab


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
                padding: 8px 20px;
            }}
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        
        # 카드 제목 통일 설정 (모든 카드의 제목 크기와 테두리를 여기서 관리)
        title_label = QLabel(f"{icon} {title}")
        title_label.setFont(QFont("맑은 고딕", 15, QFont.Weight.Bold))
        title_label.setStyleSheet(f"""
            color: {NAVER_GREEN}; 
            background-color: {NAVER_GREEN_LIGHT};
            border: 2px solid {NAVER_GREEN};
            border-radius: 8px;
            padding: 6px 14px;
        """)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        layout.addWidget(self.header)
        
        # 콘텐츠 영역
        self.content = QWidget()
        self.content.setStyleSheet("QWidget { background-color: transparent; border: none; }")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 10, 20, 20)
        self.content_layout.setSpacing(10)
        
        layout.addWidget(self.content)
    
    @staticmethod
    def create_section_label(text, font_family="맑은 고딕"):
        """
        카드 내부의 섹션 라벨 생성 (통일된 스타일)
        모든 섹션 제목의 크기와 스타일을 여기서 중앙 관리
        """
        label = QLabel(text)
        label.setFont(QFont(font_family, 13, QFont.Weight.Bold))
        label.setStyleSheet(f"""
            color: {NAVER_TEXT}; 
            background-color: transparent;
            padding: 2px 0px;
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
        self.setGeometry(100, 100, 1100, 850)
        
        # 드래그 관련 변수 초기화
        self.drag_position = None
        
        # 시그널 연결
        self.countdown_signal.connect(self.start_countdown)
        self.progress_signal.connect(self._update_progress_status_safe)
        
        # 아이콘 설정 (모든 창에 적용)
        if os.path.exists("david153.ico"):
            icon = QIcon("david153.ico")
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
                padding: 10px;
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
                padding: 8px;
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
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ 설정 로드 실패: {e}")
        return {}
    
    def save_config_file(self):
        """설정 파일 저장 (UTF-8)"""
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            self.show_message("✅ 저장 완료", "설정이 성공적으로 저장되었습니다!", "info")
        except Exception as e:
            self.show_message("❌ 저장 실패", f"설정 저장 중 오류:\n{str(e)}", "error")
    
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
        
        # 네이버 스타일 적용
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {NAVER_CARD_BG};
            }}
            QMessageBox QLabel {{
                color: {NAVER_TEXT};
                font-size: 13px;
                padding: 10px;
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
                padding: 15px 30px;
            }}
        """)
        header.setFixedHeight(90)
        
        header_layout = QGridLayout(header)
        header_layout.setContentsMargins(30, 0, 30, 0)
        header_layout.setColumnStretch(0, 1)
        header_layout.setColumnStretch(1, 0)
        header_layout.setColumnStretch(2, 1)
        
        # 왼쪽 제목
        left_label = QLabel("Auto Naver Blog Program__V 5.0")
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
                padding: 10px 25px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:checked {{
                background-color: white;
                color: {NAVER_GREEN};
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
                padding: 10px 25px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
            QPushButton:checked {{
                background-color: white;
                color: {NAVER_GREEN};
            }}
        """)
        self.settings_tab_btn.setCheckable(True)
        self.settings_tab_btn.clicked.connect(lambda: self._switch_tab(1))
        tab_buttons_layout.addWidget(self.settings_tab_btn)
        
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
                border: 3px solid #018541;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                border: 3px solid #016A34;
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
                border: 3px solid #B71C1C;
            }}
            QPushButton:enabled:hover {{
                border: 3px solid #A01818;
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
                border: 3px solid #CC7A00;
            }}
            QPushButton:enabled:hover {{
                border: 3px solid #B36A00;
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
                border: 3px solid #0047A3;
            }}
            QPushButton:enabled:hover {{
                border: 3px solid #003A85;
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
        
        self.login_setup_btn = QPushButton("➡️ 설정하기")
        self.login_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_setup_btn.setFixedHeight(25)
        self.login_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_ORANGE};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #E68900;
            }}
        """)
        self.login_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        login_status_layout.addWidget(self.login_setup_btn)
        login_status_layout.addStretch()
        
        status_card.content_layout.addLayout(login_status_layout)
        
        # API 키 상태
        api_status_layout = QHBoxLayout()
        self.api_status_label = QLabel("🔑 API 키: 미설정")
        self.api_status_label.setFont(QFont(self.font_family, 13))
        self.api_status_label.setStyleSheet(f"color: #000000; border: none;")
        api_status_layout.addWidget(self.api_status_label)
        
        self.api_setup_btn = QPushButton("➡️ 설정하기")
        self.api_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.api_setup_btn.setFixedHeight(25)
        self.api_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_ORANGE};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #E68900;
            }}
        """)
        self.api_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        api_status_layout.addWidget(self.api_setup_btn)
        api_status_layout.addStretch()
        
        status_card.content_layout.addLayout(api_status_layout)
        
        # 키워드 개수 상태
        keyword_status_layout = QHBoxLayout()
        self.keyword_count_label = QLabel("📦 키워드 개수: 0개")
        self.keyword_count_label.setFont(QFont(self.font_family, 13))
        self.keyword_count_label.setStyleSheet(f"color: #000000; border: none;")
        keyword_status_layout.addWidget(self.keyword_count_label)
        
        self.keyword_setup_btn = QPushButton("➡️ 설정하기")
        self.keyword_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keyword_setup_btn.setFixedHeight(25)
        self.keyword_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_ORANGE};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #E68900;
            }}
        """)
        self.keyword_setup_btn.clicked.connect(lambda: self._switch_tab(1))
        keyword_status_layout.addWidget(self.keyword_setup_btn)
        keyword_status_layout.addStretch()
        
        status_card.content_layout.addLayout(keyword_status_layout)
        
        self.interval_label = QLabel("⏱️ 대기 시간: 10분")
        self.interval_label.setFont(QFont(self.font_family, 13))
        self.interval_label.setStyleSheet(f"color: #000000; border: none;")
        status_card.content_layout.addWidget(self.interval_label)
        
        # 카드 크기 최소화
        status_card.setMaximumHeight(status_card.sizeHint().height())
        
        left_layout.addWidget(status_card)
        left_layout.addStretch()
        
        layout.addWidget(left_widget)
        
        # 우측: 현재 진행 현황 카드
        progress_card = PremiumCard("진행 현황", "📋")
        
        # 로그 메시지 표시 영역 (스크롤 가능)
        log_scroll = QScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll.setMinimumHeight(300)
        log_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 8px;
                background-color: {NAVER_BG};
            }}
        """)
        
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.log_label = QLabel("⏸️ 대기 중...")
        self.log_label.setFont(QFont(self.font_family, 13))
        self.log_label.setStyleSheet(f"color: {NAVER_TEXT_SUB}; background-color: transparent; padding: 10px;")
        self.log_label.setWordWrap(True)
        self.log_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
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
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(16)
        
        # 균등 분할
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        
        # === Row 0, Col 0: 네이버 로그인 정보 ===
        login_card = PremiumCard("네이버 로그인 정보", "👤")
        
        # 경고 라벨
        warning_label = QLabel("⚠️ 2차 인증 해제 필수")
        warning_label.setStyleSheet(f"""
            background-color: {NAVER_ORANGE}; 
            color: white; 
            padding: 4px 12px; 
            border-radius: 12px;
            font-size: 13px;
            font-weight: bold;
            border: none;
        """)
        login_card.header.layout().addWidget(warning_label)
        
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
        self.naver_id_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 10px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
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
        self.naver_pw_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 10px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        pw_container.addWidget(self.naver_pw_entry)
        self.pw_toggle_btn = QPushButton("👁️")
        self.pw_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pw_toggle_btn.setFixedSize(46, 46)
        self.pw_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_TEXT_SUB};
                border: none;
                border-radius: 10px;
                color: white;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {NAVER_TEXT};
            }}
        """)
        self.pw_toggle_btn.clicked.connect(self.toggle_password)
        pw_container.addWidget(self.pw_toggle_btn)
        pw_layout.addLayout(pw_container)
        login_grid.addWidget(pw_widget, 0, 1)
        
        login_card.content_layout.addLayout(login_grid)
        
        login_save_btn = QPushButton("💾 로그인 정보 저장")
        login_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_save_btn.setStyleSheet(f"background-color: {NAVER_GREEN}; padding: 8px 20px; font-size: 13px;")
        login_save_btn.clicked.connect(self.save_login_info)
        login_card.content_layout.addWidget(login_save_btn)
        
        # 카드 크기 최소화
        login_card.setMaximumHeight(login_card.sizeHint().height())
        
        layout.addWidget(login_card, 0, 0)
        
        # === Row 0, Col 1: 대기 시간 설정 ===
        time_card = PremiumCard("대기 시간 설정", "⏱️")
        
        # 대기 시간 입력 레이아웃
        time_input_layout = QVBoxLayout()
        time_input_layout.setSpacing(10)
        
        # 대기 시간 라벨
        time_main_label = PremiumCard.create_section_label("⏱️ 대기 시간 : 포스팅 완료 후 다음 포스팅 시작까지 대기 시간", self.font_family)
        time_input_layout.addWidget(time_main_label)
        
        # 입력 필드 레이아웃
        interval_input_layout = QHBoxLayout()
        interval_input_layout.setSpacing(10)
        
        self.interval_entry = QLineEdit()
        self.interval_entry.setPlaceholderText("10")
        self.interval_entry.setText("10")
        self.interval_entry.setFixedWidth(110)
        self.interval_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 10px;
                background-color: white;
                color: {NAVER_TEXT};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {NAVER_GREEN};
            }}
        """)
        interval_input_layout.addWidget(self.interval_entry)
        
        interval_text_label = PremiumCard.create_section_label("분 간격", self.font_family)
        interval_input_layout.addWidget(interval_text_label)
        interval_input_layout.addStretch()
        
        time_input_layout.addLayout(interval_input_layout)
        time_card.content_layout.addLayout(time_input_layout)
        
        time_save_btn = QPushButton("💾 대기 시간 저장")
        time_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        time_save_btn.setStyleSheet(f"background-color: {NAVER_GREEN}; padding: 8px 20px; font-size: 13px;")
        time_save_btn.clicked.connect(self.save_time_settings)
        time_card.content_layout.addWidget(time_save_btn)
        
        # 카드 크기 최소화
        time_card.setMaximumHeight(time_card.sizeHint().height())
        
        layout.addWidget(time_card, 0, 1)
        
        # === Row 1, Col 0: 외부 링크 설정 ===
        link_card = PremiumCard("외부 링크 설정", "🔗")
        
        # 헤더에 체크박스 추가
        self.use_link_checkbox = QCheckBox("사용")
        self.use_link_checkbox.setChecked(False)
        self.use_link_checkbox.setFont(QFont(self.font_family, 13, QFont.Weight.Bold))
        self.use_link_checkbox.setStyleSheet(f"color: {NAVER_TEXT}; background-color: transparent; border: none; margin-left: 10px;")
        self.use_link_checkbox.stateChanged.connect(self.toggle_external_link)
        link_card.header.layout().insertWidget(1, self.use_link_checkbox)
        
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
        self.link_url_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 10px;
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
        
        self.link_text_entry.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid {NAVER_BORDER};
                border-radius: 10px;
                padding: 10px;
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
        self.link_text_entry.focusInEvent = lambda e: self._clear_example_text(self.link_text_entry, "더 알아보기") if self.link_text_entry.isEnabled() else None
        text_layout.addWidget(self.link_text_entry)
        link_grid.addWidget(text_widget, 0, 1)
        
        link_card.content_layout.addLayout(link_grid)
        
        link_save_btn = QPushButton("💾 링크 설정 저장")
        link_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        link_save_btn.setStyleSheet(f"background-color: {NAVER_GREEN}; padding: 8px 20px; font-size: 13px;")
        link_save_btn.clicked.connect(self.save_link_settings)
        link_card.content_layout.addWidget(link_save_btn)
        
        # 카드 크기 최소화
        link_card.setMaximumHeight(link_card.sizeHint().height())
        
        layout.addWidget(link_card, 1, 0)
        
        # 초기 취소선 적용 (체크 해제 상태이므로)
        self.toggle_external_link()
        
        # === Row 1, Col 1: API 키 설정 ===
        api_card = PremiumCard("API 키 설정", "🔑")
        
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
        gpt_api_input_layout.addWidget(self.gpt_api_entry)
        
        self.gpt_toggle_btn = QPushButton("👁️")
        self.gpt_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gpt_toggle_btn.setFixedSize(40, 35)
        self.gpt_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_TEXT_SUB};
                border: none;
                border-radius: 8px;
                color: white;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {NAVER_TEXT};
            }}
        """)
        self.gpt_toggle_btn.clicked.connect(self.toggle_gpt_api_key)
        gpt_api_input_layout.addWidget(self.gpt_toggle_btn)
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
        gemini_api_input_layout.addWidget(self.gemini_api_entry)
        
        self.gemini_toggle_btn = QPushButton("👁️")
        self.gemini_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gemini_toggle_btn.setFixedSize(40, 35)
        self.gemini_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVER_TEXT_SUB};
                border: none;
                border-radius: 8px;
                color: white;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {NAVER_TEXT};
            }}
        """)
        self.gemini_toggle_btn.clicked.connect(self.toggle_gemini_api_key)
        gemini_api_input_layout.addWidget(self.gemini_toggle_btn)
        gemini_api_layout.addLayout(gemini_api_input_layout)
        
        api_grid.addWidget(gemini_api_widget, 0, 1)
        
        api_card.content_layout.addLayout(api_grid)
        
        # 버튼 레이아웃
        api_button_layout = QHBoxLayout()
        
        api_save_btn = QPushButton("💾 API 키 저장")
        api_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        api_save_btn.setStyleSheet(f"background-color: {NAVER_GREEN}; padding: 8px 20px; font-size: 13px;")
        api_save_btn.clicked.connect(self.save_api_key)
        api_button_layout.addWidget(api_save_btn)
        
        api_card.content_layout.addLayout(api_button_layout)
        
        # 카드 크기 최소화
        api_card.setMaximumHeight(api_card.sizeHint().height())
        
        layout.addWidget(api_card, 1, 1)
        
        # === Row 2, Col 0: 파일 관리 ===
        file_card = PremiumCard("파일 관리", "📁")
        
        file_grid = QGridLayout()
        file_grid.setColumnStretch(0, 1)
        file_grid.setColumnStretch(1, 1)
        
        # 키워드 파일
        keyword_widget = QWidget()
        keyword_widget.setStyleSheet("QWidget { background-color: transparent; }")
        keyword_layout = QHBoxLayout(keyword_widget)
        keyword_layout.setContentsMargins(0, 0, 0, 0)
        keyword_layout.setSpacing(10)
        
        keyword_label = PremiumCard.create_section_label("📝 키워드 파일", self.font_family)
        keyword_layout.addWidget(keyword_label)
        
        keyword_open_btn = QPushButton("📂 열기")
        keyword_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        keyword_open_btn.setStyleSheet(f"""
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
        keyword_open_btn.clicked.connect(lambda: self.open_file("keywords.txt"))
        keyword_layout.addWidget(keyword_open_btn, 1)
        
        file_grid.addWidget(keyword_widget, 0, 0)
        
        # 프롬프트 파일
        prompt_widget = QWidget()
        prompt_widget.setStyleSheet("QWidget { background-color: transparent; }")
        prompt_layout = QHBoxLayout(prompt_widget)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.setSpacing(10)
        
        prompt_label = PremiumCard.create_section_label("💬 프롬프트 파일", self.font_family)
        prompt_layout.addWidget(prompt_label)
        
        prompt_open_btn = QPushButton("📂 열기")
        prompt_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prompt_open_btn.setStyleSheet(f"""
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
        prompt_open_btn.clicked.connect(lambda: self.open_file("prompt.txt"))
        prompt_layout.addWidget(prompt_open_btn, 1)
        
        file_grid.addWidget(prompt_widget, 0, 1)
        
        file_card.content_layout.addLayout(file_grid)
        
        # 카드 크기 최소화
        file_card.setMaximumHeight(file_card.sizeHint().height())
        
        layout.addWidget(file_card, 2, 0)
        
        # === Row 2, Col 1: AI 모델 선택 ===
        ai_card = PremiumCard("AI 모델 선택", "🤖")
        
        from PyQt6.QtWidgets import QButtonGroup
        
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
        
        # 카드 크기 최소화
        ai_card.setMaximumHeight(ai_card.sizeHint().height())
        
        layout.addWidget(ai_card, 2, 1)
        
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
        
        self.update_status_display()
    
    def update_status_display(self):
        """상태 표시 업데이트"""
        # 로그인 정보 상태
        if self.naver_id_entry.text() and self.naver_pw_entry.text():
            self.login_status_label.setText("👤 로그인 정보: 설정 완료")
            self.login_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.login_setup_btn.hide()
        else:
            self.login_status_label.setText("👤 로그인 정보: 미설정")
            self.login_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.login_setup_btn.show()
        
        # API 키 상태
        gpt_key = self.gpt_api_entry.text() if hasattr(self, 'gpt_api_entry') else ""
        gemini_key = self.gemini_api_entry.text() if hasattr(self, 'gemini_api_entry') else ""
        
        if gpt_key or gemini_key:
            if gpt_key and gemini_key:
                self.api_status_label.setText("🔑 API 키: GPT + Gemini 설정")
            elif gpt_key:
                self.api_status_label.setText("🔑 API 키: GPT 설정")
            else:
                self.api_status_label.setText("🔑 API 키: Gemini 설정")
            self.api_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.api_setup_btn.hide()
        else:
            self.api_status_label.setText("🔑 API 키: 미설정")
            self.api_status_label.setStyleSheet(f"color: #000000; border: none;")
            self.api_setup_btn.show()
        
        # 키워드 개수
        keyword_count = self.count_keywords()
        self.keyword_count_label.setText(f"📦 키워드 개수: {keyword_count}개")
        
        if keyword_count > 0:
            self.keyword_count_label.setStyleSheet(f"color: #000000; border: none;")
            self.keyword_setup_btn.hide()
        else:
            self.keyword_count_label.setStyleSheet(f"color: #000000; border: none;")
            self.keyword_setup_btn.show()
        
        # 발행 간격
        interval = self.interval_entry.text() or "10"
        self.interval_label.setText(f"⏱️ 대기 시간: {interval}분")
    
    def count_keywords(self):
        """키워드 개수 카운트"""
        try:
            if os.path.exists("keywords.txt"):
                with open("keywords.txt", "r", encoding="utf-8") as f:
                    return len([line.strip() for line in f if line.strip()])
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
        else:
            self.gpt_api_entry.setEchoMode(QLineEdit.EchoMode.Password)
    
    def toggle_gemini_api_key(self):
        """Gemini API 키 표시/숨김"""
        if self.gemini_api_entry.echoMode() == QLineEdit.EchoMode.Password:
            self.gemini_api_entry.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.gemini_api_entry.setEchoMode(QLineEdit.EchoMode.Password)
    
    def toggle_password(self):
        """비밀번호 표시/숨김"""
        if self.naver_pw_entry.echoMode() == QLineEdit.EchoMode.Password:
            self.naver_pw_entry.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.naver_pw_entry.setEchoMode(QLineEdit.EchoMode.Password)
    
    def toggle_external_link(self):
        """외부 링크 활성화/비활성화"""
        enabled = self.use_link_checkbox.isChecked()
        
        # 활성화 상태 설정
        self.link_url_entry.setEnabled(enabled)
        self.link_text_entry.setEnabled(enabled)
        
        # 체크 시 링크 URL에 자동 포커스 및 텍스트 선택
        if enabled:
            self.link_url_entry.setFocus()
            self.link_url_entry.selectAll()
    
    def _clear_example_text(self, widget, example_text):
        """예시 텍스트 삭제"""
        if widget.text() == example_text:
            widget.clear()
    
    def open_file(self, filename):
        """파일 열기"""
        import subprocess
        import platform
        
        file_path = os.path.join(os.getcwd(), filename)
        
        if not os.path.exists(file_path):
            # 파일이 없으면 생성
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    if filename == "keywords.txt":
                        f.write("# 키워드를 한 줄에 하나씩 입력하세요\n")
                    elif filename == "prompt.txt":
                        f.write("# AI 프롬프트를 입력하세요\n")
                self.show_message("파일 생성", f"{filename} 파일을 생성했습니다.", "info")
            except Exception as e:
                self.show_message("오류", f"파일 생성 실패: {str(e)}", "error")
                return
        
        # 파일 열기
        try:
            if platform.system() == 'Windows':
                os.startfile(file_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', file_path])
            else:  # Linux
                subprocess.run(['xdg-open', file_path])
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 열기 실패: {str(e)}")
    
    def save_api_key(self):
        """API 키 저장"""
        self.config["gpt_api_key"] = self.gpt_api_entry.text()
        self.config["gemini_api_key"] = self.gemini_api_entry.text()
        # 구버전 호환성을 위해 api_key도 저장
        self.config["api_key"] = self.gpt_api_entry.text() if self.gpt_radio.isChecked() else self.gemini_api_entry.text()
        self.config["ai_model"] = "gpt" if self.gpt_radio.isChecked() else "gemini"
        self.save_config_file()
        self.update_status_display()
    
    def save_login_info(self):
        """로그인 정보 저장"""
        self.config["naver_id"] = self.naver_id_entry.text()
        self.config["naver_pw"] = self.naver_pw_entry.text()
        self.save_config_file()
        self.update_status_display()
    
    def save_time_settings(self):
        """발행 간격 저장"""
        self.config["interval"] = int(self.interval_entry.text() or "10")
        self.save_config_file()
        self.update_status_display()
    
    def toggle_time_selection(self):
        """더 이상 사용하지 않는 함수 (호환성 유지)"""
        pass
    
    def save_link_settings(self):
        """링크 설정 저장"""
        self.config["use_external_link"] = self.use_link_checkbox.isChecked()
        self.config["external_link"] = self.link_url_entry.text()
        self.config["external_link_text"] = self.link_text_entry.text()
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
        
        # 첫 시작일 때는 발행 간격 0, 아니면 설정된 간격 사용
        wait_interval = 0 if is_first_start else interval
        
        # 첫 시작일 때는 즉시 포스팅 시작 (발행 간격 대기 없음)
        if is_first_start:
            self.update_progress_status("🚀 첫 포스팅을 즉시 시작합니다...")
            print("🚀 첫 포스팅을 즉시 시작합니다...")
        else:
            self.update_progress_status(f"⏰ 발행 간격 {interval}분 대기 후 포스팅을 시작합니다...")
            print(f"⏰ 발행 간격 {interval}분 대기 후 포스팅을 시작합니다...")
        
        # 진행 상태 업데이트
        self.update_progress_status("🚀 포스팅 프로세스를 시작합니다...")
        print("🚀 포스팅 프로세스를 시작합니다...")
        
        # 자동화 바로 시작 (별도 스레드)
        def run_automation():
            try:
                external_link = self.link_url_entry.text() if self.use_link_checkbox.isChecked() else ""
                external_link_text = self.link_text_entry.text() if self.use_link_checkbox.isChecked() else ""
                
                start_automation(
                    naver_id=self.naver_id_entry.text(),
                    naver_pw=self.naver_pw_entry.text(),
                    api_key=api_key,
                    ai_model=ai_model,
                    theme="",
                    open_type="전체공개",
                    external_link=external_link,
                    external_link_text=external_link_text,
                    publish_time="now",  # 항상 현재 시간에 발행
                    scheduled_hour="00",
                    scheduled_minute="00",
                    wait_interval=wait_interval,  # 발행 간격 전달
                    callback=self.log_message
                )
                
                self.update_progress_status("✅ 포스팅이 완료되었습니다!")
                print("✅ 포스팅이 완료되었습니다!")
                
                # 포스팅 완료 후 다음 포스팅을 자동으로 시작
                if self.is_running and not self.is_paused:
                    self.update_progress_status("🔄 다음 포스팅을 준비합니다...")
                    print("🔄 다음 포스팅을 준비합니다...")
                    # 다음 포스팅은 발행 간격 대기가 필요함 (is_first_start=False)
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
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.show_message("⏹️ 정지", "포스팅을 정지했습니다.", "info")
    
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
        self.interval_label.setText(f"⏱️ 대기 시간: {interval}분")
    
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
            self.interval_label.setText(f"⏱️ 대기 시간: {interval}분")
            
            # 카운트다운 완료 후 자동으로 다음 포스팅 시작
            if self.is_running and not self.is_paused:
                self.update_progress_status("⏰ 발행 간격 완료 - 다음 포스팅을 시작합니다")
                print("⏰ 발행 간격 완료 - 다음 포스팅을 시작합니다")
                # start_posting()을 호출하지 않고 직접 실행 (is_first_start=False)
                self.start_posting(is_first_start=False)
    
    def log_message(self, message):
        """로그 메시지 출력 및 진행 상태 업데이트 (중복 방지)"""
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
            # 기존 로그에 새 메시지 추가 (중복 방지)
            current_log = self.log_label.text()
            
            # 중복 메시지 체크
            if current_log == "⏸️ 대기 중...":
                new_log = message
            else:
                # 마지막 로그와 동일하면 추가하지 않음
                last_message = current_log.split("\n")[-1] if "\n" in current_log else current_log
                if last_message.strip() != message.strip():
                    new_log = current_log + "\n" + message
                else:
                    return  # 중복이면 종료
            
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
    app = QApplication(sys.argv)
    
    # UTF-8 환경 확인
    print(f"✅ 시스템 인코딩: {sys.getdefaultencoding()}")
    print(f"✅ 파일 시스템 인코딩: {sys.getfilesystemencoding()}")
    
    window = NaverBlogGUI()
    window.show()
    
    sys.exit(app.exec())
