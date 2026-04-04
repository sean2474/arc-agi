"""Anthropic API client wrapper.

게임 로직을 모르는 순수 API 래퍼.
prompt_builder가 만든 메시지를 보내고 응답을 반환할 뿐.
"""

import os
from dataclasses import dataclass
from typing import Protocol

import anthropic
from dotenv import load_dotenv


@dataclass
class LLMResponse:
    """LLM 응답."""

    content: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMClient(Protocol):
    """LLM 클라이언트 인터페이스. DIP를 위한 Protocol."""

    def send(self, system: str, messages: list[dict]) -> LLMResponse: ...

    def get_usage_summary(self) -> str: ...


class AnthropicClient:
    """Anthropic API 클라이언트."""

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1024,
    ) -> None:
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    def send(
        self,
        system: str,
        messages: list[dict],
    ) -> LLMResponse:
        """메시지를 보내고 응답을 반환한다.

        messages 형식:
          텍스트: [{"role": "user", "content": "text"}]
          이미지: [{"role": "user", "content": [
              {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
              {"type": "text", "text": "describe this"}
          ]}]
        """
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
        )

        content = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_calls += 1

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
        )

    def get_cost_estimate(self) -> float:
        """누적 비용 추정 (USD)."""
        # Haiku 4.5 pricing
        input_cost = self.total_input_tokens / 1_000_000 * 0.80
        output_cost = self.total_output_tokens / 1_000_000 * 4.00
        return input_cost + output_cost

    def get_usage_summary(self) -> str:
        """사용량 요약 문자열."""
        cost = self.get_cost_estimate()
        return (
            f"Calls: {self.total_calls}, "
            f"Input: {self.total_input_tokens} tokens, "
            f"Output: {self.total_output_tokens} tokens, "
            f"Est. cost: ${cost:.4f}"
        )
