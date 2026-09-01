from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[1] / "src" / "product_search"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_core_does_not_depend_on_web_or_infrastructure() -> None:
    for path in (SOURCE_ROOT / "core").glob("*.py"):
        imports = imported_modules(path)
        assert not any(
            module.startswith(("product_search.web", "product_search.infrastructure"))
            for module in imports
        ), path


def test_web_does_not_import_database_implementation() -> None:
    imports = imported_modules(SOURCE_ROOT / "web" / "app.py")
    assert "product_search.infrastructure.database" not in imports
