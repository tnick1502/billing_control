import ast
from pathlib import Path


API_DIR = Path(__file__).resolve().parents[1] / "app" / "api"
REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"


def _is_get_db_dependency(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == "Depends"
        and bool(node.args)
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "get_db"
    )


def test_all_api_db_dependencies_commit_before_response():
    violations: list[str] = []
    dependency_count = 0

    for path in sorted(API_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_get_db_dependency(node):
                continue
            dependency_count += 1
            scope = next((kw.value for kw in node.keywords if kw.arg == "scope"), None)
            if not isinstance(scope, ast.Constant) or scope.value != "function":
                violations.append(f"{path.name}:{node.lineno}")

    assert dependency_count > 0
    assert violations == [], (
        "DB dependency must be Depends(get_db, scope=\"function\") so commit happens "
        f"before the response: {', '.join(violations)}"
    )


def test_fastapi_is_pinned_to_version_with_dependency_scope_support():
    requirements = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    fastapi_lines = [line.strip() for line in requirements if line.strip().startswith("fastapi")]
    assert fastapi_lines == ["fastapi==0.140.2"]
