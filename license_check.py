# -*- coding: utf-8 -*-
"""License manager (Google Spreadsheet based)."""

import hashlib
import json
import os
import platform
import socket
import subprocess
import uuid
from datetime import datetime


class LicenseManager:
    """라이선스 관리 클래스"""

    SPREADSHEET_ID = "19X7umIeRL6HLPVPvSmBy6gl2U8sx9MqwX9fTXhuMVB0"
    SHEET_NAME = "시트1"

    def __init__(self):
        self.license_file = os.path.join("setting", "license.json")
        self.license_data = self.load_license()

    def _normalize_text(self, value):
        if value is None:
            return ""
        return str(value).strip().replace("\x00", "").replace("\r", "").replace("\n", "")

    def _run_cmd(self, command):
        """쉘 명령 결과를 안전하게 1줄 문자열로 반환"""
        try:
            result = subprocess.check_output(
                command,
                shell=isinstance(command, str),
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            return self._normalize_text(result)
        except Exception:
            return ""

    def _first_non_empty_line(self, text, excludes=None):
        excludes = excludes or []
        exclude_set = {x.lower() for x in excludes}
        for line in (text or "").split("\n"):
            v = self._normalize_text(line)
            if not v:
                continue
            if v.lower() in exclude_set:
                continue
            return v
        return ""

    def get_local_ip(self):
        """로컬 IP (참고용)"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_mac_address(self):
        """MAC 주소"""
        try:
            mac = ":".join(["{:02x}".format((uuid.getnode() >> elements) & 0xFF) for elements in range(0, 8 * 6, 8)][::-1])
            return mac
        except Exception:
            return "00:00:00:00:00:00"

    def get_windows_machine_id(self):
        """Windows UUID 조회"""
        try:
            if platform.system() == "Windows":
                ps = self._run_cmd(
                    ["powershell", "-Command", "(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID"]
                )
                uuid_str = self._first_non_empty_line(ps, excludes=["uuid"])
                if uuid_str and len(uuid_str) > 10:
                    return uuid_str

                wmic = self._run_cmd("wmic csproduct get uuid")
                uuid_str = self._first_non_empty_line(wmic, excludes=["uuid"])
                if uuid_str and len(uuid_str) > 10:
                    return uuid_str

            return self._normalize_text(str(uuid.getnode()))
        except Exception:
            return self._normalize_text(str(uuid.getnode()))

    def _get_windows_hardware_fingerprint_parts(self):
        """1PC 제한 강화를 위한 하드웨어 식별자 수집"""
        parts = []
        if platform.system() != "Windows":
            return parts

        queries = [
            ("cs_uuid", "(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID"),
            ("bios", "(Get-CimInstance -Class Win32_BIOS).SerialNumber"),
            ("board", "(Get-CimInstance -Class Win32_BaseBoard).SerialNumber"),
            ("cpu", "(Get-CimInstance -Class Win32_Processor | Select-Object -First 1).ProcessorId"),
            ("disk", "(Get-CimInstance -Class Win32_DiskDrive | Select-Object -First 1).SerialNumber"),
        ]
        for label, script in queries:
            raw = self._run_cmd(["powershell", "-Command", script])
            value = self._first_non_empty_line(raw, excludes=["serialnumber", "processorid", "uuid"])
            if value:
                parts.append(f"{label}:{value.lower()}")

        return parts

    def get_machine_id(self):
        """고정 머신 ID 반환 (하드웨어 지문 기반)"""
        mac = self._normalize_text(self.get_mac_address()).lower()
        win_id = self._normalize_text(self.get_windows_machine_id()).lower()
        hw_parts = self._get_windows_hardware_fingerprint_parts()

        # 변동 가능성이 높은 host/os 값은 제외하고 하드웨어 항목만 사용
        fingerprint_parts = [f"uuid:{win_id}", f"mac:{mac}"] + hw_parts
        fingerprint = "|".join([p for p in fingerprint_parts if p and not p.endswith(":")])
        machine_id = hashlib.sha256(fingerprint.encode("utf-8", errors="ignore")).hexdigest()[:32].lower()
        return machine_id

    def load_license(self):
        """라이선스 파일 로드"""
        try:
            if os.path.exists(self.license_file):
                with open(self.license_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception:
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
                "local_ip": self.get_local_ip(),
                "registered_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active",
            }
            with open(self.license_file, "w", encoding="utf-8") as f:
                json.dump(license_data, f, ensure_ascii=False, indent=4)
            self.license_data = license_data
            return True
        except Exception as e:
            print(f"라이선스 저장 오류: {e}")
            return False

    def fetch_buyers_from_sheet(self):
        """Google Spreadsheet에서 구매자 정보 조회"""
        try:
            url = f"https://docs.google.com/spreadsheets/d/{self.SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={self.SHEET_NAME}"
            import requests

            response = requests.get(url, timeout=10)
            response.encoding = "utf-8"
            if response.status_code != 200:
                print(f"스프레드시트 접근 실패: {response.status_code}")
                return {}

            lines = response.text.strip().split("\n")
            buyers = {}
            for line in lines[1:]:
                try:
                    parts = line.replace('"', "").split(",")
                    if len(parts) < 4:
                        continue
                    name = parts[0].strip()
                    email = parts[1].strip()
                    machine_id = parts[2].strip().lower()
                    expire_date = parts[3].strip()
                    if machine_id and name:
                        buyers[machine_id] = {
                            "name": name,
                            "email": email,
                            "machine_id": machine_id,
                            "expire_date": expire_date,
                        }
                except Exception:
                    continue
            return buyers
        except Exception as e:
            print(f"스프레드시트 로드 오류: {e}")
            return {}

    def check_machine_in_spreadsheet(self, current_machine_id):
        """스프레드시트 등록 여부 확인"""
        buyers = self.fetch_buyers_from_sheet()
        if not buyers:
            return False, "구매자 정보를 불러오지 못했습니다. 네트워크 연결을 확인하세요."

        current_machine_id = (current_machine_id or "").strip().lower()
        if current_machine_id in buyers:
            buyer_info = buyers[current_machine_id]
            expire_date = buyer_info.get("expire_date", "")
            try:
                if expire_date:
                    expire_dt = datetime.strptime(expire_date, "%Y-%m-%d")
                    if datetime.now() > expire_dt:
                        return False, f"라이선스가 만료되었습니다. 구매자: {buyer_info['name']} / 만료일: {expire_date}"
            except Exception:
                pass
            return True, f"인증 성공 / 구매자: {buyer_info['name']} / 머신 ID: {current_machine_id[:16]}..."

        return False, f"등록되지 않은 컴퓨터입니다. 현재 머신 ID: {current_machine_id}"

    def verify_license(self):
        """라이선스 검증"""
        current_machine_id = self.get_machine_id()
        is_valid, message = self.check_machine_in_spreadsheet(current_machine_id)
        if not is_valid:
            return False, message

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
                "local_ip": self.get_local_ip(),
                "expire_date": buyer.get("expire_date", "N/A"),
            }

        return {
            "status": "미등록",
            "name": "N/A",
            "email": "N/A",
            "machine_id": current_machine_id,
            "mac_address": self.get_mac_address(),
            "local_ip": self.get_local_ip(),
            "expire_date": "N/A",
        }
