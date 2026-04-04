# Failure Taxonomy

게임 실패 시 Evaluator가 반드시 아래 분류 중 하나를 붙여야 한다.
다음 Planner는 이 분류를 보고 전략을 수정한다.

## Categories

### perception_error
- 오브젝트 인식 실패 (프레임 분석이 틀림)
- 예: 오브젝트를 못 찾음, 색상/크기 오인식, 배경과 오브젝트 구분 실패
- **대응**: 프레임 분석 로직 수정, 오브젝트 추출 알고리즘 개선

### planning_error
- Goal hypothesis 자체가 틀림
- 예: 게임 규칙을 잘못 파악, 승리 조건 오해, 잘못된 전략 선택
- **대응**: 가설 재수립, 더 많은 탐색적 실험, 게임 분석 보강

### execution_error
- Goal은 맞는데 action이 헛돔
- 예: 좌표 계산 오류, 액션 시퀀스 오류, 타이밍 실수
- **대응**: 액션 선택 로직 수정, 좌표 변환 검증

### environment_error
- 환경/API 버그 또는 예상치 못한 동작
- 예: API 응답 이상, 프레임 데이터 누락, 알 수 없는 게임 상태
- **대응**: 에러 핸들링 추가, 환경 조건 확인

## Usage

Evaluator는 `failure_classification` 필드에 위 4개 중 하나를 반드시 기록.
게임을 클리어한 경우 `null`.
`failure_detail`에 구체적인 실패 원인 설명을 포함.
