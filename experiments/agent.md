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

## 사이클 구조

```
Phase 1 (static_observation):
  SCAN → HYPOTHESIZE → UPDATE → phase 전환
  DECIDE/EXECUTE 없음.

Phase 2~4:
  DECIDE(1액션) → EXECUTE → OBSERVE(변화 관찰) → EVALUATE → UPDATE
```

자세한 설명은 thinking_process.md 참고.

### LLM 호출

| Phase | 순서 | 호출 | 역할 |
|-------|------|------|------|
| **Phase 1** | 1 | SCAN | 전체 프레임 분석. objects 추출. |
| **Phase 1** | 2 | HYPOTHESIZE | 초기 가설 수립. 오브젝트 역할/게임타입/목표 추측. |
| **Phase 1** | 3 | UPDATE | objects + 가설을 world_model에 저장. |
| **Phase 2~4** | 1 | DECIDE | 1개 액션 결정. world_model 기반. |
| **Phase 2~4** | 2 | (EXECUTE) | 코드가 env.step(action) 실행. |
| **Phase 2~4** | 3 | OBSERVE | 변화 관찰. 뭐가 바뀌었는지만. |
| **Phase 2~4** | 4 | EVALUATE | 목표 달성 여부 판정. |
| **Phase 2~4** | 5 | UPDATE | world_model 갱신. confidence 조정. |

## DECIDE 프롬프트

1개 액션만 반환. phase hint를 코드가 전달.

응답: action + goal + success_condition + failure_condition + win_condition_hypothesis

### click+object

click은 좌표가 아니라 object를 대상으로.
코드가 object의 position에서 좌표를 자동 계산.

## EVALUATE+UPDATE 프롬프트 (Phase 2+ 전용)

기존 EVALUATE와 UPDATE를 합침. 한 번의 LLM 호출로:
1. before/after 비교 → 뭐가 변했는지
2. 목표 달성 여부 판정
3. world_model 갱신 (objects 위치, action confidence, interactions 등)
4. 새 오브젝트 감지 → 탐색 우선순위 조정

```
STEP 1 - CHANGES: 뭐가 바뀌었는지
STEP 2 - GOAL CHECK: 성공/실패
STEP 3 - NEW OBJECTS: 이전에 없던 새 오브젝트 감지 시 주의
STEP 4 - WORLD MODEL UPDATE: confidence 갱신, interactions 추가/제거
```

## INCIDENT 프롬프트

game_over 또는 level_complete 시에만 호출.
게임 유형을 가정하는 용어 사용하지 않음.

## 프롬프트 원칙

- specific한 example 금지 — bias
- JSON 구조만 "..."로
- 게임 유형을 가정하는 용어 금지
- goal이 좌표라는 가정 금지
