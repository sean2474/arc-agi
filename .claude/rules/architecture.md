# Architecture Rules

## 3-Agent Pattern

### Planner
- **역할**: 게임 상태 분석, 전략 수립
- **경계**: 코드 수정 불가. 전략만 출력.
- **입력**: 게임 프레임 분석 결과, 이전 평가 JSON, 게임별 분석, 실패 분류
- **출력**: docs/strategy/current.md (고정 스키마)

### Generator
- **역할**: Planner 전략에 따른 코드 구현
- **경계**: 전략 자체를 변경 불가. 전략 문서의 Approach를 따라 구현.
- **입력**: docs/strategy/current.md, docs/structure.md
- **출력**: src/ 코드, tests/ 테스트, docs/structure.md 업데이트

### Evaluator
- **역할**: 코드 품질 + 게임 결과 독립 평가
- **경계**: 코드 수정 불가. 평가 결과만 출력.
- **입력**: src/ 코드, 테스트 결과, 게임 실행 결과
- **출력**: docs/evaluations/{timestamp}.json (고정 스키마)

## Data Flow

```
Planner ──(strategy/current.md)──→ Generator ──(src/ code)──→ Evaluator
   ↑                                                              │
   └──────────────(evaluations/*.json + failure classification)───┘
```

## Rules

- Planner가 만든 전략의 Success Criteria는 Evaluator의 평가 기준이 된다
- Generator는 코드 작성 전 docs/structure.md를 읽고 기존 모듈을 확인한다
- Evaluator는 관대하게 통과시키지 않는다. 문제를 발견하면 반드시 지적한다.
- 실패 시 Evaluator가 failure_classification을 붙이고, Planner가 이를 참고해 전략을 수정한다
