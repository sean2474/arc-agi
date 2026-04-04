#!/usr/bin/env python3
"""Planner의 전략 문서를 저장한다.

필수 필드를 검증하고, 이전 전략을 history/로 아카이브한다.
검증 실패 시 exit 2로 종료 (에이전트에게 에러 피드백).

Usage:
    python scripts/save_strategy.py --data '{"goal": "...", ...}'
    echo '{"goal": "..."}' | python scripts/save_strategy.py
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
STRATEGY_DIR = PROJECT_ROOT / "docs" / "strategy"
CURRENT_FILE = STRATEGY_DIR / "current.md"
HISTORY_DIR = STRATEGY_DIR / "history"

REQUIRED_FIELDS = ["goal", "hypothesis", "approach", "constraints", "success_criteria"]


def validate_strategy(data: dict) -> list[str]:
    """전략 데이터의 필수 필드를 검증한다."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"필수 필드 누락: '{field}'")
        elif not data[field]:
            errors.append(f"필드가 비어있음: '{field}'")

    if "approach" in data and not isinstance(data["approach"], list):
        errors.append("'approach'는 리스트여야 합니다")

    if "constraints" in data and not isinstance(data["constraints"], list):
        errors.append("'constraints'는 리스트여야 합니다")

    if "success_criteria" in data and not isinstance(data["success_criteria"], list):
        errors.append("'success_criteria'는 리스트여야 합니다")

    return errors


def format_strategy_md(data: dict) -> str:
    """JSON 데이터를 마크다운 전략 문서로 포맷한다."""
    lines = []
    lines.append(f"## Goal\n\n{data['goal']}\n")
    lines.append(f"## Hypothesis\n\n{data['hypothesis']}\n")

    lines.append("## Approach\n")
    for i, step in enumerate(data["approach"], 1):
        lines.append(f"{i}. {step}")
    lines.append("")

    lines.append("## Constraints\n")
    for c in data["constraints"]:
        lines.append(f"- {c}")
    lines.append("")

    lines.append("## Success Criteria\n")
    for sc in data["success_criteria"]:
        lines.append(f"- [ ] {sc}")
    lines.append("")

    return "\n".join(lines)


def archive_current() -> None:
    """현재 전략을 history/로 아카이브한다."""
    if not CURRENT_FILE.exists():
        return

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = HISTORY_DIR / f"{timestamp}.md"
    shutil.copy2(CURRENT_FILE, archive_path)
    print(f"이전 전략 아카이브: {archive_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="전략 문서 저장")
    parser.add_argument("--data", type=str, help="JSON 데이터")
    args = parser.parse_args()

    # 입력 받기
    if args.data:
        raw = args.data
    else:
        raw = sys.stdin.read()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 에러: {e}", file=sys.stderr)
        return 2

    # 검증
    errors = validate_strategy(data)
    if errors:
        print("전략 문서 검증 실패:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    # 이전 전략 아카이브
    archive_current()

    # 저장
    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
    md_content = format_strategy_md(data)
    CURRENT_FILE.write_text(md_content)
    print(f"전략 저장 완료: {CURRENT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
