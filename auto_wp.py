#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto WP -    
WordPress    PyQt6 GUI
"""

import sys
import os
import subprocess
import threading
import time
import random
import re
import webbrowser
import json
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image, ImageDraw, ImageFont
import openai
from openai import OpenAI
import base64
import pandas as pd

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                           QTextEdit, QTextBrowser, QLineEdit, QProgressBar, QFrame, 
                           QScrollArea, QStackedWidget, QListWidget, 
                           QTabWidget, QGroupBox, QSpacerItem, QSizePolicy,
                           QFileDialog, QComboBox, QSpinBox, QPlainTextEdit)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QRect
from PyQt6.QtGui import (QFont, QPixmap, QPalette, QColor, QIcon, 
                        QPainter, QBrush, QLinearGradient, QTextOption, QCursor)
import platform

#    
class ClickableLabel(QLabel):
    clicked = pyqtSignal(str)  # URL  
    
    def __init__(self, text="", url="", parent=None):
        super().__init__(text, parent)
        self.url = url
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            QLabel {
                color: #00a0d2;
                text-decoration: underline;
            }
            QLabel:hover {
                color: #0073aa;
            }
        """)
    
    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton and self.url:
                self.clicked.emit(self.url)
            super().mousePressEvent(event)
        except Exception as e:
            #    
            pass

# WordPress   
WORDPRESS_COLORS = {
    'primary_blue': '#0073aa',      # WordPress  
    'dark_blue': '#005177',         #  
    'light_blue': '#00a0d2',        #  
    'background_dark': '#1e1e1e',   #  
    'surface_dark': '#2d2d2d',      # / 
    'surface_light': '#383838',     #   
    'text_primary': '#ffffff',      #  
    'text_secondary': '#cccccc',    #  
    'success': '#46b450',           #  
    'warning': '#ffb900',           #  
    'error': '#dc3232',             #  
    'accent': '#00d084'             # WordPress  
}

#  requests   (     )
_session = None

def get_requests_session():
    """     requests """
    global _session
    if _session is None:
        _session = requests.Session()
        
        #    (  )
        adapter = HTTPAdapter(
            pool_connections=3,
            pool_maxsize=5,
            max_retries=0
        )
        _session.mount('http://', adapter)
        _session.mount('https://', adapter)
        
        #   
        _session.headers.update({
            'User-Agent': 'Auto-WP/1.0',
            'Connection': 'keep-alive',
            'Accept-Encoding': 'gzip, deflate',
            'Cache-Control': 'no-cache'
        })
    
    return _session

def get_base_path():
    """     """
    if getattr(sys, 'frozen', False):
        # exe    
        return os.path.dirname(sys.executable)
    else:
        #  Python    
        return os.path.dirname(__file__)

class WordPressButton(QPushButton):
    """WordPress  """
    def __init__(self, text, button_type="primary", parent=None):
        super().__init__(text, parent)
        self.button_type = button_type
        self.is_active = False  #   
        self.updateStyle()
        
    def setActive(self, active):
        """   """
        self.is_active = active
        self.updateStyle()
        
    def updateStyle(self):
        """  """
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
        
        if self.button_type == "primary":
            #       
            bg_color = "#1e3a8a" if self.is_active else WORDPRESS_COLORS['primary_blue']
            self.setStyleSheet(base_style + f"""
                QPushButton {{
                    background-color: {bg_color};
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
                    color: {WORDPRESS_COLORS['text_secondary']};
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
    
    def setButtonType(self, button_type):
        """     """
        self.button_type = button_type
        self.updateStyle()

class ModernCard(QFrame):
    """   """
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {WORDPRESS_COLORS['surface_dark']};
                border: 1px solid {WORDPRESS_COLORS['surface_light']};
                border-radius: 12px;
                padding: 12px;
                margin: 4px;
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet(f"""
                QLabel {{
                    color: {WORDPRESS_COLORS['text_primary']};
                    font-size: 14px;
                    font-weight: bold;
                    margin-bottom: 8px;
                    border: 3px solid {WORDPRESS_COLORS['primary_blue']};
                    border-radius: 8px;
                    padding: 8px;
                    background-color: {WORDPRESS_COLORS['surface_light']};
                }}
            """)
            layout.addWidget(title_label)
        
        self.setLayout(layout)
    
    def addContent(self, widget):
        """  """
        self.layout().addWidget(widget)

class ContentGenerator:
    """     """
    def __init__(self, config_data, log_func):
        self.config_data = config_data
        self.log = log_func
    
    def call_openai_api(self, client, prompt, step_name, max_tokens=1500, temperature=0.7, system_content=None):
        """ OpenAI API  """
        try:
            if system_content:
                # system user   
                messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ]
            else:
                #  
                messages = [{"role": "user", "content": prompt}]
                
            response = client.chat.completions.create(
                model=self.config_data.get('gpt_model', 'gpt-4o-mini'),
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=60
            )
            return response.choices[0].message.content
        except Exception as api_error:
            self.log(f" {step_name} API  : {api_error}")
            self.log(f" {step_name} API  : {type(api_error).__name__}")
            if hasattr(api_error, 'response'):
                self.log(f" {step_name} API  : {api_error.response.status_code if api_error.response else 'None'}")
            return None  #     None 
    
    def generate_anchor_urls(self, keyword):
        """ URL """
        try:
            import urllib.parse
            
            #  URL 
            encoded_keyword = urllib.parse.quote(keyword)
            
            urls = {
                'naver_search': f"https://search.naver.com/search.naver?query={encoded_keyword}",
                'namu_wiki': f"https://namu.wiki/w/{encoded_keyword}",
                'play_store': f"https://play.google.com/store/search?q={encoded_keyword}&amp;c=apps",
                'app_store': f"https://www.apple.com/kr/search/{encoded_keyword}?src=globalnav"
            }
            
            # HTML    
            anchor_links = {
                'naver_search_link': f'<a href="{urls["naver_search"]}" target="_blank" rel="noopener">{keyword}   </a>',
                'namu_wiki_link': f'<a href="{urls["namu_wiki"]}" target="_blank" rel="noopener">{keyword} </a>',
                'play_store_link': f'<a href="{urls["play_store"]}" target="_blank" rel="noopener">{keyword}  </a>',
                'app_store_link': f'<a href="{urls["app_store"]}" target="_blank" rel="noopener">{keyword}  </a>'
            }
            
            return urls, anchor_links
            
        except Exception as e:
            self.log(f" URL  : {e}")
            return {}, {}
    
    def replace_prompt_variables(self, prompt_content, keyword, urls, anchor_links, **kwargs):
        """    """
        try:
            #   
            result = prompt_content.replace("{keyword}", keyword)
            
            # URL 
            result = result.replace("{naver_search_url}", urls.get('naver_search', ''))
            result = result.replace("{namu_wiki_url}", urls.get('namu_wiki', ''))
            result = result.replace("{play_store_url}", urls.get('play_store', ''))
            result = result.replace("{app_store_url}", urls.get('app_store', ''))
            
            #   
            result = result.replace("{naver_search_link}", anchor_links.get('naver_search_link', ''))
            result = result.replace("{namu_wiki_link}", anchor_links.get('namu_wiki_link', ''))
            result = result.replace("{play_store_link}", anchor_links.get('play_store_link', ''))
            result = result.replace("{app_store_link}", anchor_links.get('app_store_link', ''))
            
            #   (title, intro, body1, body2, body3 )
            for key, value in kwargs.items():
                if value is not None:
                    result = result.replace(f"{{{key}}}", str(value))
            
            return result
            
        except Exception as e:
            self.log(f"   : {e}")
            return prompt_content
    
    def remove_title_from_intro(self, content, title):
        """    - <h1>     """
        try:
            import re
            
            # HTML    
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            # <h1>   
            content = re.sub(r'<h1[^>]*>.*?</h1>', '', content, flags=re.DOTALL | re.IGNORECASE)
            
            #     ( )
            if ':' in clean_title:
                core_title = clean_title.split(':')[0].strip()
            elif '|' in clean_title:
                core_title = clean_title.split('|')[0].strip()
            else:
                core_title = clean_title
            
            #       
            lines = content.split('\n')
            filtered_lines = []
            title_found = False
            
            for line in lines:
                line = line.strip()
                
                if not line:
                    filtered_lines.append('')
                    continue
                
                #       
                line_clean = re.sub(r'<[^>]+>', '', line).strip()
                
                #   <p>      
                if (not title_found and 
                    not line.startswith('<p') and 
                    (line_clean == clean_title or 
                     line_clean == core_title or
                     (len(line_clean) > 10 and 
                      (clean_title.lower() in line_clean.lower() or 
                       core_title.lower() in line_clean.lower())))):
                    # self.log(f"   : '{line_clean[:30]}...'")  # 
                    title_found = True
                    continue
                
                # HTML   
                if line.startswith('<h') or line.startswith('#'):
                    continue
                    
                filtered_lines.append(line)
            
            result = '\n'.join(filtered_lines).strip()
            
            #   
            result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
            
            # self.log("    ")  # 
            return result if result else content
            
        except Exception as e:
            self.log(f"   : {e}")
            return content
    
    def clean_content(self, content):
        """    """
        if not content:
            return content
            
        import re
        
        #    (   )
        content = re.sub(r'^\d+\.\s*(||\d*|\d*)\s*[:]\s*', '', content, flags=re.MULTILINE)
        
        #    
        content = re.sub(r'```[\w]*\n?', '', content)  # ```html, ```css  
        content = re.sub(r'```\n?', '', content)       #  ``` 
        content = re.sub(r'`([^`]+)`', r'\1', content) #    
        
        #    
        content = re.sub(r'^#{1,6}\s*', '', content, flags=re.MULTILINE)  #   
        content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', content)  #  HTML
        content = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', content)  #  HTML
        
        #     
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # 3   2
        content = re.sub(r'[ \t]+', ' ', content)  #   
        
        return content.strip()

    def ensure_h2_tags(self, content, keyword):
        """ <h2>  3  ,   """
        try:
            import re
            
            #  <h2>   
            h2_tags = re.findall(r'<h2[^>]*>.*?</h2>', content, re.DOTALL | re.IGNORECASE)
            h2_count = len(h2_tags)
            
            if h2_count >= 3:
                return content  #    
            
            # <h2>     
            
            # GPT     3 
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.config_data.get('gpt_api_key'))
                
                retry_prompt = f"""  <h2>    {h2_count} . 
 <h2>    3   .

: {keyword}

 :
{content}

   
1. <h2>   3  
2. <p>   
3. : <p></p><h2>1</h2><p>1</p><h2>2</h2><p>2</p><h2>3</h2><p>3</p>
4.  ('1. :', '1:' )   """

                response = client.chat.completions.create(
                    model=self.config_data.get('gpt_model', 'gpt-4o-mini'),
                    messages=[
                        {
                            "role": "system", 
                            "content": " HTML  .  <h2>  3    . <h2>  3   ."
                        },
                        {"role": "user", "content": retry_prompt}
                    ],
                    max_tokens=8000,
                    temperature=0.7,
                    timeout=60
                )
                
                retry_content = response.choices[0].message.content
                retry_content = self.clean_content(retry_content)
                
                #    <h2>   
                retry_h2_count = len(re.findall(r'<h2[^>]*>.*?</h2>', retry_content, re.DOTALL | re.IGNORECASE))
                
                if retry_h2_count >= 3:
                    self.log(f"  : {retry_h2_count}  ")
                    return retry_content
                else:
                    self.log(f"  : {retry_h2_count} ,   ")
                    
            except Exception as e:
                self.log(f" GPT  : {e},   ")
            
            # GPT      
            
            #       
            paragraphs = re.findall(r'<p[^>]*>.*?</p>', content, re.DOTALL | re.IGNORECASE)
            
            if len(paragraphs) == 0:
                #     
                return f"""<p>{keyword}    .      .</p>

<h2>{keyword}   </h2>
<p>{keyword}        .      .</p>

<h2>{keyword}    </h2>
<p>{keyword}            .    .</p>

<h2>{keyword}    </h2>
<p>{keyword}      .      .</p>"""
            
            #     ,   
            intro = paragraphs[0]
            
            #  3 
            h2_titles = [
                f"{keyword}    ",
                f"{keyword}    ",
                f"{keyword}   "
            ]
            
            result = f"{intro}\n"
            
            #     
            remaining_paragraphs = paragraphs[1:] if len(paragraphs) > 1 else []
            
            for i in range(3):  #  3  
                result += f"\n<h2>{h2_titles[i]}</h2>\n"
                
                if i < len(remaining_paragraphs):
                    #   
                    result += f"{remaining_paragraphs[i]}\n"
                else:
                    #   
                    result += f"<p>{keyword}    .        .</p>\n"
            
            self.log("    ")
            return result.strip()
            
        except Exception as e:
            self.log(f"   : {e}")
            return content

    def generate_title_from_prompt1(self, keyword, client):
        """ 1      """
        try:
            #  1  
            prompts_dir = os.path.join(get_base_path(), "prompts")
            prompt1_file = os.path.join(prompts_dir, "prompt1.txt")
            
            if os.path.exists(prompt1_file):
                with open(prompt1_file, 'r', encoding='utf-8') as f:
                    prompt1_content = f.read()
            else:
                #     
                prompt1_content = self.get_default_prompt("prompt1.txt")
            
            #  URL 
            urls, anchor_links = self.generate_anchor_urls(keyword)
            
            #   
            prompt1 = self.replace_prompt_variables(prompt1_content, keyword, urls, anchor_links)
            
            #   
            title_prompt = f"{prompt1}\n\n . ':'    ."
            
            response = client.chat.completions.create(
                model=self.config_data.get('gpt_model', 'gpt-4o-mini'),
                messages=[{"role": "user", "content": title_prompt}],
                max_tokens=100,
                temperature=0.7,
                timeout=60
            )
            
            title = response.choices[0].message.content.strip()
            
            # ':'   
            if title.startswith(':'):
                title = title[3:].strip()
            
            return title
            
        except Exception as e:
            self.log(f"  : {e}")
            #     
            return f"{keyword} |   "

    def generate_title_from_approval(self, keyword, client):
        """approval.txt      """
        try:
            # approval   
            prompts_dir = os.path.join(get_base_path(), "prompts")
            approval_file = os.path.join(prompts_dir, "approval.txt")
            
            if os.path.exists(approval_file):
                with open(approval_file, 'r', encoding='utf-8') as f:
                    approval_content = f.read()
            else:
                #     
                return f"{keyword} |  "
            
            #    
            title_guidelines = ""
            lines = approval_content.split('\n')
            capture_title_section = False
            
            for line in lines:
                if '' in line and ('' in line or '' in line or '' in line):
                    capture_title_section = True
                    continue
                elif capture_title_section:
                    if line.strip() and not line.startswith('{'):
                        title_guidelines += line + '\n'
                    elif line.startswith('{') or not line.strip():
                        if title_guidelines.strip():
                            break
            
            if title_guidelines.strip():
                #      
                title_prompt = f"""
    '{keyword}'   :

{title_guidelines}

: {keyword}

 . ':'    .
                """
                
                response = client.chat.completions.create(
                    model=self.config_data.get('gpt_model', 'gpt-4o-mini'),
                    messages=[{"role": "user", "content": title_prompt}],
                    max_tokens=100,
                    temperature=0.7,
                    timeout=60
                )
                
                title = response.choices[0].message.content.strip()
                
                # ':'   
                if title.startswith(':'):
                    title = title[3:].strip()
                
                return title
            else:
                #      
                return f"{keyword} |  "
                
        except Exception as e:
            self.log(f"approval   : {e}")
            #     
            return f"{keyword} |  "

    def read_prompt_file(self, file_path):
        """  """
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            else:
                self.log(f"     : {file_path}")
                return ""
        except Exception as e:
            self.log(f"   : {e}")
            return ""

    def generate_content_with_5_prompts(self, keyword):
        """5    """
        try:
            self.log(f" 5    : {keyword}")
            
            # OpenAI  
            api_key = self.config_data.get('gpt_api_key')
            if not api_key or api_key == "your_openai_api_key":
                self.log(" OpenAI API   !")
                return self.generate_simple_content(keyword)
            
            client = OpenAI(api_key=api_key)
            
            #  URL 
            try:
                urls, anchor_links = self.generate_anchor_urls(keyword)
            except Exception as e:
                self.log(f"  URL  : {e}")
                urls, anchor_links = {}, {}
            
            #   
            prompts_dir = os.path.join(get_base_path(), "prompts")
            
            if not os.path.exists(prompts_dir):
                self.log("    !")
                return self.generate_simple_content(keyword, urls, anchor_links)
            
            # 1:    (prompt1.txt)
            self.log("1:    ...")
            title_and_intro = None  #  
            try:
                prompt1_content = self.read_prompt_file(os.path.join(prompts_dir, "prompt1.txt"))
                prompt1 = self.replace_prompt_variables(prompt1_content, keyword, urls, anchor_links)
                
                try:
                    title_and_intro = self.call_openai_api(
                        client, prompt1, "1", max_tokens=1000, temperature=0.7
                    )
                    if title_and_intro is None:
                        self.log(" 1 API  None. fallback   ")
                        return self.generate_simple_content(keyword, urls, anchor_links)
                    self.log("     ")
                except Exception as api_error:
                    # fallback  
                    return self.generate_simple_content(keyword, urls, anchor_links)
            except Exception as e:
                self.log(f" 1  : {e}")
                self.log(f" 1  : {type(e).__name__}")
                import traceback
                self.log(f" : {traceback.format_exc()}")
                return self.generate_simple_content(keyword, urls, anchor_links)
            
            # title_and_intro None  
            if not title_and_intro:
                self.log(" 1  ")
                return self.generate_simple_content(keyword, urls, anchor_links)
            
            #   
            if ":" in title_and_intro and ":" in title_and_intro:
                title_start = title_and_intro.find(":") + 3
                intro_start = title_and_intro.find(":")
                title = title_and_intro[title_start:intro_start].strip()
                intro = title_and_intro[intro_start+3:].strip()
            else:
                #      
                lines = title_and_intro.split('\n')
                title = lines[0].strip()
                intro = '\n'.join(lines[1:]).strip()
            
            #    
            intro = self.remove_title_from_intro(intro, title)
            
            # 2:  1  (prompt2.txt)
            self.log("2:   1  ...")
            body1 = None  #  
            try:
                prompt2_content = self.read_prompt_file(os.path.join(prompts_dir, "prompt2.txt"))
                prompt2 = self.replace_prompt_variables(prompt2_content, keyword, urls, anchor_links, title=title, intro=intro)
                
                # API     
                if len(prompt2) > 10000:  #    
                    self.log(f"   : {len(prompt2)}")
                
                try:
                    body1 = self.call_openai_api(
                        client, prompt2, "2", max_tokens=1500, temperature=0.7
                    )
                    if body1 is None:
                        self.log(" 2 API  None. fallback   ")
                        return self.generate_simple_content(keyword, urls, anchor_links)
                    self.log("   1  ")
                except Exception as api_error:
                    # fallback  
                    return self.generate_simple_content(keyword, urls, anchor_links)
            except Exception as e:
                self.log(f"   1  : {e}")
                self.log(f"  : {type(e).__name__}")
                import traceback
                self.log(f" : {traceback.format_exc()}")
                return self.generate_simple_content(keyword, urls, anchor_links)
            
            if not body1:
                self.log(" 2  ")
                return self.generate_simple_content(keyword, urls, anchor_links)
            
            # 3:  2  (prompt3.txt)
            self.log("3:   2  ...")
            body2 = None  #  
            try:
                prompt3_content = self.read_prompt_file(os.path.join(prompts_dir, "prompt3.txt"))
                prompt3 = self.replace_prompt_variables(prompt3_content, keyword, urls, anchor_links, body1=body1)
                
                body2 = self.call_openai_api(
                    client, prompt3, "3", max_tokens=1500, temperature=0.7
                )
                if body2 is None:
                    self.log(" 3 API  None. fallback   ")
                    return self.generate_simple_content(keyword, urls, anchor_links)
                self.log("   2  ")
            except Exception as e:
                self.log(f"   2  : {e}")
                import traceback
                self.log(f" : {traceback.format_exc()}")
                return self.generate_simple_content(keyword, urls, anchor_links)
            
            if not body2:
                self.log(" 3  ")
                return self.generate_simple_content(keyword, urls, anchor_links)
            
            # 4:  3  (prompt4.txt)
            self.log("4:   3  ...")
            body3 = None  #  
            try:
                prompt4_content = self.read_prompt_file(os.path.join(prompts_dir, "prompt4.txt"))
                prompt4 = self.replace_prompt_variables(prompt4_content, keyword, urls, anchor_links, body2=body2)
                
                body3 = self.call_openai_api(
                    client, prompt4, "4", max_tokens=1500, temperature=0.7
                )
                if body3 is None:
                    self.log(" 4 API  None. fallback   ")
                    return self.generate_simple_content(keyword, urls, anchor_links)
                self.log("   3  ")
            except Exception as e:
                self.log(f"   3  : {e}")
                import traceback
                self.log(f" : {traceback.format_exc()}")
                self.log("    ...")
                #       
                try:
                    return self.generate_simple_content(keyword, urls, anchor_links)
                except:
                    self.log(" fallback   .")
                    return f"<h1>{keyword}</h1><p>{keyword}  .</p>"
            
            if not body3:
                self.log(" 4  ")
                try:
                    return self.generate_simple_content(keyword, urls, anchor_links)
                except:
                    return f"<h1>{keyword}</h1><p>{keyword}  .</p>"
            
            # 5:     (prompt5.txt)
            self.log("5:     ...")
            conclusion = None  #  
            try:
                prompt5_content = self.read_prompt_file(os.path.join(prompts_dir, "prompt5.txt"))
                prompt5 = self.replace_prompt_variables(prompt5_content, keyword, urls, anchor_links, body3=body3)
                
                conclusion = self.call_openai_api(
                    client, prompt5, "5", max_tokens=1000, temperature=0.7
                )
                if conclusion is None:
                    self.log(" 5 API  None. fallback   ")
                    try:
                        return self.generate_simple_content(keyword, urls, anchor_links)
                    except:
                        return f"{keyword} ", f"<h1>{keyword}</h1><p>{keyword}  .</p>"
                self.log("     ")
            except Exception as e:
                self.log(f"     : {e}")
                import traceback
                self.log(f" : {traceback.format_exc()}")
                self.log("    ...")
                #       
                try:
                    return self.generate_simple_content(keyword, urls, anchor_links)
                except:
                    return f"{keyword} ", f"<h1>{keyword}</h1><p>{keyword}  .</p>"
            
            if not conclusion:
                self.log(" 5  ")
                try:
                    return self.generate_simple_content(keyword, urls, anchor_links)
                except:
                    return f"{keyword} ", f"<h1>{keyword}</h1><p>{keyword}  .</p>"
            
            #    
            intro = self.clean_content(intro)
            body1 = self.clean_content(body1)
            body2 = self.clean_content(body2)
            body3 = self.clean_content(body3)
            conclusion = self.clean_content(conclusion)
            
            #   
            final_content = f"{intro}\n\n{body1}\n\n{body2}\n\n{body3}\n\n{conclusion}"
            
            #   ( )
            del intro, body1, body2, body3, conclusion
            
            #   
            self.save_content_to_file(title, final_content, keyword)
            
            self.log(" 5    !")
            return title, final_content
            
        except Exception as e:
            self.log(f" 5       : {e}")
            import traceback
            self.log(f"  : {traceback.format_exc()}")
            self.log("     ...")
            #     fallback -   
            try:
                urls, anchor_links = self.generate_anchor_urls(keyword)
                return self.generate_simple_content(keyword, urls, anchor_links)
            except Exception as fallback_error:
                self.log(f" fallback   : {fallback_error}")
                #    HTML 
                simple_title = f"{keyword}  "
                simple_content = f"<h1>{simple_title}</h1><p>{keyword}   .</p>"
                return simple_title, simple_content

    def generate_simple_content(self, keyword, urls=None, anchor_links=None):
        """   (fallback)"""
        try:
            # API      
            api_key = self.config_data.get('gpt_api_key')
            if not api_key or api_key == "your_openai_api_key":
                self.log(" API     ")
                title = f"<h1>{keyword}:  </h1>"
                content = f"""
<p>{keyword}    .</p>

<h2>1. {keyword} </h2>
<p>{keyword}       .     .</p>

<h2>2. {keyword}  </h2>
<p>{keyword}     :</p>
<ul>
<li>  </li>
<li>  </li>
<li>  </li>
</ul>

<h2>3. {keyword}  </h2>
<p>{keyword}     .</p>

<h2></h2>
<p>{keyword}           .</p>
"""
                #   
                self.save_content_to_file(title, content, keyword)
                return title, content
            
            client = OpenAI(api_key=api_key)
            
            simple_prompt = f""" '{keyword}'     .
            
:
1.   (200 )
2.   3  
3.  

HTML  ,     ."""

            response = client.chat.completions.create(
                model=self.config_data.get('gpt_model', 'gpt-4o-mini'),
                messages=[{"role": "user", "content": simple_prompt}],
                max_tokens=2000,
                temperature=0.7,
                timeout=60
            )
            
            content = response.choices[0].message.content
            title = f"{keyword}:  "
            
            return title, self.clean_content(content)
            
        except Exception as e:
            self.log(f"   : {e}")
            #  
            title = f"{keyword} "
            content = f"<p>{keyword}   .</p>"
            return title, content

    def generate_approval_content(self, keyword):
        """   -  """
        try:
            # OpenAI  
            client = OpenAI(api_key=self.config_data.get('gpt_api_key'))
            
            self.log("   ...")
            
            #   
            system_content = f"""  SEO  .     .

: {keyword}

#   (   ):

1. : <p>   300 

2. 1: <h2>   20-30
3. 1: <p>   1500 

4. 2: <h2>   20-30  
5. 2: <p>   1500 

6. 3: <h2>   20-30
7. 3: <p>   1500 

#  :
-  <h2>  3 
-   <p>  
-  "~" 
- {keyword}   
-  HTML   

#  :
<p> </p>
<h2>  </h2>
<p>  </p>
<h2>  </h2>
<p>  </p>
<h2>  </h2>
<p>  </p>"""
            
            #   
            user_prompt = f" '{keyword}'     SEO  ."
            
            # GPT API 
            content = self.call_openai_api(
                client, user_prompt, " ", 
                max_tokens=12000, temperature=0.7, system_content=system_content
            )
            
            if content is None:
                self.log("   API  None. fallback   ")
                return self.generate_simple_content(keyword, [], [])
            
            #  
            content = self.clean_content(content)
            
            #      (  )
            content = self.ensure_h2_tags_for_approval(content, keyword, client)
            
            #   ( )
            title = self.generate_simple_title(keyword, client)
            
            #    
            content = self.remove_title_from_intro(content, title)
            
            #   
            self.save_content_to_file(title, content, keyword)
            
            return title, content
            
        except Exception as e:
            self.log(f"   : {e}")
            #      
            simple_title = f"{keyword}  "
            simple_content = f"""
            <p>{keyword}     .    .</p>
            
            <h2>{keyword}  </h2>
            <p>{keyword}     ,       .</p>
            
            <h2>{keyword}  </h2>
            <p>{keyword}     .        .</p>
            
            <h2>{keyword}  </h2>
            <p>{keyword}     .        .</p>
            """
            simple_content = self.clean_content(simple_content)
            return simple_title, simple_content

# HTML  
<p> </p>

<h2>  1</h2>
<p>1 </p>

<h2>  2</h2>
<p>2 </p>

<h2>  3</h2>
<p>3 </p>

#  HTML 
<div>, <html>, <head>, <title>, <body>, <article>, <hr>  """
            
            #   
            user_prompt = f" '{keyword}'     SEO  ."
            
            # GPT API 
            content = self.call_openai_api(
                client, user_prompt, " ", 
                max_tokens=12000, temperature=0.7, system_content=system_content
            )
            
            if content is None:
                self.log("   API  None. fallback   ")
                return self.generate_simple_content(keyword, [], [])
            
            #  
            content = self.clean_content(content)
            
            #      (  )
            content = self.ensure_h2_tags_for_approval(content, keyword, client)
            
            #   ( )
            title = self.generate_simple_title(keyword, client)
            
            #    
            content = self.remove_title_from_intro(content, title)
            
            #   
            self.save_content_to_file(title, content, keyword)
            
            return title, content
            
        except Exception as e:
            self.log(f"   : {e}")
            #      
            simple_title = f"{keyword}  "
            simple_content = f"""
            <p>{keyword}     .    .</p>
            
            <h2>{keyword}  </h2>
            <p>{keyword}     ,       .</p>
            
            <h2>{keyword}  </h2>
            <p>{keyword}     .        .</p>
            
            <h2>{keyword}  </h2>
            <p>{keyword}     .        .</p>
            """
            simple_content = self.clean_content(simple_content)
            return simple_title, simple_content

    def generate_simple_title(self, keyword, client):
        """  """
        try:
            title_prompt = f" '{keyword}' SEO    . : [ ]: [1], [2], [3]  30  ."
            
            response = client.chat.completions.create(
                model=self.config_data.get('gpt_model', 'gpt-4o-mini'),
                messages=[{"role": "user", "content": title_prompt}],
                max_tokens=100,
                temperature=0.7,
                timeout=60
            )
            
            title = response.choices[0].message.content.strip()
            return title
            
        except Exception as e:
            self.log(f"  : {e}")
            return f"{keyword}:  ,  , "

    def ensure_h2_tags_for_approval(self, content, keyword, client):
        """  <h2>    """
        try:
            import re
            
            #  <h2>   
            h2_tags = re.findall(r'<h2[^>]*>.*?</h2>', content, re.DOTALL | re.IGNORECASE)
            h2_count = len(h2_tags)
            
            if h2_count >= 3:
                return content  #    
            
            # <h2>      
            self.log(f"   ({h2_count}),   ...")
            
            retry_system_prompt = f""" 10    SEO  . 

 #    
1.  <h2>   3  
2. HTML : <p></p><h2>1</h2><p>1</p><h2>2</h2><p>2</p><h2>3</h2><p>3</p>
3.  ('1. :', '1:' )   
4.  '{keyword}'  

 :
- :  3 <h2> 
- : 20-35 ( )
- :    (: "~  ", "~ ", "~  ")
- HTML: <h2>   
- : ,   

 :
-   1,500-2,000
- : "~"  
- HTML: <p>  
-  : , , H, ,   """

            retry_user_prompt = f""" '{keyword}'    <h2>  3    .

  ():
{content}

 : <h2>   3  !"""

            try:
                response = client.chat.completions.create(
                    model=self.config_data.get('gpt_model', 'gpt-4o-mini'),
                    messages=[
                        {"role": "system", "content": retry_system_prompt},
                        {"role": "user", "content": retry_user_prompt}
                    ],
                    max_tokens=12000,
                    temperature=0.7,
                    timeout=60
                )
                
                retry_content = response.choices[0].message.content
                retry_content = self.clean_content(retry_content)
                
                #    <h2>   
                retry_h2_count = len(re.findall(r'<h2[^>]*>.*?</h2>', retry_content, re.DOTALL | re.IGNORECASE))
                
                if retry_h2_count >= 3:
                    self.log(f"   : {retry_h2_count}  ")
                    return retry_content
                else:
                    self.log(f"   : {retry_h2_count} ")
                    
            except Exception as e:
                self.log(f"   : {e}")
            
            #  :    
            self.log("    ...")
            return self.create_manual_structure_for_approval(content, keyword)
                    
        except Exception as e:
            self.log(f"   : {e}")
            return content

    def create_manual_structure_for_approval(self, content, keyword):
        """   """
        try:
            import re
            
            #    
            paragraphs = re.findall(r'<p[^>]*>.*?</p>', content, re.DOTALL | re.IGNORECASE)
            
            if len(paragraphs) == 0:
                #     
                intro_text = f"{keyword}     .      ."
            else:
                #      (HTML    )
                intro_text = re.sub(r'<[^>]+>', '', paragraphs[0])
            
            #    3 
            h2_titles = [
                f"{keyword}     ",
                f"{keyword}     ",
                f"{keyword}     "
            ]
            
            #   
            body_contents = [
                f"{keyword}       .         ,       .    {keyword}     ,       .      , {keyword}      .",
                
                f"{keyword}       .        ,       .    ,           .  {keyword}           .",
                
                f"{keyword}         .     {keyword}      ,    .    , {keyword}      ,         .           ."
            ]
            
            #   
            result = f"<p>{intro_text}</p>\n"
            
            for i in range(3):
                result += f"\n<h2>{h2_titles[i]}</h2>\n"
                result += f"<p>{body_contents[i]}</p>\n"
            
            self.log("     ")
            return result.strip()
            
        except Exception as e:
            self.log(f"   : {e}")
            #  
            return f"""<p>{keyword}   .</p>

<h2>{keyword}  </h2>
<p>{keyword}   .</p>

<h2>{keyword}  </h2>
<p>{keyword}    .</p>

<h2>{keyword} </h2>
<p>{keyword}   .</p>"""

    def save_content_to_file(self, title, content, keyword):
        """   """
        try:
            from datetime import datetime
            
            # output  
            output_dir = os.path.join(get_base_path(), "output")
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            #   ( )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"content_{timestamp}.html"
            filepath = os.path.join(output_dir, filename)
            
            # HTML  
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"<h1>{title}</h1>\n{content}")
            
        except Exception as e:
            self.log(f"   : {e}")
    
    def create_thumbnail(self, title, keyword):
        """   -   JPG  """
        try:
            from PIL import Image, ImageDraw, ImageFont
            import glob
            import random
            
            #   JPG  
            images_dir = os.path.join(get_base_path(), "images")
            jpg_files = glob.glob(os.path.join(images_dir, "*.jpg"))
            
            if not jpg_files:
                self.log("   JPG  ")
                return self.create_basic_thumbnail(title, keyword)
            
            #    
            bg_image_path = random.choice(jpg_files)
            #     
            
            #      300px 
            bg_img = Image.open(bg_image_path)
            bg_img = bg_img.resize((300, 300), Image.Resampling.LANCZOS)
            
            #    (  )
            overlay = Image.new('RGBA', (300, 300), (0, 0, 0, 120))
            bg_img = bg_img.convert('RGBA')
            bg_img = Image.alpha_composite(bg_img, overlay)
            bg_img = bg_img.convert('RGB')
            
            draw = ImageDraw.Draw(bg_img)
            
            #   (    )
            try:
                #   (Windows  )
                font_large = ImageFont.truetype("malgun.ttf", 26)
                font_small = ImageFont.truetype("malgun.ttf", 20)
            except:
                try:
                    #  (Google  )
                    font_large = ImageFont.truetype("NanumGothic.ttf", 26)
                    font_small = ImageFont.truetype("NanumGothic.ttf", 20)
                except:
                    try:
                        #     
                        fonts_dir = os.path.join(get_base_path(), "fonts")
                        timon_font = os.path.join(fonts_dir, "timon.ttf")
                        if os.path.exists(timon_font):
                            font_large = ImageFont.truetype(timon_font, 26)
                            font_small = ImageFont.truetype(timon_font, 20)
                        else:
                            raise FileNotFoundError("timon.ttf not found")
                    except:
                        try:
                            # Windows   
                            font_large = ImageFont.truetype("batang.ttf", 26)
                            font_small = ImageFont.truetype("batang.ttf", 20)
                        except:
                            try:
                                #  
                                font_large = ImageFont.truetype("dotum.ttf", 26)
                                font_small = ImageFont.truetype("dotum.ttf", 20)
                            except:
                                #    (  )
                                font_large = ImageFont.load_default()
                                font_small = ImageFont.load_default()
            
            #  HTML    
            import re
            import textwrap
            clean_title = re.sub(r'<[^>]+>', '', title)
            clean_title = clean_title.strip()
            
            #   ( )
            # , , , , |  
            clean_title = re.sub(r'[^\w\s|---]', '', clean_title)
            clean_title = clean_title.strip()
            
            #  | 
            if '|' in clean_title:
                parts = clean_title.split('|', 1)
                core_keyword = parts[0].strip()
                hook_phrase = parts[1].strip()
            else:
                # |    
                core_keyword = clean_title
                hook_phrase = ""
            
            #  
            text_color = 'white'
            
            #      
            all_text_lines = []
            
            #   (  )
            if core_keyword:
                #      (  8 )
                core_lines = textwrap.wrap(core_keyword, width=8)
                for line in core_lines:
                    all_text_lines.append(('large', line))
            
            #   (  )
            if hook_phrase:
                #      (  10 )
                hook_lines = textwrap.wrap(hook_phrase, width=10)
                for line in hook_lines:
                    all_text_lines.append(('small', line))
            
            #    
            total_height = len(all_text_lines) * 35  #   35px
            start_y = (300 - total_height) // 2  #  
            
            #    
            for i, (font_type, line) in enumerate(all_text_lines):
                current_font = font_large if font_type == 'large' else font_small
                
                if current_font:
                    bbox = draw.textbbox((0, 0), line, font=current_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                else:
                    text_width = len(line) * (15 if font_type == 'large' else 12)
                    text_height = 24 if font_type == 'large' else 18
                
                x = (300 - text_width) // 2
                y = start_y + (i * 35)
                
                #    ( )
                if current_font:
                    #  (,  )
                    draw.text((x+2, y+2), line, fill='black', font=current_font)
                    #   ()
                    draw.text((x, y), line, fill=text_color, font=current_font)
                else:
                    # 
                    draw.text((x+2, y+2), line, fill='black')
                    #  
                    draw.text((x, y), line, fill=text_color)
            
            #  
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(get_base_path(), "output")
            os.makedirs(output_dir, exist_ok=True)
            
            thumbnail_path = os.path.join(output_dir, f"thumbnail_{timestamp}.webp")
            
            # WebP  
            bg_img.save(thumbnail_path, "WEBP", quality=95, optimize=True)
            
            #      (  )
            return thumbnail_path
            
        except Exception as e:
            self.log(f"   : {e}")
            return self.create_basic_thumbnail(title, keyword)
    
    def create_basic_thumbnail(self, title, keyword):
        """   (  )"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            #    300x300  
            img = Image.new('RGB', (300, 300), color='#0073aa')
            draw = ImageDraw.Draw(img)
            
            #    
            try:
                #   (Windows  )
                font = ImageFont.truetype("malgun.ttf", 22)
            except:
                try:
                    #  (Google  )
                    font = ImageFont.truetype("NanumGothic.ttf", 22)
                except:
                    try:
                        #     
                        fonts_dir = os.path.join(get_base_path(), "fonts")
                        timon_font = os.path.join(fonts_dir, "timon.ttf")
                        if os.path.exists(timon_font):
                            font = ImageFont.truetype(timon_font, 22)
                        else:
                            raise FileNotFoundError("timon.ttf not found")
                    except:
                        try:
                            # Windows   
                            font = ImageFont.truetype("batang.ttf", 22)
                        except:
                            try:
                                #  
                                font = ImageFont.truetype("dotum.ttf", 22)
                            except:
                                #   
                                font = ImageFont.load_default()
            
            #  
            import re
            clean_title = re.sub(r'<[^>]+>', '', title)
            if len(clean_title) > 20:
                clean_title = clean_title[:20] + "..."
            
            #   
            if font:
                bbox = draw.textbbox((0, 0), clean_title, font=font)
                text_width = bbox[2] - bbox[0]
            else:
                text_width = len(clean_title) * 12
            
            x = (300 - text_width) // 2
            y = 140
            
            #   
            if font:
                #  (,  )
                draw.text((x+2, y+2), clean_title, fill='black', font=font)
                #   ()
                draw.text((x, y), clean_title, fill='white', font=font)
            else:
                # 
                draw.text((x+2, y+2), clean_title, fill='black')
                #  
                draw.text((x, y), clean_title, fill='white')
            
            #  
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(get_base_path(), "output")
            os.makedirs(output_dir, exist_ok=True)
            thumbnail_path = os.path.join(output_dir, f"thumbnail_{timestamp}.webp")
            img.save(thumbnail_path, "WEBP", quality=95)
            
            #  
            del img, draw
            
            #      
            return thumbnail_path
        except:
            self.log(f"    ")
            return None
    
    def post_to_wordpress(self, title, content, thumbnail_path):
        """ """
        try:
            session = get_requests_session()
            
            site_url = self.config_data.get('site_url', '').rstrip('/')
            username = self.config_data.get('username', '')
            password = self.config_data.get('password', '')
            category = self.config_data.get('category', '1')
            
            # WordPress REST API 
            api_url = f"{site_url}/wp-json/wp/v2/posts"
            
            #  
            auth = (username, password)
            
            #  
            post_data = {
                'title': title,
                'content': content,
                'status': 'publish',
                'categories': [int(category)]
            }
            
            # API 
            response = session.post(api_url, json=post_data, auth=auth, timeout=30)
            
            if response.status_code == 201:
                post_info = response.json()
                post_id = post_info.get('id')
                post_url = post_info.get('link')
                
                #  URL 
                admin_url = site_url.replace('/wp-json/wp/v2/posts', '')
                edit_url = f"{admin_url}/wp-admin/post.php?post={post_id}&action=edit"
                
                #     (   )
                # self.log(f"  ID: {post_id}")  # 
                
                #   ()
                if thumbnail_path and os.path.exists(thumbnail_path):
                    try:
                        self.upload_featured_image(post_id, thumbnail_path, session, auth)
                        #    upload_featured_image  
                    except Exception as e:
                        self.log(f"    : {e}")
                        import traceback
                        self.log(f"   : {traceback.format_exc()}")
                
                return {'success': True, 'edit_url': edit_url, 'post_url': post_url}
            else:
                self.log(f"  : {response.status_code} - {response.text}")
                return {'success': False}
                
        except Exception as e:
            self.log(f" : {e}")
            return {'success': False}
    
    def upload_featured_image(self, post_id, image_path, session, auth):
        """  """
        try:
            site_url = self.config_data.get('site_url', '').rstrip('/')
            media_url = f"{site_url}/wp-json/wp/v2/media"
            
            #   
            with open(image_path, 'rb') as img_file:
                files = {'file': img_file}
                headers = {'Content-Disposition': f'attachment; filename="{os.path.basename(image_path)}"'}
                
                response = session.post(media_url, files=files, headers=headers, auth=auth, timeout=30)
                
                if response.status_code == 201:
                    media_info = response.json()
                    media_id = media_info.get('id')
                    
                    #    
                    post_url = f"{site_url}/wp-json/wp/v2/posts/{post_id}"
                    update_data = {'featured_media': media_id}
                    
                    session.post(post_url, json=update_data, auth=auth, timeout=30)
                    self.log(f"   ")
                    
        except Exception as e:
            self.log(f"   : {e}")
            import traceback
            self.log(f"   : {traceback.format_exc()}")

    def move_keyword_to_used(self, keyword):
        """  used_keywords.txt """
        try:
            # used_keywords.txt 
            used_keywords_path = os.path.join(get_base_path(), "used_keywords.txt")
            with open(used_keywords_path, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{keyword} (: {timestamp})\n")
            
            # keywords.txt   
            keywords_path = os.path.join(get_base_path(), "keywords.txt")
            if os.path.exists(keywords_path):
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                #     
                updated_lines = []
                for line in lines:
                    if line.strip() != keyword and not line.strip().startswith('#'):
                        updated_lines.append(line)
                    elif line.strip() != keyword:  #  
                        updated_lines.append(line)
                
                with open(keywords_path, 'w', encoding='utf-8') as f:
                    f.writelines(updated_lines)
            
            self.log(f"   : {keyword}")
        except Exception as e:
            self.log(f"  : {e}")

class AutoWP(QMainWindow):
    #    
    log_signal = pyqtSignal(str)  #    
    update_buttons_signal = pyqtSignal()  #    
    
    def __init__(self):
        super().__init__()
        
        # GUI    
        self._is_initializing = True
        
        self.setWindowTitle("Auto WP - WordPress   ")
        self.setGeometry(100, 100, 1400, 900)
        
        #    
        if platform.system() == "Windows":
            try:
                # Windows  
                import ctypes
                self.user32 = ctypes.windll.user32
                self.kernel32 = ctypes.windll.kernel32
            except:
                pass
        
        #   
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {WORDPRESS_COLORS['background_dark']};
                color: {WORDPRESS_COLORS['text_primary']};
                font-family: 'Segoe UI', 'Inter', 'Arial', sans-serif;
            }}
            QLabel {{
                color: {WORDPRESS_COLORS['text_primary']};
                font-size: 14px;
            }}
            QLineEdit, QTextEdit, QSpinBox, QComboBox {{
                background-color: {WORDPRESS_COLORS['surface_light']};
                border: 1px solid {WORDPRESS_COLORS['surface_light']};
                border-radius: 4px;
                padding: 8px;
                color: {WORDPRESS_COLORS['text_primary']};
                font-size: 14px;
            }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border: 2px solid {WORDPRESS_COLORS['primary_blue']};
            }}
        """)
        
        #   
        try:
            if os.path.exists("daivd153.ico"):
                self.setWindowIcon(QIcon("daivd153.ico"))
        except:
            pass
        
        #  
        self.config_data = {}
        self.posting_thread = None
        self.is_posting = False
        self.is_paused = False
        self.current_keyword = ""
        self.remaining_keywords = []
        self.wait_time = 0
        self.total_keywords = 0
        self.success_count = 0
        self.fail_count = 0
        self.pause_start_time = None
        self.data_lock = threading.Lock()  #    
        self.remaining_wait_time = 0
        self.paused_wait_time = 0  #     
        
        #   
        self.posting_mode = " "
        
        # GUI 
        self.setup_ui()

        #  
        self.load_config()
        self.update_config_display()
        
        #    GUI   (GUI   )
        # self.log(" Auto WP !")  # 
        self.log("=" * 50)
        self.log("WordPress    v8.12")
        self.log(": ")
        self.log("=" * 50)
        
        #   
        #    ( )
        self.timer = QTimer()
        self.timer.timeout.connect(self.safe_update_status_display)
        self.timer.start(5000)  # 5  ( )
        
        #    
        self.log_signal.connect(self._safe_log_to_gui)
        self.update_buttons_signal.connect(self._safe_update_button_states)
    
    def setup_ui(self):
        """UI """
        #  
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        #  
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        #    ( )
        self.content_stack = QStackedWidget()
        self.setupPages()
        main_layout.addWidget(self.content_stack)
        
        central_widget.setLayout(main_layout)
        
        # 
        self.statusBar().setStyleSheet(f"""
            QStatusBar {{
                background-color: {WORDPRESS_COLORS['surface_dark']};
                border-top: 1px solid {WORDPRESS_COLORS['surface_light']};
                color: {WORDPRESS_COLORS['text_secondary']};
            }}
        """)
        self.statusBar().showMessage("                                                                                                                                                                                                                                                                                                                          : ")
        
        #  
        self._is_initializing = False
        
    def resizeEvent(self, event):
        """       -  """
        #     
        if getattr(self, '_is_initializing', True) or not event:
            return
        
        #  resizeEvent    
        try:
            super().resizeEvent(event)
        except:
            pass  #   
    
    def adjust_component_sizes(self):
        """     """
        #    16px    
        try:
            #    
            #     
            pass  #     ( )
        except Exception as e:
            #     
            pass
            pass
                
        except (AttributeError, RuntimeError):
            #     
            pass
    
    def setupPages(self):
        """ """
        self.pages = {
            'dashboard': self.create_dashboard_page()
        }
        
        for page in self.pages.values():
            self.content_stack.addWidget(page)
        
        self.content_stack.setCurrentWidget(self.pages['dashboard'])
        
        #    
        self.update_button_states()

    def create_dashboard_page(self):
        """  """
        page = QWidget()
        
        #   
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        #    
        scroll_content = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        #     
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)
        
        #   -       
        left_column = QVBoxLayout()
        left_column.setSpacing(15)
        
        # WordPress  
        wordpress_card = ModernCard("   ")
        wordpress_layout = QVBoxLayout()
        wordpress_layout.setSpacing(5)
        wordpress_layout.setContentsMargins(10, 5, 10, 5)
        
        #    
        mode_buttons_layout = QVBoxLayout()
        mode_buttons_layout.setSpacing(8)
        
        self.approval_mode_btn = WordPressButton(" ", "secondary")
        self.revenue_mode_btn = WordPressButton(" ", "primary")
        
        #      
        for btn in [self.approval_mode_btn, self.revenue_mode_btn]:
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(50)
            btn.setCheckable(True)
            #   14px 
            current_style = btn.styleSheet()
            btn.setStyleSheet(current_style.replace('font-size: 16px', 'font-size: 14px'))
        
        #    
        self.revenue_mode_btn.setChecked(True)  # :  
        
        #   
        self.revenue_mode_btn.clicked.connect(lambda: self.select_posting_mode(" "))
        self.approval_mode_btn.clicked.connect(lambda: self.select_posting_mode(" "))
        
        mode_buttons_layout.addWidget(self.approval_mode_btn)
        mode_buttons_layout.addWidget(self.revenue_mode_btn)
        
        wordpress_layout.addLayout(mode_buttons_layout)
        wordpress_card.layout().addLayout(wordpress_layout)
        wordpress_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        left_column.addWidget(wordpress_card)

        #   
        posting_card = ModernCard("  ")
        posting_layout = QVBoxLayout()
        posting_layout.setSpacing(5)
        posting_layout.setContentsMargins(10, 5, 10, 5)
        
        #    - 2x2 
        posting_buttons_layout = QVBoxLayout()
        posting_buttons_layout.setSpacing(8)
        
        #   : , 
        first_row_layout = QHBoxLayout()
        first_row_layout.setSpacing(8)
        
        self.start_btn = WordPressButton(" ", "primary")
        self.stop_btn = WordPressButton(" ", "error")
        
        #   : , 
        second_row_layout = QHBoxLayout()
        second_row_layout.setSpacing(8)
        
        self.resume_btn = WordPressButton(" ", "success")
        self.pause_btn = WordPressButton(" ", "warning")
        
        #      
        for btn in [self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn]:
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(50)
            #   14px 
            current_style = btn.styleSheet()
            btn.setStyleSheet(current_style.replace('font-size: 16px', 'font-size: 14px'))
        
        #   
        self.start_btn.clicked.connect(self.start_posting)
        self.stop_btn.clicked.connect(self.stop_posting)
        self.resume_btn.clicked.connect(self.resume_posting)
        self.pause_btn.clicked.connect(self.pause_posting)
        
        #     
        first_row_layout.addWidget(self.start_btn)
        first_row_layout.addWidget(self.stop_btn)
        
        #     
        second_row_layout.addWidget(self.resume_btn)
        second_row_layout.addWidget(self.pause_btn)
        
        #  
        posting_buttons_layout.addLayout(first_row_layout)
        posting_buttons_layout.addLayout(second_row_layout)
        
        posting_layout.addLayout(posting_buttons_layout)
        posting_card.layout().addLayout(posting_layout)
        posting_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        left_column.addWidget(posting_card)
        
        #   -    
        right_column = QVBoxLayout()
        right_column.setSpacing(15)
        
        #   
        monitoring_card = ModernCard("  ")
        monitoring_layout = QVBoxLayout()
        monitoring_layout.setSpacing(10)
        
        #    - 3  
        status_info_layout = QHBoxLayout()
        status_info_layout.setSpacing(20)
        
        #  
        keyword_widget = QWidget()
        keyword_layout = QVBoxLayout()
        keyword_layout.setContentsMargins(0, 0, 0, 0)
        keyword_layout.setSpacing(2)  #  
        
        keyword_title = QLabel(" ")
        keyword_title.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        keyword_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        keyword_layout.addWidget(keyword_title)
        
        self.current_keyword_label = QLabel("")
        self.current_keyword_label.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['primary_blue']};
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            background-color: rgba(0, 123, 255, 0.1);
            border-radius: 8px;
            border: 1px solid {WORDPRESS_COLORS['primary_blue']};
        """)
        self.current_keyword_label.setWordWrap(True)
        self.current_keyword_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.current_keyword_label.setFixedHeight(40)  #   
        keyword_layout.addWidget(self.current_keyword_label)
        keyword_widget.setLayout(keyword_layout)
        
        #  
        remaining_widget = QWidget()
        remaining_layout = QVBoxLayout()
        remaining_layout.setContentsMargins(0, 0, 0, 0)
        remaining_layout.setSpacing(2)  #  
        
        remaining_title = QLabel(" ")
        remaining_title.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        remaining_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        remaining_layout.addWidget(remaining_title)
        
        self.remaining_keywords_label = QLabel("0")
        self.remaining_keywords_label.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['warning']};
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            background-color: rgba(255, 193, 7, 0.1);
            border-radius: 8px;
            border: 1px solid {WORDPRESS_COLORS['warning']};
        """)
        self.remaining_keywords_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.remaining_keywords_label.setFixedHeight(40)  #   
        remaining_layout.addWidget(self.remaining_keywords_label)
        remaining_widget.setLayout(remaining_layout)
        
        #  
        wait_widget = QWidget()
        wait_layout = QVBoxLayout()
        wait_layout.setContentsMargins(0, 0, 0, 0)
        wait_layout.setSpacing(2)  #  
        
        #  
        keyword_widget = QWidget()
        keyword_layout = QVBoxLayout()
        keyword_layout.setContentsMargins(0, 0, 0, 0)
        keyword_layout.setSpacing(2)
        
        keyword_title = QLabel(" ")
        keyword_title.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        keyword_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        keyword_layout.addWidget(keyword_title)
        
        self.current_keyword_label = QLabel("")
        self.current_keyword_label.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['primary_blue']};
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            background-color: rgba(0, 123, 255, 0.1);
            border-radius: 8px;
            border: 1px solid {WORDPRESS_COLORS['primary_blue']};
        """)
        self.current_keyword_label.setWordWrap(True)
        self.current_keyword_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.current_keyword_label.setFixedHeight(40)
        keyword_layout.addWidget(self.current_keyword_label)
        keyword_widget.setLayout(keyword_layout)
        
        #  
        remaining_widget = QWidget()
        remaining_layout = QVBoxLayout()
        remaining_layout.setContentsMargins(0, 0, 0, 0)
        remaining_layout.setSpacing(2)
        
        remaining_title = QLabel(" ")
        remaining_title.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        remaining_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        remaining_layout.addWidget(remaining_title)
        
        self.remaining_keywords_label = QLabel("0")
        self.remaining_keywords_label.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['warning']};
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            background-color: rgba(255, 193, 7, 0.1);
            border-radius: 8px;
            border: 1px solid {WORDPRESS_COLORS['warning']};
        """)
        self.remaining_keywords_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.remaining_keywords_label.setFixedHeight(40)
        remaining_layout.addWidget(self.remaining_keywords_label)
        remaining_widget.setLayout(remaining_layout)
        
        #  
        wait_widget = QWidget()
        wait_layout = QVBoxLayout()
        wait_layout.setContentsMargins(0, 0, 0, 0)
        wait_layout.setSpacing(2)
        
        wait_title = QLabel(" ")
        wait_title.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        wait_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wait_layout.addWidget(wait_title)
        
        self.wait_time_label = QLabel("0 0")
        self.wait_time_label.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_secondary']};
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            background-color: rgba(108, 117, 125, 0.1);
            border-radius: 8px;
            border: 1px solid {WORDPRESS_COLORS['text_secondary']};
        """)
        self.wait_time_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.wait_time_label.setFixedHeight(40)
        wait_layout.addWidget(self.wait_time_label)
        wait_widget.setLayout(wait_layout)
        
        #  
        keyword_widget = QWidget()
        keyword_layout = QVBoxLayout()
        keyword_layout.setContentsMargins(0, 0, 0, 0)
        keyword_layout.setSpacing(2)
        
        keyword_title = QLabel(" ")
        keyword_title.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        keyword_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        keyword_layout.addWidget(keyword_title)
        
        self.current_keyword_label = QLabel("")
        self.current_keyword_label.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['primary_blue']};
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            background-color: rgba(0, 123, 255, 0.1);
            border-radius: 8px;
            border: 1px solid {WORDPRESS_COLORS['primary_blue']};
        """)
        self.current_keyword_label.setWordWrap(True)
        self.current_keyword_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.current_keyword_label.setFixedHeight(40)
        keyword_layout.addWidget(self.current_keyword_label)
        keyword_widget.setLayout(keyword_layout)
        
        #  
        remaining_widget = QWidget()
        remaining_layout = QVBoxLayout()
        remaining_layout.setContentsMargins(0, 0, 0, 0)
        remaining_layout.setSpacing(2)
        
        remaining_title = QLabel(" ")
        remaining_title.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        remaining_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        remaining_layout.addWidget(remaining_title)
        
        self.remaining_keywords_label = QLabel("0")
        self.remaining_keywords_label.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['warning']};
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            background-color: rgba(255, 193, 7, 0.1);
            border-radius: 8px;
            border: 1px solid {WORDPRESS_COLORS['warning']};
        """)
        self.remaining_keywords_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.remaining_keywords_label.setFixedHeight(40)
        remaining_layout.addWidget(self.remaining_keywords_label)
        remaining_widget.setLayout(remaining_layout)
        
        #  
        wait_widget = QWidget()
        wait_layout = QVBoxLayout()
        wait_layout.setContentsMargins(0, 0, 0, 0)
        wait_layout.setSpacing(2)
        
        wait_title = QLabel(" ")
        wait_title.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_primary']};
            font-size: 14px;
            font-weight: bold;
        """)
        wait_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wait_layout.addWidget(wait_title)
        
        self.wait_time_label = QLabel("0 0")
        self.wait_time_label.setStyleSheet(f"""
            color: {WORDPRESS_COLORS['text_secondary']};
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            background-color: rgba(108, 117, 125, 0.1);
            border-radius: 8px;
            border: 1px solid {WORDPRESS_COLORS['text_secondary']};
        """)
        self.wait_time_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.wait_time_label.setFixedHeight(40)
        wait_layout.addWidget(self.wait_time_label)
        wait_widget.setLayout(wait_layout)
        
        status_info_layout.addWidget(keyword_widget)
        status_info_layout.addWidget(remaining_widget)
        status_info_layout.addWidget(wait_widget)
        
        monitoring_layout.addLayout(status_info_layout)
        monitoring_card.layout().addLayout(monitoring_layout)
        monitoring_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        #    ( )
        files_card = ModernCard("  ")
        files_layout = QVBoxLayout()
        files_layout.setSpacing(5)
        files_layout.setContentsMargins(10, 5, 10, 5)
        
        #   
        file_buttons_layout = QVBoxLayout()
        file_buttons_layout.setSpacing(8)
        
        #    -    
        first_row = QHBoxLayout()
        first_row.setSpacing(8)
        
        self.open_keywords_btn = WordPressButton("   ", "secondary")
        self.open_excel_config_btn = WordPressButton("   ", "secondary")
        
        first_row.addWidget(self.open_keywords_btn)
        first_row.addWidget(self.open_excel_config_btn)
        
        #    -    
        second_row = QHBoxLayout()
        second_row.setSpacing(8)
        
        self.open_prompts_btn = WordPressButton("   ", "secondary")
        self.open_images_btn = WordPressButton("   ", "secondary")
        
        second_row.addWidget(self.open_prompts_btn)
        second_row.addWidget(self.open_images_btn)
        
        #       
        for btn in [self.open_keywords_btn, self.open_excel_config_btn, self.open_prompts_btn, self.open_images_btn]:
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(40)
            btn.setCheckable(False)
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setDown(False)
            #   14px 
            current_style = btn.styleSheet()
            btn.setStyleSheet(current_style.replace('font-size: 16px', 'font-size: 14px'))
            btn.setStyleSheet(btn.styleSheet().replace('font-size: 14px', 'font-size: 14px'))
        
        #    
        self.open_keywords_btn.clicked.connect(self.open_keywords_file)
        self.open_excel_config_btn.clicked.connect(self.open_excel_config_file)
        self.open_prompts_btn.clicked.connect(self.open_prompts_folder)
        self.open_images_btn.clicked.connect(self.open_images_folder)
        
        file_buttons_layout.addLayout(first_row)
        file_buttons_layout.addLayout(second_row)
        
        files_layout.addLayout(file_buttons_layout)
        files_card.layout().addLayout(files_layout)
        files_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        right_column.addWidget(files_card)
        
        #    (  )
        right_column.addWidget(monitoring_card)
        
        #      
        top_layout.addLayout(left_column, 1)  # stretch factor 1
        top_layout.addLayout(right_column, 1)  # stretch factor 1
        
        #   
        layout.addLayout(top_layout, 0)  # stretch factor 0 
        
        #  -   
        self.create_progress_section(layout)
        
        #    
        scroll_content.setLayout(layout)
        scroll_area.setWidget(scroll_content)
        
        #    
        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll_area)
        page.setLayout(page_layout)
        
        return page

    def create_progress_section(self, layout):
        """   """
        #    ( )
        progress_card = ModernCard("  ")
        
        #  URL 
        self.site_url_label = QLabel(" :  ")
        self.site_url_label.setStyleSheet(f"""
            QLabel {{
                color: {WORDPRESS_COLORS['primary_blue']};
                font-size: 14px;
                text-decoration: underline;
                padding: 8px;
                margin-bottom: 10px;
            }}
            QLabel:hover {{
                color: {WORDPRESS_COLORS['dark_blue']};
                background-color: {WORDPRESS_COLORS['surface_light']};
                border-radius: 4px;
            }}
        """)
        self.site_url_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.site_url_label.mousePressEvent = self.open_wp_admin
        
        #  URL   
        progress_card.addContent(self.site_url_label)
        
        #    (QTextBrowser  -   )
        self.progress_log = QTextBrowser()
        self.progress_log.setReadOnly(True)
        self.progress_log.setMinimumHeight(400)
        self.progress_log.setMaximumHeight(600)
        self.progress_log.setOpenExternalLinks(True)  #    
        
        # wheelEvent  progress_log 
        self.progress_log.wheelEvent = self.progress_log_wheel_event
        
        #     (wheelEvent  )
        default_font = self.progress_log.font()
        default_font.setPointSize(12)
        default_font.setFamily('Consolas, Monaco, monospace')
        self.progress_log.setFont(default_font)
        
        #  (QTextBrowser)
        self.progress_log.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {WORDPRESS_COLORS['background_dark']};
                border: 1px solid {WORDPRESS_COLORS['surface_light']};
                border-radius: 8px;
                color: {WORDPRESS_COLORS['text_primary']};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                padding: 10px;
            }}
            QScrollBar:vertical {{
                background-color: {WORDPRESS_COLORS['surface_dark']};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {WORDPRESS_COLORS['primary_blue']};
                border-radius: 6px;
                min-height: 20px;
            }}
        """)
        
        #     
        progress_card.addContent(self.progress_log)
        
        #    ( stretch factor   )
        layout.addWidget(progress_card, 1)

    def progress_log_wheel_event(self, event):
        """  Ctrl+ /  """
        try:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                # Ctrl     
                delta = event.angleDelta().y()
                current_font = self.progress_log.font()
                current_size = current_font.pointSize()
                
                #   0    
                if current_size <= 0:
                    current_size = 12
                
                if delta > 0:  #    ()
                    new_size = min(current_size + 1, 24)  #  24px
                else:  #    ()
                    new_size = max(current_size - 1, 8)   #  8px
                
                #   
                if new_size > 0:
                    current_font.setPointSize(new_size)
                    self.progress_log.setFont(current_font)
                event.accept()
                return
            else:
                #  
                from PyQt6.QtWidgets import QTextBrowser
                QTextBrowser.wheelEvent(self.progress_log, event)
        except Exception as e:
            #       
            try:
                from PyQt6.QtWidgets import QTextBrowser
                QTextBrowser.wheelEvent(self.progress_log, event)
            except:
                pass

    def select_posting_mode(self, mode):
        """   ( )"""
        self.posting_mode = mode
        
        #   
        if mode == " ":
            self.revenue_mode_btn.setChecked(True)
            self.revenue_mode_btn.setButtonType("primary")
            self.approval_mode_btn.setChecked(False)
            self.approval_mode_btn.setButtonType("secondary")
        else:  #  
            self.approval_mode_btn.setChecked(True)
            self.approval_mode_btn.setButtonType("primary")
            self.revenue_mode_btn.setChecked(False)
            self.revenue_mode_btn.setButtonType("secondary")
        
        self.log(f"  : {mode}")
        self.update_button_states()

    def update_button_states(self):
        """    """
        try:
            #     
            self.update_buttons_signal.emit()
        except Exception as e:
            print(f"    : {e}")

    def _safe_update_button_states(self):
        """     """
        try:
            if not hasattr(self, 'start_btn') or not self.start_btn:
                return  #     
                
            if self.is_posting:
                if self.is_paused:
                    #  
                    self.start_btn.setEnabled(False)
                    self.start_btn.setActive(True)
                    if hasattr(self, 'stop_btn'):
                        self.stop_btn.setEnabled(True)
                    if hasattr(self, 'resume_btn'):
                        self.resume_btn.setEnabled(True)
                        self.resume_btn.setText(" ")
                    if hasattr(self, 'pause_btn'):
                        self.pause_btn.setEnabled(False)
                else:
                    #  
                    self.start_btn.setEnabled(False)
                    self.start_btn.setActive(True)
                    if hasattr(self, 'stop_btn'):
                        self.stop_btn.setEnabled(True)
                    if hasattr(self, 'resume_btn'):
                        self.resume_btn.setEnabled(False)
                    if hasattr(self, 'pause_btn'):
                        self.pause_btn.setEnabled(True)
            else:
                #   -     
                self.start_btn.setEnabled(True)
                self.start_btn.setActive(False)
                self.start_btn.setText(" ")
                if hasattr(self, 'stop_btn'):
                    self.stop_btn.setEnabled(False)
                if hasattr(self, 'resume_btn'):
                    self.resume_btn.setEnabled(True)
                    self.resume_btn.setText(" ")
                if hasattr(self, 'pause_btn'):
                    self.pause_btn.setEnabled(False)
        except (AttributeError, RuntimeError) as e:
            #       
            pass
        except Exception as e:
            #       
            pass

    def reload_resources(self):
        """   """
        try:
            #   
            self.load_config()
            self.update_config_display()
            
            #     (   )
            if self.is_posting and not self.is_paused:
                new_keywords = self.load_keywords()
                #    
                used_keywords = []
                try:
                    used_path = os.path.join(get_base_path(), "used_keywords.txt")
                    if os.path.exists(used_path):
                        with open(used_path, 'r', encoding='utf-8') as f:
                            used_keywords = [line.strip() for line in f.readlines()]
                except:
                    pass
                
                #   
                for keyword in new_keywords:
                    if keyword not in used_keywords and keyword not in self.remaining_keywords:
                        self.remaining_keywords.append(keyword)
            
            #    ( )
            
        except Exception as e:
            self.log(f"   : {e}")

    def switch_posting_mode(self, mode):
        """   ( )"""
        self.posting_mode = mode
        self.log(f"  : {mode}")
    
    def safe_update_status_display(self):
        """    ()"""
        try:
            #      
            if getattr(self, '_is_initializing', True):
                return
            
            # GUI   
            if not hasattr(self, 'current_keyword_label') or not self.current_keyword_label:
                return
                
            #   
            self.update_status_display()
        except Exception as e:
            #       (  )
            pass
    
    def update_status_display(self):
        """  """
        try:
            #   
            if hasattr(self, 'current_keyword_label') and self.current_keyword_label:
                try:
                    current_keyword = getattr(self, 'current_keyword', "")
                    self.current_keyword_label.setText(current_keyword or "")
                except (RuntimeError, AttributeError):
                    # GUI   
                    pass
                    
            #   
            if hasattr(self, 'remaining_keywords_label') and self.remaining_keywords_label:
                try:
                    remaining_keywords = getattr(self, 'remaining_keywords', [])
                    if remaining_keywords is not None and isinstance(remaining_keywords, list):
                        remaining_count = len(remaining_keywords)
                    else:
                        remaining_count = 0
                    self.remaining_keywords_label.setText(f"{remaining_count}")
                except (RuntimeError, AttributeError):
                    # GUI   
                    pass
            
            if hasattr(self, 'wait_time_label') and self.wait_time_label:
                try:
                    wait_time = getattr(self, 'wait_time', 0)
                    if isinstance(wait_time, (int, float)) and wait_time >= 0:
                        minutes = int(wait_time) // 60
                        seconds = int(wait_time) % 60
                        self.wait_time_label.setText(f"{minutes} {seconds}")
                    else:
                        self.wait_time_label.setText("0 0")
                except (RuntimeError, AttributeError):
                    # GUI   
                    pass
                
        except Exception as e:
            #        
            pass

    def safe_update_status_display(self, message=None):
        """    (   )"""
        try:
            if message:
                #     
                self.log(message)
            self.update_status_display()
        except Exception as e:
            #       
            pass

    def update_config_display(self):
        """  """
        try:
            #      -     
            if hasattr(self, 'site_url_input'):
                site_url = self.config_data.get('site_url', '')
                if site_url and site_url not in ['', 'https://yoursite.com', 'https://your-site.com']:
                    self.site_url_input.setText(site_url)
                else:
                    self.site_url_input.setText('')
                    
            if hasattr(self, 'username_input'):
                username = self.config_data.get('username', '')
                if username and username not in ['', 'your_username']:
                    self.username_input.setText(username)
                else:
                    self.username_input.setText('')
                    
            if hasattr(self, 'password_input'):
                password = self.config_data.get('password', '')
                if password and password not in ['', 'your_password']:
                    self.password_input.setText(password)
                else:
                    self.password_input.setText('')
                    
            if hasattr(self, 'category_input'):
                category = str(self.config_data.get('category', '1'))
                if category and category not in ['', '1']:
                    self.category_input.setText(category)
                else:
                    self.category_input.setText('')
                    
            if hasattr(self, 'api_key_input'):
                api_key = self.config_data.get('gpt_api_key', '')
                if api_key and api_key not in ['', 'your_openai_api_key']:
                    self.api_key_input.setText(api_key)
                else:
                    self.api_key_input.setText('')
                    
            if hasattr(self, 'wait_input'):
                wait_time = self.config_data.get('wait_minutes', '5-10')
                if wait_time and wait_time not in ['', '5-10']:
                    self.wait_input.setText(wait_time)
                else:
                    self.wait_input.setText('')
                    
            if hasattr(self, 'model_input'):
                model = self.config_data.get('gpt_model', 'gpt-4o-mini')
                index = self.model_input.findText(model)
                if index >= 0:
                    self.model_input.setCurrentIndex(index)
            
            #    
            if hasattr(self, 'site_info_label'):
                site_url = self.config_data.get('site_url', '')
                if site_url and site_url not in ['', 'https://yoursite.com', 'https://your-site.com']:
                    self.site_info_label.setText(f" URL - {site_url}")
                    self.site_info_label.setStyleSheet(f"color: {WORDPRESS_COLORS['success']}; font-size: 14px;")
                else:
                    self.site_info_label.setText(" URL -  ")
                    self.site_info_label.setStyleSheet(f"color: {WORDPRESS_COLORS['error']}; font-size: 14px;")
            
            if hasattr(self, 'user_info_label'):
                username = self.config_data.get('username', '')
                if username and username not in ['', 'your_username']:
                    self.user_info_label.setText(f" - {username}")
                    self.user_info_label.setStyleSheet(f"color: {WORDPRESS_COLORS['success']}; font-size: 14px;")
                else:
                    self.user_info_label.setText(" -  ")
                    self.user_info_label.setStyleSheet(f"color: {WORDPRESS_COLORS['error']}; font-size: 14px;")
            
            if hasattr(self, 'api_info_label'):
                api_key = self.config_data.get('gpt_api_key', '')
                if api_key and api_key not in ['', 'your_openai_api_key']:
                    self.api_info_label.setText("API  -  ")
                    self.api_info_label.setStyleSheet(f"color: {WORDPRESS_COLORS['success']}; font-size: 14px;")
                else:
                    self.api_info_label.setText("API  -  ")
                    self.api_info_label.setStyleSheet(f"color: {WORDPRESS_COLORS['error']}; font-size: 14px;")
                    
        except Exception as e:
            print(f"   : {e}")

    def log(self, message):
        """   """
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            
            #   ( )
            print(formatted_message)
            
            # GUI      
            self.log_signal.emit(formatted_message)
                
        except Exception as e:
            print(f" : {e}")

    def _safe_log_to_gui(self, formatted_message):
        """   GUI  """
        try:
            if hasattr(self, 'progress_log') and self.progress_log is not None:
                # URL HTML   (  )
                import re
                html_message = formatted_message
                # URL    (, ,    )
                url_pattern = r'(https?://[^\s,.\)]+)'
                html_message = re.sub(url_pattern, r'<a href="\1">\1</a>', html_message)
                
                # HTML  (  )
                self.progress_log.append(html_message)
                
                #  
                from PyQt6.QtGui import QTextCursor
                self.progress_log.moveCursor(QTextCursor.MoveOperation.End)
                
                #     ( 50 )
                if self.progress_log.document().lineCount() > 50:
                    cursor = self.progress_log.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.Start)
                    cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, 1)
                    cursor.removeSelectedText()
                    
        except Exception as gui_error:
            # GUI   
            print(f"GUI   : {gui_error}")

    def _update_progress_gui(self, message):
        """GUI   (    -   )"""
        try:
            if hasattr(self, 'progress_log') and self.progress_log is not None:
                self.progress_log.appendPlainText(message)
                
                #  
                from PyQt6.QtGui import QTextCursor
                self.progress_log.moveCursor(QTextCursor.MoveOperation.End)
                
                #     ( 50 )
                if self.progress_log.document().lineCount() > 50:
                    cursor = self.progress_log.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.Start)
                    for _ in range(10):  #  10 
                        cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
                    cursor.removeSelectedText()
        except Exception as e:
            print(f"GUI  : {e}")

    def show_clickable_success(self, title, edit_url, count):
        """    - URL  """
        try:
            #  HTML   
            title = re.sub(r'```html\s*', '', title)
            title = re.sub(r'```\s*', '', title)
            title = title.strip()
            
            #   
            display_title = title[:80] + "..." if len(title) > 80 else title
            
            #   (    )
            self.log(f"  : {display_title}")
            if edit_url:
                # URL  
                self.log(f"   : {edit_url}")
        
        except Exception as e:
            try:
                self.log(f"     : {e}")
            except:
                print(f"   : {e}")

    def _update_success_gui(self, timestamp, title, edit_url):
        """GUI   """
        try:
            if hasattr(self, 'progress_log') and self.progress_log is not None:
                #  
                success_msg = f"[{timestamp}]   : {title}"
                self.progress_log.appendPlainText(success_msg)
                
                #  
                if edit_url:
                    edit_msg = f"[{timestamp}]    : {edit_url}"
                    self.progress_log.appendPlainText(edit_msg)
                
                #  
                from PyQt6.QtGui import QTextCursor
                self.progress_log.moveCursor(QTextCursor.MoveOperation.End)
        except Exception as e:
            print(f"GUI    : {e}")

    def open_link_in_browser(self, url):
        """  """
        try:
            import webbrowser
            webbrowser.open(url.toString())
            if hasattr(self, 'log'):
                self.log(f"  : {url.toString()}")
        except Exception as e:
            try:
                if hasattr(self, 'log'):
                    self.log(f"  : {e}")
            except:
                print(f"  : {e}")

    def open_edit_url(self, url):
        """ URL """
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            try:
                if hasattr(self, 'log'):
                    self.log(f"URL  : {e}")
            except:
                print(f"URL  : {e}")

    def open_wp_admin(self, event):
        """    """
        try:
            if hasattr(self, 'config_data') and self.config_data:
                site_url = self.config_data.get('site_url', '')
                if site_url and site_url not in ['', 'https://your-site.com']:
                    # URL  - edit.php  
                    admin_url = site_url.rstrip('/')
                    admin_url += '/wp-admin/edit.php'
                    
                    #    (  )
                    import webbrowser
                    webbrowser.open(admin_url)
                else:
                    if hasattr(self, 'log'):
                        self.log("  URL  .    .")
            else:
                if hasattr(self, 'log'):
                    self.log("    .")
        except Exception as e:
            try:
                if hasattr(self, 'log'):
                    self.log(f"    : {e}")
            except:
                print(f"    : {e}")

    def update_site_url_display(self):
        """ URL  """
        try:
            if hasattr(self, 'config_data') and self.config_data:
                site_url = self.config_data.get('site_url', '')
                if site_url and site_url not in ['', 'https://your-site.com']:
                    # URL   
                    display_url = site_url.replace('https://', '').replace('http://', '')
                    if hasattr(self, 'site_url_label'):
                        self.site_url_label.setText(f" : {display_url}")
                else:
                    if hasattr(self, 'site_url_label'):
                        self.site_url_label.setText(" :  ")
            else:
                if hasattr(self, 'site_url_label'):
                    self.site_url_label.setText(" :  ")
        except Exception as e:
            self.log(f" URL  : {e}")

    def load_config(self):
        """   (XLSX  )"""
        try:
            excel_path = os.path.join(get_base_path(), "wordpress_setting.xlsx")
            if os.path.exists(excel_path):
                # XLSX   (  )
                df = pd.read_excel(excel_path, engine='openpyxl')
                
                #   
                self.config_data = {}
                for _, row in df.iterrows():
                    self.config_data[row['']] = row['']
                
                #       ( )
                if not hasattr(self, 'config_loaded') or not self.config_loaded:
                    self.log("     ")
                    self.config_loaded = True
                #  URL  
                self.update_site_url_display()
            else:
                self.create_excel_config_file()
                
        except Exception as e:
            self.log(f"   : {e}")
            self.create_excel_config_file()

    def create_excel_config_file(self):
        """    (XLSX ,    )"""
        try:
            excel_path = os.path.join(get_base_path(), "wordpress_setting.xlsx")
            
            #   
            config_data = {
                '': ['site_url', 'username', 'password', 'gpt_api_key', 'gpt_model', 'category', 'wait_minutes'],
                '': ['https://your-site.com', 'your_username', 'your_password', 'your_openai_api_key', 'gpt-4o-mini', '1', '5-10'],
                '': [
                    'WordPress  URL (: https://yoursite.com)',
                    'WordPress  ',
                    'WordPress   (   )',
                    'OpenAI API  - openai.com API Keys   (sk-  )',
                    ' GPT  (gpt-4o-mini )',
                    '  ',
                    '  ()'
                ]
            }
            
            # DataFrame   XLSX  (   )
            df = pd.DataFrame(config_data)
            df.to_excel(excel_path, index=False, engine='openpyxl')
            
            #   
            self.config_data = {}
            for i, setting_name in enumerate(config_data['']):
                self.config_data[setting_name] = config_data[''][i]
            
            self.log(" XLSX      (  )")
            
        except Exception as e:
            self.log(f"    : {e}")

    def create_config_file(self):
        """   (JSON ) -  """
        self.create_excel_config_file()

    def load_keywords(self):
        """  """
        try:
            keywords_path = os.path.join(get_base_path(), "keywords.txt")
            if not os.path.exists(keywords_path):
                return []
            
            with open(keywords_path, 'r', encoding='utf-8') as f:
                keywords = [line.strip() for line in f.readlines() 
                           if line.strip() and not line.strip().startswith('#')]
            
            return keywords
            
        except Exception as e:
            self.log(f"  : {e}")
            return []

    def open_keywords_file(self):
        """  """
        try:
            keywords_path = os.path.join(get_base_path(), "keywords.txt")
            
            if os.path.exists(keywords_path):
                if os.name == 'nt':  # Windows
                    os.startfile(keywords_path)
                else:  #  OS
                    subprocess.run(['open', keywords_path], check=False)
                self.log("   ")
            else:
                #    
                with open(keywords_path, 'w', encoding='utf-8') as f:
                    f.write("#     \n")
                    f.write("# :\n")
                    f.write("# 1\n")
                    f.write("# 2\n")
                
                if os.name == 'nt':  # Windows
                    os.startfile(keywords_path)
                else:  #  OS
                    subprocess.run(['open', keywords_path], check=False)
                self.log("     ")
            
        except Exception as e:
            self.log(f"   : {e}")

    def open_excel_config_file(self):
        """    (    )"""
        try:
            excel_path = os.path.join(get_base_path(), "wordpress_setting.xlsx")
            if not os.path.exists(excel_path):
                #   
                self.create_excel_config_file()
            
            #     
            if os.name == 'nt':  # Windows
                os.startfile(excel_path)
            else:  #  OS
                subprocess.run(['open', excel_path], check=False)
                
            self.log(" XLSX     ")
            
        except Exception as e:
            self.log(f"     : {e}")

    def open_prompts_folder(self):
        """  """
        try:
            base_path = get_base_path()
            prompts_path = os.path.join(base_path, "prompts")
            
            #   
            if not os.path.exists(prompts_path):
                os.makedirs(prompts_path, exist_ok=True)
                #    
                self.create_default_prompts(prompts_path)
            
            #    (check=False )
            if os.name == 'nt':  # Windows
                subprocess.run(['explorer', prompts_path], check=False)
            else:  #  OS
                subprocess.run(['open', prompts_path], check=False)
                
            self.log("    ")
            
        except Exception as e:
            self.log(f"    : {e}")

    def open_images_folder(self):
        """  """
        try:
            base_path = get_base_path()
            images_path = os.path.join(base_path, "images")
            
            #   
            if not os.path.exists(images_path):
                os.makedirs(images_path, exist_ok=True)
            
            #   
            if os.name == 'nt':  # Windows
                subprocess.run(['explorer', images_path], check=False)
            else:  #  OS
                subprocess.run(['open', images_path], check=False)
                
            self.log("    ")
        except Exception as e:
            self.log(f"    : {e}")
    
    def show_keyword_warning(self, remaining_count):
        """ 20    """
        try:
            from PyQt6.QtWidgets import QMessageBox
            
            #   
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setWindowTitle("  ")
            msg_box.setText(f"  {remaining_count} !")
            msg_box.setInformativeText(
                "   .\n"
                "  .\n\n"
                "  ."
            )
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)
            
            #      (   )
            def show_message():
                msg_box.exec()
            
            # QTimer    
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, show_message)
            
            self.log(f"    : {remaining_count} ")
            
        except Exception as e:
            self.log(f"   : {e}")
    
    def create_default_prompts(self, prompts_path):
        """   """
        try:
            # prompt1.txt 
            prompt1_content = """ 10  SEO  .   '~'     . 
-    html   . 

{keyword} ,  seo   '' '' .

' '
- {keyword} ,    . (.   , , vs , )
-  :     ,    {keyword}    1 .
-  :    (   ,  ) 
-  :     (, , , vs )   
-  :      . (3, n, n, TOPn, 2025 ) , '2023'  .
-   : ' |  ' . , '{keyword} |  '  ,    .  50~60  .
-'', '', '', '', '', '', '', '', '', '  ', '', '', '', '', '', '', '', ''   ,    .

' '
-  '~' ,            .
-     ,     . ''    .
-      ,   .
-   {keyword}   .
-               .

' '
     :
-  : {naver_search_link}
- : {namu_wiki_link}
- : {play_store_link}
- : {app_store_link}"""
            
            with open(os.path.join(prompts_path, "prompt1.txt"), 'w', encoding='utf-8') as f:
                f.write(prompt1_content)
                
            # prompt2.txt ~ prompt5.txt 
            for i in range(2, 6):
                filename = f"prompt{i}.txt"
                content = self.get_default_prompt(filename)
                with open(os.path.join(prompts_path, filename), 'w', encoding='utf-8') as f:
                    f.write(content)
                
            self.log("      (  )")
        except Exception as e:
            self.log(f"     : {e}")

    def open_font_folder(self):
        """  """
        try:
            font_folder = os.path.join(os.path.dirname(__file__), "fonts")
            if not os.path.exists(font_folder):
                os.makedirs(font_folder)
            os.startfile(font_folder)
            self.log("   ")
        except Exception as e:
            self.log(f"    : {e}")
    
    def open_output_folder(self):
        """  """
        try:
            output_folder = os.path.join(os.path.dirname(__file__), "output")
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)
            os.startfile(output_folder)
            self.log("   ")
        except Exception as e:
            self.log(f"    : {e}")

    def closeEvent(self, event):
        """    -  """
        try:
            #     
            if getattr(self, 'is_posting', False):
                try:
                    if hasattr(self, 'log'):
                        self.log("   .")
                        self.log("    .")
                    #  
                    self.is_posting = False
                    self.is_paused = False
                except:
                    pass
            else:
                #       (  )
                try:
                    if hasattr(self, 'log'):
                        self.log("  .")
                except:
                    pass
                    
                #  
                try:
                    if hasattr(self, 'timer') and self.timer:
                        self.timer.stop()
                except:
                    pass
                    
                #  
                event.accept()
        except Exception as e:
            #    
            event.accept()

    def start_posting(self):
        """ """
        #       
        self.start_btn.setEnabled(False)
        self.start_btn.setActive(True)
        
        #  
        self.reload_resources()
        
        #  
        site_url = self.config_data.get('site_url', '').strip()
        username = self.config_data.get('username', '').strip()
        password = self.config_data.get('password', '').strip()
        gpt_api_key = self.config_data.get('gpt_api_key', '').strip()
        
        #  
        invalid_values = ['', 'nan', 'None', 'https://yoursite.com', 'https://your-site.com', 'your_username', 'your_password', 'your_openai_api_key']
        
        missing_fields = []
        if not site_url or site_url in invalid_values:
            missing_fields.append(" URL")
        if not username or username in invalid_values:
            missing_fields.append("")
        if not password or password in invalid_values:
            missing_fields.append("")
        if not gpt_api_key or gpt_api_key in invalid_values:
            missing_fields.append("GPT API ")
        
        if missing_fields:
            self.log(f" :   : {', '.join(missing_fields)}")
            return
        
        #  
        keywords = self.load_keywords()
        if not keywords:
            self.log(" :   .")
            return
        
        self.remaining_keywords = keywords.copy()
        self.total_keywords = len(keywords)
        self.success_count = 0
        self.fail_count = 0
        self.is_posting = True
        self.is_paused = False
        self.paused_wait_time = 0  # 
        
        # self.log("  !")  # 
        
        #  
        try:
            #     (  )
            self.posting_started = True
            # daemon=True     
            self.posting_thread = threading.Thread(target=self.posting_loop, daemon=True)
            self.posting_thread.start()
            self.log(f"   -  {len(keywords)} ")
        except Exception as e:
            self.log(f"   : {e}")
            self.is_posting = False
            self.start_btn.setEnabled(True)
            self.start_btn.setActive(False)
            return
        
        self.update_button_states()

    def pause_posting(self):
        """ -   """
        if self.is_posting and not self.is_paused:
            self.is_paused = True
            self.pause_start_time = time.time()
            #    
            self.paused_wait_time = max(0, self.wait_time)
            self.log(f"   ( : {self.paused_wait_time//60} {self.paused_wait_time%60})")
            self.update_button_states()

    def resume_posting(self):
        """  -   """
        if self.is_posting and self.is_paused:
            #   
            if hasattr(self, 'resume_btn'):
                self.resume_btn.setEnabled(False)
            
            #  
            self.reload_resources()
            
            self.is_paused = False
            #   
            self.wait_time = self.paused_wait_time
            self.log(f"   ( : {self.wait_time//60} {self.wait_time%60})")
            self.update_button_states()
        elif not self.is_posting:
            #   
            if hasattr(self, 'resume_btn'):
                self.resume_btn.setEnabled(False)
            #      
            self.start_posting()

    def stop_posting(self):
        """ -  """
        self.is_posting = False
        self.is_paused = False
        self.current_keyword = ""
        self.remaining_keywords = []
        self.wait_time = 0
        self.paused_wait_time = 0
        self.success_count = 0
        self.fail_count = 0
        
        #  
        self.reload_resources()
        
        self.log("  ")
        self.update_button_states()

    def parse_wait_interval(self, wait_minutes_str):
        """   (  )"""
        try:
            if '-' in str(wait_minutes_str):
                min_wait, max_wait = map(int, str(wait_minutes_str).split('-'))
                return random.randint(min_wait * 60, max_wait * 60)
            else:
                return int(float(wait_minutes_str)) * 60
        except Exception as e:
            self.log(f"  : {e},  5 ")
            return 300

    def posting_loop(self):
        """ """
        try:
            content_generator = ContentGenerator(self.config_data, self.log)
            # self.log(f" : {len(self.remaining_keywords)}")  # 
            
            while self.is_posting and self.remaining_keywords:
                try:
                    if self.is_paused:
                        time.sleep(1)
                        continue
                    
                    #    ()
                    remaining_count = len(getattr(self, 'remaining_keywords', []))
                    completed_count = getattr(self, 'total_keywords', 0) - remaining_count
                    
                    #    
                    
                    #  20     ( )
                    if remaining_count == 20 and not hasattr(self, 'warned_20_keywords'):
                        self.warned_20_keywords = True
                        self.show_keyword_warning(remaining_count)
                    
                    if not self.remaining_keywords:
                        break
                        
                    keyword = self.remaining_keywords.pop(0)
                    self.current_keyword = keyword
                    self.log(f" : {keyword}")
                    
                    try:
                        #    
                        
                        if self.posting_mode == " ":
                            title, content = content_generator.generate_approval_content(keyword)
                        else:
                            title, content = content_generator.generate_content_with_5_prompts(keyword)
                        
                        if title and content:
                            #  
                            thumbnail_path = content_generator.create_thumbnail(title, keyword)
                            
                            # WordPress 
                            result = content_generator.post_to_wordpress(title, content, thumbnail_path)
                            if result and result.get('success'):
                                content_generator.move_keyword_to_used(keyword)
                                self.success_count += 1
                                
                                #    
                                edit_url = result.get('edit_url', '')
                                self.show_clickable_success(title, edit_url, self.success_count)
                            else:
                                self.fail_count += 1
                                self.log(f"  : {keyword}")
                        else:
                            self.fail_count += 1
                            self.log(f"   : {keyword}")
                        
                        #    (/    )
                        if self.remaining_keywords and self.is_posting:
                            #    (   )
                            if self.wait_time <= 0:
                                wait_minutes = self.config_data.get('wait_minutes', '5-10')
                                self.wait_time = self.parse_wait_interval(wait_minutes)
                            
                            wait_display = f"{self.wait_time//60} {self.wait_time%60}" if self.wait_time >= 60 else f"{self.wait_time}"
                            self.log(f"   : {wait_display} ( : {len(self.remaining_keywords)})")
                            
                            #    (   -  )
                            while self.wait_time > 0 and self.is_posting:
                                try:
                                    #    ( )
                                    if not getattr(self, 'is_posting', False):
                                        self.log(" is_posting False  -   ")
                                        break
                                    
                                    #    (  )
                                    if not hasattr(self, 'wait_time'):
                                        self.log(" wait_time   -   ")
                                        break
                                        
                                    if self.is_paused:
                                        #    
                                        time.sleep(1)
                                        continue
                                    
                                    self.wait_time -= 1
                                    time.sleep(1)
                                    
                                except KeyboardInterrupt:
                                    try:
                                        self.log("   ")
                                    except:
                                        pass
                                    self.is_posting = False
                                    break
                                except Exception as wait_error:
                                    #       
                                    time.sleep(1)
                            
                            #      ()
                            
                    except Exception as keyword_error:
                        #      -      
                        self.log(f"  '{keyword}'   : {keyword_error}")
                        self.log(f"    ...")
                        self.fail_count += 1
                        #       
                        try:
                            content_generator.move_keyword_to_used(keyword)
                        except:
                            pass
                
                except Exception as e:
                    self.log(f"    : {e}")
                    self.log(f"   ...")
                    time.sleep(5)  # 5    
                    continue
            
            #    (   )
            self.log(f"     - remaining_keywords: {len(self.remaining_keywords)}, is_posting: {self.is_posting}")
            
            if not self.remaining_keywords:
                #    
                total_processed = self.success_count + self.fail_count
                self.log("    !")
                self.log(f"  :  {self.success_count},  {self.fail_count},  {total_processed}")
                self.log("    ''      .")
                self.is_posting = False
                try:
                    self.update_button_states()
                except:
                    pass
            elif not self.is_posting:
                #   
                self.log("  .")
                self.log(f"  :  {self.success_count},  {self.fail_count}")
                self.log("   ''  .")
                try:
                    self.update_button_states()
                except:
                    pass
            else:
                #   
                self.log("    .")
                self.log(f"  :  {self.success_count},  {self.fail_count}")
                self.log("   ''  .")
                self.is_posting = False
                try:
                    self.update_button_states()
                except:
                    pass
                
        except KeyboardInterrupt:
            self.log("   .")
            self.log(f"  :  {self.success_count},  {self.fail_count}")
            self.is_posting = False
            try:
                self.update_button_states()
            except:
                pass
                
        except Exception as e:
            self.log(f"    : {e}")
            import traceback
            self.log(f" : {traceback.format_exc()}")
            self.log("   ''   .")
            self.is_posting = False
            try:
                self.update_button_states()
            except:
                pass
        
        finally:
            #      (  )
            if self.is_posting:
                self.is_posting = False
                try:
                    self.update_button_states()
                except:
                    pass
                
            #     
            try:
                self.safe_update_status_display("   -       ")
            except:
                pass
            
            #    ()
            try:
                if hasattr(self, 'start_btn') and self.start_btn:
                    self.start_btn.setEnabled(True)
                    self.start_btn.setActive(False)
                if hasattr(self, 'pause_btn') and self.pause_btn:
                    self.pause_btn.setEnabled(False)
                    self.pause_btn.setActive(False)
            except:
                pass
            
            #    -  
            #  sys.exit()  app.quit()  

def main():
    """ """
    try:
        app = QApplication(sys.argv)
        
        #    -      (   )
        app.setQuitOnLastWindowClosed(False)
        
        #    (GUI   )
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            # GUI     
            print(f"GUI  : {exc_type.__name__}: {exc_value}")
        
        sys.excepthook = handle_exception
        
        #   
        try:
            icon_path = os.path.join(get_base_path(), "daivd153.ico")
            if os.path.exists(icon_path):
                app.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"  : {e}")
        
        #  
        font = QFont("Segoe UI", 10)
        app.setFont(font)
        
        #   
        window = AutoWP()
        
        #  
        window.show()
        
        #     (  )
        window.setFocus()  #    
        
        #   (  )
        try:
            return app.exec()
        except Exception as e:
            print(f"  : {e}")
            return 0
        
    except ImportError as e:
        error_msg = f"""
  : {e}

  :
pip install PyQt6 pandas requests pillow openai

 requirements.txt :
pip install -r requirements.txt
"""
        print(error_msg)
        input(" Enter ...")
        return 1
        
    except KeyboardInterrupt:
        print("\n\n   .")
        print(" .")
        return 0
        
    except Exception as e:
        error_msg = f"""
    :
{e}

  :
1. Python   (3.8  )
2.   
3.   
4.      
"""
        print(error_msg)
        input(" Enter ...")
        return 1

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n .")
    except Exception as e:
        print(f" : {e}")
        print(" .")
