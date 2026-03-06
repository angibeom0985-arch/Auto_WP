# -*- coding: utf-8 -*-
"""License manager (Google Spreadsheet based)."""

import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import uuid
from datetime import datetime


def get_base_path():
    """실행 파일의 기본 경로 반환 (EXE/PY 모두 지원)"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_windows_hidden_subprocess_kwargs():
    """Windows에서 subprocess 실행 시 콘솔창 숨김 옵션 반환"""
    if os.name != "nt":
        return {}
    kwargs = {}
    try:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    except Exception:
        pass
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


class LicenseManager:
    """라이선스 관리 클래스"""

    SPREADSHEET_ID = "19X7umIeRL6HLPVPvSmBy6gl2U8sx9MqwX9fTXhuMVB0"
    SHEET_NAME = "시트1"
    MACHINE_ID_PREFIX = "WP-"

    def __init__(self):
        setting_root = os.path.join(get_base_path(), "setting")
        self.legacy_license_file = os.path.join(setting_root, "license.json")
        self.license_file = os.path.join(setting_root, "etc", "license.json")
        self._purge_local_license_files()
        self.license_data = {}

    def _purge_local_license_files(self):
        """로컬 라이선스 파일을 남기지 않도록 정리"""
        for path in (self.legacy_license_file, self.license_file):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    def _normalize_text(self, value):
        if value is None:
            return ""
        return str(value).strip().replace("\x00", "").replace("\r", "").replace("\n", "")

    def _run_cmd(self, command):
        """쉘 명령 결과를 안전하게 1줄 문자열로 반환"""
        try:
            if isinstance(command, list) and command:
                exe = str(command[0]).lower()
                if exe in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
                    # 사용자 프로필/대화형 프롬프트 영향 제거
                    command = [command[0], "-NoProfile", "-NonInteractive"] + command[1:]
            result = subprocess.check_output(
                command,
                shell=isinstance(command, str),
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=8,
                **_get_windows_hidden_subprocess_kwargs(),
            )
            return self._normalize_text(result)
        except (subprocess.TimeoutExpired, Exception):
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

    def _canonical_machine_id(self, machine_id):
        """머신 ID를 비교용 코어값으로 정규화 (WP 접두어 유무 모두 허용)"""
        mid = self._normalize_text(machine_id).lower()
        # 신규 포맷: WP-xxxxxxxx...
        if mid.startswith("wp-"):
            mid = mid[3:]
        # 구포맷 호환: WPxxxxxxxx...
        elif mid.startswith("wp"):
            mid = mid[2:]
        return mid.strip()

    def _format_machine_id(self, machine_id_core):
        """표시/저장용 머신 ID 포맷"""
        core = self._canonical_machine_id(machine_id_core)
        if not core:
            return ""
        return f"{self.MACHINE_ID_PREFIX}{core}"

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
        return self._format_machine_id(machine_id)

    def load_license(self):
        """로컬 라이선스 파일 미사용"""
        return {}

    def save_license(self, license_key, machine_id):
        """로컬 라이선스 파일 미사용"""
        return True

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
                    machine_id_raw = parts[2].strip()
                    machine_id_core = self._canonical_machine_id(machine_id_raw)
                    machine_id = self._format_machine_id(machine_id_core)
                    expire_date = parts[3].strip()
                    if machine_id_core and name:
                        buyer_entry = {
                            "name": name,
                            "email": email,
                            "machine_id": machine_id,
                            "expire_date": expire_date,
                        }
                        # 신규 포맷(WP...)과 기존 포맷(무접두어) 모두 인식
                        buyers[machine_id] = buyer_entry
                        buyers[machine_id_core] = buyer_entry
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

        current_core = self._canonical_machine_id(current_machine_id)
        current_prefixed = self._format_machine_id(current_core)
        lookup_keys = [current_prefixed, current_core]
        matched_key = next((k for k in lookup_keys if k in buyers), None)
        if matched_key:
            buyer_info = buyers[matched_key]
            expire_date = buyer_info.get("expire_date", "")
            try:
                if expire_date:
                    expire_dt = datetime.strptime(expire_date, "%Y-%m-%d")
                    if datetime.now() > expire_dt:
                        return False, f"라이선스가 만료되었습니다. 구매자: {buyer_info['name']} / 만료일: {expire_date}"
            except Exception:
                pass
            return True, f"인증 성공 / 구매자: {buyer_info['name']} / 머신 ID: {current_prefixed[:16]}..."

        return False, f"등록되지 않은 컴퓨터입니다. 현재 머신 ID: {current_prefixed}"

    def verify_license(self):
        """라이선스 검증"""
        current_machine_id = self.get_machine_id()
        is_valid, message = self.check_machine_in_spreadsheet(current_machine_id)
        if not is_valid:
            return False, message

        return True, message

    def get_license_info(self):
        """라이선스 정보 반환"""
        current_machine_id = self.get_machine_id()
        buyers = self.fetch_buyers_from_sheet()

        current_core = self._canonical_machine_id(current_machine_id)
        lookup_keys = [current_machine_id, current_core]
        matched_key = next((k for k in lookup_keys if k in buyers), None)
        if matched_key:
            buyer = buyers[matched_key]
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
