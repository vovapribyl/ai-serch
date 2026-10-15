"""A transient matching process may clear; unknown or persistent state stays closed."""

from types import SimpleNamespace

import pytest


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.mark.parametrize("transient", [True, False])
def test_interphase_gate_waits_bounded_and_requires_confirmed_absence(tmp_path, transient):
    from tests.support.replenishment_probe import wait_for_probe_quiescence

    clock = Clock()
    calls = []

    def command(argv, **kwargs):
        calls.append(kwargs["timeout"])
        present = clock.now < 0.2 or not transient
        text = f"42 42 python run_replenishment_worker.py {tmp_path}/control.json\n"
        return SimpleNamespace(returncode=0, stdout=text if present else "")

    result = wait_for_probe_quiescence(
        tmp_path, seconds=0.5, command=command, clock=clock, sleep=clock.sleep
    )
    assert result["status"] == ("QUIESCENT" if transient else "PROCESS_TIMEOUT")
    assert 0 < clock.now <= 0.5 and len(calls) > 1
    assert all(0 < value <= 0.5 for value in calls)
    assert result["first_candidates"] == [{"pid": 42, "pgid": 42, "role": "worker"}]
    assert not transient or result["candidates"] == []
    assert str(tmp_path) not in str(result) and "control.json" not in str(result)


@pytest.mark.parametrize("bad", ["command", "malformed"])
def test_unknown_process_observation_never_grants_interphase_admission(tmp_path, bad):
    import subprocess

    from tests.support.replenishment_probe import wait_for_probe_quiescence

    def command(*args, **kwargs):
        if bad == "command":
            raise subprocess.TimeoutExpired("SECRET_COMMAND", 1, stderr="SECRET_DETAIL")
        return SimpleNamespace(returncode=0, stdout="malformed process table")

    result = wait_for_probe_quiescence(tmp_path, seconds=0.5, command=command)
    assert result["status"] == "OBSERVATION_FAILED"
    assert result["check"] == "INTERPHASE_PROCESSES"
    assert "SECRET" not in str(result)


def test_already_quiescent_has_no_sleep_and_ignores_other_roots(tmp_path):
    from tests.support.replenishment_probe import wait_for_probe_quiescence

    result = wait_for_probe_quiescence(
        tmp_path,
        command=lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout="40 40 python run_replenishment_worker.py /another/control.json\n"
        ),
        sleep=lambda _: pytest.fail("already absent: no wait"),
    )
    assert result["status"] == "QUIESCENT" and result["polls"] == 1


def test_absence_returned_after_deadline_does_not_open_gate(tmp_path):
    from tests.support.replenishment_probe import wait_for_probe_quiescence

    clock = Clock()

    def command(*args, **kwargs):
        clock.now += 0.6
        return SimpleNamespace(returncode=0, stdout="")

    result = wait_for_probe_quiescence(
        tmp_path, seconds=0.5, command=command, clock=clock, sleep=clock.sleep
    )
    assert result["status"] == "PROCESS_TIMEOUT"


def test_unrelated_multiline_command_does_not_make_process_table_unknown(tmp_path):
    from tests.support.replenishment_probe import wait_for_probe_quiescence

    result = wait_for_probe_quiescence(
        tmp_path,
        command=lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout="12 12 zsh -c python - <<EOF\nfrom pathlib import Path\nEOF\n",
        ),
    )
    assert result["status"] == "QUIESCENT"
