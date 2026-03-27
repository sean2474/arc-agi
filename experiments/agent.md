# Agent Design

## 사이클 구조

매 스텝마다 Phase에 따라 다른 사이클을 실행.

```
Phase 1 (static_observation):
  OBSERVE → UPDATE(objects를 world model에 저장) → phase 전환
  DECIDE/EXECUTE 없음. 액션 실행 안 함.

Phase 2~4:
  OBSERVE → DECIDE(1액션) → EXECUTE → EVALUATE → UPDATE
```

### LLM 호출

| 단계 | 역할 | 핵심 원칙 |
|------|------|----------|
| **OBSERVE** | 뭐가 보이는지 | 관찰만. 판단/의도 금지. CoT 강제 |
| **DECIDE** | 뭘 할지 | 1개 액션만. world_model 기반. 낮은 confidence 우선 |
| **EVALUATE** | 어떻게 됐는지 | 정직한 평가. 합리화 금지 |
| **UPDATE** | 뭘 배웠는지 | summary + world_model confidence 갱신 |

### 왜 OBSERVE와 DECIDE를 분리하는가

- 한 호출에서 관찰+결정 동시 → reasoning이 intent를 오염
- 분리 → OBSERVE는 사실만, DECIDE가 판단

## OBSERVE 프롬프트

CoT 강제. 6단계 추론.

```
STEP 1 - OBJECTS: 모든 구분 가능한 오브젝트/영역 나열
STEP 2 - PATTERNS: 구조 파악 (사각형, 통로, 경계 등)
STEP 3 - DIFF: 이전 프레임과 비교 (변화에 집중)
STEP 4 - CLASSIFY: 움직인 것 = dynamic, 안 움직인 것 = static
STEP 5 - CHALLENGE: 가설 반박 (핵심)
```

응답: objects 딕셔너리 + patterns + changes + contradictions + unknowns

## DECIDE 프롬프트

1개 액션만 반환. phase hint를 코드가 생성해서 전달.

응답: action + goal + success_condition + failure_condition + win_condition_hypothesis

### click+object

click은 좌표가 아니라 object를 대상으로.
코드가 object의 position에서 좌표를 자동 계산.

```
"action": ["click", "object_name"]
→ 코드가 center_of(obj["position"]) → ["click", x, y]
```

## EVALUATE 프롬프트

CoT 강제. 4단계.

```
STEP 1 - COMPARE: before/after 비교
STEP 2 - GOAL CHECK: 성공/실패 판정
STEP 3 - SURPRISES: 예상 밖 변화
STEP 4 - LESSONS: 기억할 것
```

## UPDATE 프롬프트

summary + world_model 둘 다 갱신.
actions, objects는 merge (기존 키 유지).

## INCIDENT 프롬프트

game_over 또는 level_complete 시에만 호출.
specific한 용어("player died" 등) 사용하지 않음.
"game state changed to GAME_OVER" 같이 중립적으로.

## 프롬프트 원칙

- specific한 example 금지 — LLM이 example에 bias됨
- JSON 구조만 보여주고 값은 "..."로
- "player", "character" 등 게임 유형을 가정하는 용어 금지
- goal이 좌표라는 가정 금지
