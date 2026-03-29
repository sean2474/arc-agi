# Agent Design

## 인간의 게임 플레이 사고 프로세스 (참고)

실제 인간이 미지의 게임을 플레이할 때의 패턴:

1. **가용 액션 확인** — "클릭밖에 없음", "방향키가 가능하네"
2. **오브젝트별 실험** — "일단 색깔별로 한번씩 클릭해보자"
3. **즉각 가설 + 반증** — "높이를 맞추는건가? 아니면 배를 넘기는건가?"
4. **이전 레벨 지식 활용** — "전처럼 죽지 않고 초록색으로 가면 될거같다"
5. **새 오브젝트 경계** — "새로운 주황색이 생겼다. 추정할 수 없다."
6. **리스크 관리** — "확실하지 않으니 안전하게", "리스크를 만들 필요 없음"
7. **패턴 일반화** — "같은색 클릭은 같은색에 변화를 준다" (나중에 반증될 수도)
8. **변화에만 집중** — 이미 알고 있는 오브젝트는 다시 분석 안 함. "파란색이 움직였다"만 확인.

## 모델 구성

| 역할 | 모델 | 용도 |
|------|------|------|
| VLM | Qwen2.5-VL-7B | SCAN(이름/역할만), HYPOTHESIZE, DECIDE, REDEFINE(이벤트 시), ANALYZE, UPDATE |
| 코드 | Python | blob 추출, diff 계산, 이벤트 감지, 카메라 추적, PLANNER |

단일 VLM 구조. SCAN/DECIDE/REDEFINE은 이미지+텍스트, 나머지는 텍스트만. 32GB VRAM 제약.
**코드가 위치/크기/색상 100% 정확하게 계산 → VLM은 의미론적 해석만 담당.**

## 사이클 구조

```
Phase 1 (첫 프레임):
  [코드] detect_background + extract_blobs + auto_tag
  → SCAN(VLM: 이름/역할만) → HYPOTHESIZE(VLM) → UPDATE(VLM) → phase 전환

Phase 2~4 (시퀀스 실행 중이 아닐 때):
  PLANNER(코드) → DECIDE(VLM+이미지) → EXECUTE
  → [코드] blob diff + 이벤트 감지
      ├─ split/merge/appear → REDEFINE(VLM: 영향 blob만)
      └─ disappear         → is_present=false (코드)
  → ANALYZE(VLM: 코드 diff 수신) → UPDATE(VLM)

Phase 2~4 (시퀀스 실행 중일 때):
  EXECUTE → [코드] diff+이벤트 → REDEFINE(조건부)
  → ANALYZE(VLM)
  ├─ continue: 다음 action 실행
  ├─ abort:   UPDATE(VLM) → PLANNER → DECIDE (re-plan)
  └─ success: UPDATE(VLM) → PLANNER (다음 plan)
```

### 호출 순서

| Phase | 순서 | 호출 | 담당 | 역할 |
|-------|------|------|------|------|
| **Phase 1** | 1 | blob 추출 | 코드 | detect_background + extract_blobs. obj_NNN 키 부여. HUD 자동 태깅. |
| **Phase 1** | 2 | SCAN | VLM+이미지 | 코드가 추출한 blob 목록 수신 → name, type_hypothesis 부여만. 위치/크기/색상 추정 금지. |
| **Phase 1** | 3 | HYPOTHESIZE | VLM | 초기 가설 수립. 오브젝트 역할/게임타입/목표 추측. |
| **Phase 1** | 4 | UPDATE | VLM | objects + 가설을 world_model에 저장. |
| **Phase 2** | 1 | PLANNER | 코드 | plans 리스트에서 pending 중 가장 우선 plan 선택. status → active. |
| **Phase 2** | 2 | DECIDE | VLM+이미지 | current_subgoal + objects(bbox 포함) + 이미지 → action_sequence (최대 6개). |
| **Phase 2** | 3 | EXECUTE | 코드 | pending_sequence에서 action 1개 pop 후 env.step(). |
| **Phase 2~4** | 4 | diff+이벤트 | 코드 | 각 애니메이션 프레임 쌍마다: (1) 카메라 shift 감지(SSE) → (2) blob bbox 보정 → (3) 오브젝트 이동 delta 계산. 이벤트 merge 후 ANALYZE에 전달. |
| **Phase 2** | 5 | REDEFINE | VLM+이미지 | split/merge/appear 시만. 영향 blob의 name/type_hypothesis 재부여. |
| **Phase 2** | 6 | ANALYZE | 코드 | plan.target_object + blob diff → continue/abort/success 판정. VLM 호출 없음. |
| **Phase 2** | 7 | UPDATE | VLM | abort/success 시만. world_model + plans 갱신. |

## PLANNER

코드만. LLM 호출 없음. `world_model.plans`에서 `status=pending` 중 priority 가장 낮은 것 선택.
pending 없으면 UPDATE에서 새 plan 생성 트리거.

## DECIDE

입력: `current_subgoal` + objects(bbox 포함) + 이미지.
**game goal / goal_hypotheses 없음** — 순수 경로/상호작용 계획만.
출력: `action_sequence` (최대 6개) + **`desired_event`** (코드 ANALYZE가 검증할 기대 이벤트).
click: `["click", "obj_name"]` 형식. `"click"` 단독 문자열 금지.

## ANALYZE (코드, VLM 호출 없음)

DECIDE의 `desired_event` + 실제 blob diff 비교 → `continue / abort / success` 판정.

**desired_event 있는 plan**:
- desired_event 타입이 실제 diff와 일치 → `continue`
- 불일치 또는 변화 없음 → `abort` (액션 효과 없음)
- desired obj 외 예상 밖 blob 변화 → `abort` (환경 변화)
- `disappear` 이벤트 + `is_present=false` → `success`
- game_over → `abort` + INCIDENT
- level_complete → `success` + INCIDENT

**desired_event 없는 plan (탐색형)**:
- 단일 action만 허용 (sequence 1개)
- 실행 후 무조건 UPDATE 트리거

## UPDATE

ANALYZE discoveries + (INCIDENT) 결과로 world_model 갱신. abort/success 시만 호출.
`plans` 갱신: abort → plan 수정 또는 새 plan 추가. success → done 마킹.

## INCIDENT

game_over 또는 level_complete 시에만 호출. ANALYZE 전에 실행.
게임 유형을 가정하는 용어 사용 금지.

## 이벤트 분류

### 오브젝트 이벤트 (코드 자동 감지)
| 이벤트 | 트리거 |
|--------|--------|
| `move` | blob 위치 변경 |
| `appear` | 이전 프레임에 없던 blob 등장 |
| `disappear` | 이전 프레임에 있던 blob 소멸 |
| `split` | 같이 움직이던 blob들의 벡터 분리 |
| `merge` | touching + 동일 벡터로 이동 |
| `rotate` | 같은 셀 수, 다른 배치 |
| `transform` | 같은 위치에서 색상/모양 변경 |
| `collide` | 두 blob이 touching 상태가 됨 |
| `teleport` | 거리 threshold 초과하는 순간이동 |

### 월드 이벤트 (obs.state로 코드 감지)
| 이벤트 | 조건 |
|--------|------|
| `game_over` | obs.state == GAME_OVER |
| `level_complete` | obs.state == LEVEL_COMPLETE |
| `score_change` | HUD 숫자 변화 |

## 프롬프트 원칙

- specific한 example 금지 — bias
- JSON 구조만 "..."로
- 게임 유형을 가정하는 용어 금지
- goal이 좌표라는 가정 금지
- SCAN: 코드가 blob 추출 후 LLM은 name/type_hypothesis만 부여
- HUD: 가장자리 blob → step_counter/score/hud 라벨. 액션 대상 제외
- No Fallback: 에러 시 RuntimeError. 조용한 대체 금지.
