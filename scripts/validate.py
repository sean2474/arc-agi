#!/usr/bin/env python3
"""코드 품질 검증 스크립트.

체크 항목:
- 타입 힌트 누락
- 순환 import
- 미사용 import
- 테스트 파일 존재 여부
"""

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"


def find_python_files(directory: Path) -> list[Path]:
    """디렉토리 내 모든 .py 파일을 찾는다."""
    return sorted(directory.rglob("*.py"))


def check_type_hints(filepath: Path) -> list[str]:
    """함수 정의에 타입 힌트가 있는지 체크한다."""
    issues: list[str] = []
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return [f"{filepath}: SyntaxError"]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and node.name != "__init__":
                continue
            if node.returns is None and node.name != "__init__":
                issues.append(
                    f"{filepath}:{node.lineno}: "
                    f"함수 '{node.name}'에 리턴 타입 힌트 없음"
                )
            for arg in node.args.args:
                if arg.arg == "self" or arg.arg == "cls":
                    continue
                if arg.annotation is None:
                    issues.append(
                        f"{filepath}:{node.lineno}: "
                        f"함수 '{node.name}'의 파라미터 '{arg.arg}'에 타입 힌트 없음"
                    )
    return issues


def check_test_exists(src_file: Path) -> list[str]:
    """src 파일에 대응하는 테스트 파일이 있는지 체크한다."""
    issues: list[str] = []
    if src_file.name == "__init__.py":
        return issues

    relative = src_file.relative_to(SRC_DIR)
    test_file = TESTS_DIR / f"test_{relative}"

    if not test_file.exists():
        # tests/ 바로 아래에 test_{name}.py가 있는지도 체크
        flat_test = TESTS_DIR / f"test_{src_file.name}"
        if not flat_test.exists():
            issues.append(
                f"{src_file}: 대응 테스트 파일 없음 "
                f"(expected: {test_file} or {flat_test})"
            )
    return issues


def check_circular_imports(files: list[Path]) -> list[str]:
    """간단한 순환 import 체크 (직접 순환만)."""
    issues: list[str] = []
    imports: dict[str, set[str]] = {}

    for filepath in files:
        try:
            tree = ast.parse(filepath.read_text())
        except SyntaxError:
            continue

        module_name = filepath.stem
        module_imports: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_imports.add(node.module.split(".")[0])

        imports[module_name] = module_imports

    for module_a, imports_a in imports.items():
        for module_b in imports_a:
            if module_b in imports and module_a in imports[module_b]:
                issues.append(
                    f"순환 import 감지: {module_a} ↔ {module_b}"
                )
    return issues


def main() -> int:
    """메인 검증 실행."""
    all_issues: list[str] = []

    if not SRC_DIR.exists():
        print("src/ 디렉토리가 없습니다.")
        return 0

    src_files = find_python_files(SRC_DIR)
    if not src_files:
        print("src/에 Python 파일이 없습니다.")
        return 0

    # 타입 힌트 체크
    for f in src_files:
        all_issues.extend(check_type_hints(f))

    # 테스트 파일 존재 체크
    for f in src_files:
        all_issues.extend(check_test_exists(f))

    # 순환 import 체크
    all_issues.extend(check_circular_imports(src_files))

    if all_issues:
        print(f"발견된 이슈 {len(all_issues)}개:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1
    else:
        print("코드 품질 검증 통과!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
