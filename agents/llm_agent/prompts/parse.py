import json
import re


def _strip_json_comments(text: str) -> str:
    """JSON 문자열에서 // 인라인 주석 제거."""
    return re.sub(r"//[^\n]*", "", text)


def parse_llm_response(text: str) -> dict | None:
    """LLM 응답에서 JSON 추출. <think> 태그, 코드블록 등 처리."""
    if not text:
        return None

    # 0. <think>...</think> 태그 제거 (Qwen3 등 thinking 모델)
    think_end = text.find("</think>")
    if think_end != -1:
        text = text[think_end + len("</think>"):]
    elif text.strip().startswith("<think>"):
        # </think>가 없으면 thinking에서 토큰 소진 → JSON 없음
        return None

    text = text.strip()
    if not text:
        return None

    # 1. 코드블록 안의 JSON 추출 (```json ... ``` 또는 ``` ... ```)
    code_block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if code_block:
        try:
            return json.loads(_strip_json_comments(code_block.group(1)))
        except json.JSONDecodeError:
            pass

    # 2. 가장 바깥쪽 { } 찾기 (bracket matching)
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(_strip_json_comments(text[start:i + 1]))
                except json.JSONDecodeError:
                    break

    # 3. 마지막 수단: greedy regex
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(_strip_json_comments(match.group()))
        except json.JSONDecodeError:
            pass

    return None
