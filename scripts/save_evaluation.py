#!/usr/bin/env python3
"""Evaluator의 평가 결과를 JSON으로 저장한다.

JSON 스키마를 검증하고, docs/evaluations/에 저장한다.
검증 실패 시 exit 2로 종료.

Usage:
    python scripts/save_evaluation.py --data '{"timestamp": "...", ...}'
    echo '{"timestamp": "..."}' | python scripts/save_evaluation.py
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
EVALUATIONS_DIR = PROJECT_ROOT / "docs" / "evaluations"

REQUIRED_FIELDS = [
    "timestamp",
    "code_review",
    "game_results",
    "failure_classification",
    "failure_detail",
    "recommendations",
    "comparison",
]

CODE_REVIEW_FIELDS = ["tests_passed", "solid_violations", "architecture_issues"]
GAME_RESULTS_FIELDS = ["game_id", "levels_completed", "total_steps", "score", "state"]

VALID_FAILURE_TYPES = [
    "perception_error",
    "planning_error",
    "execution_error",
    "environment_error",
    None,
]


def validate_evaluation(data: dict) -> list[str]:
    """평가 데이터의 JSON 스키마를 검증한다."""
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"필수 필드 누락: '{field}'")

    # code_review 하위 필드
    cr = data.get("code_review")
    if isinstance(cr, dict):
        for field in CODE_REVIEW_FIELDS:
            if field not in cr:
                errors.append(f"code_review 필수 필드 누락: '{field}'")
    elif cr is not None:
        errors.append("'code_review'는 dict여야 합니다")

    # game_results 하위 필드
    gr = data.get("game_results")
    if isinstance(gr, dict):
        for field in GAME_RESULTS_FIELDS:
            if field not in gr:
                errors.append(f"game_results 필수 필드 누락: '{field}'")
    elif gr is not None:
        errors.append("'game_results'는 dict여야 합니다")

    # failure_classification 값 검증
    fc = data.get("failure_classification")
    if fc not in VALID_FAILURE_TYPES:
        errors.append(
            f"유효하지 않은 failure_classification: '{fc}'. "
            f"허용값: {VALID_FAILURE_TYPES}"
        )

    # recommendations는 리스트
    recs = data.get("recommendations")
    if recs is not None and not isinstance(recs, list):
        errors.append("'recommendations'는 리스트여야 합니다")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="평가 결과 저장")
    parser.add_argument("--data", type=str, help="JSON 데이터")
    args = parser.parse_args()

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
    errors = validate_evaluation(data)
    if errors:
        print("평가 결과 검증 실패:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    # 저장
    EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = data.get("timestamp", datetime.now().isoformat())
    safe_ts = timestamp.replace(":", "").replace("-", "").replace("T", "_")[:15]
    filename = f"{safe_ts}.json"
    filepath = EVALUATIONS_DIR / filename

    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"평가 결과 저장 완료: {filepath}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
