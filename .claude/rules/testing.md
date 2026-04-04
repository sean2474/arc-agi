# Testing Rules

## Framework
- pytest 사용
- tests/ 디렉토리에 src/ 미러 구조

## Requirements
- src/에 새 모듈 추가 시 tests/에 대응 테스트 파일 필수
- 결정론적 로직 (픽셀 분석, 좌표 계산, diff) → deterministic test (고정 입출력)
- 엣지 케이스 포함: 빈 프레임, 전체 같은 색, 경계 좌표 등

## Naming
- 테스트 파일: `tests/test_{module_name}.py`
- 테스트 함수: `test_{기능}_{조건}_{기대결과}` 또는 간결하게 `test_{기능}`

## Running
```bash
pytest tests/                  # 전체 테스트
pytest tests/test_specific.py  # 특정 파일
pytest -x                      # 첫 실패에서 멈춤
```
