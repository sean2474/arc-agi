"""VLM 모델 로딩 + LoRA 설정."""

from pathlib import Path
from typing import Any

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForImageTextToText, AutoProcessor


class ModelLoader:
    """VLM 모델을 로딩하고 LoRA를 적용한다."""

    def __init__(
        self,
        model_path: str,
        lora_r: int = 16,
        lora_alpha: int = 32,
        lora_dropout: float = 0.05,
        target_modules: list[str] | None = None,
    ) -> None:
        self._model_path = model_path
        self._lora_r = lora_r
        self._lora_alpha = lora_alpha
        self._lora_dropout = lora_dropout
        self._target_modules = target_modules or ["q_proj", "v_proj"]

    def load(self) -> tuple[Any, Any]:
        """모델 + processor를 로딩하고 LoRA를 적용한다.

        Returns:
            (model, processor) 튜플.
        """
        processor = AutoProcessor.from_pretrained(self._model_path)
        base_model = AutoModelForImageTextToText.from_pretrained(
            self._model_path,
            dtype=torch.bfloat16,
            device_map="auto",
        )

        lora_config = LoraConfig(
            r=self._lora_r,
            lora_alpha=self._lora_alpha,
            target_modules=self._target_modules,
            lora_dropout=self._lora_dropout,
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(base_model, lora_config)
        model.print_trainable_parameters()

        return model, processor

    def save_checkpoint(self, model: Any, path: Path) -> None:
        """LoRA 체크포인트를 저장한다."""
        model.save_pretrained(path)
        print(f"  >>> Checkpoint: {path}")
