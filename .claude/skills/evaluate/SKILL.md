---
name: evaluate
description: Evaluator 에이전트를 호출하여 코드 품질과 게임 결과를 평가한다
argument-hint: "[game_id]"
---

# Evaluate: 독립 평가

Evaluator 에이전트를 호출하여 코드 품질 + 게임 결과를 평가한다.

## Current Strategy

!`cat docs/strategy/current.md 2>/dev/null || echo "(전략 없음)"`

## Test Results

!`cd /Users/sean2474/Desktop/project/arc-agi-3 && pytest tests/ --tb=short 2>&1 | tail -20 || echo "(테스트 없음)"`

## Task

### 코드 평가
1. src/ 코드를 읽고 SOLID 원칙 준수 여부를 판단한다
2. `pytest tests/`를 실행하여 테스트 통과 여부를 확인한다
3. `python scripts/validate_structure.py`로 structure.md 일치를 확인한다
4. 현재 전략의 Success Criteria 충족 여부를 판단한다

### 게임 평가 (game_id가 주어진 경우)
5. 게임을 실행하여 결과를 확인한다
6. 실패 시 failure_classification을 반드시 분류한다

### 결과 저장
7. `python scripts/save_evaluation.py --data '<json>'`으로 평가 결과를 저장한다

**관대하게 통과시키지 않는다. 문제가 있으면 반드시 기록한다.**

대상 게임: $ARGUMENTS
