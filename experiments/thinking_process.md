# Thinking Process — 각 단계별 설명

## 전체 흐름

```
Phase 1 (첫 프레임):
  SCAN → UPDATE → phase 전환

Phase 2~4 (매 스텝):
  DECIDE → EXECUTE → OBSERVE → EVALUATE → UPDATE
```

---

## SCAN (Phase 1 전용)

"여기 뭐가 있지?" — 아무것도 모르는 상태에서 전체 프레임을 처음 분석.

- 입력: current frame만 (이전 프레임 없음)
- 목적: 화면에 있는 모든 오브젝트를 처음으로 파악
- 프롬프트 구조:
  ```
  STEP 1 - OBJECTS: 모든 구분 가능한 오브젝트/영역 나열
    각각: hex 값, 색 이름, 위치(row/col 범위), 크기, 모양
  STEP 2 - PATTERNS: 전체 구조 파악
    사각형, 통로, 경계, 반복 패턴 등
  ```
- 하지 않는 일:
  - 판단, 의도, 액션 제안 금지
  - 뭐가 뭔지 추측 금지 (전부 type: "unknown")
  - DIFF/CLASSIFY/CHALLENGE 없음 (비교할 프레임이 없으므로)
- 출력: objects 딕셔너리 + patterns

---

## OBSERVE (Phase 2+ 전용)

"뭐가 바뀌었지?" — 이미 오브젝트를 알고 있는 상태. 액션 실행 후 **변화만** 관찰.

- 입력: before frame + after frame + world_model(기존 objects 포함)
- 목적: 방금 실행한 액션으로 뭐가 바뀌었는지 확인
- 프롬프트 구조:
  ```
  STEP 1 - DIFF: before/after 비교
    어떤 셀이 변했는지, 어떤 오브젝트가 움직였는지
    사라진 것, 새로 나타난 것
  STEP 2 - CLASSIFY: 움직인 것 = dynamic, 안 움직인 것 = static
  STEP 3 - NEW OBJECTS: 이전에 없던 새 오브젝트가 있으면 기록
  STEP 4 - CHALLENGE: 관찰 결과에 대한 반박
    static으로 분류한 것이 실제로는 dynamic일 수도?
  ```
- 하지 않는 일:
  - 이미 알고 있는 오브젝트를 처음부터 다시 나열
  - 전체 프레임 분석 (SCAN의 역할)
  - 판단/의도 금지
- 출력: changes + 오브젝트 분류 업데이트 + new_objects + contradictions

### SCAN vs OBSERVE 비교

| | SCAN (Phase 1) | OBSERVE (Phase 2+) |
|---|---|---|
| **언제** | 첫 프레임, 새 레벨 시작 | 매 액션 실행 후 |
| **입력** | current frame만 | before + after frame |
| **초점** | 전체 오브젝트 추출 | 변화 감지 |
| **CoT** | OBJECTS + PATTERNS | DIFF + CLASSIFY + NEW + CHALLENGE |
| **출력** | objects 딕셔너리 | changes + 분류 업데이트 |

---

## DECIDE

- 입력: world_model + reports + phase hint
- 목적: 다음에 할 1개 액션을 결정
- 하는 일:
  - world_model의 confidence를 보고 가장 정보가 부족한 곳을 우선 탐색
  - Phase에 따라 다른 전략:
    - Phase 2 (action_discovery): untested action 테스트
    - Phase 3 (interaction_discovery): 오브젝트에 접근/작용 시도
    - Phase 4 (goal_execution): 목표 달성 전략 실행
  - goal + success_condition + failure_condition 명시
- 하지 않는 일:
  - 여러 액션 한번에 출력 (항상 1개만)
  - 관찰 (OBSERVE의 역할)
- 출력: action (1개) + goal + success/failure condition + win_condition_hypothesis

---

## EXECUTE

- 코드에서 처리 (LLM 호출 없음)
- env.step(action) 실행
- before/after frame 저장

---

## EVALUATE

- 입력: before/after frame + OBSERVE 결과 + goal + success/failure condition
- 목적: 방금 실행한 액션의 결과를 평가
- 하는 일:
  - goal 달성 여부 판정 (success_condition / failure_condition 기준)
  - 예상 밖 변화 감지
  - 배운 것 정리 (key_learnings)
  - 새로운 발견 (discoveries) 추출
- 하지 않는 일:
  - 다음 액션 계획 (DECIDE의 역할)
  - world_model 갱신 (UPDATE의 역할)
  - 합리화 금지 — 실패하면 실패라고 정직하게
- 출력: report (goal_achieved, reasoning, key_learnings) + discoveries

---

## UPDATE

- 입력: world_model + EVALUATE report + discoveries + (INCIDENT 결과)
- 목적: world_model과 summary를 갱신
- 하는 일:
  - action confidence 갱신 (테스트 결과 반영)
  - objects 상태 업데이트 (위치, type, interaction_tested)
  - interactions 추가/제거
  - dangers 추가
  - 방향키: 1개 테스트 결과로 나머지 3개 추론
  - immediate_plan / strategic_plan 갱신
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
