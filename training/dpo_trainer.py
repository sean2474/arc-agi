"""DPO 학습."""

import random
from typing import Any

import torch
import torch.nn.functional as F
from PIL import Image

from training.trajectory_collector import build_prompt_text


def get_all_action_log_probs(
    model: Any,
    processor: Any,
    image: Image.Image,
    goal: str,
) -> dict[int, torch.Tensor]:
    """4개 액션 모두의 log probability를 한번에 계산한다."""
    text = build_prompt_text(processor, image, goal)
    inputs = processor(
        text=[text], images=[image], return_tensors="pt", padding=True,
    )
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    if model.training:
        outputs = model(**inputs)
    else:
        with torch.no_grad():
            outputs = model(**inputs)

    # 마지막 토큰의 logits -> 다음 토큰 분포
    last_logits = outputs.logits[:, -1, :]
    log_probs = F.log_softmax(last_logits, dim=-1)

    result: dict[int, torch.Tensor] = {}
    for action_id in range(1, 5):
        token_id = processor.tokenizer.encode(
            str(action_id), add_special_tokens=False,
        )[-1]
        result[action_id] = log_probs[:, token_id]

    return result


class DPOTrainer:
    """DPO preference learning."""

    def __init__(self, beta: float = 0.1) -> None:
        self._beta = beta

    def collect_preferences(self, trajectory: list[dict]) -> list[dict]:
        """trajectory에서 preference 쌍을 생성한다.

        같은 프레임에서 reward가 높은 액션 vs 낮은 액션 쌍을 만든다.
        """
        if len(trajectory) < 2:
            return []

        pairs: list[dict] = []

        # 흥미로운 스텝만 선택 (reward가 높거나 낮은 것)
        sorted_steps = sorted(
            trajectory, key=lambda x: abs(x["reward"]), reverse=True,
        )
        key_steps = sorted_steps[:max(3, len(sorted_steps) // 4)]

        for step_data in key_steps:
            frame_raw = step_data.get("frame_raw")
            if frame_raw is None:
                continue

            taken_action = step_data["action"]
            taken_reward = step_data["reward"]
            goal = step_data["goal"]
            image = step_data["image"]

            if taken_reward > 0:
                other_action = random.choice(
                    [a for a in [1, 2, 3, 4] if a != taken_action],
                )
                pairs.append({
                    "image": image,
                    "goal": goal,
                    "chosen_action": taken_action,
                    "rejected_action": other_action,
                })
            elif taken_reward < -0.05:
                other_action = random.choice(
                    [a for a in [1, 2, 3, 4] if a != taken_action],
                )
                pairs.append({
                    "image": image,
                    "goal": goal,
                    "chosen_action": other_action,
                    "rejected_action": taken_action,
                })

        return pairs

    def cache_ref_log_probs(
        self,
        model: Any,
        processor: Any,
        pairs: list[dict],
        cache: dict[int, dict[int, torch.Tensor]],
    ) -> None:
        """ref model log probs를 캐시한다."""
        for pair in pairs:
            cache_key = id(pair["image"])
            if cache_key not in cache:
                with torch.no_grad():
                    model.eval()
                    ref_lps = get_all_action_log_probs(
                        model, processor, pair["image"], pair["goal"],
                    )
                    cache[cache_key] = {
                        k: v.detach().clone() for k, v in ref_lps.items()
                    }

    def train_step(
        self,
        model: Any,
        processor: Any,
        pairs: list[dict],
        optimizer: torch.optim.Optimizer,
        ref_log_probs_cache: dict[int, dict[int, torch.Tensor]],
    ) -> float:
        """DPO 학습 스텝.

        ref_model 대신 캐시된 ref log probs 사용 (메모리 절약).
        """
        if not pairs:
            return 0.0

        model.train()
        optimizer.zero_grad()
        total_loss = 0.0
        valid_pairs = 0

        for pair in pairs:
            image = pair["image"]
            goal = pair["goal"]
            chosen = pair["chosen_action"]
            rejected = pair["rejected_action"]

            # 현재 모델의 log probs
            action_logps = get_all_action_log_probs(
                model, processor, image, goal,
            )
            chosen_logp = action_logps[chosen]
            rejected_logp = action_logps[rejected]

            # ref 모델 log probs (캐시에서, 없으면 uniform 가정)
            cache_key = id(image)
            if cache_key in ref_log_probs_cache:
                ref_probs = ref_log_probs_cache[cache_key]
                ref_chosen_logp = ref_probs[chosen]
                ref_rejected_logp = ref_probs[rejected]
            else:
                # uniform prior: log(0.25) = -1.386
                ref_chosen_logp = torch.tensor(
                    -1.386, device=chosen_logp.device,
                )
                ref_rejected_logp = torch.tensor(
                    -1.386, device=chosen_logp.device,
                )

            # DPO loss
            logits = self._beta * (
                (chosen_logp - ref_chosen_logp)
                - (rejected_logp - ref_rejected_logp)
            )
            loss = -F.logsigmoid(logits).mean()

            if not torch.isnan(loss):
                loss.backward()
                total_loss += loss.item()
                valid_pairs += 1

        if valid_pairs > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

        optimizer.zero_grad()
        model.eval()

        return total_loss / max(valid_pairs, 1)
