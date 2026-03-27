# Experiment Log

## TODO

- [ ] Qwen3-8B 테스트 (Phase System + <think> 파싱 + 1액션 + Phase 1 버그 수정)
- [ ] 배경 자동 감지 (값 분포 통계 → OBSERVE 힌트)
- [ ] VLM 병행 (형태 인식)

## 아이디어

### EVALUATE/UPDATE에 grid가 필요한가?
OBSERVE가 "뭐가 바뀌었는지"를 요약해주면, EVALUATE/UPDATE는 OBSERVE 결과만 보고 판단 가능.
grid를 빼면 토큰 ~8000자 절약 (64x64 hex 2장).
하지만 OBSERVE가 놓친 변화를 EVALUATE가 못 잡을 수도 있음.
→ 실험 필요: grid 있을 때 vs 없을 때 성능 비교

### diff grid 표현
LLM이 64x64 텍스트 두 개를 비교하는 건 거의 불가능.
대신 프레임을 before/after 튜플로 표현:

```
grid_diff -> [[(prev_val, after_val), (prev_val, after_val), ...], ...]
```

변하지 않은 셀은 단일 값, 변한 셀은 (before, after) 튜플로.
이러면 LLM이 한 그리드만 보면서 "어디가 변했는지" 바로 알 수 있음.

예: `"44(4c)44"` → 가운데 셀이 4→c로 변함

또는 코드가 diff를 계산해서 요약만 전달하는 방법도 있음:
```
DIFF: 52 cells changed, mainly in rows 30-50 cols 20-40
  3→c: 12 cells, c→5: 15 cells, 5→3: 8 cells
```

→ 실험해서 어떤 방식이 8B 모델에 효과적인지 비교 필요

## 관찰

### 2026-03-27

#### Qwen3-8B <think> 파싱 문제
- Qwen3-8B가 `<think>...</think>` 태그로 추론 과정을 출력
- max_tokens가 부족하면 think에서 토큰을 다 소진해서 JSON 미도달
- 해결: max_tokens 무제한 + parse.py에서 `</think>` 뒤 내용만 파싱

#### 프롬프트 bias 문제
- "player", "move to row 45 col 30" 같은 specific example이 LLM을 bias시킴
- "캐릭터가 있다"는 가정 자체가 bias — 클릭 기반 게임일 수도
- 해결: JSON 구조만 `"..."`로 보여주고, 게임 유형 가정하는 용어 금지

#### 배경 vs 오브젝트 구분
- 가장 많은 값 = 배경이라는 가정이 위험 (벽일 수도)
- 같은 색이 다른 오브젝트일 수 있고, 한 오브젝트가 여러 색일 수 있음
- 결론: 코드는 값 분포만 전달, LLM이 판단

#### 레벨 전환 시 confidence
- 고정 비율(/2 등)보다 LLM이 OBSERVE에서 판단하는 게 유연
- 게임마다 레벨 간 차이가 다르므로

## 이전 테스트 결과

### Anthropic Sonnet (ls20, 30스텝)
- 레벨 클리어: 0
- LLM 호출: 22회
- 입력 토큰: 57,791
- CoT가 작동하긴 했지만 게임 규칙 파악 실패
- "52 changes" 같은 무의미한 숫자에 집착하는 문제

### Anthropic Haiku (ls20)
- 대부분 파싱 실패
- 작은 모델에서 시퀀스 출력 불안정
- → 1액션 구조로 전환하는 계기
