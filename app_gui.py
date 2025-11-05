"""
네이버 블로그 자동 포스팅 GUI 애플리케이션 v2.0
탭 구조 + 모니터링 기능 + 네이버 스타일 디자인
"""

import customtkinter as ctk
from tkinter import messagebox
import threading
import os
import json
from Auto_Naver import start_automation


# 네이버 스타일 색상 정의
NAVER_GREEN = "#03C75A"
NAVER_GREEN_HOVER = "#02B350"
NAVER_BG = "#FFFFFF"
NAVER_LIGHT_BG = "#F7F9FA"
NAVER_TEXT = "#1E1E23"
NAVER_GRAY = "#8E8E93"
NAVER_BORDER = "#E4E4E4"

# 블로그 주제 목록
BLOG_THEMES = {
    "엔터테인먼트·예술": ["문학·책", "영화", "미술·디자인", "공연·전시", "음악", "드라마", "스타·연예인", "만화·애니", "방송"],
    "생활·노하우·쇼핑": ["일상·생각", "육아·결혼", "반려동물", "좋은글·이미지", "패션·미용", "인테리어·DIY", "요리·레시피", "상품리뷰", "원예·재배"],
    "취미·여가·여행": ["게임", "스포츠", "사진", "자동차", "취미", "국내여행", "세계여행", "맛집"],
    "지식·동향": ["IT·컴퓨터", "사회·정치", "건강·의학", "비즈니스·경제", "어학·외국어", "교육·학문"]
}

# 설정 파일 경로
CONFIG_FILE = "config.json"


class NaverBlogApp(ctk.CTk):
    """네이버 블로그 자동 포스팅 GUI 애플리케이션"""
    
    def __init__(self):
        super().__init__()
        
        # 윈도우 설정
        self.title("네이버 블로그 AI 자동 포스팅 v2.0")
        self.geometry("900x700")
        self.resizable(True, True)
        
        # 테마 설정
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")
        self.configure(fg_color=NAVER_BG)
        
        # 설정 로드
        self.config = self.load_config()
        
        # 상태 변수
        self.is_running = False
        self.is_paused = False
        
        # 선택된 주제
        self.selected_theme = ctk.StringVar(value="")
        
        # GUI 구성
        self._create_widgets()
        
        # 저장된 설정 적용
        self._apply_config()
    
    def load_config(self):
        """설정 파일 로드"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_config(self):
        """설정 파일 저장"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("저장 실패", f"설정 저장 중 오류 발생:\n{str(e)}")
    
    def _create_widgets(self):
        """GUI 위젯 생성"""
        
        # 헤더
        header_frame = ctk.CTkFrame(self, fg_color=NAVER_GREEN, height=80, corner_radius=0)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="🤖 네이버 블로그 AI 자동 포스팅",
            font=ctk.CTkFont(family="맑은 고딕", size=26, weight="bold"),
            text_color="white"
        )
        title_label.pack(pady=20)
        
        # 탭뷰
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=NAVER_BG,
            segmented_button_fg_color=NAVER_LIGHT_BG,
            segmented_button_selected_color=NAVER_GREEN,
            segmented_button_selected_hover_color=NAVER_GREEN_HOVER,
            segmented_button_unselected_color=NAVER_LIGHT_BG,
            segmented_button_unselected_hover_color=NAVER_BORDER,
            text_color=NAVER_TEXT,
            corner_radius=0
        )
        self.tabview.pack(fill="both", expand=True, padx=0, pady=0)
        
        # 탭 추가
        self.tabview.add("📊 모니터링")
        self.tabview.add("⚙️ 설정")
        
        # 각 탭 구성
        self._create_monitoring_tab()
        self._create_settings_tab()
    
    def _create_monitoring_tab(self):
        """모니터링 탭 생성"""
        tab = self.tabview.tab("📊 모니터링")
        
        # 스크롤 프레임
        scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=NAVER_BG,
            scrollbar_button_color=NAVER_GRAY,
            scrollbar_button_hover_color=NAVER_GREEN
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 상태 정보 카드
        status_card = ctk.CTkFrame(scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        status_card.pack(fill="x", pady=(0, 15))
        
        status_title = ctk.CTkLabel(
            status_card,
            text="📈 실시간 상태",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        status_title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 키워드 개수
        keyword_frame = ctk.CTkFrame(status_card, fg_color="transparent")
        keyword_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(
            keyword_frame,
            text="키워드 개수:",
            font=ctk.CTkFont(family="맑은 고딕", size=14),
            text_color=NAVER_GRAY,
            anchor="w"
        ).pack(side="left", padx=(0, 10))
        
        self.keyword_count_label = ctk.CTkLabel(
            keyword_frame,
            text=f"{self.count_keywords()}개",
            font=ctk.CTkFont(family="맑은 고딕", size=14, weight="bold"),
            text_color=NAVER_GREEN,
            anchor="w"
        )
        self.keyword_count_label.pack(side="left")
        
        # AI 모델
        model_frame = ctk.CTkFrame(status_card, fg_color="transparent")
        model_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(
            model_frame,
            text="AI 모델:",
            font=ctk.CTkFont(family="맑은 고딕", size=14),
            text_color=NAVER_GRAY,
            anchor="w"
        ).pack(side="left", padx=(0, 10))
        
        ctk.CTkLabel(
            model_frame,
            text="Gemini 1.5 Flash",
            font=ctk.CTkFont(family="맑은 고딕", size=14, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        ).pack(side="left")
        
        # 예약 시간 (향후 기능)
        schedule_frame = ctk.CTkFrame(status_card, fg_color="transparent")
        schedule_frame.pack(fill="x", padx=20, pady=(5, 15))
        
        ctk.CTkLabel(
            schedule_frame,
            text="예약 시간:",
            font=ctk.CTkFont(family="맑은 고딕", size=14),
            text_color=NAVER_GRAY,
            anchor="w"
        ).pack(side="left", padx=(0, 10))
        
        ctk.CTkLabel(
            schedule_frame,
            text="즉시 실행",
            font=ctk.CTkFont(family="맑은 고딕", size=14, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        ).pack(side="left")
        
        # 컨트롤 버튼 카드
        control_card = ctk.CTkFrame(scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        control_card.pack(fill="x", pady=(0, 15))
        
        control_title = ctk.CTkLabel(
            control_card,
            text="🎮 포스팅 제어",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        control_title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 버튼 그리드
        button_grid = ctk.CTkFrame(control_card, fg_color="transparent")
        button_grid.pack(fill="x", padx=20, pady=(0, 15))
        
        # 시작 버튼
        self.start_btn = ctk.CTkButton(
            button_grid,
            text="▶️ 시작",
            font=ctk.CTkFont(family="맑은 고딕", size=15, weight="bold"),
            height=50,
            corner_radius=8,
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER,
            text_color="white",
            command=self.start_posting
        )
        self.start_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        # 정지 버튼
        self.stop_btn = ctk.CTkButton(
            button_grid,
            text="⏹️ 정지",
            font=ctk.CTkFont(family="맑은 고딕", size=15, weight="bold"),
            height=50,
            corner_radius=8,
            fg_color="#FF3B30",
            hover_color="#CC2F26",
            text_color="white",
            state="disabled",
            command=self.stop_posting
        )
        self.stop_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # 일시정지 버튼
        self.pause_btn = ctk.CTkButton(
            button_grid,
            text="⏸️ 일시정지",
            font=ctk.CTkFont(family="맑은 고딕", size=15, weight="bold"),
            height=50,
            corner_radius=8,
            fg_color="#FF9500",
            hover_color="#CC7700",
            text_color="white",
            state="disabled",
            command=self.pause_posting
        )
        self.pause_btn.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        
        # 재개 버튼
        self.resume_btn = ctk.CTkButton(
            button_grid,
            text="▶️ 재개",
            font=ctk.CTkFont(family="맑은 고딕", size=15, weight="bold"),
            height=50,
            corner_radius=8,
            fg_color="#007AFF",
            hover_color="#0062CC",
            text_color="white",
            state="disabled",
            command=self.resume_posting
        )
        self.resume_btn.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        button_grid.grid_columnconfigure(0, weight=1)
        button_grid.grid_columnconfigure(1, weight=1)
        
        # 진행 상황 카드
        progress_card = ctk.CTkFrame(scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        progress_card.pack(fill="both", expand=True)
        
        progress_title = ctk.CTkLabel(
            progress_card,
            text="📝 진행 상황",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        progress_title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 로그 텍스트박스
        self.log_text = ctk.CTkTextbox(
            progress_card,
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            fg_color=NAVER_BG,
            text_color=NAVER_TEXT,
            height=200,
            corner_radius=8,
            border_width=1,
            border_color=NAVER_BORDER
        )
        self.log_text.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log_text.insert("1.0", "✅ 준비 완료. '시작' 버튼을 눌러주세요.\n")
        self.log_text.configure(state="disabled")
    
    def _create_settings_tab(self):
        """설정 탭 생성"""
        tab = self.tabview.tab("⚙️ 설정")
        
        # 스크롤 프레임
        scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=NAVER_BG,
            scrollbar_button_color=NAVER_GRAY,
            scrollbar_button_hover_color=NAVER_GREEN
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 파일 열기 섹션
        self._create_file_section(scroll)
        
        # API 키 섹션
        self._create_api_section(scroll)
        
        # 로그인 정보 섹션
        self._create_login_section(scroll)
        
        # 주제 설정 섹션
        self._create_theme_section(scroll)
        
        # 외부 링크 섹션
        self._create_link_section(scroll)
        
        # 포스팅 설정 섹션
        self._create_posting_section(scroll)
    
    def _create_file_section(self, parent):
        """파일 열기 섹션"""
        card = ctk.CTkFrame(parent, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        card.pack(fill="x", pady=(0, 15))
        
        title = ctk.CTkLabel(
            card,
            text="📁 파일 관리",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 버튼 그리드
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        files = [
            ("keywords.txt", "키워드 파일"),
            ("prompt.txt", "프롬프트 파일")
        ]
        
        for i, (filename, label) in enumerate(files):
            btn = ctk.CTkButton(
                btn_frame,
                text=f"📄 {label} 열기",
                font=ctk.CTkFont(family="맑은 고딕", size=13),
                height=40,
                corner_radius=8,
                fg_color=NAVER_GREEN,
                hover_color=NAVER_GREEN_HOVER,
                text_color="white",
                command=lambda f=filename: self.open_file(f)
            )
            btn.grid(row=i//2, column=i%2, padx=5, pady=5, sticky="ew")
        
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
    
    def _create_api_section(self, parent):
        """API 키 섹션"""
        card = ctk.CTkFrame(parent, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        card.pack(fill="x", pady=(0, 15))
        
        title = ctk.CTkLabel(
            card,
            text="🔑 Gemini API 키",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        title.pack(fill="x", padx=20, pady=(15, 10))
        
        # API 키 입력
        api_frame = ctk.CTkFrame(card, fg_color="transparent")
        api_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        self.api_entry = ctk.CTkEntry(
            api_frame,
            placeholder_text="Gemini API 키를 입력하세요",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_BORDER,
            fg_color=NAVER_BG,
            show="*"
        )
        self.api_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # 공개/비공개 토글
        self.api_show_var = ctk.BooleanVar(value=False)
        api_toggle = ctk.CTkCheckBox(
            api_frame,
            text="표시",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            variable=self.api_show_var,
            command=self.toggle_api_visibility,
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER,
            text_color=NAVER_TEXT
        )
        api_toggle.pack(side="left")
        
        # 저장 버튼
        save_btn = ctk.CTkButton(
            card,
            text="💾 API 키 저장",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER,
            text_color="white",
            command=self.save_api_key
        )
        save_btn.pack(fill="x", padx=20, pady=(0, 15))
    
    def _create_login_section(self, parent):
        """로그인 정보 섹션"""
        card = ctk.CTkFrame(parent, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        card.pack(fill="x", pady=(0, 15))
        
        title = ctk.CTkLabel(
            card,
            text="👤 네이버 로그인 정보",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 아이디
        id_label = ctk.CTkLabel(
            card,
            text="아이디",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            text_color=NAVER_GRAY,
            anchor="w"
        )
        id_label.pack(fill="x", padx=20, pady=(5, 2))
        
        self.id_entry = ctk.CTkEntry(
            card,
            placeholder_text="네이버 아이디",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_BORDER,
            fg_color=NAVER_BG
        )
        self.id_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 비밀번호
        pw_label = ctk.CTkLabel(
            card,
            text="비밀번호",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            text_color=NAVER_GRAY,
            anchor="w"
        )
        pw_label.pack(fill="x", padx=20, pady=(5, 2))
        
        pw_frame = ctk.CTkFrame(card, fg_color="transparent")
        pw_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        self.pw_entry = ctk.CTkEntry(
            pw_frame,
            placeholder_text="비밀번호",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_BORDER,
            fg_color=NAVER_BG,
            show="*"
        )
        self.pw_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # 공개/비공개 토글
        self.pw_show_var = ctk.BooleanVar(value=False)
        pw_toggle = ctk.CTkCheckBox(
            pw_frame,
            text="표시",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            variable=self.pw_show_var,
            command=self.toggle_pw_visibility,
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER,
            text_color=NAVER_TEXT
        )
        pw_toggle.pack(side="left")
        
        # 저장 버튼
        save_btn = ctk.CTkButton(
            card,
            text="💾 로그인 정보 저장",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER,
            text_color="white",
            command=self.save_login_info
        )
        save_btn.pack(fill="x", padx=20, pady=(0, 15))
    
    def _create_theme_section(self, parent):
        """주제 설정 섹션"""
        card = ctk.CTkFrame(parent, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        card.pack(fill="x", pady=(0, 15))
        
        title = ctk.CTkLabel(
            card,
            text="📂 블로그 주제",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        title.pack(fill="x", padx=20, pady=(15, 5))
        
        desc = ctk.CTkLabel(
            card,
            text="주제를 선택하면 블로그 홈에서 주제별로 글을 볼 수 있습니다.",
            font=ctk.CTkFont(family="맑은 고딕", size=11),
            text_color=NAVER_GRAY,
            anchor="w",
            wraplength=800
        )
        desc.pack(fill="x", padx=20, pady=(0, 10))
        
        # 주제 선택 안 함
        no_theme_rb = ctk.CTkRadioButton(
            card,
            text="주제 선택 안 함",
            variable=self.selected_theme,
            value="",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            text_color=NAVER_TEXT,
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER
        )
        no_theme_rb.pack(anchor="w", padx=20, pady=(5, 10))
        no_theme_rb.select()
        
        # 카테고리별 주제
        for category, themes in BLOG_THEMES.items():
            cat_label = ctk.CTkLabel(
                card,
                text=f"▪ {category}",
                font=ctk.CTkFont(family="맑은 고딕", size=13, weight="bold"),
                text_color=NAVER_TEXT,
                anchor="w"
            )
            cat_label.pack(fill="x", padx=20, pady=(10, 5))
            
            cat_frame = ctk.CTkFrame(card, fg_color="transparent")
            cat_frame.pack(fill="x", padx=40, pady=(0, 5))
            
            for i, theme in enumerate(themes):
                rb = ctk.CTkRadioButton(
                    cat_frame,
                    text=theme,
                    variable=self.selected_theme,
                    value=theme,
                    font=ctk.CTkFont(family="맑은 고딕", size=12),
                    text_color=NAVER_TEXT,
                    fg_color=NAVER_GREEN,
                    hover_color=NAVER_GREEN_HOVER
                )
                rb.grid(row=i//4, column=i%4, sticky="w", padx=10, pady=3)
            
            for col in range(4):
                cat_frame.grid_columnconfigure(col, weight=1)
        
        ctk.CTkLabel(card, text="", height=10).pack()
    
    def _create_link_section(self, parent):
        """외부 링크 섹션"""
        card = ctk.CTkFrame(parent, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        card.pack(fill="x", pady=(0, 15))
        
        title = ctk.CTkLabel(
            card,
            text="🔗 외부 링크",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 사용 여부
        self.link_enabled_var = ctk.BooleanVar(value=False)
        link_check = ctk.CTkCheckBox(
            card,
            text="외부 링크 사용",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            variable=self.link_enabled_var,
            command=self.toggle_link_inputs,
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER,
            text_color=NAVER_TEXT
        )
        link_check.pack(anchor="w", padx=20, pady=(0, 10))
        
        # URL
        url_label = ctk.CTkLabel(
            card,
            text="링크 URL",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            text_color=NAVER_GRAY,
            anchor="w"
        )
        url_label.pack(fill="x", padx=20, pady=(5, 2))
        
        self.link_url_entry = ctk.CTkEntry(
            card,
            placeholder_text="https://example.com",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_BORDER,
            fg_color=NAVER_BG,
            state="disabled"
        )
        self.link_url_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 텍스트
        text_label = ctk.CTkLabel(
            card,
            text="링크 텍스트",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            text_color=NAVER_GRAY,
            anchor="w"
        )
        text_label.pack(fill="x", padx=20, pady=(5, 2))
        
        self.link_text_entry = ctk.CTkEntry(
            card,
            placeholder_text="더 자세한 내용 보기",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_BORDER,
            fg_color=NAVER_BG,
            state="disabled"
        )
        self.link_text_entry.pack(fill="x", padx=20, pady=(0, 15))
    
    def _create_posting_section(self, parent):
        """포스팅 설정 섹션"""
        card = ctk.CTkFrame(parent, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        card.pack(fill="x", pady=(0, 15))
        
        title = ctk.CTkLabel(
            card,
            text="⚙️ 포스팅 설정",
            font=ctk.CTkFont(family="맑은 고딕", size=18, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 공개 설정
        open_label = ctk.CTkLabel(
            card,
            text="공개 설정",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            text_color=NAVER_GRAY,
            anchor="w"
        )
        open_label.pack(fill="x", padx=20, pady=(5, 2))
        
        self.open_combobox = ctk.CTkComboBox(
            card,
            values=["전체공개", "이웃공개", "서로이웃공개", "비공개"],
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            dropdown_font=ctk.CTkFont(family="맑은 고딕", size=12),
            height=40,
            corner_radius=8,
            border_color=NAVER_BORDER,
            fg_color=NAVER_BG,
            button_color=NAVER_GREEN,
            button_hover_color=NAVER_GREEN_HOVER
        )
        self.open_combobox.set("전체공개")
        self.open_combobox.pack(fill="x", padx=20, pady=(0, 15))
    
    # 유틸리티 함수들
    
    def count_keywords(self):
        """키워드 개수 세기"""
        try:
            if os.path.exists("keywords.txt"):
                with open("keywords.txt", 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    keywords = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
                    return len(keywords)
        except:
            pass
        return 0
    
    def open_file(self, filename):
        """파일 열기"""
        try:
            os.startfile(filename)
        except Exception as e:
            messagebox.showerror("오류", f"파일 열기 실패:\n{str(e)}")
    
    def toggle_api_visibility(self):
        """API 키 표시/숨김"""
        if self.api_show_var.get():
            self.api_entry.configure(show="")
        else:
            self.api_entry.configure(show="*")
    
    def toggle_pw_visibility(self):
        """비밀번호 표시/숨김"""
        if self.pw_show_var.get():
            self.pw_entry.configure(show="")
        else:
            self.pw_entry.configure(show="*")
    
    def toggle_link_inputs(self):
        """외부 링크 입력 필드 활성화/비활성화"""
        if self.link_enabled_var.get():
            self.link_url_entry.configure(state="normal")
            self.link_text_entry.configure(state="normal")
        else:
            self.link_url_entry.configure(state="disabled")
            self.link_text_entry.configure(state="disabled")
    
    def save_api_key(self):
        """API 키 저장"""
        api_key = self.api_entry.get().strip()
        if not api_key:
            messagebox.showwarning("경고", "API 키를 입력해주세요.")
            return
        
        self.config['api_key'] = api_key
        self.save_config()
        messagebox.showinfo("저장 완료", "API 키가 저장되었습니다.")
    
    def save_login_info(self):
        """로그인 정보 저장"""
        naver_id = self.id_entry.get().strip()
        naver_pw = self.pw_entry.get().strip()
        
        if not naver_id or not naver_pw:
            messagebox.showwarning("경고", "아이디와 비밀번호를 모두 입력해주세요.")
            return
        
        self.config['naver_id'] = naver_id
        self.config['naver_pw'] = naver_pw
        self.save_config()
        messagebox.showinfo("저장 완료", "로그인 정보가 저장되었습니다.")
    
    def _apply_config(self):
        """저장된 설정 적용"""
        if 'api_key' in self.config:
            self.api_entry.insert(0, self.config['api_key'])
        if 'naver_id' in self.config:
            self.id_entry.insert(0, self.config['naver_id'])
        if 'naver_pw' in self.config:
            self.pw_entry.insert(0, self.config['naver_pw'])
    
    def log_message(self, message):
        """로그 메시지 추가"""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    
    def validate_inputs(self):
        """입력값 검증"""
        api_key = self.api_entry.get().strip()
        naver_id = self.id_entry.get().strip()
        naver_pw = self.pw_entry.get().strip()
        
        if not api_key:
            messagebox.showerror("입력 오류", "Gemini API 키를 입력해주세요.")
            self.tabview.set("⚙️ 설정")
            return False
        
        if not naver_id:
            messagebox.showerror("입력 오류", "네이버 아이디를 입력해주세요.")
            self.tabview.set("⚙️ 설정")
            return False
        
        if not naver_pw:
            messagebox.showerror("입력 오류", "비밀번호를 입력해주세요.")
            self.tabview.set("⚙️ 설정")
            return False
        
        return True
    
    # 포스팅 제어 함수들
    
    def start_posting(self):
        """포스팅 시작"""
        if self.is_running:
            messagebox.showwarning("실행 중", "이미 포스팅이 진행 중입니다.")
            return
        
        if not self.validate_inputs():
            return
        
        response = messagebox.askyesno(
            "포스팅 확인",
            "AI가 keywords.txt의 키워드로 글을 작성하여\n네이버 블로그에 자동으로 게시합니다.\n\n계속하시겠습니까?"
        )
        
        if not response:
            return
        
        self.is_running = True
        self.is_paused = False
        
        # 버튼 상태 변경
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.pause_btn.configure(state="normal")
        self.resume_btn.configure(state="disabled")
        
        # 모니터링 탭으로 전환
        self.tabview.set("📊 모니터링")
        
        self.log_message("⏳ 포스팅 시작...")
        
        # 데이터 수집
        api_key = self.api_entry.get().strip()
        naver_id = self.id_entry.get().strip()
        naver_pw = self.pw_entry.get().strip()
        theme = self.selected_theme.get()
        open_type = self.open_combobox.get()
        
        external_link = ""
        external_link_text = ""
        if self.link_enabled_var.get():
            external_link = self.link_url_entry.get().strip()
            external_link_text = self.link_text_entry.get().strip()
        
        # 스레드로 실행
        thread = threading.Thread(
            target=self.run_automation,
            args=(naver_id, naver_pw, api_key, theme, open_type, external_link, external_link_text),
            daemon=True
        )
        thread.start()
    
    def stop_posting(self):
        """포스팅 정지"""
        if messagebox.askyesno("정지 확인", "포스팅을 정지하시겠습니까?"):
            self.is_running = False
            self.is_paused = False
            
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.pause_btn.configure(state="disabled")
            self.resume_btn.configure(state="disabled")
            
            self.log_message("⏹️ 포스팅이 정지되었습니다.")
    
    def pause_posting(self):
        """포스팅 일시정지"""
        self.is_paused = True
        
        self.pause_btn.configure(state="disabled")
        self.resume_btn.configure(state="normal")
        
        self.log_message("⏸️ 포스팅이 일시정지되었습니다.")
    
    def resume_posting(self):
        """포스팅 재개"""
        self.is_paused = False
        
        self.pause_btn.configure(state="normal")
        self.resume_btn.configure(state="disabled")
        
        self.log_message("▶️ 포스팅을 재개합니다.")
    
    def run_automation(self, naver_id, naver_pw, api_key, theme, open_type, external_link, external_link_text):
        """자동화 실행"""
        try:
            success = start_automation(
                naver_id=naver_id,
                naver_pw=naver_pw,
                gemini_api_key=api_key,
                theme=theme,
                open_type=open_type,
                external_link=external_link,
                external_link_text=external_link_text,
                callback=lambda msg: self.after(0, self.log_message, msg)
            )
            
            if success:
                self.after(0, lambda: messagebox.showinfo(
                    "성공",
                    "AI 포스팅이 성공적으로 완료되었습니다! 🎉"
                ))
                self.after(0, self.log_message, "✅ 포스팅 성공!")
            else:
                self.after(0, lambda: messagebox.showerror(
                    "실패",
                    "포스팅에 실패했습니다.\n로그를 확인해주세요."
                ))
                self.after(0, self.log_message, "❌ 포스팅 실패")
        
        except Exception as e:
            self.after(0, lambda: messagebox.showerror(
                "오류",
                f"오류가 발생했습니다:\n{str(e)}"
            ))
            self.after(0, self.log_message, f"❌ 오류: {str(e)}")
        
        finally:
            self.is_running = False
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            self.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.after(0, lambda: self.pause_btn.configure(state="disabled"))
            self.after(0, lambda: self.resume_btn.configure(state="disabled"))
    
    def run(self):
        """애플리케이션 실행"""
        self.mainloop()


def main():
    """메인 함수"""
    app = NaverBlogApp()
    app.run()


if __name__ == "__main__":
    main()
