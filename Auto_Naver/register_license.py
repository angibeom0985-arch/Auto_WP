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
    current_machine_id = manager.get_machine_id()
    current_mac = manager.get_mac_address()
    current_ip = manager.get_local_ip()
    
    print(f"\n[현재 컴퓨터 정보]")
    print(f"머신 ID: {current_machine_id}")
    print(f"MAC 주소: {current_mac}")
    print(f"로컬 IP: {current_ip} (참고용)")
    
    # 기존 라이선스 확인
    if manager.license_data:
        print("\n[기존 라이선스 정보]")
        print(f"등록일: {manager.license_data.get('registered_date', 'N/A')}")
        print(f"머신 ID: {manager.license_data.get('registered_machine_id', 'N/A')}")
        
        choice = input("\n기존 라이선스를 덮어쓰시겠습니까? (y/n): ")
        if choice.lower() != 'y':
            print("취소되었습니다.")
            return
    
    # 라이선스 키 입력
    print("\n[새 라이선스 등록]")
    print("※ 이제 IP 주소가 아닌 머신 ID로 등록됩니다.")
    print("※ 와이파이 변경, 재부팅 시에도 라이선스가 유지됩니다.")
    license_key = input("\n라이선스 키를 입력하세요: ").strip()
    
    if not license_key:
        print("라이선스 키가 입력되지 않았습니다.")
        return
    
    # 머신 ID 확인
    print(f"\n다음 머신 ID로 등록됩니다:")
    print(f"머신 ID: {current_machine_id}")
    print(f"MAC 주소: {current_mac}")
    confirm = input("\n계속하시겠습니까? (y/n): ")
    
    if confirm.lower() != 'y':
        print("취소되었습니다.")
        return
    
    # 라이선스 등록
    if manager.save_license(license_key, current_machine_id):
        print("\n✅ 라이선스가 성공적으로 등록되었습니다!")
        print(f"머신 ID: {current_machine_id}")
        print(f"MAC 주소: {current_mac}")
        print("\n※ 스프레드시트에 위 머신 ID를 등록해주세요.")
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
