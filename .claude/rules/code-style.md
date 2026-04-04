# Code Style

## Python
- Python 3.14
- 타입 힌트 필수 (모든 함수 파라미터 + 리턴 타입)
- dataclass 또는 pydantic BaseModel로 데이터 구조 정의
- numpy ndarray는 `npt.NDArray[np.int_]` 등 타입 주석

## Formatting
- ruff로 린팅
- 4-space indentation (PEP 8)

## Imports
- stdlib → third-party → local 순서
- 순환 import 금지
- 미사용 import 금지

## Naming
- 클래스: PascalCase
- 함수/변수: snake_case
- 상수: UPPER_SNAKE_CASE
- private: _prefix
