# -*- coding: utf-8 -*-
"""
네이버 블로그 자동화 모듈
Selenium을 사용하여 네이버 로그인 및 블로그 포스팅을 자동화합니다.
Gemini AI를 활용하여 자동으로 블로그 글을 생성합니다.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
import google.generativeai as genai
import time
import os


class NaverBlogAutomation:
    """네이버 블로그 자동 포스팅 클래스"""
    
    def __init__(self, naver_id, naver_pw, gemini_api_key, theme="", 
                 open_type="전체공개", external_link="", external_link_text="", callback=None):
        """초기화 함수"""
        self.naver_id = naver_id
        self.naver_pw = naver_pw
        self.gemini_api_key = gemini_api_key
        self.theme = theme
        self.open_type = open_type
        self.external_link = external_link
        self.external_link_text = external_link_text
        self.callback = callback
        self.driver = None
        
        # Gemini API 설정
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    def _update_status(self, message):
        """상태 메시지 업데이트"""
        if self.callback:
            self.callback(message)
        print(message)
    
    def load_keywords(self):
        """keywords.txt 파일에서 키워드 로드"""
        try:
            keywords_file = "keywords.txt"
            if os.path.exists(keywords_file):
                with open(keywords_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    keywords = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
                    return ', '.join(keywords)
            else:
                self._update_status("경고: keywords.txt 파일이 없습니다.")
                return ""
        except Exception as e:
            self._update_status(f"키워드 로드 오류: {str(e)}")
            return ""
    
    def generate_content_with_gemini(self):
        """Gemini API를 사용하여 블로그 글 생성 (keywords만 사용)"""
        try:
            self._update_status("AI를 사용하여 글을 생성하는 중...")
            
            # keywords.txt에서 키워드 로드
            keywords = self.load_keywords()
            self._update_status(f"키워드: {keywords}")
            
            # prompt.txt 파일 읽기
            prompt_file = "prompt.txt"
            if os.path.exists(prompt_file):
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_template = f.read()
                # {keywords}만 사용
                prompt = prompt_template.replace('{keywords}', keywords)
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
"""
            
            # Gemini API 호출
            response = self.model.generate_content(prompt)
            content = response.text
            
            # 제목과 본문 분리 (첫 줄을 제목으로)
            lines = content.strip().split('\n')
            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()
            
            self._update_status("AI 글 생성 완료!")
            return title, body
            
        except Exception as e:
            self._update_status(f"AI 글 생성 오류: {str(e)}")
            return None, None
    
    def setup_driver(self):
        """크롬 드라이버 설정"""
        try:
            self._update_status("브라우저를 실행하는 중...")
            
            options = webdriver.ChromeOptions()
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--start-maximized")
            
            prefs = {"profile.default_content_setting_values.notifications": 2}
            options.add_experimental_option("prefs", prefs)
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            self._update_status("브라우저 실행 완료")
            return True
            
        except Exception as e:
            self._update_status(f"브라우저 실행 실패: {str(e)}")
            return False
    
    def login(self):
        """네이버 로그인"""
        try:
            self._update_status("네이버 접속 중...")
            
            self.driver.get("https://www.naver.com")
            time.sleep(2)
            
            self._update_status("로그인 버튼 클릭 중...")
            
            try:
                login_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".MyView-module__link_login___HpHMW"))
                )
                login_btn.click()
                time.sleep(2)
            except:
                self.driver.get("https://nid.naver.com/nidlogin.login")
                time.sleep(2)
            
            self._update_status("로그인 정보 입력 중...")
            
            id_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".input_item.id"))
            )
            self.driver.execute_script(f"arguments[0].value = '{self.naver_id}'", id_input)
            time.sleep(0.5)
            
            pw_input = self.driver.find_element(By.CSS_SELECTOR, ".input_item.pw")
            self.driver.execute_script(f"arguments[0].value = '{self.naver_pw}'", pw_input)
            time.sleep(0.5)
            
            login_button = self.driver.find_element(By.ID, "log.login")
            login_button.click()
            
            self._update_status("로그인 처리 중...")
            time.sleep(3)
            
            if "naver.com" in self.driver.current_url and "nidlogin" not in self.driver.current_url:
                self._update_status("로그인 성공!")
                return True
            else:
                self._update_status("로그인 실패: 아이디/비밀번호를 확인해주세요")
                return False
                
        except Exception as e:
            self._update_status(f"로그인 오류: {str(e)}")
            return False
    
    def write_post(self, title, content):
        """블로그 글 작성"""
        try:
            self._update_status("블로그 페이지로 이동 중...")
            
            self.driver.get("https://section.blog.naver.com/BlogHome.naver?directoryNo=0&currentPage=1&groupId=0")
            time.sleep(3)
            
            self._update_status("글쓰기 버튼 클릭 중...")
            
            try:
                write_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".sp_common.icon_write"))
                )
                write_btn.click()
                time.sleep(3)
            except:
                self.driver.get("https://blog.naver.com/my/post/write.naver")
                time.sleep(3)
            
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
                time.sleep(2)
            
            self._update_status("제목 입력 중...")
            
            try:
                iframe = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "mainFrame"))
                )
                self.driver.switch_to.frame(iframe)
                time.sleep(1)
            except:
                self._update_status("iframe 전환 실패 - 메인 프레임에서 진행")
            
            try:
                title_elem = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".se-section.se-section-documentTitle"))
                )
                title_elem.click()
                time.sleep(0.5)
                
                title_input = title_elem.find_element(By.CSS_SELECTOR, "p, div, span")
                title_input.send_keys(title)
                time.sleep(1)
            except Exception as e:
                self._update_status(f"제목 입력 실패: {str(e)}")
            
            self._update_status("본문 입력 중...")
            
            try:
                content_elem = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".se-section.se-section-text"))
                )
                content_elem.click()
                time.sleep(0.5)
                
                content_input = content_elem.find_element(By.CSS_SELECTOR, "p, div")
                
                # 본문을 서론과 나머지로 분리하여 외부 링크를 서론 다음에 삽입
                content_lines = content.split('\n')
                intro_ended = False
                
                for i, line in enumerate(content_lines):
                    if line.strip():
                        content_input.send_keys(line)
                        content_input.send_keys(Keys.SHIFT + Keys.ENTER)
                        time.sleep(0.1)
                        
                        # 서론 끝 감지 (첫 2-3 문단)
                        if not intro_ended and i >= 2:
                            intro_ended = True
                            
                            # 외부 링크를 서론 다음에 삽입
                            if self.external_link:
                                self._update_status("외부 링크 추가 중 (서론 다음)...")
                                content_input.send_keys(Keys.SHIFT + Keys.ENTER)
                                content_input.send_keys(Keys.SHIFT + Keys.ENTER)
                                link_text = self.external_link_text if self.external_link_text else self.external_link
                                content_input.send_keys(f"{link_text}: {self.external_link}")
                                content_input.send_keys(Keys.SHIFT + Keys.ENTER)
                                content_input.send_keys(Keys.SHIFT + Keys.ENTER)
                                time.sleep(0.5)
                
                time.sleep(1)
            except Exception as e:
                self._update_status(f"본문 입력 실패: {str(e)}")
            
            self._update_status("발행 설정 중...")
            
            self.driver.switch_to.default_content()
            time.sleep(1)
            
            try:
                publish_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".publish_btn__m9KHH"))
                )
                publish_btn.click()
                time.sleep(2)
            except Exception as e:
                self._update_status(f"발행 버튼 클릭 실패: {str(e)}")
            
            # 주제 설정
            if self.theme:
                self._update_status(f"주제 설정 중: {self.theme}")
                try:
                    theme_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".set_theme__KLbnU"))
                    )
                    theme_btn.click()
                    time.sleep(1)
                    
                    theme_label = self.driver.find_element(By.XPATH, f"//label[contains(text(), '{self.theme}')]")
                    theme_label.click()
                    time.sleep(0.5)
                    
                    ok_btn = self.driver.find_element(By.CSS_SELECTOR, ".ok_btn__mVM4b")
                    ok_btn.click()
                    time.sleep(1)
                except Exception as e:
                    self._update_status(f"주제 설정 실패: {str(e)}")
            
            # 공개 설정
            self._update_status(f"공개 설정: {self.open_type}")
            try:
                open_type_map = {
                    "전체공개": "open_public",
                    "이웃공개": "open_neighbor",
                    "서로이웃공개": "open_both_neighbor",
                    "비공개": "open_private"
                }
                
                open_type_id = open_type_map.get(self.open_type, "open_public")
                open_radio = self.driver.find_element(By.ID, open_type_id)
                self.driver.execute_script("arguments[0].click();", open_radio)
                time.sleep(0.5)
            except Exception as e:
                self._update_status(f"공개 설정 실패: {str(e)}")
            
            # 태그 입력 (최대 3개, keywords.txt에서 가져옴)
            self._update_status("태그 입력 중...")
            try:
                keywords = self.load_keywords()
                # 최대 3개만 사용
                tags = [k.strip() for k in keywords.split(',')[:3]]
                
                tag_textarea = self.driver.find_element(By.CSS_SELECTOR, ".tag_textarea__CD7pC")
                tag_textarea.click()
                time.sleep(0.5)
                
                for tag in tags:
                    if tag:
                        tag_textarea.send_keys(tag)
                        tag_textarea.send_keys(Keys.ENTER)
                        time.sleep(0.3)
            except Exception as e:
                self._update_status(f"태그 입력 실패: {str(e)}")
            
            self._update_status("최종 발행 중...")
            
            try:
                final_publish_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn_area__fO7mp button"))
                )
                final_publish_btn.click()
                time.sleep(3)
                
                self._update_status("포스팅 성공! ")
                return True
            except Exception as e:
                self._update_status(f"최종 발행 실패: {str(e)}")
                return False
            
        except Exception as e:
            self._update_status(f"포스팅 오류: {str(e)}")
            return False
    
    def run(self):
        """전체 프로세스 실행"""
        try:
            title, content = self.generate_content_with_gemini()
            if not title or not content:
                return False
            
            if not self.setup_driver():
                return False
            
            if not self.login():
                return False
            
            if not self.write_post(title, content):
                return False
            
            time.sleep(2)
            return True
            
        except Exception as e:
            self._update_status(f"실행 오류: {str(e)}")
            return False
    
    def close(self):
        """브라우저 종료"""
        if self.driver:
            self._update_status("브라우저 종료 중...")
            self.driver.quit()
            self._update_status("작업 완료")


def start_automation(naver_id, naver_pw, gemini_api_key, theme="", 
                     open_type="전체공개", external_link="", external_link_text="", callback=None):
    """자동화 시작 함수"""
    automation = NaverBlogAutomation(
        naver_id, naver_pw, gemini_api_key, 
        theme, open_type, external_link, external_link_text, callback
    )
    return automation.run()
