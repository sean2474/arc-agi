---
name: plan
description: Planner 에이전트를 호출하여 게임 전략을 수립한다
argument-hint: "[game_id]"
---

# Plan: 전략 수립

Planner 에이전트를 호출하여 게임 전략을 수립한다.

## Context

현재 전략:
!`cat docs/strategy/current.md 2>/dev/null || echo "(전략 없음)"`

최신 평가:
!`ls -t docs/evaluations/*.json 2>/dev/null | head -1 | xargs cat 2>/dev/null || echo "(평가 없음)"`

## Task

1. 위의 컨텍스트 (이전 전략, 최신 평가 결과)를 분석한다
2. $ARGUMENTS 게임에 대한 분석이 있으면 `docs/games/$ARGUMENTS/analysis.md`를 읽는다
3. Planner 에이전트의 규칙에 따라 전략을 수립한다
4. `python scripts/save_strategy.py --data '<json>'`으로 저장한다

전략은 반드시 Goal, Hypothesis, Approach, Constraints, Success Criteria를 포함해야 한다.
이전 평가에 failure_classification이 있으면 해당 실패 유형에 맞는 대응을 반영한다.
