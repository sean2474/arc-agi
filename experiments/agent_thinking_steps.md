# Thinking Process — 각 단계별 설명

## 모델 구성

단일 VLM 구조 (32GB VRAM 제약).

| 역할 | 모델 | 용도 |
|------|------|------|
| VLM | Qwen2.5-VL-7B | OBSERVE, DECIDE, EVALUATE, UPDATE, INCIDENT |

VLM은 이미지도, 텍스트만도 처리 가능. DECIDE/OBSERVE에 이미지 추가 전달.
코드가 blob 추출 + diff 계산을 담당 → VLM은 의미론적 해석만.

## 전체 흐름

```
매 스텝 (시퀀스 종료 시):
  [코드] BlobManager init/step → detect_scale → sync_from_blobs
  → 자동 재분류 (move blob: unknown/obstacle → controllable)
  → OBSERVE(VLM+이미지)  ← 첫 호출 시 unnamed blob 분류 포함
  → EVALUATE(VLM) → UPDATE(VLM)
  → PLANNER(코드) → DECIDE(VLM+이미지) → EXECUTE

매 스텝 (시퀀스 실행 중):
  [코드] BlobManager step → 자동 재분류
  → ANALYZE(코드)
  ├─ pending 있음: 다음 action 실행
  └─ pending 없음: OBSERVE → EVALUATE → UPDATE → PLANNER → DECIDE
```

---

### 코드 전처리 (BlobManager)

**첫 스텝:**
- `detect_background_colors(grid)` → 배경 색상 집합
- `extract_blobs(grid, bg_colors)` → flood fill, `obj_001`... 키 부여
- `detect_scale(grid)` → 카메라 upscale factor (1/2/3/4)
- `sync_from_blobs(scale=N)` → game-space position/size world model에 저장

**이후 스텝:**
- `BlobManager.step(anim_frames)` → 이벤트 감지 (move/collide/appear/disappear/rotation)
- `sync_from_blobs(scale=N)` → 갱신

### 자동 재분류 (코드)

move 이벤트가 발생한 blob 중 `type_hypothesis`가 `unknown` 또는 `obstacle`인 것은
코드가 `controllable`로 자동 재분류. LLM 호출 없음.

---

## PLANNER (알고리즘, LLM 호출 없음)

- 입력: world_model.plans 리스트
- 목적: 현재 실행할 서브골 1개 선택
- 하는 일:
  - `status=pending`인 항목 중 priority 숫자 가장 낮은 것 선택
  - 선택된 항목 status → `active`
  - pending 항목 없으면 UPDATE에 "새 plan 생성 필요" 신호 전달
- 출력: `current_subgoal` (plan의 description + rationale)

---

## DECIDE (VLM + 이미지)

- 입력: `current_subgoal` + objects(bbox 포함) + **bbox 어노테이션 이미지** + **ACTION HISTORY** (최근 20 스텝 `action → observation`)
- 목적: 서브골 달성을 위한 **action sequence** 계획
- **game goal / goal_hypotheses / reports 입력 없음** — 순수 경로/상호작용 계획만
- 하는 일:
  - 이미지와 object 위치를 보고 경로 계산
    - 예: player(3,5) → target(3,10), 중간 벽(col 7) → 우회 경로
  - 최대 6개 action의 sequence 계획
- 하지 않는 일:
  - 게임 목표 판단 (Planner의 역할)
- 출력:
  ```json
  {
    "reasoning": "player at (3,5), target at (3,10), wall at col 7. detour: right×2, down×1, right×2",
    "action_sequence": ["right", "right", "down", "right", "right"]
  }
  ```
  click 액세 예시:
  ```json
  {
    "reasoning": "need to click on platform",
    "action_sequence": [["click", "obj_004"]]
  }
  ```
  - click 아이템은 **배열** `["click", "obj_id"]` 형식. **instance_id(`obj_NNN`) 사용** — name 사용 금지. `"click"` 단독 문자열 → `RuntimeError`

---

## EXECUTE + 애니메이션 분석 (코드)

- env.step(action) 실행 → `obs.frame` 리스트 반환 (중간 애니메이션 프레임 포함)
- LLM 없음. 코드가 전체 프레임 시퀀스를 분석

### 애니메이션 프레임 분석 파이프라인

연속 프레임 쌍 `(frame[i] → frame[i+1])` 마다:

```
1. 카메라 shift 감지 (SSE 기반, 탐색 범위 ±4)
   - 모든 픽셀 SSE. 배경이 화면의 대부분이므로 배경 패턴이 dominant
   - 이전 프레임 대비 diff < threshold → camera shift 없음으로 처리

2. 카메라 shift 있으면 → 모든 tracked blob의 bbox를 (-dr, -dc) 보정

3. 보정된 위치 기준으로 오브젝트 이동 delta 계산
   - 보정 후에도 위치가 달라진 blob → 자체 이동 (move 이벤트)
   - 보정 후 사라진 blob → disappear
   - 보정 후 새로 나타난 blob → appear
```

### 연속 이벤트 merge

```
같은 blob이 같은 방향으로 N프레임 연속 이동 → 하나의 move 이벤트로 압축
  frame0→1: obj_001 (dr=0, dc=+1)
  frame1→2: obj_001 (dr=0, dc=+1)
  frame2→3: obj_001 (dr=0, dc=+1)
  → move(obj_001, delta=(0, +3), frames=[0, 2])

방향이 바뀌거나 멈추면 → 새 이벤트로 분리
appear / disappear / collide → 발생한 프레임 시점에 기록
```

### false disappear 방지 (코드 포스트 루프)

애니메이션 루프 완료 후, 첫 번째 camera frame을 찾아
그 이전의 모든 프레임에서 `cause=unknown` disappear 이벤트를 소급 제거.
(카메라 스크롤 시작 직전 프레임에서 쾐릭터가 화면 밀으로 이동해 일시적으로 사라지는 경우 오탐 방지.)

### 이벤트 `obj` 필드 규칙

모든 이벤트의 `obj` 필드는 **`obj_id`** (`obj_001` 등)로 고정. name은 `name` 필드에 추가로 표시용.

### 최종 출력 (ANALYZE에 전달)

```json
[
  {"type": "camera_shift", "delta": [0, -2], "frames": [0, 3]},
  {"type": "move", "obj": "obj_001", "name": "player", "delta": [0, 3], "frames": [0, 2]},
  {"type": "collide", "obj_a": "obj_001", "name_a": "player", "obj_b": "obj_005", "name_b": "enemy", "frame": 3},
  {"type": "disappear", "obj": "obj_005", "name": "enemy", "frame": 3, "cause": "collide_destroy"}
]
```

---

## OBSERVE (VLM + 이미지)

- 입력: before/after 이미지 + 이벤트 목록 + world_model
- **STEP 0 (unnamed blob 존재 시만)**: 이미지를 보고 각 unnamed obj에 name + type_hypothesis 부여
  - 결과는 `renamed_objects` 필드로 반환 → 기존 경로 재사용
  - 이미 name 있으면 이 단계 스킵
- **STEP 1~5**: 이벤트 기반 변경 추적, 재분류, 관계 갱신
- 이벤트 없고 이미지 동일 시 NO-CHANGE SHORTCUT으로 즉시 반환

---

## ANALYZE (코드, VLM 호출 없음)

`pending_sequence` 기반 단순 판정. LLM 없음.

| 조건 | 결과 |
|------|------|
| `pending_sequence` 항목 남아있음 | continue — 다음 action 실행 |
| `pending_sequence` 비어있음 | done — `mark_plan(done)` → OBSERVE → EVALUATE → UPDATE → PLANNER → DECIDE |

---

## EVALUATE

- 시퀀스 완료 시 OBSERVE 직후 호출.
- 입력: `observe_result` + `current_subgoal`(description, success_condition, failure_condition) + `planned_sequence` + (INCIDENT 결과)
- 하는 일:
  - OBSERVE 결과를 기반으로 goal 달성 여부 판단
  - 예상 외 현상 보고
  - 한 혁수에서 배운 점 key_learnings 정리
- 출력: `goal_achieved`, `goal_evaluation`, `confidence`, `new_discoveries`, `report`(key_learnings 포함)

## UPDATE

- 입력: world_model + EVALUATE `evaluation` + `discoveries` + (INCIDENT 결과)
- 목적: world_model과 summary를 갱신
- 하는 일:
  - action confidence 갱신 (테스트 결과 반영)
  - objects 상태 업데이트 (type, interaction_tested)
  - interactions 추가/제거
  - relationships 갱신
    - 코드 diff에서 감지된 passive 이벤트 → `interaction_result` 채움, confidence 상승
    - 반증된 relationship → confidence 낮춤 또는 제거
  - dangers 추가
  - 방향키: 1개 테스트 결과로 나머지 3개 추론
  - plans 갱신 (새 서브골 추가, done/failed 정리)
- 하지 않는 일:
  - 오브젝트 관찰 또는 위치 추적 (코드의 역할)
  - 판단 (ANALYZE의 역할)
- 출력: updated_summary + updated_world_model

---

## INCIDENT (특수)

- game_over 또는 level_complete 시에만 호출
- ANALYZE 전에 실행
- 목적: 사건 원인 분석
  - game_over: 뭐가 원인이었는지, 어떻게 피할 수 있는지
  - level_complete: 뭐가 트리거였는지, 다음 레벨에도 적용 가능한지
- 출력: incident_result → ANALYZE와 UPDATE에 전달
