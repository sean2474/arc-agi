# Document Schemas

에이전트 간 문서는 고정된 스키마를 따라야 한다. 자유 마크다운 금지.
필수 섹션이 없으면 저장 스크립트가 reject한다.

## Strategy Document (Planner → Generator)

저장 경로: `docs/strategy/current.md`
저장 방법: `python scripts/save_strategy.py --data '<json>'`

필수 섹션:

```markdown
## Goal
(이 스프린트에서 달성할 구체적 목표. 1-2문장)

## Hypothesis
(왜 이 접근이 작동할 것이라 생각하는지)

## Approach
(구체적 단계들, 번호 리스트)

## Constraints
(하지 말아야 할 것, 건드리지 말아야 할 코드)

## Success Criteria
(Generator와 Evaluator가 공유하는 완료 기준. 체크리스트)
```

## Evaluation Report (Evaluator → Planner/사용자)

저장 경로: `docs/evaluations/{timestamp}.json`
저장 방법: `python scripts/save_evaluation.py --data '<json>'`

필수 필드:

```json
{
  "timestamp": "ISO 8601",
  "code_review": {
    "tests_passed": "bool",
    "solid_violations": ["string"],
    "architecture_issues": ["string"],
    "structure_sync": "bool (structure.md와 코드 일치 여부)"
  },
  "game_results": {
    "game_id": "string",
    "levels_completed": "int",
    "total_steps": "int",
    "score": "float",
    "state": "GameState string"
  },
  "failure_classification": "perception_error|planning_error|execution_error|environment_error|null",
  "failure_detail": "string or null",
  "recommendations": ["string"],
  "comparison": {
    "previous_experiment": "string or null",
    "score_delta": "float or null",
    "improved": "bool or null"
  }
}
```

## Game Analysis (게임별 지식)

저장 경로: `docs/games/{game_id}/analysis.md`

필수 섹션:

```markdown
## Objects
(발견한 오브젝트 목록, 색상, 크기, 위치 패턴)

## Rules
(파악한 게임 규칙들)

## Action Effects
(각 ACTION이 무엇을 하는지)

## Level Progression
(레벨별 변화 패턴)

## Open Questions
(아직 모르는 것들)
```

## Code Structure Registry

경로: `docs/structure.md`

포맷:

```markdown
## src/{module_name}/
- `filename.py` — 모듈 설명
  - `ClassName` — 클래스 설명
  - `function_name(params) -> return` — 함수 설명
```

Generator가 새 모듈/함수 작성 시 반드시 여기에 등록.
Evaluator가 실제 코드와 일치 여부를 검증.
