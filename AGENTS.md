# Agent Instructions / 에이전트 지침

## 🛡️ Protected: Machine ID / License Logic
## 🛡️ 보호됨: 머신 ID / 라이선스 로직

**English**
- Do not modify any Machine ID or license enforcement logic without explicit user consent.
- This includes file changes, refactors, data-path changes, or edits that affect how machine IDs are generated, stored, verified, or displayed.
- If a task would touch this area, stop and ask for confirmation first, even if you have broad permissions.

**Korean (한국어)**
- 사용자의 명시적인 동의 없이 머신 ID(기기 고유값) 또는 라이선스 강제 로직을 절대 수정하지 마십시오.
- 여기에는 파일 변경, 리팩토링, 데이터 경로 변경, 또는 머신 ID가 생성, 저장, 검증, 표시되는 방식에 영향을 주는 모든 편집이 포함됩니다.
- 만약 작업이 이 영역을 건드려야 한다면, 광범위한 권한이 있더라도 작업을 멈추고 먼저 확인을 요청하십시오.

### 🚫 Protected paths (non-exhaustive) / 보호된 경로 (예시)
- `Auto_WP/license_check.py`
- `Auto_WP/register_license.py`
- `Auto_WP/Auto_WP_V8.13.py` (any Machine ID related UI/logic / 머신 ID 관련 UI 또는 로직)
- `Auto_WP/setting` (license or machine-id related data / 라이선스나 머신 ID 관련 데이터)
- Any file containing "machine_id", "머신 ID", or "머신ID"
- "machine_id", "머신 ID", "머신ID"가 포함된 모든 파일
