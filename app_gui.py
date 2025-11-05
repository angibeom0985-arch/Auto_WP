"""
네이버 블로그 자동 포스팅 GUI 애플리케이션
CustomTkinter를 사용한 네이버 스타일의 GUI + Gemini AI 연동
"""

import customtkinter as ctk
from tkinter import messagebox
import threading
from Auto_Naver import start_automation


# 네이버 스타일 색상 정의
NAVER_GREEN = "#03C75A"
NAVER_GREEN_HOVER = "#02B350"
NAVER_BG = "#FFFFFF"
NAVER_LIGHT_BG = "#F5F7F8"
NAVER_TEXT = "#000000"
NAVER_GRAY = "#C4C4C4"

# 블로그 주제 목록 (사진과 동일한 구조)
BLOG_THEMES = {
    "엔터테인먼트·예술": ["문학·책", "영화", "미술·디자인", "공연·전시", "음악", "드라마", "스타·연예인", "만화·애니", "방송"],
    "생활·노하우·쇼핑": ["일상·생각", "육아·결혼", "반려동물", "좋은글·이미지", "패션·미용", "인테리어·DIY", "요리·레시피", "상품리뷰", "원예·재배"],
    "취미·여가·여행": ["게임", "스포츠", "사진", "자동차", "취미", "국내여행", "세계여행", "맛집"],
    "지식·동향": ["IT·컴퓨터", "사회·정치", "건강·의학", "비즈니스·경제", "어학·외국어", "교육·학문"]
}


class NaverBlogApp(ctk.CTk):
    """네이버 블로그 자동 포스팅 GUI 애플리케이션"""
    
    def __init__(self):
        super().__init__()
        
        # 윈도우 설정
        self.title("네이버 블로그 AI 자동 포스팅")
        self.geometry("850x1000")
        self.resizable(True, True)
        
        # 테마 설정 (라이트 모드)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")
        
        # 배경색 설정
        self.configure(fg_color=NAVER_BG)
        
        # 선택된 주제를 저장할 변수
        self.selected_theme = ctk.StringVar(value="")
        
        # GUI 구성
        self._create_widgets()
        
        # 자동화 실행 상태
        self.is_running = False
    
    def _create_widgets(self):
        """GUI 위젯 생성"""
        
        # 스크롤 가능한 메인 컨테이너
        main_scroll = ctk.CTkScrollableFrame(self, fg_color=NAVER_BG)
        main_scroll.pack(fill="both", expand=True, padx=30, pady=30)
        
        # ===== 헤더 섹션 =====
        header_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_BG)
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="🤖 네이버 블로그 AI 자동 포스팅",
            font=ctk.CTkFont(family="맑은 고딕", size=24, weight="bold"),
            text_color=NAVER_TEXT
        )
        title_label.pack()
        
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Gemini AI가 keywords.txt 파일의 키워드로 블로그 글을 자동 작성합니다",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            text_color=NAVER_GRAY
        )
        subtitle_label.pack(pady=(5, 0))
        
        # 구분선
        separator1 = ctk.CTkFrame(main_scroll, height=2, fg_color=NAVER_LIGHT_BG)
        separator1.pack(fill="x", pady=10)
        
        # ===== API 키 섹션 =====
        api_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        api_frame.pack(fill="x", pady=(0, 20))
        
        api_title = ctk.CTkLabel(
            api_frame,
            text="🔑 Gemini API 키",
            font=ctk.CTkFont(family="맑은 고딕", size=16, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        api_title.pack(fill="x", padx=20, pady=(15, 10))
        
        self.api_entry = ctk.CTkEntry(
            api_frame,
            placeholder_text="Gemini API 키를 입력하세요 (https://aistudio.google.com/)",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_GRAY,
            fg_color=NAVER_BG,
            show="*"
        )
        self.api_entry.pack(fill="x", padx=20, pady=(0, 15))
        
        # ===== 로그인 섹션 =====
        login_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        login_frame.pack(fill="x", pady=(0, 20))
        
        login_title = ctk.CTkLabel(
            login_frame,
            text="🔐 네이버 로그인 정보",
            font=ctk.CTkFont(family="맑은 고딕", size=16, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        login_title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 아이디
        self.id_entry = ctk.CTkEntry(
            login_frame,
            placeholder_text="네이버 아이디",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_GRAY,
            fg_color=NAVER_BG
        )
        self.id_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 비밀번호
        self.pw_entry = ctk.CTkEntry(
            login_frame,
            placeholder_text="비밀번호",
            show="*",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_GRAY,
            fg_color=NAVER_BG
        )
        self.pw_entry.pack(fill="x", padx=20, pady=(0, 15))
        
        # ===== AI 글 생성 섹션 =====
        ai_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        ai_frame.pack(fill="x", pady=(0, 20))
        
        ai_title = ctk.CTkLabel(
            ai_frame,
            text="✨ AI 글 생성 설정",
            font=ctk.CTkFont(family="맑은 고딕", size=16, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        ai_title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 키워드 안내
        keyword_info = ctk.CTkLabel(
            ai_frame,
            text="💡 AI가 keywords.txt 파일의 키워드로 자동으로 글을 작성합니다",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        keyword_info.pack(fill="x", padx=20, pady=(0, 15))
        
        # ===== 주제 설정 섹션 (사진과 동일하게) =====
        theme_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        theme_frame.pack(fill="x", pady=(0, 20))
        
        theme_title = ctk.CTkLabel(
            theme_frame,
            text="📂 주제 설정",
            font=ctk.CTkFont(family="맑은 고딕", size=16, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        theme_title.pack(fill="x", padx=20, pady=(15, 5))
        
        theme_desc = ctk.CTkLabel(
            theme_frame,
            text="주제를 선택하면 내블로그와 블로그 홈에서 주제별로 글을 볼 수 있습니다.\n주제를 선택하지 않아도 '블로그 홈 > 주제별 글보기 > 전체'에서 볼 수 있습니다.",
            font=ctk.CTkFont(family="맑은 고딕", size=10),
            text_color=NAVER_GRAY,
            anchor="w",
            justify="left"
        )
        theme_desc.pack(fill="x", padx=20, pady=(0, 10))
        
        # 주제 그리드 생성
        theme_grid = ctk.CTkFrame(theme_frame, fg_color=NAVER_BG, corner_radius=8)
        theme_grid.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        
        # 각 카테고리별로 라디오 버튼 생성
        col = 0
        for category, themes in BLOG_THEMES.items():
            cat_frame = ctk.CTkFrame(theme_grid, fg_color="transparent")
            cat_frame.grid(row=0, column=col, padx=10, pady=10, sticky="n")
            
            # 카테고리 제목
            cat_label = ctk.CTkLabel(
                cat_frame,
                text=category,
                font=ctk.CTkFont(family="맑은 고딕", size=12, weight="bold"),
                text_color=NAVER_TEXT
            )
            cat_label.pack(anchor="w", pady=(0, 5))
            
            # 각 주제에 대한 라디오 버튼
            for theme in themes:
                rb = ctk.CTkRadioButton(
                    cat_frame,
                    text=theme,
                    variable=self.selected_theme,
                    value=theme,
                    font=ctk.CTkFont(family="맑은 고딕", size=11),
                    fg_color=NAVER_GREEN,
                    hover_color=NAVER_GREEN_HOVER
                )
                rb.pack(anchor="w", pady=2)
            
            col += 1
        
        # "주제 선택 안 함" 라디오 버튼
        no_theme_rb = ctk.CTkRadioButton(
            theme_frame,
            text="주제 선택 안 함",
            variable=self.selected_theme,
            value="",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER
        )
        no_theme_rb.pack(anchor="w", padx=20, pady=(5, 15))
        no_theme_rb.select()  # 기본 선택
        
        # ===== 포스팅 설정 섹션 =====
        setting_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        setting_frame.pack(fill="x", pady=(0, 20))
        
        setting_title = ctk.CTkLabel(
            setting_frame,
            text="⚙️ 포스팅 설정",
            font=ctk.CTkFont(family="맑은 고딕", size=16, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        setting_title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 공개 설정
        open_label = ctk.CTkLabel(
            setting_frame,
            text="공개 설정",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        open_label.pack(fill="x", padx=20, pady=(5, 2))
        
        self.open_combobox = ctk.CTkComboBox(
            setting_frame,
            values=["전체공개", "이웃공개", "서로이웃공개", "비공개"],
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            dropdown_font=ctk.CTkFont(family="맑은 고딕", size=12),
            height=40,
            corner_radius=8,
            border_color=NAVER_GRAY,
            fg_color=NAVER_BG,
            button_color=NAVER_GREEN,
            button_hover_color=NAVER_GREEN_HOVER
        )
        self.open_combobox.set("전체공개")
        self.open_combobox.pack(fill="x", padx=20, pady=(0, 15))
        
        # ===== 외부 링크 섹션 =====
        link_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_LIGHT_BG, corner_radius=12)
        link_frame.pack(fill="x", pady=(0, 20))
        
        link_title = ctk.CTkLabel(
            link_frame,
            text="🔗 외부 링크 (선택사항)",
            font=ctk.CTkFont(family="맑은 고딕", size=16, weight="bold"),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        link_title.pack(fill="x", padx=20, pady=(15, 10))
        
        # 링크 URL
        link_url_label = ctk.CTkLabel(
            link_frame,
            text="링크 URL",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        link_url_label.pack(fill="x", padx=20, pady=(5, 2))
        
        self.link_url_entry = ctk.CTkEntry(
            link_frame,
            placeholder_text="https://example.com",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_GRAY,
            fg_color=NAVER_BG
        )
        self.link_url_entry.pack(fill="x", padx=20, pady=(0, 10))
        
        # 링크 텍스트
        link_text_label = ctk.CTkLabel(
            link_frame,
            text="링크 텍스트",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        link_text_label.pack(fill="x", padx=20, pady=(5, 2))
        
        self.link_text_entry = ctk.CTkEntry(
            link_frame,
            placeholder_text="더 자세한 내용 보기",
            font=ctk.CTkFont(family="맑은 고딕", size=13),
            height=40,
            corner_radius=8,
            border_color=NAVER_GRAY,
            fg_color=NAVER_BG
        )
        self.link_text_entry.pack(fill="x", padx=20, pady=(0, 15))
        
        # ===== 실행 섹션 =====
        action_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_BG)
        action_frame.pack(fill="x", pady=(0, 10))
        
        self.post_button = ctk.CTkButton(
            action_frame,
            text="🚀 AI 포스팅 실행",
            font=ctk.CTkFont(family="맑은 고딕", size=16, weight="bold"),
            height=50,
            corner_radius=8,
            fg_color=NAVER_GREEN,
            hover_color=NAVER_GREEN_HOVER,
            text_color="white",
            command=self.start_posting
        )
        self.post_button.pack(fill="x", pady=(0, 10))
        
        # ===== 상태 표시 섹션 =====
        status_frame = ctk.CTkFrame(main_scroll, fg_color=NAVER_LIGHT_BG, corner_radius=8)
        status_frame.pack(fill="x")
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="✅ 준비 완료 (keywords.txt 파일을 확인하세요)",
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            text_color=NAVER_TEXT,
            anchor="w"
        )
        self.status_label.pack(fill="x", padx=15, pady=10)
    
    def update_status(self, message):
        """상태 메시지 업데이트"""
        self.after(0, lambda: self.status_label.configure(text=f"📢 {message}"))
    
    def validate_inputs(self):
        """입력값 검증"""
        api_key = self.api_entry.get().strip()
        naver_id = self.id_entry.get().strip()
        naver_pw = self.pw_entry.get().strip()
        
        if not api_key:
            messagebox.showerror("입력 오류", "Gemini API 키를 입력해주세요.\n\nhttps://aistudio.google.com/")
            return False
        
        if not naver_id:
            messagebox.showerror("입력 오류", "네이버 아이디를 입력해주세요.")
            return False
        
        if not naver_pw:
            messagebox.showerror("입력 오류", "비밀번호를 입력해주세요.")
            return False
        
        return True
    
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
        self.post_button.configure(state="disabled", text="⏳ AI 포스팅 중...")
        self.update_status("포스팅 준비 중...")
        
        api_key = self.api_entry.get().strip()
        naver_id = self.id_entry.get().strip()
        naver_pw = self.pw_entry.get().strip()
        theme = self.selected_theme.get()
        open_type = self.open_combobox.get()
        external_link = self.link_url_entry.get().strip()
        external_link_text = self.link_text_entry.get().strip()
        
        thread = threading.Thread(
            target=self.run_automation,
            args=(naver_id, naver_pw, api_key, theme, open_type, external_link, external_link_text),
            daemon=True
        )
        thread.start()
    
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
                callback=self.update_status
            )
            
            if success:
                self.after(0, lambda: messagebox.showinfo(
                    "성공",
                    "AI 포스팅이 성공적으로 완료되었습니다! 🎉\n\n브라우저에서 결과를 확인해주세요."
                ))
                self.update_status("✅ 포스팅 성공!")
            else:
                self.after(0, lambda: messagebox.showerror(
                    "실패",
                    "포스팅에 실패했습니다.\n상태 메시지를 확인하고 다시 시도해주세요."
                ))
                self.update_status("❌ 포스팅 실패")
        
        except Exception as e:
            self.after(0, lambda: messagebox.showerror(
                "오류",
                f"오류가 발생했습니다:\n{str(e)}"
            ))
            self.update_status(f"❌ 오류: {str(e)}")
        
        finally:
            self.is_running = False
            self.after(0, lambda: self.post_button.configure(
                state="normal",
                text="🚀 AI 포스팅 실행"
            ))
    
    def run(self):
        """애플리케이션 실행"""
        self.mainloop()


def main():
    """메인 함수"""
    app = NaverBlogApp()
    app.run()


if __name__ == "__main__":
    main()
