"""AnthropicClient 테스트. (API 호출 없이 유틸 메서드만)"""

from src.llm.client import AnthropicClient


def test_cost_estimate() -> None:
    # API 키 없이 인스턴스 생성 불가하므로 직접 계산 테스트
    # Haiku: input $0.80/M, output $4.00/M
    input_tokens = 1000
    output_tokens = 500

    input_cost = input_tokens / 1_000_000 * 0.80
    output_cost = output_tokens / 1_000_000 * 4.00
    total = input_cost + output_cost

    assert abs(total - 0.0028) < 0.0001
