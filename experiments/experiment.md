# Experiment Log

## TODO

- [ ] Qwen3-8B 첫 테스트 (Phase System + <think> 파싱 + 1액션)
- [ ] 배경 자동 감지 (값 분포 통계 → OBSERVE 힌트)
- [ ] VLM 병행 (형태 인식)

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
