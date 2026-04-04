---
name: build
description: Generator 에이전트를 호출하여 현재 전략에 따라 코드를 구현한다
argument-hint: "[description]"
---

# Build: 코드 구현

Generator 에이전트를 호출하여 현재 전략에 따라 코드를 구현한다.

## Current Strategy

!`cat docs/strategy/current.md 2>/dev/null || echo "ERROR: 전략이 없습니다. 먼저 /plan을 실행하세요."`

## Current Structure

!`cat docs/structure.md 2>/dev/null || echo "(structure.md 비어있음)"`

## Task

1. 위의 전략 문서(Goal, Approach, Constraints, Success Criteria)를 따른다
2. docs/structure.md에서 기존 모듈을 확인하고 재사용한다
3. src/에 코드를 구현한다
4. tests/에 테스트를 작성한다
5. `pytest tests/`를 실행하여 통과를 확인한다
6. docs/structure.md를 새로 만든 모듈/함수로 업데이트한다
7. `python scripts/validate.py`로 코드 품질을 검증한다

추가 지시: $ARGUMENTS
