# Experiment Log

## TODO

- [ ] Qwen3-8B 테스트 (Phase System + <think> 파싱 + 1액션 + Phase 1 버그 수정)
- [ ] 배경 자동 감지 (값 분포 통계 → OBSERVE 힌트)
- [ ] VLM 병행 (형태 인식)

## 아이디어

### EVALUATE/UPDATE에 grid 제거 결정
OBSERVE에 코드가 계산한 diff 요약을 전달하고, EVALUATE/UPDATE는 OBSERVE 결과만 사용.
grid 원본은 SCAN에서만 사용 (첫 프레임 전체 분석).
이유: 8B 모델이 64x64 hex 문자열 비교 불가능 → "no changes detected" 반복 문제.

### [해결 필요] LLM이 64x64 grid diff를 못 잡는 문제
8B 모델이 4096자 hex 문자열 두 개를 텍스트로 비교하는 건 불가능.
실제로 변화가 있는데 "no changes detected"라고 계속 반복.
→ 코드가 diff를 계산해서 OBSERVE 프롬프트에 요약으로 전달해야 함.

### [핵심 문제] 텍스트 LLM이 64x64 grid를 제대로 못 읽음
SCAN도 품질이 낮음 — 오브젝트 추출 부정확 (위치/값 불일치, 의미없는 오브젝트 생성)
OBSERVE도 변화를 못 잡음 — "no changes detected" 반복
원인: 8B 텍스트 모델이 4096자 hex 배열을 시각적으로 이해하는 건 한계.

### CNN + LLM 하이브리드 아이디어

Stochastic Goose (CNN 기반 랜덤 탐색)가 25% 달성.
런타임 29초로 110게임 처리. "변화량이 큰 액션"을 찾는 단순 전략.

이걸 LLM과 결합하면:
- Phase A (CNN 빠른 탐색, ~30초): 각 액션을 빠르게 시도, action→effect map 수집
  - 어떤 액션이 프레임을 바꾸는지, game_over/level_complete 이벤트 수집
- Phase B (LLM 규칙 해석, 1~2번 호출): CNN이 수집한 데이터를 한번에 전달
  - "up → 이 영역 변화, game_over가 이때 발생" → LLM이 규칙/goal 해석
- Phase C (LLM guided play): LLM 전략 + CNN 빠른 실행
  - 필요할 때만 LLM 재호출

시간 예산: 게임당 ~90초 → 110게임 = ~2.7시간. 6시간 여유.
LLM 호출 수가 극적으로 줄어듦 (매 스텝 4회 → 게임당 2~3회).

기존 구조(매 스텝 LLM 4회)와의 차이:
- 기존: 스텝당 60-120초 → 게임당 2-3스텝밖에 못 함
- CNN 하이브리드: 탐색은 CNN이 빠르게, LLM은 해석만

### VLM 사용 방안
SCAN과 OBSERVE에 VLM 사용. DECIDE/EVALUATE/UPDATE는 텍스트 LLM 유지.
- grid를 이미지로 렌더링 (64x64 pixel → 확대)
- SCAN: VLM에게 이미지 보여주고 오브젝트 추출
- OBSERVE: before/after 이미지 2장으로 변화 관찰
- 순차 실행이면 GPU 메모리 문제 없음 (VLM 먼저, 언로드, 텍스트 LLM 로드)
- 또는 작은 VLM(Qwen2-VL-2B 등)이면 동시에 올려도 가능

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
