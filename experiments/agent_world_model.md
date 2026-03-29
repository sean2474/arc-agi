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
      "instance_id": "obj_001",
      "name": "platform",
      "shape": "rectangle",
      "type_hypothesis": "unknown",
      "colors": ["c"],
      "position": "46,33",
      "size": "2x5",
      "bbox": {"row_min": 46, "row_max": 47, "col_min": 33, "col_max": 37},
      "clickable": false,
      "interaction_tested": false
    }
  },
  "controllable": {"description": null, "confidence": 0.0},
  "goal_hypotheses": [
    {"description": "...", "confidence": 0.3, "supporting_evidence": [], "contradicting_evidence": []}
  ],
  "dangers": [],
  "interactions": [],
  "relationships": [],
  "plans": [
    {"description": "...", "priority": 1, "status": "pending", "confidence": 0.5, "rationale": "..."}
  ]
}
```

## Object Identity

오브젝트는 **instance_id (key)** 로 식별. id는 고정, name은 변경 가능.

```json
"obj_001": {
  "instance_id": "obj_001",
  "name": "platform",
  "shape": "rectangle",
  "type_hypothesis": "static",
  "colors": ["c"],
  "position": "46,33",
  "size": "2x5",
  "bbox": {"row_min": 46, "row_max": 47, "col_min": 33, "col_max": 37},
  "clickable": false,
  "interaction_tested": false
}
```

- **instance_id**: 코드가 부여. 고정. `obj_001`, `obj_002`, ... 순서대로.
  - **UPDATE LLM은 새 오브젝트를 직접 삽입할 수 없음** — `apply_llm_update`는 `obj_NNN` 형식 키만 허용. name-keyed 오브젝트 삽입 차단.
  - 새 오브젝트 추가는 SCAN 또는 OBSERVE(`new_objects`)만 가능.
- **name**: VLM이 게임 맥락으로 붙이는 이름 (`"player"`, `"goal"`, `"wall"` 등). OBSERVE마다 재평가 가능. 게임 역할 기반으로 지을 것 — 색깔/모양 이름(`"green_block"`) 금지.
- **shape**: 모양 (`"square"`, `"rectangle"`, `"L-shape"` 등). name과 분리.
- **type_hypothesis**: `"unknown"` → `"static"` / `"dynamic"` / `"controllable"` / `"dangerous"` / `"goal"`
- **colors**: **ARC index** 배열 (`"e"`, `"9"` 등). LLM은 `0`=white, `e`=green 등 ARC index를 사용해야 함. RGB hex(`"00FF00"`)는 지원하지 않음.
  - bbox 영역에 해당 ARC index가 없으면 코드가 `RuntimeError` 발생 — LLM 할루시네이션 검증.
- **colors(old)**: hex 색상값 배열. 오브젝트가 여러 색으로 구성될 수 있음 (예: 캐릭터의 몸통+머리). 단색이면 1개. 같은 색이어도 다른 instance일 수 있음.
- **position**: VLM이 반환하는 top-left 좌표 `"row,col"` 형식.
- **size**: VLM이 반환하는 크기 `"HxW"` 형식.
- **bbox**: 코드가 position + size로 계산. click center 좌표 계산에 사용.

### Name 재평가 (OBSERVE)

OBSERVE마다 VLM이 기존 object name이 적절한지 판단.
변경이 필요하면 `renamed_objects` 필드로 반환:

```json
"renamed_objects": {
  "obj_003": {"new_name": "exit", "reason": "reached it and level completed"}
}
```

id는 고정이므로 rename해도 world_model continuity 유지. 코드가 `_data["objects"][id]["name"]`만 업데이트.

## 설계 원칙

**No Fallback**: 이 프로젝트에서는 fallback이 없음. 에러 발생 시 `RuntimeError`를 raise해서 근본 원인을 노출. 조용히 다른 값으로 대체하거나 무시하는 코드 금지.
- 예: click 해석 실패 → `RuntimeError` (ACTION1 대체 X)
- 예: bbox 검증 실패 → `RuntimeError` (계속 진행 X)

**Plan 중복 방지**: `add_plan()`은 동일 description(case-insensitive)이 이미 있으면 스킵. LLM UPDATE와 알고리즘 planner 모두 적용.

**executed_action 정확성**: `self.last_action`은 raw_action이 아닌 실제 실행된 `action_name`(예: `"click(player@32,15)"`)을 저장. ANALYZE가 올바른 액션명을 받도록.

## Context-Dependent Confidence

action confidence는 전역이 아니라 **context별**.
같은 "up"이라도 상황에 따라 결과가 다를 수 있음.

```json
"up": {
  "effects": [
    {"context": "default", "effect": "moves controllable up 1 cell", "confidence": 0.7},
    {"context": "near_wall", "effect": "no movement", "confidence": 0.7},
    {"context": "near_box (square, c)", "effect": "pushes box", "confidence": 0.3}
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

## Object-Object Relationships

`interactions`가 **(subject, action, object) → result** 이라면,
`relationships`는 **액선 없이도 성립하는 오브젝트 간 규칙** — 근접, 상태, 위치 조건에 의해 발생.

### 내부 저장 형식

`relationships`는 **`subject_id` / `object_id` (obj_NNN)** 로 저장 — obj_id는 고정이므로 name 변경 시에도 관계 유지.

```json
"relationships": [
  {
    "subject_id": "obj_001",
    "relation": "kills on contact",
    "object_id": "obj_005",
    "context": "adjacent",
    "interaction_result": "game_over",
    "confidence": 0.7
  }
]
```

### 필드 설명

- **subject_id / object_id**: `obj_NNN` 형식. 코드가 `_resolve_to_id(name)`으로 name → id 변환. id가 없으면 `RuntimeError`.
- **relation**: VLM이 자유롭게 서술. 타입 enum 없음 — 게임 유형 가정 금지
- **context**: 관계가 성립하는 조건 (`"adjacent"`, `"on_top_of"`, `"in_line_of_sight"`, `"any"` 등)
- **interaction_result**: 실제 관찰된 결과. 처음에 `null`, 발생 후 채워짐
- **confidence**: `0.0`~`1.0`. 처음 가설이면 `0.3`, 1회 확인이면 `0.7`

### 프롬프트 직렬화 (LLM 표시용)

`to_prompt_dict()`이 `subject_id`/`object_id`를 name으로 resolve해 표시. LLM은 name만 본다.

LLM(`OBSERVE`) 응답 포맷:
```json
{"subject_name": "player", "object_name": "wall", "relation": "...", "context": "any", "interaction_result": "...", "confidence": 0.7}
```
- `obj_id` 포함 금지 — LLM은 name만 제공. 코드가 `_resolve_to_id(name)`으로 obj_id 복원.

### interactions와 차이

| | `interactions` | `relationships` |
|---|---|---|
| trigger | player action | 상태/근접 조건 |
| `action` 필드 | O | X |
| 키 | visual type | `subject_id`/`object_id` (obj_NNN) |
| `interaction_result` | O | O (처음에 null) |
| 발견 시점 | 액션 실행 후 OBSERVE | passive 이벤트 (OBSERVE/INCIDENT) |

### 발견 방법

- **HYPOTHESIZE**: 시각적 배치로 가설 수립 (`confidence: 0.3`)
  - 예: 빨간 오브젝트가 이동 경로에 위치 → `killed_by` 가설
- **OBSERVE**: passive 이벤트 감지 → `interaction_result` 채움, confidence 상승
- **INCIDENT**: game_over/level_complete 원인 분석 → 관련 relationship 확정

### 활용 (Action Scoring)

- `death_risk`: subject → `relation` → object가 adjacent → risk 상승
- `progress`: `relation` 체인으로 goal 경로 분석 (예: switch activates door unlocks path)
- `info_gain`: `interaction_result: null`인 relationship의 오브젝트 근처 이동 = 높은 info_gain

## 프롬프트 직렬화 (Prompt Serialization)

world_model을 프롬프트에 넣을 때는 `obj_NNN` 키 그대로 넣지 않음.
코드가 `to_prompt_dict()`로 변환 후 전달.

### Objects 키 변환 규칙

| 상황 | 키 형식 |
|------|----------|
| 기본 | `"name (shape, color)"` |
| 이름 충돌 시 | `"name (shape, color) [obj_001]"` — instance_id suffix 추가 |
| name 없음 | `"obj_001 (shape, color)"` |

예시:
```json
"objects": {
  "player (square, 5)": {
    "instance_id": "obj_001",
    "type_hypothesis": "controllable",
    "position": "32,20",
    ...
  },
  "enemy (circle, 3)": {
    "instance_id": "obj_003",
    ...
  }
}
```

### 역매핑

VLM이 `subject_name`/`object_name`으로 name을 반환하면, 코드가 `_resolve_to_id(name)`로 `obj_id` 복원 후 저장.
매핑 실패(존재하지 않는 name) 시 → `RuntimeError`.

## click+object

click은 좌표가 아니라 **object instance_id**를 대상으로 동작.
DECIDE가 ["click", "obj_003"] 형태로 반환하면, 코드가 bbox의 center를 계산해서 실제 좌표로 변환.
click으로 interaction 확인 시:
- objects.obj_003.clickable = true
- interactions에 추가
- actions.click에 새 context+effect 추가

## goal_hypotheses

`goal`을 단일 값 대신 **경쟁하는 가설 리스트**로 관리.

```json
"goal_hypotheses": [
  {
    "description": "reach the exit tile",
    "confidence": 0.4,
    "supporting_evidence": ["moving toward bright tile triggered level_complete in level 1"],
    "contradicting_evidence": []
  },
  {
    "description": "collect all items then exit",
    "confidence": 0.2,
    "supporting_evidence": [],
    "contradicting_evidence": ["reached exit without collecting anything and nothing happened"]
  }
]
```

- 처음엔 모든 가설 confidence 0.3 이하
- EVALUATE/UPDATE에서 각 가설의 supporting/contradicting evidence 갱신
- confidence 가장 높은 가설이 현재 active goal → DECIDE의 progress 계산 기준
- 완전히 반증된 가설은 제거 (confidence 0.0)

## plans

실행 가능한 **서브골 리스트**. Planner(알고리즘)가 priority + status 기준으로 active plan 선택.

```json
"plans": [
  {
    "description": "move player to blue object and interact",
    "priority": 1,
    "status": "active",
    "confidence": 0.7,
    "rationale": "blue object looks activatable based on position near exit"
  },
  {
    "description": "test right arrow movement",
    "priority": 2,
    "status": "pending",
    "confidence": 0.5,
    "rationale": "right direction not tested yet"
  }
]
```

- **status**: `pending` → `active` → `done` / `failed`
- **priority**: 낮을수록 우선 (1이 가장 높음)
- Planner는 `status=pending`인 것 중 가장 낮은 priority 숫자 선택
- UPDATE가 `plans` 항목 추가/수정. Action Analyzer가 `done`/`failed` 마킹.

## 레벨 전환

레벨 클리어 후:
- phase → static_observation 리셋
- **interactions**: 유지.
- **dangers**: 유지.
- **action confidence**: LLM이 OBSERVE에서 조절 (코드 강제 아님)
- **plans**: 전 레벨 클리어 방법을 참고해 초기 plan 1개 추가. 기존 done/failed 항목 제거.

### Relationships / Interactions 레벨 전환

`interactions`와 `relationships`는 **visual type 기준**이므로 별도 carry-over 로직 불필요.
새 레벨에 같은 `name (shape, color)` 오브젝트가 등장하면 자동으로 기존 규칙 적용.

- **유지**: `interaction_result`가 채워진 확인된 항목
- **confidence 조정**: 확인된 것은 유지, 가설만 있는 것은 `/2`

### Object Identity 연결 (레벨 간)

새 레벨 SCAN에서 오브젝트를 발견하면 새 `instance_id` 부여 (위치가 다르므로).
`type_hypothesis`, `clickable`은 visual type 매칭으로 자동 carry-over.
`interaction_tested`는 false로 리셋 (위치/배치가 달라졌으니 재검증).

## 방향키 배치 업데이트

방향키 하나만 테스트해도 나머지 추론 가능.
나머지 액션(space, click, undo)은 개별 테스트 필요.
