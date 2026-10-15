import ast
from pathlib import Path

import pytest


def check_core(root):
    allowed = {
        "__future__",
        "dataclasses",
        "enum",
        "collections",
        "math",
        "re",
        "typing",
        "struct",
        "itertools",
    }
    modules = {p.stem: p for p in root.glob("nail_*.py")}
    for name in ("replenishment_contracts", "replenishment_ports"):
        path = root / f"{name}.py"
        if path.exists():
            modules[name] = path
    visited = set()

    def visit(name):
        if name in visited:
            return
        visited.add(name)
        for node in ast.walk(ast.parse(modules[name].read_text())):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in allowed, (name, alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    assert node.level == 1 and module in modules, (name, module)
                    visit(module)
                else:
                    assert module.split(".")[0] in allowed, (name, module)

    for name in modules:
        visit(name)


def test_nail_core_has_no_external_dependencies():
    check_core(Path(__file__).parents[1] / "src/product_search/search")


def test_checker_rejects_transitive_concrete_import_even_in_type_hints(tmp_path):
    (tmp_path / "nail_service.py").write_text("from .nail_contracts import Data\n")
    (tmp_path / "nail_contracts.py").write_text(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from PIL import Image\n"
    )
    with pytest.raises(AssertionError):
        check_core(tmp_path)
