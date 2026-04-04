"""GPU 서버 — Qwen2-VL-7B 추론 + RL 학습.

클라우드 GPU에서 실행. FastAPI로 /predict, /train 엔드포인트 제공.

Usage (서버):
    python training/server.py --port 8000

Usage (클라이언트, 로컬에서):
    POST http://<server>:8000/predict  {"image": b64, "goal": "..."}
    POST http://<server>:8000/train    {"episodes": [...]}
"""

import argparse
import base64
import io
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── FastAPI 앱 정의 (서버에서만 import) ──

def create_app():
    """FastAPI 앱 생성. GPU 환경에서만 호출."""
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI(title="ARC-AGI-3 Training Server")

    # 모델은 startup에서 로드
    model_state: dict[str, Any] = {
        "model": None,
        "processor": None,
        "episodes_trained": 0,
    }

    class PredictRequest(BaseModel):
        image: str  # base64 PNG
        goal: str
        history: list[dict] = []

    class PredictResponse(BaseModel):
        action: int
        confidence: float

    class TrainRequest(BaseModel):
        episodes: list[dict]  # [{image, goal, action, reward}, ...]

    class TrainResponse(BaseModel):
        loss: float
        updated: bool
        episodes_trained: int

    @app.on_event("startup")
    async def load_model():
        from transformers import AutoModelForImageTextToText, AutoProcessor
        import torch
        import os

        model_name = os.environ.get("MODEL_PATH", "Qwen/Qwen2.5-VL-7B-Instruct")
        logger.info(f"Loading {model_name}...")

        model_state["processor"] = AutoProcessor.from_pretrained(model_name)
        model_state["model"] = AutoModelForImageTextToText.from_pretrained(
            model_name,
            dtype=torch.bfloat16,
            device_map="auto",
        )
        logger.info("Model loaded.")

    @app.post("/predict", response_model=PredictResponse)
    async def predict(req: PredictRequest):
        """프레임 이미지 + goal → 액션 예측."""
        model = model_state["model"]
        processor = model_state["processor"]

        if model is None:
            return PredictResponse(action=1, confidence=0.0)

        import torch
        from PIL import Image

        # base64 → PIL Image
        img_bytes = base64.b64decode(req.image)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        # 프롬프트 구성
        prompt = f"You are playing a game. Goal: {req.goal}\nChoose action: 1=up, 2=down, 3=left, 4=right\nRespond with just the number."

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(
            text=[text],
            images=[image],
            return_tensors="pt",
            padding=True,
        ).to(model.device)

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=10,
                do_sample=True,
                temperature=0.7,
            )

        output_text = processor.batch_decode(
            output_ids[:, inputs.input_ids.shape[1]:],
            skip_special_tokens=True,
        )[0].strip()

        # 액션 파싱
        action = 1
        for ch in output_text:
            if ch in "1234":
                action = int(ch)
                break

        return PredictResponse(action=action, confidence=0.7)

    @app.post("/train", response_model=TrainResponse)
    async def train(req: TrainRequest):
        """에피소드 데이터로 RL 학습 (GRPO)."""
        # TODO: GRPO 구현
        # 현재는 데이터만 받고 학습 안 함 (스텁)
        model_state["episodes_trained"] += len(req.episodes)

        return TrainResponse(
            loss=0.0,
            updated=False,
            episodes_trained=model_state["episodes_trained"],
        )

    @app.get("/status")
    async def status():
        return {
            "model": "qwen2-vl-7b",
            "loaded": model_state["model"] is not None,
            "episodes_trained": model_state["episodes_trained"],
        }

    @app.post("/save_checkpoint")
    async def save_checkpoint():
        # TODO: 체크포인트 저장
        return {"saved": False, "message": "not implemented yet"}

    return app


# ── 클라이언트 (로컬에서 사용) ──

class TrainingServerClient:
    """GPU 서버와 통신하는 클라이언트."""

    def __init__(self, server_url: str = "http://localhost:8000") -> None:
        self._url = server_url.rstrip("/")

    def predict(self, image_b64: str, goal: str, history: list[dict] | None = None) -> tuple[int, float]:
        """프레임 이미지 + goal → (action_id, confidence)."""
        import requests

        resp = requests.post(
            f"{self._url}/predict",
            json={"image": image_b64, "goal": goal, "history": history or []},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["action"], data["confidence"]

    def train(self, episodes: list[dict]) -> dict:
        """에피소드 데이터를 서버에 전송하여 학습."""
        import requests

        resp = requests.post(
            f"{self._url}/train",
            json={"episodes": episodes},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    def get_status(self) -> dict:
        """서버 상태 확인."""
        import requests

        resp = requests.get(f"{self._url}/status", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def is_alive(self) -> bool:
        """서버가 살아있는지 확인."""
        try:
            self.get_status()
            return True
        except Exception:
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2-VL-7B-Instruct",
                        help="모델 경로 (로컬 또는 HF hub)")
    args = parser.parse_args()

    import uvicorn
    import os
    os.environ["MODEL_PATH"] = args.model

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)
