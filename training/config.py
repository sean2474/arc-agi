"""학습 하이퍼파라미터."""

from dataclasses import dataclass


@dataclass
class TrainingConfig:
    # 모델
    model_name: str = "Qwen/Qwen2-VL-7B-Instruct"

    # 서버
    server_url: str = "http://localhost:8000"

    # 학습 루프
    num_episodes: int = 10000
    max_steps_per_episode: int = 200
    eval_interval: int = 5        # N스텝마다 Claude Evaluator 호출

    # Reward
    frame_change_weight: float = 0.5
    goal_reward_weight: float = 0.5

    # RL (GRPO)
    learning_rate: float = 1e-5
    batch_size: int = 4
    grpo_group_size: int = 4      # GRPO에서 한 prompt당 생성할 응답 수
    kl_coeff: float = 0.05

    # 게임
    games: list[str] | None = None  # None이면 전체

    # Claude Evaluator
    evaluator_model: str = "claude-sonnet-4-20250514"

    # 체크포인트
    save_interval: int = 100      # N 에피소드마다 체크포인트 저장
    checkpoint_dir: str = "training/checkpoints"
