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
| VLM | Qwen2.5-VL-7B | 전체 단계 (SCAN, OBSERVE, HYPOTHESIZE, DECIDE, EVALUATE, UPDATE) |

단일 VLM으로 전체 단계 처리. SCAN/OBSERVE/DECIDE는 이미지 + 텍스트 입력, 나머지는 텍스트만.
32GB VRAM 제약으로 단일 모델 사용.

## 사이클 구조

```
Phase 1 (static_observation):
  SCAN(VLM+이미지) → HYPOTHESIZE(VLM) → UPDATE(VLM) → phase 전환
  DECIDE/EXECUTE 없음.

Phase 2~4 (시퀀스 실행 중이 아닐 때):
  PLANNER(코드) → DECIDE(VLM+이미지) → EXECUTE → OBSERVE(VLM+이미지) → ACTION ANALYZER(VLM) → UPDATE(VLM)

Phase 2~4 (시퀀스 실행 중일 때):
  EXECUTE → OBSERVE(VLM+이미지) → ACTION ANALYZER(VLM)
  ├─ continue: 다음 action 실행
  ├─ abort: UPDATE(VLM) → PLANNER → DECIDE (re-plan)
  └─ success: UPDATE(VLM) → PLANNER (plan done, 다음 plan)
```

자세한 설명은 thinking_process.md 참고.

### 호출 순서

| Phase | 순서 | 호출 | 모델 | 역할 |
|-------|------|------|------|------|
| **Phase 1** | 1 | SCAN | VLM+이미지 | 이미지로 전체 프레임 분석. objects + position 추출. 코드가 value로 그리드 스캔해 bbox 계산. |
| **Phase 1** | 2 | HYPOTHESIZE | VLM | 초기 가설 수립. 오브젝트 역할/게임타입/목표 추측. |
| **Phase 1** | 3 | UPDATE | VLM | objects + 가설을 world_model에 저장. |
| **Phase 2~4** | 1 | PLANNER | 코드 | plans 리스트에서 pending 중 가장 우선 plan 선택. status → active. |
| **Phase 2~4** | 2 | DECIDE | VLM+이미지 | current_subgoal + obs + objects + 이미지 → action_sequence (최대 6개). |
| **Phase 2~4** | 3 | (EXECUTE) | 코드 | pending_sequence에서 action 1개 pop 후 env.step(). |
| **Phase 2~4** | 4 | OBSERVE | VLM+어노테이션 이미지 | before/after 이미지(bbox outline+label 포함) 비교 + 코드 diff 요약. |
| **Phase 2~4** | 5 | ACTION ANALYZER | VLM | continue/abort/success 판정. abort 시 re-plan 트리거. |
| **Phase 2~4** | 6 | UPDATE | VLM | abort/success 시만. world_model + plans 갱신. |

## PLANNER

코드만. LLM 호출 없음. `world_model.plans`에서 `status=pending` 중 priority 가장 낙은 것 선택.
pending 없으면 UPDATE에서 새 plan 생성 트리거.

## DECIDE

입력: `current_subgoal` + OBSERVE 결과 + objects + 이미지. 
**game goal / goal_hypotheses 없음** — 순수 경로/상호작용 계획만.
이미지와 object bbox로 경로 계산 → action_sequence (최대 6개) 반환.
click: `["click", "obj_id"]` 형식.

## ACTION ANALYZER

OBSERVE 결과 + 계획된 sequence 증거 → `continue / abort / success` 판정.
- **continue**: 다음 action 그대로 실행
- **abort**: 예상 밖 변화 → pending_sequence 초기화 → UPDATE → Planner re-plan
- **success**: 서브골 달성 → plan `done` → UPDATE → Planner 다음 plan

## UPDATE

Action Analyzer discoveries + (INCIDENT)로 world_model 갱신. abort/success 시만 호출.
`plans` 갱신: abort → plan 수정 또는 새 plan 추가. success → done 마킹.

## INCIDENT

game_over 또는 level_complete 시에만 호출.
게임 유형을 가정하는 용어 사용하지 않음.

## 프롬프트 원칙

- specific한 example 금지 — bias
- JSON 구조만 "..."로
- 게임 유형을 가정하는 용어 금지
- goal이 좌표라는 가정 금지
