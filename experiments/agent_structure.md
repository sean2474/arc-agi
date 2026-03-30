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
| VLM | Qwen2.5-VL-7B | OBSERVE, DECIDE, EVALUATE, UPDATE, INCIDENT |
| 코드 | Python | blob 추출, diff 계산, 이벤트 감지, 카메라 추적, PLANNER, ANALYZE, 자동 재분류 |

단일 VLM 구조. DECIDE/REDEFINE은 이미지+텍스트, 나머지는 텍스트만. 32GB VRAM 제약.
**코드가 위치/크기/색상 100% 정확하게 계산 → VLM은 의미론적 해석만 담당.**

## 사이클 구조

```
Phase 1 (첫 프레임):
  [코드] detect_background + extract_blobs + auto_tag → phase 전환

Phase 2~4 (시퀀스 실행 중이 아닐 때):
  PLANNER(코드) → DECIDE(VLM+이미지) → EXECUTE
  → [코드] blob diff + 이벤트 감지
      ├─ split/merge/appear → REDEFINE(VLM: 영향 blob만)
      └─ disappear         → is_present=false (코드)
  → ANALYZE(코드: pending_sequence 기반) → OBSERVE(VLM) → EVALUATE(VLM) → UPDATE(VLM)

Phase 2~4 (시퀀스 실행 중일 때):
  EXECUTE → [코드] diff+이벤트 → 자동 재분류
  → ANALYZE(코드)
  ├─ pending_sequence 있음: 다음 action 실행
  └─ pending_sequence 없음: mark_plan(done) → OBSERVE → EVALUATE → UPDATE → PLANNER → DECIDE
```

### 호출 순서

| Phase | 순서 | 호출 | 담당 | 역할 |
|-------|------|------|------|------|
| **Phase 1** | 1 | blob 추출 | 코드 | detect_background + extract_blobs. obj_NNN 키 부여. HUD 자동 태깅. phase 전환. |
| **Phase 2** | 1 | PLANNER | 코드 | plans 리스트에서 pending 중 가장 우선 plan 선택. status → active. |
| **Phase 2** | 2 | DECIDE | VLM+이미지 | current_subgoal + objects(bbox 포함) + 이미지 → action_sequence (최대 6개). |
| **Phase 2** | 3 | EXECUTE | 코드 | pending_sequence에서 action 1개 pop 후 env.step(). |
| **Phase 2** | 4 | diff+이벤트 | 코드 | 각 애니메이션 프레임 쌍마다: (1) 카메라 shift 감지(SSE) → (2) blob bbox 보정 → (3) 오브젝트 이동 delta 계산. 이벤트 merge 후 ANALYZE에 전달. |
| **Phase 2** | 5 | REDEFINE | VLM+이미지 | split/merge/appear 시만. 영향 blob의 name/type_hypothesis 재부여. |
| **Phase 2** | 5.5 | 자동 재분류 | 코드 | move 이벤트 발생한 blob 중 type=unknown/obstacle → controllable 자동 재분류. |
| **Phase 2** | 6 | ANALYZE | 코드 | `pending_sequence` 남아있으면 continue(next action), 비었으면 done → mark_plan + OBSERVE. VLM 호출 없음. |
| **Phase 2** | 7 | OBSERVE | VLM | before/after 이미지 비교. 이벤트 없고 이미지 동일 시 NO-CHANGE SHORTCUT으로 즉시 반환. |
| **Phase 2** | 8 | EVALUATE | VLM | observe_result + current_subgoal → goal_achieved, reasoning, key_learnings, new_discoveries 반환. |
| **Phase 2** | 9 | UPDATE | VLM | EVALUATE 결과 + discoveries → world_model + summary 갱신. |

## PLANNER

코드만. LLM 호출 없음. `world_model.plans`에서 `status=pending` 중 priority 가장 낮은 것 선택.
pending 없으면 UPDATE에서 새 plan 생성 트리거.

## DECIDE

입력: `current_subgoal` + objects(bbox 포함) + 이미지 + **ACTION HISTORY** (최근 20 스텝 `action → observation`).
**game goal / goal_hypotheses 없음** — 순수 경로/상호작용 계획만.
출력: `action_sequence` (최대 6개).
click: **`["click", "obj_id"]`** 형식 (`obj_003` 등 instance_id 사용). `"click"` 단독 문자열 금지. name 사용 금지.

## ANALYZE (코드, VLM 호출 없음)

`pending_sequence` 기반 단순 판정. LLM 없음.

| 조건 | 결과 |
|------|------|
| `pending_sequence` 항목 남아있음 | continue — 다음 action 실행 |
| `pending_sequence` 비어있음 | done — `mark_plan(done)` → UPDATE → PLANNER → DECIDE |

## EVALUATE

시퀀스 완료 시 OBSERVE 직후 호출.
입력: observe_result + current_subgoal (description, success_condition, failure_condition) + planned_sequence.
출력: `goal_achieved`, `reasoning`, `key_learnings`, `new_discoveries`.

## UPDATE

EVALUATE 직후 호출. EVALUATE 결과(evaluation) + discoveries + INCIDENT 결과 함께 전달.
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
- HUD: 가장자리 blob → step_counter/score/hud 라벨. 액션 대상 제외
- No Fallback: 에러 시 RuntimeError. 조용한 대체 금지.
