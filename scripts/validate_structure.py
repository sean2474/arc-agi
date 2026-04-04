#!/usr/bin/env python3
"""structure.md와 실제 코드의 일치 여부를 검증한다.

체크 항목:
- structure.md에 있는데 실제 파일이 없는 경우
- 실제 파일이 있는데 structure.md에 없는 경우
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
STRUCTURE_FILE = PROJECT_ROOT / "docs" / "structure.md"


def parse_structure_files(content: str) -> set[str]:
    """structure.md에서 파일 경로를 추출한다."""
    files: set[str] = set()
    current_dir = ""

    for line in content.splitlines():
        # ## src/module_name/ 형태
        dir_match = re.match(r"^##\s+(src/\S+)", line)
        if dir_match:
            current_dir = dir_match.group(1).rstrip("/")
            continue

        # - `filename.py` 형태
        file_match = re.match(r"^-\s+`(\S+\.py)`", line)
        if file_match and current_dir:
            filepath = f"{current_dir}/{file_match.group(1)}"
            files.add(filepath)

    return files


def get_actual_files() -> set[str]:
    """src/ 내 실제 Python 파일 목록을 가져온다."""
    if not SRC_DIR.exists():
        return set()

    files: set[str] = set()
    for f in SRC_DIR.rglob("*.py"):
        if f.name == "__init__.py":
            continue
        relative = str(f.relative_to(PROJECT_ROOT))
        files.add(relative)
    return files


def main() -> int:
    """structure.md와 실제 코드 일치를 검증한다."""
    if not STRUCTURE_FILE.exists():
        print("docs/structure.md가 없습니다.")
        return 0

    content = STRUCTURE_FILE.read_text()
    if not content.strip():
        print("docs/structure.md가 비어있습니다.")
        return 0

    documented = parse_structure_files(content)
    actual = get_actual_files()

    issues: list[str] = []

    # structure.md에 있는데 실제 파일이 없는 경우
    for f in sorted(documented - actual):
        issues.append(f"structure.md에 있지만 파일 없음: {f}")

    # 실제 파일이 있는데 structure.md에 없는 경우
    for f in sorted(actual - documented):
        issues.append(f"파일이 있지만 structure.md에 미등록: {f}")

    if issues:
        print(f"Structure 일치 이슈 {len(issues)}개:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    else:
        print("Structure 일치 검증 통과!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
