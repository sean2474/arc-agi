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

단일 VLM으로 전체 단계 처리. SCAN/OBSERVE는 이미지 + 텍스트 입력, 나머지는 텍스트만.
32GB VRAM 제약으로 단일 모델 사용.

## 사이클 구조

```
Phase 1 (static_observation):
  SCAN(VLM+이미지) → HYPOTHESIZE(VLM) → UPDATE(VLM) → phase 전환
  DECIDE/EXECUTE 없음.

Phase 2~4:
  DECIDE(VLM) → EXECUTE → OBSERVE(VLM+이미지) → EVALUATE(VLM) → UPDATE(VLM)
```

자세한 설명은 thinking_process.md 참고.

### 호출 순서

| Phase | 순서 | 호출 | 모델 | 역할 |
|-------|------|------|------|------|
| **Phase 1** | 1 | SCAN | VLM+이미지 | 이미지로 전체 프레임 분석. objects + position 추출. 코드가 value로 그리드 스캔해 bbox 계산. |
| **Phase 1** | 2 | HYPOTHESIZE | VLM | 초기 가설 수립. 오브젝트 역할/게임타입/목표 추측. |
| **Phase 1** | 3 | UPDATE | VLM | objects + 가설을 world_model에 저장. |
| **Phase 2~4** | 1 | DECIDE | VLM | 1개 액션 결정. world_model 기반. |
| **Phase 2~4** | 2 | (EXECUTE) | 코드 | env.step(action) 실행. |
| **Phase 2~4** | 3 | OBSERVE | VLM+어노테이션 이미지 | before/after 이미지(bbox outline+label 포함) 비교 + 코드 diff 요약. |
| **Phase 2~4** | 4 | EVALUATE | VLM | OBSERVE 결과로 목표 달성 여부 판정. |
| **Phase 2~4** | 5 | UPDATE | VLM | world_model 갱신. confidence 조정. |

## DECIDE

1개 액션만 반환. phase hint를 코드가 전달.
click은 좌표가 아니라 object instance_id를 대상으로.

`relationships` 활용:
- `interaction_result: null`인 relationship → 테스트 우선 (info_gain 높음)
- 위험 관계 확인된 오브젝트 근처 → 위험도 높음 (death_risk 상승)

## EVALUATE

OBSERVE 결과만으로 판단. grid 원본 없음. VLM이 독립적으로 재분석하지 않음.

## UPDATE

EVALUATE report + discoveries로 world_model 갱신. grid 원본 없음.
`relationships` 갱신: OBSERVE 결과에서 passive 이벤트 반영 → `interaction_result` 채움, confidence 조정.

## INCIDENT

game_over 또는 level_complete 시에만 호출.
게임 유형을 가정하는 용어 사용하지 않음.

## 프롬프트 원칙

- specific한 example 금지 — bias
- JSON 구조만 "..."로
- 게임 유형을 가정하는 용어 금지
- goal이 좌표라는 가정 금지
