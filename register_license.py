# -*- coding: utf-8 -*-
"""
라이선스 등록 도구
관리자용
"""

import sys
from license_check import LicenseManager

def main():
    print("=" * 50)
    print("네이버 블로그 자동화 - 라이선스 등록 도구")
    print("=" * 50)
    
    manager = LicenseManager()
    current_ip = manager.get_local_ip()
    
    print(f"\n현재 IP 주소: {current_ip}")
    print(f"머신 ID: {manager.get_machine_id()}")
    
    # 기존 라이선스 확인
    if manager.license_data:
        print("\n[기존 라이선스 정보]")
        info = manager.get_license_info()
        print(f"상태: {info['status']}")
        print(f"등록 IP: {info['ip']}")
        print(f"등록일: {info['registered_date']}")
        
        choice = input("\n기존 라이선스를 덮어쓰시겠습니까? (y/n): ")
        if choice.lower() != 'y':
            print("취소되었습니다.")
            return
    
    # 라이선스 키 입력
    print("\n[새 라이선스 등록]")
    license_key = input("라이선스 키를 입력하세요: ").strip()
    
    if not license_key:
        print("라이선스 키가 입력되지 않았습니다.")
        return
    
    # IP 주소 확인
    print(f"\n다음 IP로 등록됩니다: {current_ip}")
    confirm = input("계속하시겠습니까? (y/n): ")
    
    if confirm.lower() != 'y':
        print("취소되었습니다.")
        return
    
    # 라이선스 등록
    if manager.save_license(license_key, current_ip):
        print("\n✅ 라이선스가 성공적으로 등록되었습니다!")
        print(f"등록 IP: {current_ip}")
        print(f"머신 ID: {manager.get_machine_id()}")
    else:
        print("\n❌ 라이선스 등록에 실패했습니다.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")
    
    input("\n\nEnter 키를 눌러 종료...")
