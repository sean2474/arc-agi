# ARC-AGI-3 환경 구조 메모

## 게임 정보 (env.info)

| 필드 | 타입 | 예시 (ls20) | 설명 |
|------|------|-------------|------|
| `game_id` | `str` | `"ls20-9607627b"` | 게임 ID + 버전 해시 |
| `title` | `str` | `"LS20"` | 게임 이름 |
| `tags` | `list[str]` | `["keyboard"]` | 게임 태그. `keyboard`=simple only, `mouse`=complex 포함 |
| `baseline_actions` | `list[int]` | `[21, 123, 39, 92, 54, 108, 109]` | 레벨별 베이스라인 액션 수 |

---

## Action Space

### 액션 종류
- **RESET** (value=0) — 게임/레벨 리셋
- **ACTION1~ACTION7** (value=1~7) — 게임별로 사용 가능한 액션이 다름

### Simple vs Complex
- **Simple** (`is_simple()=True`): 데이터 없이 액션 ID만 전달 (예: 방향키)
- **Complex** (`is_complex()=True`): `x, y` 좌표 등 추가 데이터 필요 (예: 마우스 클릭)

### ls20 예시
```
ACTION1 (value=1) simple=True   ← 아마 상/하/좌/우 중 하나
ACTION2 (value=2) simple=True
ACTION3 (value=3) simple=True
ACTION4 (value=4) simple=True
```
- `keyboard` 태그 게임이라 전부 simple action

### Complex Action 사용법
```python
action = GameAction.ACTION5
action.set_data({"x": 32, "y": 16})
action.reasoning = {"action": action.value, "reason": "clicked target"}
```

---

## Observation Space (FrameDataRaw)

`env.step(action)` 호출 시 반환되는 Pydantic 모델.

| 필드 | 타입 | 설명 |
|------|------|------|
| `game_id` | `str` | 게임 ID |
| `state` | `GameState` | 현재 상태 |
| `levels_completed` | `int` | 지금까지 완료한 레벨 수 |
| `win_levels` | `int` | 승리에 필요한 총 레벨 수 (ls20=7) |
| `action_input` | `ActionInput` | 방금 수행한 액션 정보 (`id`, `data`, `reasoning`) |
| `guid` | `str \| None` | 세션 고유 ID |
| `full_reset` | `bool` | 전체 리셋 여부 |
| `available_actions` | `list[int]` | 현재 사용 가능한 액션 value 목록 |

### GameState 값
```
NOT_PLAYED   — 아직 시작 안 함
NOT_FINISHED — 진행 중
WIN          — 승리 (모든 레벨 클리어)
GAME_OVER    — 실패
```

### frame (핵심 관측 데이터)
```
obs.frame → list[ndarray]
```
- 보통 **1개의 numpy array** (길이 1인 리스트)
- shape: **(64, 64)**, dtype: **int8**
- 값 범위: **0~12** (색상/타일 인덱스)
- 매 step마다 업데이트된 그리드 상태를 반환

#### ls20 프레임 예시
```
frame[0]: shape=(64, 64) dtype=int8
unique values: [0, 1, 3, 4, 5, 8, 9, 11, 12]
```

---

## 프레임 히스토리

ARC-AGI-3 Toolkit 자체는 **히스토리를 자동으로 관리하지 않음**.

- `env.step()` → 매번 현재 프레임 1개만 반환
- 히스토리가 필요하면 **직접 리스트에 누적**해야 함

```python
frames = []
obs = env.step(GameAction.RESET)
frames.append(obs)

for _ in range(100):
    action = agent.choose_action(frames, frames[-1])
    obs = env.step(action)
    frames.append(obs)
```

공식 에이전트 인터페이스에서도 이렇게 사용:
```python
def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
    # frames = 지금까지 모든 프레임 히스토리
    # latest_frame = 가장 최근 프레임
```

---

## observation_space (초기 상태)

`env.observation_space`로 step 전에도 확인 가능:
```json
{
  "game_id": "ls20-9607627b",
  "state": "NOT_FINISHED",
  "levels_completed": 0,
  "win_levels": 7,
  "action_input": {"id": 0, "data": {}, "reasoning": null},
  "guid": "e317aae8-...",
  "full_reset": true,
  "available_actions": [1, 2, 3, 4]
}
```

---

## 요약

```
게임 루프:
  1. arc = Arcade()
  2. env = arc.make("ls20")
  3. obs = env.step(RESET)          → 64x64 int8 그리드 + 메타데이터
  4. obs = env.step(ACTION1~7)      → 업데이트된 그리드
  5. obs.state == WIN 이면 종료
  6. arc.get_scorecard() 로 점수 확인
```