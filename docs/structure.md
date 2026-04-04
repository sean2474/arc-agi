# Code Structure Registry

## src/agent/
- `base.py` — 에이전트 기본 타입 정의
  - `GameState` dataclass — 구조화된 게임 상태
  - `AgentResponse` dataclass — 에이전트 액션 선택 결과
  - `Agent` Protocol — 에이전트 인터페이스 (구조적 서브타이핑)
- `llm_agent.py` — LLM 기반 에이전트 (단순 매 스텝)
  - `LLMAgent` — LLMClient + PromptBuilder + ResponseParser로 액션 선택
- `vlm_agent.py` — VLM 기반 에이전트 (이미지 + 단일 액션)
  - `VLMAgent` — 매 스텝 프레임 이미지로 액션 선택
- `pao_agent.py` — Planner-Actor-Observer 에이전트
  - `PlannerService` — goal/subgoal 생성 (LLMClient + PlannerResponseParser)
  - `ActorService` — subgoal 방향 단일 액션 선택 (LLMClient + ResponseParser)
  - `PAOAgent` — 조율자: PlannerService, ActorService, Observer를 연결

## src/env/
- `state_extractor.py` — 게임 프레임에서 구조화된 상태 추출
  - `StateExtractor` ABC — extract(GameState) -> dict
  - `DefaultExtractor` — 기본 (색상 분포만)
  - `GameDataAccessor` Protocol — 게임 내부 데이터 접근 인터페이스 (DIP)
  - `Ls20GameAccessor` — ls20 게임 인스턴스를 GameDataAccessor로 래핑
  - `Ls20Extractor` — ls20 전용 (GameDataAccessor를 통해 접근)
- `observer.py` — 프레임 변화 관찰 (코드 기반, LLM 없음)
  - `Observation` dataclass — 이동/차단/도구변경/슬롯클리어/리셋 등
  - `Observer` — observe(extracted) -> Observation

## src/llm/
- `client.py` — Anthropic API 래퍼
  - `LLMResponse` dataclass — 응답 + 토큰 사용량
  - `LLMClient` Protocol — LLM 클라이언트 인터페이스 (DIP)
  - `AnthropicClient` — send(), get_cost_estimate(), get_usage_summary()
- `prompt_builder.py` — 게임 상태 -> 프롬프트 변환
  - `PromptBuilder` ABC — build_system(), build_user_message() -> str | list
  - `Ls20PromptBuilder` — ls20 전용 프롬프트
- `vlm_prompt_builder.py` — VLM용 프롬프트 (이미지 포함)
  - `Ls20VLMPromptBuilder` — 프레임 이미지 + 상태 텍스트
- `pao_prompts.py` — Planner-Actor-Observer 프롬프트
  - `PLANNER_SYSTEM` — subgoal 생성용 시스템 프롬프트
  - `ACTOR_SYSTEM` — 단일 액션 선택용 시스템 프롬프트
  - `build_planner_message()`, `build_actor_message()`
- `response_parser.py` — LLM 응답 파싱 (공통 추출 로직)
  - `ResponseParser` Protocol — 액션 응답 파서 인터페이스
  - `JsonActionParser` — {"thinking": "...", "action": N} 파싱
  - `PlannerResponseParser` — {"subgoals": [...]} 파싱
- `frame_renderer.py` — 프레임을 PNG 이미지로 변환
  - `frame_to_base64()` — API 전송용 base64 인코딩

## src/experiment/
- `tracker.py` — 실험 추적
  - `ExperimentTracker` — record_episode(), save(), list_experiments()

## training/
- `config.py` — 학습 하이퍼파라미터
  - `TrainingConfig` dataclass — 모델, 서버, 학습 루프, reward, RL, 게임, 체크포인트 설정
- `model_loader.py` — VLM 모델 로딩 + LoRA 설정
  - `ModelLoader` — load() -> (model, processor), save_checkpoint(model, path)
- `trajectory_collector.py` — 에피소드 실행 + trajectory 수집
  - `TrajectoryCollector` — collect(model, processor, env, game_id, goal, max_steps) -> dict
  - `frame_to_pil(frame, scale) -> Image` — 프레임을 PIL 이미지로 변환
  - `frame_diff_ratio(prev, curr) -> float` — 프레임 변화 비율
  - `build_prompt_text(processor, image, goal, action_str) -> str` — VLM 프롬프트 생성
  - `predict_action(model, processor, image, goal) -> int` — 모델 액션 예측
- `dpo_trainer.py` — DPO preference learning
  - `DPOTrainer` — collect_preferences(trajectory), train_step(model, ...), cache_ref_log_probs(...)
  - `get_all_action_log_probs(model, processor, image, goal) -> dict[int, Tensor]`
- `rewards.py` — Reward 함수
  - `compute_frame_diff(prev, curr) -> float` — 프레임 변화 비율
  - `step_reward(prev, curr, weight) -> float` — 스텝 코드 기반 reward
  - `combine_rewards(step_r, goal_r, ...) -> float` — 합산 reward
  - `observation_reward(obs: Observation) -> float` — Observer 기반 세밀한 reward
- `evaluator.py` — Claude 기반 goal 달성 평가
  - `Evaluator` — evaluate(before, after, goal), evaluate_episode(...) (LLMClient Protocol 준수)
- `goal_generator.py` — 학습용 goal 생성
  - `GoalGenerator` — generate(game_id) -> str, add_goals(game_id, goals)
- `train_local.py` — DPO 학습 오케스트레이터 (main 진입점)
- `loop.py` — 원격 서버 학습 오케스트레이터
- `server.py` — 원격 GPU 서버 클라이언트
