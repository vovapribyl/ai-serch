"""The core must admit work using the injected monotonic clock, not wall time."""

import ast
from pathlib import Path

import pytest

from product_search.search.replenishment_contracts import ExecutionWindow
from tests.test_replenishment_contracts import package


class Clock:
    def __init__(self, now):
        self.now = now

    def monotonic(self):
        return self.now


@pytest.mark.parametrize(
    ("now", "expected"), [(10, True), (61.999, True), (62, False), (70, False)]
)
def test_work_respects_deadline_and_cleanup_with_injected_clock(now, expected):
    clock = Clock(now)
    window = ExecutionWindow(package(), clock, started_at=10)
    assert window.can_start(5) is expected


def test_clock_advancing_prevents_another_operation():
    clock = Clock(10)
    window = ExecutionWindow(package(), clock, started_at=10)
    assert window.can_start(5)
    clock.now = 62
    assert not window.can_start(5)


def test_core_dependencies_are_only_policy_or_pure_standard_library():
    root = Path(__file__).parents[1] / "src/product_search/search"
    allowed = {"__future__", "dataclasses", "enum", "math", "re", "typing", "collections"}
    for path in root.glob("*replenishment*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in allowed for a in node.names)
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1
                    assert node.module in {"replenishment_contracts", "replenishment_ports", "nail_contracts"}
                else:
                    assert (node.module or "").split(".")[0] in allowed


@pytest.mark.parametrize("now", [float("nan"), float("inf"), 9, None, True])
def test_invalid_or_reversed_clock_never_admits_work(now):
    assert not ExecutionWindow(package(), Clock(now), started_at=10).can_start(5)


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), None, True])
def test_invalid_operation_budget_never_admits_work(seconds):
    assert not ExecutionWindow(package(), Clock(10), started_at=10).can_start(seconds)
