# ARC-AGI-3 API Reference

## Core Classes

### Arcade
```python
from arc_agi import Arcade, OperationMode

arc = Arcade(operation_mode=OperationMode.OFFLINE)  # 로컬 개발
arc = Arcade(operation_mode=OperationMode.ONLINE)   # 스코어카드/리플레이
arc = Arcade(operation_mode=OperationMode.COMPETITION)  # 대회 모드
```

### EnvironmentWrapper
```python
env = arc.make("game_id", seed=0, render_mode="terminal")
obs = env.reset()                              # → FrameDataRaw | None
obs = env.step(action, data={}, reasoning={})  # → FrameDataRaw | None
actions = env.action_space                     # → list[GameAction]
obs = env.observation_space                    # → FrameDataRaw | None
info = env.info                                # → EnvironmentInfo
```

### FrameDataRaw
| Field | Type | Description |
|-------|------|-------------|
| game_id | str | 게임 식별자 |
| frame | List[ndarray] | 64x64 프레임 데이터, 값 0-15 |
| state | GameState | 현재 게임 상태 |
| levels_completed | int | 완료한 레벨 수 (0-254) |
| win_levels | int | 이긴 레벨 수 |
| available_actions | list[int] | 사용 가능한 액션 ID들 |
| action_input | ActionInput | 마지막 수행한 액션 |
| guid | str | 세션 ID |

### GameState (Enum)
| Value | Description |
|-------|-------------|
| NOT_PLAYED | 게임 시작 전 |
| NOT_FINISHED | 게임 진행 중 |
| WIN | 게임 승리 |
| GAME_OVER | 게임 오버 |

### GameAction (Enum)
| Action | ID | Type | Description |
|--------|-----|------|-------------|
| RESET | 0 | Simple | 게임/레벨 리셋 |
| ACTION1 | 1 | Simple | 게임별 (보통 Up) |
| ACTION2 | 2 | Simple | 게임별 (보통 Down) |
| ACTION3 | 3 | Simple | 게임별 (보통 Left) |
| ACTION4 | 4 | Simple | 게임별 (보통 Right) |
| ACTION5 | 5 | Simple | 게임별 (interact) |
| ACTION6 | 6 | Complex | x,y 좌표 필요 (0-63) |
| ACTION7 | 7 | Simple | Undo |

```python
# Simple action
obs = env.step(GameAction.ACTION1)

# Complex action (ACTION6)
obs = env.step(GameAction.ACTION6, data={"x": 32, "y": 32})

# With reasoning
obs = env.step(GameAction.ACTION1, reasoning={"thought": "trying up"})
```

### Scorecard
```python
scorecard_id = arc.create_scorecard(tags=["experiment"])
env = arc.make("game_id", scorecard_id=scorecard_id)
# ... play ...
result = arc.close_scorecard(scorecard_id)
print(result.score)
```

## Scoring: RHAE (Relative Human Action Efficiency)
- per-level: `(human_baseline / ai_actions) ^ 2`, capped at 1.0
- per-game: weighted average by level index (later levels weigh more)
- total: average of all game scores
