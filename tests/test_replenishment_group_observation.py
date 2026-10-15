"""Unknown group visibility must never be accepted as confirmed termination."""

import os
import time
from types import SimpleNamespace

from product_search.infrastructure.replenishment_supervisor import OwnedProcesses


def registry():
    owned = OwnedProcesses.__new__(OwnedProcesses)
    owned.clock = time.monotonic
    owned._children = [(SimpleNamespace(pid=12345, poll=lambda: -15), object())]
    return owned


def test_transient_permission_denial_waits_for_positive_absence(monkeypatch):
    calls = []

    def observe(pgid, sig):
        calls.append((pgid, sig))
        assert sig == 0  # Never signal an already reaped leader's group.
        if len(calls) <= 2:
            raise PermissionError(1, "private detail")
        raise ProcessLookupError(3, "absent")

    monkeypatch.setattr(os, "killpg", observe)
    owned = registry()
    assert owned.stop(time.monotonic() + 1, 0.1, 0.1) is True
    assert len(calls) >= 3 and not owned._children


def test_persistent_permission_denial_never_confirms_or_releases_registry(monkeypatch):
    calls = []

    def observe(pgid, sig):
        calls.append(sig)
        assert sig == 0
        raise PermissionError(1, "private detail")

    monkeypatch.setattr(os, "killpg", observe)
    owned = registry()
    original = list(owned._children)
    assert owned.stop(time.monotonic() + 0.05, 0.01, 0.01) is False
    assert owned._children == original and calls and set(calls) == {0}
