# -*- coding: utf-8 -*-
"""
라이선스 및 IP 제한 모듈 (Google Spreadsheet 연동)
"""

import socket
import hashlib
import json
import os
from datetime import datetime
# import requests  <-- removed top-level import
import uuid
import subprocess
import platform

class LicenseManager:
    """라이선스 관리 클래스 - Google Spreadsheet 연동"""
    
    # Google Spreadsheet ID
    SPREADSHEET_ID = "1fce6TBReHs9fMuUtI7ovSkNPnbHtawMUY-IfyIOhGC4"
    SHEET_NAME = "시트1"
    
    def __init__(self):
        self.license_file = os.path.join("setting", "license.json")
        self.license_data = self.load_license()
    
    def get_local_ip(self):
        """로컬 IP 주소 가져오기 (참고용)"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def get_mac_address(self):
        """MAC 주소 가져오기 (하드웨어 고유값)"""
        try:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                           for elements in range(0,8*6,8)][::-1])
            return mac
        except:
            return "00:00:00:00:00:00"
    
    def get_windows_machine_id(self):
        """Windows 머신 고유 ID 가져오기"""
        try:
            if platform.system() == "Windows":
                # PowerShell 명령어로 UUID 가져오기 (Windows 11 호환)
                try:
                    result = subprocess.check_output(
                        ['powershell', '-Command', '(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID'],
                        shell=False,
                        stderr=subprocess.DEVNULL
                    )
                    uuid_str = result.decode().strip()
                    if uuid_str and len(uuid_str) > 10:
                        return uuid_str
                except:
                    pass
                
                # 폴백: wmic 시도 (구버전 Windows)
                try:
                    result = subprocess.check_output('wmic csproduct get uuid', shell=True, stderr=subprocess.DEVNULL)
                    uuid_str = result.decode().split('\n')[1].strip()
                    if uuid_str and len(uuid_str) > 10:
                        return uuid_str
                except:
                    pass
            
            # 모든 방법 실패 시 uuid.getnode() 사용
            return str(uuid.getnode())
        except:
            return str(uuid.getnode())
    
    def get_machine_id(self):
        """머신 고유 ID 생성 (MAC + Windows UUID 조합)"""
        mac = self.get_mac_address()
        win_id = self.get_windows_machine_id()
        combined = f"{mac}_{win_id}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]
    
    def load_license(self):
        """라이선스 파일 로드"""
        try:
            if os.path.exists(self.license_file):
                with open(self.license_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except:
            return {}
    
    def save_license(self, license_key, machine_id):
        """라이선스 정보 저장"""
        try:
            os.makedirs("setting", exist_ok=True)
            
            license_data = {
                "license_key": license_key,
                "registered_machine_id": machine_id,
                "mac_address": self.get_mac_address(),
                "windows_id": self.get_windows_machine_id(),
                "local_ip": self.get_local_ip(),  # 참고용
                "registered_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }
            
            with open(self.license_file, 'w', encoding='utf-8') as f:
                json.dump(license_data, f, ensure_ascii=False, indent=4)
            
            self.license_data = license_data
            return True
        except Exception as e:
            print(f"라이선스 저장 오류: {e}")
            return False
    
    def fetch_buyers_from_sheet(self):
        """Google Spreadsheet에서 구매자 정보 가져오기"""
        try:
            # Google Sheets를 CSV로 export하는 URL
            url = f"https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={self.SHEET_NAME}"
            
            import requests  # Lazy load
            response = requests.get(url, timeout=10)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                # CSV 파싱
                lines = response.text.strip().split('\n')
                buyers = {}
                
                # 첫 줄은 헤더이므로 건너뛰기
                for line in lines[1:]:
                    try:
                        # CSV 파싱 (간단한 방식)
                        parts = line.replace('"', '').split(',')
                        if len(parts) >= 4:
                            name = parts[0].strip()  # 이름
                            email = parts[1].strip()  # 이메일
                            machine_id = parts[2].strip()  # 머신 ID (이전에는 IP였음)
                            date = parts[3].strip()  # 만료일
                            
                            if machine_id and name:  # 머신 ID와 이름이 있는 경우만
                                buyers[machine_id] = {
                                    "name": name,
                                    "email": email,
                                    "machine_id": machine_id,
                                    "expire_date": date
                                }
                    except:
                        continue
                
                return buyers
            else:
                print(f"스프레드시트 접근 실패: {response.status_code}")
                return {}
        except Exception as e:
            print(f"스프레드시트 로드 오류: {e}")
            return {}
    
    def check_machine_in_spreadsheet(self, current_machine_id):
        """스프레드시트에서 현재 머신 ID 확인"""
        buyers = self.fetch_buyers_from_sheet()
        
        if not buyers:
            return False, "구매자 정보를 불러올 수 없습니다. 인터넷 연결을 확인하세요."
        
        if current_machine_id in buyers:
            buyer_info = buyers[current_machine_id]
            expire_date = buyer_info.get("expire_date", "")
            
            # 만료일 체크
            try:
                if expire_date and expire_date != "":
                    expire_dt = datetime.strptime(expire_date, "%Y-%m-%d")
                    if datetime.now() > expire_dt:
                        return False, f"라이선스가 만료되었습니다.\n구매자: {buyer_info['name']}\n만료일: {expire_date}"
            except:
                pass  # 날짜 파싱 실패 시 무시
            
            return True, f"인증 성공\n구매자: {buyer_info['name']}\n머신 ID: {current_machine_id[:16]}..."
        
        return False, f"등록되지 않은 컴퓨터입니다.\n현재 머신 ID: {current_machine_id}\n\n구매 후 머신 ID를 등록해주세요."
    
    def verify_license(self):
        """라이선스 검증 - Google Spreadsheet 기반"""
        current_machine_id = self.get_machine_id()
        
        # Google Spreadsheet에서 머신 ID 확인
        is_valid, message = self.check_machine_in_spreadsheet(current_machine_id)
        
        if not is_valid:
            return False, message
        
        # 로컬 라이선스 파일 업데이트
        if not self.license_data or self.license_data.get("registered_machine_id") != current_machine_id:
            self.save_license("SPREADSHEET_VERIFIED", current_machine_id)
        
        return True, message
    
    def get_license_info(self):
        """라이선스 정보 반환"""
        current_machine_id = self.get_machine_id()
        buyers = self.fetch_buyers_from_sheet()
        
        if current_machine_id in buyers:
            buyer = buyers[current_machine_id]
            return {
                "status": "등록됨",
                "name": buyer.get("name", "N/A"),
                "email": buyer.get("email", "N/A"),
                "machine_id": current_machine_id,
                "mac_address": self.get_mac_address(),
                "local_ip": self.get_local_ip(),  # 참고용
                "expire_date": buyer.get("expire_date", "N/A")
            }
        
        return {
            "status": "미등록",
            "name": "N/A",
            "email": "N/A",
            "machine_id": current_machine_id,
            "mac_address": self.get_mac_address(),
            "local_ip": self.get_local_ip(),  # 참고용
            "expire_date": "N/A"
        }
