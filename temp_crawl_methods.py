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
                        
                        # URL에서 post 번호 추출하여 정확한 URL 생성
                        if "/PostView.naver" in post_url or "logNo=" in post_url:
                            # 이미 정확한 URL
                            final_url = post_url
                        else:
                            final_url = post_url
                        
                        posts.append({
                            'title': post_title,
                            'url': final_url,
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
    
