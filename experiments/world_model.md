# World Model

게임 규칙에 대한 구조화된 가설 + confidence.
summary(자유 텍스트)와 달리, world model은 코드가 직접 읽고 판단할 수 있는 구조.

## 구조

```json
{
  "phase": "static_observation",
  "game_type": {"hypothesis": "unknown", "confidence": 0.0},
  "actions": {
    "up": {
      "effects": [
        {"context": "default", "effect": "unknown", "confidence": 0.0}
      ]
    },
    "click": {
      "effects": [
        {"context": "default", "effect": "unknown", "confidence": 0.0}
      ],
      "target": null
    }
  },
  "objects": {
    "obj_001": {
      "type_hypothesis": "unknown",
      "instance_id": "obj_001",
      "value": "c",
      "bbox": {"row_min": 46, "row_max": 47, "col_min": 33, "col_max": 37},
      "clickable": false,
      "interaction_tested": false
    }
  },
  "controllable": {"description": null, "confidence": 0.0},
  "goal": {"description": null, "confidence": 0.0},
  "dangers": [],
  "interactions": [],
  "immediate_plan": {"description": "...", "confidence": 0.0},
  "strategic_plan": {"description": "...", "confidence": 0.0}
}
```

## Object Identity

오브젝트는 단순 name이 아니라 **instance_id + bounding box**로 식별.
같은 색/모양 오브젝트가 여러 개일 수 있으므로.

```json
"obj_001": {
  "type_hypothesis": "unknown",
  "instance_id": "obj_001",
  "value": "c",
  "bbox": {"row_min": 46, "row_max": 47, "col_min": 33, "col_max": 37},
  "clickable": false,
  "interaction_tested": false
}
```

- **instance_id**: 고유 식별자. SCAN에서 발견 순서대로 `obj_001`, `obj_002`, ...
- **type_hypothesis**: "unknown" → "static" / "dynamic" / "controllable" / "dangerous" / "goal" 등
- **bbox**: bounding box. click 시 center 좌표 계산에도 사용.
- **value**: hex 값. 같은 값이어도 다른 instance일 수 있음.

왜 이름 대신 instance_id?
- LLM이 "lime_block"이라고 이름 붙이면 같은 색 블록이 2개일 때 혼동
- instance_id는 코드가 부여 → 안정적
- LLM은 type_hypothesis만 관리

## Context-Dependent Confidence

action confidence는 전역이 아니라 **context별**.
같은 "up"이라도 상황에 따라 결과가 다를 수 있음.

```json
"up": {
  "effects": [
    {"context": "default", "effect": "moves controllable up 1 cell", "confidence": 0.7},
    {"context": "near_wall", "effect": "no movement", "confidence": 0.7},
    {"context": "near_obj_003", "effect": "pushes obj_003", "confidence": 0.3}
  ]
}
```

- **context**: 상황 조건. 처음에는 "default"만 있음.
- 같은 action이 다른 결과를 낳으면 context를 분리해서 기록.
- 예: "빈칸에서 up" → 이동, "벽 앞에서 up" → no-op, "오브젝트 옆에서 up" → push

### confidence 계산
코드가 `get_action_confidence(action_name)`을 호출하면:
- effects가 1개면 그 confidence 반환
- effects가 여러 개면 가장 높은 confidence 반환 (최소한 하나는 검증됨)
- effects가 0개면 0.0

## confidence 규칙

| 값 | 의미 |
|----|------|
| 0.0 | 전혀 모름 (테스트 안 함) |
| 0.3 | 가설만 있음 (관찰 기반 추측) |
| 0.7 | 1회 검증됨 (기대대로 변화 확인) |
| 1.0 | 반복 확인됨 |

## Phase System

Phase는 **선형 순서가 아님**. 현재 상태에서 가장 필요한 것으로 동적 결정.
action 테스트 중에 interaction 가설이 생길 수도 있고,
game_over로 goal 가설이 바로 생길 수도 있음.

### Phase 정의

| Phase | 조건 | 의미 |
|-------|------|------|
| static_observation | objects가 비어있음 | 아직 아무것도 모름 |
| action_discovery | untested action이 있음 | 기본 조작법 파악 중 |
| interaction_discovery | untested object가 있음 | 오브젝트 상호작용 파악 중 |
| goal_execution | goal confidence > 0 | 목표를 향해 실행 중 |

### Phase 전환 — 비선형

우선순위:
1. objects가 비어있으면 → static_observation
2. untested action이 있으면 → action_discovery (goal 가설이 있어도 action 파악 우선)
3. goal confidence >= 0.3이고 untested action 없으면 → goal_execution
4. untested object가 있으면 → interaction_discovery
5. 그 외 → goal_execution

핵심: goal 가설이 일찍 생겨도 untested action이 있으면 먼저 처리.
action discovery 중에 game_over가 나면 바로 danger가 기록되고 goal 가설이 생길 수 있음.

## click+object

click은 좌표가 아니라 **object instance_id**를 대상으로 동작.
DECIDE가 ["click", "obj_003"] 형태로 반환하면, 코드가 bbox의 center를 계산해서 실제 좌표로 변환.

click으로 interaction 확인 시:
- objects.obj_003.clickable = true
- interactions에 추가
- actions.click에 새 context+effect 추가

## plans

immediate_plan과 strategic_plan도 confidence를 가짐.
새로운 정보가 들어올 때마다 plan 유효성 재평가.
confidence가 낮아지면 재수립.

## 레벨 전환

레벨 클리어 후:
- phase → static_observation 리셋
- **interactions**: 유지.
- **dangers**: 유지.
- **action confidence**: LLM이 OBSERVE에서 조절 (코드 강제 아님)
- **strategic_plan**: 전 레벨 클리어 방법을 참고로 포함.

### Object Identity 연결 (레벨 간)

새 레벨 SCAN에서 오브젝트를 발견하면, 이전 레벨의 objects와 매칭 시도.

매칭 조건: value가 같고, 비슷한 크기/형태.
매칭 성공 → 이전 레벨의 type_hypothesis, clickable, interaction 지식을 carry-over.
매칭 실패 → 새 instance_id 부여, type_hypothesis = "unknown".
interaction_tested는 false로 리셋 (위치가 달라졌으니 재검증 필요).

이렇게 하면 같은 value "c"인 오브젝트가 새 레벨에 나타나도
이전 레벨에서 "controllable"이었다는 지식이 유지됨.

## 방향키 배치 업데이트

방향키 하나만 테스트해도 나머지 추론 가능.
나머지 액션(space, click, undo)은 개별 테스트 필요.
