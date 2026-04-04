# ARC-AGI-3 Game Agent

## Project Overview

ARC-AGI-3 interactive reasoning benchmark를 풀기 위한 AI 게임 에이전트.
게임은 턴 기반: 64x64 프레임 수신 → 액션 선택 → 다음 프레임 수신.

- **Python 3.14**, arc_agi 0.9.6, arcengine 0.9.3
- 로컬 오프라인 개발 우선 (OperationMode.OFFLINE)

## API Quick Reference

```python
from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState

arc = Arcade(operation_mode=OperationMode.OFFLINE)
env = arc.make("game_id", seed=0)
obs = env.reset()          # → FrameDataRaw
obs = env.step(action, data={}, reasoning={})  # → FrameDataRaw

# obs.frame      → List[ndarray] (64x64, values 0-15)
# obs.state      → GameState (NOT_PLAYED|NOT_FINISHED|WIN|GAME_OVER)
# obs.available_actions → list[int] (action IDs)
# env.action_space → list[GameAction]
```

## Architecture: Planner → Generator → Evaluator

이 프로젝트는 3-에이전트 패턴을 사용한다:

| Agent | 역할 | 출력 |
|-------|------|------|
| **Planner** | 게임 분석, 전략 수립 | docs/strategy/current.md |
| **Generator** | 전략에 따라 코드 구현 | src/ 코드 + tests/ |
| **Evaluator** | 코드 품질 + 게임 결과 평가 | docs/evaluations/*.json |

에이전트 간 문서는 **고정된 스키마**를 따른다. 자세한 포맷은 `.claude/rules/document-schemas.md` 참조.

## Code Rules

- **타입 힌트 필수**: 모든 함수 파라미터와 리턴 타입
- **테스트 필수**: src/의 모든 모듈은 tests/에 대응 테스트
- **새 라이브러리 도입 금지**: 기존 의존성만 사용 (arc-agi, arcengine, numpy, pytest, ruff)
- **SOLID 원칙 준수**: Evaluator가 리뷰 시 체크
- **코드 재사용**: 새 코드 작성 전 docs/structure.md에서 기존 모듈 검색

## Directory Structure

```
src/           → 소스 코드 (Generator가 작성)
tests/         → 테스트
docs/          → 지식 축적
  structure.md → 코드 구조 레지스트리 (모듈/함수 목록)
  games/       → 게임별 분석 (오브젝트, 규칙, 패턴)
  strategy/    → 전략 문서 (current.md + history/)
  evaluations/ → 평가 보고서 (JSON)
experiments/   → 실험 추적 ({timestamp}_{name}/)
scripts/       → 유틸리티 (검증, 분석, 저장 스크립트)
```

## Commands

```bash
pytest tests/                          # 테스트 실행
python scripts/validate.py             # 코드 품질 검증
python scripts/validate_structure.py   # structure.md ↔ 코드 일치 검증
python scripts/validate_docs.py        # 문서 스키마 검증
```

## Workflow

`/sprint` = `/plan` → 사용자 확인 → `/build` → `/evaluate`

See `.claude/rules/` for detailed rules on each topic.
