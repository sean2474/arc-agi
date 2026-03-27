# World Model

게임 규칙에 대한 구조화된 가설 + confidence.
summary(자유 텍스트)와 달리, world model은 코드가 직접 읽고 판단할 수 있는 구조.

## 구조

```json
{
  "phase": "static_observation",
  "game_type": {"hypothesis": "unknown", "confidence": 0.0},
  "actions": {
    "up":    {"effect": "unknown", "confidence": 0.0},
    "down":  {"effect": "unknown", "confidence": 0.0},
    "left":  {"effect": "unknown", "confidence": 0.0},
    "right": {"effect": "unknown", "confidence": 0.0},
    "space": {"effect": "unknown", "confidence": 0.0},
    "click": {"effect": "unknown", "confidence": 0.0, "target": null},
    "undo":  {"effect": "unknown", "confidence": 0.0}
  },
  "objects": {
    "name": {"value": "...", "position": "...", "type": "unknown", "clickable": false, "interaction_tested": false}
  },
  "controllable": {"description": null, "confidence": 0.0},
  "goal": {"description": null, "confidence": 0.0},
  "dangers": [],
  "interactions": [
    {"subject": "...", "object": "...", "action": "...", "result": "...", "confidence": 0.0}
  ],
  "immediate_plan": {"description": "...", "confidence": 0.0},
  "strategic_plan": {"description": "...", "confidence": 0.0}
}
```

## confidence 규칙

| 값 | 의미 |
|----|------|
| 0.0 | 전혀 모름 (테스트 안 함) |
| 0.3 | 가설만 있음 (관찰 기반 추측) |
| 0.7 | 1회 검증됨 (기대대로 변화 확인) |
| 1.0 | 반복 확인됨 |

## Phase System

에이전트는 4단계를 순서대로 진행. "캐릭터"라는 가정 없이, "액션의 결과로 뭐가 변하는지"만 추적.

### Phase 1: Static Observation
- 첫 프레임만 보고 모든 구분 가능한 요소 추출
- 아직 뭐가 뭔지 모름 — 전부 type: "unknown"
- DECIDE/EXECUTE 없음. 관찰만.
- 종료: 첫 OBSERVE 완료

### Phase 2: Action Effect Discovery
- 액션 1개씩 실행, 뭐가 바뀌었는지 관찰
- 움직인 오브젝트 → type: "dynamic" 또는 "controllable"
- 방향키 1개 검증 → 나머지 3개 추론 (confidence 0.5)
- 종료: action 평균 confidence >= 0.7

### Phase 3: Interaction Discovery
- controllable로 다른 오브젝트에 접근/작용 시도
- 성공 → interactions에 추가
- 실패 → type: "non-interactive"
- 위험 → dangers에 추가
- 종료: untested candidate 없음

### Phase 4: Goal Discovery + Execution
- interaction들로 win condition 가설 수립
- 가설 검증 → 레벨 클리어
- 종료: goal confidence >= 0.7 또는 레벨 클리어

### Phase 전환 (코드)

```python
def get_current_phase(world_model):
    if not world_model["objects"]:
        return "static_observation"
    action_avg = avg(action confidences)
    if action_avg < 0.7:
        return "action_discovery"
    if untested_candidates:
        return "interaction_discovery"
    return "goal_execution"
```

## click+object

click은 좌표가 아니라 object를 대상으로 동작.
스테이지마다 같은 형태여도 좌표가 달라질 수 있으므로.

```
DECIDE: "action": ["click", "object_name"]
코드: center_of(obj["position"]) → ["click", x, y]
```

click으로 interaction 확인 시:
- objects.object_name.clickable = true
- interactions에 추가
- actions.click.confidence 갱신

## plans

immediate_plan과 strategic_plan도 confidence를 가짐.
새로운 정보가 들어올 때마다 plan 유효성 재평가.
confidence가 낮아지면 재수립.

## 레벨 전환

레벨 클리어 후:
- phase → static_observation 리셋
- **objects**: position만 "unknown"으로. type, clickable 등 속성은 유지.
  같은 오브젝트가 다음 레벨에도 있을 수 있으므로 지식은 보존.
- **interactions**: 유지. 전 레벨에서 검증된 interaction은 다음 레벨에서도 유효할 가능성 높음.
- **dangers**: 유지. 위험한 오브젝트 정보는 carry-over 필수.
- **action confidence**: LLM이 OBSERVE에서 조절 (코드 강제 아님)
- **strategic_plan**: 전 레벨 클리어 방법을 참고로 포함.

objects의 interaction_tested는 false로 리셋 — 위치가 달라졌을 수 있으니 재검증 필요.
하지만 type 정보("이건 위험했다", "이건 밀 수 있었다")는 가설로 남겨둠.

## 방향키 배치 업데이트

방향키 하나만 테스트해도 나머지 추론 가능.
나머지 액션(space, click, undo)은 개별 테스트 필요.
LLM이 UPDATE에서 방향키 4개를 한꺼번에 업데이트.
