#!/usr/bin/env python3
"""문서 스키마 검증 스크립트.

전략 문서, 평가 보고서, 게임 분석 문서의 포맷을 검증한다.
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"

STRATEGY_REQUIRED_SECTIONS = [
    "## Goal",
    "## Hypothesis",
    "## Approach",
    "## Constraints",
    "## Success Criteria",
]

GAME_ANALYSIS_REQUIRED_SECTIONS = [
    "## Objects",
    "## Rules",
    "## Action Effects",
    "## Level Progression",
    "## Open Questions",
]

EVALUATION_REQUIRED_FIELDS = [
    "timestamp",
    "code_review",
    "game_results",
    "failure_classification",
    "failure_detail",
    "recommendations",
    "comparison",
]

CODE_REVIEW_REQUIRED_FIELDS = [
    "tests_passed",
    "solid_violations",
    "architecture_issues",
]

GAME_RESULTS_REQUIRED_FIELDS = [
    "game_id",
    "levels_completed",
    "total_steps",
    "score",
    "state",
]


def check_markdown_sections(
    filepath: Path, required_sections: list[str]
) -> list[str]:
    """마크다운 파일에 필수 섹션이 있는지 체크."""
    issues: list[str] = []
    if not filepath.exists():
        return [f"{filepath}: 파일이 존재하지 않음"]

    content = filepath.read_text()
    for section in required_sections:
        if section not in content:
            issues.append(f"{filepath}: 필수 섹션 누락 — '{section}'")
    return issues


def check_evaluation_json(filepath: Path) -> list[str]:
    """평가 보고서 JSON 스키마 검증."""
    issues: list[str] = []
    try:
        data = json.loads(filepath.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return [f"{filepath}: JSON 파싱 에러 — {e}"]

    for field in EVALUATION_REQUIRED_FIELDS:
        if field not in data:
            issues.append(f"{filepath}: 필수 필드 누락 — '{field}'")

    if "code_review" in data and isinstance(data["code_review"], dict):
        for field in CODE_REVIEW_REQUIRED_FIELDS:
            if field not in data["code_review"]:
                issues.append(
                    f"{filepath}: code_review 필수 필드 누락 — '{field}'"
                )

    if "game_results" in data and isinstance(data["game_results"], dict):
        for field in GAME_RESULTS_REQUIRED_FIELDS:
            if field not in data["game_results"]:
                issues.append(
                    f"{filepath}: game_results 필수 필드 누락 — '{field}'"
                )

    valid_classifications = [
        "perception_error",
        "planning_error",
        "execution_error",
        "environment_error",
        None,
    ]
    fc = data.get("failure_classification")
    if fc not in valid_classifications:
        issues.append(
            f"{filepath}: 유효하지 않은 failure_classification — '{fc}'"
        )

    return issues


def main() -> int:
    """모든 문서 스키마를 검증한다."""
    all_issues: list[str] = []

    # 전략 문서 검증
    strategy = DOCS_DIR / "strategy" / "current.md"
    if strategy.exists():
        all_issues.extend(
            check_markdown_sections(strategy, STRATEGY_REQUIRED_SECTIONS)
        )

    # 게임 분석 문서 검증
    games_dir = DOCS_DIR / "games"
    if games_dir.exists():
        for game_dir in games_dir.iterdir():
            if game_dir.is_dir():
                analysis = game_dir / "analysis.md"
                if analysis.exists():
                    all_issues.extend(
                        check_markdown_sections(
                            analysis, GAME_ANALYSIS_REQUIRED_SECTIONS
                        )
                    )

    # 평가 보고서 검증
    evals_dir = DOCS_DIR / "evaluations"
    if evals_dir.exists():
        for eval_file in sorted(evals_dir.glob("*.json")):
            all_issues.extend(check_evaluation_json(eval_file))

    if all_issues:
        print(f"문서 스키마 이슈 {len(all_issues)}개:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1
    else:
        print("문서 스키마 검증 통과!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
