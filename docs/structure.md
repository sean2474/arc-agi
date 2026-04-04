# Code Structure Registry

## src/agent/
- `base.py` — 에이전트 추상 인터페이스
  - `GameState` dataclass — 구조화된 게임 상태
  - `AgentResponse` dataclass — 에이전트 액션 선택 결과
  - `Agent` ABC — choose_action(), on_episode_start(), on_episode_end()
- `llm_agent.py` — LLM 기반 에이전트 (단순 매 스텝)
  - `LLMAgent(Agent)` — AnthropicClient + PromptBuilder로 액션 선택
- `vlm_agent.py` — VLM 기반 에이전트 (이미지 + 단일 액션)
  - `VLMAgent(Agent)` — 매 스텝 프레임 이미지로 액션 선택
- `pao_agent.py` — Planner-Actor-Observer 에이전트
  - `PAOAgent(Agent)` — Planner(subgoal 설정) + Actor(액션 실행) + Observer(변화 감지)

## src/env/
- `game_runner.py` — 에이전트로 게임 플레이 루프
  - `EpisodeResult` dataclass — 에피소드 결과
  - `GameRunner` — run(game_id) → EpisodeResult
- `state_extractor.py` — 게임 프레임에서 구조화된 상태 추출
  - `StateExtractor` ABC — extract(GameState) → dict
  - `DefaultExtractor` — 기본 (색상 분포만)
  - `Ls20Extractor` — ls20 전용 (플레이어, 도구, 슬롯, 맵)
- `observer.py` — 프레임 변화 관찰 (코드 기반, LLM 없음)
  - `Observation` dataclass — 이동/차단/도구변경/슬롯클리어/리셋 등
  - `Observer` — observe(extracted) → Observation

## src/llm/
- `client.py` — Anthropic API 래퍼
  - `LLMResponse` dataclass — 응답 + 토큰 사용량
  - `AnthropicClient` — send(), get_cost_estimate(), get_usage_summary()
- `prompt_builder.py` — 게임 상태 → 프롬프트 변환
  - `PromptBuilder` ABC — build_system(), build_user_message()
  - `Ls20PromptBuilder` — ls20 전용 프롬프트
- `vlm_prompt_builder.py` — VLM용 프롬프트 (이미지 포함)
  - `Ls20VLMPromptBuilder` — 프레임 이미지 + 상태 텍스트
- `pao_prompts.py` — Planner-Actor-Observer 프롬프트
  - `PLANNER_SYSTEM` — subgoal 생성용 시스템 프롬프트
  - `ACTOR_SYSTEM` — 단일 액션 선택용 시스템 프롬프트
  - `build_planner_message()`, `build_actor_message()`
- `frame_renderer.py` — 프레임을 PNG 이미지로 변환
  - `frame_to_base64()` — API 전송용 base64 인코딩

## src/experiment/
- `tracker.py` — 실험 추적
  - `ExperimentTracker` — record_episode(), save(), list_experiments()
