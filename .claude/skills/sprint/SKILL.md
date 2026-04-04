---
name: sprint
description: Plan → 사용자 확인 → Build → Evaluate 전체 사이클을 실행한다
argument-hint: "[game_id] [sprint_description]"
---

# Sprint: Plan → Confirm → Build → Evaluate

전체 개발 사이클을 실행한다.

## 워크플로우

### Step 1: Plan
Planner로서 전략을 수립한다.
- docs/games/, docs/evaluations/, docs/strategy/history/ 를 참고
- 전략을 수립하고 `scripts/save_strategy.py`로 저장

### Step 2: 사용자 확인
수립한 전략을 사용자에게 보여주고 승인을 요청한다.
- Goal, Hypothesis, Approach, Success Criteria를 명확히 제시
- 사용자가 수정을 요청하면 반영 후 다시 저장
- **사용자 승인 없이 다음 단계로 넘어가지 않는다**

### Step 3: Build
Generator로서 승인된 전략에 따라 코드를 구현한다.
- docs/structure.md에서 기존 코드 확인
- src/ 구현, tests/ 테스트, structure.md 업데이트
- pytest 통과 확인

### Step 4: Evaluate
Evaluator로서 결과를 평가한다.
- 코드 품질 체크 (SOLID, 아키텍처, structure 일치)
- 게임 실행 결과 분석 (game_id가 있는 경우)
- 실패 분류 + 개선 제안
- `scripts/save_evaluation.py`로 결과 저장

대상: $ARGUMENTS
