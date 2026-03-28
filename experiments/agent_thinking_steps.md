# Thinking Process — 각 단계별 설명

## 모델 구성

단일 VLM 구조 (32GB VRAM 제약).

| 역할 | 모델 | 용도 |
|------|------|------|
| VLM | Qwen2.5-VL-7B | 전체 단계. SCAN/OBSERVE는 이미지+텍스트, 나머지는 텍스트만. |

VLM은 이미지도, 텍스트만도 처리 가능. SCAN/OBSERVE에 이미지 추가 전달.

## 전체 흐름

```
Phase 1 (첫 프레임):
  SCAN(VLM+이미지) → HYPOTHESIZE(VLM) → UPDATE(VLM) → phase 전환

Phase 2~4 (매 스텝):
  DECIDE(VLM) → EXECUTE → OBSERVE(VLM+이미지) → EVALUATE(VLM) → UPDATE(VLM)
```

---

## SCAN (Phase 1 전용) — VLM 사용

"여기 뭐가 있지?" — 아무것도 모르는 상태에서 전체 프레임을 처음 분석.

- 모델: **VLM (Qwen2.5-VL-7B)**
- 입력: grid를 **좌표 오버레이 이미지**로 렌더링해서 전달
  - 64x64 hex → 512x512px 이미지 + 8셀마다 row/col 번호 레이블
  - LLM이 픽셀 좌표와 그리드 셀 좌표를 혼동하는 할루시네이션 방지
- 목적: 화면에 있는 모든 오브젝트를 시각적으로 파악
- VLM이 하는 일:
  - 이미지에서 구분 가능한 오브젝트/영역 식별
  - 각각의 색(**ARC index**: `0`=white, `e`=green 등), 위치, 크기, 모양 기록
  - 전체 구조 파악 (사각형, 통로, 경계, 패턴 등)
  - **같은 역할의 오브젝트는 반드시 하나로 통합** — 동일 색/모양이 여러 개라도 같은 역할이면 1개 항목으로 전체 bbox 반환
- 하지 않는 일:
  - 판단, 의도, 액션 제안 금지
  - 뭐가 뭔지 추측 금지 (전부 type: "unknown")
- 출력: objects **배열** (LLM이 list로 반환) + patterns
  - 코드가 `obj_001`, `obj_002`... 키를 자동 부여 (LLM이 ID 관리 불필요)
- 후처리 (코드):
  - position/size → bbox 계산
  - **유효성 검증**: position이 그리드 범위(0~63) 초과 → `RuntimeError`
  - **색상 검증**: bbox 영역에 해당 ARC color index가 없으면 → `RuntimeError`
  - 검증 실패 = LLM 할루시네이션 → 즉시 에러, fallback 없음
- **HUD 감지**: 화면 극단 모서리/가장자리 오브젝트는 거의 확실히 HUD (step_counter, score). LLM이 `name: step_counter/score/hud`로 표기. 게임 액션 대상 아님.

왜 VLM인가:
- 텍스트 LLM은 64x64 hex 배열에서 오브젝트를 정확히 못 뽑음
- VLM은 이미지를 직접 보므로 형태/위치 파악이 정확
- 좌표 오버레이로 셀 번호를 이미지에서 직접 읽을 수 있게 함

**VLM 호출 설정**: `thinking_budget=4096`. SCAN은 thinking이 중요하지만 무한 루프 방지를 위해 예산 제한.

---

## HYPOTHESIZE (Phase 1, SCAN 직후)

"이것들이 뭘 의미할까?" — SCAN 결과를 보고 초기 가설 수립.

- 입력: SCAN 결과 (objects + patterns) + available_actions
- 목적: 각 오브젝트의 역할 추측 + 게임 타입 추측 + win condition 초기 가설
- 하는 일:
  - 각 오브젝트에 대해 type_hypothesis 추측 (배경? 벽? 조작 가능? 목표? 위험?)
  - 게임 타입 추측 (네비게이션? 퍼즐? 클릭 기반? 패턴 매칭?)
  - win condition 초기 가설 (뭘 해야 이길 수 있을지)
  - 어떤 액션을 먼저 테스트해야 하는지 우선순위 제안
  - 시각적 배치로 오브젝트 간 관계 초기 가설 수립 (`relationships`, confidence 0.3)
    - 예: 이동 경로에 위치한 오브젝트 → "blocks or kills" 가설
  - 전부 confidence 낮음 (0.3) — 검증 전이므로
- 하지 않는 일:
  - 액션 결정 (DECIDE의 역할)
  - 확정적 판단 — 전부 가설일 뿐
- 출력: type_hypothesis 업데이트 + game_type 가설 + goal 가설 + relationships 초기 가설 + 탐색 우선순위

---

## OBSERVE (Phase 2+) — VLM 사용

"뭐가 바뀌었지?" — 이미 오브젝트를 알고 있는 상태. 액션 실행 후 변화 관찰.

- 모델: **VLM (Qwen2.5-VL-7B)**
- 입력: before/after **이미지 2장** (world_model 오브젝트 bbox outline + label 어노테이션 포함) + world_model + 코드 diff 요약
- 목적: 시각적으로 뭐가 바뀌었는지 파악 + diff 요약과 대조
- VLM이 하는 일:
  - before/after 이미지를 비교해서 변화를 시각적으로 식별
  - 코드 diff 요약을 참고해서 어떤 오브젝트가 영향받았는지 판단
  - 움직인 것 = dynamic, 안 움직인 것 = static 분류
  - 새로 나타난 오브젝트 감지
  - passive 이벤트 감지 → `relationships` 업데이트
    - 예: 오브젝트 A 근처에서 game_over → A의 `interaction_result` 채움
    - 예: 오브젝트 B에 올라갔더니 오브젝트 C가 사라짐 → 새 relationship 추가
- 하지 않는 일:
  - 전체 프레임 분석 (SCAN의 역할)
  - 판단/의도 금지
- 출력: changes + 오브젝트 분류 업데이트 + new_objects + relationship_updates + contradictions

VLM + 코드 diff 병행 이유:
- VLM이 시각적 변화를 직관적으로 잡고
- 코드 diff가 정확한 셀 단위 변화를 보완
- 둘을 함께 주면 더 정확한 관찰 가능

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

- 입력: `current_subgoal` + OBSERVE 결과 + objects(위치/bbox 포함, 같은 색상/모양이어도 좌표로 구분) + **bbox 어노테이션 이미지**
- 목적: 서브골 달성을 위한 **action sequence** 계획
- **game goal / goal_hypotheses / reports 입력 없음** — 순수 경로/상호작용 계획만
- 하는 일:
  - 이미지와 object 위치를 보고 경로 계산
    - 예: player(3,5) → target(3,10), 중간 벽(col 7) → 우회 경로
  - 최대 6개 action의 sequence 계획
  - 각 action의 기대 효과 추론
- 하지 않는 일:
  - 게임 목표 판단 (Planner의 역할)
  - 관찰 (OBSERVE의 역할)
  - 1개 초과 sequence 금지 → 최대 6개
- 출력:
  ```json
  {
    "reasoning": "player at (3,5), target at (3,10), wall at col 7. detour: right×2, down×1, right×2",
    "action_sequence": ["right", "right", "down", "right", "right"],
    "subgoal": "reach blue object at (3,10)"
  }
  ```
  click 액션이 필요한 경우:
  ```json
  {
    "reasoning": "need to click on platform at bbox row 46-47, col 33-37",
    "action_sequence": [["click", "platform"], "right"],
    "subgoal": "activate platform"
  }
  ```
  - click 아이템은 **배열** `["click", "obj_name"]` 형식 — 일반 액션 문자열과 혼용 금지
  - `"click"` 단독 문자열은 유효하지 않음 → `RuntimeError`

---

## EXECUTE

- 코드에서 처리 (LLM 호출 없음)
- env.step(action) 실행
- before/after frame 저장

---

## ACTION ANALYZER (VLM)

- 입력: `planned_sequence` + `executed_action` + OBSERVE 결과 + `current_subgoal`
- 목적: 방금 실행된 1개 액션이 계획대로 됐는지 판정 + 시퀀스 계속 여부 결정
- 하는 일:
  - OBSERVE 결과가 기대와 일치하는지 확인
  - 예상 밖 변화(적 이동, 오브젝트 소멸 등) 감지 → abort 트리거
  - 서브골 달성 여부 판정
  - 배운 것 정리 (discoveries)
- 하지 않는 일:
  - grid 원본 비교 (OBSERVE가 이미 했음)
  - 다음 액션 계획 (DECIDE의 역할)
  - 합리화 금지 — 실패하면 실패라고 정직하게
- 출력:
  ```json
  {
    "status": "continue | abort | success",
    "reason": "...",
    "discoveries": [...]
  }
  ```
  - `continue`: sequence 다음 action 실행
  - `abort`: 예상 밖 변화 → pending_sequence 초기화 → Planner에서 re-plan
  - `success`: 서브골 달성 → plan을 `done`으로 → Planner에서 다음 plan 선택

---

## UPDATE

- 입력: world_model + EVALUATE report + discoveries + (INCIDENT 결과)
- 목적: world_model과 summary를 갱신
- 하는 일:
  - action confidence 갱신 (테스트 결과 반영)
  - objects 상태 업데이트 (위치, type, interaction_tested)
  - interactions 추가/제거
  - relationships 갱신
    - OBSERVE에서 감지된 passive 이벤트 → `interaction_result` 채움, confidence 상승
    - 반증된 relationship → confidence 낮춤 또는 제거
  - dangers 추가
  - 방향키: 1개 테스트 결과로 나머지 3개 추론
  - plans 갱신 (새 서브골 추가, done/failed 정리)
- 하지 않는 일:
  - 관찰 (OBSERVE의 역할)
  - 판단 (EVALUATE의 역할)
- 출력: updated_summary + updated_world_model

---

## INCIDENT (특수)

- game_over 또는 level_complete 시에만 호출
- EVALUATE 전에 실행
- 목적: 사건 원인 분석
  - game_over: 뭐가 원인이었는지, 어떻게 피할 수 있는지
  - level_complete: 뭐가 트리거였는지, 다음 레벨에도 적용 가능한지
- 출력: incident_result → EVALUATE와 UPDATE에 전달
